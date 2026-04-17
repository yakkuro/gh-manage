"""Retry engine + rate-limit probe for gh CLI transport.

This module owns the retry policy for `run_gh` / `run_gh_api`. It is
intentionally separate from github_client.py so the transport layer
stays focused on classification and the retry policy is easy to audit
in isolation.

Design contract (spec §1):
  - Rate-limit reset probe is NON-RECURSIVE: it issues exactly one
    subprocess call and never re-enters retry_gh. Probe failure →
    caller falls back to a 15s fixed sleep.
  - Retry log lines are emitted to stderr for CI audit trails.
  - All config is via env vars, read at retry time (not module import),
    so tests can override per-call.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TypeVar

from gh_manage.github_client import GhRateLimitError, GhTransientError

T = TypeVar("T")


def _fetch_rate_limit_reset() -> datetime | None:
    """Probe `gh api rate_limit` for the core reset timestamp.

    Returns None on ANY failure (subprocess error, non-zero exit,
    malformed JSON, missing keys, timeout). Callers treat None as
    "fall back to fixed sleep". Never raises.

    Does NOT go through retry_gh — a rate-limit probe during retry
    must not recurse or we risk infinite loops when the probe itself
    hits rate-limit.
    """
    try:
        result = subprocess.run(
            ["gh", "api", "rate_limit"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10.0,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return None

    try:
        payload = json.loads(result.stdout)
        reset_ts = payload["resources"]["core"]["reset"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None

    try:
        return datetime.fromtimestamp(int(reset_ts), tz=timezone.utc)
    except (ValueError, OverflowError, OSError, TypeError):
        return None


def _read_int_env(
    name: str, default: int, *, minimum: int = 1, maximum: int = 10
) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, v))


def _read_float_env(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        v = float(raw)
    except ValueError:
        return default
    return max(minimum, v)


def _now() -> datetime:
    """Wall-clock now. Patched by tests."""
    return datetime.now(timezone.utc)


def retry_gh(
    fn: Callable[[], T],
    *,
    endpoint: str,
    max_attempts: int | None = None,
    rate_limit_wait_max: float | None = None,
) -> T:
    """Run fn with retry on GhTransientError and GhRateLimitError.

    See module docstring for the policy. Rate-limit handling:
    - Probe gh api rate_limit for reset timestamp.
    - If reset within rate_limit_wait_max seconds, sleep for
      (reset - now) + uniform(0, min(10, wait*0.3)) (anti-herd jitter)
      and retry ONCE.
    - If reset beyond window OR probe failed with partial info, raise
      a FRESH GhRateLimitError with reset_at populated, chained via
      `from` to the original.
    - If probe returns None (any failure), fall back to 15s fixed
      sleep + [rate-limit-probe-failed] stderr log, then retry.

    Rate-limit retry is ONE shot — if the retry also raises rate-limit,
    that second one propagates (not re-retried via rate-limit path).
    """
    if max_attempts is None:
        max_attempts = _read_int_env("GH_MANAGE_MAX_RETRIES", 3)
    if rate_limit_wait_max is None:
        rate_limit_wait_max = _read_float_env("GH_MANAGE_RATE_LIMIT_WAIT_MAX", 60.0)

    attempt = 0
    rate_limit_retried = False
    while True:
        try:
            return fn()
        except GhTransientError as e:
            if attempt >= max_attempts:
                raise
            attempt += 1
            base = 2 ** (attempt - 1)
            wait = base + random.uniform(0, base * 0.5)
            print(
                f"[retry {attempt}/{max_attempts}] {endpoint} "
                f"(GhTransientError status={e.status_code}) wait={wait:.2f}s",
                file=sys.stderr,
            )
            time.sleep(wait)
        except GhRateLimitError as e:
            if rate_limit_retried:
                # Already retried once — propagate.
                raise
            rate_limit_retried = True
            reset_at = _fetch_rate_limit_reset()
            if reset_at is None:
                if rate_limit_wait_max <= 0:
                    # Wait explicitly disabled — propagate fresh without reset info.
                    raise GhRateLimitError(
                        str(e),
                        status_code=e.status_code,
                        reset_at=None,
                    ) from e
                # Probe failure fallback.
                print(
                    f"[rate-limit-probe-failed] endpoint={endpoint} fallback_wait=15s",
                    file=sys.stderr,
                )
                time.sleep(15.0)
                continue
            wait = (reset_at - _now()).total_seconds()
            if wait > rate_limit_wait_max or wait <= 0:
                # Reset too far in the future (or already past, probe stale).
                raise GhRateLimitError(
                    str(e),
                    status_code=e.status_code,
                    reset_at=reset_at,
                ) from e
            jitter = random.uniform(0, min(10.0, wait * 0.3))
            total_wait = wait + jitter
            print(
                f"[retry rate-limit] {endpoint} "
                f"(GhRateLimitError status={e.status_code}) "
                f"wait={total_wait:.2f}s reset={reset_at.isoformat()}",
                file=sys.stderr,
            )
            time.sleep(total_wait)
