# drift_sync.py Split Design

- **Date**: 2026-04-18
- **Size**: Medium
- **Sizing Rationale**: Pure internal refactor (no behavior change), but touches a 784-line file with 6 colocated concerns, creates 7 new files, rewires imports in 3 caller modules, and must preserve a non-trivial backward-compat contract (module-attribute mocks in tests). Not Small because the scope is broad (every concern in drift_sync.py) and there are correctness risks around import ordering + test mock paths. Not Large because there's no new design — just moving existing functions to new files.
- **Target**: `yakkuro/gh-manage`
- **Goal**: Convert `src/gh_manage/drift_sync.py` (784 lines) into `src/gh_manage/drift_sync/` package with 7 submodules, one concern per file. Preserve all public and test-visible APIs so zero test mock paths need updating. This closes Theme A item 4 from [#47](https://github.com/yakkuro/gh-manage/issues/47) and unblocks #47 item 6 (structured logging, which needs clean module boundaries).

## Background

`drift_sync.py` was created in Phase 8 (cli/v0.4.0) as a single-file engine for drift detection. Over Phases 8 → 8.5 → 9 → 10 it accumulated 6 concerns in one file:

| Lines | Concern | Functions / Classes |
|---|---|---|
| ~40-88 | Data model — `ScanContext` | `@dataclass ScanContext` |
| ~89-99 | Error hierarchy | `DriftError`, `DriftOutputError` |
| ~101-148 | Check registry | `register_check`, `run_all_checks`, `_filter_by_severity` |
| ~150-287 | Diff → Finding adapters | `_labels_diff_to_findings`, `_protection_diff_to_findings` |
| ~289-443 | Drift checks | `check_labels`, `check_protection`, `check_profile_files` + private helpers |
| ~446-685 | Report formatters | `_group_by_severity`, `_count_by_severity`, `format_stdout_report`, `format_json_report`, `format_markdown_report`, `format_issue_body`, `format_issue_comment` |
| ~688-784 | Issue state machine | `parse_zero_findings_timestamps`, `should_close_issue`, `resolve_drift_issue` |

[#47](https://github.com/yakkuro/gh-manage/issues/47) Theme A item 4 flagged this as:
> split `drift_sync.py` (795 lines) — Finding / ScanContext / registry / 3 checks / 4 formatters in one file; registry "just add a function" promise oversold (needs 4-5 file edits)

`findings.py` (`Finding` + `Severity`) was already extracted in cli/v1.2.0 (PR #53). This spec handles the rest.

## Goals

1. Decompose `drift_sync.py` into 7 single-concern files inside a `drift_sync/` package.
2. Preserve backward compatibility for all external callers AND test mock paths — **no test file changes required**. Existing tests must pass without modification.
3. Make the "just add a new check" promise real: adding a new `@register_check`-decorated function should require editing only one file (`drift_sync/checks.py`), not 4-5.
4. Keep the refactor atomic at commit boundaries — each commit leaves the codebase fully green (pytest + ruff + mypy).

## Non-goals

- **Public API changes**. Every public symbol that was importable from `gh_manage.drift_sync` before is still importable after.
- **Test mock path changes**. Tests currently patch `gh_manage.drift_sync.labels_api.list_labels`, `...protection_api.get_branch_protection`, `...issues_api.*`. After this PR those paths still work (backward-compat re-exports in `__init__.py`).
- **Logic changes**. No behavior change to any check, formatter, or issue-state function. Code moves, it does not mutate.
- **`doctor/` registry changes**. `doctor/registry.py` (parallel to drift_sync's registry) is intentionally left alone — its design uses drift_sync as the reference but is independently maintained.
- **`findings.py` further split**. Already extracted; untouched.
- **`protection_sync.py` split** (#47 item 5). Tracked separately.
- **Structured logging** (#47 item 6). This split is the prerequisite; logging is a separate spec after v1.7.0 ships.
- **Module renames**. Package is named `drift_sync/` to match the existing `drift_sync.py` — no rebrand.

## §1 — Target architecture

Before:
```
src/gh_manage/
├── drift_sync.py        # 784 lines, 6 concerns
├── findings.py          # Finding + Severity (already extracted)
└── ...
```

After:
```
src/gh_manage/
├── drift_sync/
│   ├── __init__.py      # re-exports (backward-compat)
│   ├── context.py       # ~50 LOC — ScanContext + DriftError + DriftOutputError
│   ├── registry.py      # ~50 LOC — CheckFn + register_check + run_all_checks + _filter_by_severity
│   ├── adapters.py      # ~140 LOC — _labels_diff_to_findings + _protection_diff_to_findings
│   ├── checks.py        # ~150 LOC — 3 checks + helpers (_read_template_content, _content_hash)
│   ├── formatters.py    # ~240 LOC — 5 format_* fns + _group_by_severity + _count_by_severity
│   └── issue_state.py   # ~100 LOC — parse_zero_findings_timestamps + should_close_issue + resolve_drift_issue
├── findings.py          # unchanged
└── ...
```

Each submodule has a single concern. No circular imports (the dependency DAG is: context ← registry ← adapters ← checks ← formatters ← issue_state, with context as the root).

### Submodule responsibilities

| File | Owns | Depends on |
|---|---|---|
| `context.py` | `ScanContext` frozen dataclass + `DriftError`/`DriftOutputError` | nothing inside drift_sync/ |
| `registry.py` | `CheckFn` type alias, `register_check` decorator, `_CHECKS` list, `run_all_checks`, `_filter_by_severity` | `context` (for ScanContext + Finding re-export), `findings` |
| `adapters.py` | Pure functions mapping labels_sync / protection_sync diffs to `Finding` tuples | `findings` |
| `checks.py` | `check_labels`, `check_protection`, `check_profile_files` + `_read_template_content` + `_content_hash`. All decorated with `@register_check`. | `context`, `registry` (decorator), `adapters`, `findings`, `gh_manage.github_api.*`, profile/labels/protection sync modules |
| `formatters.py` | Pure functions rendering tuples of Findings as stdout/json/markdown/issue-body/issue-comment strings | `findings` only |
| `issue_state.py` | Issue lifecycle: find existing → create / update / close based on timestamps | `formatters` (for issue body/comment), `findings`, `gh_manage.github_api.issues` |

## §2 — Backward compatibility contract

`__init__.py` re-exports **every** symbol that external code currently accesses via `gh_manage.drift_sync.*`. Concretely:

### Module-attribute re-exports (for test mocks)

```python
# src/gh_manage/drift_sync/__init__.py

# Module bindings — tests patch gh_manage.drift_sync.{name}.{fn} and
# the patches flow to every caller inside the package because the
# bound objects ARE the same module objects.
from gh_manage.github_api import issues as issues_api
from gh_manage.github_api import labels as labels_api
from gh_manage.github_api import protection as protection_api
```

Test mocks observed in the current suite:
```
gh_manage.drift_sync.issues_api.add_issue_comment
gh_manage.drift_sync.issues_api.close_issue
gh_manage.drift_sync.issues_api.create_issue
gh_manage.drift_sync.issues_api.ensure_drift_label
gh_manage.drift_sync.issues_api.get_issue_comments
gh_manage.drift_sync.issues_api.search_drift_issue
gh_manage.drift_sync.issues_api.update_issue_body
gh_manage.drift_sync.labels_api.list_labels
gh_manage.drift_sync.protection_api.get_branch_protection
```

All 9 paths resolve to the same module objects as `gh_manage.github_api.{issues,labels,protection}`, so `unittest.mock.patch` affects every caller inside the package.

### Public symbol re-exports

```python
# Data model + errors
from gh_manage.drift_sync.context import (
    ScanContext,
    DriftError,
    DriftOutputError,
)
# Finding / Severity come from findings.py (not drift_sync/).
from gh_manage.findings import Finding, Severity

# Registry API
from gh_manage.drift_sync.registry import (
    CheckFn,
    register_check,
    run_all_checks,
    _filter_by_severity,  # used by commands/drift.py via attribute access with type: ignore
)

# Checks — not typically imported directly, but re-exported for completeness
from gh_manage.drift_sync.checks import (
    check_labels,
    check_protection,
    check_profile_files,
)

# Formatters
from gh_manage.drift_sync.formatters import (
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
```

### External callers — no changes needed

| Caller | Current imports | Works after split? |
|---|---|---|
| `commands/drift.py` | `from gh_manage.drift_sync import DriftError, DriftOutputError, ScanContext` + `drift_sync.X` attribute access | ✅ All re-exported from `__init__.py` |
| `commands/_shared.py` | `from gh_manage.drift_sync import DriftError` | ✅ Re-exported |
| `doctor/bridge.py` | `from gh_manage.drift_sync import ScanContext, register_check` | ✅ Re-exported |
| `doctor/report.py` | References drift_sync in docstring only | ✅ No code change |
| Tests (any file under `tests/`) | Various patch paths + direct imports | ✅ All re-exported; patch paths preserved |

## §3 — Commit sequence

Eight commits, each leaving the codebase green. Each commit is mechanically minimal (file moves + re-export wiring). No logic changes within any commit.

| Commit | Action | Post-commit state |
|---|---|---|
| 1 | `git mv src/gh_manage/drift_sync.py src/gh_manage/drift_sync/__init__.py` | Package exists; all 784 lines in `__init__.py`; tests pass unchanged |
| 2 | Extract `context.py` — move `ScanContext`, `DriftError`, `DriftOutputError`; `__init__.py` re-exports them | 780-ish lines in `__init__.py` + `context.py` (~50 LOC); tests pass |
| 3 | Extract `registry.py` — move `CheckFn`, `register_check`, `run_all_checks`, `_filter_by_severity`, `_CHECKS` | `__init__.py` further reduced; tests pass |
| 4 | Extract `adapters.py` — move `_labels_diff_to_findings`, `_protection_diff_to_findings` | tests pass |
| 5 | Extract `checks.py` — move `check_labels`, `check_protection`, `check_profile_files`, `_read_template_content`, `_content_hash` | tests pass; mocker.patch paths via `drift_sync.labels_api.list_labels` continue to work (re-export chain) |
| 6 | Extract `formatters.py` — move `_group_by_severity`, `_count_by_severity`, all 5 `format_*_report` + issue format fns | tests pass |
| 7 | Extract `issue_state.py` — move `parse_zero_findings_timestamps`, `should_close_issue`, `resolve_drift_issue` | `__init__.py` now only has re-exports + module docstring |
| 8 | Cleanup `__init__.py` — add module docstring, organize re-exports with comments | tests pass; `__init__.py` ~80 LOC of re-exports and comments |

Each commit is small and reviewable in isolation. Revert granularity: if commit N introduces a subtle bug, the downstream commits that depend on its module can be reverted cleanly.

### Commit 1 special handling

Explicit setup sequence (don't rely on `git mv` auto-creating the directory — behavior varies by git version):

```bash
cd src/gh_manage
mkdir drift_sync
git mv drift_sync.py drift_sync/__init__.py
```

Git tracks this as a rename (blame / `git log --follow` trace back to the original file). No content change in this commit. The purpose is purely to reshape the filesystem so later commits can extract submodules.

Verify after Commit 1:
```bash
uv run pytest -q  # all tests pass; the package __init__.py works as drop-in replacement
ls src/gh_manage/drift_sync/  # exactly one file: __init__.py
test ! -f src/gh_manage/drift_sync.py  # original file gone
```

## §4 — Import strategy per submodule

To keep submodules decoupled, each follows this import convention:

```python
# src/gh_manage/drift_sync/<submodule>.py
from __future__ import annotations

# External imports only (typing, stdlib, gh_manage.* OUTSIDE drift_sync/)
from gh_manage.findings import Finding  # from findings.py, not drift_sync

# Same-package siblings via relative imports OR absolute
from gh_manage.drift_sync.context import ScanContext
# Do NOT import from gh_manage.drift_sync (the package __init__) to avoid
# circular imports when __init__.py is being constructed.
```

In particular, **submodules must NEVER import from `gh_manage.drift_sync` directly** — always go to the specific submodule. Only external callers import from the package.

Import discipline enforcement (spec-critique HIGH 3): Commit 8 adds a lightweight test that greps each submodule for forbidden imports:

```python
# tests/unit/drift/test_package_structure.py (added in Commit 8)
def test_submodules_do_not_import_from_package_root() -> None:
    """Each submodule under drift_sync/ must import only from specific
    sibling submodules or from external modules, never from
    `gh_manage.drift_sync` (the package __init__.py). Importing from
    the package root creates a load-order cycle because __init__.py
    itself imports from the submodules.
    """
    from importlib.resources import files

    package_root = files("gh_manage.drift_sync")
    submodules = [
        p
        for p in package_root.iterdir()
        if p.is_file()
        and p.name.endswith(".py")
        and p.name not in ("__init__.py",)
    ]
    assert len(submodules) == 6, (
        f"Expected 6 submodules (context, registry, adapters, checks, "
        f"formatters, issue_state), found {len(submodules)}: "
        f"{sorted(p.name for p in submodules)}"
    )

    offenders = []
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
        "(circular import risk). Offenders:\n" + "\n".join(offenders)
    )
```

This lint-as-test approach (5 lines of grep-style checks) is cheap to run and catches the entire class of circular-import bugs without needing a separate static-analysis tool.

### checks.py module-attribute pattern (load-bearing for test mocks)

`checks.py` needs `labels_api`, `protection_api`, `issues_api` bindings. Two options:

**Option P1 (recommended)**: `checks.py` does `from gh_manage.github_api import labels as labels_api` directly. This keeps `checks.labels_api` as a local name distinct from `drift_sync.labels_api`. Tests patching `drift_sync.labels_api.list_labels` still work because BOTH names refer to the same module object (`gh_manage.github_api.labels`), and patching a function on a module is observed through every reference to that module.

**Option P2**: `checks.py` does `from gh_manage.drift_sync import labels_api`. Creates a dependency from checks.py back onto `drift_sync/__init__.py`, which re-exports labels_api. Works but introduces a package-level import cycle risk.

Chose P1 — simpler, no cycle risk, tests still pass because of Python's module-object identity semantics.

## §5 — Testing strategy

### No test changes required

The correctness bar: `uv run pytest -q` returns the SAME pass count before and after the refactor, with NO test file edits. If any test fails, either:
1. The refactor moved code incorrectly (logic regression) → fix the move.
2. The test was coupled to an internal detail that shifted (e.g., imported a private helper from the old location) → migrate the test's import only, not the assertion. Document the migration.

### Verification steps per commit

After each of the 8 commits:

```bash
uv run pytest -q           # all tests pass
uvx ruff@0.8.0 check src/  # lint clean
uv run mypy src/            # type check clean
```

### Integration verification after commit 8

```bash
# Self-dogfood: drift scan produces byte-identical summary
uv run gh-manage drift . --profile python-service > /tmp/post-split.out
# Compare with pre-split baseline (captured before commit 1):
diff /tmp/pre-split.out /tmp/post-split.out
# Expected: identical (no behavior change)

# Full-fleet scan
uv run gh-manage drift --all  # 22 repos, 0 FAILED
```

### New sanity tests (added in commit 8)

Four tests in a new file `tests/unit/drift/test_package_structure.py`. First two are identity checks; last two are functional/structural guards responding to spec-critique round 1.

```python
# tests/unit/drift/test_package_structure.py (new file)
from __future__ import annotations

import pytest
from pytest_mock import MockerFixture


def test_drift_sync_reexports_are_complete() -> None:
    """Regression guard: every public symbol previously at the
    drift_sync.py top level must still be importable from
    gh_manage.drift_sync (the package __init__.py) after the split.
    """
    from gh_manage import drift_sync

    # Backward-compat module attributes (test mocks depend on these)
    assert hasattr(drift_sync, "labels_api")
    assert hasattr(drift_sync, "protection_api")
    assert hasattr(drift_sync, "issues_api")

    # Public symbols
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

    # Private symbol used by commands/drift.py via attribute access
    assert hasattr(drift_sync, "_filter_by_severity")


def test_mock_path_identity() -> None:
    """Sanity check: drift_sync's module bindings resolve to the actual
    github_api submodules. This is necessary-but-not-sufficient for the
    test-mock contract. See test_mock_patch_reaches_checks for the
    functional verification.
    """
    from gh_manage import drift_sync
    from gh_manage.github_api import issues as issues_api
    from gh_manage.github_api import labels as labels_api
    from gh_manage.github_api import protection as protection_api

    assert drift_sync.labels_api is labels_api
    assert drift_sync.protection_api is protection_api
    assert drift_sync.issues_api is issues_api


def test_mock_patch_reaches_checks(mocker: MockerFixture) -> None:
    """Functional mock guard (spec-critique HIGH 1, convergent):
    patching gh_manage.drift_sync.labels_api.list_labels must affect
    what check_labels sees when run through run_all_checks. If the
    split ever re-binds labels_api in a way that breaks this flow, the
    identity check above would still pass but the real mock contract
    would be broken — this test catches that.
    """
    from gh_manage import drift_sync
    from gh_manage.drift_sync import ScanContext
    from gh_manage.findings import Finding
    from gh_manage.models.branch_protection import BranchProtectionConfig
    from gh_manage.models.labels import LabelsConfig
    from gh_manage.models.profiles import ProfileSpec
    from pathlib import Path

    sentinel = [{"name": "sentinel-label", "color": "ffffff", "description": ""}]
    mock_list = mocker.patch(
        "gh_manage.drift_sync.labels_api.list_labels",
        return_value=sentinel,
    )
    # Minimal stub ctx — check_labels only reads repo + labels_config.
    # Other checks fetch protection / profile files; stub those mocks too
    # so run_all_checks completes without network calls.
    mocker.patch(
        "gh_manage.drift_sync.protection_api.get_branch_protection",
        return_value={},
    )

    # Build a ScanContext with a valid minimal LabelsConfig; labels_config
    # is required by check_labels. Use whatever the bundled labels.yml
    # would produce (empty label set is fine for this test — any findings
    # shape will do; we only care that list_labels was called).
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
    # The mock was consulted at least once during check execution.
    assert mock_list.called, (
        "patching gh_manage.drift_sync.labels_api.list_labels did not reach "
        "check_labels. The split's module-attribute re-exports may be broken."
    )


def test_checks_registration() -> None:
    """Regression guard (spec-critique HIGH 4): the 3 drift checks
    must be registered in the _CHECKS registry after package import.
    If extract Commit 5 introduces a subtle bug (e.g., checks.py not
    imported by __init__.py, so @register_check never runs), this
    test catches it — empty _CHECKS would silently return 0 findings
    on every drift scan.
    """
    from gh_manage.drift_sync.registry import _CHECKS
    from gh_manage.drift_sync.checks import (
        check_labels,
        check_protection,
        check_profile_files,
    )

    check_fns = {fn for fn in _CHECKS}
    assert check_labels in check_fns
    assert check_protection in check_fns
    assert check_profile_files in check_fns
```

The `test_mock_patch_reaches_checks` functional test is the load-bearing regression guard: even if a future refactor breaks the module-object identity relationship (e.g., by re-binding `labels_api` to a wrapper object), this test catches the silent failure.

## §6 — Release plan

- **Tag**: `cli/v1.7.0` — CLI-track minor bump. Pure internal refactor (no behavior change, no public API change), but minor is appropriate because the package layout changed (a fact observable by anyone who reads or extends the module). Patch bump would undersell the change.
- **Release notes**:
  - "Internal refactor: `drift_sync` split into 7 single-concern submodules. No public API change; all existing imports continue to work via package-level re-exports. Unblocks structured logging follow-up (#47 item 6)."
- **Compatibility**: Additive only. Adding a new drift check now only requires editing `drift_sync/checks.py`.

Files bumped:
- `src/gh_manage/__init__.py` — `__version__ = "1.7.0"`
- `pyproject.toml` — `version = "1.7.0"`
- `tests/test_sanity.py` — assertion updated to `1.7.0`
- `uv.lock` — regenerated by `uv sync`

## §7 — Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Circular imports between submodules | Package load fails with ImportError | Strict DAG: context → registry → adapters → checks → formatters → issue_state. Each submodule imports only from earlier submodules + external gh_manage modules, never from `gh_manage.drift_sync` (the __init__.py). |
| Test mocker.patch paths silently break (test passes but no longer actually patches) | Regression undetected | New `test_mock_path_compatibility` asserts `drift_sync.labels_api is gh_manage.github_api.labels` (identity check, not just attribute existence). Mocks rely on this identity. |
| Private name `_filter_by_severity` accessed by `commands/drift.py` via attribute (not imported) | Commands break after split if `__init__.py` doesn't re-export | Explicit `_filter_by_severity` re-export in `__init__.py` even though it's private-by-convention; matches the current coupling. |
| `@register_check` decorator side effect — checks are registered AT IMPORT TIME when `checks.py` is imported | If `__init__.py` fails to import `checks.py` (e.g., typo), `_CHECKS` is empty and `run_all_checks` returns 0 findings silently | `__init__.py` explicitly imports `checks` (even just to register). Verified in Commit 5 with a test that asserts `_CHECKS` contains the 3 expected checks. |
| Commit sequence breaks mid-extract (e.g., commit 3 references something moved in commit 5 that hasn't happened yet) | Intermediate commit fails its own pytest → blocked PR | Each commit is self-contained. Moves happen in dependency order (bottom-up: context first, issue_state last). Running pytest after each commit validates closure. |
| Git rename detection fails on `git mv drift_sync.py drift_sync/__init__.py` | Blame loses history; diff looks like delete + create | Use `git mv` explicitly; set `git log --follow` expectations in release notes for reviewers. `git log --follow src/gh_manage/drift_sync/__init__.py` traces back to the original file. |
| `doctor/bridge.py` uses `register_check` from drift_sync to add a doctor-specific check into the drift `_CHECKS` registry | After split, if `register_check` in the package's __init__ and in `drift_sync/registry.py` don't share the same underlying `_CHECKS` list, the doctor bridge loses its check | `_CHECKS` lives in `registry.py` as a module-level list. `register_check` mutates it. `__init__.py` imports and re-exports `register_check` from `registry.py`. Doctor's check_registration, via `register_check`, mutates the SAME `_CHECKS` list that `run_all_checks` reads. Test: `doctor/bridge.py`'s shape check appears in `run_all_checks` output post-split. |

## §8 — Acceptance Criteria

- [ ] `src/gh_manage/drift_sync.py` no longer exists.
- [ ] `src/gh_manage/drift_sync/` package exists with files: `__init__.py`, `context.py`, `registry.py`, `adapters.py`, `checks.py`, `formatters.py`, `issue_state.py`.
- [ ] Each submodule has the function/class list described in §1.
- [ ] `src/gh_manage/drift_sync/__init__.py` re-exports every public symbol + the 3 `*_api` bindings listed in §2.
- [ ] `uv run pytest -q` returns the same pass count as before (568 — was 567 + 2 new regression-guard tests). All existing tests pass without modification.
- [ ] New tests in `tests/unit/drift/test_package_structure.py` all pass: `test_drift_sync_reexports_are_complete`, `test_mock_path_identity`, `test_mock_patch_reaches_checks` (functional mock guard), `test_checks_registration` (_CHECKS populated), `test_submodules_do_not_import_from_package_root` (import-discipline lint-as-test).
- [ ] `uvx ruff@0.8.0 check + format --check src/ tests/` clean.
- [ ] `uv run mypy src/` clean.
- [ ] Self-dogfood: `uv run gh-manage drift . --profile python-service` produces byte-identical (modulo timestamps) output vs. pre-split baseline.
- [ ] Self-dogfood: `uv run gh-manage drift --all` reports 22 repos scanned, 0 FAILED, with exactly the same finding count as pre-split.
- [ ] `doctor/bridge.py`'s `shape/job-shape-coherence` check still appears in `run_all_checks` output (regression guard: `register_check` wiring across package boundary).
- [ ] Version bumped to `1.7.0` across `__init__.py`, `pyproject.toml`, `test_sanity.py`, `uv.lock`.
- [ ] PR open, 4-reviewer protocol clean, merged, `cli/v1.7.0` tagged + released.

## §9 — Open Questions

None. Design decisions resolved during 2026-04-18 brainstorming:
- Split granularity: 7 files (Option A).
- Commit granularity: 8 atomic commits.
- Release bump: cli/v1.7.0 (minor, internal refactor).
- Test mock paths: preserved via `__init__.py` re-exports; no test edits required.

Spec-critique round 1 findings (5 HIGH, 5 MEDIUM, 2 LOW) addressed:
- **HIGH 1 + 5 (convergent, mock functional verification)**: §5 now includes `test_mock_patch_reaches_checks` — a functional test that actually patches and runs `run_all_checks`, verifying the mock was observed. Identity check alone is insufficient.
- **HIGH 2 (Commit 1 directory preset)**: §3 "Commit 1 special handling" now gives the explicit `mkdir` + `git mv` sequence + post-commit verification.
- **HIGH 3 (import discipline enforcement)**: §4 now includes `test_submodules_do_not_import_from_package_root` — a lint-as-test that greps each submodule for forbidden `from gh_manage.drift_sync import ...` patterns. 5-line test catches the circular-import class of bugs.
- **HIGH 4 (convergent, _CHECKS population + import order)**: §5 now includes `test_checks_registration` that asserts `_CHECKS` contains all 3 checks post-package-load. Catches the "checks.py not imported → empty registry → silent 0 findings" bug.

MEDIUM and LOW items either covered by the above (most MEDIUMs flagged the same underlying issues) or accepted as documented risks.

## References

- Theme A umbrella: [`#47`](https://github.com/yakkuro/gh-manage/issues/47)
- `findings.py` first-step extraction: PR #53 (cli/v1.2.0)
- Downstream dependency (structured logging): [`#47`](https://github.com/yakkuro/gh-manage/issues/47) item 6
- Current file: `src/gh_manage/drift_sync.py` (784 lines at commit `6dfc2d8` on main)
- Test file that drives the mock-path backward-compat constraint: `tests/unit/cli/test_drift.py`
