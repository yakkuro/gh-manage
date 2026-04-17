# Theme A Resilience Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden `gh` CLI transport (HTTP-status-first classifier + retry layer with anti-herd jitter) and parallelize `gh-manage drift --all` with a configurable worker pool, so 20+ repo scans survive transient failures and rate-limit pressure.

**Architecture:** Two sequential PRs. PR 1 (`cli/v1.3.0`) refactors `src/gh_manage/github_client.py` classifier to a Path A (HTTP) / Path B (network) structure, adds `GhTransientError` + `.status_code` attribute, and wraps `run_gh` with a new `retry_gh` engine (`src/gh_manage/github_retry.py`). PR 2 (`cli/v1.4.0`) refactors `_scan_all_repos` in `src/gh_manage/commands/drift.py` to `ThreadPoolExecutor` with a `--concurrency N` CLI flag and main-thread-only output emission. PR 2 depends on PR 1 being merged and tagged first.

**Tech Stack:** Python 3.12, `uv`, `click` 8.x, `pytest` + `pytest-mock`, `concurrent.futures.ThreadPoolExecutor` (stdlib), `ruff` 0.8.0 (pinned to match reusable workflow), `mypy` 1.12, `gh` CLI subprocess.

**Spec:** [`docs/specs/2026-04-17-theme-a-resilience-pack-design.md`](../specs/2026-04-17-theme-a-resilience-pack-design.md)

**Related issues:** [#47](https://github.com/yakkuro/gh-manage/issues/47) (Theme A umbrella), [#27](https://github.com/yakkuro/gh-manage/issues/27) (Phase 10 rollout)

---

## File structure (locked in by this plan)

**PR 1 touches:**
- Modify: `src/gh_manage/github_client.py` — replace classifier, add `GhTransientError`, `.status_code` kwarg on base; wrap `run_gh` with `retry_gh`.
- Create: `src/gh_manage/github_retry.py` — retry engine (`retry_gh`, `_fetch_rate_limit_reset`, retry logging, env-var config).
- Modify: `tests/unit/github_client/test_github_client.py` — expanded classifier table, canary fixture.
- Create: `tests/unit/github_client/test_github_retry.py` — retry policy tests.
- Modify: `src/gh_manage/__init__.py` (version) — bump to `1.3.0` at release task.

**PR 2 touches:**
- Modify: `src/gh_manage/commands/drift.py` — `_scan_all_repos` refactor; `--concurrency` option on `drift` command.
- Create: `tests/unit/commands/test_drift.py` — parallel execution tests. (The file does NOT currently exist; other command tests live next to it.)
- Modify: `src/gh_manage/__init__.py` (version) — bump to `1.4.0` at release task.

Both PRs use branches cut from `main` (for PR 2, after PR 1 is merged).

---

## Prerequisite: branch setup

- [ ] **Step 0.1: Rename the current spec branch to the PR 1 working branch**

You are currently on `feat/theme-a-resilience-spec` with two commits that added the spec. Rename in-place so the same branch becomes PR 1:

```bash
git branch -m feat/theme-a-resilience-spec feat/resilience-pr1-transport-retry
```

Verify:
```bash
git branch --show-current
# Expected: feat/resilience-pr1-transport-retry
```

- [ ] **Step 0.2: Add this plan document to the branch**

The plan file is being written now. Stage and commit it to the PR 1 branch so implementation tasks run on the same branch.

```bash
git add docs/plans/2026-04-17-theme-a-resilience-pack-plan.md
git commit -m "docs: add Theme A resilience pack implementation plan"
```

---

# PR 1: Transport Resilience (`cli/v1.3.0`)

Branch: `feat/resilience-pr1-transport-retry`

Release tag target: `cli/v1.3.0`

## Task 1: Add `status_code` kwarg to `GhError` and subclasses (no behavior change yet)

**Files:**
- Modify: `src/gh_manage/github_client.py:19-44` — base class + subclasses
- Test: `tests/unit/github_client/test_github_client.py` — append new tests

**Rationale:** Introducing the attribute first (without touching the classifier) lets us keep commits small and lets every classifier test assert `status_code` from Task 2 onward.

- [ ] **Step 1.1: Write the failing test**

Append to `tests/unit/github_client/test_github_client.py`:

```python
# Task 1: status_code attribute on base GhError
def test_gh_error_base_accepts_status_code_kwarg() -> None:
    from gh_manage.github_client import GhError

    e = GhError("boom", status_code=503)
    assert str(e) == "boom"
    assert e.status_code == 503


def test_gh_error_status_code_defaults_to_none() -> None:
    from gh_manage.github_client import GhError

    e = GhError("boom")
    assert e.status_code is None


def test_gh_error_subclasses_accept_status_code() -> None:
    from gh_manage.github_client import GhAuthError, GhNotFoundError

    assert GhAuthError("x", status_code=401).status_code == 401
    assert GhNotFoundError("x", status_code=404).status_code == 404
```

- [ ] **Step 1.2: Run the test to confirm Red**

```bash
uv run pytest tests/unit/github_client/test_github_client.py::test_gh_error_base_accepts_status_code_kwarg -v
```
Expected: FAIL with `TypeError: GhError.__init__() got an unexpected keyword argument 'status_code'` (or similar).

- [ ] **Step 1.3: Implement the minimal change**

Edit `src/gh_manage/github_client.py` — replace the base class definition:

```python
class GhError(Exception):
    """Base class for gh CLI subprocess failures. Never raised directly.

    Subclasses populate status_code when classification came from a parsed
    HTTP status (Path A). Network-level failures (Path B) leave it None.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
```

Other subclasses (`GhNotInstalledError`, `GhAuthError`, `GhNotFoundError`, `GhPermissionError`, `GhRateLimitError`, `GhAPIError`) stay unchanged — they inherit `__init__`.

- [ ] **Step 1.4: Run the new tests + full suite**

```bash
uv run pytest tests/unit/github_client/ -v
uv run pytest -q
```
Expected: new tests PASS; full suite still green (no existing call site breaks because `message` remains positional).

- [ ] **Step 1.5: Commit**

```bash
git add src/gh_manage/github_client.py tests/unit/github_client/test_github_client.py
git commit -m "feat(github_client): add status_code kwarg to GhError base

Foundation for Path-A HTTP-status-first classifier (spec §1). No behavior
change: existing callers keep working, status_code defaults to None."
```

---

## Task 2: Add `GhTransientError` subclass (for retry eligibility)

**Files:**
- Modify: `src/gh_manage/github_client.py` — append new class after `GhAPIError`
- Test: `tests/unit/github_client/test_github_client.py`

- [ ] **Step 2.1: Write the failing test**

```python
# Task 2: GhTransientError
def test_gh_transient_error_is_ghapierror_subclass() -> None:
    from gh_manage.github_client import GhAPIError, GhError, GhTransientError

    assert issubclass(GhTransientError, GhAPIError)
    assert issubclass(GhTransientError, GhError)


def test_gh_transient_error_accepts_status_code() -> None:
    from gh_manage.github_client import GhTransientError

    e = GhTransientError("temp 503", status_code=503)
    assert e.status_code == 503

    e_net = GhTransientError("network", status_code=None)
    assert e_net.status_code is None
```

- [ ] **Step 2.2: Run to confirm Red**

```bash
uv run pytest tests/unit/github_client/test_github_client.py::test_gh_transient_error_is_ghapierror_subclass -v
```
Expected: FAIL with `ImportError: cannot import name 'GhTransientError'`.

- [ ] **Step 2.3: Implement the class**

Append after the `GhAPIError` definition in `src/gh_manage/github_client.py`:

```python
class GhTransientError(GhAPIError):
    """Retry-eligible failures — 5xx from GitHub or network-level (no response).

    Inherits GhAPIError so existing `except GhAPIError` catch clauses
    transparently catch transient failures. The retry layer in
    gh_manage.github_retry uses `isinstance(e, (GhTransientError,
    GhRateLimitError))` as its cheap retry predicate.
    """
```

- [ ] **Step 2.4: Run tests**

```bash
uv run pytest tests/unit/github_client/ -v
uv run pytest -q
```
Expected: new tests PASS; full suite green.

- [ ] **Step 2.5: Commit**

```bash
git add src/gh_manage/github_client.py tests/unit/github_client/test_github_client.py
git commit -m "feat(github_client): add GhTransientError for retry eligibility

Subclass of GhAPIError so existing catch clauses transparently receive
transient failures. Used by retry layer in Task 4 (spec §1)."
```

---

## Task 3: Refactor classifier to Path A / Path B structure (TDD, table-driven)

**Files:**
- Modify: `src/gh_manage/github_client.py:47-85` — replace `_raise_classified_error`
- Test: `tests/unit/github_client/test_github_client.py` — replace old parametrize table, add new ones

**Rationale:** This is the CRITICAL 1 fix from spec-critique round 1. Path A parses `(HTTP <code>)` from stderr and dispatches by code. Path B is taken only when the regex does NOT match, and checks for network markers.

- [ ] **Step 3.1: Write the new table-driven test (full replacement)**

Replace the existing `test_run_gh_api_classifies_stderr_into_typed_exception` (tests/unit/github_client/test_github_client.py:46-62) with a richer table covering both paths:

```python
# Task 3: Path A (HTTP-status-parsed) classifier
@pytest.mark.parametrize(
    ("stderr", "expected_exc", "expected_status"),
    [
        # Path A — HTTP status parsed from stderr
        ("gh: Not Found (HTTP 404)\n", GhNotFoundError, 404),
        ("gh: Bad credentials (HTTP 401)\n", GhAuthError, 401),
        ("gh: Forbidden (HTTP 403)\n", GhPermissionError, 403),
        ("gh: API rate limit exceeded (HTTP 403)\n", GhRateLimitError, 403),
        ("gh: You have exceeded a secondary rate limit (HTTP 403)\n", GhRateLimitError, 403),
        ("gh: abuse detection mechanism (HTTP 403)\n", GhRateLimitError, 403),
        ("gh: Too Many Requests (HTTP 429)\n", GhRateLimitError, 429),
        ("gh: Internal Server Error (HTTP 500)\n", GhTransientError, 500),
        ("gh: Bad Gateway (HTTP 502)\n", GhTransientError, 502),
        ("gh: Service Unavailable (HTTP 503)\n", GhTransientError, 503),
        ("gh: Gateway Timeout (HTTP 504)\n", GhTransientError, 504),
        ("gh: I'm a teapot (HTTP 418)\n", GhAPIError, 418),
        ("gh: weird code (HTTP 599)\n", GhAPIError, 599),
    ],
)
def test_path_a_http_status_classification(
    mocker: MockerFixture,
    stderr: str,
    expected_exc: type[Exception],
    expected_status: int,
) -> None:
    _mock_gh_failure(mocker, stderr)
    with pytest.raises(expected_exc) as exc_info:
        run_gh_api("repos/foo/bar/labels")
    assert exc_info.value.status_code == expected_status


# Task 3: Path B (no HTTP status — network level)
@pytest.mark.parametrize(
    ("stderr", "expected_exc"),
    [
        ("error: dial tcp: lookup api.github.com: no such host\n", GhTransientError),
        ("error: dial tcp 140.82.121.5:443: connection refused\n", GhTransientError),
        ("error: Post https://api.github.com: i/o timeout\n", GhTransientError),
        ("error: context deadline exceeded\n", GhTransientError),
        ("error: connection refused\n", GhTransientError),
        ("error: some totally unknown error\n", GhAPIError),
        ("\n", GhAPIError),
    ],
)
def test_path_b_network_marker_classification(
    mocker: MockerFixture,
    stderr: str,
    expected_exc: type[Exception],
) -> None:
    _mock_gh_failure(mocker, stderr)
    with pytest.raises(expected_exc) as exc_info:
        run_gh_api("repos/foo/bar/labels")
    assert exc_info.value.status_code is None


# Task 3: Path A wins when BOTH HTTP status AND network markers present
def test_path_a_wins_over_path_b_when_both_present(mocker: MockerFixture) -> None:
    _mock_gh_failure(
        mocker,
        "gh: Internal Server Error (HTTP 500): dial tcp failed\n",
    )
    with pytest.raises(GhTransientError) as exc_info:
        run_gh_api("repos/foo/bar/labels")
    assert exc_info.value.status_code == 500


# Task 3: Canary — `gh` CLI format must keep (HTTP <code>) parseable
def test_canary_gh_cli_http_code_format_parseable() -> None:
    """If a future gh CLI version drops '(HTTP <code>)' from stderr, this
    test breaks loudly before every downstream retry test also breaks."""
    import re

    # This is the exact contract the classifier depends on.
    match = re.search(r"\(HTTP (\d{3})\)", "gh: Not Found (HTTP 404)\n")
    assert match is not None
    assert match.group(1) == "404"
```

Keep the existing `test_gh_not_found_error_message_contains_gh_auth_status` and `test_gh_auth_error_mentions_gh_auth_login` — update their stderr fixtures to use the `(HTTP <code>)` format:

```python
def test_gh_not_found_error_message_contains_gh_auth_status(
    mocker: MockerFixture,
) -> None:
    _mock_gh_failure(mocker, "gh: Not Found (HTTP 404)\n")
    with pytest.raises(GhNotFoundError, match="gh auth status"):
        run_gh_api("repos/foo/bar/labels")


def test_gh_auth_error_mentions_gh_auth_login(mocker: MockerFixture) -> None:
    _mock_gh_failure(mocker, "gh: Bad credentials (HTTP 401)\n")
    with pytest.raises(GhAuthError, match="gh auth login"):
        run_gh_api("repos/foo/bar/labels")
```

Also import `GhTransientError` at the top of the test file:

```python
from gh_manage.github_client import (
    GhAPIError,
    GhAuthError,
    GhError,
    GhNotFoundError,
    GhNotInstalledError,
    GhPermissionError,
    GhRateLimitError,
    GhTransientError,  # NEW
    run_gh,
    run_gh_api,
)
```

- [ ] **Step 3.2: Run tests to confirm Red**

```bash
uv run pytest tests/unit/github_client/test_github_client.py::test_path_a_http_status_classification -v
```
Expected: FAIL. The old classifier returns `GhRateLimitError` on `"rate limit"` substring first and does not populate `status_code`. Several parametrized rows fail.

- [ ] **Step 3.3: Implement the refactored classifier**

Replace `_raise_classified_error` in `src/gh_manage/github_client.py:47-85` with:

```python
import re as _re  # top of file with other imports

_HTTP_STATUS_RE = _re.compile(r"\(HTTP (\d{3})\)")
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
```

- [ ] **Step 3.4: Run tests to verify Green**

```bash
uv run pytest tests/unit/github_client/ -v
```
Expected: all tests PASS including the new Path A/B parametrizations.

- [ ] **Step 3.5: Run full suite**

```bash
uv run pytest -q
```
Expected: 496 + ~25 new tests all green. Any pre-existing test using a non-`(HTTP <code>)` stderr format for classification will fail — if so, update those fixtures to use the new format, too. (Known cases: already covered in Step 3.1 updates.)

- [ ] **Step 3.6: Lint + format check**

```bash
uvx ruff@0.8.0 check src/gh_manage/github_client.py tests/unit/github_client/test_github_client.py
uvx ruff@0.8.0 format --check src/gh_manage/github_client.py tests/unit/github_client/test_github_client.py
```
Expected: both clean. If format --check fails, run `uvx ruff@0.8.0 format src/... tests/...` and re-check.

- [ ] **Step 3.7: Commit**

```bash
git add src/gh_manage/github_client.py tests/unit/github_client/test_github_client.py
git commit -m "refactor(github_client): Path A/B classifier, HTTP-status-first

Classifier now parses (HTTP <code>) from stderr and dispatches by code
(Path A); falls through to network-marker matching (Path B) when no
HTTP status is present. status_code is populated on every classified
exception. Spec §1, addresses critique round 1 CRITICAL 1.

All 13 HTTP status scenarios + 7 network-marker scenarios covered by
table-driven tests. Canary test guards against future gh CLI format
changes that would break Path A parsing."
```

---

## Task 4: Immutable `reset_at` on `GhRateLimitError`

**Files:**
- Modify: `src/gh_manage/github_client.py` — `GhRateLimitError.__init__`
- Test: `tests/unit/github_client/test_github_client.py`

**Rationale:** Spec-critique MEDIUM 1. Retry layer must not mutate the exception; it must construct a fresh one with `reset_at` set.

- [ ] **Step 4.1: Write the failing test**

```python
# Task 4: GhRateLimitError with reset_at
from datetime import datetime, timezone


def test_gh_rate_limit_error_reset_at_defaults_to_none() -> None:
    from gh_manage.github_client import GhRateLimitError

    e = GhRateLimitError("x")
    assert e.reset_at is None
    assert e.status_code is None


def test_gh_rate_limit_error_with_reset_at_and_status_code() -> None:
    from gh_manage.github_client import GhRateLimitError

    ts = datetime(2026, 4, 17, 10, 45, tzinfo=timezone.utc)
    e = GhRateLimitError("wait", status_code=429, reset_at=ts)
    assert e.status_code == 429
    assert e.reset_at == ts
```

- [ ] **Step 4.2: Run to confirm Red**

```bash
uv run pytest tests/unit/github_client/test_github_client.py::test_gh_rate_limit_error_with_reset_at_and_status_code -v
```
Expected: FAIL with `TypeError: GhRateLimitError.__init__() got an unexpected keyword argument 'reset_at'`.

- [ ] **Step 4.3: Implement**

Replace the `GhRateLimitError` class definition in `src/gh_manage/github_client.py`:

```python
class GhRateLimitError(GhError):
    """429 or 403 rate-limit. reset_at is populated by the retry layer
    when it has fetched the reset timestamp; the classifier itself
    always constructs with reset_at=None because stderr lacks the
    timestamp. Immutable — never mutated after construction.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        reset_at: datetime | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.reset_at = reset_at
```

Add `from datetime import datetime` near the top of `src/gh_manage/github_client.py` (next to `import json`).

- [ ] **Step 4.4: Run tests**

```bash
uv run pytest tests/unit/github_client/ -v
uv run pytest -q
```
Expected: Green.

- [ ] **Step 4.5: Commit**

```bash
git add src/gh_manage/github_client.py tests/unit/github_client/test_github_client.py
git commit -m "feat(github_client): immutable reset_at on GhRateLimitError

Spec §1, addresses critique round 1 MEDIUM 1. Retry layer will
construct fresh GhRateLimitError instances with reset_at populated
rather than mutating the original. Classifier always builds with
reset_at=None (stderr lacks the timestamp)."
```

---

## Task 5: Rate-limit reset probe helper

**Files:**
- Create: `src/gh_manage/github_retry.py` (new module — start with just the probe)
- Create: `tests/unit/github_client/test_github_retry.py`

- [ ] **Step 5.1: Write the failing tests**

Create `tests/unit/github_client/test_github_retry.py`:

```python
"""Tests for gh_manage.github_retry — retry engine + rate-limit probe."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from subprocess import CompletedProcess

import pytest
from pytest_mock import MockerFixture


def _mock_subprocess_ok(mocker: MockerFixture, stdout: str):
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=""),
    )


def _mock_subprocess_fail(mocker: MockerFixture, stderr: str, returncode: int = 1):
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr=stderr
        ),
    )


def test_fetch_rate_limit_reset_returns_datetime_on_success(
    mocker: MockerFixture,
) -> None:
    from gh_manage.github_retry import _fetch_rate_limit_reset

    reset_ts = 1_744_886_400  # 2026-04-17T10:00:00Z (example)
    body = json.dumps(
        {"resources": {"core": {"reset": reset_ts, "remaining": 0, "limit": 5000}}}
    )
    _mock_subprocess_ok(mocker, body)

    result = _fetch_rate_limit_reset()
    assert isinstance(result, datetime)
    assert result == datetime.fromtimestamp(reset_ts, tz=timezone.utc)


def test_fetch_rate_limit_reset_returns_none_on_probe_failure(
    mocker: MockerFixture,
) -> None:
    from gh_manage.github_retry import _fetch_rate_limit_reset

    _mock_subprocess_fail(mocker, "some probe error")
    result = _fetch_rate_limit_reset()
    assert result is None


def test_fetch_rate_limit_reset_returns_none_on_malformed_json(
    mocker: MockerFixture,
) -> None:
    from gh_manage.github_retry import _fetch_rate_limit_reset

    _mock_subprocess_ok(mocker, "{not valid json")
    assert _fetch_rate_limit_reset() is None


def test_fetch_rate_limit_reset_returns_none_on_subprocess_timeout(
    mocker: MockerFixture,
) -> None:
    from gh_manage.github_retry import _fetch_rate_limit_reset

    mocker.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 5))
    assert _fetch_rate_limit_reset() is None
```

- [ ] **Step 5.2: Run to confirm Red**

```bash
uv run pytest tests/unit/github_client/test_github_retry.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'gh_manage.github_retry'`.

- [ ] **Step 5.3: Implement the probe**

Create `src/gh_manage/github_retry.py`:

```python
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
```

- [ ] **Step 5.4: Run tests**

```bash
uv run pytest tests/unit/github_client/test_github_retry.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 5.5: Commit**

```bash
git add src/gh_manage/github_retry.py tests/unit/github_client/test_github_retry.py
git commit -m "feat(github_retry): add rate-limit reset probe helper

_fetch_rate_limit_reset() issues a single `gh api rate_limit` call
and returns the core reset time or None on any failure. Non-recursive
by contract (spec §1 — must not re-enter retry_gh to avoid infinite
loops on probe-side rate limits)."
```

---

## Task 6: `retry_gh` — transient retry with exponential backoff + jitter

**Files:**
- Modify: `src/gh_manage/github_retry.py` — add `retry_gh`
- Modify: `tests/unit/github_client/test_github_retry.py` — add retry tests

- [ ] **Step 6.1: Write the failing tests**

Append to `tests/unit/github_client/test_github_retry.py`:

```python
# Task 6: retry_gh transient path
def test_retry_gh_succeeds_after_transient_failures(
    mocker: MockerFixture,
) -> None:
    """3 transient failures, then success → retry_gh returns the value."""
    from gh_manage.github_client import GhTransientError
    from gh_manage.github_retry import retry_gh

    mocker.patch("time.sleep", return_value=None)  # skip real sleeps
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 4:
            raise GhTransientError("temp", status_code=503)
        return "ok"

    result = retry_gh(flaky, endpoint="api repos/foo", max_attempts=3)
    assert result == "ok"
    assert calls["n"] == 4  # 1 initial + 3 retries


def test_retry_gh_gives_up_after_max_attempts(mocker: MockerFixture) -> None:
    from gh_manage.github_client import GhTransientError
    from gh_manage.github_retry import retry_gh

    mocker.patch("time.sleep", return_value=None)
    calls = {"n": 0}

    def always_fail() -> str:
        calls["n"] += 1
        raise GhTransientError("temp", status_code=503)

    with pytest.raises(GhTransientError):
        retry_gh(always_fail, endpoint="api repos/foo", max_attempts=3)
    assert calls["n"] == 4  # 1 initial + 3 retries


def test_retry_gh_does_not_retry_non_retriable(mocker: MockerFixture) -> None:
    """401/403-perm/404 must pass through on the first attempt."""
    from gh_manage.github_client import GhAuthError, GhNotFoundError, GhPermissionError
    from gh_manage.github_retry import retry_gh

    sleep_mock = mocker.patch("time.sleep", return_value=None)

    for exc_cls in (GhAuthError, GhNotFoundError, GhPermissionError):
        calls = {"n": 0}

        def fn(cls=exc_cls) -> str:
            calls["n"] += 1
            raise cls("perm")

        with pytest.raises(exc_cls):
            retry_gh(fn, endpoint="api repos/foo", max_attempts=3)
        assert calls["n"] == 1

    assert sleep_mock.call_count == 0  # zero retries → zero sleeps


def test_retry_gh_exponential_backoff_with_jitter(mocker: MockerFixture) -> None:
    """Sleep durations should be in [1, 1.5), [2, 3), [4, 6) for attempts 1-3."""
    from gh_manage.github_client import GhTransientError
    from gh_manage.github_retry import retry_gh

    sleeps: list[float] = []

    def record_sleep(t: float) -> None:
        sleeps.append(t)

    mocker.patch("time.sleep", side_effect=record_sleep)
    calls = {"n": 0}

    def always_fail() -> str:
        calls["n"] += 1
        raise GhTransientError("temp", status_code=503)

    with pytest.raises(GhTransientError):
        retry_gh(always_fail, endpoint="api repos/foo", max_attempts=3)

    assert len(sleeps) == 3
    assert 1.0 <= sleeps[0] < 1.5
    assert 2.0 <= sleeps[1] < 3.0
    assert 4.0 <= sleeps[2] < 6.0


def test_retry_gh_env_var_overrides_max_attempts(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gh_manage.github_client import GhTransientError
    from gh_manage.github_retry import retry_gh

    monkeypatch.setenv("GH_MANAGE_MAX_RETRIES", "1")
    mocker.patch("time.sleep", return_value=None)
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise GhTransientError("temp", status_code=503)

    with pytest.raises(GhTransientError):
        retry_gh(fn, endpoint="api repos/foo")
    assert calls["n"] == 2  # 1 initial + 1 retry
```

- [ ] **Step 6.2: Run to confirm Red**

```bash
uv run pytest tests/unit/github_client/test_github_retry.py::test_retry_gh_succeeds_after_transient_failures -v
```
Expected: FAIL with `ImportError: cannot import name 'retry_gh' from 'gh_manage.github_retry'`.

- [ ] **Step 6.3: Implement retry_gh (transient path only — rate-limit in Task 7)**

Append to `src/gh_manage/github_retry.py`:

```python
import os
import random
import sys
import time
from collections.abc import Callable
from typing import TypeVar

from gh_manage.github_client import GhRateLimitError, GhTransientError

T = TypeVar("T")


def _read_int_env(name: str, default: int, *, minimum: int = 1, maximum: int = 10) -> int:
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
        rate_limit_wait_max = _read_float_env(
            "GH_MANAGE_RATE_LIMIT_WAIT_MAX", 60.0
        )

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
```

- [ ] **Step 6.4: Run tests**

```bash
uv run pytest tests/unit/github_client/test_github_retry.py -v
```
Expected: all 5 new tests + 4 probe tests PASS.

- [ ] **Step 6.5: Commit**

```bash
git add src/gh_manage/github_retry.py tests/unit/github_client/test_github_retry.py
git commit -m "feat(github_retry): retry_gh transient-path with exponential backoff

Retries on GhTransientError (5xx + network) with 1s → 2s → 4s backoff
and 0-50% multiplicative jitter. max_attempts via GH_MANAGE_MAX_RETRIES
env var (default 3, clamped to [1,10]). Non-retriable errors pass
through on first attempt. Rate-limit path: Task 7. Spec §1."
```

---

## Task 7: `retry_gh` — rate-limit handling with reset probe + anti-herd jitter

**Files:**
- Modify: `src/gh_manage/github_retry.py` — extend `retry_gh`
- Modify: `tests/unit/github_client/test_github_retry.py` — add rate-limit tests

**Rationale:** Spec §1 rate-limit policy + critique CRITICAL 2 mitigation (anti-herd jitter).

- [ ] **Step 7.1: Write the failing tests**

Append to `tests/unit/github_client/test_github_retry.py`:

```python
# Task 7: retry_gh rate-limit path
def test_retry_gh_waits_and_retries_on_rate_limit_within_window(
    mocker: MockerFixture,
) -> None:
    """429 with reset within 60s → sleep + retry once, next call succeeds."""
    from gh_manage.github_client import GhRateLimitError
    from gh_manage.github_retry import retry_gh

    now = datetime.now(timezone.utc)
    reset_at = now + timedelta(seconds=30)

    sleeps: list[float] = []
    mocker.patch("time.sleep", side_effect=sleeps.append)
    mocker.patch(
        "gh_manage.github_retry._fetch_rate_limit_reset",
        return_value=reset_at,
    )
    mocker.patch(
        "gh_manage.github_retry._now",
        return_value=now,
    )

    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise GhRateLimitError("throttled", status_code=429)
        return "ok"

    result = retry_gh(flaky, endpoint="api repos/foo")
    assert result == "ok"
    assert calls["n"] == 2
    # sleep = (30 - 0) + uniform(0, min(10, 30*0.3=9)) → in [30, 39)
    assert len(sleeps) == 1
    assert 30.0 <= sleeps[0] < 39.0


def test_retry_gh_raises_fresh_exception_when_reset_beyond_window(
    mocker: MockerFixture,
) -> None:
    """Reset > wait_max → raise a FRESH GhRateLimitError with reset_at."""
    from gh_manage.github_client import GhRateLimitError
    from gh_manage.github_retry import retry_gh

    now = datetime.now(timezone.utc)
    reset_at = now + timedelta(seconds=300)  # 5 min — beyond 60s max

    mocker.patch("time.sleep", return_value=None)
    mocker.patch(
        "gh_manage.github_retry._fetch_rate_limit_reset",
        return_value=reset_at,
    )
    mocker.patch("gh_manage.github_retry._now", return_value=now)

    original = GhRateLimitError("throttled", status_code=429)

    def fn() -> str:
        raise original

    with pytest.raises(GhRateLimitError) as exc_info:
        retry_gh(fn, endpoint="api repos/foo", rate_limit_wait_max=60.0)
    # Must be a fresh instance, not the original
    assert exc_info.value is not original
    assert exc_info.value.reset_at == reset_at
    assert exc_info.value.status_code == 429
    assert exc_info.value.__cause__ is original


def test_retry_gh_probe_failure_falls_back_to_15s(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """Probe returns None → 15s fixed sleep + log line + retry once."""
    from gh_manage.github_client import GhRateLimitError
    from gh_manage.github_retry import retry_gh

    sleeps: list[float] = []
    mocker.patch("time.sleep", side_effect=sleeps.append)
    mocker.patch("gh_manage.github_retry._fetch_rate_limit_reset", return_value=None)

    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise GhRateLimitError("throttled", status_code=429)
        return "ok"

    result = retry_gh(flaky, endpoint="api repos/foo")
    assert result == "ok"
    assert sleeps == [15.0]
    stderr = capsys.readouterr().err
    assert "[rate-limit-probe-failed]" in stderr
    assert "fallback_wait=15s" in stderr


def test_retry_gh_rate_limit_log_includes_reset(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    from gh_manage.github_client import GhRateLimitError
    from gh_manage.github_retry import retry_gh

    now = datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc)
    reset_at = datetime(2026, 4, 17, 10, 0, 30, tzinfo=timezone.utc)
    mocker.patch("time.sleep", return_value=None)
    mocker.patch("gh_manage.github_retry._fetch_rate_limit_reset", return_value=reset_at)
    mocker.patch("gh_manage.github_retry._now", return_value=now)

    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise GhRateLimitError("throttled", status_code=429)
        return "ok"

    retry_gh(flaky, endpoint="api repos/foo")
    stderr = capsys.readouterr().err
    assert "GhRateLimitError" in stderr
    assert "reset=2026-04-17T10:00:30" in stderr


def test_retry_gh_rate_limit_wait_max_zero_disables_wait(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GH_MANAGE_RATE_LIMIT_WAIT_MAX=0 → never wait, always re-raise."""
    from gh_manage.github_client import GhRateLimitError
    from gh_manage.github_retry import retry_gh

    monkeypatch.setenv("GH_MANAGE_RATE_LIMIT_WAIT_MAX", "0")
    now = datetime.now(timezone.utc)
    reset_at = now + timedelta(seconds=10)
    mocker.patch("time.sleep", return_value=None)
    mocker.patch("gh_manage.github_retry._fetch_rate_limit_reset", return_value=reset_at)
    mocker.patch("gh_manage.github_retry._now", return_value=now)

    original = GhRateLimitError("throttled", status_code=429)

    def fn() -> str:
        raise original

    with pytest.raises(GhRateLimitError) as exc_info:
        retry_gh(fn, endpoint="api repos/foo")
    assert exc_info.value.reset_at == reset_at
    assert exc_info.value.__cause__ is original


# Imports at the top of the file — add timedelta:
# from datetime import datetime, timedelta, timezone
```

Also add the `timedelta` import to the top of `test_github_retry.py`:
```python
from datetime import datetime, timedelta, timezone
```

- [ ] **Step 7.2: Run to confirm Red**

```bash
uv run pytest tests/unit/github_client/test_github_retry.py::test_retry_gh_waits_and_retries_on_rate_limit_within_window -v
```
Expected: FAIL — current retry_gh re-raises GhRateLimitError immediately, no probe invoked.

- [ ] **Step 7.3: Implement rate-limit handling**

Extend `src/gh_manage/github_retry.py` — add `_now()` helper (for test mockability), replace the `retry_gh` body:

```python
from datetime import datetime, timezone


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

    Returns the retry counter does not apply to rate-limit — we
    retry once after rate-limit wait, then either succeed or the
    next exception is re-raised.
    """
    if max_attempts is None:
        max_attempts = _read_int_env("GH_MANAGE_MAX_RETRIES", 3)
    if rate_limit_wait_max is None:
        rate_limit_wait_max = _read_float_env(
            "GH_MANAGE_RATE_LIMIT_WAIT_MAX", 60.0
        )

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
                # Probe failure fallback.
                print(
                    f"[rate-limit-probe-failed] endpoint={endpoint} "
                    f"fallback_wait=15s",
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
```

- [ ] **Step 7.4: Run tests to verify Green**

```bash
uv run pytest tests/unit/github_client/test_github_retry.py -v
```
Expected: all rate-limit tests PASS, old transient tests still PASS.

- [ ] **Step 7.5: Verify with broader suite**

```bash
uv run pytest -q
```
Expected: green.

- [ ] **Step 7.6: Lint + format**

```bash
uvx ruff@0.8.0 check src/gh_manage/github_retry.py tests/unit/github_client/test_github_retry.py
uvx ruff@0.8.0 format --check src/gh_manage/github_retry.py tests/unit/github_client/test_github_retry.py
```
Expected: clean. Fix format issues if any via `uvx ruff@0.8.0 format src/... tests/...`.

- [ ] **Step 7.7: Commit**

```bash
git add src/gh_manage/github_retry.py tests/unit/github_client/test_github_retry.py
git commit -m "feat(github_retry): rate-limit handling with reset probe + anti-herd jitter

Rate-limit errors: probe gh api rate_limit, sleep (reset - now) +
uniform(0, min(10, wait*0.3)) jitter if within GH_MANAGE_RATE_LIMIT_WAIT_MAX
(default 60s) and retry once. Beyond window → fresh GhRateLimitError
with reset_at, chained via __cause__. Probe failure → 15s fixed sleep
with [rate-limit-probe-failed] stderr log. Anti-herd jitter prevents
lock-step retries under parallel --all scan (critique CRITICAL 2)."
```

---

## Task 8: Wrap `run_gh` with `retry_gh`

**Files:**
- Modify: `src/gh_manage/github_client.py:88-118` — `run_gh` body wraps with `retry_gh`
- Modify: `tests/unit/github_client/test_github_client.py` — add integration test

- [ ] **Step 8.1: Write the failing test**

Append to `tests/unit/github_client/test_github_client.py`:

```python
# Task 8: run_gh wraps with retry_gh
def test_run_gh_retries_transient_failures(mocker: MockerFixture) -> None:
    """run_gh should retry on HTTP 503 via retry_gh transparently."""
    mocker.patch("time.sleep", return_value=None)

    # First call 503, second call 200 with stdout "ok\n"
    responses = [
        CompletedProcess(args=[], returncode=1, stdout="", stderr="gh: Service Unavailable (HTTP 503)\n"),
        CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr=""),
    ]
    call_count = {"n": 0}

    def fake_run(*args, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        return responses[idx]

    mocker.patch("subprocess.run", side_effect=fake_run)

    result = run_gh(["api", "repos/foo"])
    assert result == "ok\n"
    assert call_count["n"] == 2


def test_run_gh_non_retriable_passes_through_immediately(
    mocker: MockerFixture,
) -> None:
    """run_gh should NOT retry on 404 — permanent error."""
    from subprocess import CompletedProcess as CP

    call_count = {"n": 0}

    def fake_run(*args, **kwargs):
        call_count["n"] += 1
        return CP(args=[], returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)\n")

    mocker.patch("subprocess.run", side_effect=fake_run)
    mocker.patch("time.sleep", return_value=None)

    with pytest.raises(GhNotFoundError):
        run_gh(["api", "repos/missing"])
    assert call_count["n"] == 1
```

- [ ] **Step 8.2: Run to confirm Red**

```bash
uv run pytest tests/unit/github_client/test_github_client.py::test_run_gh_retries_transient_failures -v
```
Expected: FAIL. Current `run_gh` has no retry; it fails on the first 503.

- [ ] **Step 8.3: Implement the wrapping**

Replace `run_gh` in `src/gh_manage/github_client.py:88-118` with:

```python
def run_gh(args: list[str], *, stdin_input: str | None = None) -> str:
    """Run `gh <args>` and return stdout, with automatic retry on transient
    failures (5xx + network) and rate-limit recovery.

    See gh_manage.github_retry.retry_gh for the retry policy.
    Raises GhNotInstalledError if gh is not on PATH.
    Raises a GhError subclass on non-zero exit after retries are
    exhausted (classified by stderr).
    """
    # Local import to avoid circular dependency at module load.
    from gh_manage.github_retry import retry_gh

    def _attempt() -> str:
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

    return retry_gh(_attempt, endpoint=" ".join(args))
```

- [ ] **Step 8.4: Run tests**

```bash
uv run pytest tests/unit/github_client/ -v
uv run pytest -q
```
Expected: all tests PASS. Some existing tests that mocked one subprocess call may still pass because `retry_gh` only retries on `GhTransientError` / `GhRateLimitError`; non-retriable errors pass through on first attempt.

- [ ] **Step 8.5: Lint + format + mypy**

```bash
uvx ruff@0.8.0 check src/gh_manage/ tests/unit/github_client/
uvx ruff@0.8.0 format --check src/gh_manage/ tests/unit/github_client/
uv run mypy src/gh_manage/github_client.py src/gh_manage/github_retry.py
```
Expected: all clean.

- [ ] **Step 8.6: Commit**

```bash
git add src/gh_manage/github_client.py tests/unit/github_client/test_github_client.py
git commit -m "feat(github_client): wrap run_gh with retry_gh

run_gh now retries 5xx / network / rate-limit failures transparently
via gh_manage.github_retry.retry_gh. All existing callers (run_gh_api,
labels.py, repo_info.py) gain retry for free. Non-retriable errors
(401/403-perm/404) still pass through on first attempt.

Spec §1, addresses #47 (Theme A item 3 — GhRateLimitError previously
defined but never caught)."
```

---

## Task 9: PR 1 verification + self-dogfood

- [ ] **Step 9.1: Run the full suite fresh**

```bash
uv run pytest -q
```
Expected: green. Verify test count: should be 496 + ~25 new = ~521 tests.

- [ ] **Step 9.2: Coverage check**

```bash
uv run pytest --cov=src/gh_manage/github_client --cov=src/gh_manage/github_retry --cov-report=term
```
Expected: ≥85% on both files. If below, add tests until met.

- [ ] **Step 9.3: Lint + format + mypy on full source**

```bash
uvx ruff@0.8.0 check src/ tests/
uvx ruff@0.8.0 format --check src/ tests/
uv run mypy src/
```
Expected: all clean. Fix anything that isn't.

- [ ] **Step 9.4: Self-dogfood — single-repo drift**

```bash
uv run gh-manage drift . --profile python-service
```
Expected: exits 0, produces drift report for gh-manage repo (findings may or may not exist depending on current drift state). The point is to confirm transport retry is transparent — no regressions.

- [ ] **Step 9.5: Self-dogfood — full --all**

```bash
uv run gh-manage drift --all
```
Expected: all 9 current repos scanned, zero NEW FAILED entries compared to prior runs. Any retry attempts appear in stderr as `[retry N/3] ...` lines.

- [ ] **Step 9.6: Verify retry log format**

Inspect the stderr from Step 9.5. If any retry lines appear, confirm format matches spec §4:

```
[retry 1/3] api repos/... (GhTransientError status=503) wait=1.24s
```

If no retry lines appear (all API calls succeed first try), that's fine — we're proving the happy path isn't broken.

- [ ] **Step 9.7: Commit anything that came up (usually nothing)**

If Steps 9.1-9.6 surfaced any fix or format tweak, commit it now:

```bash
git status
# If changes: git add ...; git commit -m "chore: ..."
```

---

## Task 10: PR 1 release — version bump, PR, review, merge, tag

- [ ] **Step 10.1: Bump CLI version to 1.3.0**

Edit `src/gh_manage/__init__.py` — change the `__version__` string to `"1.3.0"`. Verify current value first:

```bash
grep __version__ src/gh_manage/__init__.py
```

Then use Edit to change the single line (exact old value comes from the grep). If version is stored elsewhere (e.g., pyproject.toml), bump that too — check:

```bash
grep -n "^version" pyproject.toml
```

and bump to `1.3.0` in lockstep.

- [ ] **Step 10.2: Verify version change**

```bash
grep __version__ src/gh_manage/__init__.py
grep "^version" pyproject.toml
uv run gh-manage --version
```
Expected: all show `1.3.0`.

- [ ] **Step 10.3: Commit version bump**

```bash
git add src/gh_manage/__init__.py pyproject.toml
git commit -m "chore: bump cli version to 1.3.0"
```

- [ ] **Step 10.4: Push branch and open PR**

```bash
git push -u origin feat/resilience-pr1-transport-retry
gh pr create --title "feat: transport retry + HTTP status classifier (cli/v1.3.0)" \
  --body "$(cat <<'EOF'
## Summary

Implements PR 1 of the Theme A resilience pack (spec §[docs/specs/2026-04-17-theme-a-resilience-pack-design.md](docs/specs/2026-04-17-theme-a-resilience-pack-design.md)).

Hardens gh CLI transport so 20+ repo drift scans (Phase 10 target, #27)
survive transient GitHub failures and rate-limit pressure that would
otherwise abort the entire scan.

## What ships

- **Path A / Path B classifier refactor** — `_raise_classified_error` in `src/gh_manage/github_client.py` now parses `(HTTP <code>)` from stderr (Path A) and falls through to network-marker matching (Path B) when no HTTP status is present. Paths are mutually exclusive and exhaustive.
- **`GhTransientError`** — new `GhAPIError` subclass covering 500/502/503/504 and network-level failures. Retry layer's cheap retry predicate.
- **`.status_code` on `GhError`** — populated for every HTTP-classified exception. `GhRateLimitError` additionally carries immutable `.reset_at`.
- **`retry_gh` engine** (new `src/gh_manage/github_retry.py`) — exponential backoff (1→2→4s) with 0-50% jitter for transient errors; rate-limit probe via `gh api rate_limit` + (reset − now) sleep with anti-herd jitter `uniform(0, min(10, wait*0.3))`; fresh `GhRateLimitError` with `reset_at` populated when reset is beyond wait window; 15s fallback on probe failure.
- **`run_gh` wrapping** — all existing callers (`run_gh_api`, `labels.py`, `repo_info.py`) gain retry transparently.
- **Env var config** — `GH_MANAGE_MAX_RETRIES` (default 3), `GH_MANAGE_RATE_LIMIT_WAIT_MAX` (default 60s).

## Non-goals (tracked elsewhere)

- Parallel `--all` scan → PR 2 (`cli/v1.4.0`).
- `drift_sync.py` / `protection_sync.py` file splits → #47.
- Structured logging / run history → #47 / #50.
- Per-repo circuit breaker, shared rate-limit state → deferred.
- #40 label 422 silent swallowing → separate PR (now unblocked by `.status_code`).

## Test plan

- [x] Full pytest suite green (~521 tests incl. ~25 new).
- [x] Classifier coverage: all HTTP status codes (401/403/404/429/5xx) + 7 network markers + Path A/B exclusivity canary.
- [x] Retry coverage: transient retry + max-attempts + non-retriable pass-through + rate-limit within/beyond window + probe failure fallback + env var overrides.
- [x] `uvx ruff@0.8.0 check + format --check` clean.
- [x] `uv run mypy src/` clean.
- [x] Self-dogfood: `uv run gh-manage drift . --profile python-service` exits 0.
- [x] Self-dogfood: `uv run gh-manage drift --all` green across 9 repos.
- [ ] 4-reviewer protocol clean (Codex + superpowers + SFH + code-reviewer).

## Release plan

- Merge → tag `cli/v1.3.0` per `docs/release-checklist.md`.
- PR 2 (`feat/resilience-pr2-parallel-scan`, `cli/v1.4.0`) will be cut from `main` after this lands.

Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

Capture the PR number returned by `gh pr create`; you'll need it for the review step.

- [ ] **Step 10.5: Run the 4-reviewer protocol**

Per `claude-dotfiles/rules/workflow-review.md`, launch all 4 reviewers in parallel (single message, 4 Agent tool-use blocks):

1. `bash scripts/codex-review-resilient.sh "<prompt with diff summary>"` — run as background bash command.
2. `Agent(subagent_type="superpowers:code-reviewer", ...)` — pass plan + spec paths.
3. `Agent(subagent_type="pr-review-toolkit:silent-failure-hunter", ...)` — pass `git diff main..HEAD`.
4. `Agent(subagent_type="code-reviewer", model="sonnet", ...)` — diff likely 500-2000 LOC, sonnet is appropriate; confirm with `git diff main..HEAD --stat | tail -1`.

Wait for all 4 to complete. Address CRITICAL and HIGH findings before merge. Document MEDIUM/LOW decisions inline in the PR.

- [ ] **Step 10.6: Watch CI and merge**

```bash
gh pr checks <PR-number> --watch
```

Once CI is green and review is clean:

```bash
gh pr merge <PR-number> --squash --delete-branch
```

- [ ] **Step 10.7: Tag the release**

```bash
git fetch origin main
git checkout main
git pull
git tag -a cli/v1.3.0 -m "cli/v1.3.0 — transport retry + HTTP status classifier

- Path A / Path B classifier refactor
- GhTransientError subclass, .status_code on GhError
- retry_gh with exponential backoff + anti-herd jitter
- Rate-limit reset probe with 60s wait window
- Env var config: GH_MANAGE_MAX_RETRIES, GH_MANAGE_RATE_LIMIT_WAIT_MAX"
git push origin cli/v1.3.0
```

- [ ] **Step 10.8: Create GitHub release**

```bash
gh release create cli/v1.3.0 --title "cli/v1.3.0 — Transport retry + HTTP status classifier" \
  --notes "See PR #<PR-number> for full details. Breaking changes: none (additive only — GhTransientError inherits GhAPIError, status_code defaults to None on all existing exceptions)."
```

**PR 1 complete.** Stop here and wait for user confirmation before starting PR 2. PR 2 requires this tag to be live.

---

# PR 2: Parallel `--all` Scan (`cli/v1.4.0`)

Branch: `feat/resilience-pr2-parallel-scan` — cut from `main` AFTER PR 1 is merged and tagged.

Release tag target: `cli/v1.4.0`

## Task 11: Create PR 2 branch + add `--concurrency` CLI flag with clamp validation

**Files:**
- Modify: `src/gh_manage/commands/drift.py:225-229` (add option) + clamp logic
- Create: `tests/unit/commands/test_drift.py` — NEW file

- [ ] **Step 11.1: Cut PR 2 branch from latest main**

```bash
git checkout main
git pull
git checkout -b feat/resilience-pr2-parallel-scan
```

- [ ] **Step 11.2: Write the failing clamp test**

Create `tests/unit/commands/test_drift.py`:

```python
"""Tests for gh_manage.commands.drift — CLI-level behavior.

Engine tests live in tests/unit/drift/. This file covers CLI flag
validation and the parallel _scan_all_repos orchestration (Task 12+).
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from gh_manage.commands.drift import drift


def test_concurrency_zero_rejected() -> None:
    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "0"])
    assert result.exit_code != 0
    assert "concurrency" in result.output.lower()


def test_concurrency_seventeen_rejected() -> None:
    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "17"])
    assert result.exit_code != 0
    assert "concurrency" in result.output.lower()


def test_concurrency_one_accepted() -> None:
    """--concurrency 1 must be a valid value (sequential-equivalent mode).

    The actual invocation will fail because we haven't mocked repos.yml,
    but the click validation must pass first.
    """
    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "1"])
    # click validation passed if the error isn't about the flag itself
    assert "concurrency" not in result.output.lower() or result.exit_code == 0
```

- [ ] **Step 11.3: Run to confirm Red**

```bash
uv run pytest tests/unit/commands/test_drift.py::test_concurrency_zero_rejected -v
```
Expected: FAIL — `--concurrency` is not a known flag; click reports an "unknown option" error with "concurrency" in the output, which makes this test pass accidentally. Tighten the assertion:

Change the assertion to:
```python
    assert "no such option" not in result.output.lower()  # flag must exist
    assert "invalid value" in result.output.lower() or result.exit_code == 2
```

Re-run. Expected: FAIL with "No such option: --concurrency".

- [ ] **Step 11.4: Add the CLI option with click's IntRange**

In `src/gh_manage/commands/drift.py`, insert a new option after the `--all` option (line 229):

```python
@click.option(
    "--concurrency",
    type=click.IntRange(1, 16),
    default=4,
    show_default=True,
    help="Parallel worker count for --all mode. Values outside [1,16] are rejected. "
         "Only meaningful with --all; ignored otherwise. "
         "--concurrency 8+ may interact with GitHub secondary rate-limit.",
)
```

Update the `drift(...)` signature at line 249 to add `concurrency: int`:

```python
def drift(
    path: Path | None,
    profile_name: str | None,
    scan_all: bool,
    concurrency: int,
    severity: str,
    report_mode: str,
    output: Path | None,
) -> None:
```

Don't pass `concurrency` to `_scan_all_repos` yet — that's Task 12.

- [ ] **Step 11.5: Run tests**

```bash
uv run pytest tests/unit/commands/test_drift.py -v
```
Expected: all 3 tests PASS.

- [ ] **Step 11.6: Run full suite**

```bash
uv run pytest -q
```
Expected: green.

- [ ] **Step 11.7: Commit**

```bash
git add src/gh_manage/commands/drift.py tests/unit/commands/test_drift.py
git commit -m "feat(drift): add --concurrency flag with [1,16] clamp

Validation only in this commit — wiring into _scan_all_repos is Task 12.
Default 4 (spec §2). IntRange gives free click error message for
out-of-range values."
```

---

## Task 12: Refactor `_scan_all_repos` to `ThreadPoolExecutor` with main-thread output

**Files:**
- Modify: `src/gh_manage/commands/drift.py:147-202` — `_scan_all_repos` body
- Modify: `tests/unit/commands/test_drift.py` — add parallel tests

- [ ] **Step 12.1: Write the failing parallel tests**

Append to `tests/unit/commands/test_drift.py`:

```python
# Task 12: parallel _scan_all_repos
import time
from pathlib import Path


def test_scan_all_repos_parallel_returns_all_three_results(mocker) -> None:
    """3 mock repos, concurrency=3, all succeed → all 3 in stdout."""
    from gh_manage.commands.drift import _scan_all_repos
    from gh_manage.models.repos import ReposConfig, RepoEntry

    fake_config = ReposConfig(
        repos=[
            RepoEntry(name="yakkuro/a", profile="python-service", enabled=True),
            RepoEntry(name="yakkuro/b", profile="python-service", enabled=True),
            RepoEntry(name="yakkuro/c", profile="python-service", enabled=True),
        ]
    )

    mocker.patch(
        "gh_manage.commands.drift.load_config", return_value=fake_config
    )
    mocker.patch(
        "gh_manage.commands.drift.resolve_repos_path",
        return_value=Path("/fake/repos.yml"),
    )

    def fake_scan(owner_repo, *args, **kwargs):
        return f"scan-of-{owner_repo}"

    mocker.patch(
        "gh_manage.commands.drift._scan_single_repo", side_effect=fake_scan
    )

    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "3"])

    assert result.exit_code == 0, result.output
    assert "scan-of-yakkuro/a" in result.output
    assert "scan-of-yakkuro/b" in result.output
    assert "scan-of-yakkuro/c" in result.output


def test_scan_all_repos_one_failure_does_not_abort_others(mocker) -> None:
    from gh_manage.commands.drift import _scan_all_repos
    from gh_manage.github_client import GhAPIError
    from gh_manage.models.repos import ReposConfig, RepoEntry

    fake_config = ReposConfig(
        repos=[
            RepoEntry(name="yakkuro/ok", profile="python-service", enabled=True),
            RepoEntry(name="yakkuro/bad", profile="python-service", enabled=True),
        ]
    )
    mocker.patch("gh_manage.commands.drift.load_config", return_value=fake_config)
    mocker.patch(
        "gh_manage.commands.drift.resolve_repos_path",
        return_value=Path("/fake/repos.yml"),
    )

    def fake_scan(owner_repo, *args, **kwargs):
        if owner_repo == "yakkuro/bad":
            raise GhAPIError("synthetic failure", status_code=500)
        return "ok-output"

    mocker.patch(
        "gh_manage.commands.drift._scan_single_repo", side_effect=fake_scan
    )

    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "2"])

    assert result.exit_code == 0
    assert "ok-output" in result.output
    # Summary (stderr in the real app; CliRunner with mix_stderr=True merges them)
    assert "FAILED" in result.output
    assert "yakkuro/bad" in result.output


def test_scan_all_repos_summary_in_repos_yml_order(mocker) -> None:
    """Per-repo results may stream in completion order, but the final
    summary must list repos in repos.yml order for deterministic diffs.
    """
    from gh_manage.models.repos import ReposConfig, RepoEntry

    fake_config = ReposConfig(
        repos=[
            RepoEntry(name="yakkuro/first", profile="python-service", enabled=True),
            RepoEntry(name="yakkuro/second", profile="python-service", enabled=True),
            RepoEntry(name="yakkuro/third", profile="python-service", enabled=True),
        ]
    )
    mocker.patch("gh_manage.commands.drift.load_config", return_value=fake_config)
    mocker.patch(
        "gh_manage.commands.drift.resolve_repos_path",
        return_value=Path("/fake/repos.yml"),
    )
    mocker.patch(
        "gh_manage.commands.drift._scan_single_repo", return_value="done"
    )

    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "3"])
    assert result.exit_code == 0

    # Summary lines appear after '--- Scan Summary ---'
    summary = result.output.split("--- Scan Summary ---", 1)[1]
    first_idx = summary.index("yakkuro/first")
    second_idx = summary.index("yakkuro/second")
    third_idx = summary.index("yakkuro/third")
    assert first_idx < second_idx < third_idx


def test_scan_all_repos_parallel_wall_clock_faster_than_sequential(
    mocker,
) -> None:
    """4 mock repos @ 1s each; concurrency=4 must finish < 1.8s (overhead
    budget). concurrency=1 must be > 3.5s (sequential). Guards against
    GIL-bound regressions where workers don't actually run in parallel.
    """
    from gh_manage.models.repos import ReposConfig, RepoEntry

    fake_config = ReposConfig(
        repos=[
            RepoEntry(name=f"yakkuro/r{i}", profile="python-service", enabled=True)
            for i in range(4)
        ]
    )
    mocker.patch("gh_manage.commands.drift.load_config", return_value=fake_config)
    mocker.patch(
        "gh_manage.commands.drift.resolve_repos_path",
        return_value=Path("/fake/repos.yml"),
    )

    def slow_scan(owner_repo, *args, **kwargs):
        time.sleep(1.0)
        return "done"

    mocker.patch(
        "gh_manage.commands.drift._scan_single_repo", side_effect=slow_scan
    )

    runner = CliRunner()
    t0 = time.monotonic()
    result = runner.invoke(drift, ["--all", "--concurrency", "4"])
    parallel_elapsed = time.monotonic() - t0
    assert result.exit_code == 0
    assert parallel_elapsed < 1.8, f"parallel took {parallel_elapsed:.2f}s"

    t0 = time.monotonic()
    result = runner.invoke(drift, ["--all", "--concurrency", "1"])
    sequential_elapsed = time.monotonic() - t0
    assert result.exit_code == 0
    assert sequential_elapsed > 3.5, f"sequential took {sequential_elapsed:.2f}s"


def test_scan_all_repos_disabled_entries_skipped(mocker) -> None:
    from gh_manage.models.repos import ReposConfig, RepoEntry

    fake_config = ReposConfig(
        repos=[
            RepoEntry(name="yakkuro/on", profile="python-service", enabled=True),
            RepoEntry(name="yakkuro/off", profile="python-service", enabled=False),
        ]
    )
    mocker.patch("gh_manage.commands.drift.load_config", return_value=fake_config)
    mocker.patch(
        "gh_manage.commands.drift.resolve_repos_path",
        return_value=Path("/fake/repos.yml"),
    )

    scan_mock = mocker.patch(
        "gh_manage.commands.drift._scan_single_repo", return_value="done"
    )

    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "2"])
    assert result.exit_code == 0
    assert "SKIPPED" in result.output
    assert "yakkuro/off" in result.output
    assert scan_mock.call_count == 1  # only the enabled one
```

- [ ] **Step 12.2: Run to confirm Red**

```bash
uv run pytest tests/unit/commands/test_drift.py::test_scan_all_repos_parallel_returns_all_three_results -v
```
Expected: FAIL — `_scan_all_repos` signature doesn't accept `concurrency` yet, and the parallel path doesn't exist.

- [ ] **Step 12.3: Refactor `_scan_all_repos` to ThreadPoolExecutor**

Replace `_scan_all_repos` in `src/gh_manage/commands/drift.py:147-202` with:

```python
def _scan_all_repos(
    severity: str,
    report_mode: str,
    output: Path | None,
    concurrency: int = 4,
) -> None:
    """Scan all enabled repos from repos.yml in parallel.

    Threading discipline (spec §2): workers are pure functions that
    return (name, status_label, payload_or_exc). Only the main thread
    emits to stdout/stderr — no print locks needed, line-atomic output
    is guaranteed.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from gh_manage.models.repos import ReposConfig

    repos_path = resolve_repos_path()
    config = load_config(repos_path, ReposConfig)

    # Partition repos: enabled vs disabled
    enabled_entries = [e for e in config.repos if e.enabled]
    disabled_entries = [e for e in config.repos if not e.enabled]

    per_repo_results: dict[str, str] = {}  # name -> "OK" | "SKIPPED (...)" | "FAILED (...)"

    for e in disabled_entries:
        per_repo_results[e.name] = f"  {e.name}: SKIPPED (disabled)"

    def _worker(entry):
        try:
            result_str = _scan_single_repo(
                entry.name,
                entry.profile,
                severity,
                report_mode,
                output,
                skip_profile_check=True,
            )
            return (entry.name, "OK", result_str)
        except (
            GhError,
            ConfigError,
            GitError,
            ProfileError,
            ProtectionError,
            DriftError,
        ) as e:
            return (entry.name, "FAILED", e)

    if enabled_entries and concurrency > 1:
        click.echo(
            f"[drift --all] {len(enabled_entries)} repos, concurrency={concurrency}",
            err=True,
        )

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        future_to_entry = {pool.submit(_worker, e): e for e in enabled_entries}
        completed = 0
        for future in as_completed(future_to_entry):
            name, status, payload = future.result()
            completed += 1
            if status == "OK":
                if report_mode in ("stdout", "json", "markdown-file"):
                    click.echo(payload)
                per_repo_results[name] = f"  {name}: OK"
            else:  # FAILED
                per_repo_results[name] = f"  {name}: FAILED ({payload})"
            if concurrency > 1:
                click.echo(
                    f"[drift --all] {completed}/{len(enabled_entries)} scanned",
                    err=True,
                )

    scanned = len(enabled_entries)
    skipped = len(disabled_entries)
    failed = sum(1 for v in per_repo_results.values() if "FAILED" in v)
    click.echo(
        f"\n--- Scan Summary ---\nScanned: {scanned}, Skipped: {skipped}, Failed: {failed}",
        err=True,
    )
    # Print per-repo results in repos.yml order (deterministic)
    for entry in config.repos:
        click.echo(per_repo_results[entry.name], err=True)
```

Also wire the CLI flag to the function — edit line 265 from:
```python
        _scan_all_repos(severity, report_mode, output)
```
to:
```python
        _scan_all_repos(severity, report_mode, output, concurrency=concurrency)
```

- [ ] **Step 12.4: Run tests**

```bash
uv run pytest tests/unit/commands/test_drift.py -v
```
Expected: all parallel tests PASS.

- [ ] **Step 12.5: Run full suite**

```bash
uv run pytest -q
```
Expected: green. If any existing test that called `_scan_all_repos` directly (without `concurrency=`) fails, note that the new kwarg has default 4 so they should still work.

- [ ] **Step 12.6: Lint + format + mypy**

```bash
uvx ruff@0.8.0 check src/ tests/
uvx ruff@0.8.0 format --check src/ tests/
uv run mypy src/
```
Expected: clean.

- [ ] **Step 12.7: Commit**

```bash
git add src/gh_manage/commands/drift.py tests/unit/commands/test_drift.py
git commit -m "feat(drift): parallel --all scan via ThreadPoolExecutor

Main-thread-only output emission: workers return tuples, main thread
emits via click.echo in as_completed order. Per-repo results stream
in completion order to stdout; summary is printed in repos.yml order
for deterministic diffs. Progress lines to stderr when concurrency > 1.

Spec §2. Paired with cli/v1.3.0 retry layer (PR 1) for rate-limit
resilience under concurrent load."
```

---

## Task 13: PR 2 verification + self-dogfood

- [ ] **Step 13.1: Run the full suite**

```bash
uv run pytest -q
```
Expected: green. Test count should be ~521 + ~5 PR-2 tests = ~526.

- [ ] **Step 13.2: Self-dogfood — default concurrency**

```bash
uv run gh-manage drift --all
```
Expected: completes in noticeably less wall-clock than before PR 2 (baseline: ~2 minutes for 9 repos sequentially; expect ~30-45s at concurrency=4). Stderr shows progress lines. Zero FAILED entries.

- [ ] **Step 13.3: Self-dogfood — concurrency=1 (sequential equivalent)**

```bash
uv run gh-manage drift --all --concurrency 1
```
Expected: summary byte-identical (excluding timing lines and progress indicator) to pre-PR-2 `--all`. Slower than Step 13.2.

- [ ] **Step 13.4: Self-dogfood — concurrency out-of-range**

```bash
uv run gh-manage drift --all --concurrency 17
```
Expected: exit code 2 with click `Invalid value for '--concurrency': 17 is not in the range 1..16`.

- [ ] **Step 13.5: Commit anything surfaced (usually nothing)**

```bash
git status
```

---

## Task 14: PR 2 release — version bump, PR, review, merge, tag

- [ ] **Step 14.1: Bump CLI version to 1.4.0**

Edit `src/gh_manage/__init__.py` — change `__version__` to `"1.4.0"`. Also bump `pyproject.toml` if version lives there.

```bash
grep __version__ src/gh_manage/__init__.py
grep "^version" pyproject.toml
```

After editing, verify:
```bash
uv run gh-manage --version
```
Expected: 1.4.0.

- [ ] **Step 14.2: Commit version bump**

```bash
git add src/gh_manage/__init__.py pyproject.toml
git commit -m "chore: bump cli version to 1.4.0"
```

- [ ] **Step 14.3: Push and open PR**

```bash
git push -u origin feat/resilience-pr2-parallel-scan
gh pr create --title "feat: parallel --all drift scan with --concurrency (cli/v1.4.0)" \
  --body "$(cat <<'EOF'
## Summary

Implements PR 2 of the Theme A resilience pack (spec §[docs/specs/2026-04-17-theme-a-resilience-pack-design.md](docs/specs/2026-04-17-theme-a-resilience-pack-design.md)).

Depends on cli/v1.3.0 (PR 1 — transport retry) for rate-limit recovery
under concurrent load. Phase 10 rollout (#27) needs this to scale drift
scans from 9 to 20+ repos without 4+ minute wall-clock.

## What ships

- **`gh-manage drift --all --concurrency N`** — new flag, default 4, clamp `[1, 16]` (click IntRange). `--concurrency 8+` documented as "use at your own risk" due to GitHub secondary rate-limit interaction.
- **`_scan_all_repos` refactor** — now uses `concurrent.futures.ThreadPoolExecutor`. Workers are pure functions returning `(name, status, payload)`. Main thread emits output via `as_completed` loop — no print locks needed, line-atomic guarantee.
- **Per-repo streaming** — stdout in completion order (fast feedback).
- **Deterministic summary** — stderr summary in `repos.yml` order (diff-friendly across runs).
- **Progress indicator** — `[drift --all] N/M scanned` lines to stderr when `concurrency > 1`.

## Non-goals (tracked elsewhere)

- Circuit breaker per-repo, shared rate-limit state across workers → #47 (deferred until fleet > 40).
- Structured logging / metrics → #47 / #50.
- Additional doctor checks, workflow-YAML prompt-injection linter → #48.

## Test plan

- [x] Full pytest suite green (~526 tests).
- [x] Timed concurrency smoke: 4 workers × 1s → <1.8s; concurrency=1 → >3.5s.
- [x] One-repo-fails test: other repos complete, FAILED entry in summary.
- [x] Repos.yml-order summary test.
- [x] Click IntRange rejects 0 / 17 with clear message.
- [x] `uvx ruff@0.8.0 check + format --check` clean.
- [x] `uv run mypy src/` clean.
- [x] Self-dogfood: `uv run gh-manage drift --all` green across 9 repos, noticeably faster than v1.3.0.
- [x] Self-dogfood: `uv run gh-manage drift --all --concurrency 1` summary byte-identical to pre-PR-2 (excluding timing + progress lines).
- [ ] 4-reviewer protocol clean.

## Release plan

Merge → tag `cli/v1.4.0` per `docs/release-checklist.md`.

Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

- [ ] **Step 14.4: Run the 4-reviewer protocol** (same as Step 10.5).

- [ ] **Step 14.5: Watch CI and merge**

```bash
gh pr checks <PR-number> --watch
gh pr merge <PR-number> --squash --delete-branch
```

- [ ] **Step 14.6: Tag + release**

```bash
git fetch origin main
git checkout main
git pull
git tag -a cli/v1.4.0 -m "cli/v1.4.0 — parallel --all drift scan

- ThreadPoolExecutor-based parallel scan, default concurrency=4
- --concurrency N flag, clamped [1, 16]
- Main-thread-only output emission (line-atomic)
- Per-repo streaming to stdout, deterministic summary in repos.yml order
- Progress indicator to stderr when concurrency > 1

Depends on cli/v1.3.0's retry layer for rate-limit resilience."
git push origin cli/v1.4.0
gh release create cli/v1.4.0 --title "cli/v1.4.0 — Parallel drift --all" \
  --notes "See PR #<PR-number>. --concurrency 8+ may interact with GitHub secondary rate-limit; default 4 is safe."
```

- [ ] **Step 14.7: Post-release — combined acceptance**

Manually run on the current 9-repo fleet:

```bash
uv run gh-manage drift --all
```

Verify:
- Completes in <60s (well below the <4min Phase 10 target even pre-scale).
- Zero FAILED entries.
- Retry log lines from cli/v1.3.0 may appear in stderr if any flake; confirm format is readable.

**Plan complete.** Theme A items 2 + 3 + 7 from #47 are closed. Remaining Theme A work (file splits #4/#5, structured logging #6, #40 label 422) is tracked on #47 and addressed in separate future plans.

---

# Self-review (plan vs. spec)

| Spec section | Covered by task(s) |
|---|---|
| §1 Data Model (`status_code`, `GhTransientError`, `reset_at`) | Tasks 1, 2, 4 |
| §1 Classifier (Path A / Path B) | Task 3 |
| §1 Retry Layer (backoff, jitter, env vars, logging) | Tasks 6, 7 |
| §1 Rate-limit Reset Probe | Task 5 |
| §1 `run_gh` wrapping | Task 8 |
| §2 ThreadPoolExecutor + `--concurrency` | Tasks 11, 12 |
| §2 Main-thread output + progress | Task 12 |
| §2 Order-deterministic summary | Task 12 (test asserts it) |
| §3 Classifier tests (table-driven, canary) | Task 3 |
| §3 Retry tests (probe failure, env var, anti-herd) | Tasks 5, 6, 7 |
| §3 Parallel tests (timed smoke, ordering) | Task 12 |
| §4 Retry log format | Tasks 6, 7 (stderr prints) |
| §4 Progress hint | Task 12 |
| §5 Release plan (cli/v1.3.0, cli/v1.4.0) | Tasks 10, 14 |
| §5 Compatibility & Rollback | PR descriptions (Tasks 10.4, 14.3) |
| §6 Risks (all rows) | Tasks 6, 7 (jitter), Task 5 (non-recursion), Task 8 (additive catch) |
| §7 Acceptance Criteria PR 1 | Task 9 |
| §7 Acceptance Criteria PR 2 | Task 13 |
| §7 Combined Post-v1.4.0 | Task 14.7 |

No spec requirement lacks a task. No placeholders. Types are consistent: `GhTransientError` / `retry_gh` / `_fetch_rate_limit_reset` / `_now` referenced identically in Tasks 5-8.
