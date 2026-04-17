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
    except (ValueError, OverflowError, OSError):
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


def retry_gh(
    fn: Callable[[], T],
    *,
    endpoint: str,
    max_attempts: int | None = None,
    rate_limit_wait_max: float | None = None,
) -> T:
    """Run fn with retry on GhTransientError and GhRateLimitError.

    Transient errors: exponential backoff 1s → 2s → 4s with 0-50%
    multiplicative jitter (sleep in [base, base*1.5)).

    Rate-limit errors: handled in Task 7 (this task's implementation
    re-raises immediately to keep the commit focused).

    Env var overrides:
      - GH_MANAGE_MAX_RETRIES (default 3, clamped to [1, 10])
      - GH_MANAGE_RATE_LIMIT_WAIT_MAX (default 60.0, min 0)
    """
    if max_attempts is None:
        max_attempts = _read_int_env("GH_MANAGE_MAX_RETRIES", 3)
    if rate_limit_wait_max is None:
        rate_limit_wait_max = _read_float_env("GH_MANAGE_RATE_LIMIT_WAIT_MAX", 60.0)

    attempt = 0
    while True:
        try:
            return fn()
        except GhTransientError as e:
            if attempt >= max_attempts:
                raise
            attempt += 1
            base = 2 ** (attempt - 1)  # 1, 2, 4 for attempts 1, 2, 3
            wait = base + random.uniform(0, base * 0.5)
            print(
                f"[retry {attempt}/{max_attempts}] {endpoint} "
                f"(GhTransientError status={e.status_code}) wait={wait:.2f}s",
                file=sys.stderr,
            )
            time.sleep(wait)
        except GhRateLimitError:
            # Rate-limit handling added in Task 7. For now, re-raise.
            raise
