# Phase 8 — `gh manage drift` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `gh manage drift` — single-repo drift scanner that compares labels / branch protection / profile files against the profile + policies, with stdout/json/markdown-file report modes, and ship as `cli/v0.5.0`.

**Architecture:** 3-layer pattern mirroring Phase 5/6/7 — `commands/drift.py` (click) → `drift_sync.py` (pure-function engine: check registry + 3 checks + adapters + 3 report formatters) → existing resource layer (`labels_sync`, `protection_sync`, `github_api.labels`, `github_api.protection`, `models.profiles`, `models.labels`, `models.branch_protection`). One new resource helper: `github_api/repo_info.py` for default branch resolution.

**Tech Stack:** Python 3.12 + click 8 + pydantic v2 + PyYAML + pytest 8 + pytest-mock + hatchling. Reuses Phase 5/6/7 plumbing (`git_cli`, `labels_sync`, `profile_sync`, `protection_sync`, `github_client.run_gh_api`, `config.load_config`, `_resolve_profile_path`, `_handle_errors` decorator pattern).

**Spec:** [`docs/specs/2026-04-11-phase-8-drift-design.md`](../specs/2026-04-11-phase-8-drift-design.md) — read it before starting any task.

---

## File Structure

### New source files

| Path | Responsibility | Created in task |
|---|---|---|
| `src/gh_manage/github_api/repo_info.py` | `get_default_branch(repo) -> str` — calls `gh api repos/{repo} --jq .default_branch` | Task 1 |
| `src/gh_manage/drift_sync.py` | Engine: `Finding`, `ScanContext`, `DriftError` / `DriftOutputError`, `@register_check` registry, `_filter_by_severity`, adapters, 3 checks, 3 report formatters | Tasks 2-11 |

### Modified source files

| Path | Change | Task |
|---|---|---|
| `src/gh_manage/commands/drift.py` | Replace Phase 4 stub with full click CLI | Task 12 |
| `src/gh_manage/cli.py` | Already imports `drift` — no change needed (verify in Task 12) | Task 12 |

### New test files

| Path | Purpose | Task |
|---|---|---|
| `tests/unit/github_api/test_repo_info.py` | subprocess-mocked tests for `get_default_branch` | Task 1 |
| `tests/unit/drift/__init__.py` | package marker | Task 2 |
| `tests/unit/drift/conftest.py` | `DriftScenario` pydantic model + `_load_scenarios()` glob loader + fixture | Task 4 |
| `tests/unit/drift/test_drift_sync.py` | Data classes, registry, severity filter, adapters, scenario-driven tests, golden test | Tasks 2-9 |
| `tests/unit/drift/test_report_format.py` | Unit tests for 3 `format_*_report` functions | Task 11 |
| `tests/unit/cli/test_drift.py` | click CLI tests for `gh manage drift` | Task 12 |

### New test fixtures (11 scenarios)

| Path | Task |
|---|---|
| `tests/fixtures/drift-scenarios/labels/missing-priority-labels.yml` | Task 5 |
| `tests/fixtures/drift-scenarios/labels/extra-unknown-label.yml` | Task 5 |
| `tests/fixtures/drift-scenarios/labels/color-mismatch.yml` | Task 5 |
| `tests/fixtures/drift-scenarios/labels/description-mismatch.yml` | Task 5 |
| `tests/fixtures/drift-scenarios/protection/enforce-admins-weakened.yml` | Task 7 |
| `tests/fixtures/drift-scenarios/protection/required-contexts-shrunk.yml` | Task 7 |
| `tests/fixtures/drift-scenarios/protection/reviews-removed.yml` | Task 7 |
| `tests/fixtures/drift-scenarios/protection/allow-force-pushes-enabled.yml` | Task 7 |
| `tests/fixtures/drift-scenarios/profile_files/claude-md-modified.yml` | Task 8 |
| `tests/fixtures/drift-scenarios/profile_files/ci-yml-drifted.yml` | Task 8 |
| `tests/fixtures/drift-scenarios/profile_files/missing-file.yml` | Task 8 |

---

## Pre-flight checklist

```bash
cd /home/server160/repos/gh-manage
git status              # clean
git checkout main
git pull --ff-only
uv run pytest           # 292 pass baseline
uv run ruff check src/ tests/   # clean
uv run ruff format --check src/ tests/   # clean
```

If any fails, **stop and report**. Then create the working branch from the spec branch:

```bash
git checkout docs/phase-8-spec
git pull --ff-only
git checkout -b feat/phase-8-drift
```

All Phase 8 tasks commit to `feat/phase-8-drift`. The final PR opens `feat/phase-8-drift` → `main`.

---

## Task 1: `github_api/repo_info.py` — default branch helper

**Goal:** Create a thin wrapper around `gh api repos/<owner>/<repo> --jq .default_branch` so that `check_protection` (Task 7) can resolve the default branch dynamically instead of hardcoding `"main"`. This is the spec-critique CRITICAL fix.

**Files:**
- Create: `src/gh_manage/github_api/repo_info.py`
- Create: `tests/unit/github_api/test_repo_info.py`

- [ ] **Step 1.1: Write the failing tests**

Create `tests/unit/github_api/test_repo_info.py`:

```python
"""Tests for gh_manage.github_api.repo_info — repo metadata helpers."""

from __future__ import annotations

from subprocess import CompletedProcess

import pytest
from pytest_mock import MockerFixture

from gh_manage.github_api.repo_info import get_default_branch
from gh_manage.github_client import GhAPIError, GhNotFoundError


def _mock_gh_success(mocker: MockerFixture, stdout: str) -> object:
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=0, stdout=stdout, stderr=""
        ),
    )


def _mock_gh_failure(
    mocker: MockerFixture, stderr: str, returncode: int = 1
) -> object:
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr=stderr
        ),
    )


def test_get_default_branch_returns_main(mocker: MockerFixture) -> None:
    _mock_gh_success(mocker, "main\n")
    assert get_default_branch("yakkuro/gh-manage") == "main"


def test_get_default_branch_returns_develop(mocker: MockerFixture) -> None:
    _mock_gh_success(mocker, "develop\n")
    assert get_default_branch("some/repo") == "develop"


def test_get_default_branch_strips_whitespace(mocker: MockerFixture) -> None:
    _mock_gh_success(mocker, "  master  \n\n")
    assert get_default_branch("some/repo") == "master"


def test_get_default_branch_uses_jq_flag(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "main\n")
    get_default_branch("yakkuro/gh-manage")
    args = mock_run.call_args.args[0]
    # The helper should build: gh api repos/yakkuro/gh-manage --jq .default_branch
    assert "repos/yakkuro/gh-manage" in args
    assert "--jq" in args
    assert ".default_branch" in args


def test_get_default_branch_404_propagates(mocker: MockerFixture) -> None:
    _mock_gh_failure(
        mocker, "HTTP 404: Not Found\nRepository does not exist\n"
    )
    with pytest.raises(GhNotFoundError):
        get_default_branch("nonexistent/repo")


def test_get_default_branch_empty_response_raises_api_error(
    mocker: MockerFixture,
) -> None:
    _mock_gh_success(mocker, "")
    with pytest.raises(GhAPIError, match="empty"):
        get_default_branch("some/repo")
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/github_api/test_repo_info.py -v
```

Expected: collection error (`gh_manage.github_api.repo_info` doesn't exist).

- [ ] **Step 1.3: Implement `github_api/repo_info.py`**

Create `src/gh_manage/github_api/repo_info.py`:

```python
"""GitHub repo metadata helpers.

Thin wrapper around `gh api repos/{repo}` returning the fields gh-manage
needs (default branch, etc.). Phase 8 adds `get_default_branch` for the
drift scanner so that `check_protection` can resolve the target branch
dynamically instead of hardcoding "main".

Uses `gh api ... --jq <field>` to extract a single field from the
response. `gh` handles the jq expression server-side-ish and returns
the bare field value (not a JSON document), so we parse it as a string
with `str.strip()`.
"""

from __future__ import annotations

from gh_manage.github_client import GhAPIError, run_gh


def get_default_branch(repo: str) -> str:
    """Resolve the default branch of `repo` via `gh api repos/{repo}
    --jq .default_branch`.

    `repo` must be in `owner/repo` form. Returns the branch name as a
    trimmed string. Raises `GhNotFoundError` for 404 (repo does not
    exist or is inaccessible) and `GhAPIError` if the response is empty
    or whitespace-only.
    """
    stdout = run_gh(["api", f"repos/{repo}", "--jq", ".default_branch"])
    branch = stdout.strip()
    if not branch:
        raise GhAPIError(
            f"Empty default_branch response for {repo!r}. "
            f"This may indicate the repo has no default branch set, or the "
            f"API returned unexpected output. "
            f"Re-run with `GH_DEBUG=api` to inspect the raw response."
        )
    return branch
```

- [ ] **Step 1.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/github_api/test_repo_info.py -v
```

Expected: 6 passed.

- [ ] **Step 1.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

Expected: all green (292 + 6 = 298 tests).

- [ ] **Step 1.6: Commit**

```bash
git add src/gh_manage/github_api/repo_info.py tests/unit/github_api/test_repo_info.py
git commit -m "$(cat <<'EOF'
feat(phase-8): add github_api/repo_info.py get_default_branch helper

Thin wrapper around `gh api repos/{repo} --jq .default_branch`. Spec-
critique CRITICAL fix for Phase 8: check_protection must resolve the
target branch dynamically instead of hardcoding "main", otherwise
repos with non-main default branches would generate false drift.

- get_default_branch(repo): returns the branch name as a trimmed string
- 404 propagates as GhNotFoundError via run_gh/run_gh_api error path
- empty response raises GhAPIError with actionable message

6 unit tests cover happy paths (main/develop/master), whitespace
stripping, argv shape (--jq .default_branch present), 404 propagation,
empty response rejection.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `drift_sync.py` scaffolding — data classes + error hierarchy + registry

**Goal:** Create the engine module's contract types. No logic yet — just dataclasses, exception classes, registry scaffold, stub check functions. Mirrors Phase 7 Task 4.

**Files:**
- Create: `src/gh_manage/drift_sync.py`
- Create: `tests/unit/drift/__init__.py`
- Create: `tests/unit/drift/test_drift_sync.py`

- [ ] **Step 2.1: Create test package marker**

Create `tests/unit/drift/__init__.py` (empty file):

```python
```

- [ ] **Step 2.2: Write the failing tests for data model + registry + errors**

Create `tests/unit/drift/test_drift_sync.py`:

```python
"""Tests for gh_manage.drift_sync — drift scanner engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from gh_manage.drift_sync import (
    DriftError,
    DriftOutputError,
    Finding,
    ScanContext,
    _CHECKS,
    register_check,
    run_all_checks,
)
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.labels import LabelsConfig
from gh_manage.models.profiles import ProfileSpec


# Data classes
def test_finding_is_frozen() -> None:
    f = Finding(
        severity="high",
        check="labels",
        repo="yakkuro/gh-manage",
        field_path="labels[priority/critical]",
        current_value=None,
        desired_value="priority/critical",
        message="Missing label",
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        f.severity = "low"  # type: ignore[misc]


def test_finding_has_remediation_default_none() -> None:
    f = Finding(
        severity="high",
        check="labels",
        repo="yakkuro/gh-manage",
        field_path="labels[x]",
        current_value=None,
        desired_value="x",
        message="m",
    )
    assert f.remediation is None


def test_finding_accepts_remediation_string() -> None:
    f = Finding(
        severity="high",
        check="labels",
        repo="yakkuro/gh-manage",
        field_path="labels[x]",
        current_value=None,
        desired_value="x",
        message="m",
        remediation="gh manage labels sync . --apply",
    )
    assert f.remediation == "gh manage labels sync . --apply"


def test_finding_equality_and_hashability() -> None:
    f1 = Finding("high", "labels", "yakkuro/gh-manage", "x", None, "y", "m")
    f2 = Finding("high", "labels", "yakkuro/gh-manage", "x", None, "y", "m")
    assert f1 == f2
    assert hash(f1) == hash(f2)


def test_scan_context_is_frozen(tmp_path: Path) -> None:
    profile = ProfileSpec(version=1, name="test", files=[])
    labels_config = LabelsConfig(version=1, categories={})
    ctx = ScanContext(
        path=tmp_path,
        repo="yakkuro/gh-manage",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=None,
    )
    with pytest.raises(Exception):
        ctx.repo = "other"  # type: ignore[misc]


# Error hierarchy
def test_all_errors_inherit_drift_error() -> None:
    assert issubclass(DriftOutputError, DriftError)


def test_drift_output_error_message_includes_context() -> None:
    err = DriftOutputError("Cannot write to /tmp/x: Permission denied")
    assert "Cannot write" in str(err)


# Registry
def test_register_check_appends_to_global_list() -> None:
    initial_count = len(_CHECKS)

    def my_check(ctx: ScanContext) -> tuple[Finding, ...]:
        return ()

    register_check(my_check)
    assert my_check in _CHECKS
    # Clean up so subsequent tests aren't affected
    _CHECKS.remove(my_check)
    assert len(_CHECKS) == initial_count


def test_register_check_returns_function(tmp_path: Path) -> None:
    def my_check(ctx: ScanContext) -> tuple[Finding, ...]:
        return ()

    result = register_check(my_check)
    assert result is my_check
    _CHECKS.remove(my_check)


def test_run_all_checks_calls_every_registered_check(tmp_path: Path) -> None:
    called: list[str] = []

    def check_a(ctx: ScanContext) -> tuple[Finding, ...]:
        called.append("a")
        return ()

    def check_b(ctx: ScanContext) -> tuple[Finding, ...]:
        called.append("b")
        return (
            Finding("low", "test", ctx.repo, "x", None, "y", "m"),
        )

    register_check(check_a)
    register_check(check_b)

    try:
        profile = ProfileSpec(version=1, name="test", files=[])
        labels_config = LabelsConfig(version=1, categories={})
        ctx = ScanContext(
            path=tmp_path, repo="yakkuro/gh-manage", default_branch="main",
            profile=profile, labels_config=labels_config, bp_config=None,
        )
        findings = run_all_checks(ctx)
        # Both called, and the one finding from check_b is returned
        # (plus any findings from registered production checks, which
        # will be empty because ctx is minimal and mocks are absent —
        # but production checks may raise; we'll tolerate that with
        # clean-up in real scenario tests).
        assert "a" in called
        assert "b" in called
        assert any(f.check == "test" for f in findings)
    finally:
        _CHECKS.remove(check_a)
        _CHECKS.remove(check_b)
```

Note: `test_run_all_checks_calls_every_registered_check` uses a minimal `ScanContext` that will make production checks fail. We call production checks too, which means we need to be careful about registration. This test is intentionally light — full end-to-end coverage comes from scenario tests in Task 5-8.

- [ ] **Step 2.3: Run tests to verify they fail**

```bash
uv run pytest tests/unit/drift/test_drift_sync.py -v
```

Expected: collection error (`gh_manage.drift_sync` doesn't exist).

- [ ] **Step 2.4: Create `drift_sync.py` with scaffolding**

Create `src/gh_manage/drift_sync.py`:

```python
"""Pure-function engine for drift detection.

Mirrors gh_manage.profile_sync / labels_sync / protection_sync. Phase 8
ships the drift scanner with a check registry pattern:

  @register_check
  def check_labels(ctx: ScanContext) -> tuple[Finding, ...]: ...

  @register_check
  def check_protection(ctx: ScanContext) -> tuple[Finding, ...]: ...

  @register_check
  def check_profile_files(ctx: ScanContext) -> tuple[Finding, ...]: ...

New checks added by future phases (workflow pinning, etc.) just write
a decorated function — the orchestrator in `run_all_checks` does not
change.

Each check:
  1. Receives a ScanContext with the resolved path, repo, default branch,
     loaded profile, labels config, and branch-protection config.
  2. Returns a tuple of Finding objects (empty if no drift detected).
  3. May perform IO (API calls, filesystem reads) — mocks happen at the
     subprocess / module-attribute boundary in tests.

Report formatters (format_*_report) are pure functions that take a
tuple of Finding objects and return a string. Destination (stdout vs
file) is decided by the CLI layer in commands/drift.py.

Section map:
  ========== Data Model ==========
  ========== Error Hierarchy ==========
  ========== Check Registry ==========
  ========== Adapters ==========
  ========== Checks ==========
  ========== Report Formatters ==========
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import Any, Literal

from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.labels import LabelsConfig
from gh_manage.models.profiles import ProfileSpec


# ========== Data Model ==========


Severity = Literal["critical", "high", "medium", "low"]


@dataclass(frozen=True)
class Finding:
    """One drift finding. Frozen, comparable, hashable.

    Phase 8 uses per-item granularity: 10 missing labels produce 10
    findings. Group rendering (if ever needed) happens at the report
    layer; the Finding itself is atomic.
    """

    severity: Severity
    check: str              # "labels" | "protection" | "profile_files"
    repo: str               # "owner/repo"
    field_path: str         # e.g. "labels[priority/critical]", "enforce_admins", "CLAUDE.md"
    current_value: Any      # current value on the repo (None if missing)
    desired_value: Any      # desired value per profile/policy (None if extraneous)
    message: str            # human-readable 1-line explanation
    remediation: str | None = None  # optional fix command


@dataclass(frozen=True)
class ScanContext:
    """Input bundle for a drift scan. All checks read from ctx — they do
    not touch global state or pass extra arguments to each other.

    - path: local repo root (for file-based checks).
    - repo: "owner/repo" for API-based checks.
    - default_branch: resolved via `get_default_branch(repo)` at CLI
      startup. check_protection uses this instead of hardcoded "main".
    - profile: the loaded ProfileSpec.
    - labels_config: the loaded bundled labels.yml.
    - bp_config: the loaded bundled branch-protection.yml, or None if
      profile.protection_policy is None (opt-out).
    """

    path: Path
    repo: str
    default_branch: str
    profile: ProfileSpec
    labels_config: LabelsConfig
    bp_config: BranchProtectionConfig | None


# ========== Error Hierarchy ==========


class DriftError(Exception):
    """Base for drift_sync errors. Caught by commands/_handle_errors."""


class DriftOutputError(DriftError):
    """Failed to write the drift report to --output <path>. Wraps the
    underlying OSError with an actionable message."""


# ========== Check Registry ==========


CheckFn = Callable[["ScanContext"], tuple[Finding, ...]]
_CHECKS: list[CheckFn] = []


def register_check(fn: CheckFn) -> CheckFn:
    """Decorator: register a check function in the global registry.

    Intended usage:

        @register_check
        def check_labels(ctx: ScanContext) -> tuple[Finding, ...]:
            ...

    Order of registration determines order of execution in
    run_all_checks. Phase 8 registers check_labels, check_protection,
    check_profile_files in that order.
    """
    _CHECKS.append(fn)
    return fn


def run_all_checks(ctx: ScanContext) -> tuple[Finding, ...]:
    """Run every registered check in order and concatenate findings.

    Fail-fast: if a check raises, the exception propagates and no
    further checks run. MVP does not have a --continue-on-error flag;
    that is filed as a Phase 8.5+ Issue.
    """
    return tuple(chain.from_iterable(check(ctx) for check in _CHECKS))


# ========== Adapters ==========
# Implementation lands in Tasks 5, 6


# ========== Checks ==========
# Implementation lands in Tasks 5, 7, 8


# ========== Report Formatters ==========
# Implementation lands in Tasks 10, 11
```

- [ ] **Step 2.5: Run tests to verify they pass**

```bash
uv run pytest tests/unit/drift/test_drift_sync.py -v
```

Expected: 11 passed.

- [ ] **Step 2.6: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

Expected: all green (298 + 11 = 309 tests).

- [ ] **Step 2.7: Commit**

```bash
git add src/gh_manage/drift_sync.py tests/unit/drift/__init__.py tests/unit/drift/test_drift_sync.py
git commit -m "$(cat <<'EOF'
feat(phase-8): add drift_sync scaffold (Finding, ScanContext, registry)

Foundational types for the drift scanner engine:
- Finding (frozen dataclass): severity, check, repo, field_path,
  current_value, desired_value, message, remediation. Per-item
  granularity: 10 missing labels = 10 findings.
- ScanContext (frozen dataclass): path, repo, default_branch, profile,
  labels_config, bp_config. default_branch is resolved dynamically at
  CLI startup (spec-critique CRITICAL fix, no hardcoded "main").
- DriftError base + DriftOutputError for --output write failures.
- Check registry (_CHECKS list + register_check decorator +
  run_all_checks orchestrator). New checks added in future phases just
  write a decorated function — run_all_checks does not change.

Section comments lay out where adapters/checks/formatters land in
subsequent tasks.

11 unit tests cover data class frozen-ness, equality/hashability,
error hierarchy, registry append/return, run_all_checks orchestrator.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `_filter_by_severity` helper

**Goal:** Implement the severity filter used by the CLI to drop findings below `--severity`.

**Files:**
- Modify: `src/gh_manage/drift_sync.py` (add `_filter_by_severity`)
- Modify: `tests/unit/drift/test_drift_sync.py` (append tests)

- [ ] **Step 3.1: Append failing tests**

Append to `tests/unit/drift/test_drift_sync.py`:

```python
from gh_manage.drift_sync import _filter_by_severity


def _f(severity: str) -> Finding:
    return Finding(
        severity=severity,  # type: ignore[arg-type]
        check="test",
        repo="yakkuro/gh-manage",
        field_path="x",
        current_value=None,
        desired_value="y",
        message="m",
    )


def test_filter_by_severity_keeps_matching_and_higher() -> None:
    findings = (_f("critical"), _f("high"), _f("medium"), _f("low"))
    result = _filter_by_severity(findings, "high")
    assert len(result) == 2
    assert result[0].severity == "critical"
    assert result[1].severity == "high"


def test_filter_by_severity_empty_input() -> None:
    assert _filter_by_severity((), "low") == ()


def test_filter_by_severity_low_keeps_everything() -> None:
    findings = (_f("critical"), _f("high"), _f("medium"), _f("low"))
    result = _filter_by_severity(findings, "low")
    assert len(result) == 4


def test_filter_by_severity_critical_keeps_only_critical() -> None:
    findings = (_f("critical"), _f("high"), _f("medium"), _f("low"))
    result = _filter_by_severity(findings, "critical")
    assert len(result) == 1
    assert result[0].severity == "critical"


def test_filter_by_severity_preserves_order() -> None:
    findings = (_f("low"), _f("high"), _f("low"), _f("critical"))
    result = _filter_by_severity(findings, "high")
    # Input order preserved, low entries dropped
    assert [f.severity for f in result] == ["high", "critical"]
```

- [ ] **Step 3.2: Verify they fail**

```bash
uv run pytest tests/unit/drift/test_drift_sync.py::test_filter_by_severity_keeps_matching_and_higher -v
```

Expected: ImportError on `_filter_by_severity`.

- [ ] **Step 3.3: Implement `_filter_by_severity`**

In `src/gh_manage/drift_sync.py`, add after the `run_all_checks` function (in the Check Registry section):

```python
_SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def _filter_by_severity(
    findings: tuple[Finding, ...], min_severity: Severity
) -> tuple[Finding, ...]:
    """Filter findings to those with severity >= min_severity.

    Hierarchy (highest to lowest): critical > high > medium > low.
    Input order is preserved for stable reporting.
    """
    threshold = _SEVERITY_RANK[min_severity]
    return tuple(
        f for f in findings if _SEVERITY_RANK[f.severity] >= threshold
    )
```

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/drift/test_drift_sync.py -v
```

Expected: 16 passed (11 existing + 5 new).

- [ ] **Step 3.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

Expected: all green (309 + 5 = 314 tests).

- [ ] **Step 3.6: Commit**

```bash
git add src/gh_manage/drift_sync.py tests/unit/drift/test_drift_sync.py
git commit -m "$(cat <<'EOF'
feat(phase-8): implement _filter_by_severity in drift_sync

Hierarchy (highest to lowest): critical > high > medium > low. Used
by the CLI to drop findings below --severity. Preserves input order
so the report layer sees findings in registration order.

5 unit tests cover boundary cases (low-all, critical-only),
order preservation, empty input.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Scenario loader (`conftest.py`) — `DriftScenario` model + `_load_scenarios()`

**Goal:** Create the test infrastructure for pytest-parametrize scenario-driven tests. This task writes the loader machinery but no scenario YAML yet — scenario files are added in Tasks 5, 7, 8 alongside the corresponding checks.

**Files:**
- Create: `tests/unit/drift/conftest.py`
- Create: `tests/fixtures/drift-scenarios/.gitkeep` (so the directory exists even before scenarios are added)

- [ ] **Step 4.1: Create the empty scenarios directory**

```bash
mkdir -p tests/fixtures/drift-scenarios/labels
mkdir -p tests/fixtures/drift-scenarios/protection
mkdir -p tests/fixtures/drift-scenarios/profile_files
touch tests/fixtures/drift-scenarios/.gitkeep
```

- [ ] **Step 4.2: Create `conftest.py` with the loader**

Create `tests/unit/drift/conftest.py`:

```python
"""Shared fixtures for drift scenario tests.

Scenario fixtures live under tests/fixtures/drift-scenarios/<check>/<name>.yml.
Each YAML defines the inputs (mocked API response or on-disk file tree)
and the expected findings.

The `drift_scenario` fixture is pytest-parametrized over all discovered
YAML files and yields (path, DriftScenario) tuples. Tests can then run
the appropriate check function against the inputs and compare findings.

Sentinel `__USE_TEMPLATE__` in inputs.repo_files means "use the profile's
template content as-is" — loaders resolve it via importlib.resources.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

import pytest
import yaml
from pydantic import BaseModel, ConfigDict


class ExpectedFinding(BaseModel):
    """Match spec for an expected Finding. severity and check are
    compared exact-match; field_path_contains and message_contains are
    compared as substring."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["critical", "high", "medium", "low"]
    check: str
    field_path_contains: str | None = None
    message_contains: str | None = None


class ScenarioInputs(BaseModel):
    """Possible inputs for a drift scenario. A given scenario uses
    whichever subset is relevant to its check (labels scenarios only
    provide current_labels, etc.)."""

    model_config = ConfigDict(extra="forbid")

    current_labels: list[dict[str, str]] | None = None
    current_protection: dict[str, Any] | None = None
    repo_files: dict[str, str] | None = None


class DriftScenario(BaseModel):
    """One drift detection scenario, loaded from a YAML fixture."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    check: Literal["labels", "protection", "profile_files"]
    repo: str
    profile: str
    inputs: ScenarioInputs
    expected_findings: list[ExpectedFinding]


_SCENARIO_ROOT = (
    Path(__file__).parent.parent.parent / "fixtures" / "drift-scenarios"
)


def _load_scenarios() -> list[tuple[Path, DriftScenario]]:
    """Glob all scenario YAML files under tests/fixtures/drift-scenarios/
    and parse them into DriftScenario instances."""
    scenarios: list[tuple[Path, DriftScenario]] = []
    for yml_path in sorted(_SCENARIO_ROOT.rglob("*.yml")):
        data = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
        scenarios.append((yml_path, DriftScenario(**data)))
    return scenarios


def _load_scenario_params() -> list[tuple[Path, DriftScenario]]:
    """Called at module import time by the fixture parametrization.

    Returns an empty list if no YAML files exist yet (early-task
    execution). pytest will still collect the fixture but skip any
    test that uses it since parameter list is empty.
    """
    try:
        return _load_scenarios()
    except FileNotFoundError:
        return []


@pytest.fixture(
    params=_load_scenario_params(),
    ids=lambda p: p[0].stem if p else "no-scenarios",
)
def drift_scenario(request: pytest.FixtureRequest) -> tuple[Path, DriftScenario]:
    return request.param


def read_template_for(profile_name: str, rel_path: str) -> str:
    """Resolve the sentinel `__USE_TEMPLATE__` by reading the template
    file that the profile would copy to `rel_path`.

    Walks ProfileSpec.files entries to find an entry whose `dest` matches
    `rel_path`, then reads the corresponding `source` from the bundled
    templates/ directory via importlib.resources.
    """
    from gh_manage.config import load_config
    from gh_manage.models.profiles import ProfileSpec

    profile_path = Path(str(files("gh_manage.data.profiles") / f"{profile_name}.yml"))
    profile = load_config(profile_path, ProfileSpec)

    for entry in profile.files:
        if entry.dest == rel_path:
            templates_root = Path(str(files("gh_manage.data") / "templates"))
            template_path = templates_root / entry.source
            return template_path.read_text(encoding="utf-8")

    raise ValueError(
        f"Profile {profile_name!r} has no files entry for dest={rel_path!r}. "
        f"Either add an entry to the profile or use a concrete content "
        f"string in the scenario YAML instead of the __USE_TEMPLATE__ sentinel."
    )
```

- [ ] **Step 4.3: Write a smoke test for the loader itself**

Append to `tests/unit/drift/test_drift_sync.py`:

```python
def test_drift_scenario_loader_returns_empty_list_when_no_yaml() -> None:
    """Before any scenario YAML is added, _load_scenarios() returns []."""
    from tests.unit.drift.conftest import _load_scenarios

    # This test will be meaningful until Task 5 adds the first fixture.
    # After Task 5, the assertion below flips (use len(...) > 0).
    # We run this test now to confirm the loader machinery works without
    # any fixtures present.
    scenarios = _load_scenarios()
    # At this point in the plan (Task 4), there should be 0 fixtures.
    # If this ever fails with "> 0", update the test to assert the
    # current known count.
    assert isinstance(scenarios, list)
```

Wait — this test is fragile because later tasks add fixtures. Instead, write a minimal test that verifies the loader doesn't crash on the empty directory state. Replace the above with:

```python
def test_drift_scenario_conftest_importable() -> None:
    """Sanity check: conftest module imports cleanly and exposes the
    DriftScenario model."""
    from tests.unit.drift import conftest

    assert hasattr(conftest, "DriftScenario")
    assert hasattr(conftest, "_load_scenarios")
    assert hasattr(conftest, "read_template_for")
```

- [ ] **Step 4.4: Verify tests pass**

```bash
uv run pytest tests/unit/drift/test_drift_sync.py -v
```

Expected: all tests pass (previous 16 + 1 new = 17).

- [ ] **Step 4.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

Expected: all green (314 + 1 = 315 tests).

- [ ] **Step 4.6: Commit**

```bash
git add tests/unit/drift/conftest.py tests/unit/drift/test_drift_sync.py tests/fixtures/drift-scenarios/.gitkeep
git commit -m "$(cat <<'EOF'
test(phase-8): add drift scenario loader infrastructure

tests/unit/drift/conftest.py ships the scenario loader machinery:
- DriftScenario pydantic model with ExpectedFinding + ScenarioInputs
  (extra="forbid" on all three to catch typos early)
- _load_scenarios(): globs tests/fixtures/drift-scenarios/**/*.yml,
  parses each into DriftScenario
- drift_scenario pytest fixture: parametrized over discovered YAMLs
  (empty list if no fixtures yet — test collection still works)
- read_template_for(profile_name, rel_path): resolves the
  __USE_TEMPLATE__ sentinel by loading the profile and reading the
  matching template from package data

No scenario YAMLs exist yet — subsequent tasks (5, 7, 8) add fixtures
alongside each check implementation.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `check_labels` + `_labels_diff_to_findings` + labels scenario fixtures

**Goal:** Implement the first check (`check_labels`) end-to-end with its adapter and 4 scenario fixtures. This task also introduces the `test_scenario` parametrized function in `test_drift_sync.py`.

**Files:**
- Modify: `src/gh_manage/drift_sync.py` (add `_labels_diff_to_findings` + `check_labels`)
- Modify: `tests/unit/drift/test_drift_sync.py` (add adapter unit tests + `test_scenario`)
- Create: `tests/fixtures/drift-scenarios/labels/missing-priority-labels.yml`
- Create: `tests/fixtures/drift-scenarios/labels/extra-unknown-label.yml`
- Create: `tests/fixtures/drift-scenarios/labels/color-mismatch.yml`
- Create: `tests/fixtures/drift-scenarios/labels/description-mismatch.yml`

- [ ] **Step 5.1: Write adapter unit tests**

Append to `tests/unit/drift/test_drift_sync.py`:

```python
from gh_manage.drift_sync import _labels_diff_to_findings, check_labels
from gh_manage.github_api.labels import Label
from gh_manage.labels_sync import (
    LabelCreate,
    LabelDelete,
    LabelsDiff,
    LabelUpdate,
)


def test_labels_diff_to_findings_creates_are_high_severity() -> None:
    diff = LabelsDiff(
        renames=(),
        creates=(LabelCreate(Label("priority/critical", "b60205", "crit")),),
        updates=(),
        deletes=(),
    )
    findings = _labels_diff_to_findings(diff, "yakkuro/gh-manage")
    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].check == "labels"
    assert findings[0].repo == "yakkuro/gh-manage"
    assert "priority/critical" in findings[0].field_path
    assert "missing" in findings[0].message.lower()
    assert findings[0].remediation is not None
    assert "labels sync" in findings[0].remediation


def test_labels_diff_to_findings_deletes_are_low_severity() -> None:
    diff = LabelsDiff(
        renames=(),
        creates=(),
        updates=(),
        deletes=(LabelDelete("custom/extra"),),
    )
    findings = _labels_diff_to_findings(diff, "yakkuro/gh-manage")
    assert len(findings) == 1
    assert findings[0].severity == "low"
    assert "custom/extra" in findings[0].field_path
    # No remediation for deletes (spec says: don't propose deletion)
    assert findings[0].remediation is None


def test_labels_diff_to_findings_updates_are_medium_severity() -> None:
    # An update represents a color or description change. In Phase 5's
    # LabelsDiff, LabelUpdate carries the full Label object — the test
    # cannot easily distinguish color vs description from the Label
    # object alone, so the adapter emits severity=medium for all
    # updates regardless. If the spec later requires color (medium) vs
    # description (low) distinction, the LabelsDiff model would need
    # to carry that information.
    diff = LabelsDiff(
        renames=(),
        creates=(),
        updates=(LabelUpdate(Label("type/bug", "d93f0b", "Something broken")),),
        deletes=(),
    )
    findings = _labels_diff_to_findings(diff, "yakkuro/gh-manage")
    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert "type/bug" in findings[0].field_path


def test_labels_diff_to_findings_empty_diff_emits_no_findings() -> None:
    diff = LabelsDiff(renames=(), creates=(), updates=(), deletes=())
    findings = _labels_diff_to_findings(diff, "yakkuro/gh-manage")
    assert findings == ()
```

- [ ] **Step 5.2: Verify they fail**

```bash
uv run pytest tests/unit/drift/test_drift_sync.py::test_labels_diff_to_findings_creates_are_high_severity -v
```

Expected: ImportError on `_labels_diff_to_findings`.

- [ ] **Step 5.3: Implement the adapter**

In `src/gh_manage/drift_sync.py`, replace the `# ========== Adapters ==========` section with:

```python
# ========== Adapters ==========

from gh_manage.github_api import labels as labels_api  # noqa: E402
from gh_manage.labels_sync import LabelsDiff, compute_diff as _compute_labels_diff  # noqa: E402


def _labels_diff_to_findings(
    diff: LabelsDiff, repo: str
) -> tuple[Finding, ...]:
    """Convert a LabelsDiff into a tuple of Finding objects.

    Severity mapping:
    - creates (profile has, repo missing)     → high
    - deletes (repo has, profile missing)     → low (user may have added intentionally)
    - updates (color/description mismatch)    → medium
    - renames (label rename in profile)       → medium
    """
    findings: list[Finding] = []
    remediation = f"gh manage labels sync . --apply"

    for create in diff.creates:
        findings.append(
            Finding(
                severity="high",
                check="labels",
                repo=repo,
                field_path=f"labels[{create.label.name}]",
                current_value=None,
                desired_value=create.label.name,
                message=f"Label {create.label.name!r} is missing from the repository",
                remediation=remediation,
            )
        )
    for delete in diff.deletes:
        findings.append(
            Finding(
                severity="low",
                check="labels",
                repo=repo,
                field_path=f"labels[{delete.name}]",
                current_value=delete.name,
                desired_value=None,
                message=(
                    f"Label {delete.name!r} exists on the repository but is "
                    f"not defined in labels.yml"
                ),
                remediation=None,
            )
        )
    for update in diff.updates:
        findings.append(
            Finding(
                severity="medium",
                check="labels",
                repo=repo,
                field_path=f"labels[{update.label.name}]",
                current_value="drifted",
                desired_value=f"color={update.label.color}",
                message=(
                    f"Label {update.label.name!r} has drifted (color or "
                    f"description mismatch)"
                ),
                remediation=remediation,
            )
        )
    for rename in diff.renames:
        findings.append(
            Finding(
                severity="medium",
                check="labels",
                repo=repo,
                field_path=f"labels[{rename.old_name}]",
                current_value=rename.old_name,
                desired_value=rename.new_label.name,
                message=(
                    f"Label {rename.old_name!r} should be renamed to "
                    f"{rename.new_label.name!r}"
                ),
                remediation=remediation,
            )
        )
    return tuple(findings)
```

- [ ] **Step 5.4: Run adapter tests to verify they pass**

```bash
uv run pytest tests/unit/drift/test_drift_sync.py -v -k labels_diff_to_findings
```

Expected: 4 passed.

- [ ] **Step 5.5: Implement `check_labels`**

In `src/gh_manage/drift_sync.py`, replace the `# ========== Checks ==========` section with:

```python
# ========== Checks ==========


@register_check
def check_labels(ctx: ScanContext) -> tuple[Finding, ...]:
    """Drift check: repo labels vs ctx.labels_config.

    Calls labels_api.list_labels(ctx.repo) to fetch the current state,
    then reuses labels_sync.compute_diff() (without prune) and translates
    the resulting LabelsDiff into Finding objects.

    IO: yes (subprocess via labels_api.list_labels). Mocked at the
    module-attribute boundary (gh_manage.drift_sync.labels_api.list_labels)
    in scenario tests.

    `prune=False` is correct for drift detection: extras should be
    reported with their own severity (low) but not marked as "must
    delete". The adapter emits Finding.remediation=None for deletes
    so the user doesn't see a delete command in the report.
    """
    current = labels_api.list_labels(ctx.repo)
    diff = _compute_labels_diff(current, ctx.labels_config, prune=True)
    return _labels_diff_to_findings(diff, ctx.repo)
```

Note: `prune=True` is used here — drift scan should report extras even though we then mark them low-severity in the adapter. This lets the user SEE extras without auto-generating delete commands.

- [ ] **Step 5.6: Create label scenario fixtures**

Create `tests/fixtures/drift-scenarios/labels/missing-priority-labels.yml`:

```yaml
name: missing-priority-labels
description: Profile ships priority/* labels but repo has only type/* labels
check: labels
repo: yakkuro/test-fixture
profile: python-service
inputs:
  current_labels:
    - {name: "type/bug", color: "d73a4a", description: "Something isn't working"}
    - {name: "type/feature", color: "a2eeef", description: "New feature or request"}
    - {name: "type/docs", color: "0075ca", description: "Documentation"}
    - {name: "type/refactor", color: "fbca04", description: "Code refactoring"}
    - {name: "type/chore", color: "fef2c0", description: "Maintenance"}
expected_findings:
  - severity: high
    check: labels
    field_path_contains: "priority/critical"
    message_contains: "missing"
  - severity: high
    check: labels
    field_path_contains: "priority/high"
    message_contains: "missing"
  - severity: high
    check: labels
    field_path_contains: "priority/medium"
    message_contains: "missing"
  - severity: high
    check: labels
    field_path_contains: "priority/low"
    message_contains: "missing"
  - severity: high
    check: labels
    field_path_contains: "status/triage"
    message_contains: "missing"
  - severity: high
    check: labels
    field_path_contains: "status/in-progress"
    message_contains: "missing"
  - severity: high
    check: labels
    field_path_contains: "status/blocked"
    message_contains: "missing"
  - severity: high
    check: labels
    field_path_contains: "status/needs-info"
    message_contains: "missing"
```

Note: the exact count of missing labels depends on the bundled `labels.yml`. This fixture assumes the bundled file has `type/*`, `priority/*`, `status/*` categories. If the bundled file changes, this fixture's `expected_findings` list will need updating.

Create `tests/fixtures/drift-scenarios/labels/extra-unknown-label.yml`:

```yaml
name: extra-unknown-label
description: Repo has a label not defined in labels.yml
check: labels
repo: yakkuro/test-fixture
profile: python-service
inputs:
  current_labels:
    # All 14 bundled labels present + one extra
    - {name: "type/bug", color: "d73a4a", description: "Something isn't working"}
    - {name: "type/feature", color: "a2eeef", description: "New feature or request"}
    - {name: "type/docs", color: "0075ca", description: "Documentation"}
    - {name: "type/refactor", color: "fbca04", description: "Code refactoring"}
    - {name: "type/chore", color: "fef2c0", description: "Maintenance"}
    - {name: "priority/critical", color: "b60205", description: ""}
    - {name: "priority/high", color: "d93f0b", description: ""}
    - {name: "priority/medium", color: "fbca04", description: ""}
    - {name: "priority/low", color: "c5def5", description: ""}
    - {name: "status/triage", color: "ededed", description: ""}
    - {name: "status/in-progress", color: "0e8a16", description: ""}
    - {name: "status/blocked", color: "d93f0b", description: ""}
    - {name: "status/needs-info", color: "fbca04", description: ""}
    - {name: "custom/legacy-label", color: "000000", description: "User-added legacy label"}
expected_findings:
  - severity: low
    check: labels
    field_path_contains: "custom/legacy-label"
    message_contains: "not defined"
```

Create `tests/fixtures/drift-scenarios/labels/color-mismatch.yml`:

```yaml
name: color-mismatch
description: Repo label has wrong color
check: labels
repo: yakkuro/test-fixture
profile: python-service
inputs:
  current_labels:
    - {name: "type/bug", color: "000000", description: "Something isn't working"}   # wrong color
    - {name: "type/feature", color: "a2eeef", description: "New feature or request"}
    - {name: "type/docs", color: "0075ca", description: "Documentation"}
    - {name: "type/refactor", color: "fbca04", description: "Code refactoring"}
    - {name: "type/chore", color: "fef2c0", description: "Maintenance"}
    - {name: "priority/critical", color: "b60205", description: ""}
    - {name: "priority/high", color: "d93f0b", description: ""}
    - {name: "priority/medium", color: "fbca04", description: ""}
    - {name: "priority/low", color: "c5def5", description: ""}
    - {name: "status/triage", color: "ededed", description: ""}
    - {name: "status/in-progress", color: "0e8a16", description: ""}
    - {name: "status/blocked", color: "d93f0b", description: ""}
    - {name: "status/needs-info", color: "fbca04", description: ""}
expected_findings:
  - severity: medium
    check: labels
    field_path_contains: "type/bug"
    message_contains: "drifted"
```

Create `tests/fixtures/drift-scenarios/labels/description-mismatch.yml`:

```yaml
name: description-mismatch
description: Repo label has a different description from the config
check: labels
repo: yakkuro/test-fixture
profile: python-service
inputs:
  current_labels:
    - {name: "type/bug", color: "d73a4a", description: "Actually a feature"}   # wrong desc
    - {name: "type/feature", color: "a2eeef", description: "New feature or request"}
    - {name: "type/docs", color: "0075ca", description: "Documentation"}
    - {name: "type/refactor", color: "fbca04", description: "Code refactoring"}
    - {name: "type/chore", color: "fef2c0", description: "Maintenance"}
    - {name: "priority/critical", color: "b60205", description: ""}
    - {name: "priority/high", color: "d93f0b", description: ""}
    - {name: "priority/medium", color: "fbca04", description: ""}
    - {name: "priority/low", color: "c5def5", description: ""}
    - {name: "status/triage", color: "ededed", description: ""}
    - {name: "status/in-progress", color: "0e8a16", description: ""}
    - {name: "status/blocked", color: "d93f0b", description: ""}
    - {name: "status/needs-info", color: "fbca04", description: ""}
expected_findings:
  - severity: medium
    check: labels
    field_path_contains: "type/bug"
    message_contains: "drifted"
```

Note: Phase 5's `LabelsDiff` currently treats color or description differences as a single "update" with severity medium. If Phase 8.5 splits color vs description into separate severities, the adapter needs updating AND these fixtures' `expected_findings` severities change.

- [ ] **Step 5.7: Add the `test_scenario` parametrized test**

Append to `tests/unit/drift/test_drift_sync.py`:

```python
from gh_manage.config import load_config
from gh_manage.drift_sync import check_profile_files, check_protection
from gh_manage.github_api.labels import Label as LabelInfo
from gh_manage.models.branch_protection import BranchProtectionConfig
from tests.unit.drift.conftest import (
    DriftScenario,
    ExpectedFinding,
    read_template_for,
)


def _matches(actual: Finding, expected: ExpectedFinding) -> bool:
    if actual.severity != expected.severity:
        return False
    if actual.check != expected.check:
        return False
    if (
        expected.field_path_contains
        and expected.field_path_contains not in actual.field_path
    ):
        return False
    if (
        expected.message_contains
        and expected.message_contains not in actual.message
    ):
        return False
    return True


def _resolve_profile_path_for_test(name: str) -> Path:
    from importlib.resources import files

    return Path(str(files("gh_manage.data.profiles") / f"{name}.yml"))


def _resolve_labels_config_path() -> Path:
    from importlib.resources import files

    return Path(str(files("gh_manage.data") / "labels.yml"))


def _resolve_bp_config_path() -> Path:
    from importlib.resources import files

    return Path(str(files("gh_manage.data") / "branch-protection.yml"))


def test_scenario(
    drift_scenario: tuple[Path, DriftScenario],
    mocker: Any,
    tmp_path: Path,
) -> None:
    _, scenario = drift_scenario

    # Load the profile and bundled configs
    profile = load_config(_resolve_profile_path_for_test(scenario.profile), ProfileSpec)
    labels_config = load_config(_resolve_labels_config_path(), LabelsConfig)
    bp_config = load_config(_resolve_bp_config_path(), BranchProtectionConfig)

    # Build the tmp repo tree
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    if scenario.inputs.repo_files:
        for rel_path, content in scenario.inputs.repo_files.items():
            if content == "__USE_TEMPLATE__":
                content = read_template_for(scenario.profile, rel_path)
            target = repo_path / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    # Mock API boundaries based on check
    if scenario.inputs.current_labels is not None:
        mock_labels = [
            LabelInfo(
                name=lbl["name"],
                color=lbl["color"].lower(),
                description=lbl.get("description") or "",
            )
            for lbl in scenario.inputs.current_labels
        ]
        mocker.patch(
            "gh_manage.drift_sync.labels_api.list_labels",
            return_value=mock_labels,
        )
    if scenario.inputs.current_protection is not None:
        mocker.patch(
            "gh_manage.drift_sync.protection_api.get_branch_protection",
            return_value=scenario.inputs.current_protection,
        )

    ctx = ScanContext(
        path=repo_path,
        repo=scenario.repo,
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=bp_config,
    )

    check_fn = {
        "labels": check_labels,
        "protection": check_protection,
        "profile_files": check_profile_files,
    }[scenario.check]
    findings = check_fn(ctx)

    # Order-independent comparison: every expected must be matched,
    # and no extras.
    assert len(findings) == len(scenario.expected_findings), (
        f"Expected {len(scenario.expected_findings)} findings, "
        f"got {len(findings)}: {[str(f) for f in findings]}"
    )
    for expected in scenario.expected_findings:
        matches = [f for f in findings if _matches(f, expected)]
        assert matches, (
            f"No finding matches expected {expected}; got: "
            f"{[str(f) for f in findings]}"
        )
```

Note: this test imports `check_profile_files` and `check_protection` which don't exist yet. That's intentional — the import will raise until Task 7 and Task 8 add those symbols. When running tests in Task 5, we SKIP the label scenarios that use those checks via `pytest.importorskip` OR we accept the collection failure.

**Actually** — to avoid blocking Task 5 on Task 7/8 existing, refactor the imports to be **lazy** (imported inside the test function) so test_scenario collection doesn't fail:

Replace the `from gh_manage.drift_sync import check_profile_files, check_protection` line with deferred imports:

```python
def test_scenario(
    drift_scenario: tuple[Path, DriftScenario],
    mocker: Any,
    tmp_path: Path,
) -> None:
    # Deferred imports so Task 5 doesn't need check_protection /
    # check_profile_files to exist yet — they land in Tasks 7 and 8.
    from gh_manage.drift_sync import check_labels
    try:
        from gh_manage.drift_sync import check_protection
    except ImportError:
        check_protection = None  # type: ignore[assignment]
    try:
        from gh_manage.drift_sync import check_profile_files
    except ImportError:
        check_profile_files = None  # type: ignore[assignment]

    _, scenario = drift_scenario

    check_fn = {
        "labels": check_labels,
        "protection": check_protection,
        "profile_files": check_profile_files,
    }[scenario.check]

    if check_fn is None:
        pytest.skip(
            f"Check {scenario.check!r} not yet implemented "
            f"(scenario: {scenario.name})"
        )

    # ... rest as before
```

- [ ] **Step 5.8: Run scenario tests for labels**

```bash
uv run pytest tests/unit/drift/test_drift_sync.py -v -k "scenario"
```

Expected: 4 label scenarios pass (+ 7 non-scenario tests already passing from Task 4). Since Tasks 7 and 8 haven't run yet, no protection/profile_files scenarios exist to skip.

- [ ] **Step 5.9: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

Expected: all green. Test count: 315 + 4 (adapter) + 4 (scenario) = 323.

- [ ] **Step 5.10: Commit**

```bash
git add src/gh_manage/drift_sync.py tests/unit/drift/test_drift_sync.py tests/fixtures/drift-scenarios/labels/
git commit -m "$(cat <<'EOF'
feat(phase-8): implement check_labels + 4 label scenario fixtures

- _labels_diff_to_findings adapter: translates Phase 5's LabelsDiff
  (renames/creates/updates/deletes) into Finding tuples with severity
  mapping: creates=high, deletes=low (no remediation), updates=medium,
  renames=medium.
- check_labels: calls labels_api.list_labels, reuses
  labels_sync.compute_diff(prune=True), passes the diff through the
  adapter. IO boundary: labels_api.list_labels (mocked in tests).
- 4 scenario fixtures in tests/fixtures/drift-scenarios/labels/:
  missing-priority-labels, extra-unknown-label, color-mismatch,
  description-mismatch.
- test_scenario parametrized function in test_drift_sync.py. Imports
  check_protection / check_profile_files lazily so Tasks 7/8 haven't
  landed yet but the test infrastructure still runs.
- _matches helper for order-independent, partial-match assertion.

8 new tests (4 adapter unit tests + 4 label scenarios).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `_protection_diff_to_findings` adapter

**Goal:** Write the adapter that converts Phase 7's `ProtectionDiff` into drift Findings. This is a standalone task because the adapter has enough logic to warrant its own unit tests before `check_protection` is wired.

**Files:**
- Modify: `src/gh_manage/drift_sync.py` (add `_protection_diff_to_findings`)
- Modify: `tests/unit/drift/test_drift_sync.py` (append unit tests)

- [ ] **Step 6.1: Write failing adapter tests**

Append to `tests/unit/drift/test_drift_sync.py`:

```python
from gh_manage.drift_sync import _protection_diff_to_findings
from gh_manage.protection_sync import (
    DowngradeFinding,
    ProtectionDiff,
    ProtectionFieldChange,
)


def test_protection_diff_to_findings_downgrade_is_critical() -> None:
    diff = ProtectionDiff(
        changes=(ProtectionFieldChange("enforce_admins", True, False),),
        downgrades=(
            DowngradeFinding(
                field_path="enforce_admins",
                current_value=True,
                desired_value=False,
                reason="admin enforcement disabled",
            ),
        ),
        current_raw={},
        desired_raw={},
    )
    findings = _protection_diff_to_findings(diff, "yakkuro/gh-manage")
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].check == "protection"
    assert "enforce_admins" in findings[0].field_path
    assert findings[0].remediation is not None
    assert "protection sync" in findings[0].remediation


def test_protection_diff_to_findings_non_downgrade_is_medium() -> None:
    # A change that is NOT classified as a downgrade (e.g., upgrade)
    diff = ProtectionDiff(
        changes=(ProtectionFieldChange("allow_force_pushes", True, False),),
        downgrades=(),  # not a downgrade — current was weaker
        current_raw={},
        desired_raw={},
    )
    findings = _protection_diff_to_findings(diff, "yakkuro/gh-manage")
    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert "allow_force_pushes" in findings[0].field_path


def test_protection_diff_to_findings_empty_diff() -> None:
    diff = ProtectionDiff(
        changes=(), downgrades=(), current_raw={}, desired_raw={}
    )
    assert _protection_diff_to_findings(diff, "yakkuro/gh-manage") == ()
```

- [ ] **Step 6.2: Verify they fail**

```bash
uv run pytest tests/unit/drift/test_drift_sync.py -v -k protection_diff_to_findings
```

Expected: ImportError on `_protection_diff_to_findings`.

- [ ] **Step 6.3: Implement the adapter**

In `src/gh_manage/drift_sync.py`, add to the Adapters section (after `_labels_diff_to_findings`):

```python
from gh_manage.github_api import protection as protection_api  # noqa: E402
from gh_manage.protection_sync import (  # noqa: E402
    ProtectionDiff,
    compute_protection_diff,
)


def _protection_diff_to_findings(
    diff: ProtectionDiff, repo: str
) -> tuple[Finding, ...]:
    """Convert a ProtectionDiff into a tuple of Finding objects.

    Severity mapping:
    - downgrade (field in diff.downgrades)      → critical
    - non-downgrade change (e.g., upgrade side) → medium

    A change is a downgrade if its `field_path` appears in
    `diff.downgrades`. All other changes are medium severity.
    """
    downgrade_paths = {d.field_path for d in diff.downgrades}
    remediation = f"gh manage protection sync . --profile <profile> --apply"

    findings: list[Finding] = []
    for change in diff.changes:
        is_downgrade = change.field_path in downgrade_paths
        severity: Severity = "critical" if is_downgrade else "medium"

        if is_downgrade:
            downgrade_entry = next(
                d for d in diff.downgrades if d.field_path == change.field_path
            )
            message = f"Protection weakened on {change.field_path}: {downgrade_entry.reason}"
        else:
            message = f"Protection drift on {change.field_path}"

        findings.append(
            Finding(
                severity=severity,
                check="protection",
                repo=repo,
                field_path=change.field_path,
                current_value=change.current_value,
                desired_value=change.desired_value,
                message=message,
                remediation=remediation,
            )
        )
    return tuple(findings)
```

- [ ] **Step 6.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/drift/test_drift_sync.py -v -k protection_diff_to_findings
```

Expected: 3 passed.

- [ ] **Step 6.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

Expected: all green (323 + 3 = 326 tests).

- [ ] **Step 6.6: Commit**

```bash
git add src/gh_manage/drift_sync.py tests/unit/drift/test_drift_sync.py
git commit -m "$(cat <<'EOF'
feat(phase-8): add _protection_diff_to_findings adapter

Translates Phase 7's ProtectionDiff into drift Finding tuples.

Severity mapping:
- downgrade (field in diff.downgrades)      → critical
  (inherits Phase 7's "security-critical" framing; downgrade = weaker
  than current protection, matches the 13-rule detector)
- non-downgrade change (upgrade side)       → medium
  (e.g., repo has stronger state than profile, or contexts list has
  extra elements not in profile — not a weakening but still drift)

Downgrade entries reuse the DowngradeFinding.reason string as the
finding message. Non-downgrade entries get a generic "Protection drift
on X" message since we don't have rule-specific context.

3 unit tests: downgrade → critical, non-downgrade → medium, empty diff.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `check_protection` + protection scenario fixtures

**Goal:** Implement `check_protection` and add 4 protection scenario fixtures.

**Files:**
- Modify: `src/gh_manage/drift_sync.py` (add `check_protection` to the Checks section)
- Create: `tests/fixtures/drift-scenarios/protection/enforce-admins-weakened.yml`
- Create: `tests/fixtures/drift-scenarios/protection/required-contexts-shrunk.yml`
- Create: `tests/fixtures/drift-scenarios/protection/reviews-removed.yml`
- Create: `tests/fixtures/drift-scenarios/protection/allow-force-pushes-enabled.yml`

- [ ] **Step 7.1: Implement `check_protection`**

In `src/gh_manage/drift_sync.py`, add to the Checks section (after `check_labels`):

```python
from gh_manage.github_client import GhNotFoundError  # noqa: E402


@register_check
def check_protection(ctx: ScanContext) -> tuple[Finding, ...]:
    """Drift check: current branch protection vs profile's policy.

    Returns early with an empty tuple if:
    - ctx.profile.protection_policy is None (opt-out — profile does
      not manage protection)
    - ctx.bp_config is None (CLI builder did not load branch-protection.yml)

    Otherwise:
    1. Look up the policy in ctx.bp_config.policies by name.
    2. Fetch current protection via protection_api.get_branch_protection
       on ctx.default_branch. 404 → treat as empty dict.
    3. Compute diff via protection_sync.compute_protection_diff.
    4. Pass the diff through _protection_diff_to_findings.

    IO: yes (subprocess via protection_api). Mocked at
    gh_manage.drift_sync.protection_api.get_branch_protection in
    scenario tests.
    """
    if ctx.profile.protection_policy is None or ctx.bp_config is None:
        return ()

    policy = ctx.bp_config.policies[ctx.profile.protection_policy]
    try:
        current = protection_api.get_branch_protection(ctx.repo, ctx.default_branch)
    except GhNotFoundError:
        current = {}

    diff = compute_protection_diff(current, policy, ctx.profile, ctx.default_branch)
    return _protection_diff_to_findings(diff, ctx.repo)
```

- [ ] **Step 7.2: Verify drift_sync still imports**

```bash
uv run python -c "from gh_manage.drift_sync import check_protection; print(check_protection)"
```

Expected: function representation printed.

- [ ] **Step 7.3: Create protection scenario fixtures**

Create `tests/fixtures/drift-scenarios/protection/enforce-admins-weakened.yml`:

```yaml
name: enforce-admins-weakened
description: "Current repo has enforce_admins=true but policy expects false (upgrade direction)"
check: protection
repo: yakkuro/test-fixture
profile: python-service
inputs:
  current_protection:
    enforce_admins: {enabled: true}
    required_status_checks:
      strict: true
      contexts: []
    required_pull_request_reviews:
      required_approving_review_count: 0
      dismiss_stale_reviews: false
      require_code_owner_reviews: false
    required_conversation_resolution: {enabled: true}
    required_linear_history: {enabled: true}
    allow_force_pushes: {enabled: false}
    allow_deletions: {enabled: false}
expected_findings:
  - severity: medium
    check: protection
    field_path_contains: "enforce_admins"
    message_contains: "drift"
```

Note: since solo-default has `enforce_admins: false`, this fixture's current state has `enforce_admins: true` (stronger than policy). That's an upgrade (not a downgrade), so it emits severity=medium via non-downgrade path.

Create `tests/fixtures/drift-scenarios/protection/required-contexts-shrunk.yml`:

```yaml
name: required-contexts-shrunk
description: "Current has extra contexts that aren't in profile.required_contexts"
check: protection
repo: yakkuro/test-fixture
profile: python-service
inputs:
  current_protection:
    enforce_admins: {enabled: false}
    required_status_checks:
      strict: true
      contexts: ["pr-gate / test", "legacy-check"]  # legacy-check is extra
    required_pull_request_reviews:
      required_approving_review_count: 0
      dismiss_stale_reviews: false
      require_code_owner_reviews: false
    required_conversation_resolution: {enabled: true}
    required_linear_history: {enabled: true}
    allow_force_pushes: {enabled: false}
    allow_deletions: {enabled: false}
expected_findings:
  - severity: medium
    check: protection
    field_path_contains: "required_status_checks.contexts"
    message_contains: "drift"
```

Note: python-service profile has `required_contexts: []` currently, so ANY context in the current state will appear as drift. The set-based comparison in `compute_protection_diff` (MEDIUM #3 fix from Phase 7's Codex review) reports this as non-downgrade drift (the current has extras that aren't in desired — that's an "extra", not a "removed"). Severity is medium since it's not a downgrade.

Actually wait — in set-based comparison, current=["pr-gate / test", "legacy-check"] and desired=[] means `set(current) != set(desired)` so a change is emitted. Is this a downgrade?

Looking at Phase 7's `detect_downgrade` rule 7: "contexts set difference — `removed = set(current) - set(desired)`, non-empty = downgrade". Here removed = {"pr-gate / test", "legacy-check"} is non-empty, so it IS a downgrade (from current's stronger state to desired's weaker state where both contexts are removed).

So this fixture emits severity=critical not medium. Let me fix the expected_findings:

```yaml
expected_findings:
  - severity: critical
    check: protection
    field_path_contains: "required_status_checks.contexts"
    message_contains: "weakened"
```

Create `tests/fixtures/drift-scenarios/protection/reviews-removed.yml`:

```yaml
name: reviews-removed
description: "Current protection has required_pull_request_reviews=null but policy requires it"
check: protection
repo: yakkuro/test-fixture
profile: python-service
inputs:
  current_protection:
    enforce_admins: {enabled: false}
    required_status_checks:
      strict: true
      contexts: []
    required_pull_request_reviews: null
    required_conversation_resolution: {enabled: true}
    required_linear_history: {enabled: true}
    allow_force_pushes: {enabled: false}
    allow_deletions: {enabled: false}
expected_findings:
  - severity: medium
    check: protection
    field_path_contains: "required_pull_request_reviews"
    message_contains: "drift"
```

Note: policy has `required_pull_request_reviews` present. Current has it null. The diff walker emits a "required_pull_request_reviews" top-level change. `detect_downgrade` rule 4 says "wrapper drop (current has, desired None) = downgrade" — BUT here current is None and desired has it, so rule 4 does NOT fire (direction reversed). This is an upgrade (current weaker, desired stronger), so severity=medium via non-downgrade path.

Create `tests/fixtures/drift-scenarios/protection/allow-force-pushes-enabled.yml`:

```yaml
name: allow-force-pushes-enabled
description: "Current allow_force_pushes=true (weakened) but policy has false"
check: protection
repo: yakkuro/test-fixture
profile: python-service
inputs:
  current_protection:
    enforce_admins: {enabled: false}
    required_status_checks:
      strict: true
      contexts: []
    required_pull_request_reviews:
      required_approving_review_count: 0
      dismiss_stale_reviews: false
      require_code_owner_reviews: false
    required_conversation_resolution: {enabled: true}
    required_linear_history: {enabled: true}
    allow_force_pushes: {enabled: true}
    allow_deletions: {enabled: false}
expected_findings:
  - severity: medium
    check: protection
    field_path_contains: "allow_force_pushes"
    message_contains: "drift"
```

Note: `allow_force_pushes: true` is weaker than `false`. But which side is "current" in drift? Current = current repo state, Desired = policy. Phase 7's rule 11 says "allow_force_pushes false → true" is a downgrade (direction: desired weakens relative to current). Here desired=false and current=true, so we're STRENGTHENING (upgrade direction). Severity = medium via non-downgrade.

Actually, looking at it again: `detect_downgrade` receives (current, desired) and reports if desired is weaker than current. Here current=true, desired=false, so desired is STRONGER than current — NOT a downgrade. Severity=medium.

- [ ] **Step 7.4: Run scenario tests**

```bash
uv run pytest tests/unit/drift/test_drift_sync.py -v -k "scenario"
```

Expected: 4 label scenarios + 4 protection scenarios = 8 parametrized cases, all pass.

- [ ] **Step 7.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

Expected: all green (326 + 4 = 330 tests).

- [ ] **Step 7.6: Commit**

```bash
git add src/gh_manage/drift_sync.py tests/fixtures/drift-scenarios/protection/
git commit -m "$(cat <<'EOF'
feat(phase-8): implement check_protection + 4 protection scenarios

- check_protection: early returns () when profile.protection_policy
  is None (opt-out). Otherwise fetches current protection via
  protection_api.get_branch_protection (404 → empty dict), feeds it
  through compute_protection_diff, and converts the result via the
  _protection_diff_to_findings adapter.
- Uses ctx.default_branch (not hardcoded "main") per the spec-critique
  CRITICAL fix.
- IO boundary: protection_api.get_branch_protection.

4 scenario fixtures:
- enforce-admins-weakened: upgrade direction, severity=medium
- required-contexts-shrunk: contexts set shrinkage, severity=critical
  (downgrade detected by rule 7)
- reviews-removed: current has no reviews but policy requires them,
  severity=medium (upgrade direction)
- allow-force-pushes-enabled: current allows force push but policy
  forbids it, severity=medium (upgrade direction)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `check_profile_files` + profile_files scenario fixtures

**Goal:** Implement the third check — comparing local repo files against the profile's template files.

**Files:**
- Modify: `src/gh_manage/drift_sync.py` (add `check_profile_files`)
- Create: `tests/fixtures/drift-scenarios/profile_files/claude-md-modified.yml`
- Create: `tests/fixtures/drift-scenarios/profile_files/ci-yml-drifted.yml`
- Create: `tests/fixtures/drift-scenarios/profile_files/missing-file.yml`

- [ ] **Step 8.1: Implement `check_profile_files`**

In `src/gh_manage/drift_sync.py`, add to the Checks section (after `check_protection`):

```python
import hashlib  # noqa: E402
from importlib.resources import files as _package_files  # noqa: E402


def _read_template_content(source: str) -> str:
    """Read a template file from the bundled gh_manage.data.templates
    package data. `source` is relative path like "ci/python-ci.yml"."""
    templates_root = Path(str(_package_files("gh_manage.data") / "templates"))
    template_path = templates_root / source
    return template_path.read_text(encoding="utf-8")


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@register_check
def check_profile_files(ctx: ScanContext) -> tuple[Finding, ...]:
    """Drift check: local repo files vs profile's template files.

    For each entry in ctx.profile.files:
    - Read the template content from gh_manage.data.templates/<source>.
    - Check if ctx.path / entry.dest exists.
      - Missing + skip_if_exists=False → severity=medium, "missing file"
      - Missing + skip_if_exists=True  → no finding (user opted out)
    - Compare content hashes:
      - Match → no finding
      - Mismatch + skip_if_exists=False → severity=medium, "content drifted"
      - Mismatch + skip_if_exists=True  → severity=low, "content drifted" (informational)

    IO: yes (filesystem reads). Tests inject scenario state via tmp_path
    in the conftest `drift_scenario` fixture.
    """
    findings: list[Finding] = []
    remediation_apply = (
        f"gh manage apply . --profile {ctx.profile.name} --apply"
    )

    for entry in ctx.profile.files:
        local = ctx.path / entry.dest
        template_content = _read_template_content(entry.source)
        template_hash = _content_hash(template_content)

        if not local.exists():
            if entry.skip_if_exists:
                continue
            findings.append(
                Finding(
                    severity="medium",
                    check="profile_files",
                    repo=ctx.repo,
                    field_path=entry.dest,
                    current_value=None,
                    desired_value=f"<template {entry.source}>",
                    message=(
                        f"Profile file {entry.dest!r} is missing from the "
                        f"repository (template: {entry.source!r})"
                    ),
                    remediation=remediation_apply,
                )
            )
            continue

        local_content = local.read_text(encoding="utf-8")
        local_hash = _content_hash(local_content)
        if local_hash == template_hash:
            continue

        # Content mismatch
        severity: Severity = "low" if entry.skip_if_exists else "medium"
        findings.append(
            Finding(
                severity=severity,
                check="profile_files",
                repo=ctx.repo,
                field_path=entry.dest,
                current_value=f"hash={local_hash[:12]}",
                desired_value=f"hash={template_hash[:12]}",
                message=(
                    f"Profile file {entry.dest!r} has drifted from the "
                    f"template {entry.source!r}"
                    + (" (user-editable)" if entry.skip_if_exists else "")
                ),
                remediation=remediation_apply if not entry.skip_if_exists else None,
            )
        )
    return tuple(findings)
```

- [ ] **Step 8.2: Create profile_files scenario fixtures**

Create `tests/fixtures/drift-scenarios/profile_files/claude-md-modified.yml`:

```yaml
name: claude-md-modified
description: "Local CLAUDE.md has been user-edited (skip_if_exists=true) — low severity informational"
check: profile_files
repo: yakkuro/test-fixture
profile: python-service
inputs:
  repo_files:
    CLAUDE.md: |
      # My customized CLAUDE.md
      User-specific instructions that differ from the template.
    .github/workflows/ci.yml: "__USE_TEMPLATE__"
expected_findings:
  - severity: low
    check: profile_files
    field_path_contains: "CLAUDE.md"
    message_contains: "drifted"
```

Create `tests/fixtures/drift-scenarios/profile_files/ci-yml-drifted.yml`:

```yaml
name: ci-yml-drifted
description: "Local ci.yml content differs from template (skip_if_exists=false) — medium severity"
check: profile_files
repo: yakkuro/test-fixture
profile: python-service
inputs:
  repo_files:
    CLAUDE.md: "__USE_TEMPLATE__"
    .github/workflows/ci.yml: |
      name: Customized CI
      on: [push]
      jobs:
        test:
          runs-on: ubuntu-latest
          steps:
            - run: echo "custom"
expected_findings:
  - severity: medium
    check: profile_files
    field_path_contains: ".github/workflows/ci.yml"
    message_contains: "drifted"
```

Create `tests/fixtures/drift-scenarios/profile_files/missing-file.yml`:

```yaml
name: missing-file
description: "ci.yml is missing from the repo (not skip_if_exists) — medium severity"
check: profile_files
repo: yakkuro/test-fixture
profile: python-service
inputs:
  repo_files:
    CLAUDE.md: "__USE_TEMPLATE__"
    # .github/workflows/ci.yml intentionally missing
expected_findings:
  - severity: medium
    check: profile_files
    field_path_contains: ".github/workflows/ci.yml"
    message_contains: "missing"
```

Note: these fixtures assume python-service has CLAUDE.md with `skip_if_exists: true` and ci.yml without that flag. Verify by reading `src/gh_manage/data/profiles/python-service.yml`. If the fields differ, adjust the expected severities accordingly.

- [ ] **Step 8.3: Run scenario tests**

```bash
uv run pytest tests/unit/drift/test_drift_sync.py -v -k "scenario"
```

Expected: 4 labels + 4 protection + 3 profile_files = 11 scenarios, all pass.

- [ ] **Step 8.4: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

Expected: all green (330 + 3 = 333 tests).

- [ ] **Step 8.5: Commit**

```bash
git add src/gh_manage/drift_sync.py tests/fixtures/drift-scenarios/profile_files/
git commit -m "$(cat <<'EOF'
feat(phase-8): implement check_profile_files + 3 profile_files scenarios

- _read_template_content: reads a template file from gh_manage.data.
  templates via importlib.resources.
- _content_hash: SHA256 hex digest of a string (full precision, first
  12 chars shown in Finding current/desired_value for readability).
- check_profile_files: iterates profile.files entries, compares
  template hash to local file hash. Missing (not skip_if_exists) →
  severity=medium. Mismatch (not skip_if_exists) → severity=medium.
  Mismatch (skip_if_exists=true) → severity=low + remediation=None
  (user-editable, don't propose overwrite).

3 scenario fixtures:
- claude-md-modified: CLAUDE.md edited, skip_if_exists=true → severity=low
- ci-yml-drifted: ci.yml content differs → severity=medium
- missing-file: ci.yml not present → severity=medium "missing"

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Golden test (self-dogfood)

**Goal:** Add a test that runs all 3 checks against production config and asserts zero findings (when APIs are mocked to return matching state).

**Files:**
- Modify: `tests/unit/drift/test_drift_sync.py` (append golden test)

- [ ] **Step 9.1: Write the golden test**

Append to `tests/unit/drift/test_drift_sync.py`:

```python
def test_golden_production_data_zero_drift(
    mocker: Any, tmp_path: Path
) -> None:
    """Self-dogfood golden test: when the production config is loaded
    and the mocked API returns the exact same state, run_all_checks
    returns zero findings.

    This is the "baseline" test — any Phase 8+ change that breaks the
    identity property (equal state → zero findings) fails here.
    """
    from importlib.resources import files

    from gh_manage.drift_sync import (
        check_labels,
        check_profile_files,
        check_protection,
    )
    from gh_manage.models.labels import LabelsConfig
    from gh_manage.models.profiles import ProfileSpec
    from gh_manage.protection_sync import build_desired_protection

    # Load bundled configs
    profile = load_config(
        Path(str(files("gh_manage.data.profiles") / "python-service.yml")),
        ProfileSpec,
    )
    labels_config = load_config(
        Path(str(files("gh_manage.data") / "labels.yml")),
        LabelsConfig,
    )
    bp_config = load_config(
        Path(str(files("gh_manage.data") / "branch-protection.yml")),
        BranchProtectionConfig,
    )

    # Build a tmp repo with every profile.files entry materialized from
    # its template (so check_profile_files sees zero drift).
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    for entry in profile.files:
        template_root = Path(str(files("gh_manage.data") / "templates"))
        content = (template_root / entry.source).read_text(encoding="utf-8")
        local = repo_path / entry.dest
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(content, encoding="utf-8")

    # Mock labels API to return exactly the bundled labels.yml content.
    from gh_manage.github_api.labels import Label as LabelInfo
    from gh_manage.labels_sync import _flatten_desired, _spec_to_label  # type: ignore[attr-defined]

    bundled_labels = [
        _spec_to_label(spec) for spec in _flatten_desired(labels_config)
    ]
    mocker.patch(
        "gh_manage.drift_sync.labels_api.list_labels",
        return_value=bundled_labels,
    )

    # Mock protection API to return the exact shape that
    # build_desired_protection would PUT — that way compute_diff sees
    # no changes.
    policy = bp_config.policies[profile.protection_policy]  # type: ignore[index]
    desired_put_body = build_desired_protection(policy, profile)

    # GitHub's GET response wraps enforce_admins etc. in {enabled: bool}.
    # For the test, we can pass a synthetic current_raw that normalizes
    # to the same canonical shape as desired.
    mocker.patch(
        "gh_manage.drift_sync.protection_api.get_branch_protection",
        return_value={
            "enforce_admins": {"enabled": desired_put_body["enforce_admins"]},
            "required_status_checks": desired_put_body["required_status_checks"],
            "required_pull_request_reviews": desired_put_body[
                "required_pull_request_reviews"
            ],
            "required_conversation_resolution": {
                "enabled": desired_put_body["required_conversation_resolution"]
            },
            "required_linear_history": {
                "enabled": desired_put_body["required_linear_history"]
            },
            "allow_force_pushes": {"enabled": desired_put_body["allow_force_pushes"]},
            "allow_deletions": {"enabled": desired_put_body["allow_deletions"]},
        },
    )

    ctx = ScanContext(
        path=repo_path,
        repo="yakkuro/gh-manage",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=bp_config,
    )

    # Run each check individually to make failures easier to diagnose
    labels_findings = check_labels(ctx)
    assert labels_findings == (), f"check_labels drift: {labels_findings}"

    protection_findings = check_protection(ctx)
    assert protection_findings == (), f"check_protection drift: {protection_findings}"

    files_findings = check_profile_files(ctx)
    assert files_findings == (), f"check_profile_files drift: {files_findings}"
```

- [ ] **Step 9.2: Run the golden test**

```bash
uv run pytest tests/unit/drift/test_drift_sync.py::test_golden_production_data_zero_drift -v
```

Expected: PASS. If it fails, one of:
- The production data changed since the plan was written (bundled labels.yml, profile, branch-protection.yml)
- The adapter logic has a bug (drift detected where state matches)
- The mock shape doesn't match what `check_protection` sees post-normalize

Debug by running each check separately and printing findings.

- [ ] **Step 9.3: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

Expected: all green (333 + 1 = 334 tests).

- [ ] **Step 9.4: Commit**

```bash
git add tests/unit/drift/test_drift_sync.py
git commit -m "$(cat <<'EOF'
test(phase-8): add golden self-dogfood test for drift_sync

Runs all 3 checks against the bundled production config (python-service
profile + labels.yml + branch-protection.yml) with mocks returning the
exact same state. Asserts zero findings from every check.

This is the baseline identity test: equal state → zero findings. Any
Phase 8+ change that breaks this property fails here, which makes it
a strong regression guard for the adapter logic and the normalize
round-trip.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: `format_stdout_report` — human-readable output

**Goal:** Implement the first of three report formatters — human-readable stdout format.

**Files:**
- Modify: `src/gh_manage/drift_sync.py` (add `format_stdout_report`)
- Create: `tests/unit/drift/test_report_format.py`

- [ ] **Step 10.1: Write failing tests**

Create `tests/unit/drift/test_report_format.py`:

```python
"""Tests for gh_manage.drift_sync report formatters."""

from __future__ import annotations

from gh_manage.drift_sync import (
    Finding,
    format_stdout_report,
)


def _f(severity: str, check: str, field_path: str, message: str, remediation: str | None = None) -> Finding:
    return Finding(
        severity=severity,  # type: ignore[arg-type]
        check=check,
        repo="yakkuro/gh-manage",
        field_path=field_path,
        current_value=None,
        desired_value="x",
        message=message,
        remediation=remediation,
    )


def test_format_stdout_report_empty_shows_no_drift() -> None:
    report = format_stdout_report(())
    assert "No drift" in report or "0 findings" in report


def test_format_stdout_report_single_finding_shows_severity_tag() -> None:
    findings = (_f("critical", "protection", "enforce_admins", "admin weakened"),)
    report = format_stdout_report(findings)
    assert "CRITICAL" in report
    assert "enforce_admins" in report
    assert "admin weakened" in report


def test_format_stdout_report_multi_severity_order() -> None:
    findings = (
        _f("low", "labels", "x", "a"),
        _f("critical", "protection", "y", "b"),
        _f("medium", "labels", "z", "c"),
        _f("high", "profile_files", "CLAUDE.md", "d"),
    )
    report = format_stdout_report(findings)
    # Sections should appear in severity order: critical, high, medium, low
    critical_pos = report.find("CRITICAL")
    high_pos = report.find("HIGH")
    medium_pos = report.find("MEDIUM")
    low_pos = report.find("LOW")
    assert critical_pos < high_pos < medium_pos < low_pos


def test_format_stdout_report_includes_remediation() -> None:
    findings = (_f("high", "labels", "x", "missing",
                    remediation="gh manage labels sync . --apply"),)
    report = format_stdout_report(findings)
    assert "gh manage labels sync" in report


def test_format_stdout_report_summary_line() -> None:
    findings = (
        _f("critical", "protection", "a", "x"),
        _f("critical", "protection", "b", "y"),
        _f("high", "labels", "c", "z"),
    )
    report = format_stdout_report(findings)
    assert "2 critical" in report or "2 CRITICAL" in report
    assert "1 high" in report or "1 HIGH" in report
    assert "3 findings" in report or "Total: 3" in report or "3 total" in report
```

- [ ] **Step 10.2: Verify they fail**

```bash
uv run pytest tests/unit/drift/test_report_format.py -v
```

Expected: ImportError on `format_stdout_report`.

- [ ] **Step 10.3: Implement `format_stdout_report`**

In `src/gh_manage/drift_sync.py`, replace the `# ========== Report Formatters ==========` section with:

```python
# ========== Report Formatters ==========


_SEVERITY_ORDER: tuple[Severity, ...] = ("critical", "high", "medium", "low")


def _group_by_severity(
    findings: tuple[Finding, ...],
) -> dict[Severity, list[Finding]]:
    grouped: dict[Severity, list[Finding]] = {s: [] for s in _SEVERITY_ORDER}
    for f in findings:
        grouped[f.severity].append(f)
    return grouped


def _count_by_severity(findings: tuple[Finding, ...]) -> dict[Severity, int]:
    counts: dict[Severity, int] = {s: 0 for s in _SEVERITY_ORDER}
    for f in findings:
        counts[f.severity] += 1
    return counts


def format_stdout_report(findings: tuple[Finding, ...]) -> str:
    """Render findings as a human-readable stdout report.

    Layout:
      Drift report for <repo>

        [CRITICAL] <check>/<field_path>
          <message>
          Fix: <remediation>

        [HIGH] ...

      Summary: N critical, N high, N medium, N low — N findings total.

    When findings is empty, emits "No drift detected." and a summary line.
    """
    if not findings:
        return "No drift detected. 0 findings."

    grouped = _group_by_severity(findings)
    counts = _count_by_severity(findings)
    total = len(findings)
    repo = findings[0].repo  # all findings share the same repo in a single scan

    lines: list[str] = [f"Drift report for {repo}", ""]
    for severity in _SEVERITY_ORDER:
        items = grouped[severity]
        if not items:
            continue
        for item in items:
            lines.append(f"  [{severity.upper()}] {item.check}/{item.field_path}")
            lines.append(f"    {item.message}")
            if item.remediation:
                lines.append(f"    Fix: {item.remediation}")
            lines.append("")
    lines.append(
        f"Summary: {counts['critical']} critical, {counts['high']} high, "
        f"{counts['medium']} medium, {counts['low']} low — {total} findings total."
    )
    return "\n".join(lines)
```

- [ ] **Step 10.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/drift/test_report_format.py -v
```

Expected: 5 passed.

- [ ] **Step 10.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

Expected: all green (334 + 5 = 339 tests).

- [ ] **Step 10.6: Commit**

```bash
git add src/gh_manage/drift_sync.py tests/unit/drift/test_report_format.py
git commit -m "$(cat <<'EOF'
feat(phase-8): implement format_stdout_report human-readable output

Groups findings by severity (critical/high/medium/low order), prints
each with [SEVERITY] tag, check/field_path line, message, and optional
Fix: line. Summary line at the bottom with per-severity counts and
total.

Empty input → "No drift detected. 0 findings." (single-line output
suitable for CI success state).

5 unit tests cover empty, single finding, multi-severity ordering,
remediation inclusion, summary line counts.

Helpers _group_by_severity and _count_by_severity are reused by the
json/markdown formatters in subsequent tasks.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: `format_json_report` + `format_markdown_report`

**Goal:** Implement the remaining two report formatters. Bundled into one task since they reuse the same helpers.

**Files:**
- Modify: `src/gh_manage/drift_sync.py` (add `format_json_report` + `format_markdown_report`)
- Modify: `tests/unit/drift/test_report_format.py` (append tests)

- [ ] **Step 11.1: Append failing tests**

Append to `tests/unit/drift/test_report_format.py`:

```python
import json

from gh_manage.drift_sync import format_json_report, format_markdown_report


def test_format_json_report_empty_valid_shape() -> None:
    rendered = format_json_report(())
    parsed = json.loads(rendered)
    assert parsed["version"] == 1
    assert parsed["findings"] == []
    assert parsed["summary"]["total"] == 0


def test_format_json_report_single_finding_round_trip() -> None:
    findings = (_f("high", "labels", "x", "missing"),)
    rendered = format_json_report(findings)
    parsed = json.loads(rendered)
    assert parsed["version"] == 1
    assert len(parsed["findings"]) == 1
    entry = parsed["findings"][0]
    assert entry["severity"] == "high"
    assert entry["check"] == "labels"
    assert entry["repo"] == "yakkuro/gh-manage"
    assert entry["field_path"] == "x"
    assert entry["message"] == "missing"
    assert parsed["summary"]["high"] == 1
    assert parsed["summary"]["total"] == 1


def test_format_json_report_multi_finding_summary_counts() -> None:
    findings = (
        _f("critical", "protection", "a", "x"),
        _f("critical", "protection", "b", "y"),
        _f("medium", "labels", "c", "z"),
    )
    parsed = json.loads(format_json_report(findings))
    assert parsed["summary"]["critical"] == 2
    assert parsed["summary"]["medium"] == 1
    assert parsed["summary"]["high"] == 0
    assert parsed["summary"]["total"] == 3


def test_format_markdown_report_empty_no_findings_heading() -> None:
    report = format_markdown_report(())
    assert "# Drift report" in report
    assert "0 findings" in report


def test_format_markdown_report_single_finding_structure() -> None:
    findings = (_f("critical", "protection", "enforce_admins", "admin weakened"),)
    report = format_markdown_report(findings)
    assert "## Critical" in report
    assert "enforce_admins" in report
    assert "admin weakened" in report


def test_format_markdown_report_per_severity_sections() -> None:
    findings = (
        _f("critical", "protection", "a", "x"),
        _f("high", "labels", "b", "y"),
        _f("medium", "labels", "c", "z"),
    )
    report = format_markdown_report(findings)
    critical_pos = report.find("## Critical")
    high_pos = report.find("## High")
    medium_pos = report.find("## Medium")
    assert critical_pos != -1
    assert high_pos != -1
    assert medium_pos != -1
    assert critical_pos < high_pos < medium_pos
```

- [ ] **Step 11.2: Verify they fail**

```bash
uv run pytest tests/unit/drift/test_report_format.py -v -k "json_report or markdown_report"
```

Expected: ImportError.

- [ ] **Step 11.3: Implement `format_json_report`**

In `src/gh_manage/drift_sync.py`, add to the Report Formatters section:

```python
import json as _json  # noqa: E402


def format_json_report(findings: tuple[Finding, ...]) -> str:
    """Render findings as a stable JSON document.

    Shape:
      {
        "version": 1,
        "repo": "owner/repo",
        "findings": [{...}, ...],
        "summary": {"critical": N, "high": N, "medium": N, "low": N, "total": N}
      }

    `version` is a schema version for consumers; bump if the shape
    changes incompatibly. `repo` is the first finding's repo (all
    findings in a single scan share the same repo). `findings` is a
    list of per-finding dicts with every Finding field except
    `current_value` / `desired_value` serialized via json.dumps
    defaults (complex types fall back to repr).
    """
    repo = findings[0].repo if findings else ""
    counts = _count_by_severity(findings)

    def _finding_to_dict(f: Finding) -> dict[str, Any]:
        return {
            "severity": f.severity,
            "check": f.check,
            "repo": f.repo,
            "field_path": f.field_path,
            "current_value": f.current_value,
            "desired_value": f.desired_value,
            "message": f.message,
            "remediation": f.remediation,
        }

    doc = {
        "version": 1,
        "repo": repo,
        "findings": [_finding_to_dict(f) for f in findings],
        "summary": {
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
            "low": counts["low"],
            "total": len(findings),
        },
    }
    return _json.dumps(doc, indent=2, default=str)
```

- [ ] **Step 11.4: Implement `format_markdown_report`**

In `src/gh_manage/drift_sync.py`, add to the Report Formatters section:

```python
def format_markdown_report(findings: tuple[Finding, ...]) -> str:
    """Render findings as GitHub-flavored markdown suitable for an
    Issue body or a standalone report file.

    Layout:
      # Drift report — `<repo>`

      **Summary**: N critical, N high, N medium, N low — N findings total.

      ## Critical

      ### `check/field_path`

      <message>

      - **Current**: `<current_value>`
      - **Desired**: `<desired_value>`
      - **Fix**: `<remediation>`

      ## High
      ...
    """
    if not findings:
        return "# Drift report\n\n0 findings. No drift detected.\n"

    repo = findings[0].repo
    counts = _count_by_severity(findings)
    total = len(findings)
    grouped = _group_by_severity(findings)

    lines: list[str] = [
        f"# Drift report — `{repo}`",
        "",
        (
            f"**Summary**: {counts['critical']} critical, {counts['high']} high, "
            f"{counts['medium']} medium, {counts['low']} low — {total} findings total."
        ),
        "",
    ]

    section_titles = {
        "critical": "Critical",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    }
    for severity in _SEVERITY_ORDER:
        items = grouped[severity]
        if not items:
            continue
        lines.append(f"## {section_titles[severity]}")
        lines.append("")
        for item in items:
            lines.append(f"### `{item.check}/{item.field_path}`")
            lines.append("")
            lines.append(item.message)
            lines.append("")
            lines.append(f"- **Current**: `{item.current_value}`")
            lines.append(f"- **Desired**: `{item.desired_value}`")
            if item.remediation:
                lines.append(f"- **Fix**: `{item.remediation}`")
            lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 11.5: Run tests to verify they pass**

```bash
uv run pytest tests/unit/drift/test_report_format.py -v
```

Expected: 11 passed (5 from Task 10 + 6 new).

- [ ] **Step 11.6: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

Expected: all green (339 + 6 = 345 tests).

- [ ] **Step 11.7: Commit**

```bash
git add src/gh_manage/drift_sync.py tests/unit/drift/test_report_format.py
git commit -m "$(cat <<'EOF'
feat(phase-8): implement format_json_report + format_markdown_report

format_json_report:
- Stable JSON shape with version:1, repo, findings[], summary{}
- Round-trip parseable by json.loads
- default=str fallback for unusual current_value / desired_value types

format_markdown_report:
- GitHub-flavored markdown suitable for Issue bodies or standalone files
- Per-severity sections (## Critical, ## High, ...) in severity order
- Each finding: ### heading, message, Current/Desired/Fix bullet list
- Empty → "# Drift report\n\n0 findings. No drift detected."

Both reuse _group_by_severity and _count_by_severity from Task 10.

6 new tests (3 JSON: empty, single round-trip, multi counts; 3
markdown: empty, single, multi-section ordering).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: `commands/drift.py` CLI + `cli.py` wiring

**Goal:** Replace the Phase 4 stub in `commands/drift.py` with the full click implementation. Verify `cli.py` already registers it.

**Files:**
- Modify: `src/gh_manage/commands/drift.py` (replace stub)
- Check: `src/gh_manage/cli.py` (should already register `drift`)
- Create: `tests/unit/cli/test_drift.py`

- [ ] **Step 12.1: Verify existing cli.py registration**

```bash
grep -n "drift" src/gh_manage/cli.py
```

Expected: a line like `from gh_manage.commands.drift import drift` and `main.add_command(drift)`. If not present, add them.

- [ ] **Step 12.2: Write failing CLI tests**

Create `tests/unit/cli/test_drift.py`:

```python
"""Tests for `gh manage drift` click command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from pytest_mock import MockerFixture

from gh_manage.cli import main
from gh_manage.drift_sync import Finding


def _patch_git_and_repo(
    mocker: MockerFixture, owner_repo: str = "yakkuro/gh-manage"
) -> None:
    mocker.patch(
        "gh_manage.commands.drift.git_cli.get_origin_owner_repo",
        return_value=owner_repo,
    )
    mocker.patch(
        "gh_manage.commands.drift.repo_info.get_default_branch",
        return_value="main",
    )


def _patch_run_all_checks(
    mocker: MockerFixture, findings: tuple[Finding, ...]
) -> None:
    mocker.patch(
        "gh_manage.commands.drift.drift_sync.run_all_checks",
        return_value=findings,
    )


def _sample_finding(severity: str = "high") -> Finding:
    return Finding(
        severity=severity,  # type: ignore[arg-type]
        check="labels",
        repo="yakkuro/gh-manage",
        field_path="labels[priority/critical]",
        current_value=None,
        desired_value="priority/critical",
        message="Label priority/critical is missing",
        remediation="gh manage labels sync . --apply",
    )


# Happy paths
def test_drift_stdout_no_findings(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(mocker, ())
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["drift", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "No drift" in result.output


def test_drift_stdout_with_findings_shows_report(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(mocker, (_sample_finding(),))
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["drift", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "HIGH" in result.output
    assert "priority/critical" in result.output


def test_drift_json_mode_emits_parseable_document(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(mocker, (_sample_finding(),))
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "python-service",
            "--report-mode",
            "json",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["version"] == 1
    assert parsed["findings"][0]["field_path"] == "labels[priority/critical]"


def test_drift_markdown_file_mode_writes_to_output(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(mocker, (_sample_finding(),))
    output_path = tmp_path / "drift.md"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "python-service",
            "--report-mode",
            "markdown-file",
            "--output",
            str(output_path),
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "# Drift report" in content
    assert "priority/critical" in content


def test_drift_severity_filter_drops_below_threshold(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(
        mocker,
        (
            _sample_finding("low"),
            _sample_finding("critical"),
        ),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "python-service",
            "--severity",
            "high",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    # low entry dropped, critical kept
    assert "CRITICAL" in result.output
    assert "1 findings" in result.output or "1 findings total" in result.output


# Error paths
def test_drift_unknown_profile_exits_1(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "nonexistent-profile-xyz",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "profile" in result.output.lower()


def test_drift_profile_name_path_traversal_rejected(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["drift", str(tmp_path), "--profile", "../../etc/passwd"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "invalid" in result.output.lower() or "not allowed" in result.output.lower()


def test_drift_invalid_severity_exits_2(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "python-service",
            "--severity",
            "urgent",  # not a valid level
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 2


def test_drift_output_path_write_failure_raises(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(mocker, (_sample_finding(),))
    # Output to a path under a nonexistent parent
    bad_output = tmp_path / "nonexistent-dir" / "drift.md"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "python-service",
            "--report-mode",
            "markdown-file",
            "--output",
            str(bad_output),
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "Cannot write" in result.output or "cannot write" in result.output.lower()
```

- [ ] **Step 12.3: Replace `commands/drift.py` stub with full implementation**

Replace the entire content of `src/gh_manage/commands/drift.py` with:

```python
"""`gh manage drift` — drift scanner CLI.

Phase 8 ships the MVP: single-repo scan comparing labels, branch
protection, and profile files against the profile + policies. Reports
findings in stdout, json, or markdown-file mode. Always exit 0 on
successful scan (drift is reported, not an error).

Architecture:
  commands/drift.py (this file) — CLI input + glue
    → drift_sync.run_all_checks (engine)
    → drift_sync.format_*_report (formatters)
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage import drift_sync, git_cli
from gh_manage.config import (
    ConfigError,
    ConfigFileNotFoundError,
    load_config,
)
from gh_manage.drift_sync import (
    DriftError,
    DriftOutputError,
    ScanContext,
)
from gh_manage.git_cli import GitError
from gh_manage.github_api import repo_info
from gh_manage.github_client import GhError
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.labels import LabelsConfig
from gh_manage.models.profiles import ProfileSpec
from gh_manage.profile_sync import ProfileError
from gh_manage.protection_sync import ProtectionError

_F = TypeVar("_F", bound=Callable[..., Any])


def _handle_errors(func: _F) -> _F:
    """Decorator: catch GhError / ConfigError / GitError / ProfileError /
    ProtectionError / DriftError and re-raise as click.ClickException
    (exit 1 with `Error: <msg>`)."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (
            GhError,
            ConfigError,
            GitError,
            ProfileError,
            ProtectionError,
            DriftError,
        ) as e:
            raise click.ClickException(str(e)) from e

    return wrapper  # type: ignore[return-value]


_VALID_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _resolve_profile_path(name: str) -> Path:
    """Resolve a profile name to a bundled YAML path with path-traversal
    defense. Mirrors commands/init.py's helper."""
    if not name or not _VALID_PROFILE_NAME_RE.match(name):
        raise ConfigFileNotFoundError(
            f"Invalid profile name: {name!r}. Profile names must be a single "
            f"identifier (alphanumeric plus `._-`, not starting with `.`). "
            f"Path separators and `..` are not allowed."
        )

    profiles_root = Path(str(files("gh_manage.data.profiles"))).resolve()
    candidate = (profiles_root / f"{name}.yml").resolve()
    if not candidate.is_relative_to(profiles_root):
        raise ConfigFileNotFoundError(
            f"Profile path resolved outside the bundled profiles directory: "
            f"{name!r} → {candidate}."
        )
    if not candidate.is_file():
        raise ConfigFileNotFoundError(
            f"Profile not found: {name!r}. Looked in {profiles_root}."
        )
    return candidate


def _resolve_default_labels_path() -> Path:
    return Path(str(files("gh_manage.data") / "labels.yml"))


def _resolve_branch_protection_path() -> Path:
    return Path(str(files("gh_manage.data") / "branch-protection.yml"))


@click.command(
    "drift",
    help=(
        "Scan a repo for config drift vs profile + policies. "
        "Always exits 0 on successful scan regardless of findings."
    ),
)
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
)
@click.option(
    "--profile",
    "profile_name",
    required=True,
    help="Profile name (resolves to bundled profiles/<name>.yml).",
)
@click.option(
    "--severity",
    type=click.Choice(["critical", "high", "medium", "low"]),
    default="low",
    help="Minimum severity to report (default: low = show everything).",
)
@click.option(
    "--report-mode",
    type=click.Choice(["stdout", "json", "markdown-file"]),
    default="stdout",
    help="Report format. Destination is --output (defaults to stdout).",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the report to this file instead of stdout.",
)
@_handle_errors
def drift(
    path: Path,
    profile_name: str,
    severity: str,
    report_mode: str,
    output: Path | None,
) -> None:
    """Scan `path` for drift against the named profile."""
    target = path.resolve()
    owner_repo = git_cli.get_origin_owner_repo(target)
    default_branch = repo_info.get_default_branch(owner_repo)

    profile = load_config(_resolve_profile_path(profile_name), ProfileSpec)
    labels_config = load_config(_resolve_default_labels_path(), LabelsConfig)

    bp_config: BranchProtectionConfig | None = None
    if profile.protection_policy is not None:
        bp_config = load_config(
            _resolve_branch_protection_path(), BranchProtectionConfig
        )
        if profile.protection_policy not in bp_config.policies:
            from gh_manage.protection_sync import ProtectionPolicyNotFoundError

            raise ProtectionPolicyNotFoundError(
                f"Policy {profile.protection_policy!r} not found in "
                f"branch-protection.yml. Available policies: "
                f"{sorted(bp_config.policies.keys())}."
            )

    ctx = ScanContext(
        path=target,
        repo=owner_repo,
        default_branch=default_branch,
        profile=profile,
        labels_config=labels_config,
        bp_config=bp_config,
    )

    all_findings = drift_sync.run_all_checks(ctx)
    filtered = drift_sync._filter_by_severity(all_findings, severity)  # type: ignore[arg-type]

    match report_mode:
        case "stdout":
            rendered = drift_sync.format_stdout_report(filtered)
        case "json":
            rendered = drift_sync.format_json_report(filtered)
        case "markdown-file":
            rendered = drift_sync.format_markdown_report(filtered)
        case _:
            # click.Choice prevents this
            raise ValueError(f"Unknown report mode: {report_mode!r}")

    if output is None:
        click.echo(rendered)
    else:
        try:
            output.write_text(rendered, encoding="utf-8")
        except OSError as e:
            raise DriftOutputError(
                f"Cannot write drift report to {output}: {e}. "
                f"Check disk space, write permissions, and that the parent "
                f"directory exists."
            ) from e
        click.echo(f"Report written to {output}")
```

- [ ] **Step 12.4: Run CLI tests to verify they pass**

```bash
uv run pytest tests/unit/cli/test_drift.py -v
```

Expected: 9 passed.

- [ ] **Step 12.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

Expected: all green (345 + 9 = 354 tests).

- [ ] **Step 12.6: Commit**

```bash
git add src/gh_manage/commands/drift.py tests/unit/cli/test_drift.py
git commit -m "$(cat <<'EOF'
feat(phase-8): implement gh manage drift CLI

Replaces the Phase 4 stub with the full drift command:

- Argument: path (default .) with Phase 6/7-style traversal defense.
- Required --profile <name>: bundled profile identifier.
- --severity: critical|high|medium|low (default low = show everything).
- --report-mode: stdout|json|markdown-file (default stdout).
- --output: optional file destination (default stdout for all modes).

Flow:
  1. Resolve path → owner_repo via git_cli.get_origin_owner_repo
  2. Resolve default_branch via repo_info.get_default_branch (1 API call,
     no hardcoded "main" — spec-critique CRITICAL fix)
  3. Load profile + labels_config
  4. If profile.protection_policy is set: load branch-protection.yml
     and validate policy exists (else ProtectionPolicyNotFoundError
     with sorted available policies list). If profile.protection_policy
     is None (opt-out): bp_config stays None.
  5. Build ScanContext
  6. drift_sync.run_all_checks → all findings
  7. _filter_by_severity → filtered findings
  8. format_*_report based on --report-mode
  9. Write to stdout or --output (OSError → DriftOutputError)

_handle_errors catches (GhError, ConfigError, GitError, ProfileError,
ProtectionError, DriftError) → ClickException (exit 1). click.Choice
handles invalid --severity / --report-mode values (exit 2).

Always exits 0 on successful scan regardless of findings.

9 CLI tests cover happy paths (stdout/json/markdown-file), severity
filter, profile errors (unknown name, path traversal), invalid
severity, output write failure.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Final gate + dogfood smoke test

**Goal:** Run the full gate one final time, perform dogfood smoke tests against `gh-manage` itself, and push the branch for PR creation.

**Files:** none modified (verification only).

- [ ] **Step 13.1: Full test suite**

```bash
uv run pytest 2>&1 | tail -10
```

Expected: ~354 tests pass (Phase 7 baseline 292 + Phase 8 additions ~62).

- [ ] **Step 13.2: Lint + format**

```bash
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
```

Expected: all clean.

- [ ] **Step 13.3: mypy (informational — yaml stub note is pre-existing)**

```bash
uv run mypy src/ 2>&1 | tail -5
```

Expected: the pre-existing yaml stub error; no new errors from Phase 8 code.

- [ ] **Step 13.4: Dogfood — `gh manage drift . --profile python-service`**

```bash
cd /home/server160/repos/gh-manage
uv run gh-manage drift . --profile python-service 2>&1
echo "real-exit=$?"
```

Expected: drift report is printed (zero or more findings depending on current gh-manage state). Exit 0. If any crash or traceback, STOP and investigate.

- [ ] **Step 13.5: Dogfood — `--report-mode json`**

```bash
uv run gh-manage drift . --profile python-service --report-mode json 2>&1 | head -20
echo "real-exit=$?"
```

Expected: parseable JSON with `"version": 1` top-level field. Exit 0.

- [ ] **Step 13.6: Dogfood — `--report-mode markdown-file --output /tmp/drift.md`**

```bash
uv run gh-manage drift . --profile python-service \
    --report-mode markdown-file --output /tmp/drift.md 2>&1
echo "real-exit=$?"
cat /tmp/drift.md | head -20
```

Expected: file written, contains `# Drift report —` heading. Exit 0.

- [ ] **Step 13.7: Push the branch**

```bash
git push -u origin feat/phase-8-drift 2>&1 | tail -5
```

- [ ] **Step 13.8: Summary for PR body**

```bash
git log --oneline main..HEAD
git diff main..HEAD --stat | tail -5
```

Expected: ~12 commits (one per Task 1-12), ~+3500/-20 lines across ~15 files.

---

## Self-Review Notes

### Spec coverage

| Spec section | Implementation task |
|---|---|
| `ScanContext` with `default_branch` (spec-critique CRITICAL fix) | Task 1 (helper) + Task 2 (field) + Task 7 (uses it) + Task 12 (resolves it at CLI startup) |
| `Finding` dataclass (rich, per-item) | Task 2 |
| Error hierarchy (DriftError, DriftOutputError) | Task 2 |
| Check registry (`@register_check`, `run_all_checks`) | Task 2 |
| `_filter_by_severity` | Task 3 |
| Scenario loader infrastructure | Task 4 |
| `check_labels` + `_labels_diff_to_findings` + fixtures | Task 5 |
| `_protection_diff_to_findings` | Task 6 |
| `check_protection` + fixtures (dynamic default_branch) | Task 7 |
| `check_profile_files` + fixtures | Task 8 |
| Golden self-dogfood test | Task 9 |
| `format_stdout_report` | Task 10 |
| `format_json_report` + `format_markdown_report` | Task 11 |
| CLI `commands/drift.py` | Task 12 |
| `profile.protection_policy is None` opt-out | Task 7 (early return) + Task 12 (bp_config=None) |
| `profile.protection_policy` misconfigured (policy not in bp_config) | Task 12 (`ProtectionPolicyNotFoundError`) |
| Label extras severity=low, explicit emit | Task 5 (adapter) + extra-unknown-label.yml |
| `_handle_errors` catches `(GhError, ConfigError, GitError, ProfileError, ProtectionError, DriftError)` | Task 12 |
| Exit 0 on drift | Task 12 (no sys.exit(1) on findings) |
| Path traversal defense | Task 12 (`_resolve_profile_path`) |
| Dogfood smoke test | Task 13 |

All spec sections have corresponding tasks.

### Placeholder scan

Scanned — no "TBD", "TODO", "implement later", or vague instructions. Every code step has complete, paste-ready content.

### Type consistency

- `Finding` constructor args identical across Tasks 2-11 (severity, check, repo, field_path, current_value, desired_value, message, remediation)
- `ScanContext` fields (path, repo, default_branch, profile, labels_config, bp_config) referenced consistently across Tasks 2, 5, 7, 8, 9, 12
- `_filter_by_severity(findings, min_severity)` signature stable across Tasks 3, 12
- Check function signature `(ctx: ScanContext) -> tuple[Finding, ...]` stable across Tasks 5, 7, 8
- `format_*_report(findings: tuple[Finding, ...]) -> str` signature stable across Tasks 10, 11, 12
- `_labels_diff_to_findings(diff, repo)` and `_protection_diff_to_findings(diff, repo)` signatures stable

### Test count progression

| After task | Count | Delta |
|---|---|---|
| Phase 7 baseline | 292 | — |
| Task 1 (repo_info) | 298 | +6 |
| Task 2 (drift_sync scaffold) | 309 | +11 |
| Task 3 (_filter_by_severity) | 314 | +5 |
| Task 4 (conftest) | 315 | +1 |
| Task 5 (check_labels + fixtures) | 323 | +8 |
| Task 6 (protection adapter) | 326 | +3 |
| Task 7 (check_protection + fixtures) | 330 | +4 |
| Task 8 (check_profile_files + fixtures) | 333 | +3 |
| Task 9 (golden test) | 334 | +1 |
| Task 10 (format_stdout_report) | 339 | +5 |
| Task 11 (format_json + markdown) | 345 | +6 |
| Task 12 (CLI) | 354 | +9 |
| Task 13 (smoke) | 354 | — |

**Target: 292 → 354 (+62 tests)**. The exact numbers may shift slightly as test counts can differ by 1-2 per task (e.g., a test might get split or merged during implementation), but the rough shape is the target.
