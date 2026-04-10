# Phase 5 — Labels Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `cli/v0.2.0` — the first real domain command on gh-manage's CLI tag track. Implement `gh manage labels sync/diff/show` with rename support, prune semantics, and a 3-layer architecture (`github_client` → `labels_sync` → `commands/labels`).

**Architecture:** Tier 2 (3-layer). `src/gh_manage/github_client.py` holds the generic `gh api` transport layer AND the label CRUD helpers with a typed `GhError` hierarchy. `src/gh_manage/labels_sync.py` is pure functions (`compute_diff`, `apply_diff`) with a frozen `LabelsDiff` dataclass. `src/gh_manage/commands/labels.py` is a thin click group with 3 subcommands that catches errors via a decorator and formats plain-text diffs. No new dependencies — click/pydantic/pyyaml/pytest/pytest-mock are already pinned from Phase 0-4.

**Tech Stack:** Python 3.12, click 8, pydantic v2, PyYAML, `subprocess.run` for `gh` CLI calls, pytest + pytest-mock (subprocess mocking + function monkey-patching), Phase 4's `load_config` + `LabelsConfig`.

**Spec reference:** `docs/specs/2026-04-11-phase-5-labels-sync-design.md` (1175 lines, 8 brainstorming Qs, 1 round of spec-critique).

---

## File Structure

New / modified files after Phase 5 merges:

```
gh-manage/
├── config/
│   └── labels.yml                            # NEW — gh-manage's own label definitions (14 labels)
├── src/gh_manage/
│   ├── __init__.py                           # MODIFY — __version__ "0.1.0" → "0.2.0"
│   ├── github_client.py                      # NEW — transport + label CRUD + GhError hierarchy
│   ├── labels_sync.py                        # NEW — pure functions: compute_diff + apply_diff
│   ├── models/
│   │   └── labels.py                         # MODIFY — add old_name: str | None = None
│   └── commands/
│       └── labels.py                         # REWRITE — stub → click group with 3 subcommands
├── tests/
│   ├── test_sanity.py                        # MODIFY — expected __version__ "0.1.0" → "0.2.0"
│   ├── unit/
│   │   ├── cli/
│   │   │   ├── test_cli_entry.py             # MODIFY — remove "labels" from stub parametrize lists
│   │   │   └── test_labels.py                # NEW — 18 click runner tests
│   │   ├── config/
│   │   │   └── test_load_config.py           # MODIFY — add 1 test for labels-valid-with-rename.yml
│   │   ├── github_client/
│   │   │   ├── __init__.py                   # NEW (empty marker)
│   │   │   └── test_github_client.py         # NEW — 18 tests with subprocess mocked
│   │   └── labels_sync/
│   │       ├── __init__.py                   # NEW (empty marker)
│   │       └── test_labels_sync.py           # NEW — 19 pure-function + monkey-patch tests
│   └── fixtures/config/
│       └── labels-valid-with-rename.yml      # NEW — fixture with old_name for LabelsConfig test
├── pyproject.toml                            # MODIFY — version "0.1.0" → "0.2.0"
├── CHANGELOG-cli.md                          # MODIFY — add [0.2.0] entry
└── docs/usage/cli.md                         # MODIFY — add labels subcommand section + walkthrough
```

**File responsibilities:**

- `config/labels.yml` — source of truth for gh-manage's repo labels. 14 labels across 2 categories (type + meta). Exercised by self-dogfood.
- `src/gh_manage/github_client.py` — single point of contact with the `gh` CLI. Contains `GhError` base + 6 subclasses, `Label` frozen dataclass, `run_gh`/`run_gh_api` low-level transport, and 4 label CRUD helpers (`list_labels`, `create_label`, `update_label`, `delete_label`). All `subprocess.run` calls for `gh` live here; nowhere else.
- `src/gh_manage/labels_sync.py` — pure-function domain logic. Contains 4 operation dataclasses (`LabelRename`, `LabelCreate`, `LabelUpdate`, `LabelDelete`), the `LabelsDiff` aggregate, `compute_diff` (matching/rename/prune algorithm), and `apply_diff` (fail-fast execution with progress callback). Imports `github_client` but does NOT touch subprocess directly. Tests monkey-patch `github_client` functions.
- `src/gh_manage/models/labels.py` — extended with one new optional field (`old_name: str | None = None`). Backward compatible.
- `src/gh_manage/commands/labels.py` — thin click group. Contains `_parse_repo`, `_format_diff`, `_handle_errors` decorator, and 3 `@labels.command` functions (`sync`, `diff_cmd`, `show`). Click decorators catch errors via `_handle_errors`. No business logic lives here.

**Dependency direction (strict, no cycles):**

```
commands/labels.py
       │
       ▼
labels_sync.py ──────────┐
       │                 │
       ▼                 ▼
github_client.py    models/labels.py
```

---

## Commit plan overview

Each task produces ONE commit. Conventional commit types in parentheses.

1. (chore) Bootstrap: version bump + `LabelSpec.old_name` + 1 new config test + `labels-valid-with-rename.yml` fixture
2. (feat) `github_client.py` + `test_github_client.py` with 18 tests
3. (feat) `labels_sync.py` + `test_labels_sync.py` with 19 tests
4. (feat) `commands/labels.py` rewrite + `test_labels.py` with 18 tests + `test_cli_entry.py` update
5. (feat) `config/labels.yml` with 14 labels
6. (docs) `CHANGELOG-cli.md` [0.2.0] + `docs/usage/cli.md` labels section
7. Final verification + PR (no commits, just gate + push + `gh pr create`)

Total: 6 commits. Task 7 is verification + PR open.

---

## Task 1: Bootstrap — version bump + `LabelSpec.old_name` + backward-compat fixture

**Files:**
- Modify: `src/gh_manage/__init__.py`
- Modify: `pyproject.toml` (line 3)
- Modify: `tests/test_sanity.py`
- Modify: `src/gh_manage/models/labels.py`
- Create: `tests/fixtures/config/labels-valid-with-rename.yml`
- Modify: `tests/unit/config/test_load_config.py`

- [ ] **Step 1.1: Bump `__version__` in `src/gh_manage/__init__.py`**

Full new file content:

```python
"""gh-manage: GitHub-based CI/CD, Issue management, and operational system."""

__version__ = "0.2.0"
```

- [ ] **Step 1.2: Bump `version` in `pyproject.toml` line 3**

Change line 3 from `version = "0.1.0"` to `version = "0.2.0"`. No other lines touched.

Verify:

```bash
grep -n '^version' pyproject.toml
```

Expected: `3:version = "0.2.0"`

- [ ] **Step 1.3: Update `tests/test_sanity.py` to expect `"0.2.0"`**

Only the version literal changes. Full file content (to be written in place):

```python
"""Sanity tests that verify the Phase 0 scaffolding is wired correctly."""

from __future__ import annotations

import gh_manage


def test_package_version_is_defined() -> None:
    assert hasattr(gh_manage, "__version__")
    assert isinstance(gh_manage.__version__, str)
    assert gh_manage.__version__ == "0.2.0"


def test_cli_module_is_importable() -> None:
    from gh_manage import cli

    assert hasattr(cli, "main")
    assert callable(cli.main)
```

- [ ] **Step 1.4: Add `old_name: str | None = None` to `src/gh_manage/models/labels.py`**

Full new file content:

```python
"""Pydantic schema for config/labels.yml (version 1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LabelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    color: str = Field(pattern=r"^[0-9a-fA-F]{6}$")
    description: str | None = None
    old_name: str | None = None


class CategorySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    labels: list[LabelSpec] = Field(min_length=1)


class LabelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    categories: dict[str, CategorySpec] = Field(min_length=1)
```

- [ ] **Step 1.5: Create `tests/fixtures/config/labels-valid-with-rename.yml`**

Full file content:

```yaml
version: 1
categories:
  type:
    description: "Test category with rename support"
    labels:
      - name: "fix"
        old_name: "bug"
        color: "d73a4a"
        description: "Bug fix"
      - name: "feat"
        color: "a2eeef"
        description: "New feature"
```

- [ ] **Step 1.6: Add 1 new test to `tests/unit/config/test_load_config.py`**

Append this test to the END of the file (after `test_os_error_preserves_cause`):

```python


def test_load_labels_config_with_old_name_field() -> None:
    """Regression test for Phase 5: LabelsConfig accepts the new optional
    old_name field on LabelSpec. Existing Phase 4 fixtures (which don't
    set old_name) continue to validate because old_name defaults to None."""
    config = load_config(FIXTURES / "labels-valid-with-rename.yml", LabelsConfig)
    assert isinstance(config, LabelsConfig)
    assert config.version == 1
    type_labels = config.categories["type"].labels
    assert len(type_labels) == 2
    # Label with old_name
    assert type_labels[0].name == "fix"
    assert type_labels[0].old_name == "bug"
    # Label without old_name — defaults to None
    assert type_labels[1].name == "feat"
    assert type_labels[1].old_name is None
```

- [ ] **Step 1.7: Run sanity + config tests to verify the changes**

```bash
uv run pytest tests/test_sanity.py tests/unit/config/ -v
```

Expected: 2 sanity tests + 13 config tests (12 from Phase 4 + 1 new) all PASS.

```
tests/test_sanity.py::test_package_version_is_defined PASSED
tests/test_sanity.py::test_cli_module_is_importable PASSED
tests/unit/config/test_load_config.py::test_load_valid_labels_yml_returns_typed_model PASSED
... (11 more existing config tests)
tests/unit/config/test_load_config.py::test_load_labels_config_with_old_name_field PASSED
=========================== 15 passed in X.XX s ===========================
```

If any fail, fix the implementation (version literal or LabelSpec field) and re-run.

- [ ] **Step 1.8: Commit**

```bash
git add src/gh_manage/__init__.py pyproject.toml tests/test_sanity.py \
        src/gh_manage/models/labels.py \
        tests/fixtures/config/labels-valid-with-rename.yml \
        tests/unit/config/test_load_config.py
git commit -m "$(cat <<'EOF'
chore(phase-5): bump version to 0.2.0 + add LabelSpec.old_name field

- src/gh_manage/__init__.py + pyproject.toml + tests/test_sanity.py:
  version bump 0.1.0 → 0.2.0.
- src/gh_manage/models/labels.py: add optional old_name field to
  LabelSpec for rename support (Q3 A). Backward-compatible: defaults
  to None, Phase 4 fixtures validate unchanged.
- tests/fixtures/config/labels-valid-with-rename.yml: new fixture with
  old_name to verify Phase 5 schema extension.
- tests/unit/config/test_load_config.py: +1 test
  (test_load_labels_config_with_old_name_field) asserting the new
  fixture loads and the old_name field is preserved.
EOF
)"
```

---

## Task 2: `github_client.py` — transport + label CRUD + error hierarchy

This task ships the entire github_client module in one commit. Red-Green TDD rhythm is preserved internally: test file first, implementation next, verify Green, break one line to prove Red, restore.

**Files:**
- Create: `tests/unit/github_client/__init__.py` (empty marker)
- Create: `tests/unit/github_client/test_github_client.py`
- Create: `src/gh_manage/github_client.py`

- [ ] **Step 2.1: Create `tests/unit/github_client/__init__.py`**

Empty file (0 bytes). Package marker.

```bash
: > tests/unit/github_client/__init__.py
```

- [ ] **Step 2.2: Create `tests/unit/github_client/test_github_client.py` with all 18 tests**

Full file content:

```python
"""Tests for gh_manage.github_client with subprocess.run mocked."""

from __future__ import annotations

import json
from subprocess import CompletedProcess

import pytest
from pytest_mock import MockerFixture

from gh_manage.github_client import (
    GhAPIError,
    GhAuthError,
    GhNotFoundError,
    GhNotInstalledError,
    GhPermissionError,
    GhRateLimitError,
    Label,
    create_label,
    delete_label,
    list_labels,
    run_gh_api,
    update_label,
)


def _mock_gh_success(mocker: MockerFixture, stdout: str):
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=0, stdout=stdout, stderr=""
        ),
    )


def _mock_gh_failure(mocker: MockerFixture, stderr: str, returncode: int = 1):
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr=stderr
        ),
    )


# Happy path — list_labels
def test_list_labels_parses_json_response(mocker: MockerFixture) -> None:
    _mock_gh_success(
        mocker,
        json.dumps(
            [
                {"name": "bug", "color": "d73a4a", "description": "Buggy"},
                {"name": "feat", "color": "a2eeef", "description": None},
            ]
        ),
    )
    result = list_labels("yakkuro/gh-manage")
    assert result == [
        Label(name="bug", color="d73a4a", description="Buggy"),
        Label(name="feat", color="a2eeef", description=""),
    ]


def test_list_labels_auto_paginates(mocker: MockerFixture) -> None:
    """list_labels must pass --paginate to gh api."""
    mock_run = _mock_gh_success(mocker, "[]")
    list_labels("yakkuro/gh-manage")
    args = mock_run.call_args.args[0]
    assert "--paginate" in args


def test_list_labels_handles_empty_response(mocker: MockerFixture) -> None:
    _mock_gh_success(mocker, "[]")
    result = list_labels("yakkuro/gh-manage")
    assert result == []


# Normalization
def test_list_labels_normalizes_color_to_lowercase(mocker: MockerFixture) -> None:
    _mock_gh_success(
        mocker,
        json.dumps([{"name": "bug", "color": "D73A4A", "description": "x"}]),
    )
    result = list_labels("yakkuro/gh-manage")
    assert result[0].color == "d73a4a"


def test_list_labels_converts_null_description_to_empty_string(
    mocker: MockerFixture,
) -> None:
    _mock_gh_success(
        mocker,
        json.dumps([{"name": "bug", "color": "d73a4a", "description": None}]),
    )
    result = list_labels("yakkuro/gh-manage")
    assert result[0].description == ""


# Happy path — create_label
def test_create_label_sends_correct_body(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "")
    create_label(
        "yakkuro/gh-manage",
        Label(name="chore", color="e1e7eb", description="housekeeping"),
    )
    args = mock_run.call_args.args[0]
    assert "api" in args
    assert "repos/yakkuro/gh-manage/labels" in args
    assert "-X" in args
    assert "POST" in args
    assert "name=chore" in args
    assert "color=e1e7eb" in args
    assert "description=housekeeping" in args


# Happy path — update_label with rename
def test_update_label_with_rename_includes_new_name(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "")
    update_label(
        "yakkuro/gh-manage",
        current_name="bug",
        new_label=Label(name="fix", color="d73a4a", description="Bug fix"),
    )
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/labels/bug" in args
    assert "-X" in args
    assert "PATCH" in args
    assert "new_name=fix" in args
    assert "color=d73a4a" in args
    assert "description=Bug fix" in args


# Happy path — update_label without rename
def test_update_label_without_rename_omits_new_name(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "")
    update_label(
        "yakkuro/gh-manage",
        current_name="fix",
        new_label=Label(name="fix", color="d73a4a", description="Updated desc"),
    )
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/labels/fix" in args
    assert "-X" in args
    assert "PATCH" in args
    assert not any("new_name=" in a for a in args)
    assert "color=d73a4a" in args
    assert "description=Updated desc" in args


# Happy path — delete_label
def test_delete_label_calls_correct_endpoint(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "")
    delete_label("yakkuro/gh-manage", "bug")
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/labels/bug" in args
    assert "-X" in args
    assert "DELETE" in args


# Error classification — parametrized
@pytest.mark.parametrize(
    ("stderr", "expected_exc"),
    [
        ("HTTP 404: Not Found\n", GhNotFoundError),
        ("You are not logged in to any GitHub hosts.\n", GhAuthError),
        ("Bad credentials\n", GhAuthError),
        ("HTTP 403: Forbidden\n", GhPermissionError),
        ("API rate limit exceeded\n", GhRateLimitError),
        ("Some unknown error\n", GhAPIError),
    ],
)
def test_run_gh_api_classifies_stderr_into_typed_exception(
    mocker: MockerFixture, stderr: str, expected_exc: type[Exception]
) -> None:
    _mock_gh_failure(mocker, stderr)
    with pytest.raises(expected_exc):
        run_gh_api("repos/foo/bar/labels")


# Not-installed case
def test_run_gh_api_filenotfound_raises_gh_not_installed(
    mocker: MockerFixture,
) -> None:
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("gh"))
    with pytest.raises(GhNotInstalledError, match="cli.github.com"):
        run_gh_api("repos/foo/bar/labels")


# Actionable messages
def test_gh_not_found_error_message_contains_gh_auth_status(
    mocker: MockerFixture,
) -> None:
    _mock_gh_failure(mocker, "HTTP 404: Not Found\n")
    with pytest.raises(GhNotFoundError, match="gh auth status"):
        run_gh_api("repos/foo/bar/labels")


def test_gh_auth_error_mentions_gh_auth_login(mocker: MockerFixture) -> None:
    _mock_gh_failure(mocker, "You are not logged in.\n")
    with pytest.raises(GhAuthError, match="gh auth login"):
        run_gh_api("repos/foo/bar/labels")
```

- [ ] **Step 2.3: Red verification — tests must fail because github_client.py doesn't exist yet**

```bash
uv run pytest tests/unit/github_client/ -v
```

Expected: collection error with `ModuleNotFoundError: No module named 'gh_manage.github_client'`. This is the expected Red state. If pytest reports anything else, stop and report NEEDS_CONTEXT.

- [ ] **Step 2.4: Create `src/gh_manage/github_client.py`**

Full file content:

```python
"""gh CLI subprocess transport + label CRUD helpers.

All `gh` subprocess invocations for gh-manage go through this module.
Error handling maps `gh api` failures to a typed GhError hierarchy with
actionable messages.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Label:
    """A GitHub label in normalized form.

    - color: always lowercase 6-char hex (github_client.list_labels
      normalizes from GitHub API which returns lowercase, but we lowercase
      defensively for cross-API consistency).
    - description: always str, never None. GitHub returns null for unset
      descriptions; we normalize to "" so equality comparisons are safe.
    """

    name: str
    color: str
    description: str


def _raise_classified_error(
    *, endpoint: str, returncode: int, stderr: str
) -> NoReturn:
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
    return json.loads(stdout)


def list_labels(repo: str) -> list[Label]:
    """GET /repos/{repo}/labels — auto-paginated.

    `repo` must be in `owner/repo` form.
    Returns a list of Label instances with color lowercased and
    description normalized to "" if the API returned null.
    """
    data = run_gh_api(f"repos/{repo}/labels", paginate=True)
    if data is None:
        return []
    return [
        Label(
            name=item["name"],
            color=item["color"].lower(),
            description=item.get("description") or "",
        )
        for item in data
    ]


def create_label(repo: str, label: Label) -> None:
    """POST /repos/{repo}/labels with {name, color, description}."""
    run_gh_api(
        f"repos/{repo}/labels",
        method="POST",
        fields={
            "name": label.name,
            "color": label.color,
            "description": label.description,
        },
    )


def update_label(repo: str, current_name: str, new_label: Label) -> None:
    """PATCH /repos/{repo}/labels/{current_name}.

    If new_label.name != current_name the body includes new_name (rename).
    Otherwise only color/description are updated.
    """
    fields = {
        "color": new_label.color,
        "description": new_label.description,
    }
    if new_label.name != current_name:
        fields["new_name"] = new_label.name

    run_gh_api(
        f"repos/{repo}/labels/{current_name}",
        method="PATCH",
        fields=fields,
    )


def delete_label(repo: str, name: str) -> None:
    """DELETE /repos/{repo}/labels/{name}."""
    run_gh_api(
        f"repos/{repo}/labels/{name}",
        method="DELETE",
    )
```

- [ ] **Step 2.5: Green verification — all 18 tests pass**

```bash
uv run pytest tests/unit/github_client/ -v
```

Expected: 18 tests PASS (11 non-parametrized + 1 parametrized across 6 stderr cases + 1 filenotfound test + 2 actionable message tests = wait, let me recount: 3 list_labels happy + 2 normalization + 4 CRUD + 6 parametrized errors + 1 filenotfound + 2 actionable = 18).

```
========================== 18 passed in X.XX s ===========================
```

- [ ] **Step 2.6: Red-Green verification — prove the tests catch a real regression**

Temporarily break the `list_labels` color normalization — change `color=item["color"].lower()` to `color=item["color"]` (remove `.lower()`). Re-run:

```bash
uv run pytest tests/unit/github_client/test_github_client.py::test_list_labels_normalizes_color_to_lowercase -v
```

Expected: FAILED with `assert 'D73A4A' == 'd73a4a'`. Restore the `.lower()` call and re-run all 18 tests:

```bash
uv run pytest tests/unit/github_client/ -v
```

Expected: 18 passed again.

- [ ] **Step 2.7: Full test suite must still be green**

```bash
uv run pytest -v
```

Expected: existing Phase 4 tests (30) + Task 1's new config test (1) + Task 2's 18 = 49 tests PASS.

- [ ] **Step 2.8: mypy must be clean (reusable gate invocation)**

```bash
uv run --with "mypy==1.12.0" mypy src
```

Expected: `Success: no issues found in X source files`. If mypy complains about `NoReturn` or `Any` usage, fix inline (these are all stdlib `typing` imports and should just work on Python 3.12).

- [ ] **Step 2.9: Commit**

```bash
git add tests/unit/github_client/ src/gh_manage/github_client.py
git commit -m "$(cat <<'EOF'
feat(phase-5): add github_client.py with transport + label CRUD + GhError

New module src/gh_manage/github_client.py:

- GhError hierarchy: base + 6 subclasses (NotInstalled, Auth, NotFound,
  Permission, RateLimit, APIError) with actionable messages including
  the failing endpoint and suggested remediation commands.
- Label frozen dataclass: normalized (lowercase color, empty-string
  description for None from GitHub API).
- run_gh(args): subprocess wrapper with FileNotFoundError → GhNotInstalled.
- run_gh_api(endpoint, method, fields, paginate): gh api wrapper with
  JSON parsing and empty-body → None handling.
- _raise_classified_error: stderr pattern matching in order (rate limit
  first, then 404/401/403, then catch-all APIError).
- list_labels / create_label / update_label / delete_label: typed
  CRUD helpers. update_label handles rename via new_name body field.

Tests (tests/unit/github_client/test_github_client.py): 18 cases with
subprocess.run mocked via pytest-mock. Covers happy path, color/desc
normalization, 6 error classifications, FileNotFoundError path, and
2 actionable-message spot checks.
EOF
)"
```

---

## Task 3: `labels_sync.py` — pure-function diff + apply

**Files:**
- Create: `tests/unit/labels_sync/__init__.py` (empty marker)
- Create: `tests/unit/labels_sync/test_labels_sync.py`
- Create: `src/gh_manage/labels_sync.py`

- [ ] **Step 3.1: Create `tests/unit/labels_sync/__init__.py`**

Empty file.

```bash
: > tests/unit/labels_sync/__init__.py
```

- [ ] **Step 3.2: Create `tests/unit/labels_sync/test_labels_sync.py` with all 19 tests**

Full file content:

```python
"""Tests for gh_manage.labels_sync — pure-function diff computation and apply."""

from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from gh_manage.github_client import GhAPIError, Label
from gh_manage.labels_sync import (
    LabelCreate,
    LabelDelete,
    LabelRename,
    LabelsDiff,
    LabelUpdate,
    apply_diff,
    compute_diff,
)
from gh_manage.models.labels import CategorySpec, LabelSpec, LabelsConfig


def _make_config(specs: list[LabelSpec]) -> LabelsConfig:
    """Build a LabelsConfig with one category containing the given specs."""
    return LabelsConfig(
        version=1,
        categories={
            "test": CategorySpec(description="test", labels=specs),
        },
    )


# compute_diff — happy paths
def test_empty_repo_with_new_labels_produces_creates_only() -> None:
    current: list[Label] = []
    desired = _make_config(
        [
            LabelSpec(name="bug", color="ff0000", description="broken"),
            LabelSpec(name="feat", color="00ff00", description="new"),
        ]
    )
    diff = compute_diff(current, desired)
    assert len(diff.creates) == 2
    assert len(diff.renames) == 0
    assert len(diff.updates) == 0
    assert len(diff.deletes) == 0


def test_matching_labels_produce_empty_diff() -> None:
    current = [Label(name="bug", color="d73a4a", description="broken")]
    desired = _make_config(
        [LabelSpec(name="bug", color="d73a4a", description="broken")]
    )
    diff = compute_diff(current, desired)
    assert diff.is_empty


def test_color_mismatch_produces_update() -> None:
    current = [Label(name="bug", color="d73a4a", description="broken")]
    desired = _make_config(
        [LabelSpec(name="bug", color="ff0000", description="broken")]
    )
    diff = compute_diff(current, desired)
    assert len(diff.updates) == 1
    assert diff.updates[0].label.color == "ff0000"


def test_description_mismatch_produces_update() -> None:
    current = [Label(name="bug", color="d73a4a", description="old")]
    desired = _make_config(
        [LabelSpec(name="bug", color="d73a4a", description="new")]
    )
    diff = compute_diff(current, desired)
    assert len(diff.updates) == 1


def test_uppercase_desired_color_matches_lowercase_current() -> None:
    """compute_diff must normalize spec.color via .lower() before comparing."""
    current = [Label(name="bug", color="d73a4a", description="x")]
    desired = _make_config(
        [LabelSpec(name="bug", color="D73A4A", description="x")]
    )
    diff = compute_diff(current, desired)
    assert diff.is_empty


def test_none_description_in_spec_matches_empty_description_in_current() -> None:
    """LabelSpec.description=None must equal Label.description=''."""
    current = [Label(name="bug", color="d73a4a", description="")]
    desired = _make_config(
        [LabelSpec(name="bug", color="d73a4a", description=None)]
    )
    diff = compute_diff(current, desired)
    assert diff.is_empty


# compute_diff — rename logic
def test_old_name_match_produces_rename_not_create() -> None:
    current = [Label(name="bug", color="d73a4a", description="broken")]
    desired = _make_config(
        [
            LabelSpec(
                name="fix", old_name="bug", color="d73a4a", description="Bug fix"
            )
        ]
    )
    diff = compute_diff(current, desired)
    assert len(diff.renames) == 1
    assert diff.renames[0].old_name == "bug"
    assert diff.renames[0].new_label.name == "fix"
    assert len(diff.creates) == 0


def test_rename_with_color_change_is_single_rename_not_update() -> None:
    """A rename that also changes color is ONE rename operation, not a
    separate rename + update. The PATCH request includes new_name, color,
    and description in one call."""
    current = [Label(name="bug", color="d73a4a", description="x")]
    desired = _make_config(
        [LabelSpec(name="fix", old_name="bug", color="ff0000", description="x")]
    )
    diff = compute_diff(current, desired)
    assert len(diff.renames) == 1
    assert diff.renames[0].new_label.color == "ff0000"
    assert len(diff.updates) == 0


def test_name_match_preferred_over_old_name_match() -> None:
    """If a spec's name already matches a current label, that takes
    precedence over the spec's old_name field. The old_name-referenced
    label stays unmatched (no rename)."""
    current = [
        Label(name="fix", color="d73a4a", description="fix"),
        Label(name="bug", color="ffffff", description="bug"),
    ]
    desired = _make_config(
        [LabelSpec(name="fix", old_name="bug", color="d73a4a", description="fix")]
    )
    diff = compute_diff(current, desired)
    assert len(diff.renames) == 0
    # "fix" matches; "bug" is unmatched but prune=False so no delete
    assert diff.is_empty


# compute_diff — prune logic
def test_prune_false_ignores_extra_labels() -> None:
    current = [
        Label(name="bug", color="d73a4a", description="x"),
        Label(name="old-label", color="ffffff", description="y"),
    ]
    desired = _make_config(
        [LabelSpec(name="bug", color="d73a4a", description="x")]
    )
    diff = compute_diff(current, desired, prune=False)
    assert len(diff.deletes) == 0


def test_prune_true_emits_deletes_for_extras() -> None:
    current = [
        Label(name="bug", color="d73a4a", description="x"),
        Label(name="old-label", color="ffffff", description="y"),
    ]
    desired = _make_config(
        [LabelSpec(name="bug", color="d73a4a", description="x")]
    )
    diff = compute_diff(current, desired, prune=True)
    assert len(diff.deletes) == 1
    assert diff.deletes[0].name == "old-label"


def test_prune_does_not_delete_label_consumed_by_rename() -> None:
    """Even with prune=True, a label that was consumed by a rename
    should NOT be emitted as a delete."""
    current = [Label(name="bug", color="d73a4a", description="x")]
    desired = _make_config(
        [LabelSpec(name="fix", old_name="bug", color="d73a4a", description="x")]
    )
    diff = compute_diff(current, desired, prune=True)
    assert len(diff.deletes) == 0
    assert len(diff.renames) == 1


# compute_diff — edge cases
def test_prune_false_with_unrelated_desired_no_deletes() -> None:
    """With prune=False, labels in current but not in desired (by name or
    old_name) are ignored — no delete emitted."""
    current = [Label(name="bug", color="d73a4a", description="x")]
    desired = _make_config(
        [LabelSpec(name="other", color="ffffff", description="y")]
    )
    diff = compute_diff(current, desired, prune=False)
    assert len(diff.deletes) == 0
    assert len(diff.creates) == 1


def test_prune_true_with_unrelated_desired_deletes_all_current() -> None:
    current = [
        Label(name="bug", color="d73a4a", description="x"),
        Label(name="feat", color="00ff00", description="y"),
    ]
    desired = _make_config(
        [LabelSpec(name="other", color="ffffff", description="z")]
    )
    diff = compute_diff(current, desired, prune=True)
    assert len(diff.deletes) == 2
    delete_names = {d.name for d in diff.deletes}
    assert delete_names == {"bug", "feat"}


# apply_diff — execution order
def test_apply_diff_calls_renames_before_creates(mocker: MockerFixture) -> None:
    call_order: list[str] = []

    mocker.patch(
        "gh_manage.github_client.update_label",
        side_effect=lambda *a, **k: call_order.append("update"),
    )
    mocker.patch(
        "gh_manage.github_client.create_label",
        side_effect=lambda *a, **k: call_order.append("create"),
    )
    mocker.patch("gh_manage.github_client.delete_label")

    diff = LabelsDiff(
        renames=(LabelRename(old_name="bug", new_label=Label("fix", "d73a4a", "x")),),
        creates=(LabelCreate(label=Label("chore", "e1e7eb", "y")),),
        updates=(),
        deletes=(),
    )
    apply_diff(diff, "yakkuro/gh-manage")
    assert call_order == ["update", "create"]


def test_apply_diff_calls_deletes_last(mocker: MockerFixture) -> None:
    call_order: list[str] = []
    mocker.patch(
        "gh_manage.github_client.create_label",
        side_effect=lambda *a, **k: call_order.append("create"),
    )
    mocker.patch(
        "gh_manage.github_client.update_label",
        side_effect=lambda *a, **k: call_order.append("update"),
    )
    mocker.patch(
        "gh_manage.github_client.delete_label",
        side_effect=lambda *a, **k: call_order.append("delete"),
    )

    diff = LabelsDiff(
        renames=(),
        creates=(LabelCreate(label=Label("chore", "e1e7eb", "x")),),
        updates=(LabelUpdate(label=Label("bug", "ff0000", "x")),),
        deletes=(LabelDelete(name="old"),),
    )
    apply_diff(diff, "yakkuro/gh-manage")
    assert call_order[-1] == "delete"


def test_apply_diff_fails_fast_on_first_error(mocker: MockerFixture) -> None:
    """When the rename step raises, subsequent create/update/delete must
    NOT be called."""

    def fail_update(*args, **kwargs):
        raise GhAPIError("simulated failure")

    mock_create = mocker.patch("gh_manage.github_client.create_label")
    mocker.patch("gh_manage.github_client.update_label", side_effect=fail_update)
    mocker.patch("gh_manage.github_client.delete_label")

    diff = LabelsDiff(
        renames=(LabelRename(old_name="bug", new_label=Label("fix", "d73a4a", "x")),),
        creates=(LabelCreate(label=Label("chore", "e1e7eb", "y")),),
        updates=(),
        deletes=(),
    )
    with pytest.raises(GhAPIError):
        apply_diff(diff, "yakkuro/gh-manage")
    mock_create.assert_not_called()


def test_apply_diff_progress_callback_invoked_in_order(
    mocker: MockerFixture,
) -> None:
    mocker.patch("gh_manage.github_client.update_label")
    mocker.patch("gh_manage.github_client.create_label")
    mocker.patch("gh_manage.github_client.delete_label")

    progress_calls: list[str] = []
    diff = LabelsDiff(
        renames=(LabelRename(old_name="bug", new_label=Label("fix", "d73a4a", "x")),),
        creates=(LabelCreate(label=Label("chore", "e1e7eb", "y")),),
        updates=(),
        deletes=(),
    )
    apply_diff(diff, "yakkuro/gh-manage", progress=progress_calls.append)
    assert len(progress_calls) == 2
    assert "bug" in progress_calls[0]
    assert "fix" in progress_calls[0]
    assert "chore" in progress_calls[1]


# LabelsDiff — properties
def test_labels_diff_is_empty_and_total_changes() -> None:
    empty = LabelsDiff(renames=(), creates=(), updates=(), deletes=())
    assert empty.is_empty
    assert empty.total_changes == 0

    nonempty = LabelsDiff(
        renames=(LabelRename(old_name="a", new_label=Label("b", "000000", "")),),
        creates=(LabelCreate(label=Label("c", "111111", "")),),
        updates=(),
        deletes=(),
    )
    assert not nonempty.is_empty
    assert nonempty.total_changes == 2
```

- [ ] **Step 3.3: Red verification — tests must fail because labels_sync.py doesn't exist**

```bash
uv run pytest tests/unit/labels_sync/ -v
```

Expected: `ModuleNotFoundError: No module named 'gh_manage.labels_sync'`. This is the Red state.

- [ ] **Step 3.4: Create `src/gh_manage/labels_sync.py`**

Full file content:

```python
"""Pure-function label diff computation and application.

All functions here are click/subprocess independent. Tests can exercise
compute_diff with in-memory data and apply_diff with monkey-patched
github_client module functions.

Dependency direction: this module imports github_client for the Label
dataclass and the 4 CRUD helpers. It does NOT import click or subprocess.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from gh_manage import github_client
from gh_manage.github_client import Label
from gh_manage.models.labels import LabelsConfig, LabelSpec


@dataclass(frozen=True)
class LabelRename:
    """A label rename operation. Uses PATCH with new_name body field."""

    old_name: str
    new_label: Label


@dataclass(frozen=True)
class LabelCreate:
    """A label creation. Uses POST."""

    label: Label


@dataclass(frozen=True)
class LabelUpdate:
    """A same-name label update (color/description only). Uses PATCH without new_name."""

    label: Label


@dataclass(frozen=True)
class LabelDelete:
    """A label deletion. Uses DELETE. Only emitted when prune=True."""

    name: str


@dataclass(frozen=True)
class LabelsDiff:
    """Computed diff between current repo labels and desired config.

    Operations are grouped by type into frozen tuples. Empty tuples for
    any empty bucket. apply_diff executes them in fail-fast order:
    renames → creates → updates → deletes.
    """

    renames: tuple[LabelRename, ...]
    creates: tuple[LabelCreate, ...]
    updates: tuple[LabelUpdate, ...]
    deletes: tuple[LabelDelete, ...]

    @property
    def is_empty(self) -> bool:
        return not (
            self.renames or self.creates or self.updates or self.deletes
        )

    @property
    def total_changes(self) -> int:
        return (
            len(self.renames)
            + len(self.creates)
            + len(self.updates)
            + len(self.deletes)
        )


def _spec_to_label(spec: LabelSpec) -> Label:
    """Convert a LabelSpec (from yml) into a Label (github_client type).

    Normalizes:
      - color.lower() — LabelSpec regex accepts any case; we lowercase here
        so compute_diff comparisons are case-insensitive.
      - description None → "" — LabelSpec.description is str | None,
        Label.description is str. Normalize None to "" so equality works.
    """
    return Label(
        name=spec.name,
        color=spec.color.lower(),
        description=spec.description or "",
    )


def _flatten_desired(desired: LabelsConfig) -> list[LabelSpec]:
    """Flatten LabelsConfig.categories into a flat list of LabelSpec."""
    specs: list[LabelSpec] = []
    for category in desired.categories.values():
        specs.extend(category.labels)
    return specs


def compute_diff(
    current: list[Label],
    desired: LabelsConfig,
    *,
    prune: bool = False,
) -> LabelsDiff:
    """Compute the diff between current repo labels and desired config.

    Algorithm:
      1. Build a name→Label map of current labels.
      2. For each LabelSpec in flattened desired.categories:
         a. If spec.name is in current: compare color/desc → LabelUpdate or skip.
         b. Elif spec.old_name is set and in current: LabelRename.
         c. Else: LabelCreate.
         Mark any matched current name as consumed in either case.
      3. For each current label NOT consumed in step 2:
         - prune=True → LabelDelete.
         - prune=False → ignore.

    Normalization (applied before any equality check):
      - Color: spec.color.lower() vs current.color (already lowercase from
        github_client.list_labels normalization).
      - Description: (spec.description or "") vs current.description
        (already "" if GitHub returned null).
    """
    current_by_name = {label.name: label for label in current}
    consumed: set[str] = set()

    renames: list[LabelRename] = []
    creates: list[LabelCreate] = []
    updates: list[LabelUpdate] = []

    for spec in _flatten_desired(desired):
        desired_label = _spec_to_label(spec)

        # Case a: name match (preferred over old_name)
        if spec.name in current_by_name:
            existing = current_by_name[spec.name]
            if (
                existing.color != desired_label.color
                or existing.description != desired_label.description
            ):
                updates.append(LabelUpdate(label=desired_label))
            consumed.add(spec.name)
            continue

        # Case b: rename via old_name
        if spec.old_name and spec.old_name in current_by_name:
            renames.append(
                LabelRename(old_name=spec.old_name, new_label=desired_label)
            )
            consumed.add(spec.old_name)
            continue

        # Case c: no match at all → create
        creates.append(LabelCreate(label=desired_label))

    deletes: list[LabelDelete] = []
    if prune:
        for label in current:
            if label.name not in consumed:
                deletes.append(LabelDelete(name=label.name))

    return LabelsDiff(
        renames=tuple(renames),
        creates=tuple(creates),
        updates=tuple(updates),
        deletes=tuple(deletes),
    )


def apply_diff(
    diff: LabelsDiff,
    repo: str,
    *,
    progress: Callable[[str], None] = lambda _: None,
) -> None:
    """Apply diff operations in fail-fast order.

    Execution order:
      1. Renames — first, so subsequent creates don't collide with old names.
      2. Creates — new labels.
      3. Updates — same-name color/desc changes.
      4. Deletes — last, so a failed delete doesn't orphan dependent state.

    Fail-fast semantics: on the first GhError from github_client, the
    exception propagates to the caller. No rollback; operations are
    idempotent, so re-running after fixing the cause picks up remaining work.

    `progress` is called with a one-line description BEFORE each operation.
    CLI layer passes click.echo; tests pass a no-op lambda or a list.append.
    """
    for rename in diff.renames:
        progress(f"~ {rename.old_name} → {rename.new_label.name}")
        github_client.update_label(repo, rename.old_name, rename.new_label)
    for create in diff.creates:
        progress(f"+ {create.label.name}")
        github_client.create_label(repo, create.label)
    for update in diff.updates:
        progress(f"≈ {update.label.name}")
        github_client.update_label(repo, update.label.name, update.label)
    for delete in diff.deletes:
        progress(f"- {delete.name}")
        github_client.delete_label(repo, delete.name)
```

- [ ] **Step 3.5: Green verification — all 19 labels_sync tests pass**

```bash
uv run pytest tests/unit/labels_sync/ -v
```

Expected: 19 tests PASS.

- [ ] **Step 3.6: Red-Green verification — break one line to prove regressions are caught**

Temporarily change `_spec_to_label` to omit the `.lower()`:

```python
# WAS: color=spec.color.lower(),
color=spec.color,  # temporarily broken
```

Run:

```bash
uv run pytest tests/unit/labels_sync/test_labels_sync.py::test_uppercase_desired_color_matches_lowercase_current -v
```

Expected: FAILED. Restore the `.lower()` and re-run all 19:

```bash
uv run pytest tests/unit/labels_sync/ -v
```

Expected: 19 passed.

- [ ] **Step 3.7: Full suite + mypy clean**

```bash
uv run pytest -v
```

Expected: 49 (post-Task-2) + 19 new = 68 tests PASS.

```bash
uv run --with "mypy==1.12.0" mypy src
```

Expected: clean.

- [ ] **Step 3.8: Commit**

```bash
git add tests/unit/labels_sync/ src/gh_manage/labels_sync.py
git commit -m "$(cat <<'EOF'
feat(phase-5): add labels_sync.py with compute_diff + apply_diff

New module src/gh_manage/labels_sync.py:

- 4 operation dataclasses: LabelRename, LabelCreate, LabelUpdate,
  LabelDelete (all frozen).
- LabelsDiff aggregate dataclass with is_empty and total_changes
  properties.
- _spec_to_label helper: LabelSpec → Label with color.lower() and
  description None→"" normalization.
- _flatten_desired helper: LabelsConfig.categories → list[LabelSpec].
- compute_diff: matching algorithm
  (name match → update or skip; old_name match → rename; else create;
  prune=True → deletes for unmatched current labels).
- apply_diff: fail-fast execution with progress callback. Execution
  order: renames → creates → updates → deletes. Idempotent.

Tests (tests/unit/labels_sync/test_labels_sync.py): 19 test functions.
Pure-function tests for compute_diff (6 happy + 3 rename + 3 prune +
2 edge) and apply_diff tests (4, monkey-patching github_client
functions) and 1 LabelsDiff properties test.
EOF
)"
```

---

## Task 4: `commands/labels.py` rewrite + `test_labels.py` + `test_cli_entry.py` update

**Files:**
- Rewrite: `src/gh_manage/commands/labels.py`
- Create: `tests/unit/cli/test_labels.py`
- Modify: `tests/unit/cli/test_cli_entry.py` (remove "labels" from stub parametrize lists)

- [ ] **Step 4.1: Rewrite `src/gh_manage/commands/labels.py` from stub to click group**

Full new file content (replacing the Phase 4 stub):

```python
"""gh manage labels — sync, diff, show GitHub repo labels."""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage import github_client, labels_sync
from gh_manage.config import ConfigError, load_config
from gh_manage.github_client import GhError
from gh_manage.labels_sync import LabelsDiff
from gh_manage.models.labels import LabelsConfig

DEFAULT_OWNER = "yakkuro"
DEFAULT_CONFIG_PATH = Path("config/labels.yml")

_F = TypeVar("_F", bound=Callable[..., Any])


def _parse_repo(repo: str) -> str:
    """Normalize bare name to owner/repo (Q6 C).

    Called by ALL THREE subcommands (sync, diff, show) on their `<repo>`
    argument to keep repo normalization consistent.
    """
    if "/" in repo:
        return repo
    return f"{DEFAULT_OWNER}/{repo}"


def _format_diff(diff: LabelsDiff) -> str:
    """Render LabelsDiff as plain text (Q7 A)."""
    lines: list[str] = []
    for rename in diff.renames:
        lines.append(f"~ {rename.old_name} → {rename.new_label.name}")
        lines.append(
            f"    color={rename.new_label.color}  "
            f"desc={rename.new_label.description!r}"
        )
    for create in diff.creates:
        lines.append(
            f"+ {create.label.name}  color={create.label.color}  "
            f"desc={create.label.description!r}"
        )
    for update in diff.updates:
        lines.append(
            f"≈ {update.label.name}  color={update.label.color}  "
            f"desc={update.label.description!r}"
        )
    for delete in diff.deletes:
        lines.append(f"- {delete.name}")
    return "\n".join(lines)


def _handle_errors(func: _F) -> _F:
    """Decorator: catch GhError/ConfigError and re-raise as click.ClickException.

    click.ClickException prints `Error: <msg>` to stderr and exits 1.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (GhError, ConfigError) as e:
            raise click.ClickException(str(e)) from e

    return wrapper  # type: ignore[return-value]


@click.group(help="Synchronize GitHub repo labels against config/labels.yml.")
def labels() -> None:
    """Entry group for labels subcommands."""


@labels.command(
    help=(
        "Apply config/labels.yml to a repo. Default is dry-run; "
        "pass --apply to execute."
    ),
)
@click.argument("repo")
@click.option(
    "--apply",
    "apply_flag",
    is_flag=True,
    help="Actually execute changes (default is dry-run).",
)
@click.option(
    "--prune",
    is_flag=True,
    help="Delete labels not in config (requires --apply).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Explicit dry-run; conflicts with --apply.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_CONFIG_PATH,
    help="Path to labels.yml.",
)
@_handle_errors
def sync(
    repo: str,
    apply_flag: bool,
    prune: bool,
    dry_run: bool,
    config_path: Path,
) -> None:
    if apply_flag and dry_run:
        raise click.UsageError("--apply and --dry-run are mutually exclusive.")

    qualified = _parse_repo(repo)
    config = load_config(config_path, LabelsConfig)
    current = github_client.list_labels(qualified)

    diff = labels_sync.compute_diff(current, config, prune=prune)

    if diff.is_empty:
        click.echo("No changes.")
        return

    click.echo(_format_diff(diff))

    if not apply_flag:
        click.echo(
            f"\nDry-run: {diff.total_changes} changes. "
            f"Re-run with --apply to execute."
        )
        return

    click.echo("")
    labels_sync.apply_diff(diff, qualified, progress=click.echo)
    click.echo(f"\nApplied {diff.total_changes} changes.")


@labels.command(
    "diff",
    help=(
        "Show diff between config/labels.yml and a repo. "
        "Exit 0 if no diff, 1 if diff present (git diff --quiet style)."
    ),
)
@click.argument("repo")
@click.option(
    "--prune",
    is_flag=True,
    help="Include would-be deletes in the diff.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_CONFIG_PATH,
)
@_handle_errors
def diff_cmd(repo: str, prune: bool, config_path: Path) -> None:
    qualified = _parse_repo(repo)
    config = load_config(config_path, LabelsConfig)
    current = github_client.list_labels(qualified)

    diff = labels_sync.compute_diff(current, config, prune=prune)

    if diff.is_empty:
        click.echo("No diff.")
        sys.exit(0)

    click.echo(_format_diff(diff))
    sys.exit(1)


@labels.command(
    "show",
    help="List current labels on a repo (read-only).",
)
@click.argument("repo")
@_handle_errors
def show(repo: str) -> None:
    """Show does NOT load config/labels.yml — it lists the repo's current
    state. No --config flag, no config validation. The only failure modes
    are GhError subclasses from the list_labels call."""
    qualified = _parse_repo(repo)
    current = github_client.list_labels(qualified)
    for label in sorted(current, key=lambda lb: lb.name):
        click.echo(
            f"{label.name}  color={label.color}  desc={label.description!r}"
        )
```

- [ ] **Step 4.2: Update `tests/unit/cli/test_cli_entry.py` — remove "labels" from stub parametrize lists**

The Phase 4 test file has parametrize tests that include `"labels"` as a stub case. After Task 4, `labels` is a click group, not a stub. Update the two parametrized tests by removing `"labels"` from their subcommand lists.

Use Read to get the current content, then edit these two places:

Change 1: `test_stub_subcommand_exits_with_exact_phase_message` parametrize list:

```python
# BEFORE:
@pytest.mark.parametrize(
    "subcommand",
    ["init", "apply", "labels", "protection", "drift", "issues"],
)
def test_stub_subcommand_exits_with_exact_phase_message(subcommand: str) -> None:

# AFTER:
@pytest.mark.parametrize(
    "subcommand",
    ["init", "apply", "protection", "drift", "issues"],
)
def test_stub_subcommand_exits_with_exact_phase_message(subcommand: str) -> None:
```

Change 2: `test_stub_subcommand_help_shows_help_without_firing_stub` parametrize list (same removal of `"labels"`):

```python
# BEFORE:
@pytest.mark.parametrize(
    "subcommand",
    ["init", "apply", "labels", "protection", "drift", "issues"],
)
def test_stub_subcommand_help_shows_help_without_firing_stub(subcommand: str) -> None:

# AFTER:
@pytest.mark.parametrize(
    "subcommand",
    ["init", "apply", "protection", "drift", "issues"],
)
def test_stub_subcommand_help_shows_help_without_firing_stub(subcommand: str) -> None:
```

Change 3: Remove the `"labels"` entry from the `STUB_ERROR_MESSAGES` dict:

```python
# BEFORE the dict contains:
    "labels": (
        "error: `gh manage labels` is not yet implemented — "
        "scheduled for cli/v0.2.0 (Phase 5)."
    ),

# AFTER: this key is DELETED entirely from the dict.
```

Nothing else in test_cli_entry.py changes.

- [ ] **Step 4.3: Create `tests/unit/cli/test_labels.py` with all 18 tests**

Full file content:

```python
"""Tests for commands/labels.py click subcommands."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from pytest_mock import MockerFixture

from gh_manage.cli import main
from gh_manage.commands.labels import _parse_repo
from gh_manage.github_client import GhAuthError, GhNotFoundError, Label
from gh_manage.labels_sync import (
    LabelCreate,
    LabelsDiff,
)


def _empty_diff() -> LabelsDiff:
    return LabelsDiff(renames=(), creates=(), updates=(), deletes=())


def _nonempty_diff() -> LabelsDiff:
    return LabelsDiff(
        renames=(),
        creates=(LabelCreate(label=Label("chore", "e1e7eb", "x")),),
        updates=(),
        deletes=(),
    )


def _write_minimal_config(path: Path) -> None:
    """Write a minimal valid labels.yml fixture."""
    path.write_text(
        "version: 1\n"
        "categories:\n"
        "  test:\n"
        "    description: \"t\"\n"
        "    labels:\n"
        "      - {name: \"chore\", color: \"e1e7eb\", description: \"x\"}\n",
        encoding="utf-8",
    )


# _parse_repo — parametrized (Q6 C)
@pytest.mark.parametrize(
    ("input_repo", "expected"),
    [
        ("gh-manage", "yakkuro/gh-manage"),
        ("yakkuro/gh-manage", "yakkuro/gh-manage"),
        ("other-org/other-repo", "other-org/other-repo"),
    ],
)
def test_parse_repo_normalization(input_repo: str, expected: str) -> None:
    assert _parse_repo(input_repo) == expected


# sync command
def test_sync_dry_run_by_default_prints_plan(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_nonempty_diff(),
    )
    mock_apply = mocker.patch(
        "gh_manage.commands.labels.labels_sync.apply_diff"
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["labels", "sync", "gh-manage", "--config", str(config_file)],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "Dry-run" in result.output
    mock_apply.assert_not_called()


def test_sync_with_apply_calls_apply_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_nonempty_diff(),
    )
    mock_apply = mocker.patch(
        "gh_manage.commands.labels.labels_sync.apply_diff"
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "labels",
            "sync",
            "gh-manage",
            "--apply",
            "--config",
            str(config_file),
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "Applied" in result.output
    mock_apply.assert_called_once()


def test_sync_with_apply_passes_prune_to_compute_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mock_compute = mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_empty_diff(),
    )
    mocker.patch("gh_manage.commands.labels.labels_sync.apply_diff")

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    runner.invoke(
        main,
        [
            "labels",
            "sync",
            "gh-manage",
            "--apply",
            "--prune",
            "--config",
            str(config_file),
        ],
        prog_name="gh-manage",
    )
    assert mock_compute.call_args.kwargs["prune"] is True


def test_sync_apply_and_dry_run_conflict_raises_usage_error(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "labels",
            "sync",
            "gh-manage",
            "--apply",
            "--dry-run",
            "--config",
            str(config_file),
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 2  # click UsageError


def test_sync_bare_repo_prepends_yakkuro(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mock_list = mocker.patch(
        "gh_manage.github_client.list_labels", return_value=[]
    )
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_empty_diff(),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    runner.invoke(
        main,
        ["labels", "sync", "gh-manage", "--config", str(config_file)],
        prog_name="gh-manage",
    )
    mock_list.assert_called_once_with("yakkuro/gh-manage")


def test_sync_owner_slash_repo_passes_through(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mock_list = mocker.patch(
        "gh_manage.github_client.list_labels", return_value=[]
    )
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_empty_diff(),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    runner.invoke(
        main,
        [
            "labels",
            "sync",
            "other-org/other-repo",
            "--config",
            str(config_file),
        ],
        prog_name="gh-manage",
    )
    mock_list.assert_called_once_with("other-org/other-repo")


def test_sync_empty_diff_prints_no_changes(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_empty_diff(),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["labels", "sync", "gh-manage", "--config", str(config_file)],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "No changes" in result.output


def test_sync_gh_auth_error_displays_actionable_message(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch(
        "gh_manage.github_client.list_labels",
        side_effect=GhAuthError("Run `gh auth login` and try again."),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["labels", "sync", "gh-manage", "--config", str(config_file)],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "gh auth login" in result.output


def test_sync_config_not_found_returns_click_path_error() -> None:
    """click.Path(exists=True) rejects nonexistent paths at arg parse time,
    returning exit 2 (usage error) not 1 (ConfigError)."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "labels",
            "sync",
            "gh-manage",
            "--config",
            "/nonexistent/labels.yml",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 2


# diff command
def test_diff_exit_zero_when_no_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_empty_diff(),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["labels", "diff", "gh-manage", "--config", str(config_file)],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "No diff" in result.output


def test_diff_exit_one_when_diff_present(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_nonempty_diff(),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["labels", "diff", "gh-manage", "--config", str(config_file)],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "chore" in result.output


def test_diff_prune_flag_passed_to_compute_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mock_compute = mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_empty_diff(),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    runner.invoke(
        main,
        [
            "labels",
            "diff",
            "gh-manage",
            "--prune",
            "--config",
            str(config_file),
        ],
        prog_name="gh-manage",
    )
    assert mock_compute.call_args.kwargs["prune"] is True


# show command
def test_show_lists_current_labels_sorted(mocker: MockerFixture) -> None:
    mocker.patch(
        "gh_manage.github_client.list_labels",
        return_value=[
            Label(name="zebra", color="000000", description="z"),
            Label(name="alpha", color="ffffff", description="a"),
        ],
    )
    runner = CliRunner()
    result = runner.invoke(
        main, ["labels", "show", "gh-manage"], prog_name="gh-manage"
    )
    assert result.exit_code == 0
    # alpha appears before zebra
    alpha_idx = result.output.index("alpha")
    zebra_idx = result.output.index("zebra")
    assert alpha_idx < zebra_idx


def test_show_does_not_load_config(mocker: MockerFixture) -> None:
    """show should succeed without any config/labels.yml present."""
    mocker.patch(
        "gh_manage.github_client.list_labels",
        return_value=[Label(name="bug", color="d73a4a", description="x")],
    )
    mock_load = mocker.patch("gh_manage.commands.labels.load_config")
    runner = CliRunner()
    result = runner.invoke(
        main, ["labels", "show", "gh-manage"], prog_name="gh-manage"
    )
    assert result.exit_code == 0
    mock_load.assert_not_called()


def test_show_gh_not_found_displays_actionable_message(
    mocker: MockerFixture,
) -> None:
    mocker.patch(
        "gh_manage.github_client.list_labels",
        side_effect=GhNotFoundError(
            "GitHub API returned 404 for repos/foo/bar/labels. "
            "Check the resource name and your auth status with `gh auth status`."
        ),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["labels", "show", "nonexistent"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "gh auth status" in result.output
```

- [ ] **Step 4.4: Run the full Phase 5 test suite to verify everything is green**

```bash
uv run pytest -v
```

Expected test count: 2 sanity + 13 config (12 Phase 4 + 1 new from Task 1) + 15 CLI (17 Phase 4 - 2 "labels" parametrized cases removed) + 18 github_client + 19 labels_sync + 18 labels = **85 tests PASS**.

Note: After removing `"labels"` from the 2 parametrize lists, the CLI test count drops by 2 (since labels was a parametrize case in BOTH `test_stub_subcommand_exits_with_exact_phase_message` and `test_stub_subcommand_help_shows_help_without_firing_stub`). Phase 4 had 17 CLI tests (3 + 6 + 1 + 6 + 1 subprocess regression). After removing labels from the 2 parametrize lists: 3 + 5 + 1 + 5 + 1 = 15 CLI tests. Plus the 18 new labels tests → 33 CLI tests total.

Corrected total: 2 sanity + 13 config + 33 CLI + 18 github_client + 19 labels_sync = **85 tests**.

If any test fails, fix the implementation and re-run.

- [ ] **Step 4.5: Manual smoke test — `gh-manage labels --help` shows the group**

```bash
./gh-manage labels --help
```

Expected: click help for the group with `sync`, `diff`, `show` subcommands listed. Exit 0.

```bash
./gh-manage labels
```

Expected: click shows the group help (no subcommand provided) or usage error. Note the exit code for later reference.

```bash
./gh-manage labels sync --help
```

Expected: `Usage: gh-manage labels sync [OPTIONS] REPO` with all flags documented. Exit 0.

These smoke tests are informational; they're not AC items yet (the AC comes in Task 7 after config/labels.yml exists).

- [ ] **Step 4.6: mypy + ruff clean**

```bash
uv run --with "mypy==1.12.0" mypy src
uv run ruff check .
uv run ruff format --check .
```

Expected: all clean.

- [ ] **Step 4.7: Commit**

```bash
git add src/gh_manage/commands/labels.py tests/unit/cli/test_labels.py \
        tests/unit/cli/test_cli_entry.py
git commit -m "$(cat <<'EOF'
feat(phase-5): rewrite commands/labels.py as click group with 3 subcommands

- src/gh_manage/commands/labels.py: replaced Phase 4 stub with click
  group containing sync/diff_cmd/show subcommands. Each uses the
  @_handle_errors decorator to catch GhError/ConfigError and convert
  to click.ClickException. _parse_repo normalizes bare names to
  yakkuro/<name>. _format_diff renders LabelsDiff as plain text.
- tests/unit/cli/test_labels.py: 18 tests covering repo normalization
  (parametrized 3x), sync dry-run and --apply, --apply + --dry-run
  conflict, bare vs qualified repo, empty diff, GhAuthError display,
  nonexistent config path, diff exit code 0/1, --prune flag, show
  sorted output, show skipping config load, show 404 display.
- tests/unit/cli/test_cli_entry.py: removed "labels" from stub
  parametrize lists since labels is no longer a stub. STUB_ERROR_MESSAGES
  dict updated to remove the "labels" entry.

cli.py does NOT need changes: main.add_command(labels_cmd.labels) still
works because labels_cmd.labels is now a click group instead of a stub,
and add_command accepts both.
EOF
)"
```

---

## Task 5: `config/labels.yml`

**Files:**
- Create: `config/labels.yml`

- [ ] **Step 5.1: Create `config/labels.yml`**

Full file content:

```yaml
version: 1
categories:
  type:
    description: "Conventional Commits type labels"
    labels:
      - { name: "fix",      old_name: "bug",           color: "d73a4a", description: "Bug fix (fix:)" }
      - { name: "feat",     old_name: "enhancement",   color: "a2eeef", description: "New feature (feat:)" }
      - { name: "docs",     old_name: "documentation", color: "0075ca", description: "Documentation changes (docs:)" }
      - { name: "chore",    color: "e1e7eb", description: "Maintenance / housekeeping (chore:)" }
      - { name: "refactor", color: "ffd866", description: "Refactor without behavior change (refactor:)" }
      - { name: "test",     color: "c5def5", description: "Test additions / changes (test:)" }
      - { name: "ci",       color: "b4a5ff", description: "CI/CD changes (ci:)" }
      - { name: "perf",     color: "5319e7", description: "Performance improvements (perf:)" }
  meta:
    description: "Meta / status labels"
    labels:
      - { name: "duplicate",        color: "cfd3d7", description: "This issue or PR already exists" }
      - { name: "good first issue", color: "7057ff", description: "Good for newcomers" }
      - { name: "help wanted",      color: "008672", description: "Extra attention is needed" }
      - { name: "invalid",          color: "e4e669", description: "Not actionable" }
      - { name: "question",         color: "d876e3", description: "Further information is requested" }
      - { name: "wontfix",          color: "ffffff", description: "This will not be worked on" }
```

- [ ] **Step 5.2: Verify the config validates against `LabelsConfig`**

```bash
uv run python -c "from pathlib import Path; from gh_manage.config import load_config; from gh_manage.models.labels import LabelsConfig; c = load_config(Path('config/labels.yml'), LabelsConfig); print(f'Loaded {sum(len(cat.labels) for cat in c.categories.values())} labels across {len(c.categories)} categories')"
```

Expected output: `Loaded 14 labels across 2 categories`

- [ ] **Step 5.3: Commit**

```bash
git add config/labels.yml
git commit -m "$(cat <<'EOF'
feat(phase-5): add config/labels.yml with 14 gh-manage labels

Source of truth for gh-manage's repository labels. Two categories:

- type: 8 Conventional Commits labels. Three use old_name to rename
  from GitHub defaults:
    bug          → fix  (keeps d73a4a color)
    enhancement  → feat (keeps a2eeef color)
    documentation → docs (keeps 0075ca color)
  Five new labels: chore, refactor, test, ci, perf.

- meta: 6 labels matching GitHub's current defaults exactly
  (duplicate, good first issue, help wanted, invalid, question,
  wontfix) so they're noops during self-dogfood.

Self-dogfood diff against gh-manage's current labels (predicted):
  3 renames + 5 creates + 0 updates + 0 deletes = 8 changes

Verified: the file validates against LabelsConfig via load_config.
EOF
)"
```

---

## Task 6: Documentation — `CHANGELOG-cli.md` [0.2.0] + `docs/usage/cli.md` labels section

**Files:**
- Modify: `CHANGELOG-cli.md`
- Modify: `docs/usage/cli.md`

- [ ] **Step 6.1: Add `[0.2.0] - 2026-04-11` entry to `CHANGELOG-cli.md`**

Insert the new entry ABOVE the existing `## [0.1.0] - 2026-04-10` section. The `## [Unreleased]` section remains with `_Nothing yet._` content. The new entry text:

```markdown
## [0.2.0] - 2026-04-11

First real domain command on the CLI track: `gh manage labels sync/diff/show`. Phase 5 milestone. Self-dogfooded by applying gh-manage's own Conventional-Commits-aligned labels via `gh manage labels sync gh-manage --apply` (3 renames + 5 creates).

### Added

- **`src/gh_manage/github_client.py`** — subprocess transport for `gh` and `gh api` with a 6-subclass `GhError` hierarchy (`GhNotInstalledError`, `GhAuthError`, `GhNotFoundError`, `GhPermissionError`, `GhRateLimitError`, `GhAPIError`). Every error message includes actionable next steps. Label CRUD helpers: `list_labels` (auto-paginated), `create_label`, `update_label` (handles rename via `new_name` body field), `delete_label`. Colors are normalized to lowercase; null descriptions are normalized to empty strings.
- **`src/gh_manage/labels_sync.py`** — pure-function diff computation (`compute_diff`) and application (`apply_diff`). Typed `LabelsDiff` dataclass with `LabelRename`, `LabelCreate`, `LabelUpdate`, `LabelDelete` buckets. Rename detection via explicit `old_name` field on `LabelSpec`. Fail-fast execution order: renames → creates → updates → deletes.
- **`src/gh_manage/commands/labels.py`** — click group with 3 subcommands: `sync` (default dry-run, `--apply` to execute, `--prune` to include deletes), `diff` (exit 0 if no diff, 1 if diff present, `git diff --quiet` style), `show` (read-only). `<repo>` accepts both bare name (`gh-manage` → `yakkuro/gh-manage`) and qualified (`yakkuro/gh-manage`, `other-org/other-repo`). Unified error handling via `_handle_errors` decorator that converts `GhError`/`ConfigError` to `click.ClickException`.
- **`config/labels.yml`** — gh-manage's own label definitions. Type category with 8 Conventional Commits labels (3 using `old_name` to rename from GitHub defaults: `bug`→`fix`, `enhancement`→`feat`, `documentation`→`docs`) and meta category with 6 preserved GitHub default labels.
- **`tests/unit/github_client/test_github_client.py`** — 18 tests with `subprocess.run` mocked: 9 happy path (list/create/update/delete + normalization), 6 error classification (parametrized over stderr patterns), 1 FileNotFoundError → GhNotInstalledError, 2 actionable message spot checks.
- **`tests/unit/labels_sync/test_labels_sync.py`** — 19 pure-function tests covering `compute_diff` (6 happy path including case-insensitive color and None/"" description, 3 rename, 3 prune, 2 edge case) and `apply_diff` (4 execution order + progress + fail-fast tests) and 1 `LabelsDiff` properties test.
- **`tests/unit/cli/test_labels.py`** — 18 CliRunner tests covering repo normalization (parametrized 3×), sync (9 cases), diff (3 cases), show (3 cases).
- **`tests/fixtures/config/labels-valid-with-rename.yml`** — new fixture with `old_name` field used by `test_load_config.py` to verify backward-compatible Phase 5 schema extension.

### Changed

- **`src/gh_manage/models/labels.py`** — `LabelSpec` gains optional `old_name: str | None = None` field for rename support (Q3 A). Backward compatible: existing Phase 4 fixtures validate unchanged.
- **`src/gh_manage/__init__.py`** — `__version__` bumped from `"0.1.0"` to `"0.2.0"`.
- **`pyproject.toml`** — `version` bumped from `"0.1.0"` to `"0.2.0"`. No new dependencies.
- **`tests/test_sanity.py`** — expected `__version__` bumped to `"0.2.0"`.
- **`tests/unit/cli/test_cli_entry.py`** — removed `"labels"` from the 2 stub parametrize lists and from `STUB_ERROR_MESSAGES` dict, since `labels` is no longer a stub. Remaining stubs: `init`, `apply`, `protection`, `drift`, `issues`.
- **`tests/unit/config/test_load_config.py`** — +1 test (`test_load_labels_config_with_old_name_field`) asserting the new `labels-valid-with-rename.yml` fixture loads and the `old_name` field is preserved.
- **`docs/usage/cli.md`** — new `## labels` section with `sync`/`diff`/`show` usage examples, self-dogfood walkthrough, and error message examples. Roadmap table updated to mark `labels` as shipped in `cli/v0.2.0`.

### Known limitations

- **No `--format json`** — diff output is plain text only. Phase 5.1 may add JSON via a `.render()` method on `LabelsDiff` (structure is already typed).
- **No batch mode** — single-repo only. `labels sync --all` against a `repos.yml` requires Phase 6's `repos.yml` schema.
- **No rate-limit retry** — `GhRateLimitError` is raised immediately. Scheduled runs may add retry in Phase 8.
- **No rollback on partial failure** — operations are idempotent; re-running picks up remaining work.
- **No heuristic rename detection** — only explicit `old_name` triggers rename. Renaming without `old_name` becomes create + delete.
- **`yakkuro` is the hardcoded default owner** — can be overridden by passing `<owner>/<repo>`. No env var override.

[0.2.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v0.2.0
```

Also update the footer link block — add the `[0.2.0]` comparison link:

```markdown
[Unreleased]: https://github.com/yakkuro/gh-manage/compare/cli/v0.2.0...HEAD
[0.2.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v0.2.0
[0.1.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v0.1.0
```

(The `[Unreleased]` line changes from comparing to `cli/v0.1.0...HEAD` to comparing to `cli/v0.2.0...HEAD`.)

- [ ] **Step 6.2: Update `docs/usage/cli.md` with a `labels` section**

Find the existing `## Subcommand roadmap` table in `docs/usage/cli.md`. Update it: mark `labels` as shipped in `cli/v0.2.0` (remove the "Planned version" hint for it, or change to "Available in cli/v0.2.0"). Specifically, change the `labels` row:

```markdown
| `labels` | **cli/v0.2.0** ✅ | Phase 5 | Synchronize GitHub repo labels against `config/labels.yml` (sync/diff/show subcommands) |
```

Then insert a new `## labels` section BEFORE the `## Uninstalling` section. Full section content:

```markdown
## labels

Shipped in `cli/v0.2.0`. Synchronizes GitHub repository labels against `config/labels.yml` (the source of truth).

### Commands

- **`gh manage labels sync <repo>`** — Compute and optionally apply label changes.
  - Default: dry-run (shows the plan, exits 0)
  - `--apply` — execute the plan
  - `--prune` — include deletes in the plan (labels not in config get deleted; requires `--apply` to take effect)
  - `--dry-run` — explicit dry-run (conflicts with `--apply`)
  - `--config PATH` — path to labels.yml (default: `config/labels.yml`)

- **`gh manage labels diff <repo>`** — Show diff without applying.
  - Exits 0 if no diff, 1 if diff present (`git diff --quiet` style)
  - `--prune` — include would-be deletes in diff
  - `--config PATH` — same as sync

- **`gh manage labels show <repo>`** — List current labels on the repo (read-only). No config loaded.

### Repo argument format

Both bare name and `owner/repo` are accepted:

```bash
gh manage labels sync gh-manage               # expands to yakkuro/gh-manage
gh manage labels sync yakkuro/gh-manage       # explicit
gh manage labels sync other-org/other-repo    # non-yakkuro org
```

### Walkthrough: gh-manage self-dogfood

```bash
# 1. Dry-run: see the planned changes
$ gh manage labels diff gh-manage
~ bug → fix
    color=d73a4a  desc='Bug fix (fix:)'
~ documentation → docs
    color=0075ca  desc='Documentation changes (docs:)'
~ enhancement → feat
    color=a2eeef  desc='New feature (feat:)'
+ chore  color=e1e7eb  desc='Maintenance / housekeeping (chore:)'
+ refactor  color=ffd866  desc='Refactor without behavior change (refactor:)'
+ test  color=c5def5  desc='Test additions / changes (test:)'
+ ci  color=b4a5ff  desc='CI/CD changes (ci:)'
+ perf  color=5319e7  desc='Performance improvements (perf:)'
# Exit code: 1 (diff present)

# 2. Apply the changes
$ gh manage labels sync gh-manage --apply
# Same diff output, followed by progress lines and "Applied 8 changes."

# 3. Verify idempotency
$ gh manage labels diff gh-manage
No diff.
# Exit code: 0

# 4. Show the final state
$ gh manage labels show gh-manage
chore  color=e1e7eb  desc='Maintenance / housekeeping (chore:)'
ci  color=b4a5ff  desc='CI/CD changes (ci:)'
docs  color=0075ca  desc='Documentation changes (docs:)'
duplicate  color=cfd3d7  desc='This issue or PR already exists'
feat  color=a2eeef  desc='New feature (feat:)'
fix  color=d73a4a  desc='Bug fix (fix:)'
good first issue  color=7057ff  desc='Good for newcomers'
help wanted  color=008672  desc='Extra attention is needed'
invalid  color=e4e669  desc='Not actionable'
perf  color=5319e7  desc='Performance improvements (perf:)'
question  color=d876e3  desc='Further information is requested'
refactor  color=ffd866  desc='Refactor without behavior change (refactor:)'
test  color=c5def5  desc='Test additions / changes (test:)'
wontfix  color=ffffff  desc='This will not be worked on'
```

### Error messages

All error messages include actionable remediation. Examples:

**Unauthenticated:**
```
$ gh manage labels sync gh-manage
Error: The `gh` CLI is not authenticated or the token is invalid. Run `gh auth login` (or `gh auth refresh`) and try again.
# Exit code: 1
```

**Nonexistent repo:**
```
$ gh manage labels sync yakkuro/does-not-exist
Error: GitHub API returned 404 for repos/yakkuro/does-not-exist/labels. Check the resource name and your auth status with `gh auth status`.
# Exit code: 1
```

**Insufficient scope:**
```
$ gh manage labels sync yakkuro/gh-manage --apply
Error: Permission denied on repos/yakkuro/gh-manage/labels. Your `gh` token may lack the required scope. Run `gh auth refresh -s repo` to add `repo` scope.
# Exit code: 1
```
```

- [ ] **Step 6.3: Commit**

```bash
git add CHANGELOG-cli.md docs/usage/cli.md
git commit -m "$(cat <<'EOF'
docs(phase-5): add CHANGELOG-cli.md [0.2.0] + labels section in docs/usage/cli.md

- CHANGELOG-cli.md: new [0.2.0] - 2026-04-11 entry documenting all
  Phase 5 additions (github_client.py, labels_sync.py,
  commands/labels.py rewrite, config/labels.yml) and modifications
  (LabelSpec.old_name, version bump, test file adjustments). Known
  limitations section notes deferred features (JSON output, batch
  mode, rate-limit retry).
- docs/usage/cli.md: new "labels" section with sync/diff/show usage,
  repo argument formats, self-dogfood walkthrough showing the 3
  renames + 5 creates for gh-manage's own labels, and error message
  examples for auth/404/permission cases. Roadmap table updated to
  mark labels as shipped in cli/v0.2.0.
EOF
)"
```

---

## Task 7: Final verification + PR (no commits)

- [ ] **Step 7.1: Run `ruff check` on the full repo**

```bash
uv run ruff check .
```

Expected: `All checks passed!`. If violations are reported in Phase 5 files, fix them before proceeding (usually unused imports or line length).

- [ ] **Step 7.2: Run `ruff format --check`**

```bash
uv run ruff format --check .
```

Expected: clean. If formatting differs, run `uv run ruff format .` and commit as `style(phase-5): apply ruff format`.

- [ ] **Step 7.3: Run `mypy` via the reusable gate's exact invocation**

```bash
uv run --with "mypy==1.12.0" mypy src
```

Expected: `Success: no issues found in X source files`. If mypy reports errors in Phase 5 code, fix them. Do NOT add `# type: ignore` without justification.

- [ ] **Step 7.4: Run the full test suite**

```bash
uv run pytest -v
```

Expected: **85 tests PASS** (2 sanity + 13 config + 33 CLI + 18 github_client + 19 labels_sync).

- [ ] **Step 7.5: Check coverage is ≥ 90% on new modules**

```bash
uv run pytest --cov=gh_manage.github_client --cov=gh_manage.labels_sync --cov=gh_manage.commands.labels --cov-report=term-missing
```

Expected: all 3 modules report ≥ 90% line coverage. If any module is below, add targeted tests for uncovered lines before proceeding.

- [ ] **Step 7.6: End-to-end smoke — `gh manage labels --help` with the group**

```bash
./gh-manage labels --help
```

Expected: click group help showing `sync`, `diff`, `show` subcommands. Exit 0.

```bash
./gh-manage labels diff --help
```

Expected: diff subcommand help. Exit 0.

- [ ] **Step 7.7: Self-dogfood — run the 5-step walkthrough (MANUAL, captured into PR description)**

WARNING: Steps 2 (the `--apply`) will actually modify the gh-manage repository's labels. Only run this if the branch is ready to be merged.

If you want to preview WITHOUT applying, run only steps 1, 3, 4 (the diff + show commands; they're read-only).

```bash
# Capture the full walkthrough to a file for the PR description
{
  echo "## Phase 5 self-dogfood walkthrough"
  echo
  echo '### 1. Before state'
  echo '$ ./gh-manage labels show gh-manage'
  ./gh-manage labels show gh-manage
  echo
  echo '### 2. Pre-sync diff (predicted: 3 renames + 5 creates)'
  echo '$ ./gh-manage labels diff gh-manage'
  ./gh-manage labels diff gh-manage
  echo "  (exit $?)"
  echo
  echo '### 3. Dry-run summary'
  echo '$ ./gh-manage labels sync gh-manage'
  ./gh-manage labels sync gh-manage
  echo "  (exit $?)"
  echo
  echo '### 4. APPLY — this modifies the repo'
  echo '$ ./gh-manage labels sync gh-manage --apply'
  ./gh-manage labels sync gh-manage --apply
  echo "  (exit $?)"
  echo
  echo '### 5. Idempotency check'
  echo '$ ./gh-manage labels diff gh-manage'
  ./gh-manage labels diff gh-manage
  echo "  (exit $?)"
  echo
  echo '### 6. After state'
  echo '$ ./gh-manage labels show gh-manage'
  ./gh-manage labels show gh-manage
} > /tmp/phase-5-dogfood.txt

cat /tmp/phase-5-dogfood.txt
```

Expected:
- Step 1: lists 9 GitHub default labels (bug, documentation, duplicate, enhancement, good first issue, help wanted, invalid, question, wontfix)
- Step 2: diff shows 3 renames + 5 creates, exit 1
- Step 3: same diff output + "Dry-run: 8 changes. Re-run with --apply to execute.", exit 0
- Step 4: progress lines for each operation, then "Applied 8 changes.", exit 0
- Step 5: "No diff.", exit 0
- Step 6: lists 14 labels sorted (chore, ci, docs, duplicate, feat, fix, good first issue, help wanted, invalid, perf, question, refactor, test, wontfix)

Keep `/tmp/phase-5-dogfood.txt` — it goes in the PR description.

- [ ] **Step 7.8: Push the branch**

```bash
git push -u origin feat/phase-5-labels-sync
```

Expected: fast-forward push. If a pre-push hook blocks, read the message and fix — do NOT `--no-verify`.

- [ ] **Step 7.9: Confirm CI is running**

```bash
gh run list --branch feat/phase-5-labels-sync --limit 3
```

Expected: at least one workflow run queued or in_progress.

- [ ] **Step 7.10: Open the PR**

```bash
gh pr create --title "feat: Phase 5 — labels sync (cli/v0.2.0)" --body "$(cat <<'EOF'
## Summary

Ship `cli/v0.2.0` — the first real domain command on gh-manage's CLI tag track.

- `src/gh_manage/github_client.py` — generic `gh api` transport + label CRUD + 6-subclass `GhError` hierarchy with actionable messages
- `src/gh_manage/labels_sync.py` — pure-function `compute_diff` + `apply_diff` with typed `LabelsDiff` dataclass, rename via explicit `old_name`
- `src/gh_manage/commands/labels.py` — click group with 3 subcommands (`sync`, `diff`, `show`). Default dry-run, `--apply` to execute, `--prune` to include deletes. Accepts bare repo name or `owner/repo`.
- `src/gh_manage/models/labels.py` — `LabelSpec` gains optional `old_name` field (Phase 5 schema extension)
- `config/labels.yml` — gh-manage's own 14 labels (8 type + 6 meta). 3 renames + 5 creates against GitHub defaults.
- 54 new tests (18 github_client + 19 labels_sync + 18 commands/labels + 1 config backward-compat) → **85 tests total**
- `CHANGELOG-cli.md [0.2.0]` + `docs/usage/cli.md` labels section with self-dogfood walkthrough
- Zero new dependencies

## Design spec

`docs/specs/2026-04-11-phase-5-labels-sync-design.md` (1175 lines, 8 brainstorming Qs, 1 round of spec-critique with 5 accepted + 4 rejected findings documented).

## Implementation plan

`docs/plans/2026-04-11-phase-5-labels-sync.md` (7 tasks: bootstrap → github_client → labels_sync → commands/labels → config → docs → verification).

## Scope (intentionally limited)

- No `--format json` (deferred to Phase 5.1, internal `LabelsDiff` is already typed)
- No batch mode (`labels sync --all` waits for Phase 6's `repos.yml`)
- No rate-limit retry (deferred to Phase 8)
- No rollback on partial failure (operations are idempotent; re-run picks up remaining work)
- No heuristic rename detection (only explicit `old_name` triggers rename)
- `yakkuro` is the hardcoded default owner

## Local verification

- `uv run ruff check .` — clean
- `uv run ruff format --check .` — clean
- `uv run --with "mypy==1.12.0" mypy src` — clean
- `uv run pytest -v` — 85 passed (2 sanity + 13 config + 33 CLI + 18 github_client + 19 labels_sync)
- Coverage on new modules ≥ 90% (github_client, labels_sync, commands/labels)

## Self-dogfood walkthrough

<details>
<summary>Full output of the 5-step walkthrough against yakkuro/gh-manage</summary>

(paste the contents of /tmp/phase-5-dogfood.txt here)

</details>

Summary:
- Before: 9 GitHub default labels
- 3 renames: `bug` → `fix`, `documentation` → `docs`, `enhancement` → `feat`
- 5 creates: `chore`, `refactor`, `test`, `ci`, `perf`
- 6 noop: `duplicate`, `good first issue`, `help wanted`, `invalid`, `question`, `wontfix`
- After: 14 labels
- Idempotency: re-running `labels diff` shows `No diff.` (exit 0)

## Test plan (post-merge)

- [ ] 4-reviewer cross-agent review (Codex + superpowers:code-reviewer + silent-failure-hunter + code-reviewer)
- [ ] Merge to main after CRITICAL/HIGH findings resolved
- [ ] Tag `cli/v0.2.0` on main
- [ ] Create GitHub release `cli/v0.2.0` with `--latest=false` (reusable track's `v0.2.1` stays `latest`)
- [ ] Smoke test `gh extension install yakkuro/gh-manage` → `gh manage labels show gh-manage` on a clean environment
- [ ] Post-Phase-5 light review/refactor checkpoint (Task #54)

Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

Expected: PR URL printed. Capture it for the 4-reviewer review task.

- [ ] **Step 7.11: Hand off to Task #52 (4-reviewer review)**

Phase 5 implementation is complete, the PR is open, CI is running. Next is the 4-reviewer cross-agent review per `workflow-review.md`.

---

## Self-Review

Completed against the spec (`docs/specs/2026-04-11-phase-5-labels-sync-design.md`).

**1. Spec coverage:**
- All 17 AC items map to tasks:
  - AC1-AC6 (live CLI behavior): Task 5 (config) + Task 7 (smoke test)
  - AC7 (usage error for `--apply --dry-run`): Task 4 (CLI test)
  - AC8-AC9 (error messages): Task 2 (github_client error hierarchy) + Task 4 (error display via _handle_errors)
  - AC10-AC12 (tests pass): Tasks 2, 3, 4
  - AC13 (coverage ≥ 90%): Task 7 verification
  - AC14-AC15 (changelog + docs): Task 6
  - AC16-AC17 (release + review): Tasks #52, #53 (outside this plan)
- All Components in the spec have corresponding create/modify steps with full code shown
- Error handling requirements (GhError hierarchy, from e chaining, actionable messages): Task 2 code
- Test strategy (Q4 B 2-layer mock): Tasks 2 (subprocess mocked), 3 (github_client functions monkey-patched), 4 (labels_sync functions monkey-patched + CliRunner)
- Architecture (Tier 2, 3-layer): enforced by Tasks 2/3/4 keeping each module focused
- Phase 4 stub removal + test adjustment: Task 4 step 4.2

**2. Placeholder scan:**
- No "TBD", "TODO", "implement later"
- No "add error handling" / "handle edge cases"
- Every test and function body is shown in full
- No "similar to Task N"
- Every `Step X.Y` has a code block or exact command

**3. Type consistency:**
- `Label(name, color, description)` — same signature in github_client.py, labels_sync.py, test_labels_sync.py, test_labels.py
- `LabelsConfig` / `LabelSpec` / `CategorySpec` — consistent field names across Task 1 (schema) and Tasks 3, 4 (usage in tests)
- `compute_diff(current, desired, *, prune)` — same signature in labels_sync.py and its callers
- `apply_diff(diff, repo, *, progress)` — same signature in labels_sync.py and commands/labels.py
- `LabelRename(old_name, new_label)` / `LabelCreate(label)` / `LabelUpdate(label)` / `LabelDelete(name)` — consistent across labels_sync.py and test files
- `GhError` subclass names (`GhNotInstalledError`, `GhAuthError`, `GhNotFoundError`, `GhPermissionError`, `GhRateLimitError`, `GhAPIError`) consistent across github_client.py, labels_sync tests, commands tests

No issues found. Plan is ready for execution.

---

## Execution handoff

**Plan complete and saved to `docs/plans/2026-04-11-phase-5-labels-sync.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — Per `feedback_execution_mode.md`, this is the default for non-trivial plans. Fresh subagent per task, two-stage review between tasks (spec compliance + code quality), fast iteration.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans` with batch execution and checkpoints.

Proceeding with **Subagent-Driven** per standing preference unless the user redirects.
