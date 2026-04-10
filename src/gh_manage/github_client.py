"""gh CLI subprocess transport + error hierarchy.

All `gh` subprocess invocations for gh-manage go through this module.
Error handling maps `gh api` failures to a typed GhError hierarchy with
actionable messages.

Resource-specific helpers (label CRUD, protection CRUD, etc.) live in
sibling modules under gh_manage.github_api.* — this file owns ONLY the
generic transport + error classification layer.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, NoReturn


class GhError(Exception):
    """Base class for gh CLI subprocess failures. Never raised directly."""


class GhNotInstalledError(GhError):
    """`gh` CLI missing on PATH."""


class GhAuthError(GhError):
    """Authentication failure — 401 or `gh auth` not logged in."""


class GhNotFoundError(GhError):
    """404 — repository or resource missing."""


class GhPermissionError(GhError):
    """403 — token lacks required scope."""


class GhRateLimitError(GhError):
    """429 — GitHub API rate limit exhausted."""


class GhAPIError(GhError):
    """Other non-2xx response (catch-all)."""


def _raise_classified_error(*, endpoint: str, returncode: int, stderr: str) -> NoReturn:
    """Classify `gh` subprocess stderr into a typed GhError subclass.

    Classification order matters: rate limit first (its message may contain
    HTTP codes), then specific codes, then catch-all.
    """
    stderr_lower = stderr.lower()

    if "rate limit" in stderr_lower:
        raise GhRateLimitError(
            f"GitHub API rate limit exceeded while calling {endpoint}. "
            f"Wait for the reset window (see `gh api rate_limit`) and retry."
        )
    if "http 404" in stderr_lower or "not found" in stderr_lower:
        raise GhNotFoundError(
            f"GitHub API returned 404 for {endpoint}. "
            f"Check the resource name and your auth status with `gh auth status`."
        )
    if (
        "bad credentials" in stderr_lower
        or "not logged in" in stderr_lower
        or "http 401" in stderr_lower
    ):
        raise GhAuthError(
            "The `gh` CLI is not authenticated or the token is invalid. "
            "Run `gh auth login` (or `gh auth refresh`) and try again."
        )
    if "http 403" in stderr_lower or "forbidden" in stderr_lower:
        raise GhPermissionError(
            f"Permission denied on {endpoint}. "
            f"Your `gh` token may lack the required scope. "
            f"Run `gh auth refresh -s repo` to add `repo` scope."
        )

    raise GhAPIError(
        f"GitHub API call failed: {endpoint} (exit {returncode}). "
        f"stderr: {stderr.strip()[:500]}. "
        f"Re-run with `GH_DEBUG=api` to see the full request/response."
    )


def run_gh(args: list[str]) -> str:
    """Run `gh <args>` and return stdout.

    Raises GhNotInstalledError if gh is not on PATH.
    Raises a GhError subclass on non-zero exit (classified by stderr).
    """
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise GhNotInstalledError(
            "The `gh` CLI is required but was not found on PATH. "
            "Install it from https://cli.github.com/ and run `gh auth login`."
        ) from e

    if result.returncode == 0:
        return result.stdout

    _raise_classified_error(
        endpoint=" ".join(args),
        returncode=result.returncode,
        stderr=result.stderr,
    )


def run_gh_api(
    endpoint: str,
    method: str = "GET",
    fields: dict[str, str] | None = None,
    paginate: bool = False,
) -> Any:
    """Run `gh api <endpoint>` and return parsed JSON.

    Builds argv as:
      gh api <endpoint> [-X METHOD] [-f key=value ...] [--paginate]
    """
    args = ["api", endpoint]
    if method != "GET":
        args.extend(["-X", method])
    if fields:
        for key, value in fields.items():
            args.extend(["-f", f"{key}={value}"])
    if paginate:
        args.append("--paginate")

    stdout = run_gh(args)
    if not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise GhAPIError(
            f"GitHub API returned invalid JSON for {endpoint}: {e}. "
            f"This may indicate a network issue, truncated response, or API "
            f"format change. Re-run with `GH_DEBUG=api` to inspect the raw "
            f"response."
        ) from e
