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
import subprocess
from datetime import datetime, timezone


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
