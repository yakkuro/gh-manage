# Issue #72 — Self-Referencing Repos Drift Exemption — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the drift scanner reporting forever-MEDIUM `profile_files/.github/workflows/ci.yml` for gh-manage's self-dogfood, while preserving real drift detection for both gh-manage's user-editable files (CLAUDE.md LOW) and external consumer repos.

**Architecture:** Add `self_referencing: bool = False` to `RepoEntry` and `ScanContext`. Mark gh-manage's `repos.yml` entry. In `check_profile_files`, skip per-entry only when `ctx.self_referencing=True` AND the template content references `<ctx.repo>/.github/workflows/`. CLI plumbs the flag from `RepoEntry` (in `--all`) or via a `repos.yml` lookup (single-repo mode).

**Tech Stack:** Python 3.12, pydantic v2, pytest 8 + pytest-mock. No new dependencies.

**Spec**: `docs/specs/2026-04-20-self-referencing-repos-design.md`

---

## File Map

| Path | Op | Purpose |
|---|---|---|
| `src/gh_manage/models/repos.py` | Modify | Add `self_referencing: bool = False` to `RepoEntry` |
| `src/gh_manage/drift_sync/context.py` | Modify | Add `self_referencing: bool = False` to `ScanContext` |
| `src/gh_manage/drift_sync/checks.py` | Modify | Add `_is_self_referencing_template` helper; per-entry skip in `check_profile_files` |
| `src/gh_manage/commands/_shared.py` | Modify | Add `_resolve_self_referencing(owner_repo)` helper |
| `src/gh_manage/commands/drift.py` | Modify | `_scan_single_repo` accepts `self_referencing`; CLI handler resolves it; `_scan_worker` passes `entry.self_referencing` |
| `src/gh_manage/data/repos.yml` | Modify | Mark `yakkuro/gh-manage` with `self_referencing: true` |
| `tests/unit/models/test_repos.py` | Modify | Schema tests for new field |
| `tests/unit/drift/test_drift_sync.py` | Modify | Helper + check_profile_files behavior tests |
| `tests/unit/commands/test_shared_self_referencing.py` | Create | `_resolve_self_referencing` lookup tests |
| `tests/fixtures/drift-scenarios/profile_files/self-referencing-ci.yml` | Create | Scenario fixture: self-ref skip path |

---

## Task 1: RepoEntry schema — add `self_referencing` field

**Files:**
- Modify: `src/gh_manage/models/repos.py:22-29`
- Test: `tests/unit/models/test_repos.py`

- [ ] **Step 1.1: Write the failing tests**

Append to `tests/unit/models/test_repos.py` (after `test_repo_entry_enabled_false`):

```python
def test_repo_entry_self_referencing_defaults_false() -> None:
    e = RepoEntry(name="yakkuro/foo", profile="python-service")
    assert e.self_referencing is False


def test_repo_entry_self_referencing_true() -> None:
    e = RepoEntry(
        name="yakkuro/gh-manage",
        profile="python-service",
        self_referencing=True,
    )
    assert e.self_referencing is True


def test_repo_entry_self_referencing_rejects_non_bool() -> None:
    # Pydantic coerces "true"/"false" strings — make sure that still works
    # for YAML compat, but reject obviously-wrong types.
    with pytest.raises(ValidationError):
        RepoEntry(
            name="yakkuro/foo",
            profile="python-service",
            self_referencing=["yes"],  # type: ignore[arg-type]
        )


def test_bundled_repos_yml_marks_gh_manage_self_referencing() -> None:
    """Regression guard: gh-manage entry must stay marked self_referencing
    so the drift scanner skips its self-hosted ci.yml."""
    repos_path = Path(str(files("gh_manage.data") / "repos.yml"))
    config = load_config(repos_path, ReposConfig)
    by_name = {e.name: e for e in config.repos}
    assert by_name["yakkuro/gh-manage"].self_referencing is True
    # All other repos should remain self_referencing=False (no other
    # self-hosted reusable publishers as of this PR).
    for name, entry in by_name.items():
        if name != "yakkuro/gh-manage":
            assert entry.self_referencing is False, (
                f"Unexpected self_referencing=True on {name}; "
                "only gh-manage should opt in."
            )
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/models/test_repos.py::test_repo_entry_self_referencing_defaults_false tests/unit/models/test_repos.py::test_repo_entry_self_referencing_true tests/unit/models/test_repos.py::test_repo_entry_self_referencing_rejects_non_bool tests/unit/models/test_repos.py::test_bundled_repos_yml_marks_gh_manage_self_referencing -v`

Expected: All four FAIL — first three with `AttributeError`/unknown field; the regression guard with `False is True`.

- [ ] **Step 1.3: Add `self_referencing` field to `RepoEntry`**

Edit `src/gh_manage/models/repos.py:22-29`. After `enabled: bool = True`, add:

```python
class RepoEntry(BaseModel):
    """One repo in repos.yml."""

    model_config = ConfigDict(extra="forbid")

    name: str  # "owner/repo" full form
    profile: str  # bundled profile name
    enabled: bool = True
    self_referencing: bool = False
    """True when this repo publishes the templates it would otherwise be
    drift-checked against (e.g., yakkuro/gh-manage). Causes
    `check_profile_files` to skip per-entry comparisons whose template
    content references `<repo>/.github/workflows/` — the self-hosted form
    that uses `./` paths cannot hash-match the pinned-tag form. See
    docs/specs/2026-04-20-self-referencing-repos-design.md."""
```

- [ ] **Step 1.4: Mark gh-manage in `repos.yml`**

Edit `src/gh_manage/data/repos.yml:3-4`. Change:

```yaml
  - name: yakkuro/gh-manage
    profile: python-service
```

to:

```yaml
  - name: yakkuro/gh-manage
    profile: python-service
    self_referencing: true
```

- [ ] **Step 1.5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/models/test_repos.py -v`

Expected: All tests pass (existing tests + 4 new).

- [ ] **Step 1.6: Commit**

```bash
git add src/gh_manage/models/repos.py src/gh_manage/data/repos.yml tests/unit/models/test_repos.py
git commit -m "feat(repos): add self_referencing flag to RepoEntry (#72)

RepoEntry gains a self_referencing: bool = False field. Mark
yakkuro/gh-manage as self_referencing: true so the drift scanner can
skip the forever-mismatching ci.yml template-hash check (separate task).

Default False preserves behavior for all other repos. Regression test
asserts only gh-manage opts in.

Refs #72."
```

---

## Task 2: ScanContext — add `self_referencing` field

**Files:**
- Modify: `src/gh_manage/drift_sync/context.py:19-48`
- Test: `tests/unit/drift/test_drift_sync.py`

- [ ] **Step 2.1: Write the failing test**

Append to `tests/unit/drift/test_drift_sync.py` (after `test_scan_context_is_frozen`):

```python
def test_scan_context_self_referencing_defaults_false(tmp_path: Path) -> None:
    profile = ProfileSpec(version=1, name="test", files=[])
    labels_config = _make_labels_config()
    ctx = ScanContext(
        path=tmp_path,
        repo="yakkuro/foo",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=None,
    )
    assert ctx.self_referencing is False


def test_scan_context_self_referencing_true(tmp_path: Path) -> None:
    profile = ProfileSpec(version=1, name="test", files=[])
    labels_config = _make_labels_config()
    ctx = ScanContext(
        path=tmp_path,
        repo="yakkuro/gh-manage",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=None,
        self_referencing=True,
    )
    assert ctx.self_referencing is True
```

- [ ] **Step 2.2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/drift/test_drift_sync.py::test_scan_context_self_referencing_defaults_false tests/unit/drift/test_drift_sync.py::test_scan_context_self_referencing_true -v`

Expected: Both FAIL with `TypeError: ScanContext.__init__() got an unexpected keyword argument 'self_referencing'` for the second; the first fails with `AttributeError`.

- [ ] **Step 2.3: Add field to `ScanContext`**

Edit `src/gh_manage/drift_sync/context.py:19-48`. After `live_required_contexts_readable: bool = True`, add:

```python
@dataclass(frozen=True)
class ScanContext:
    """... (existing docstring above unchanged) ...

    - self_referencing: True when the scanning repo is the publisher of
      the templates it would be drift-checked against. When True,
      check_profile_files skips per-entry comparisons whose template
      content references `<repo>/.github/workflows/` (the form a
      self-hosted repo cannot mirror locally). See
      docs/specs/2026-04-20-self-referencing-repos-design.md.
    """

    path: Path
    repo: str
    default_branch: str
    profile: ProfileSpec
    labels_config: LabelsConfig
    bp_config: BranchProtectionConfig | None
    live_required_contexts: tuple[str, ...] = ()
    live_required_contexts_readable: bool = True
    self_referencing: bool = False
```

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/drift/test_drift_sync.py::test_scan_context_self_referencing_defaults_false tests/unit/drift/test_drift_sync.py::test_scan_context_self_referencing_true -v`

Expected: PASS.

- [ ] **Step 2.5: Commit**

```bash
git add src/gh_manage/drift_sync/context.py tests/unit/drift/test_drift_sync.py
git commit -m "feat(drift): add self_referencing to ScanContext (#72)

Frozen-dataclass field with default False. The flag will be consumed by
check_profile_files in the next task to skip self-hosted templates whose
hash will never match the pinned-tag template content.

Refs #72."
```

---

## Task 3: `_is_self_referencing_template` helper + per-entry skip in `check_profile_files`

**Files:**
- Modify: `src/gh_manage/drift_sync/checks.py:120-198`
- Test: `tests/unit/drift/test_drift_sync.py`

- [ ] **Step 3.1: Write the failing tests**

Append to `tests/unit/drift/test_drift_sync.py` (at the end of the file):

```python
# Issue #72: self-referencing template skip


def test_is_self_referencing_template_matches_repo_url() -> None:
    from gh_manage.drift_sync.checks import _is_self_referencing_template

    content = (
        "name: CI\n"
        "jobs:\n"
        "  pr-gate:\n"
        "    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.0.0\n"
    )
    assert _is_self_referencing_template(content, "yakkuro/gh-manage") is True


def test_is_self_referencing_template_no_match_when_repo_differs() -> None:
    from gh_manage.drift_sync.checks import _is_self_referencing_template

    content = (
        "name: CI\n"
        "jobs:\n"
        "  pr-gate:\n"
        "    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.0.0\n"
    )
    # An external repo (yakkuro/foo) is NOT self-referencing for this template.
    assert _is_self_referencing_template(content, "yakkuro/foo") is False


def test_is_self_referencing_template_no_match_for_plain_doc() -> None:
    from gh_manage.drift_sync.checks import _is_self_referencing_template

    content = "# CLAUDE.md\nThis is a docs file with no workflow URLs.\n"
    assert _is_self_referencing_template(content, "yakkuro/gh-manage") is False


def test_check_profile_files_skips_self_referencing_when_flag_true(
    tmp_path: Path, mocker: Any
) -> None:
    """When self_referencing=True AND template references <repo>/.github/workflows/,
    the entry is skipped — no finding, even if the local file diverges."""
    from gh_manage.drift_sync import check_profile_files
    from gh_manage.models.profiles import ProfileFileEntry

    template_content = (
        "name: CI\n"
        "jobs:\n"
        "  pr-gate:\n"
        "    uses: yakkuro/gh-manage/.github/workflows/x.yml@v1.0.0\n"
    )
    mocker.patch(
        "gh_manage.drift_sync.checks._read_template_content",
        return_value=template_content,
    )

    profile = ProfileSpec(
        version=1,
        name="python-service",
        files=[
            ProfileFileEntry(
                source="ci/python-ci.yml",
                dest=".github/workflows/ci.yml",
                skip_if_exists=False,
            )
        ],
    )
    labels_config = _make_labels_config()
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".github" / "workflows").mkdir(parents=True)
    (repo_path / ".github" / "workflows" / "ci.yml").write_text(
        "name: CI\njobs:\n  pr-gate:\n    uses: ./.github/workflows/x.yml\n",
        encoding="utf-8",
    )

    ctx = ScanContext(
        path=repo_path,
        repo="yakkuro/gh-manage",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=None,
        self_referencing=True,
    )
    findings = check_profile_files(ctx)
    assert findings == ()


def test_check_profile_files_does_not_skip_when_self_referencing_false(
    tmp_path: Path, mocker: Any
) -> None:
    """Same setup as above but self_referencing=False: today's behavior —
    drift produces a MEDIUM finding."""
    from gh_manage.drift_sync import check_profile_files
    from gh_manage.models.profiles import ProfileFileEntry

    template_content = (
        "name: CI\n"
        "jobs:\n"
        "  pr-gate:\n"
        "    uses: yakkuro/gh-manage/.github/workflows/x.yml@v1.0.0\n"
    )
    mocker.patch(
        "gh_manage.drift_sync.checks._read_template_content",
        return_value=template_content,
    )

    profile = ProfileSpec(
        version=1,
        name="python-service",
        files=[
            ProfileFileEntry(
                source="ci/python-ci.yml",
                dest=".github/workflows/ci.yml",
                skip_if_exists=False,
            )
        ],
    )
    labels_config = _make_labels_config()
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".github" / "workflows").mkdir(parents=True)
    (repo_path / ".github" / "workflows" / "ci.yml").write_text(
        "name: CI\njobs:\n  pr-gate:\n    uses: ./.github/workflows/x.yml\n",
        encoding="utf-8",
    )

    ctx = ScanContext(
        path=repo_path,
        repo="yakkuro/gh-manage",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=None,
        self_referencing=False,
    )
    findings = check_profile_files(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert ".github/workflows/ci.yml" in findings[0].field_path


def test_check_profile_files_skips_only_self_ref_entries_not_others(
    tmp_path: Path, mocker: Any
) -> None:
    """Two entries: one self-referencing (skipped), one plain doc (still
    drift-checked). Confirms per-entry granularity — CLAUDE.md LOW signal
    still fires for self_referencing repos."""
    from gh_manage.drift_sync import check_profile_files
    from gh_manage.models.profiles import ProfileFileEntry

    workflow_template = (
        "name: CI\n"
        "jobs:\n"
        "  pr-gate:\n"
        "    uses: yakkuro/gh-manage/.github/workflows/x.yml@v1.0.0\n"
    )
    claude_template = "# CLAUDE.md (template)\nProject conventions.\n"

    def fake_read(source: str) -> str:
        if source == "ci/python-ci.yml":
            return workflow_template
        if source == "shared/CLAUDE.md":
            return claude_template
        raise AssertionError(f"unexpected source: {source!r}")

    mocker.patch(
        "gh_manage.drift_sync.checks._read_template_content", side_effect=fake_read
    )

    profile = ProfileSpec(
        version=1,
        name="python-service",
        files=[
            ProfileFileEntry(
                source="ci/python-ci.yml",
                dest=".github/workflows/ci.yml",
                skip_if_exists=False,
            ),
            ProfileFileEntry(
                source="shared/CLAUDE.md",
                dest="CLAUDE.md",
                skip_if_exists=True,
            ),
        ],
    )
    labels_config = _make_labels_config()
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".github" / "workflows").mkdir(parents=True)
    (repo_path / ".github" / "workflows" / "ci.yml").write_text(
        "name: CI\njobs:\n  pr-gate:\n    uses: ./.github/workflows/x.yml\n",
        encoding="utf-8",
    )
    (repo_path / "CLAUDE.md").write_text(
        "# CLAUDE.md (heavily edited)\nLocal overrides.\n",
        encoding="utf-8",
    )

    ctx = ScanContext(
        path=repo_path,
        repo="yakkuro/gh-manage",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=None,
        self_referencing=True,
    )
    findings = check_profile_files(ctx)
    # Workflow skipped, CLAUDE.md still drifts (LOW because skip_if_exists=True).
    assert len(findings) == 1
    assert findings[0].severity == "low"
    assert "CLAUDE.md" in findings[0].field_path
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/drift/test_drift_sync.py -k "self_referencing or is_self_referencing" -v`

Expected: 6 tests FAIL — `_is_self_referencing_template` is not defined; the per-entry skip is not implemented.

- [ ] **Step 3.3: Implement helper + per-entry skip**

Edit `src/gh_manage/drift_sync/checks.py`. Add the helper above `check_profile_files`:

```python
def _is_self_referencing_template(template_content: str, repo: str) -> bool:
    """True when the template references the scanning repo's own URL.

    Self-referencing pattern: a template uses
    `<owner>/<repo>/.github/workflows/...` (the pinned-tag form), but a
    repo that publishes those workflows mirrors them locally with `./`
    paths. The two cannot hash-match by design, so the drift check should
    skip the comparison when ScanContext.self_referencing=True.

    Detection is content-based (not config-based) so that adding new
    self-referencing templates does not require per-entry config — the
    helper picks them up automatically based on URL pattern.
    """
    return f"{repo}/.github/workflows/" in template_content
```

Then modify `check_profile_files` to skip per-entry. After the `template_content = _read_template_content(entry.source)` line and before `template_hash = _content_hash(template_content)`, insert:

```python
        if ctx.self_referencing and _is_self_referencing_template(
            template_content, ctx.repo
        ):
            log.info(
                "skipping self-referencing template %s for %s "
                "(template references %s/.github/workflows/)",
                entry.source,
                ctx.repo,
                ctx.repo,
            )
            continue
```

The full updated loop body:

```python
    for entry in ctx.profile.files:
        local = ctx.path / entry.dest
        template_content = _read_template_content(entry.source)

        if ctx.self_referencing and _is_self_referencing_template(
            template_content, ctx.repo
        ):
            log.info(
                "skipping self-referencing template %s for %s "
                "(template references %s/.github/workflows/)",
                entry.source,
                ctx.repo,
                ctx.repo,
            )
            continue

        template_hash = _content_hash(template_content)

        if not local.exists():
            ...  # unchanged
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/drift/test_drift_sync.py -k "self_referencing or is_self_referencing" -v`

Expected: 6 tests PASS.

- [ ] **Step 3.5: Run the full drift suite to verify no regression**

Run: `uv run pytest tests/unit/drift/ -v`

Expected: All tests pass, including `test_golden_production_data_zero_drift` and the existing scenario tests (none of which set `self_referencing=True`).

- [ ] **Step 3.6: Commit**

```bash
git add src/gh_manage/drift_sync/checks.py tests/unit/drift/test_drift_sync.py
git commit -m "feat(drift): skip self-referencing templates in check_profile_files (#72)

When ScanContext.self_referencing=True, check_profile_files skips entries
whose template content references <repo>/.github/workflows/ — the form a
self-hosted repo cannot hash-match against its local ./ path.

Per-entry granularity preserves drift detection for non-self-referencing
files (e.g., CLAUDE.md LOW still fires on user-editable drift).

Includes structured INFO log when the skip fires so the exemption is
visible in scan logs (per cron artifact upload, PR #68).

Refs #72."
```

---

## Task 4: `_resolve_self_referencing` CLI helper

**Files:**
- Modify: `src/gh_manage/commands/_shared.py`
- Create: `tests/unit/commands/test_shared_self_referencing.py`

- [ ] **Step 4.1: Read the existing `_shared.py` to find the right insertion point**

Run: `Read("src/gh_manage/commands/_shared.py")` (no actions; familiarize the engineer with surrounding helpers like `resolve_repos_path`).

- [ ] **Step 4.2: Write the failing tests**

Create `tests/unit/commands/test_shared_self_referencing.py`:

```python
"""Tests for _resolve_self_referencing — repos.yml lookup helper.

The helper is used by the single-repo drift CLI path to find the
self_referencing flag for the local repo (whose owner/repo is derived
from `git remote get-url origin`). The --all path bypasses the lookup
because it already has the RepoEntry in scope.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gh_manage.commands._shared import _resolve_self_referencing


def test_resolve_self_referencing_returns_true_for_gh_manage() -> None:
    """gh-manage is marked self_referencing: true in bundled repos.yml."""
    assert _resolve_self_referencing("yakkuro/gh-manage") is True


def test_resolve_self_referencing_returns_false_for_other_bundled_repos() -> None:
    """All other bundled entries default to False."""
    assert _resolve_self_referencing("yakkuro/slack-agents") is False
    assert _resolve_self_referencing("yakkuro/llm-kb") is False


def test_resolve_self_referencing_returns_false_for_unregistered_repo() -> None:
    """Repos not in repos.yml safely default to False (ad-hoc scans
    of unregistered repos are allowed)."""
    assert _resolve_self_referencing("yakkuro/totally-unregistered") is False


def test_resolve_self_referencing_returns_false_when_repos_yml_missing(
    mocker: Any,
) -> None:
    """If repos.yml cannot be loaded, the helper logs a warning and
    returns False — drift checks must not abort because of this lookup."""
    from gh_manage.config import ConfigError

    mocker.patch(
        "gh_manage.commands._shared.load_config",
        side_effect=ConfigError("simulated missing repos.yml"),
    )
    assert _resolve_self_referencing("yakkuro/gh-manage") is False
```

- [ ] **Step 4.3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/commands/test_shared_self_referencing.py -v`

Expected: All four FAIL with `ImportError: cannot import name '_resolve_self_referencing'`.

- [ ] **Step 4.4: Implement the helper**

Append to `src/gh_manage/commands/_shared.py` (after the existing `resolve_*` helpers; add necessary imports near the top if missing):

```python
def _resolve_self_referencing(owner_repo: str) -> bool:
    """Look up `owner_repo` in bundled repos.yml; return its self_referencing
    flag if found, False otherwise.

    Used by the single-repo drift CLI path (where there's no RepoEntry in
    scope) to flow the flag into ScanContext. The --all path bypasses
    this helper because _scan_worker has the RepoEntry directly.

    Failures (missing repos.yml, parse error) are logged and return False
    rather than propagating — the drift scan should not abort because of
    this lookup. An unregistered repo is also a False (no entry, ad-hoc
    scan).
    """
    from gh_manage.config import ConfigError, load_config
    from gh_manage.models.repos import ReposConfig

    try:
        config = load_config(resolve_repos_path(), ReposConfig)
    except (ConfigError, OSError) as e:
        log.warning(
            "could not load repos.yml for self_referencing lookup of %s: %s; "
            "treating as self_referencing=False",
            owner_repo,
            e,
        )
        return False

    for entry in config.repos:
        if entry.name == owner_repo:
            return entry.self_referencing
    return False
```

If `_shared.py` does not already import `logging`, add at the top:

```python
import logging

log = logging.getLogger(__name__)
```

- [ ] **Step 4.5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/commands/test_shared_self_referencing.py -v`

Expected: All four PASS.

- [ ] **Step 4.6: Commit**

```bash
git add src/gh_manage/commands/_shared.py tests/unit/commands/test_shared_self_referencing.py
git commit -m "feat(commands): add _resolve_self_referencing repos.yml lookup (#72)

Helper for the single-repo drift CLI path to find the self_referencing
flag for the local repo (owner/repo from \`git remote get-url origin\`).

Defaults to False for unregistered repos and on lookup failure (logged
warning) so drift scans never abort because of this lookup.

The --all path bypasses this helper because _scan_worker has the
RepoEntry in scope and reads entry.self_referencing directly.

Refs #72."
```

---

## Task 5: Wire `self_referencing` through the drift CLI

**Files:**
- Modify: `src/gh_manage/commands/drift.py:59-199, 202-261, 419-427`

- [ ] **Step 5.1: Modify `_scan_single_repo` signature to accept `self_referencing`**

Edit the signature at `src/gh_manage/commands/drift.py:59-66`:

```python
def _scan_single_repo(
    owner_repo: str,
    profile_name: str,
    severity: str,
    report_mode: str,
    output: Path | None,
    skip_profile_check: bool = False,
    self_referencing: bool = False,
) -> str:
```

Update the docstring `Args` block to add:

```python
        self_referencing: True when this repo publishes the templates it
            would be drift-checked against. Skips per-entry comparisons
            in check_profile_files for self-hosted templates.
```

Update the `ScanContext(...)` construction at `src/gh_manage/commands/drift.py:152-161`:

```python
        ctx = ScanContext(
            path=scan_path,
            repo=owner_repo,
            default_branch=default_branch,
            profile=profile,
            labels_config=labels_config,
            bp_config=bp_config,
            live_required_contexts=live_contexts,
            live_required_contexts_readable=live_readable,
            self_referencing=self_referencing,
        )
```

- [ ] **Step 5.2: Update `_scan_worker` to pass `entry.self_referencing`**

Edit `src/gh_manage/commands/drift.py:228-235` (the `_scan_single_repo(...)` call inside `_scan_worker`):

```python
            result_str = _scan_single_repo(
                entry.name,
                entry.profile,
                severity,
                report_mode,
                output,
                skip_profile_check=True,
                self_referencing=entry.self_referencing,
            )
```

- [ ] **Step 5.3: Update single-repo CLI handler to look up via helper**

Edit `src/gh_manage/commands/drift.py:419-427`:

```python
    owner_repo = git_cli.get_origin_owner_repo(target)
    self_referencing = _resolve_self_referencing(owner_repo)
    result = _scan_single_repo(
        owner_repo,
        profile_name,
        severity,
        report_mode,
        output,
        skip_profile_check=False,
        self_referencing=self_referencing,
    )
```

Add the import near the existing `_shared` imports at the top of `drift.py`:

```python
from gh_manage.commands._shared import (
    _resolve_self_referencing,
    handle_errors,
    resolve_branch_protection_path,
    resolve_default_labels_path,
    resolve_profile_path,
    resolve_repos_path,
)
```

- [ ] **Step 5.4: Add tests for the wiring**

Append to `tests/unit/commands/test_shared_self_referencing.py` (or create a sibling `tests/unit/cli/test_drift_self_referencing_wiring.py` if `cli/` is the convention — confirm by checking `tests/unit/cli/` first):

```python
def test_scan_single_repo_passes_self_referencing_to_context(
    tmp_path: Path, mocker: Any
) -> None:
    """_scan_single_repo must propagate self_referencing into ScanContext.
    Tests use mocking because we don't want a real GitHub round-trip."""
    from gh_manage import drift_sync
    from gh_manage.commands import drift as drift_cmd

    mocker.patch(
        "gh_manage.commands.drift.repo_info.get_default_branch",
        return_value="main",
    )
    mocker.patch(
        "gh_manage.commands.drift.protection_api.get_branch_protection",
        return_value={"required_status_checks": {"contexts": []}},
    )

    captured: dict[str, Any] = {}

    def capture_run_all(ctx: drift_sync.ScanContext) -> tuple:
        captured["self_referencing"] = ctx.self_referencing
        captured["repo"] = ctx.repo
        return ()

    mocker.patch(
        "gh_manage.commands.drift.drift_sync.run_all_checks",
        side_effect=capture_run_all,
    )
    mocker.patch(
        "gh_manage.commands.drift.drift_sync.format_stdout_report",
        return_value="ok",
    )

    drift_cmd._scan_single_repo(
        owner_repo="yakkuro/gh-manage",
        profile_name="python-service",
        severity="low",
        report_mode="stdout",
        output=None,
        skip_profile_check=True,
        self_referencing=True,
    )

    assert captured["self_referencing"] is True
    assert captured["repo"] == "yakkuro/gh-manage"
```

- [ ] **Step 5.5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/commands/test_shared_self_referencing.py tests/unit/drift/ -v`

Expected: All pass.

- [ ] **Step 5.6: Run a manual smoke test against gh-manage's real drift**

Run: `uv run gh manage drift . --profile python-service`

Expected output: no MEDIUM finding for `profile_files/.github/workflows/ci.yml`. The remaining LOW finding (CLAUDE.md, if drifted) still appears.

If `gh manage` is not on PATH yet, equivalent: `uv run python -m gh_manage drift . --profile python-service`.

- [ ] **Step 5.7: Commit**

```bash
git add src/gh_manage/commands/drift.py tests/unit/commands/test_shared_self_referencing.py
git commit -m "feat(drift): wire self_referencing through CLI to ScanContext (#72)

_scan_single_repo gains a self_referencing parameter (default False) that
flows into ScanContext. Two call sites:

- _scan_worker (--all mode): passes entry.self_referencing from RepoEntry
- single-repo CLI handler: looks up via _resolve_self_referencing(owner_repo)

Smoke test: gh manage drift . on gh-manage no longer reports the forever-
MEDIUM ci.yml template-hash finding; the LOW CLAUDE.md drift signal (if
the local file diverges) still fires.

Closes #72."
```

---

## Task 6: Drift scenario fixture

**Files:**
- Create: `tests/fixtures/drift-scenarios/profile_files/self-referencing-ci.yml`

- [ ] **Step 6.1: Examine an existing fixture to confirm shape**

Run: `Read("tests/fixtures/drift-scenarios/profile_files/ci-yml-drifted.yml")`

Note: the existing scenario format (per `conftest.py`) does not currently model the `self_referencing` flag on the scenario — `ScanContext` is built inside `test_scenario` without it.

- [ ] **Step 6.2: Decide whether to extend the scenario format or use a direct unit test**

Per the spec (test plan §6), a new fixture should cover the skip path. But the conftest's `DriftScenario` model has no field for `self_referencing` and `test_scenario` always builds `ScanContext` with the default.

Two options:
- **6.2a (preferred)**: Extend `DriftScenario` to optionally carry `self_referencing: bool = False` and have `test_scenario` propagate it to `ScanContext`. Then add the YAML fixture.
- **6.2b (fallback)**: Skip the YAML fixture; the unit tests in Task 3 already cover the skip-vs-no-skip behavior end-to-end.

Pick 6.2a unless `DriftScenario` extension creates collateral failures.

- [ ] **Step 6.3: Extend `DriftScenario` for `self_referencing`**

Edit `tests/unit/drift/conftest.py` — `DriftScenario`:

```python
class DriftScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    check: Literal["labels", "protection", "profile_files"]
    repo: str
    profile: str
    inputs: ScenarioInputs
    expected_findings: list[ExpectedFinding]
    self_referencing: bool = False
```

Edit `tests/unit/drift/test_drift_sync.py` — `test_scenario` `ScanContext` build:

```python
    ctx = ScanContext(
        path=repo_path,
        repo=scenario.repo,
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=bp_config,
        self_referencing=scenario.self_referencing,
    )
```

- [ ] **Step 6.4: Create the fixture YAML**

Write `tests/fixtures/drift-scenarios/profile_files/self-referencing-ci.yml`:

```yaml
name: self-referencing-ci
description: "Self-referencing repo's local ci.yml uses ./ path; template uses pinned-tag URL. Skip is correct — no finding."
check: profile_files
repo: yakkuro/gh-manage
profile: python-service
self_referencing: true
inputs:
  repo_files:
    CLAUDE.md: "__USE_TEMPLATE__"
    .github/workflows/ci.yml: |
      name: CI
      on:
        pull_request:
          branches:
            - main
        push:
          branches:
            - main
        workflow_dispatch:
      permissions:
        contents: read
      jobs:
        pr-gate:
          name: PR Gate
          uses: ./.github/workflows/reusable-pr-gate-python.yml
          with:
            python-version: "3.12"
            gh-manage-ref: ${{ github.sha }}
expected_findings: []
```

- [ ] **Step 6.5: Run scenario tests to verify the fixture passes**

Run: `uv run pytest tests/unit/drift/test_drift_sync.py::test_scenario -v -k self-referencing-ci`

Expected: PASS — the new scenario yields zero findings because `self_referencing: true` triggers the per-entry skip for the workflow template, and `CLAUDE.md` matches the template (so no LOW either).

- [ ] **Step 6.6: Run all scenario tests to verify no regression on existing ones**

Run: `uv run pytest tests/unit/drift/test_drift_sync.py::test_scenario -v`

Expected: All scenarios pass — existing fixtures default to `self_referencing=False` so behavior is unchanged.

- [ ] **Step 6.7: Commit**

```bash
git add tests/unit/drift/conftest.py tests/unit/drift/test_drift_sync.py tests/fixtures/drift-scenarios/profile_files/self-referencing-ci.yml
git commit -m "test(drift): add self-referencing-ci scenario fixture (#72)

Extend DriftScenario with optional self_referencing flag (default False
preserves existing-scenario behavior) and propagate it into the
ScanContext built by test_scenario.

New fixture self-referencing-ci.yml exercises the skip path end-to-end:
local ci.yml uses ./.github/workflows/X form, template uses pinned-tag
yakkuro/gh-manage/.github/workflows/X@v1.0.0 form. Expected findings: [].

Refs #72."
```

---

## Task 7: Final verification

**Files:** none (verification only)

- [ ] **Step 7.1: Run the full test suite**

Run: `uv run pytest -v`

Expected: All tests pass. Total count should be ~previous + 13 new tests (4 schema + 2 context + 6 helper/check + 1 wiring; the scenario test already exists and gains a parametrization).

- [ ] **Step 7.2: Run the linter (ruff version pinned to match CI)**

Run: `uvx ruff@0.8.0 format --check src/ tests/`
Run: `uvx ruff@0.8.0 check src/ tests/`

Expected: no violations. (Per memory `feedback_ruff_version_pin`: local venv ruff differs from CI's pinned 0.8.0.)

- [ ] **Step 7.3: Run a real drift scan against the live gh-manage repo**

Run: `uv run gh manage drift . --profile python-service --report-mode stdout`

Expected output:
- 0 critical, 0 high
- 0 medium for `profile_files/.github/workflows/ci.yml` (the previously forever-MEDIUM)
- At most 1 LOW for `CLAUDE.md` if user has edits (otherwise 0)

If you still see a MEDIUM for ci.yml, check:
- `repos.yml` has `self_referencing: true` for `yakkuro/gh-manage`
- `_resolve_self_referencing("yakkuro/gh-manage")` returns True (run a quick REPL check)
- `_is_self_referencing_template(template_content, "yakkuro/gh-manage")` returns True (check the template content)

- [ ] **Step 7.4: Push branch and open PR**

```bash
git push -u origin <branch-name>
gh pr create --title "fix(drift): exempt self-referencing repos from template-hash check (closes #72)" --body "$(cat <<'EOF'
## Summary
- `RepoEntry` and `ScanContext` gain a `self_referencing: bool = False` field.
- `check_profile_files` skips per-entry when `ctx.self_referencing=True` AND the template content references `<repo>/.github/workflows/`.
- `yakkuro/gh-manage` is marked `self_referencing: true` in bundled `repos.yml`.
- CLI plumbs the flag from `RepoEntry` (`--all`) or via a `repos.yml` lookup helper (single-repo).

## Why
gh-manage publishes its own reusable workflows, so its local `ci.yml` uses `./.github/workflows/...` (cannot pin to its own tag without bootstrap pain). The bundled template uses the pinned `yakkuro/gh-manage/.github/workflows/...@v1.0.0` form. The two will never hash-match → forever-MEDIUM noise on every gh-manage scan.

Per-entry granularity (rather than skipping the whole `check_profile_files`) keeps the `CLAUDE.md` LOW signal — useful drift detection on user-editable files is preserved.

## Test plan
- [x] Unit tests: schema, ScanContext field, helper, per-entry skip behavior, CLI lookup
- [x] Drift scenario fixture: `self-referencing-ci.yml` end-to-end skip path
- [x] Manual smoke: `gh manage drift .` on gh-manage no longer flags ci.yml
- [x] Regression: existing scenarios + golden test + bundled repos.yml load test still pass

## Spec
`docs/specs/2026-04-20-self-referencing-repos-design.md`

Closes #72.
EOF
)"
```

- [ ] **Step 7.5: Watch CI and request reviews per workflow-review.md**

Run: `gh pr checks <N> --watch`

Then trigger the cross-agent review per `claude-dotfiles/rules/workflow-review.md` (Codex + 3 reviewer agents). Address any HIGH/MEDIUM findings before merge.

---

## Notes

- **No backwards-compat shim.** `self_referencing: bool = False` is additive; existing `repos.yml` entries that omit the field continue to work.
- **No CLI flag.** The flag flows from config (`repos.yml`), not CLI args. This matches the issue's "Option 1" design — repo-level opt-in is centralized.
- **Logging visibility.** `log.info` fires when the skip activates, so the structured-logging artifact (PR #68) records the exemption per scan.
- **Future-proofing.** The detection helper checks `<ctx.repo>/.github/workflows/` dynamically, so any future self-publishing repo can opt in without code changes — they just set `self_referencing: true` in their `repos.yml` entry.

## Self-Review

- Spec coverage: every acceptance criterion from #72 maps to a task (Task 5 smoke test for #1, Task 3 default-False behavior + Task 5 wiring for #2, the spec doc for #3).
- Placeholder scan: each step has either complete code or a concrete command. `<branch-name>` and `<N>` in Task 7.4–7.5 are intentional — they depend on the runtime branch and PR number.
- Type consistency: `self_referencing: bool` is used uniformly across `RepoEntry`, `ScanContext`, `_scan_single_repo`, and the helper.
- Trade-off note: per-entry skip via content inspection (Option B in the spec) was chosen over whole-check early-return (Option A) so the LOW CLAUDE.md drift signal is preserved. The memory's "early-return when self_referencing=True" wording is honored in spirit (per-entry early-return inside the loop).
