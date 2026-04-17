# `gh-manage doctor` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/specs/2026-04-17-doctor-guardrail-design.md`](../specs/2026-04-17-doctor-guardrail-design.md)

**Goal:** Add `gh-manage doctor` plus a drift-scanner shape check that flags consumer-repo CI/branch-protection mismatches (the class of defect that forced three admin merges during the v1.1.0 rollout — see #46).

**Architecture:** New `src/gh_manage/doctor/` package with a check registry parallel to (but independent of) `drift_sync.py`'s. A shared `findings.py` module holds `Finding` + `Severity`. A thin bridge registers one drift check that delegates to doctor. `init` runs doctor after file copy and rolls back on critical findings; `apply` emits warnings only.

**Tech Stack:** Python 3.12, `uv`, `click` 8.x, `pydantic` v2, `pyyaml`, `pytest` 8, `gh` CLI via `subprocess`. Follows the existing `src/gh_manage/` src-layout and Click command pattern.

---

## File structure

### Files created

| Path | Purpose |
|---|---|
| `src/gh_manage/findings.py` | Shared `Finding` frozen dataclass + `Severity` literal |
| `src/gh_manage/doctor/__init__.py` | Public API: `run_checks`, `run_on_path`, `run_on_remote` |
| `src/gh_manage/doctor/context.py` | `CheckContext` dataclass + `from_path`/`from_remote` builders |
| `src/gh_manage/doctor/registry.py` | `register_check` decorator, `_CHECKS` list, iteration helpers |
| `src/gh_manage/doctor/checks.py` | Three α checks + shared regex constant |
| `src/gh_manage/doctor/report.py` | `format_stdout`, `format_json`, `format_markdown` |
| `src/gh_manage/doctor/bridge.py` | `@register_check` in drift's registry; adapts `ScanContext`→`CheckContext` |
| `src/gh_manage/doctor/errors.py` | `DoctorError`, `DoctorCheckError`, `CiYmlParseError` |
| `src/gh_manage/commands/doctor.py` | Click command wiring |
| `tests/unit/doctor/__init__.py` | Empty package marker |
| `tests/unit/doctor/test_checks.py` | Per-check unit tests |
| `tests/unit/doctor/test_registry.py` | Registration / run helpers |
| `tests/unit/doctor/test_report.py` | Formatter tests |
| `tests/unit/doctor/test_broken_consumer_fixtures.py` | Snapshot regression on 3 known-broken repos |
| `tests/unit/commands/test_doctor_cli.py` | CLI option parse + exit code |
| `tests/unit/test_doctor_bridge.py` | Bridge registration + adapter |
| `tests/unit/test_context_adapter.py` | `ScanContext` fields ⊇ `CheckContext` fields |
| `tests/unit/data/test_template_shapes.py` | Bundled template passes doctor |
| `tests/fixtures/broken_consumers/tg_commander/ci.yml` | Fixture |
| `tests/fixtures/broken_consumers/tg_commander/protection.json` | Fixture |
| `tests/fixtures/broken_consumers/tg_commander/expected_findings.json` | Expected doctor output |
| `tests/fixtures/broken_consumers/repo_init/*` | Same three files |
| `tests/fixtures/broken_consumers/deep_research/*` | Same three files |
| `.github/workflows/doctor-smoke.yml` | Self-dogfood smoke test |

### Files modified

| Path | Change |
|---|---|
| `src/gh_manage/drift_sync.py` | Re-export `Finding`/`Severity` from `findings.py`; import `doctor.bridge` for side-effect registration |
| `src/gh_manage/commands/_shared.py` | Add `DoctorError` to `_DOMAIN_ERRORS` tuple |
| `src/gh_manage/commands/init.py` | Post-apply doctor + rollback; new helper `_rollback_copied` |
| `src/gh_manage/commands/apply.py` | Post-apply doctor warnings to stderr |
| `src/gh_manage/git_cli.py` | `GitError` accepts optional `stderr` arg; `_raise_classified_git_error` passes it through |
| `src/gh_manage/cli.py` | Register `doctor_cmd.doctor` on main group |
| `src/gh_manage/data/templates/ci/python-ci.yml` | Add required-shape comment |
| `pyproject.toml` | version → 1.2.0 (final task) |
| `src/gh_manage/__init__.py` | `__version__ = "1.2.0"` (final task) |
| `tests/test_sanity.py` | Assertion target updated to 1.2.0 (final task) |

---

## Task 1: Extract `Finding` and `Severity` to shared module

**Files:**
- Create: `src/gh_manage/findings.py`
- Modify: `src/gh_manage/drift_sync.py:60-80`
- Test: `tests/unit/test_findings.py`

- [ ] **Step 1: Write failing test for shared module**

Create `tests/unit/test_findings.py`:

```python
"""Finding/Severity moved out of drift_sync.py (spec §1 extraction)."""

from __future__ import annotations

import pytest


def test_finding_importable_from_findings_module():
    from gh_manage.findings import Finding, Severity

    f = Finding(
        severity="high",
        check="shape/test",
        repo="owner/repo",
        field_path="jobs.x",
        current_value="a",
        desired_value="b",
        message="test",
    )
    assert f.severity == "high"
    assert f.remediation is None
    # Frozen: mutation raises
    with pytest.raises((AttributeError, Exception)):
        f.severity = "low"  # type: ignore[misc]


def test_finding_still_importable_from_drift_sync_for_bc():
    # Backward compat: callers in drift_sync module keep working.
    from gh_manage.drift_sync import Finding as DriftFinding
    from gh_manage.findings import Finding as SharedFinding

    assert DriftFinding is SharedFinding


def test_severity_literal_values():
    from gh_manage.findings import Severity  # noqa: F401

    # Literal validation happens at type-check time; runtime is just str.
    # Smoke: ensure alias is importable.
```

- [ ] **Step 2: Run test to confirm fail**

```
uv run pytest tests/unit/test_findings.py -v
```

Expected: `ModuleNotFoundError: gh_manage.findings`.

- [ ] **Step 3: Create `src/gh_manage/findings.py`**

```python
"""Shared finding/severity types.

Extracted from drift_sync.py so both drift_sync (check_labels /
check_protection / check_profile_files) and doctor (shape checks) can
import the same type without a circular dependency.

This is the first concrete step of the drift_sync.py split tracked as
Theme A (#47). drift_sync.py continues to re-export Finding and
Severity for one release (cli/v1.2.x) to keep existing imports working.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


Severity = Literal["critical", "high", "medium", "low"]


@dataclass(frozen=True)
class Finding:
    """One finding. Frozen, hashable, comparable.

    severity
        critical | high | medium | low
    check
        Dotted category string; e.g. "labels", "protection",
        "profile_files", "shape/job-shape-coherence".
    repo
        "owner/repo"
    field_path
        Machine-parseable location of the mismatch; e.g.
        "labels[priority/critical]", "enforce_admins",
        ".github/workflows/ci.yml:jobs.pr-gate".
    current_value
        Value currently on the repo (None if missing).
    desired_value
        Value wanted by profile/policy (None if extraneous).
    message
        One-line human explanation.
    remediation
        Optional actionable hint.
    """

    severity: Severity
    check: str
    repo: str
    field_path: str
    current_value: Any
    desired_value: Any
    message: str
    remediation: str | None = None
```

- [ ] **Step 4: Remove definitions from `drift_sync.py` and re-export**

In `src/gh_manage/drift_sync.py`, replace lines 57-80 (the `Severity` alias, `Finding` dataclass, and their section header) with:

```python
# ========== Data Model (moved to findings.py in cli/v1.2.0) ==========

from gh_manage.findings import Finding, Severity  # re-export for bc

__all__ = ("Finding", "Severity", ...)  # keep existing members listed
```

If `drift_sync.py` does not currently declare `__all__`, skip that line. Keep the comment block so readers understand the move.

- [ ] **Step 5: Run test to confirm pass**

```
uv run pytest tests/unit/test_findings.py -v
```

Expected: all three tests pass.

- [ ] **Step 6: Run full suite to confirm no regression**

```
uv run pytest -q
```

Expected: all pre-existing tests still pass (Finding is now imported via re-export).

- [ ] **Step 7: Commit**

```bash
git add src/gh_manage/findings.py src/gh_manage/drift_sync.py tests/unit/test_findings.py
git commit -m "refactor: extract Finding/Severity to shared findings module

Spec §1: doctor and drift_sync both need Finding. Extract to
src/gh_manage/findings.py; drift_sync re-exports for backward
compat. First concrete step of the drift_sync.py split (#47)."
```

---

## Task 2: Doctor errors + CheckContext

**Files:**
- Create: `src/gh_manage/doctor/__init__.py`
- Create: `src/gh_manage/doctor/errors.py`
- Create: `src/gh_manage/doctor/context.py`
- Test: `tests/unit/doctor/__init__.py` + `tests/unit/doctor/test_context.py`

- [ ] **Step 1: Write failing test for errors + CheckContext**

Create `tests/unit/doctor/__init__.py` (empty).

Create `tests/unit/doctor/test_context.py`:

```python
"""CheckContext data shape and constructors (spec §1, §2)."""

from __future__ import annotations

from pathlib import Path


def test_errors_importable():
    from gh_manage.doctor.errors import CiYmlParseError, DoctorCheckError, DoctorError

    assert issubclass(DoctorCheckError, DoctorError)
    assert issubclass(CiYmlParseError, DoctorError)


def test_check_context_fields():
    from gh_manage.doctor.context import CheckContext

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="jobs: {}",
        profile_name="python-service",
        required_contexts=("PR Gate / PR Gate",),
        source_hint="test",
    )
    assert ctx.repo == "yakkuro/example"
    assert ctx.required_contexts == ("PR Gate / PR Gate",)


def test_check_context_is_frozen():
    from gh_manage.doctor.context import CheckContext

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="",
        profile_name="python-service",
        required_contexts=(),
        source_hint="test",
    )
    try:
        ctx.repo = "other/repo"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("CheckContext should be frozen (immutable)")
```

- [ ] **Step 2: Run test to confirm fail**

```
uv run pytest tests/unit/doctor/test_context.py -v
```

Expected: `ModuleNotFoundError: gh_manage.doctor`.

- [ ] **Step 3: Create `src/gh_manage/doctor/__init__.py`**

```python
"""gh-manage doctor — consumer-repo shape guardrail.

Public API (stable across cli/v1.2.x):

    run_checks(ctx) -> tuple[Finding, ...]
    run_named_checks(ctx, names) -> tuple[Finding, ...]
    run_on_path(path, profile_name=None) -> tuple[Finding, ...]
    run_on_remote(repo, profile_name=None) -> tuple[Finding, ...]

Spec: docs/specs/2026-04-17-doctor-guardrail-design.md
"""

from __future__ import annotations

# Importing checks registers them via @register_check side-effects.
from gh_manage.doctor import checks  # noqa: F401

from gh_manage.doctor.context import CheckContext
from gh_manage.doctor.errors import (
    CiYmlParseError,
    DoctorCheckError,
    DoctorError,
)
from gh_manage.doctor.registry import run_checks, run_named_checks

__all__ = [
    "CheckContext",
    "DoctorError",
    "DoctorCheckError",
    "CiYmlParseError",
    "run_checks",
    "run_named_checks",
]
```

The `run_on_path` / `run_on_remote` builders come in a later task (Task 9 wiring). Keep `__init__.py` importable now even though those names aren't present yet — add them at Task 9.

- [ ] **Step 4: Create `src/gh_manage/doctor/errors.py`**

```python
"""Doctor-specific error hierarchy.

DoctorError is caught by commands/_shared.py::handle_errors via the
_DOMAIN_ERRORS tuple (added separately in Task 8 wiring).
"""

from __future__ import annotations


class DoctorError(Exception):
    """Base for all doctor errors. Caught by CLI handle_errors."""


class CiYmlParseError(DoctorError):
    """Raised when the target repo's ci.yml cannot be parsed as YAML
    or lacks the structure doctor expects (e.g., no `jobs:` key).

    The wrapped message must include the path or repo identifier so the
    CLI caller can direct the user to the right file."""


class DoctorCheckError(DoctorError):
    """Raised when a single check function fails unexpectedly.

    The drift bridge catches this and converts it to a
    `Finding(severity='medium', check='shape/check-error', ...)` so one
    misbehaving repo does not abort a multi-repo drift scan.
    """
```

- [ ] **Step 5: Create `src/gh_manage/doctor/context.py`**

```python
"""CheckContext — the input bundle each doctor check receives.

CheckContext is frozen: checks must not mutate it. Builders (from_path
/ from_remote) live in doctor/__init__.py's run_on_* helpers, which
are added in a later task — this module defines only the data shape
here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckContext:
    """Inputs to a single-repo doctor run.

    repo
        "owner/repo" for reporting. For path-mode invocations this is
        derived from the origin remote.
    ci_yml_text
        Raw contents of the target repo's .github/workflows/ci.yml,
        or empty string if the file is absent.
    profile_name
        The gh-manage profile name the repo is being validated against.
        Used for profile-driven checks (e.g., required-contexts-match).
    required_contexts
        Tuple of status-check contexts required by the target repo's
        branch-protection policy on the default branch. Doctor derives
        these from the live protection API call; if protection lookup
        fails, this is an empty tuple.
    source_hint
        Short string describing where ci_yml_text came from (local
        path or remote fetch). Used only in error messages.
    """

    repo: str
    ci_yml_text: str
    profile_name: str
    required_contexts: tuple[str, ...]
    source_hint: str
```

- [ ] **Step 6: Run test to confirm pass**

```
uv run pytest tests/unit/doctor/test_context.py -v
```

Expected: all three tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/gh_manage/doctor/__init__.py src/gh_manage/doctor/errors.py src/gh_manage/doctor/context.py tests/unit/doctor/
git commit -m "feat(doctor): scaffold package with CheckContext and error hierarchy"
```

Note: the __init__.py currently imports `checks` which doesn't exist yet. Until Task 4 lands, run tests with `PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/doctor/test_context.py` to avoid caching a half-import. Or: temporarily stub `src/gh_manage/doctor/checks.py` as an empty file (`# populated in Task 4`) and commit it now; this is cleaner.

**Cleaner alternative — create a stub checks.py now:**

```python
# src/gh_manage/doctor/checks.py
"""Doctor α checks. Populated in Tasks 4-6."""
from __future__ import annotations
```

Stage it in the same commit so `from gh_manage.doctor import checks` in `__init__.py` works.

---

## Task 3: Doctor check registry

**Files:**
- Create: `src/gh_manage/doctor/registry.py`
- Test: `tests/unit/doctor/test_registry.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/doctor/test_registry.py`:

```python
"""Doctor registry decorator + run helpers (spec §1)."""

from __future__ import annotations

from gh_manage.doctor.context import CheckContext
from gh_manage.findings import Finding


def _ctx() -> CheckContext:
    return CheckContext(
        repo="yakkuro/example",
        ci_yml_text="",
        profile_name="python-service",
        required_contexts=(),
        source_hint="test",
    )


def test_register_check_adds_to_registry_and_run_checks_executes_all():
    from gh_manage.doctor import registry

    # Start clean
    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/a")
        def _a(ctx: CheckContext) -> tuple[Finding, ...]:
            return (
                Finding(
                    severity="low",
                    check="shape/a",
                    repo=ctx.repo,
                    field_path="x",
                    current_value=None,
                    desired_value=None,
                    message="a",
                ),
            )

        @registry.register_check("shape/b")
        def _b(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        findings = registry.run_checks(_ctx())
        assert len(findings) == 1
        assert findings[0].check == "shape/a"
    finally:
        registry._CHECKS[:] = before


def test_run_named_checks_filters_by_name():
    from gh_manage.doctor import registry

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/a")
        def _a(ctx: CheckContext) -> tuple[Finding, ...]:
            return (
                Finding("low", "shape/a", ctx.repo, "x", None, None, "a"),
            )

        @registry.register_check("shape/b")
        def _b(ctx: CheckContext) -> tuple[Finding, ...]:
            return (
                Finding("low", "shape/b", ctx.repo, "y", None, None, "b"),
            )

        findings = registry.run_named_checks(_ctx(), ("shape/b",))
        assert len(findings) == 1
        assert findings[0].check == "shape/b"
    finally:
        registry._CHECKS[:] = before


def test_run_named_checks_raises_on_unknown_name():
    import pytest

    from gh_manage.doctor import registry
    from gh_manage.doctor.errors import DoctorError

    with pytest.raises(DoctorError):
        registry.run_named_checks(_ctx(), ("shape/does-not-exist",))
```

- [ ] **Step 2: Run test to confirm fail**

```
uv run pytest tests/unit/doctor/test_registry.py -v
```

Expected: `ModuleNotFoundError: gh_manage.doctor.registry`.

- [ ] **Step 3: Create `src/gh_manage/doctor/registry.py`**

```python
"""Doctor check registry.

Deliberately parallel to drift_sync.py's _CHECKS registry rather than
sharing a single global. This keeps drift's check lifecycle (labels /
protection / profile_files) decoupled from doctor's shape/* checks —
each registry is a plain list whose order is the registration order.

register_check is a decorator factory: @register_check("shape/foo")
attaches the name to the function for later name-based filtering.
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import chain
from typing import TypeVar

from gh_manage.doctor.context import CheckContext
from gh_manage.doctor.errors import DoctorError
from gh_manage.findings import Finding

CheckFn = Callable[[CheckContext], "tuple[Finding, ...]"]
_F = TypeVar("_F", bound=CheckFn)

_CHECKS: list[CheckFn] = []


def register_check(name: str) -> Callable[[_F], _F]:
    """Decorator factory: register a check under `name`.

    The check function must accept a single `CheckContext` and return a
    tuple of `Finding` objects (possibly empty).

    Usage:

        @register_check("shape/example")
        def check_example(ctx: CheckContext) -> tuple[Finding, ...]:
            ...
    """

    def _decorator(fn: _F) -> _F:
        fn.__doctor_check_name__ = name  # type: ignore[attr-defined]
        _CHECKS.append(fn)
        return fn

    return _decorator


def run_checks(ctx: CheckContext) -> tuple[Finding, ...]:
    """Run every registered check in registration order.

    Exceptions from checks propagate — the drift bridge catches them
    and converts to a synthetic finding; the CLI converts them via
    handle_errors.
    """
    return tuple(chain.from_iterable(fn(ctx) for fn in _CHECKS))


def run_named_checks(
    ctx: CheckContext, names: tuple[str, ...]
) -> tuple[Finding, ...]:
    """Run only the checks whose registered name is in `names`.

    Raises DoctorError if any name is unknown; this fails fast rather
    than silently running zero checks when a typo slips in.
    """
    name_set = set(names)
    known = {
        getattr(fn, "__doctor_check_name__", None) for fn in _CHECKS
    }
    missing = name_set - known
    if missing:
        raise DoctorError(
            f"Unknown doctor check(s): {sorted(missing)}. "
            f"Known: {sorted(n for n in known if n)}."
        )
    selected = [
        fn for fn in _CHECKS
        if getattr(fn, "__doctor_check_name__", None) in name_set
    ]
    return tuple(chain.from_iterable(fn(ctx) for fn in selected))
```

- [ ] **Step 4: Run test to confirm pass**

```
uv run pytest tests/unit/doctor/test_registry.py -v
```

Expected: all three tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/doctor/registry.py tests/unit/doctor/test_registry.py
git commit -m "feat(doctor): add check registry with name-filtered runner"
```

---

## Task 4: Check 1 — `shape/job-shape-coherence`

**Files:**
- Modify: `src/gh_manage/doctor/checks.py`
- Test: `tests/unit/doctor/test_checks.py` (create)

- [ ] **Step 1: Write failing test**

Create `tests/unit/doctor/test_checks.py`:

```python
"""Doctor α checks (spec §3)."""

from __future__ import annotations

from gh_manage.doctor.context import CheckContext


def _ctx(ci_yml_text: str, required: tuple[str, ...]) -> CheckContext:
    return CheckContext(
        repo="yakkuro/example",
        ci_yml_text=ci_yml_text,
        profile_name="python-service",
        required_contexts=required,
        source_hint="test",
    )


def test_shape_job_shape_coherence_fires_when_context_does_not_match():
    # tg-commander case: jobs.test (no name:) -> context "test / PR Gate"
    ci_yml = """
name: CI
on: [pull_request]
jobs:
  test:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
    with:
      python-version: "3.12"
"""
    from gh_manage.doctor.checks import check_job_shape_coherence

    findings = check_job_shape_coherence(
        _ctx(ci_yml, required=("PR Gate / PR Gate",))
    )

    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "critical"
    assert f.check == "shape/job-shape-coherence"
    assert "test / PR Gate" in str(f.current_value)
    assert "PR Gate / PR Gate" in str(f.desired_value)


def test_shape_job_shape_coherence_passes_when_name_is_pr_gate():
    ci_yml = """
jobs:
  pr-gate:
    name: "PR Gate"
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
"""
    from gh_manage.doctor.checks import check_job_shape_coherence

    findings = check_job_shape_coherence(
        _ctx(ci_yml, required=("PR Gate / PR Gate",))
    )
    assert findings == ()


def test_shape_job_shape_coherence_ignores_non_reusable_jobs():
    # tg-commander had 'jobs.test' but if it used a non-reusable uses,
    # doctor's check 1 should skip it (check 2 may flag reusable-adoption).
    ci_yml = """
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""
    from gh_manage.doctor.checks import check_job_shape_coherence

    findings = check_job_shape_coherence(
        _ctx(ci_yml, required=("PR Gate / PR Gate",))
    )
    assert findings == ()


def test_shape_job_shape_coherence_missing_name_with_correct_id_still_fails():
    # deep-research case: jobs.pr-gate (no name:) -> "pr-gate / PR Gate"
    ci_yml = """
jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
"""
    from gh_manage.doctor.checks import check_job_shape_coherence

    findings = check_job_shape_coherence(
        _ctx(ci_yml, required=("PR Gate / PR Gate",))
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.current_value == "pr-gate / PR Gate"


def test_shape_job_shape_coherence_empty_ci_yml_produces_no_findings():
    # Missing-file behaviour (spec §2): job-shape check is silent;
    # reusable-adoption will fire separately.
    from gh_manage.doctor.checks import check_job_shape_coherence

    findings = check_job_shape_coherence(
        _ctx("", required=("PR Gate / PR Gate",))
    )
    assert findings == ()
```

- [ ] **Step 2: Run test to confirm fail**

```
uv run pytest tests/unit/doctor/test_checks.py -v
```

Expected: `ImportError: cannot import name 'check_job_shape_coherence'`.

- [ ] **Step 3: Implement check 1 in `src/gh_manage/doctor/checks.py`**

Replace the Task 2 stub with:

```python
"""Doctor α checks — spec §3.

Each check reads the CheckContext and returns zero or more Findings.
Checks are pure: they do not perform IO beyond parsing ci_yml_text.
IO (remote fetch) happens in the run_on_* builders, not here.
"""

from __future__ import annotations

import re

import yaml

from gh_manage.doctor.context import CheckContext
from gh_manage.doctor.errors import CiYmlParseError
from gh_manage.doctor.registry import register_check
from gh_manage.findings import Finding

# A job is a "reusable-pr-gate job" iff its `uses:` value matches this
# regex. Indirection via another composite workflow is NOT traced;
# such jobs are treated as bespoke and check_reusable_adoption applies
# instead. Spec §3 check 1.
_REUSABLE_USES_RE = re.compile(
    r"^yakkuro/gh-manage/\.github/workflows/"
    r"reusable-pr-gate-(python|typescript)\.yml@.+$"
)


def _parse_ci_yml(text: str, source_hint: str) -> dict:
    """Parse ci.yml text into a dict, or return {} if text is empty.

    Raises CiYmlParseError on malformed YAML or missing `jobs:` dict.
    """
    if not text.strip():
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise CiYmlParseError(
            f"Failed to parse ci.yml ({source_hint}) as YAML: {e}"
        ) from e
    if not isinstance(data, dict):
        raise CiYmlParseError(
            f"ci.yml ({source_hint}) top-level must be a mapping, got "
            f"{type(data).__name__}."
        )
    return data


def _iter_reusable_jobs(ci_yml: dict):
    """Yield (job_id, job_dict) for every job whose `uses` matches the
    reusable-pr-gate-* URL pattern."""
    jobs = ci_yml.get("jobs") or {}
    if not isinstance(jobs, dict):
        return
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        uses = job.get("uses")
        if isinstance(uses, str) and _REUSABLE_USES_RE.match(uses):
            yield job_id, job


@register_check("shape/job-shape-coherence")
def check_job_shape_coherence(ctx: CheckContext) -> tuple[Finding, ...]:
    """critical: produced status context must match protection's
    required context. See spec §3 check 1."""
    ci_yml = _parse_ci_yml(ctx.ci_yml_text, ctx.source_hint)
    findings: list[Finding] = []
    required_set = set(ctx.required_contexts)

    for job_id, job in _iter_reusable_jobs(ci_yml):
        display = job.get("name") or job_id
        produced = f"{display} / PR Gate"
        if produced in required_set:
            continue
        findings.append(
            Finding(
                severity="critical",
                check="shape/job-shape-coherence",
                repo=ctx.repo,
                field_path=f".github/workflows/ci.yml:jobs.{job_id}",
                current_value=produced,
                desired_value=sorted(ctx.required_contexts),
                message=(
                    f"Job 'jobs.{job_id}' produces status context "
                    f"{produced!r} but branch protection requires one of "
                    f"{sorted(ctx.required_contexts)!r}."
                ),
                remediation=(
                    "Rename the job id to 'pr-gate' AND set "
                    "'name: \"PR Gate\"', OR update branch protection "
                    f"to require {produced!r}."
                ),
            )
        )

    return tuple(findings)
```

- [ ] **Step 4: Run test to confirm pass**

```
uv run pytest tests/unit/doctor/test_checks.py -v
```

Expected: all five tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/doctor/checks.py tests/unit/doctor/test_checks.py
git commit -m "feat(doctor): add check shape/job-shape-coherence

Detects the class of ci.yml/branch-protection mismatch that forced
admin merges during the v1.1.0 rollout across tg-commander,
repo-init, and deep-research (#46)."
```

---

## Task 5: Check 2 — `shape/reusable-adoption`

**Files:**
- Modify: `src/gh_manage/doctor/checks.py` (append)
- Test: `tests/unit/doctor/test_checks.py` (append)

- [ ] **Step 1: Write failing test**

Append to `tests/unit/doctor/test_checks.py`:

```python
def test_shape_reusable_adoption_fires_when_no_reusable_job():
    # codelens / shelf-brain case: bespoke ci.yml, no reusable-pr-gate.
    ci_yml = """
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make ci
"""
    from gh_manage.doctor.checks import check_reusable_adoption

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text=ci_yml,
        profile_name="python-service",
        required_contexts=(),
        source_hint="test",
    )
    findings = check_reusable_adoption(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert findings[0].check == "shape/reusable-adoption"


def test_shape_reusable_adoption_silent_when_reusable_present():
    ci_yml = """
jobs:
  pr-gate:
    name: "PR Gate"
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
"""
    from gh_manage.doctor.checks import check_reusable_adoption

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text=ci_yml,
        profile_name="python-service",
        required_contexts=(),
        source_hint="test",
    )
    assert check_reusable_adoption(ctx) == ()


def test_shape_reusable_adoption_fires_when_ci_yml_missing():
    from gh_manage.doctor.checks import check_reusable_adoption

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="",
        profile_name="python-service",
        required_contexts=(),
        source_hint="test",
    )
    findings = check_reusable_adoption(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert "no ci.yml" in findings[0].message.lower() or "missing" in findings[0].message.lower()
```

- [ ] **Step 2: Run test to confirm fail**

```
uv run pytest tests/unit/doctor/test_checks.py::test_shape_reusable_adoption_fires_when_no_reusable_job -v
```

Expected: `ImportError: cannot import name 'check_reusable_adoption'`.

- [ ] **Step 3: Append check 2 to `src/gh_manage/doctor/checks.py`**

Add below the existing `check_job_shape_coherence`:

```python
@register_check("shape/reusable-adoption")
def check_reusable_adoption(ctx: CheckContext) -> tuple[Finding, ...]:
    """medium: flag repos in repos.yml that don't use a reusable-pr-gate.

    Severity is medium because bespoke CI is sometimes intentional
    (e.g., shelf-brain's postgres service requirement). The finding
    makes the choice explicit rather than silent.

    Spec §3 check 2.
    """
    ci_yml = _parse_ci_yml(ctx.ci_yml_text, ctx.source_hint)
    has_reusable = any(True for _ in _iter_reusable_jobs(ci_yml))
    if has_reusable:
        return ()
    if not ctx.ci_yml_text.strip():
        msg = (
            "No .github/workflows/ci.yml found; repo lists in repos.yml "
            f"with profile {ctx.profile_name!r} but uses no reusable "
            "gh-manage workflow."
        )
    else:
        msg = (
            "ci.yml is present but no job uses the reusable-pr-gate "
            f"workflow; profile {ctx.profile_name!r} expects adoption."
        )
    return (
        Finding(
            severity="medium",
            check="shape/reusable-adoption",
            repo=ctx.repo,
            field_path=".github/workflows/ci.yml",
            current_value="bespoke (no reusable-pr-gate-*)",
            desired_value=(
                f"uses: yakkuro/gh-manage/.github/workflows/"
                f"reusable-pr-gate-*.yml@<ref>"
            ),
            message=msg,
            remediation=(
                "Adopt the reusable workflow, OR remove the repo from "
                "repos.yml if intentionally bespoke."
            ),
        ),
    )
```

- [ ] **Step 4: Run all check tests**

```
uv run pytest tests/unit/doctor/test_checks.py -v
```

Expected: all eight tests pass (five from Task 4 + three new).

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/doctor/checks.py tests/unit/doctor/test_checks.py
git commit -m "feat(doctor): add check shape/reusable-adoption

Flags repos present in repos.yml whose ci.yml does not use the
reusable pr-gate. Medium severity because bespoke is sometimes the
right call (e.g., services)."
```

---

## Task 6: Check 3 — `shape/required-contexts-match`

**Files:**
- Modify: `src/gh_manage/doctor/context.py` (add `profile_required_contexts` field)
- Modify: `src/gh_manage/doctor/checks.py` (append)
- Test: `tests/unit/doctor/test_checks.py` (append)
- Modify: `tests/unit/doctor/test_context.py` (bump fixture)

- [ ] **Step 1: Extend CheckContext with profile's declared contexts**

The profile (e.g., `python-service.yml`) declares `required_contexts`. Check 3 compares that against the repo's live protection contexts (`CheckContext.required_contexts` — which was already the protection view). Add a second field for clarity.

In `src/gh_manage/doctor/context.py`:

```python
@dataclass(frozen=True)
class CheckContext:
    repo: str
    ci_yml_text: str
    profile_name: str
    required_contexts: tuple[str, ...]  # from live protection
    profile_required_contexts: tuple[str, ...] = ()  # from profile spec
    source_hint: str = "unknown"
```

Update `tests/unit/doctor/test_context.py` fixture to pass the new field defaulted:

```python
    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="jobs: {}",
        profile_name="python-service",
        required_contexts=("PR Gate / PR Gate",),
        source_hint="test",
    )
```

(`profile_required_contexts` defaults to `()`, so existing tests stay valid.)

- [ ] **Step 2: Write failing test**

Append to `tests/unit/doctor/test_checks.py`:

```python
def test_shape_required_contexts_match_flags_missing_high():
    # profile declares "PR Gate / PR Gate" but protection doesn't enforce it
    from gh_manage.doctor.checks import check_required_contexts_match

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="",
        profile_name="python-service",
        required_contexts=(),  # protection has no required checks
        profile_required_contexts=("PR Gate / PR Gate",),
        source_hint="test",
    )
    findings = check_required_contexts_match(ctx)
    high = [f for f in findings if f.severity == "high"]
    assert len(high) == 1
    assert "missing" in high[0].message.lower() or "not enforced" in high[0].message.lower()


def test_shape_required_contexts_match_flags_extra_medium():
    # protection requires extra context not declared by profile
    from gh_manage.doctor.checks import check_required_contexts_match

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="",
        profile_name="python-service",
        required_contexts=("PR Gate / PR Gate", "Custom / Other"),
        profile_required_contexts=("PR Gate / PR Gate",),
        source_hint="test",
    )
    findings = check_required_contexts_match(ctx)
    medium = [f for f in findings if f.severity == "medium"]
    assert len(medium) == 1
    assert "custom / other" in medium[0].message.lower()


def test_shape_required_contexts_match_silent_when_aligned():
    from gh_manage.doctor.checks import check_required_contexts_match

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="",
        profile_name="python-service",
        required_contexts=("PR Gate / PR Gate",),
        profile_required_contexts=("PR Gate / PR Gate",),
        source_hint="test",
    )
    assert check_required_contexts_match(ctx) == ()
```

- [ ] **Step 3: Run test to confirm fail**

```
uv run pytest tests/unit/doctor/test_checks.py::test_shape_required_contexts_match_flags_missing_high -v
```

Expected: `ImportError: cannot import name 'check_required_contexts_match'`.

- [ ] **Step 4: Append check 3 to `src/gh_manage/doctor/checks.py`**

```python
@register_check("shape/required-contexts-match")
def check_required_contexts_match(ctx: CheckContext) -> tuple[Finding, ...]:
    """Diff profile's declared required_contexts vs live protection.

    Missing (profile declares, protection lacks): severity high.
    Extra (protection enforces, profile doesn't declare): severity medium.

    Spec §3 check 3.
    """
    expected = set(ctx.profile_required_contexts)
    actual = set(ctx.required_contexts)
    findings: list[Finding] = []

    for missing in sorted(expected - actual):
        findings.append(
            Finding(
                severity="high",
                check="shape/required-contexts-match",
                repo=ctx.repo,
                field_path=f"branches/*/protection:required_status_checks.contexts[{missing}]",
                current_value=sorted(actual),
                desired_value=sorted(expected),
                message=(
                    f"Profile {ctx.profile_name!r} declares required "
                    f"context {missing!r} but branch protection is not "
                    f"enforcing it. PRs can merge without this gate."
                ),
                remediation=(
                    f"Run `gh-manage protection sync {ctx.repo} "
                    f"--profile {ctx.profile_name} --apply` to enforce."
                ),
            )
        )

    for extra in sorted(actual - expected):
        findings.append(
            Finding(
                severity="medium",
                check="shape/required-contexts-match",
                repo=ctx.repo,
                field_path=f"branches/*/protection:required_status_checks.contexts[{extra}]",
                current_value=sorted(actual),
                desired_value=sorted(expected),
                message=(
                    f"Branch protection requires context {extra!r} but "
                    f"profile {ctx.profile_name!r} does not declare it. "
                    f"Either the profile is incomplete or the protection "
                    f"is carrying a legacy requirement."
                ),
                remediation=(
                    "Add the context to the profile's required_contexts, "
                    "OR drop it from branch protection."
                ),
            )
        )

    return tuple(findings)
```

- [ ] **Step 5: Run all check tests**

```
uv run pytest tests/unit/doctor/test_checks.py -v
```

Expected: eleven tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/gh_manage/doctor/context.py src/gh_manage/doctor/checks.py tests/unit/doctor/test_checks.py tests/unit/doctor/test_context.py
git commit -m "feat(doctor): add check shape/required-contexts-match

Diffs profile.required_contexts vs live branch-protection contexts.
Missing=high (silent gate bypass), extra=medium (undocumented
invariant)."
```

---

## Task 7: Doctor report formatters

**Files:**
- Create: `src/gh_manage/doctor/report.py`
- Test: `tests/unit/doctor/test_report.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/doctor/test_report.py`:

```python
"""Doctor report formatters (spec §2 output sample + §4 drift
integration)."""

from __future__ import annotations

import json

from gh_manage.findings import Finding


def _findings() -> tuple[Finding, ...]:
    return (
        Finding(
            severity="critical",
            check="shape/job-shape-coherence",
            repo="yakkuro/example",
            field_path=".github/workflows/ci.yml:jobs.test",
            current_value="test / PR Gate",
            desired_value=["PR Gate / PR Gate"],
            message="context mismatch",
            remediation="rename the job",
        ),
    )


def test_format_stdout_contains_severity_counts_and_finding_sections():
    from gh_manage.doctor.report import format_stdout

    out = format_stdout(_findings(), repo="yakkuro/example")

    assert "yakkuro/example" in out
    assert "1 critical" in out
    assert "## critical" in out
    assert "shape/job-shape-coherence" in out
    assert "rename the job" in out


def test_format_stdout_empty_is_clean_summary():
    from gh_manage.doctor.report import format_stdout

    out = format_stdout((), repo="yakkuro/example")
    assert "0 critical" in out


def test_format_json_emits_valid_json_with_all_finding_fields():
    from gh_manage.doctor.report import format_json

    out = format_json(_findings(), repo="yakkuro/example")
    data = json.loads(out)
    assert data["repo"] == "yakkuro/example"
    assert len(data["findings"]) == 1
    f = data["findings"][0]
    assert f["severity"] == "critical"
    assert f["check"] == "shape/job-shape-coherence"
    assert f["current_value"] == "test / PR Gate"


def test_format_markdown_matches_drift_style_headers():
    from gh_manage.doctor.report import format_markdown

    out = format_markdown(_findings(), repo="yakkuro/example")
    # drift scanner issue body convention: ## <severity> header + ###
    # <check-name> subheader
    assert "## critical" in out
    assert "### shape/job-shape-coherence" in out
```

- [ ] **Step 2: Run test to confirm fail**

```
uv run pytest tests/unit/doctor/test_report.py -v
```

Expected: `ModuleNotFoundError: gh_manage.doctor.report`.

- [ ] **Step 3: Create `src/gh_manage/doctor/report.py`**

```python
"""Doctor report formatters: stdout / json / markdown.

Output conventions match drift_sync.format_*_report so the drift
scanner can emit shape findings alongside existing labels / protection
/ profile_files findings without a format change.

Spec §2 (CLI output) + §4 (drift integration).
"""

from __future__ import annotations

import json
from dataclasses import asdict

from gh_manage.findings import Finding, Severity

_SEVERITY_ORDER: tuple[Severity, ...] = ("critical", "high", "medium", "low")


def _bucket(findings: tuple[Finding, ...]) -> dict[Severity, list[Finding]]:
    buckets: dict[Severity, list[Finding]] = {s: [] for s in _SEVERITY_ORDER}
    for f in findings:
        buckets[f.severity].append(f)
    return buckets


def _counts_line(findings: tuple[Finding, ...]) -> str:
    counts = {s: 0 for s in _SEVERITY_ORDER}
    for f in findings:
        counts[f.severity] += 1
    return ", ".join(f"{counts[s]} {s}" for s in _SEVERITY_ORDER)


def format_stdout(findings: tuple[Finding, ...], *, repo: str) -> str:
    """Human-readable output for the doctor CLI."""
    lines: list[str] = [f"{repo} — {_counts_line(findings)}"]
    buckets = _bucket(findings)
    for sev in _SEVERITY_ORDER:
        sev_findings = buckets[sev]
        if not sev_findings:
            continue
        lines.append("")
        lines.append(f"## {sev}")
        for f in sev_findings:
            lines.append("")
            lines.append(f"### {f.check}")
            lines.append(f.field_path)
            lines.append(f"Current:  {f.current_value}")
            lines.append(f"Desired:  {f.desired_value}")
            lines.append(f.message)
            if f.remediation:
                lines.append(f"→ {f.remediation}")
    return "\n".join(lines)


def format_json(findings: tuple[Finding, ...], *, repo: str) -> str:
    """Machine-readable output. Schema matches drift's JSON v1."""
    payload = {
        "schema_version": 1,
        "repo": repo,
        "findings": [asdict(f) for f in findings],
    }
    return json.dumps(payload, indent=2, default=str, sort_keys=True)


def format_markdown(findings: tuple[Finding, ...], *, repo: str) -> str:
    """Markdown for drift-scanner issue bodies. Matches
    drift_sync.format_markdown_report heading style (## <severity>,
    ### <check>)."""
    if not findings:
        return f"# {repo}\n\nNo findings.\n"
    lines: list[str] = [f"# {repo}", "", _counts_line(findings), ""]
    buckets = _bucket(findings)
    for sev in _SEVERITY_ORDER:
        sev_findings = buckets[sev]
        if not sev_findings:
            continue
        lines.append(f"## {sev}")
        lines.append("")
        for f in sev_findings:
            lines.append(f"### {f.check}")
            lines.append("")
            lines.append(f"- **Field**: `{f.field_path}`")
            lines.append(f"- **Current**: `{f.current_value}`")
            lines.append(f"- **Desired**: `{f.desired_value}`")
            lines.append(f"- {f.message}")
            if f.remediation:
                lines.append(f"- **Fix**: {f.remediation}")
            lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

```
uv run pytest tests/unit/doctor/test_report.py -v
```

Expected: all four tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/doctor/report.py tests/unit/doctor/test_report.py
git commit -m "feat(doctor): add stdout/json/markdown report formatters"
```

---

## Task 8: `git_cli.py` stderr capture

**Files:**
- Modify: `src/gh_manage/git_cli.py:111-156`
- Test: `tests/unit/test_git_cli.py` (create or extend)

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_git_cli.py` if it doesn't exist:

```python
"""GitError must carry stderr context (Theme A — load-bearing for
doctor's actionable error messages)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


def test_git_error_preserves_stderr():
    from gh_manage.git_cli import GitError, _run_git

    fake = subprocess.CompletedProcess(
        args=["git", "rev-parse", "HEAD"],
        returncode=128,
        stdout="",
        stderr="fatal: not a git repository\n",
    )

    with patch("subprocess.run", return_value=fake):
        try:
            _run_git(["rev-parse", "HEAD"], cwd=Path("/tmp"))
        except GitError as e:
            assert "not a git repository" in str(e)
            return
    pytest.fail("Expected GitError with stderr context")
```

- [ ] **Step 2: Run test to confirm fail**

```
uv run pytest tests/unit/test_git_cli.py -v
```

Expected: test may already pass depending on existing implementation. If it fails, proceed to Step 3; if it passes, mark Step 3 a no-op and verify existing behaviour meets the spec.

- [ ] **Step 3: Ensure `GitError` includes stderr**

Open `src/gh_manage/git_cli.py`. Read the current `_raise_classified_git_error` and `_run_git` implementations (lines 111-180). The change: every `GitError` raise path must include the original `stderr` content in the exception message.

If `_run_git` currently does:

```python
if result.returncode != 0:
    _raise_classified_git_error(stderr=result.stderr, returncode=result.returncode)
```

and `_raise_classified_git_error` constructs messages with `stderr`, check that the final `raise GitError(...)` path also includes `stderr.strip()` in the message. If it wraps it but `raise GitError(str(e))` is used anywhere without `stderr`, fix that raise site.

Concrete change pattern (apply wherever `GitError(...)` is raised from a subprocess path):

```python
raise GitError(
    f"git {' '.join(args)} failed (exit {returncode}): "
    f"{stderr.strip() or '(no stderr)'}"
)
```

- [ ] **Step 4: Run test to confirm pass**

```
uv run pytest tests/unit/test_git_cli.py -v
```

Expected: pass.

- [ ] **Step 5: Run full suite**

```
uv run pytest -q
```

Expected: all tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/gh_manage/git_cli.py tests/unit/test_git_cli.py
git commit -m "fix(git-cli): include stderr context in GitError messages

Theme A hygiene (#47). Doctor relies on git errors surfacing actual
git output instead of a bare 'git command failed'."
```

---

## Task 9: CLI `gh-manage doctor` command

**Files:**
- Create: `src/gh_manage/commands/doctor.py`
- Modify: `src/gh_manage/doctor/__init__.py` (add `run_on_path`/`run_on_remote`)
- Modify: `src/gh_manage/commands/_shared.py` (add `DoctorError` to `_DOMAIN_ERRORS`)
- Modify: `src/gh_manage/cli.py` (register command)
- Test: `tests/unit/commands/test_doctor_cli.py`

- [ ] **Step 1: Add `run_on_path` / `run_on_remote` to `doctor/__init__.py`**

Append to `src/gh_manage/doctor/__init__.py`:

```python
from pathlib import Path

import yaml as _yaml

from gh_manage import git_cli
from gh_manage.commands._shared import (
    resolve_branch_protection_path,
    resolve_profile_path,
    resolve_repos_path,
)
from gh_manage.config import load_config
from gh_manage.github_api import protection as protection_api
from gh_manage.github_client import GhError, run_gh_api
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.profiles import ProfileSpec


def _load_profile(profile_name: str) -> ProfileSpec:
    return load_config(resolve_profile_path(profile_name), ProfileSpec)


def _read_local_ci_yml(path: Path) -> str:
    ci = path / ".github" / "workflows" / "ci.yml"
    try:
        return ci.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _fetch_remote_ci_yml(repo: str) -> str:
    """Return ci.yml contents for owner/repo, or '' if the file is
    absent. GitHub 404 is the missing-file signal; other errors
    propagate."""
    from gh_manage.github_client import GhNotFoundError

    try:
        raw = run_gh_api(
            ["repos", repo, "contents", ".github/workflows/ci.yml"],
            stdin_input=None,
        )
    except GhNotFoundError:
        return ""
    payload = _yaml.safe_load(raw)
    import base64

    content_b64 = payload["content"]
    return base64.b64decode(content_b64).decode("utf-8")


def _resolve_profile_required_contexts(profile: ProfileSpec) -> tuple[str, ...]:
    return tuple(profile.required_contexts or ())


def _resolve_live_required_contexts(repo: str, default_branch: str) -> tuple[str, ...]:
    try:
        payload = protection_api.get_branch_protection(repo, default_branch)
    except GhError:
        return ()
    contexts = (
        payload.get("required_status_checks", {}).get("contexts") or []
    )
    return tuple(contexts)


def _infer_profile_for_repo(repo: str) -> str:
    """Look up repo in bundled repos.yml. Raise DoctorError if absent."""
    from gh_manage.models.repos import ReposConfig

    config = load_config(resolve_repos_path(), ReposConfig)
    for entry in config.repos:
        if entry.name == repo:
            return entry.profile
    raise DoctorError(
        f"Cannot infer profile: {repo!r} is not in bundled repos.yml. "
        f"Pass --profile explicitly."
    )


def run_on_path(
    path: Path, profile_name: str | None = None
) -> "tuple[Finding, ...]":
    """Run every registered doctor check against a local repo path."""
    from gh_manage.findings import Finding  # re-export
    _ = Finding  # silence linters

    path = path.resolve()
    repo = git_cli.get_origin_owner_repo(path)
    profile_name = profile_name or _infer_profile_for_repo(repo)
    profile = _load_profile(profile_name)
    ci_yml_text = _read_local_ci_yml(path)
    live_ctx = _resolve_live_required_contexts(repo, "main")
    ctx = CheckContext(
        repo=repo,
        ci_yml_text=ci_yml_text,
        profile_name=profile_name,
        required_contexts=live_ctx,
        profile_required_contexts=_resolve_profile_required_contexts(profile),
        source_hint=str(path),
    )
    return run_checks(ctx)


def run_on_remote(
    repo: str, profile_name: str | None = None
) -> "tuple[Finding, ...]":
    """Run every registered doctor check against a remote owner/repo."""
    profile_name = profile_name or _infer_profile_for_repo(repo)
    profile = _load_profile(profile_name)
    ci_yml_text = _fetch_remote_ci_yml(repo)
    live_ctx = _resolve_live_required_contexts(repo, "main")
    ctx = CheckContext(
        repo=repo,
        ci_yml_text=ci_yml_text,
        profile_name=profile_name,
        required_contexts=live_ctx,
        profile_required_contexts=_resolve_profile_required_contexts(profile),
        source_hint=f"remote:{repo}",
    )
    return run_checks(ctx)
```

Add `run_on_path` and `run_on_remote` to `__all__`.

If `ReposConfig` doesn't exist, inspect `src/gh_manage/models/repos.py` and adapt the iteration pattern to the actual field layout. The plan's adapter is intentionally permissive; an implementer may need to adjust `entry.name`/`entry.profile` attribute names to match.

- [ ] **Step 2: Add `DoctorError` to `_DOMAIN_ERRORS`**

In `src/gh_manage/commands/_shared.py`, line 33-40, add the import and extend the tuple:

```python
from gh_manage.doctor.errors import DoctorError

_DOMAIN_ERRORS = (
    GhError,
    ConfigError,
    GitError,
    ProfileError,
    ProtectionError,
    DriftError,
    DoctorError,
)
```

- [ ] **Step 3: Write failing CLI test**

Create `tests/unit/commands/test_doctor_cli.py`:

```python
"""CLI integration for `gh-manage doctor` (spec §2)."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from gh_manage.cli import main


def test_doctor_cli_registered_on_main_group():
    result = CliRunner().invoke(main, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "doctor" in result.output.lower()


def test_doctor_cli_exit_1_on_critical_finding():
    from gh_manage.findings import Finding

    fake = (
        Finding(
            severity="critical",
            check="shape/job-shape-coherence",
            repo="yakkuro/example",
            field_path="x",
            current_value="a",
            desired_value="b",
            message="m",
        ),
    )
    with patch("gh_manage.doctor.run_on_remote", return_value=fake):
        result = CliRunner().invoke(
            main, ["doctor", "yakkuro/example", "--profile", "python-service"]
        )
    assert result.exit_code == 1
    assert "critical" in result.output.lower()


def test_doctor_cli_exit_0_on_no_findings():
    with patch("gh_manage.doctor.run_on_remote", return_value=()):
        result = CliRunner().invoke(
            main, ["doctor", "yakkuro/example", "--profile", "python-service"]
        )
    assert result.exit_code == 0


def test_doctor_cli_exit_zero_flag_overrides_critical():
    from gh_manage.findings import Finding

    fake = (
        Finding(
            severity="critical",
            check="shape/job-shape-coherence",
            repo="yakkuro/example",
            field_path="x",
            current_value="a",
            desired_value="b",
            message="m",
        ),
    )
    with patch("gh_manage.doctor.run_on_remote", return_value=fake):
        result = CliRunner().invoke(
            main,
            [
                "doctor",
                "yakkuro/example",
                "--profile",
                "python-service",
                "--exit-zero",
            ],
        )
    assert result.exit_code == 0


def test_doctor_cli_json_report_mode_emits_valid_payload():
    import json

    with patch("gh_manage.doctor.run_on_remote", return_value=()):
        result = CliRunner().invoke(
            main,
            [
                "doctor",
                "yakkuro/example",
                "--profile",
                "python-service",
                "--report-mode",
                "json",
            ],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["repo"] == "yakkuro/example"
    assert data["findings"] == []
```

- [ ] **Step 4: Run test to confirm fail**

```
uv run pytest tests/unit/commands/test_doctor_cli.py -v
```

Expected: failures / `command doctor not found`.

- [ ] **Step 5: Create `src/gh_manage/commands/doctor.py`**

```python
"""`gh-manage doctor` — consumer-shape guardrail CLI (spec §2)."""

from __future__ import annotations

from pathlib import Path

import click

from gh_manage import doctor
from gh_manage.commands._shared import handle_errors
from gh_manage.doctor import report as doctor_report
from gh_manage.findings import Finding, Severity

_REPORT_MODES = ("stdout", "json", "markdown-file")
_BLOCKING_SEVERITIES: tuple[Severity, ...] = ("critical", "high")


def _looks_like_owner_repo(target: str) -> bool:
    # Accept "owner/repo" only if it's not a local path.
    if "/" not in target:
        return False
    if target.startswith((".", "/")):
        return False
    if Path(target).exists():
        return False
    return True


def _filter_severity(
    findings: tuple[Finding, ...], min_severity: Severity | None
) -> tuple[Finding, ...]:
    if min_severity is None:
        return findings
    order = ("low", "medium", "high", "critical")
    threshold = order.index(min_severity)
    return tuple(f for f in findings if order.index(f.severity) >= threshold)


@click.command(
    "doctor",
    help="Check a repo's ci.yml / branch protection shape against a profile.",
)
@click.argument("target", type=str)
@click.option("--profile", "profile_name", default=None)
@click.option("--check", "check_names", multiple=True)
@click.option(
    "--severity",
    type=click.Choice(["critical", "high", "medium", "low"]),
    default=None,
)
@click.option(
    "--report-mode",
    type=click.Choice(_REPORT_MODES),
    default="stdout",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
)
@click.option("--exit-zero", is_flag=True)
@handle_errors
def doctor_cmd(
    target: str,
    profile_name: str | None,
    check_names: tuple[str, ...],
    severity: Severity | None,
    report_mode: str,
    output: Path | None,
    exit_zero: bool,
) -> None:
    if _looks_like_owner_repo(target):
        findings = doctor.run_on_remote(target, profile_name)
        repo = target
    else:
        path = Path(target).resolve()
        findings = doctor.run_on_path(path, profile_name)
        repo = _derive_repo_label(path, fallback=str(path))

    if check_names:
        findings = tuple(f for f in findings if f.check in set(check_names))

    findings = _filter_severity(findings, severity)

    if report_mode == "stdout":
        click.echo(doctor_report.format_stdout(findings, repo=repo))
    elif report_mode == "json":
        click.echo(doctor_report.format_json(findings, repo=repo))
    elif report_mode == "markdown-file":
        if output is None:
            raise click.UsageError("--output is required with --report-mode markdown-file")
        output.write_text(
            doctor_report.format_markdown(findings, repo=repo),
            encoding="utf-8",
        )

    if exit_zero:
        return

    if any(f.severity in _BLOCKING_SEVERITIES for f in findings):
        raise SystemExit(1)


def _derive_repo_label(path: Path, *, fallback: str) -> str:
    from gh_manage import git_cli

    try:
        return git_cli.get_origin_owner_repo(path)
    except Exception:
        return fallback


# alias for cli.py registration symmetry with other commands
doctor = doctor_cmd
```

Note: the module-level name `doctor` conflicts with the `gh_manage.doctor` package import. Rename the local alias to `doctor_command` or keep the function as `doctor_cmd` and register that in `cli.py` (preferred).

**Revised last two lines:**

```python
# (delete the `doctor = doctor_cmd` alias — ambiguous with the package import above)
```

- [ ] **Step 6: Wire into `src/gh_manage/cli.py`**

Modify `src/gh_manage/cli.py`:

```python
from gh_manage.commands import (
    apply as apply_cmd,
    doctor as doctor_cmd,
    drift as drift_cmd,
    init as init_cmd,
    issues as issues_cmd,
    labels as labels_cmd,
    protection as protection_cmd,
)
```

And after other `add_command` lines:

```python
main.add_command(doctor_cmd.doctor_cmd)
```

- [ ] **Step 7: Run tests**

```
uv run pytest tests/unit/commands/test_doctor_cli.py -v
```

Expected: all five tests pass.

- [ ] **Step 8: Manual smoke**

```
uv run gh-manage doctor --help
uv run gh-manage doctor . --profile python-service
```

Expected: help text renders; `.` invocation returns 0 (gh-manage itself is compliant).

- [ ] **Step 9: Commit**

```bash
git add src/gh_manage/commands/doctor.py src/gh_manage/commands/_shared.py src/gh_manage/cli.py src/gh_manage/doctor/__init__.py tests/unit/commands/test_doctor_cli.py
git commit -m "feat(cli): add \`gh-manage doctor\` command

Wires run_on_path / run_on_remote into a Click subcommand with
stdout/json/markdown-file output modes. Exit 1 on critical/high
findings unless --exit-zero is passed. Spec §2."
```

---

## Task 10: `init` — post-apply doctor + rollback

**Files:**
- Modify: `src/gh_manage/commands/init.py:175-192` (Apply section)
- Modify: `src/gh_manage/profile_sync.py` (if `apply_files_diff` needs PathState return)
- Test: `tests/unit/commands/test_init.py` (add test cases)

- [ ] **Step 1: Read current `apply_files_diff` contract**

```
uv run python -c "import inspect, gh_manage.profile_sync as p; print(inspect.getsource(p.apply_files_diff))"
```

Expected output: a function that copies files from templates to target. Note its current return type and whether it tracks which paths it created vs overwrote.

- [ ] **Step 2: Write failing test for init rollback on critical finding**

Append to `tests/unit/commands/test_init.py` (create if missing):

```python
"""init post-apply doctor + rollback (spec §5.B)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner


def test_init_rolls_back_created_files_on_doctor_critical(tmp_path: Path):
    """When post-apply doctor surfaces a critical finding, init must
    remove any file it just created, then exit non-zero."""
    from gh_manage.cli import main
    from gh_manage.findings import Finding

    # Arrange: make the target look like a git repo with an origin
    repo_dir = tmp_path / "target"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    # minimal .git/config with origin URL
    (repo_dir / ".git" / "config").write_text(
        "[remote \"origin\"]\n"
        "\turl = https://github.com/yakkuro/example.git\n"
    )

    fake_critical = (
        Finding(
            severity="critical",
            check="shape/job-shape-coherence",
            repo="yakkuro/example",
            field_path="x",
            current_value="a",
            desired_value="b",
            message="m",
        ),
    )

    with (
        patch("gh_manage.commands.init._profile_files_noop_diff", return_value=[repo_dir / ".github" / "workflows" / "ci.yml"]),
        patch("gh_manage.doctor.run_on_path", return_value=fake_critical),
    ):
        result = CliRunner().invoke(
            main,
            ["init", str(repo_dir), "--profile", "python-service", "--apply"],
        )

    assert result.exit_code != 0
    assert "critical" in result.output.lower() or "abort" in result.output.lower()
    assert not (repo_dir / ".github" / "workflows" / "ci.yml").exists(), (
        "Rollback should have removed the file init created."
    )
```

(This test relies on a patched seam — `_profile_files_noop_diff` — that Step 3 adds. It represents the "files that init created" list. The test is illustrative; the real patching strategy must match what `profile_sync.apply_files_diff` actually returns.)

**Simpler test when the machinery is too deep to unit-test cleanly:** use a subprocess integration test in `tests/integration/test_init_rollback.py` that runs `gh-manage init` against a real tmp-path fixture with a stubbed profile that ships a deliberately broken ci.yml template, and asserts the resulting file system is clean. The unit test above is a best-effort; if mocking proves brittle, promote it to the integration test.

- [ ] **Step 3: Add rollback logic to `commands/init.py`**

Locate the `# Apply` block (around line 175) in `src/gh_manage/commands/init.py`. Replace the `profile_sync.apply_files_diff(...)` call with:

```python
click.echo("")
created_paths: list[Path] = profile_sync.apply_files_diff(
    files_diff, target, templates_root, force=force, progress=click.echo
)
```

If `apply_files_diff` does not already return `list[Path]`, extend it to track paths it created — this is a single-point change: before each `Path.write_text` call, record the path and whether the file existed before (for backup). Return the recorded list.

After labels and protection are applied, insert the doctor gate:

```python
# Post-apply doctor gate (spec §5.B). Critical findings trigger
# rollback: remove files init created (best-effort), surface the
# doctor findings as the exception message.
from gh_manage import doctor as _doctor

findings = _doctor.run_on_path(target, profile_name=profile_name)
critical = [f for f in findings if f.severity == "critical"]
if critical:
    click.echo("\ninit post-check found critical findings:", err=True)
    click.echo(
        _doctor.report.format_stdout(tuple(critical), repo=owner_repo),
        err=True,
    )
    # Rollback
    for p in reversed(created_paths):
        try:
            if p.is_file():
                p.unlink()
        except OSError as roll_err:
            click.echo(
                f"WARNING: rollback failed for {p}: {roll_err}", err=True
            )
    raise click.ClickException(
        "init aborted due to critical doctor findings; rolled back files. "
        "See spec docs/specs/2026-04-17-doctor-guardrail-design.md §5."
    )
```

`profile_sync.apply_files_diff` return type update:

```python
# src/gh_manage/profile_sync.py
def apply_files_diff(
    diff: ProfileFilesDiff,
    target: Path,
    templates_root: Path,
    *,
    force: bool,
    progress: Callable[[str], None] = lambda _msg: None,
) -> list[Path]:
    """Return list of paths created or overwritten by this call.

    Spec §5.B rollback contract: the returned list is what init's
    rollback will `unlink`. Overwrote entries are not currently
    restored — a follow-up (#47 hygiene) can add tempdir-backed
    restoration once profile_sync grows the capacity.
    """
    created: list[Path] = []
    ...  # existing logic
    return created
```

Overwrote-file restoration is explicitly deferred per spec §5.B "best-effort" language. Current init usage is on fresh repos (no pre-existing ci.yml), so the `OVERWROTE` path is rare in practice.

- [ ] **Step 4: Run tests**

```
uv run pytest tests/unit/commands/test_init.py -v
```

Expected: pass. If the unit test mocking is too deep, convert to an integration test and mark the unit test skipped with reason.

- [ ] **Step 5: Run full suite**

```
uv run pytest -q
```

Expected: no regression.

- [ ] **Step 6: Commit**

```bash
git add src/gh_manage/commands/init.py src/gh_manage/profile_sync.py tests/unit/commands/test_init.py
git commit -m "feat(init): run doctor post-apply; rollback on critical

Closes the loop introduced by the v1.1.0 rollout misconfigs: new
repos initialised via gh-manage are now guaranteed to produce a
shape doctor considers valid. Spec §5."
```

---

## Task 11: `apply` — post-apply doctor warnings (stderr)

**Files:**
- Modify: `src/gh_manage/commands/apply.py`
- Test: `tests/unit/commands/test_apply.py` (add case)

- [ ] **Step 1: Add test for stderr warning path**

Append to `tests/unit/commands/test_apply.py`:

```python
def test_apply_prints_doctor_warnings_to_stderr(tmp_path):
    """apply must not block on critical doctor findings — emit warnings
    to stderr only. Spec §5 enforcement scope."""
    from click.testing import CliRunner
    from unittest.mock import patch

    from gh_manage.cli import main
    from gh_manage.findings import Finding

    fake = (
        Finding(
            severity="critical",
            check="shape/job-shape-coherence",
            repo="yakkuro/example",
            field_path="x",
            current_value="a",
            desired_value="b",
            message="m",
        ),
    )
    # Use mix_stderr=False so click captures stdout/stderr separately.
    runner = CliRunner(mix_stderr=False)

    with patch("gh_manage.doctor.run_on_path", return_value=fake):
        # Stub the real apply side effects so the test stays unit-level.
        with patch("gh_manage.commands.apply._apply_impl", return_value=None):
            result = runner.invoke(
                main,
                ["apply", str(tmp_path), "--profile", "python-service", "--apply"],
            )

    assert result.exit_code == 0, result.output
    assert "critical" in (result.stderr or "").lower()
    assert "critical" not in result.stdout.lower()
```

- [ ] **Step 2: Run test to confirm fail**

```
uv run pytest tests/unit/commands/test_apply.py -v
```

Expected: failure because `_apply_impl` and the doctor wire-up don't exist yet.

- [ ] **Step 3: Modify `commands/apply.py`**

Wrap the existing apply body in a `_apply_impl` function (the test stubs it). After `_apply_impl` returns, run doctor and emit warnings:

```python
# src/gh_manage/commands/apply.py (near the end of apply())
_apply_impl(...)  # existing side effects

from gh_manage import doctor as _doctor

findings = _doctor.run_on_path(target, profile_name=profile_name)
blocking = [f for f in findings if f.severity in ("critical", "high")]
if blocking:
    click.echo(
        "WARNING: post-apply doctor surfaced blocking-severity findings:",
        err=True,
    )
    click.echo(
        _doctor.report.format_stdout(tuple(blocking), repo=owner_repo),
        err=True,
    )
    click.echo(
        "Not failing apply — these findings existed pre-apply. "
        "Run `gh-manage doctor` to review, or fix and re-run.",
        err=True,
    )
```

Keep the function exiting with 0.

- [ ] **Step 4: Run test to confirm pass**

```
uv run pytest tests/unit/commands/test_apply.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/commands/apply.py tests/unit/commands/test_apply.py
git commit -m "feat(apply): emit doctor warnings to stderr after apply

apply never blocks: critical/high findings go to stderr for
visibility, apply still exits 0. Reserves space for a future
--strict flag (#48). Spec §5."
```

---

## Task 12: Bundled template comment

**Files:**
- Modify: `src/gh_manage/data/templates/ci/python-ci.yml`

- [ ] **Step 1: Read current template**

```
cat src/gh_manage/data/templates/ci/python-ci.yml
```

- [ ] **Step 2: Prepend required-shape comment**

Open `src/gh_manage/data/templates/ci/python-ci.yml` and insert before the `jobs:` block (keeping existing `name:`, `on:`, `permissions:` intact):

```yaml
# REQUIRED — DO NOT modify the two fields below without also updating branch protection.
#
# GitHub Actions generates a status context of the form
#   "<job.name OR job_id> / <job-step-name-from-reusable-workflow>"
# The bundled branch-protection policy requires the literal context
# "PR Gate / PR Gate", so both `pr-gate` as the job id AND `name: "PR Gate"`
# as the display label must stay as-is.
#
# See yakkuro/gh-manage#46 for the incident where this invariant was broken
# across three repos and caused admin-merges during the v1.1.0 rollout.
jobs:
  pr-gate:
    name: "PR Gate"
    ...
```

Do not alter the job body below `name: "PR Gate"`.

- [ ] **Step 3: Sanity check the template parses**

```
uv run python -c "import yaml; print(list(yaml.safe_load(open('src/gh_manage/data/templates/ci/python-ci.yml'))['jobs'].keys()))"
```

Expected: `['pr-gate']`.

- [ ] **Step 4: Commit**

```bash
git add src/gh_manage/data/templates/ci/python-ci.yml
git commit -m "docs(template): explain why jobs.pr-gate + name are load-bearing"
```

---

## Task 13: Bundled-template shape test

**Files:**
- Create: `tests/unit/data/__init__.py` (if missing)
- Create: `tests/unit/data/test_template_shapes.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/data/test_template_shapes.py`:

```python
"""Bundled ci-template shape test (spec §5.A).

If a bundled template is edited to produce a shape doctor considers
critical, CI fails before the template ships.
"""

from __future__ import annotations

from importlib.resources import files


def test_python_ci_template_passes_job_shape_coherence():
    from gh_manage.doctor.checks import check_job_shape_coherence
    from gh_manage.doctor.context import CheckContext

    tmpl_text = (
        files("gh_manage.data") / "templates" / "ci" / "python-ci.yml"
    ).read_text(encoding="utf-8")

    ctx = CheckContext(
        repo="yakkuro/example-consumer",
        ci_yml_text=tmpl_text,
        profile_name="python-service",
        required_contexts=("PR Gate / PR Gate",),
        source_hint="bundled:python-ci.yml",
    )
    assert check_job_shape_coherence(ctx) == ()


def test_python_ci_template_passes_reusable_adoption():
    from gh_manage.doctor.checks import check_reusable_adoption
    from gh_manage.doctor.context import CheckContext

    tmpl_text = (
        files("gh_manage.data") / "templates" / "ci" / "python-ci.yml"
    ).read_text(encoding="utf-8")

    ctx = CheckContext(
        repo="yakkuro/example-consumer",
        ci_yml_text=tmpl_text,
        profile_name="python-service",
        required_contexts=("PR Gate / PR Gate",),
        source_hint="bundled:python-ci.yml",
    )
    assert check_reusable_adoption(ctx) == ()
```

- [ ] **Step 2: Run test**

```
uv run pytest tests/unit/data/test_template_shapes.py -v
```

Expected: both tests pass. If they fail, the template comment insertion in Task 12 broke something — re-parse and fix.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/data/test_template_shapes.py tests/unit/data/__init__.py
git commit -m "test(data): bundled ci template must pass doctor checks"
```

---

## Task 14: Drift bridge

**Files:**
- Create: `src/gh_manage/doctor/bridge.py`
- Modify: `src/gh_manage/drift_sync.py` (import bridge for side-effect)
- Test: `tests/unit/test_doctor_bridge.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_doctor_bridge.py`:

```python
"""Drift bridge: one drift-registered check that delegates to doctor
and converts DoctorCheckError to a shape/check-error finding.

Spec §4."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_drift_bridge_delegates_to_doctor_run_checks():
    from gh_manage.doctor.bridge import check_shape  # registered
    from gh_manage.drift_sync import ScanContext
    from gh_manage.findings import Finding

    # Craft a minimal ScanContext-shaped stub.
    # The bridge's from_scan_context adapter is the seam.
    fake_finding = Finding(
        severity="medium",
        check="shape/job-shape-coherence",
        repo="yakkuro/example",
        field_path="x",
        current_value=None,
        desired_value=None,
        message="m",
    )

    class _FakeCtx:
        repo = "yakkuro/example"
        path = Path("/tmp/nonexistent")
        default_branch = "main"
        profile = None
        labels_config = None
        bp_config = None

    with (
        patch("gh_manage.doctor.bridge._build_check_context", return_value=object()),
        patch("gh_manage.doctor.run_checks", return_value=(fake_finding,)),
    ):
        findings = check_shape(_FakeCtx())  # type: ignore[arg-type]

    assert len(findings) == 1
    assert findings[0].check == "shape/job-shape-coherence"


def test_drift_bridge_converts_doctor_check_error_to_finding():
    from gh_manage.doctor.bridge import check_shape
    from gh_manage.doctor.errors import DoctorCheckError

    class _FakeCtx:
        repo = "yakkuro/example"
        path = Path("/tmp/nonexistent")
        default_branch = "main"
        profile = None
        labels_config = None
        bp_config = None

    with (
        patch("gh_manage.doctor.bridge._build_check_context", return_value=object()),
        patch(
            "gh_manage.doctor.run_checks",
            side_effect=DoctorCheckError("ci.yml malformed"),
        ),
    ):
        findings = check_shape(_FakeCtx())  # type: ignore[arg-type]

    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert findings[0].check == "shape/check-error"
    assert "malformed" in findings[0].message
```

- [ ] **Step 2: Run test to confirm fail**

```
uv run pytest tests/unit/test_doctor_bridge.py -v
```

Expected: `ModuleNotFoundError: gh_manage.doctor.bridge`.

- [ ] **Step 3: Create `src/gh_manage/doctor/bridge.py`**

```python
"""Bridge drift scanner <-> doctor.

drift_sync's register_check wants `(ScanContext) -> tuple[Finding, ...]`.
doctor's run_checks wants `CheckContext`. This bridge is the adapter.

Error semantics (spec §4):
- DoctorCheckError from doctor is caught and converted into a single
  medium-severity `shape/check-error` finding. This keeps a
  per-repo scan failure from aborting a multi-repo drift scan.
- Any other exception propagates — it's a bug, and drift's caller
  already has a clear-traceback mode.
"""

from __future__ import annotations

from gh_manage import doctor
from gh_manage.doctor.context import CheckContext
from gh_manage.doctor.errors import DoctorCheckError
from gh_manage.drift_sync import ScanContext, register_check as register_drift_check
from gh_manage.findings import Finding


def _build_check_context(ctx: ScanContext) -> CheckContext:
    """Adapter from ScanContext to CheckContext.

    Reads ci.yml from ctx.path/.github/workflows/ci.yml; reads live
    required contexts from the ScanContext's protection payload if
    available, else empty tuple.
    """
    ci_path = ctx.path / ".github" / "workflows" / "ci.yml"
    try:
        ci_text = ci_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        ci_text = ""

    # bp_config is the BUNDLED config; live required_contexts come from
    # the API. For the bridge's purposes we build a best-effort snapshot
    # using the existing drift_sync protection check (which already
    # consulted the live payload). Drift's own ctx does not currently
    # expose the live required-contexts directly — fall back to reading
    # from a follow-up protection adapter.
    #
    # TEMPORARY: this bridge passes empty required_contexts; doctor's
    # shape/job-shape-coherence effectively becomes a "no required
    # contexts known" check that never fires. A follow-up in the same
    # release extends ScanContext with `live_required_contexts` to
    # close the loop. Tracked as a sub-task of #47.
    return CheckContext(
        repo=ctx.repo,
        ci_yml_text=ci_text,
        profile_name=ctx.profile.name if ctx.profile else "unknown",
        required_contexts=(),
        profile_required_contexts=tuple(
            ctx.profile.required_contexts or ()
        ) if ctx.profile else (),
        source_hint=f"scan:{ctx.repo}",
    )


@register_drift_check
def check_shape(ctx: ScanContext) -> tuple[Finding, ...]:
    """Single drift check that delegates to all registered doctor
    shape/* checks."""
    try:
        doctor_ctx = _build_check_context(ctx)
        return doctor.run_checks(doctor_ctx)
    except DoctorCheckError as e:
        return (
            Finding(
                severity="medium",
                check="shape/check-error",
                repo=ctx.repo,
                field_path="doctor:bridge",
                current_value=None,
                desired_value=None,
                message=f"doctor check failed: {e}",
                remediation="Re-run `gh-manage doctor <repo>` for detail.",
            ),
        )
```

**Note on the temporary no-live-contexts behaviour**: the bridge falls back to `required_contexts=()`. This means drift's shape check initially surfaces only `shape/reusable-adoption` and `shape/required-contexts-match` (which uses the profile field, not the live field). `shape/job-shape-coherence` needs the live field to fire. Extending `ScanContext` with `live_required_contexts` is a follow-up sub-task within this spec — add it as Task 14.5 below.

Actually — **do the extension here in Task 14**. Move the follow-up inline:

Modify `src/gh_manage/drift_sync.py::ScanContext`:

```python
@dataclass(frozen=True)
class ScanContext:
    path: Path
    repo: str
    default_branch: str
    profile: ProfileSpec
    labels_config: LabelsConfig
    bp_config: BranchProtectionConfig | None
    live_required_contexts: tuple[str, ...] = ()
```

Populate `live_required_contexts` in the CLI's drift command when building `ScanContext` (lookup `protection_api.get_branch_protection(repo, default_branch)["required_status_checks"]["contexts"]`). Pass through to the bridge.

Then the bridge `_build_check_context` becomes:

```python
    return CheckContext(
        ...
        required_contexts=ctx.live_required_contexts,
        ...
    )
```

- [ ] **Step 4: Wire bridge import in `drift_sync.py`**

At the bottom of `src/gh_manage/drift_sync.py` (after all existing `@register_check` functions):

```python
# Side-effect import: doctor.bridge.check_shape is registered
# with drift's registry on module load. Spec §4.
from gh_manage.doctor import bridge as _doctor_bridge  # noqa: F401, E402
```

- [ ] **Step 5: Run test**

```
uv run pytest tests/unit/test_doctor_bridge.py -v
```

Expected: both tests pass.

- [ ] **Step 6: Run full suite**

```
uv run pytest -q
```

Expected: green. The `ScanContext` extension is backward-compatible (default empty tuple).

- [ ] **Step 7: Commit**

```bash
git add src/gh_manage/doctor/bridge.py src/gh_manage/drift_sync.py tests/unit/test_doctor_bridge.py
git commit -m "feat(drift): register shape check delegating to doctor

Spec §4. DoctorCheckError becomes a medium shape/check-error
finding so one malformed repo does not abort a --all scan."
```

---

## Task 15: Context-adapter regression test

**Files:**
- Create: `tests/unit/test_context_adapter.py`

- [ ] **Step 1: Write test**

Create `tests/unit/test_context_adapter.py`:

```python
"""Regression: ensure drift_sync.ScanContext supplies every field that
doctor.CheckContext requires (spec §4 convergent finding)."""

from __future__ import annotations

from dataclasses import fields


def test_scan_context_covers_check_context_required_fields():
    from gh_manage.doctor.context import CheckContext
    from gh_manage.drift_sync import ScanContext

    scan_fields = {f.name for f in fields(ScanContext)}

    # The subset of CheckContext fields that the bridge must supply
    # derives them from a ScanContext. The others come from local
    # filesystem reads in the bridge.
    bridge_supplied = {
        "repo",           # ScanContext.repo
        "profile_name",   # ScanContext.profile.name
        "required_contexts",         # ScanContext.live_required_contexts
        "profile_required_contexts", # ScanContext.profile.required_contexts
    }

    # Exhaustive invariant: each bridge_supplied mapping must resolve
    # to *some* ScanContext attribute path. If ScanContext changes in a
    # way that breaks the mapping, this test fails loudly.
    path_map = {
        "repo": ["repo"],
        "profile_name": ["profile"],
        "required_contexts": ["live_required_contexts"],
        "profile_required_contexts": ["profile"],
    }
    for dest, scan_parts in path_map.items():
        assert scan_parts[0] in scan_fields, (
            f"Doctor bridge expects ScanContext.{scan_parts[0]} "
            f"(for CheckContext.{dest}); missing. If you renamed the "
            f"field, update doctor/bridge.py::_build_check_context too."
        )
```

- [ ] **Step 2: Run test**

```
uv run pytest tests/unit/test_context_adapter.py -v
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_context_adapter.py
git commit -m "test: pin ScanContext ↔ CheckContext field contract

Guards against silent breakage if ScanContext fields are renamed
without updating doctor/bridge.py. Spec §4 convergent finding."
```

---

## Task 16: Broken-consumer fixtures + snapshot regression

**Files:**
- Create: `tests/fixtures/broken_consumers/tg_commander/{ci.yml,protection.json,expected_findings.json}`
- Create: same three files for `repo_init/` and `deep_research/`
- Create: `tests/unit/doctor/test_broken_consumer_fixtures.py`

- [ ] **Step 1: Create fixture files**

```
mkdir -p tests/fixtures/broken_consumers/tg_commander
mkdir -p tests/fixtures/broken_consumers/repo_init
mkdir -p tests/fixtures/broken_consumers/deep_research
```

**`tests/fixtures/broken_consumers/tg_commander/ci.yml`:**

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  test:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
    with:
      python-version: "3.12"
      gh-manage-ref: v1.1.0
      install-command: "uv sync --group dev"
      type-check: false
```

**`tests/fixtures/broken_consumers/tg_commander/protection.json`:**

```json
{
  "required_status_checks": {
    "contexts": ["PR Gate / PR Gate"]
  },
  "required_pull_request_reviews": {
    "required_approving_review_count": 0
  }
}
```

**`tests/fixtures/broken_consumers/tg_commander/expected_findings.json`:**

```json
{
  "findings": [
    {
      "severity": "critical",
      "check": "shape/job-shape-coherence",
      "field_path": ".github/workflows/ci.yml:jobs.test",
      "current_value": "test / PR Gate",
      "desired_value": ["PR Gate / PR Gate"]
    }
  ]
}
```

**`tests/fixtures/broken_consumers/repo_init/ci.yml`:**

```yaml
name: CI

on:
  pull_request:
    branches: [main]

jobs:
  call-pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
    with:
      python-version: "3.12"
      gh-manage-ref: v1.1.0
      install-command: "uv sync"
      test-command: "uv run pytest"
      lint: true
      type-check: false
```

**`tests/fixtures/broken_consumers/repo_init/protection.json`** and **`expected_findings.json`**: same pattern, with `current_value: "call-pr-gate / PR Gate"`.

**`tests/fixtures/broken_consumers/deep_research/ci.yml`:**

```yaml
name: CI

on:
  pull_request:
    branches: [main]

jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
    with:
      python-version: "3.12"
      gh-manage-ref: "v1.1.0"
      install-command: "uv sync --extra bench --extra dev"
      test-command: "uv run pytest tests/ -q"
      setup-command: "uv run mypy packages/"
```

`deep_research/expected_findings.json`: `current_value: "pr-gate / PR Gate"` (job id is correct but missing `name:`).

- [ ] **Step 2: Write snapshot regression test**

Create `tests/unit/doctor/test_broken_consumer_fixtures.py`:

```python
"""Snapshot regression: doctor must identify each of today's three
admin-merged consumers (#46) as shape/job-shape-coherence critical.

Prevents silent regressions where doctor returns green for a case it
was specifically designed to catch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "broken_consumers"


@pytest.mark.parametrize(
    "fixture_dir,expected_current",
    [
        ("tg_commander", "test / PR Gate"),
        ("repo_init", "call-pr-gate / PR Gate"),
        ("deep_research", "pr-gate / PR Gate"),
    ],
)
def test_fixture_produces_expected_job_shape_finding(
    fixture_dir: str, expected_current: str
):
    from gh_manage.doctor.checks import check_job_shape_coherence
    from gh_manage.doctor.context import CheckContext

    ci_text = (_FIXTURES / fixture_dir / "ci.yml").read_text(encoding="utf-8")
    protection = json.loads(
        (_FIXTURES / fixture_dir / "protection.json").read_text(encoding="utf-8")
    )
    required = tuple(
        protection["required_status_checks"]["contexts"]
    )

    ctx = CheckContext(
        repo=f"yakkuro/{fixture_dir}",
        ci_yml_text=ci_text,
        profile_name="python-service",
        required_contexts=required,
        source_hint=f"fixture:{fixture_dir}",
    )
    findings = check_job_shape_coherence(ctx)
    criticals = [f for f in findings if f.severity == "critical"]

    assert len(criticals) == 1, (
        f"Expected exactly one shape/job-shape-coherence critical for "
        f"{fixture_dir}, got {len(criticals)}: {findings}"
    )
    assert criticals[0].current_value == expected_current
```

- [ ] **Step 3: Run test**

```
uv run pytest tests/unit/doctor/test_broken_consumer_fixtures.py -v
```

Expected: all three parametrised cases pass.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/broken_consumers/ tests/unit/doctor/test_broken_consumer_fixtures.py
git commit -m "test(doctor): snapshot regression for #46 broken consumers

tg-commander (jobs.test), repo-init (jobs.call-pr-gate), and
deep-research (jobs.pr-gate, no name:) are frozen as fixtures and
asserted to produce exactly the shape/job-shape-coherence critical
finding. If doctor ever misses one of these, the test fails."
```

---

## Task 17: `doctor-smoke.yml` workflow

**Files:**
- Create: `.github/workflows/doctor-smoke.yml`

- [ ] **Step 1: Write workflow**

Create `.github/workflows/doctor-smoke.yml`:

```yaml
name: Doctor Smoke

on:
  pull_request:
    paths:
      - 'src/gh_manage/doctor/**'
      - 'src/gh_manage/findings.py'
      - 'src/gh_manage/data/templates/ci/**'
      - '.github/workflows/doctor-smoke.yml'
  push:
    branches: [main]
    paths:
      - 'src/gh_manage/doctor/**'
      - 'src/gh_manage/findings.py'
      - 'src/gh_manage/data/templates/ci/**'
      - '.github/workflows/doctor-smoke.yml'
  workflow_dispatch:

permissions:
  contents: read

jobs:
  self-dogfood:
    name: doctor-smoke / gh-manage self (expect clean)
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python and uv
        uses: ./actions/setup-python-uv
        with:
          python-version: "3.12"

      - name: Install
        shell: bash
        run: |
          set -euo pipefail
          uv sync --all-extras

      - name: Run doctor on this checkout
        shell: bash
        run: |
          set -euo pipefail
          uv run gh-manage doctor . --profile python-service --report-mode stdout
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/doctor-smoke.yml
git commit -m "ci: add doctor-smoke workflow for gh-manage self-dogfood"
```

---

## Task 18: Version bump to `cli/v1.2.0`

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/gh_manage/__init__.py`
- Modify: `tests/test_sanity.py`
- Modify: `uv.lock` (regenerated)

**Timing note:** per `docs/release-checklist.md`, the version bump is a dedicated `chore/bump-cli-v1.2.0` PR opened AFTER the feature PR merges. The tasks below are part of that chore PR, not the feature PR. List them here so the implementation flow is complete.

- [ ] **Step 1: Bump `pyproject.toml`**

```
sed -i 's/^version = "1\.1\.0"$/version = "1.2.0"/' pyproject.toml
```

Verify: `grep '^version' pyproject.toml` → `version = "1.2.0"`.

- [ ] **Step 2: Bump `__init__.py`**

```
sed -i 's/^__version__ = "1\.1\.0"$/__version__ = "1.2.0"/' src/gh_manage/__init__.py
```

- [ ] **Step 3: Bump `tests/test_sanity.py`**

Replace the assertion target (current: `"1.1.0"`) with `"1.2.0"`.

- [ ] **Step 4: Regenerate `uv.lock`**

```
uv sync
```

- [ ] **Step 5: Run full suite**

```
uv run pytest -q
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/gh_manage/__init__.py tests/test_sanity.py uv.lock
git commit -m "chore: bump cli version to 1.2.0"
```

- [ ] **Step 7: Follow `docs/release-checklist.md`**

After the chore PR merges, tag, release, and smoke-install per the checklist. See `docs/release-checklist.md` for the full sequence.

---

## Self-review

**Spec coverage (checked against spec sections):**

- §1 Architecture — Task 1 (findings), Task 2 (doctor scaffold), Task 3 (registry), Task 14 (bridge). All covered.
- §2 CLI surface — Task 9 (doctor CLI + profile inference + exit code contract + missing-file behaviour). Covered.
- §3 α checks — Task 4 (job-shape-coherence), Task 5 (reusable-adoption), Task 6 (required-contexts-match). Covered.
- §4 Drift integration — Task 14 (bridge + ScanContext extension + error propagation). Task 15 (context-adapter test — convergent finding). Covered.
- §5 init hardening — Task 10 (post-apply doctor + rollback), Task 11 (apply warnings to stderr), Task 12 (template comment), Task 13 (bundled template shape test). Covered.
- §6 Testing — Task 4-6 unit tests, Task 15 adapter test, Task 16 fixture regression, Task 17 smoke workflow. Version bump per §6 release plan → Task 18. Covered.

**Load-bearing A items bundled:** Task 8 (git_cli stderr capture) — the only A-theme item called out in the spec. Done.

**Placeholder scan:** search for "TBD", "TODO", "implement later". Only mentions are internal (e.g., referencing future tasks in #47). No plan-level placeholders.

**Type consistency:** `Finding` / `Severity` / `CheckContext` signatures consistent across tasks. `run_on_path` / `run_on_remote` defined in Task 9 (not Task 2) — called out explicitly in Task 2's `__init__.py` note.

**Non-goals verified:** no tasks for the 3 broken-consumer migrations (#46), auto-fix, drift cron health (#47/#50), protection-sync split, or `apply --strict`. All documented in spec §Non-goals.
