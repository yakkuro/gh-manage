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
import re
import subprocess
from typing import Any, NoReturn

_HTTP_STATUS_RE = re.compile(r"\(HTTP (\d{3})\)")
_RATE_LIMIT_MARKERS = (
    "api rate limit",
    "secondary rate limit",
    "abuse detection",
)
_NETWORK_MARKERS = (
    "dial tcp",
    "no such host",
    "connection refused",
    "i/o timeout",
    "context deadline exceeded",
)


class GhError(Exception):
    """Base class for gh CLI subprocess failures. Never raised directly.

    Subclasses populate status_code when classification came from a parsed
    HTTP status (Path A). Network-level failures (Path B) leave it None.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


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


class GhTransientError(GhAPIError):
    """Retry-eligible failures — 5xx from GitHub or network-level (no response).

    Inherits GhAPIError so existing `except GhAPIError` catch clauses
    transparently catch transient failures. The retry layer in
    gh_manage.github_retry uses `isinstance(e, (GhTransientError,
    GhRateLimitError))` as its cheap retry predicate.
    """


def _raise_classified_error(*, endpoint: str, returncode: int, stderr: str) -> NoReturn:
    """Classify `gh` subprocess stderr into a typed GhError subclass.

    Path A: If `(HTTP <code>)` is present in stderr, dispatch by the
    parsed status code (with a rate-limit body inspection for 403s).

    Path B: Otherwise, check known network-level markers; fall back to
    GhAPIError with status_code=None if nothing matches.
    """
    stderr_lower = stderr.lower()
    m = _HTTP_STATUS_RE.search(stderr)

    if m is not None:
        # Path A
        code = int(m.group(1))
        if code == 401:
            raise GhAuthError(
                "The `gh` CLI is not authenticated or the token is invalid. "
                "Run `gh auth login` (or `gh auth refresh`) and try again.",
                status_code=code,
            )
        if code == 403:
            if any(marker in stderr_lower for marker in _RATE_LIMIT_MARKERS):
                raise GhRateLimitError(
                    f"GitHub API rate limit exceeded while calling {endpoint}. "
                    f"Wait for the reset window (see `gh api rate_limit`) and retry.",
                    status_code=code,
                )
            raise GhPermissionError(
                f"Permission denied on {endpoint}. "
                f"Your `gh` token may lack the required scope. "
                f"Run `gh auth refresh -s repo` to add `repo` scope.",
                status_code=code,
            )
        if code == 404:
            raise GhNotFoundError(
                f"GitHub API returned 404 for {endpoint}. "
                f"Check the resource name and your auth status with `gh auth status`.",
                status_code=code,
            )
        if code == 429:
            raise GhRateLimitError(
                f"GitHub API rate limit exceeded (HTTP 429) while calling {endpoint}. "
                f"Wait for the reset window (see `gh api rate_limit`) and retry.",
                status_code=code,
            )
        if code in (500, 502, 503, 504):
            raise GhTransientError(
                f"GitHub API returned transient HTTP {code} for {endpoint}. "
                f"This is typically a temporary upstream issue.",
                status_code=code,
            )
        raise GhAPIError(
            f"GitHub API call failed: {endpoint} (HTTP {code}). "
            f"stderr: {stderr.strip()[:500]}. "
            f"Re-run with `GH_DEBUG=api` to see the full request/response.",
            status_code=code,
        )

    # Path B — no HTTP status parsed
    if any(marker in stderr_lower for marker in _NETWORK_MARKERS):
        raise GhTransientError(
            f"Network-level failure while calling {endpoint}: "
            f"{stderr.strip()[:200]}. Check connectivity and retry.",
            status_code=None,
        )

    raise GhAPIError(
        f"GitHub API call failed: {endpoint} (exit {returncode}). "
        f"stderr: {stderr.strip()[:500]}. "
        f"Re-run with `GH_DEBUG=api` to see the full request/response.",
        status_code=None,
    )


def run_gh(args: list[str], *, stdin_input: str | None = None) -> str:
    """Run `gh <args>` and return stdout.

    `stdin_input`, if provided, is piped into the subprocess stdin. Used
    by `run_gh_api` when a JSON body is sent via `--input -`.

    Raises GhNotInstalledError if gh is not on PATH.
    Raises a GhError subclass on non-zero exit (classified by stderr).
    """
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            check=False,
            input=stdin_input,
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
    body: dict[str, Any] | None = None,
) -> Any:
    """Run `gh api <endpoint>` and return parsed JSON.

    For non-GET requests with a JSON body, pass `body` as a dict. It is
    serialized with `json.dumps` and piped to `gh api --input -`, which
    avoids the type coercion quirks of `-f key=value` (which always sends
    string values even for booleans/numbers/nested objects).

    Builds argv as:
      gh api <endpoint> [-X METHOD] [--input -]
    """
    args = ["api", endpoint]
    if method != "GET":
        args.extend(["-X", method])

    stdin_input: str | None = None
    if body is not None:
        args.extend(["--input", "-"])
        stdin_input = json.dumps(body)

    stdout = run_gh(args, stdin_input=stdin_input)
    if not stdout.strip():
        if method in ("GET", "DELETE"):
            return None
        raise GhAPIError(
            f"GitHub API returned empty response for {method} {endpoint}. "
            f"This is unexpected for {method} requests, which should return the "
            f"created/updated resource. Re-run with `GH_DEBUG=api` to inspect "
            f"the raw response."
        )
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise GhAPIError(
            f"GitHub API returned invalid JSON for {endpoint}: {e}. "
            f"This may indicate a network issue, truncated response, or API "
            f"format change. Re-run with `GH_DEBUG=api` to inspect the raw "
            f"response."
        ) from e
