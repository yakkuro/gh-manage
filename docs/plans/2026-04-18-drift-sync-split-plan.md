# drift_sync.py Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 784-line `src/gh_manage/drift_sync.py` into a `drift_sync/` package with 6 single-concern submodules + `__init__.py`, preserving 100% backward compatibility (public imports, private attribute access, and test mocker.patch paths).

**Architecture:** Bottom-up extraction driven by a strict dependency DAG: `context → registry → adapters → checks → formatters → issue_state`. Each submodule imports only from earlier submodules and from `gh_manage.*` modules OUTSIDE `drift_sync/`, never from the package root. `__init__.py` re-exports every public symbol + 3 module-attribute bindings (`labels_api`, `protection_api`, `issues_api`) so existing test mocks continue to observe the same module objects. Commit granularity is 8 atomic commits; each commit leaves pytest + ruff + mypy green.

**Tech Stack:** Python 3.12, `uv`, `pytest 8`, `pytest-mock`, `click`, `pydantic v2`, `ruff@0.8.0`, `mypy`.

**Spec reference:** `docs/specs/2026-04-18-drift-sync-split-design.md` (approved 2026-04-18 after spec-critique round 1).

**Branch:** `refactor/drift-sync-split` (already exists at 7fc9307; this plan continues on that branch).

---

## Pre-flight

### Task 0: Baseline capture

**Files:**
- Read: `src/gh_manage/drift_sync.py` (full file, 784 lines — orientation only)

- [ ] **Step 1: Confirm branch state**

```bash
cd /home/server160/repos/gh-manage
git status
git log --oneline -3
```

Expected: on `refactor/drift-sync-split`, working tree clean, HEAD = 7fc9307 (spec critique response).

- [ ] **Step 2: Capture pre-refactor pytest pass count**

```bash
uv run pytest -q 2>&1 | tail -5
```

Expected: all tests pass. **Record the exact pass count number** — every subsequent commit must match this count (later tasks add 5 new tests, so the final count = baseline + 5).

- [ ] **Step 3: Capture pre-refactor drift scan output for self-dogfood diff**

```bash
uv run gh-manage drift . --profile python-service --format stdout > /tmp/pre-split.out 2>&1 || true
wc -l /tmp/pre-split.out
```

Expected: file written, non-empty. Leave `/tmp/pre-split.out` in place for Task 9 (integration verification).

- [ ] **Step 4: Capture external-caller import inventory (reference)**

```bash
```

Run (Grep tool):
- pattern `from gh_manage\.drift_sync`, output `content`, glob `**/*.py`
- pattern `gh_manage\.drift_sync\.`, output `content`, glob `**/*.py`

Expected callers: `src/gh_manage/commands/drift.py`, `src/gh_manage/commands/_shared.py`, `src/gh_manage/doctor/bridge.py`, plus test files under `tests/`. No code edits in this step — just verify the inventory matches the spec §2 "External callers" table. If a caller appears that the spec didn't list, **stop** and update the spec before proceeding.

---

## Commit 1: File move (`git mv` only, no content change)

### Task 1: Reshape filesystem into a package

**Files:**
- Move: `src/gh_manage/drift_sync.py` → `src/gh_manage/drift_sync/__init__.py`

- [ ] **Step 1: Create the package directory and move the file**

```bash
cd /home/server160/repos/gh-manage/src/gh_manage
mkdir drift_sync
git mv drift_sync.py drift_sync/__init__.py
cd /home/server160/repos/gh-manage
```

- [ ] **Step 2: Verify filesystem shape**

```bash
ls src/gh_manage/drift_sync/
test ! -f src/gh_manage/drift_sync.py && echo "OK: old file gone"
test -f src/gh_manage/drift_sync/__init__.py && echo "OK: __init__.py exists"
git status
```

Expected: `drift_sync/` contains exactly `__init__.py`; `git status` shows `renamed: src/gh_manage/drift_sync.py -> src/gh_manage/drift_sync/__init__.py` (git detects rename because content is identical).

- [ ] **Step 3: Run pytest — confirm no regressions**

```bash
uv run pytest -q 2>&1 | tail -5
```

Expected: same pass count as Task 0 Step 2. Python's package import lookup finds `__init__.py` and loads it; every existing `from gh_manage.drift_sync import X` and `gh_manage.drift_sync.X` attribute access continues to work unchanged.

- [ ] **Step 4: Run lint + type check**

```bash
uvx ruff@0.8.0 check src/
uvx ruff@0.8.0 format --check src/
uv run mypy src/
```

Expected: all clean. File content didn't change, only location.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor(drift_sync): convert module to package via git mv (1/8)

Move src/gh_manage/drift_sync.py -> src/gh_manage/drift_sync/__init__.py
with no content change. This reshapes the filesystem so subsequent
commits can extract submodules one concern at a time.

Git rename detection traces blame/log back to the original file:
  git log --follow src/gh_manage/drift_sync/__init__.py

All 784 lines remain in __init__.py; tests pass unchanged.

Refs #47 (Theme A item 4).
EOF
)"
```

---

## Commit 2: Extract `context.py`

### Task 2: Move `ScanContext`, `DriftError`, `DriftOutputError`

**Files:**
- Create: `src/gh_manage/drift_sync/context.py`
- Modify: `src/gh_manage/drift_sync/__init__.py` (remove extracted code, add re-export)

- [ ] **Step 1: Read current __init__.py around the three symbols**

```bash
```

Use Read tool on `src/gh_manage/drift_sync/__init__.py` lines 1-100 to confirm exact boundaries of `ScanContext` (frozen dataclass, ~25 lines) and both error classes (~10 lines combined). Note their import dependencies — `ScanContext` depends on `Path`, `BranchProtectionConfig`, `LabelsConfig`, `ProfileSpec`.

- [ ] **Step 2: Create `context.py` with moved content**

Create `src/gh_manage/drift_sync/context.py` with this structure. Replace the `<...>` bodies with the exact code copied from `__init__.py`:

```python
"""Scan context + drift-specific errors.

Lowest layer of the drift_sync package. Depends on NOTHING else inside
drift_sync/ — only on stdlib + sibling models. All other drift_sync
submodules are allowed to import from here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.labels import LabelsConfig
from gh_manage.models.profiles import ProfileSpec


@dataclass(frozen=True)
class ScanContext:
    <copy body from __init__.py verbatim>


class DriftError(Exception):
    <copy body from __init__.py verbatim>


class DriftOutputError(DriftError):
    <copy body from __init__.py verbatim>
```

- [ ] **Step 3: Remove the moved code from `__init__.py` and add re-export**

In `src/gh_manage/drift_sync/__init__.py`:
1. Delete the `@dataclass` `ScanContext` definition, the `DriftError` class, and the `DriftOutputError` class.
2. Delete the now-unused imports that `ScanContext` needed (`from dataclasses import dataclass`, `from pathlib import Path`, model imports) — but ONLY if no other code in `__init__.py` still uses them.
3. Near the top of `__init__.py`, add:

```python
from gh_manage.drift_sync.context import (
    ScanContext,
    DriftError,
    DriftOutputError,
)
```

- [ ] **Step 4: Run verification suite**

```bash
uv run pytest -q 2>&1 | tail -5
uvx ruff@0.8.0 check src/
uvx ruff@0.8.0 format --check src/
uv run mypy src/
```

Expected: all green. Pass count matches Task 0 baseline.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/drift_sync/
git commit -m "$(cat <<'EOF'
refactor(drift_sync): extract context.py (2/8)

Move ScanContext + DriftError + DriftOutputError out of __init__.py
into a new context.py submodule. __init__.py re-exports all three for
backward compatibility.

Refs #47 (Theme A item 4).
EOF
)"
```

---

## Commit 3: Extract `registry.py`

### Task 3: Move `CheckFn`, `register_check`, `_CHECKS`, `run_all_checks`, `_filter_by_severity`

**Files:**
- Create: `src/gh_manage/drift_sync/registry.py`
- Modify: `src/gh_manage/drift_sync/__init__.py`

- [ ] **Step 1: Read current __init__.py around the registry block**

Use Read to locate the `CheckFn` type alias, the `_CHECKS: list[CheckFn] = []` module-level list, the `@register_check` decorator, `run_all_checks`, and `_filter_by_severity`. Confirm they reference `ScanContext` (from context.py) and `Finding` (from `gh_manage.findings`).

- [ ] **Step 2: Create `registry.py`**

```python
"""Check registry + severity filter.

Layer 2 of the drift_sync package. Depends on context (for ScanContext)
and on gh_manage.findings (for Finding/Severity). Does NOT depend on
adapters, checks, formatters, or issue_state.

The module-level _CHECKS list is the single source of truth for which
drift checks run. @register_check mutates _CHECKS at import time; every
submodule that defines a @register_check-decorated function must be
imported by __init__.py for the check to be registered.
"""
from __future__ import annotations

from typing import Callable, Iterable

from gh_manage.drift_sync.context import ScanContext
from gh_manage.findings import Finding, Severity

CheckFn = Callable[[ScanContext], Iterable[Finding]]

_CHECKS: list[CheckFn] = []


def register_check(fn: CheckFn) -> CheckFn:
    <copy body from __init__.py verbatim>


def run_all_checks(ctx: ScanContext) -> list[Finding]:
    <copy body from __init__.py verbatim>


def _filter_by_severity(
    findings: Iterable[Finding], min_severity: Severity
) -> list[Finding]:
    <copy body from __init__.py verbatim>
```

- [ ] **Step 3: Update `__init__.py`**

Remove the extracted definitions. Add:

```python
from gh_manage.drift_sync.registry import (
    CheckFn,
    register_check,
    run_all_checks,
    _filter_by_severity,
    _CHECKS,
)
```

Note: `_filter_by_severity` is re-exported even though it's private — `commands/drift.py` accesses it via `drift_sync._filter_by_severity` attribute with a `# type: ignore`. See spec §7 risks table.

- [ ] **Step 4: Verify**

```bash
uv run pytest -q 2>&1 | tail -5
uvx ruff@0.8.0 check src/
uv run mypy src/
```

Expected: green. At this point `_CHECKS` is still empty (no `@register_check` function has been imported yet) — but that's fine because no existing test triggers `run_all_checks` before `checks.py` is imported from `__init__.py` (which still contains the `check_*` functions at this stage).

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/drift_sync/
git commit -m "$(cat <<'EOF'
refactor(drift_sync): extract registry.py (3/8)

Move CheckFn, register_check, _CHECKS, run_all_checks, and
_filter_by_severity into registry.py. __init__.py re-exports all five
(including the private _filter_by_severity used by commands/drift.py
via attribute access).

Refs #47 (Theme A item 4).
EOF
)"
```

---

## Commit 4: Extract `adapters.py`

### Task 4: Move `_labels_diff_to_findings`, `_protection_diff_to_findings`

**Files:**
- Create: `src/gh_manage/drift_sync/adapters.py`
- Modify: `src/gh_manage/drift_sync/__init__.py`

- [ ] **Step 1: Locate adapter functions in __init__.py**

Use Read to confirm `_labels_diff_to_findings` and `_protection_diff_to_findings`. Note their imports: `Finding`, `Severity`, `LabelsDiff`, and protection-diff types from `gh_manage.labels_sync` / `gh_manage.protection_sync` (or wherever the diff types live).

- [ ] **Step 2: Create `adapters.py`**

```python
"""Diff → Finding adapters.

Pure functions that convert labels_sync / protection_sync diff objects
into Finding tuples. Stateless, no I/O. Layer 3 in the DAG.
"""
from __future__ import annotations

from gh_manage.findings import Finding, Severity
from gh_manage.labels_sync import LabelsDiff


def _labels_diff_to_findings(
    diff: LabelsDiff, repo: str
) -> list[Finding]:
    <copy body from __init__.py verbatim>


def _protection_diff_to_findings(
    diff: <type>, repo: str
) -> list[Finding]:
    <copy body from __init__.py verbatim>
```

Copy the exact parameter types from `__init__.py`; do not guess.

- [ ] **Step 3: Update `__init__.py`**

Remove the two functions. Add:

```python
from gh_manage.drift_sync.adapters import (
    _labels_diff_to_findings,
    _protection_diff_to_findings,
)
```

(These private helpers are re-exported because `checks.py` in Commit 5 will import them via `from gh_manage.drift_sync.adapters import ...`, not via the package root, so technically the re-export in `__init__.py` is defensive — but keep it for discoverability and in case a future test patches the adapter.)

- [ ] **Step 4: Verify**

```bash
uv run pytest -q 2>&1 | tail -5
uvx ruff@0.8.0 check src/
uv run mypy src/
```

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/drift_sync/
git commit -m "$(cat <<'EOF'
refactor(drift_sync): extract adapters.py (4/8)

Move _labels_diff_to_findings and _protection_diff_to_findings into
adapters.py. Pure functions, no I/O, Finding-producing converters.

Refs #47 (Theme A item 4).
EOF
)"
```

---

## Commit 5: Extract `checks.py` (load-bearing for test mocks)

### Task 5: Move the three `@register_check` functions

**Files:**
- Create: `src/gh_manage/drift_sync/checks.py`
- Modify: `src/gh_manage/drift_sync/__init__.py`

- [ ] **Step 1: Identify the check block in __init__.py**

Functions to move: `check_labels` (~18 LOC), `check_protection` (~30 LOC), `check_profile_files` (~75 LOC), plus helpers `_read_template_content` (~18 LOC) and `_content_hash` (~4 LOC). All three public checks are decorated with `@register_check`.

- [ ] **Step 2: Create `checks.py`**

```python
"""Drift checks — ProfileSpec, branch protection, labels.

Each @register_check function is appended to registry._CHECKS at import
time. This module MUST be imported by __init__.py so the registrations
fire before run_all_checks is called.

Module-attribute pattern (load-bearing): labels_api / protection_api /
issues_api are bound here with `as` aliases so that patching
`gh_manage.drift_sync.labels_api.list_labels` (a path that resolves to
the same module object via __init__.py's re-export) observes every
caller inside this file. See spec §4 Option P1.
"""
from __future__ import annotations

import hashlib
from importlib.resources import files
from pathlib import Path

from gh_manage.drift_sync.adapters import (
    _labels_diff_to_findings,
    _protection_diff_to_findings,
)
from gh_manage.drift_sync.context import ScanContext
from gh_manage.drift_sync.registry import register_check
from gh_manage.findings import Finding, Severity
from gh_manage.github_api import issues as issues_api  # noqa: F401 (re-exported via __init__)
from gh_manage.github_api import labels as labels_api
from gh_manage.github_api import protection as protection_api
from gh_manage.labels_sync import compute_diff as _compute_labels_diff


def _read_template_content(<sig>) -> str:
    <copy body from __init__.py verbatim>


def _content_hash(content: str) -> str:
    <copy body from __init__.py verbatim>


@register_check
def check_labels(ctx: ScanContext) -> list[Finding]:
    <copy body from __init__.py verbatim>


@register_check
def check_protection(ctx: ScanContext) -> list[Finding]:
    <copy body from __init__.py verbatim>


@register_check
def check_profile_files(ctx: ScanContext) -> list[Finding]:
    <copy body from __init__.py verbatim>
```

**Critical:** copy `labels_api`, `protection_api`, `issues_api` references EXACTLY as they appeared in `__init__.py`. If the original called `labels_api.list_labels(...)`, keep that — do not collapse to `list_labels(...)`. The module-attribute pattern depends on the `name.fn` spelling.

- [ ] **Step 3: Update `__init__.py`**

Remove the 5 functions. Ensure `__init__.py` still has (or adds) the `from gh_manage.github_api import ... as ..._api` trio at top level (these are the module-attribute bindings that test mocks observe — they must remain in `__init__.py` even after `checks.py` has its own copies, because `gh_manage.drift_sync.labels_api` resolves via `__init__.py`'s namespace).

Also add the re-exports:

```python
# Module-attribute bindings (test mocks depend on this — these names
# resolve to the same module objects as inside checks.py, so
# `mocker.patch("gh_manage.drift_sync.labels_api.list_labels")` flows
# through every caller).
from gh_manage.github_api import issues as issues_api
from gh_manage.github_api import labels as labels_api
from gh_manage.github_api import protection as protection_api

# The checks themselves (importing checks.py also triggers @register_check)
from gh_manage.drift_sync.checks import (
    check_labels,
    check_protection,
    check_profile_files,
    _read_template_content,
    _content_hash,
)
```

The `from gh_manage.drift_sync.checks import ...` line is the trigger that causes `checks.py` to be imported and therefore `@register_check` to fire 3 times. **Without this import, `_CHECKS` remains empty after package load and every drift scan silently returns 0 findings.** This is exactly the regression that Task 11 Step 3's `test_checks_registration` catches.

- [ ] **Step 4: Verify — this is the highest-risk commit**

```bash
uv run pytest -q 2>&1 | tail -5
uvx ruff@0.8.0 check src/
uv run mypy src/
```

If any test in `tests/unit/cli/test_drift.py` fails with "list_labels was not called" or similar, the module-attribute binding broke. Debug by opening a Python REPL:

```bash
uv run python -c "
from gh_manage import drift_sync
from gh_manage.github_api import labels
print('identity:', drift_sync.labels_api is labels)
print('_CHECKS:', len(drift_sync._CHECKS))
"
```

Expected: `identity: True`, `_CHECKS: 3`. If `_CHECKS: 0`, the `from gh_manage.drift_sync.checks import ...` line is missing from `__init__.py` (or placed before the registry import in a way that creates an ordering bug).

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/drift_sync/
git commit -m "$(cat <<'EOF'
refactor(drift_sync): extract checks.py (5/8)

Move check_labels, check_protection, check_profile_files and helpers
_read_template_content, _content_hash into checks.py. Each @register_check
fires when checks.py is imported by __init__.py.

Module-attribute bindings (labels_api, protection_api, issues_api) are
preserved in __init__.py so test mocker.patch paths continue to work
(gh_manage.drift_sync.labels_api.list_labels resolves to the same
module object as inside checks.py, so the patch flows through).

Refs #47 (Theme A item 4).
EOF
)"
```

---

## Commit 6: Extract `formatters.py`

### Task 6: Move all 5 `format_*` functions + 2 severity helpers

**Files:**
- Create: `src/gh_manage/drift_sync/formatters.py`
- Modify: `src/gh_manage/drift_sync/__init__.py`

- [ ] **Step 1: Inventory formatter block**

Functions to move: `_group_by_severity`, `_count_by_severity`, `format_stdout_report`, `format_json_report`, `format_markdown_report`, `format_issue_body`, `format_issue_comment`. All pure (no I/O), depend only on `Finding` + `Severity`.

- [ ] **Step 2: Create `formatters.py`**

```python
"""Report formatters.

Pure rendering: Finding tuples → strings (stdout, JSON, Markdown,
issue body, issue comment). No I/O, no network. Layer 5.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Iterable

from gh_manage.findings import Finding, Severity


def _group_by_severity(<sig>) -> dict[Severity, list[Finding]]:
    <copy verbatim>


def _count_by_severity(<sig>) -> Counter[Severity]:
    <copy verbatim>


def format_stdout_report(<sig>) -> str:
    <copy verbatim>


def format_json_report(<sig>) -> str:
    <copy verbatim>


def format_markdown_report(<sig>) -> str:
    <copy verbatim>


def format_issue_body(<sig>) -> str:
    <copy verbatim>


def format_issue_comment(<sig>) -> str:
    <copy verbatim>
```

- [ ] **Step 3: Update `__init__.py`**

Remove the 7 functions. Add:

```python
from gh_manage.drift_sync.formatters import (
    _group_by_severity,
    _count_by_severity,
    format_stdout_report,
    format_json_report,
    format_markdown_report,
    format_issue_body,
    format_issue_comment,
)
```

- [ ] **Step 4: Verify**

```bash
uv run pytest -q 2>&1 | tail -5
uvx ruff@0.8.0 check src/
uv run mypy src/
```

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/drift_sync/
git commit -m "$(cat <<'EOF'
refactor(drift_sync): extract formatters.py (6/8)

Move 5 format_* functions + _group_by_severity + _count_by_severity
into formatters.py. Pure rendering, no I/O.

Refs #47 (Theme A item 4).
EOF
)"
```

---

## Commit 7: Extract `issue_state.py`

### Task 7: Move `parse_zero_findings_timestamps`, `should_close_issue`, `resolve_drift_issue`

**Files:**
- Create: `src/gh_manage/drift_sync/issue_state.py`
- Modify: `src/gh_manage/drift_sync/__init__.py`

- [ ] **Step 1: Inventory issue-state block**

Functions: `parse_zero_findings_timestamps` (~22 LOC), `should_close_issue` (~20 LOC), `resolve_drift_issue` (~53 LOC). Uses `issues_api` for create/update/close, calls formatters for issue body/comment.

- [ ] **Step 2: Create `issue_state.py`**

```python
"""Drift issue lifecycle.

Resolves a drift scan into a GitHub Issue action: create new,
update existing, or close on repeated zero findings. Top of the DAG.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from gh_manage.drift_sync.context import ScanContext
from gh_manage.drift_sync.formatters import format_issue_body, format_issue_comment
from gh_manage.findings import Finding, Severity
from gh_manage.github_api import issues as issues_api


def parse_zero_findings_timestamps(<sig>):
    <copy verbatim>


def should_close_issue(<sig>) -> bool:
    <copy verbatim>


def resolve_drift_issue(<sig>):
    <copy verbatim>
```

- [ ] **Step 3: Update `__init__.py`**

Remove the 3 functions. Add:

```python
from gh_manage.drift_sync.issue_state import (
    parse_zero_findings_timestamps,
    should_close_issue,
    resolve_drift_issue,
)
```

- [ ] **Step 4: Verify**

```bash
uv run pytest -q 2>&1 | tail -5
uvx ruff@0.8.0 check src/
uv run mypy src/
```

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/drift_sync/
git commit -m "$(cat <<'EOF'
refactor(drift_sync): extract issue_state.py (7/8)

Move parse_zero_findings_timestamps, should_close_issue, and
resolve_drift_issue into issue_state.py. Last submodule extracted;
__init__.py now contains only re-exports + module docstring.

Refs #47 (Theme A item 4).
EOF
)"
```

---

## Commit 8: Cleanup `__init__.py` + new regression tests

### Task 8: Polish `__init__.py`

**Files:**
- Modify: `src/gh_manage/drift_sync/__init__.py`

- [ ] **Step 1: Reorganize `__init__.py` into a clean re-export module**

Replace the entire contents of `src/gh_manage/drift_sync/__init__.py` with:

```python
"""Drift detection engine — package root.

This package was extracted from a single 784-line module in cli/v1.7.0.
External callers import from `gh_manage.drift_sync` (this file); test
mocks reach into `gh_manage.drift_sync.{labels,protection,issues}_api`
and those paths resolve through the bindings below.

Submodule layout:
  context.py     — ScanContext + drift errors (no internal deps)
  registry.py    — _CHECKS + register_check + run_all_checks
  adapters.py    — diff → Finding pure functions
  checks.py      — 3 @register_check drift checks (IMPORTED here so
                   registrations fire)
  formatters.py  — stdout/JSON/Markdown/issue renderers
  issue_state.py — drift issue lifecycle

Dependency DAG:
  context ← registry ← adapters ← checks ← formatters ← issue_state

Submodules MUST NOT import from `gh_manage.drift_sync` (the package
root). See tests/unit/drift/test_package_structure.py for enforcement.
"""
from __future__ import annotations

# Module-attribute bindings — test mocker.patch paths depend on these.
# The bound objects ARE the same module objects that checks.py imports,
# so patching gh_manage.drift_sync.labels_api.list_labels flows through
# to every caller inside the package.
from gh_manage.github_api import issues as issues_api
from gh_manage.github_api import labels as labels_api
from gh_manage.github_api import protection as protection_api

# Finding / Severity re-exported for callers that grab them via drift_sync.
from gh_manage.findings import Finding, Severity

# Context + errors
from gh_manage.drift_sync.context import (
    ScanContext,
    DriftError,
    DriftOutputError,
)

# Registry (including private _filter_by_severity + _CHECKS for commands/drift.py)
from gh_manage.drift_sync.registry import (
    CheckFn,
    register_check,
    run_all_checks,
    _filter_by_severity,
    _CHECKS,
)

# Adapters (private helpers, re-exported for discoverability)
from gh_manage.drift_sync.adapters import (
    _labels_diff_to_findings,
    _protection_diff_to_findings,
)

# Checks — importing this module triggers @register_check side effects.
# KEEP THIS IMPORT even if nothing below references the names directly.
from gh_manage.drift_sync.checks import (
    check_labels,
    check_protection,
    check_profile_files,
    _read_template_content,
    _content_hash,
)

# Formatters
from gh_manage.drift_sync.formatters import (
    _group_by_severity,
    _count_by_severity,
    format_stdout_report,
    format_json_report,
    format_markdown_report,
    format_issue_body,
    format_issue_comment,
)

# Issue state machine
from gh_manage.drift_sync.issue_state import (
    parse_zero_findings_timestamps,
    should_close_issue,
    resolve_drift_issue,
)

__all__ = [
    # Errors + context
    "DriftError",
    "DriftOutputError",
    "ScanContext",
    # Findings (re-export)
    "Finding",
    "Severity",
    # Registry
    "CheckFn",
    "register_check",
    "run_all_checks",
    # Checks
    "check_labels",
    "check_protection",
    "check_profile_files",
    # Formatters
    "format_stdout_report",
    "format_json_report",
    "format_markdown_report",
    "format_issue_body",
    "format_issue_comment",
    # Issue state
    "parse_zero_findings_timestamps",
    "should_close_issue",
    "resolve_drift_issue",
]
```

- [ ] **Step 2: Run verification**

```bash
uv run pytest -q 2>&1 | tail -5
uvx ruff@0.8.0 check src/
uvx ruff@0.8.0 format --check src/
uv run mypy src/
wc -l src/gh_manage/drift_sync/*.py
```

Expected: all green. Line counts roughly: context ≈50, registry ≈50, adapters ≈140, checks ≈150, formatters ≈240, issue_state ≈100, __init__ ≈80.

- [ ] **Step 3: Commit (without the new tests yet — those come in Task 9–11)**

```bash
git add src/gh_manage/drift_sync/
git commit -m "$(cat <<'EOF'
refactor(drift_sync): cleanup __init__.py (8/8)

__init__.py now contains only:
- module docstring describing the package layout + dependency DAG
- module-attribute bindings (labels_api, protection_api, issues_api)
- explicit re-exports grouped by submodule
- __all__ listing public API

drift_sync.py split is complete. Net LOC change: +70 (docstrings,
explicit __all__, import grouping). No behavior change.

Refs #47 (Theme A item 4).
EOF
)"
```

---

## Commit 9: Regression tests for the split

### Task 9: Add the 5 regression-guard tests

**Files:**
- Create: `tests/unit/drift/__init__.py` (if it doesn't exist)
- Create: `tests/unit/drift/test_package_structure.py`

- [ ] **Step 1: Ensure test directory exists**

```bash
mkdir -p tests/unit/drift
[ -f tests/unit/drift/__init__.py ] || touch tests/unit/drift/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/drift/test_package_structure.py` with all 5 tests from spec §5. Full verbatim content:

```python
"""Regression guards for the drift_sync package split (cli/v1.7.0).

Tests that protect the backward-compat contract from silent regressions:
1. reexports_complete — every public symbol still importable
2. mock_path_identity — module-attribute bindings resolve correctly
3. mock_patch_reaches_checks — functional mock flow still works
4. checks_registration — @register_check fired for all 3 checks
5. submodules_do_not_import_from_package_root — DAG discipline
"""
from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest
from pytest_mock import MockerFixture


def test_drift_sync_reexports_are_complete() -> None:
    from gh_manage import drift_sync

    assert hasattr(drift_sync, "labels_api")
    assert hasattr(drift_sync, "protection_api")
    assert hasattr(drift_sync, "issues_api")

    for name in (
        "ScanContext",
        "DriftError",
        "DriftOutputError",
        "Finding",
        "Severity",
        "CheckFn",
        "register_check",
        "run_all_checks",
        "check_labels",
        "check_protection",
        "check_profile_files",
        "format_stdout_report",
        "format_json_report",
        "format_markdown_report",
        "format_issue_body",
        "format_issue_comment",
        "parse_zero_findings_timestamps",
        "should_close_issue",
        "resolve_drift_issue",
    ):
        assert hasattr(drift_sync, name), f"drift_sync missing re-export: {name}"

    assert hasattr(drift_sync, "_filter_by_severity")


def test_mock_path_identity() -> None:
    from gh_manage import drift_sync
    from gh_manage.github_api import issues as issues_api
    from gh_manage.github_api import labels as labels_api
    from gh_manage.github_api import protection as protection_api

    assert drift_sync.labels_api is labels_api
    assert drift_sync.protection_api is protection_api
    assert drift_sync.issues_api is issues_api


def test_mock_patch_reaches_checks(mocker: MockerFixture) -> None:
    from gh_manage import drift_sync
    from gh_manage.drift_sync import ScanContext
    from gh_manage.models.labels import LabelsConfig
    from gh_manage.models.profiles import ProfileSpec

    sentinel = [{"name": "sentinel-label", "color": "ffffff", "description": ""}]
    mock_list = mocker.patch(
        "gh_manage.drift_sync.labels_api.list_labels",
        return_value=sentinel,
    )
    mocker.patch(
        "gh_manage.drift_sync.protection_api.get_branch_protection",
        return_value={},
    )

    labels_config = LabelsConfig(version=1, labels=[])
    ctx = ScanContext(
        path=Path("/tmp"),
        repo="yakkuro/sentinel-repo",
        default_branch="main",
        profile=ProfileSpec(
            version=1,
            name="python-service",
            description="test",
            files=[],
            protection_policy=None,
        ),
        labels_config=labels_config,
        bp_config=None,
    )

    _findings = drift_sync.run_all_checks(ctx)
    assert mock_list.called, (
        "patching gh_manage.drift_sync.labels_api.list_labels did not reach "
        "check_labels. Module-attribute re-exports may be broken."
    )


def test_checks_registration() -> None:
    from gh_manage.drift_sync.checks import (
        check_labels,
        check_profile_files,
        check_protection,
    )
    from gh_manage.drift_sync.registry import _CHECKS

    check_fns = set(_CHECKS)
    assert check_labels in check_fns
    assert check_protection in check_fns
    assert check_profile_files in check_fns


def test_submodules_do_not_import_from_package_root() -> None:
    package_root = files("gh_manage.drift_sync")
    submodules = [
        p
        for p in package_root.iterdir()
        if p.is_file() and p.name.endswith(".py") and p.name != "__init__.py"
    ]
    assert len(submodules) == 6, (
        f"Expected 6 submodules (context, registry, adapters, checks, "
        f"formatters, issue_state), found {len(submodules)}: "
        f"{sorted(p.name for p in submodules)}"
    )

    offenders: list[str] = []
    for sub in submodules:
        text = sub.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("from gh_manage.drift_sync import") or (
                stripped.startswith("from gh_manage.drift_sync ")
                and not stripped.startswith("from gh_manage.drift_sync.")
            ):
                offenders.append(f"{sub.name}:{line_no}: {stripped}")
            if stripped == "import gh_manage.drift_sync":
                offenders.append(f"{sub.name}:{line_no}: {stripped}")
    assert not offenders, (
        "drift_sync submodules must not import from the package root "
        "(circular-import risk). Offenders:\n" + "\n".join(offenders)
    )
```

- [ ] **Step 3: Run the new tests**

```bash
uv run pytest tests/unit/drift/test_package_structure.py -v
```

Expected: all 5 pass. If `test_checks_registration` fails with `_CHECKS` empty, the `from gh_manage.drift_sync.checks import ...` in `__init__.py` is wrong. If `test_submodules_do_not_import_from_package_root` fails with offenders, fix those imports in the flagged submodules to use specific siblings (e.g., `from gh_manage.drift_sync.context import X`).

- [ ] **Step 4: Full test suite**

```bash
uv run pytest -q 2>&1 | tail -5
```

Expected: baseline + 5 tests, all pass.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/drift/
git commit -m "$(cat <<'EOF'
test(drift): add 5 regression guards for package split

- test_drift_sync_reexports_are_complete: every public symbol still importable
- test_mock_path_identity: module-attribute bindings == github_api submodules
- test_mock_patch_reaches_checks: functional mock flow intact (addresses
  spec-critique HIGH 1 — identity check alone is insufficient)
- test_checks_registration: _CHECKS contains all 3 @register_check fns
  (catches the "checks.py not imported → empty registry → 0 findings
  silently" regression)
- test_submodules_do_not_import_from_package_root: lint-as-test preventing
  circular-import via package root

Refs #47 (Theme A item 4), spec-critique round 1.
EOF
)"
```

---

## Integration verification

### Task 10: Self-dogfood against real repo + full fleet

**Files:** None (verification only).

- [ ] **Step 1: Post-split single-repo drift diff**

```bash
uv run gh-manage drift . --profile python-service --format stdout > /tmp/post-split.out 2>&1 || true
diff /tmp/pre-split.out /tmp/post-split.out || true
```

Expected: no diff (or only timestamp differences). If there's a substantive diff (findings added or removed), the refactor introduced a logic regression — **stop and bisect**: `git bisect start; git bisect bad; git bisect good 7fc9307` (the spec commit before any code moves).

- [ ] **Step 2: Full-fleet drift scan**

```bash
uv run gh-manage drift --all 2>&1 | tail -20
```

Expected: 22 repos scanned, 0 FAILED, summary matches pre-split behavior.

- [ ] **Step 3: `doctor/bridge.py` cross-package check still fires**

`doctor/bridge.py` calls `register_check` from the drift_sync package to register its own shape check. Verify that check still shows up:

```bash
uv run python -c "
from gh_manage.doctor import bridge  # triggers bridge's register_check
from gh_manage.drift_sync.registry import _CHECKS
names = [fn.__name__ for fn in _CHECKS]
print(names)
assert any('shape' in n.lower() or 'job' in n.lower() for n in names), \
    f'doctor bridge check missing from _CHECKS: {names}'
print('OK: doctor bridge check registered')
"
```

Expected: OK. If the doctor bridge check is absent, `__init__.py`'s `register_check` re-export is not pointing to the same `registry._CHECKS` list the bridge is mutating — fix by ensuring `register_check` is imported from `gh_manage.drift_sync.registry` (not redefined).

---

## Release: cli/v1.7.0

### Task 11: Version bump

**Files:**
- Modify: `src/gh_manage/__init__.py:3` — `__version__ = "1.6.0"` → `"1.7.0"`
- Modify: `pyproject.toml:3` — `version = "1.6.0"` → `"1.7.0"`
- Modify: `tests/test_sanity.py:11` — assertion to `"1.7.0"`
- Modify: `uv.lock` (regenerated)

- [ ] **Step 1: Bump the three version strings**

```bash
```

Use Edit on each file:
- `src/gh_manage/__init__.py`: change `__version__ = "1.6.0"` to `__version__ = "1.7.0"`
- `pyproject.toml`: change `version = "1.6.0"` to `version = "1.7.0"`
- `tests/test_sanity.py`: change the `== "1.6.0"` assertion to `== "1.7.0"`

- [ ] **Step 2: Regenerate `uv.lock`**

```bash
uv sync
```

- [ ] **Step 3: Verify the bump**

```bash
uv run pytest tests/test_sanity.py -v
uv run pytest -q 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add src/gh_manage/__init__.py pyproject.toml tests/test_sanity.py uv.lock
git commit -m "$(cat <<'EOF'
chore(release): bump to cli/v1.7.0

Internal refactor: drift_sync split into 7 single-concern submodules.
No public API change; all existing imports continue to work via
package-level re-exports. Unblocks #47 item 6 (structured logging).
EOF
)"
```

---

## PR + 4-reviewer + merge + tag

### Task 12: Open PR and run review protocol

**Files:** None (orchestration only).

- [ ] **Step 1: Push branch**

```bash
git push -u origin refactor/drift-sync-split
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --title "refactor(drift_sync): split 784-line module into 7-file package (cli/v1.7.0)" --body "$(cat <<'EOF'
## Summary

- Converts `src/gh_manage/drift_sync.py` (784 lines, 6 concerns) into a `drift_sync/` package with 6 single-concern submodules + re-export-only `__init__.py`.
- Zero behavior change. All public symbols, private attribute access (`_filter_by_severity`), and test mocker.patch paths preserved.
- 8 atomic commits (git mv → 6 extractions → cleanup) + 1 regression-tests commit + 1 version bump.
- Closes Theme A item 4 from #47. Unblocks item 6 (structured logging).

## Split layout

```
src/gh_manage/drift_sync/
├── __init__.py      # re-exports only (~80 LOC)
├── context.py       # ScanContext + errors
├── registry.py      # _CHECKS + register_check + run_all_checks
├── adapters.py      # diff → Finding pure functions
├── checks.py        # 3 @register_check drift checks
├── formatters.py    # 5 format_* renderers
└── issue_state.py   # drift issue lifecycle
```

## Backward-compat verification

5 new regression tests in `tests/unit/drift/test_package_structure.py`:
1. All public symbols still importable from `gh_manage.drift_sync`
2. `drift_sync.labels_api is gh_manage.github_api.labels` (identity)
3. **Functional mock guard** — `mocker.patch("gh_manage.drift_sync.labels_api.list_labels")` actually reaches `check_labels` (addresses spec-critique HIGH 1)
4. `_CHECKS` populated with all 3 drift checks after package load (catches "silent empty registry" bug)
5. Submodules do not import from `gh_manage.drift_sync` (lint-as-test for DAG discipline)

## Test plan

- [x] `uv run pytest -q` — all pass (baseline count + 5 new)
- [x] `uvx ruff@0.8.0 check src/ tests/` — clean
- [x] `uv run mypy src/` — clean
- [x] Self-dogfood: `gh-manage drift . --profile python-service` byte-identical to pre-split (modulo timestamps)
- [x] Full fleet: `gh-manage drift --all` — 22 repos, 0 FAILED
- [x] `doctor/bridge.py`'s `register_check` still mutates the same `_CHECKS` list (cross-package integration confirmed)

Spec: [`docs/specs/2026-04-18-drift-sync-split-design.md`](docs/specs/2026-04-18-drift-sync-split-design.md)
Plan: [`docs/plans/2026-04-18-drift-sync-split-plan.md`](docs/plans/2026-04-18-drift-sync-split-plan.md)

Refs #47.

Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

- [ ] **Step 3: Wait for CI + capture PR number**

```bash
PR_NUM=$(gh pr view --json number -q .number)
echo "PR #$PR_NUM"
gh pr checks "$PR_NUM" --watch
```

Expected: all checks green.

- [ ] **Step 4: Run 4-reviewer protocol in parallel**

Per `workflow-review.md`, dispatch all 4 reviewers in a SINGLE message with 4 Agent tool calls in parallel:

1. Codex (via `bash scripts/codex-review-resilient.sh "..."`)
2. `superpowers:code-reviewer` — pass the plan path `docs/plans/2026-04-18-drift-sync-split-plan.md` + diff
3. `pr-review-toolkit:silent-failure-hunter` — pass the diff
4. `code-reviewer` — pass the diff; model choice depends on diff size (`git diff main..HEAD --stat | tail -1`): ≤500 lines → haiku; 501–2000 → sonnet; >2000 → opus. This refactor is file-move-heavy but net LOC change is small; expect sonnet.

- [ ] **Step 5: Triage findings**

- CRITICAL/HIGH: fix, push, re-review.
- MEDIUM: fix if cheap, otherwise document rationale in PR comment.
- LOW/nit: at judgment.
- SFH async/race findings: trust; SFH type-nits: push back per `feedback_review_triage.md`.

Do NOT merge until all 4 reviewers are complete and CRITICAL/HIGH are resolved.

- [ ] **Step 6: Merge**

```bash
gh pr merge "$PR_NUM" --squash --delete-branch
git checkout main
git pull
```

- [ ] **Step 7: Tag + release**

```bash
git tag -a cli/v1.7.0 -m "cli/v1.7.0 — drift_sync split (internal refactor)"
git push origin cli/v1.7.0
gh release create cli/v1.7.0 --title "cli/v1.7.0 — drift_sync split" --notes "$(cat <<'EOF'
## Highlights

- **Internal refactor**: `src/gh_manage/drift_sync.py` (784 lines) split into a `drift_sync/` package with 6 single-concern submodules + re-export `__init__.py`. See [PR #<NUM>](https://github.com/yakkuro/gh-manage/pull/<NUM>) for details.
- **No public API change**. Every import path that worked before continues to work. Test mocker.patch paths preserved.
- **Closes Theme A item 4** from #47. **Unblocks item 6** (structured logging).

## Two-track versioning reminder

`cli/v1.7.0` is a **CLI-track** tag (Python CLI + bundled data). Reusable workflows continue on the workflow track (current: `v1.1.0`). This release does NOT bump the workflow track because no reusable workflow files changed. See `docs/versioning.md`.

## Compatibility

Additive only. Adding a new drift check now requires editing only `drift_sync/checks.py`, not 4–5 files.
EOF
)"
```

Replace `<NUM>` with the actual PR number before running.

---

## Post-release

### Task 13: Close the umbrella issue item

- [ ] **Step 1: Comment on #47**

```bash
gh issue comment 47 --body "$(cat <<'EOF'
Theme A item 4 (split drift_sync.py) shipped in cli/v1.7.0. Package layout + regression tests documented in PR and `docs/specs/2026-04-18-drift-sync-split-design.md`.

Item 6 (structured logging) is now unblocked — each drift_sync concern lives in its own module so logger names can be module-scoped cleanly.
EOF
)"
```

- [ ] **Step 2: Verify release page**

```bash
gh release view cli/v1.7.0
```

Expected: release exists with notes above, tagged at the merge commit.

---

## Rollback notes

If a production regression surfaces after release:

- Every submodule extraction (Commits 2–7) is independent. Revert any single commit with `git revert <sha>`. The `git mv` in Commit 1 is the only structural change; reverting it back to a single file is mechanical (`git mv src/gh_manage/drift_sync/__init__.py src/gh_manage/drift_sync.py` then `rmdir src/gh_manage/drift_sync`).
- The 5 regression tests will fail-fast if re-exports or the `_CHECKS` population break. Rely on the test suite for regression detection, not manual verification.
- `git log --follow src/gh_manage/drift_sync/__init__.py` traces blame back to the original `drift_sync.py` through all 8 commits.
