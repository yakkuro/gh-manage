# Extract Shared Command Helpers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract duplicated helpers from 4 command modules into `commands/_shared.py`, eliminating security-critical code duplication.

**Architecture:** Create a single `_shared.py` module with all shared helpers, then replace each command module's private copies with imports. Work in TDD style: write a test for `_shared.py` first, then extract, then verify existing tests still pass.

**Tech Stack:** Python 3.12, click 8.x, pydantic v2, pytest 8

**Spec:** `docs/specs/2026-04-16-extract-shared-helpers-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/gh_manage/commands/_shared.py` | All shared helpers |
| Create | `tests/unit/commands/test_shared.py` | Tests for `_shared.py` |
| Modify | `src/gh_manage/commands/__init__.py` | No change needed (empty) |
| Modify | `src/gh_manage/commands/init.py` | Remove duplicates, import from `_shared` |
| Modify | `src/gh_manage/commands/apply.py` | Remove duplicates, import from `_shared` |
| Modify | `src/gh_manage/commands/drift.py` | Remove duplicates, import from `_shared` |
| Modify | `src/gh_manage/commands/protection.py` | Remove duplicates, import from `_shared` |

---

## Task 1: Create `_shared.py` with tests

**Files:**
- Create: `src/gh_manage/commands/_shared.py`
- Create: `tests/unit/commands/test_shared.py`

- [ ] **Step 1: Write failing tests for `_shared.py`**

Create `tests/unit/commands/test_shared.py`:

```python
"""Tests for commands/_shared.py — shared CLI helpers."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import click
import pytest

from gh_manage.commands._shared import (
    VALID_PROFILE_NAME_RE,
    format_files_diff,
    handle_errors,
    resolve_backup_dir,
    resolve_branch_protection_path,
    resolve_default_labels_path,
    resolve_profile_path,
    resolve_repos_path,
    resolve_templates_root,
)
from gh_manage.config import ConfigFileNotFoundError
from gh_manage.github_client import GhError
from gh_manage.profile_sync import ProfileFilesDiff


class TestValidProfileNameRe:
    def test_accepts_simple_name(self) -> None:
        assert VALID_PROFILE_NAME_RE.match("python-service")

    def test_rejects_path_traversal(self) -> None:
        assert not VALID_PROFILE_NAME_RE.match("../etc/passwd")

    def test_rejects_leading_dot(self) -> None:
        assert not VALID_PROFILE_NAME_RE.match(".hidden")

    def test_rejects_empty(self) -> None:
        assert not VALID_PROFILE_NAME_RE.match("")


class TestResolveProfilePath:
    def test_valid_profile_resolves(self) -> None:
        path = resolve_profile_path("python-service")
        assert path.is_file()
        assert path.name == "python-service.yml"

    def test_invalid_name_raises(self) -> None:
        with pytest.raises(ConfigFileNotFoundError, match="Invalid profile name"):
            resolve_profile_path("../../etc/passwd")

    def test_nonexistent_profile_raises(self) -> None:
        with pytest.raises(ConfigFileNotFoundError, match="Profile not found"):
            resolve_profile_path("nonexistent-profile-xyz")


class TestResolvePathHelpers:
    def test_templates_root_is_directory(self) -> None:
        assert resolve_templates_root().is_dir()

    def test_labels_path_is_file(self) -> None:
        assert resolve_default_labels_path().is_file()

    def test_branch_protection_path_is_file(self) -> None:
        assert resolve_branch_protection_path().is_file()

    def test_repos_path_is_file(self) -> None:
        assert resolve_repos_path().is_file()

    def test_backup_dir_is_under_home(self) -> None:
        path = resolve_backup_dir()
        assert ".gh-manage" in str(path)
        assert "backups" in str(path)


class TestHandleErrors:
    def test_gh_error_becomes_click_exception(self) -> None:
        @handle_errors
        def failing() -> None:
            raise GhError("test gh error")

        with pytest.raises(click.ClickException, match="test gh error"):
            failing()

    def test_no_error_passes_through(self) -> None:
        @handle_errors
        def succeeding() -> str:
            return "ok"

        assert succeeding() == "ok"


class TestFormatFilesDiff:
    def test_empty_diff(self) -> None:
        diff = ProfileFilesDiff(creates=(), overwrites=(), skipped=(), noops=())
        result = format_files_diff(diff)
        assert "no file changes" in result

    def test_creates_shown(self) -> None:
        from gh_manage.profile_sync import FileCreate

        diff = ProfileFilesDiff(
            creates=(FileCreate(source=Path("/s"), dest=Path("/d/file.yml")),),
            overwrites=(),
            skipped=(),
            noops=(),
        )
        result = format_files_diff(diff)
        assert "+ create" in result
        assert "file.yml" in result
```

- [ ] **Step 2: Run tests — confirm RED**

```bash
uv run pytest tests/unit/commands/test_shared.py -v
```

Expected: `ModuleNotFoundError: No module named 'gh_manage.commands._shared'`

- [ ] **Step 3: Create `_shared.py` with all helpers**

Create `src/gh_manage/commands/_shared.py`:

```python
"""Shared CLI helpers for gh-manage commands.

Extracted from commands/init.py, apply.py, drift.py, protection.py to
eliminate security-critical code duplication (Issue #38). The path
traversal defense in resolve_profile_path is load-bearing — having it
in one place ensures a security fix is applied once, not in 4 files.

This module is internal to the commands package (leading underscore).
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage.config import ConfigFileNotFoundError
from gh_manage.drift_sync import DriftError
from gh_manage.git_cli import GitError
from gh_manage.github_client import GhError
from gh_manage.profile_sync import ProfileError, ProfileFilesDiff
from gh_manage.protection_sync import ProtectionError

_F = TypeVar("_F", bound=Callable[..., Any])

VALID_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_DOMAIN_ERRORS = (
    GhError,
    ConfigError,
    GitError,
    ProfileError,
    ProtectionError,
    DriftError,
)


def handle_errors(func: _F) -> _F:
    """Decorator: catch domain errors and re-raise as click.ClickException.

    Uses the union of all domain exception types so every command module
    can share one decorator without maintaining per-command exception lists.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except _DOMAIN_ERRORS as e:
            raise click.ClickException(str(e)) from e

    return wrapper  # type: ignore[return-value]


def resolve_profile_path(name: str) -> Path:
    """Resolve a profile name to a bundled YAML path.

    LOAD-BEARING path traversal defense: regex rejects slashes / `..` /
    leading dots, then Path.resolve() + is_relative_to() provides
    defense-in-depth against symlink escapes.

    Raises ConfigFileNotFoundError on invalid name or missing profile.
    """
    if not name or not VALID_PROFILE_NAME_RE.match(name):
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
            f"{name!r} → {candidate}. This should not happen with a valid "
            f"profile name; if it does, it indicates a packaging bug."
        )

    if not candidate.is_file():
        raise ConfigFileNotFoundError(
            f"Profile not found: {name!r}. "
            f"Looked in {profiles_root}. "
            f"Available profiles can be listed with `gh manage profiles list` "
            f"(not yet implemented)."
        )
    return candidate


def resolve_templates_root() -> Path:
    """Resolve the bundled templates directory."""
    return Path(str(files("gh_manage.data") / "templates"))


def resolve_default_labels_path() -> Path:
    """Resolve the bundled labels.yml path."""
    return Path(str(files("gh_manage.data") / "labels.yml"))


def resolve_branch_protection_path() -> Path:
    """Resolve the bundled branch-protection.yml path."""
    return Path(str(files("gh_manage.data") / "branch-protection.yml"))


def resolve_repos_path() -> Path:
    """Resolve the bundled repos.yml path."""
    return Path(str(files("gh_manage.data") / "repos.yml"))


def resolve_backup_dir() -> Path:
    """Resolve the backup directory for protection snapshots."""
    return Path.home() / ".gh-manage" / "backups"


def format_files_diff(diff: ProfileFilesDiff) -> str:
    """Format a ProfileFilesDiff for human-readable CLI output."""
    lines: list[str] = ["Files:"]
    if diff.is_empty and not diff.skipped and not diff.noops:
        lines.append("  (no file changes)")
    for c in diff.creates:
        lines.append(f"  + create    {c.dest}")
    for o in diff.overwrites:
        lines.append(f"  ! overwrite {o.dest}  (use --force)")
    for s in diff.skipped:
        lines.append(f"  ≈ skip      {s.dest}  (skip_if_exists)")
    for n in diff.noops:
        lines.append(f"  = noop      {n.dest}")
    return "\n".join(lines)
```

- [ ] **Step 4: Fix import — add ConfigError to `_DOMAIN_ERRORS`**

The `_DOMAIN_ERRORS` tuple references `ConfigError` but it's not imported at the top. Add to the import block:

```python
from gh_manage.config import ConfigError, ConfigFileNotFoundError
```

- [ ] **Step 5: Run tests — confirm GREEN**

```bash
uv run pytest tests/unit/commands/test_shared.py -v
```

Expected: all pass.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: 417+ pass, zero failures.

- [ ] **Step 7: Lint check**

```bash
uvx ruff@0.8.0 check src/gh_manage/commands/_shared.py tests/unit/commands/test_shared.py && uvx ruff@0.8.0 format --check src/gh_manage/commands/_shared.py tests/unit/commands/test_shared.py
```

- [ ] **Step 8: Commit**

```bash
git add src/gh_manage/commands/_shared.py tests/unit/commands/test_shared.py
git commit -m "feat: add commands/_shared.py with extracted helpers (#38)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Replace duplicates in `commands/init.py`

**Files:**
- Modify: `src/gh_manage/commands/init.py`

- [ ] **Step 1: Replace imports and remove duplicated code**

In `src/gh_manage/commands/init.py`:

1. Add import at the top (after existing imports):

```python
from gh_manage.commands._shared import (
    format_files_diff,
    handle_errors,
    resolve_backup_dir,
    resolve_branch_protection_path,
    resolve_default_labels_path,
    resolve_profile_path,
    resolve_templates_root,
)
```

2. Delete these items entirely:
   - `_F = TypeVar(...)` (line 26)
   - `_handle_errors` function (lines 29-40)
   - `_VALID_PROFILE_NAME_RE` (line 43)
   - `_resolve_profile_path` function (lines 46-88)
   - `_resolve_templates_root` function (lines 91-92)
   - `_resolve_default_labels_path` function (lines 95-96)
   - `_resolve_branch_protection_path` function (lines 99-100)
   - `_resolve_backup_dir` function (lines 103-104)
   - `_format_files_diff` function (lines 107-119)

3. Replace all references:
   - `@_handle_errors` → `@handle_errors`
   - `_resolve_profile_path(` → `resolve_profile_path(`
   - `_resolve_templates_root()` → `resolve_templates_root()`
   - `_resolve_default_labels_path()` → `resolve_default_labels_path()`
   - `_resolve_branch_protection_path()` → `resolve_branch_protection_path()`
   - `_resolve_backup_dir()` → `resolve_backup_dir()`
   - `_format_files_diff(` → `format_files_diff(`

4. Remove now-unused imports:
   - `import functools`
   - `import re`
   - `from collections.abc import Callable`
   - `from importlib.resources import files`
   - `from typing import Any, TypeVar`

   Keep all other imports that the command logic still uses.

- [ ] **Step 2: Run init-specific tests**

```bash
uv run pytest tests/unit/cli/test_init.py -v
```

Expected: all pass.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: 417+ pass.

- [ ] **Step 4: Lint check**

```bash
uvx ruff@0.8.0 check src/gh_manage/commands/init.py && uvx ruff@0.8.0 format --check src/gh_manage/commands/init.py
```

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/commands/init.py
git commit -m "refactor: replace init.py duplicates with _shared imports (#38)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Replace duplicates in `commands/apply.py`

**Files:**
- Modify: `src/gh_manage/commands/apply.py`

- [ ] **Step 1: Replace imports and remove duplicated code**

Same pattern as Task 2. In `src/gh_manage/commands/apply.py`:

1. Add import:

```python
from gh_manage.commands._shared import (
    format_files_diff,
    handle_errors,
    resolve_backup_dir,
    resolve_branch_protection_path,
    resolve_default_labels_path,
    resolve_profile_path,
    resolve_templates_root,
)
```

2. Delete: `_F`, `_handle_errors`, `_VALID_PROFILE_NAME_RE`, `_resolve_profile_path`, `_resolve_templates_root`, `_resolve_default_labels_path`, `_resolve_branch_protection_path`, `_resolve_backup_dir`, `_format_files_diff`.

3. Replace all `_`-prefixed references with the shared versions (same list as Task 2).

4. Remove now-unused imports: `functools`, `re`, `Callable`, `files`, `Any`, `TypeVar`.

- [ ] **Step 2: Run apply-specific tests**

```bash
uv run pytest tests/unit/cli/test_apply.py -v
```

Expected: all pass.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: 417+ pass.

- [ ] **Step 4: Lint check**

```bash
uvx ruff@0.8.0 check src/gh_manage/commands/apply.py && uvx ruff@0.8.0 format --check src/gh_manage/commands/apply.py
```

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/commands/apply.py
git commit -m "refactor: replace apply.py duplicates with _shared imports (#38)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Replace duplicates in `commands/drift.py`

**Files:**
- Modify: `src/gh_manage/commands/drift.py`

- [ ] **Step 1: Replace imports and remove duplicated code**

In `src/gh_manage/commands/drift.py`:

1. Add import:

```python
from gh_manage.commands._shared import (
    handle_errors,
    resolve_branch_protection_path,
    resolve_default_labels_path,
    resolve_profile_path,
    resolve_repos_path,
)
```

2. Delete: `_F`, `_handle_errors`, `_VALID_PROFILE_NAME_RE`, `_resolve_profile_path`, `_resolve_default_labels_path`, `_resolve_branch_protection_path`, `_resolve_repos_path`.

3. Replace all `_`-prefixed references with the shared versions.

4. Remove now-unused imports: `functools`, `re`, `Callable`, `files` (from importlib.resources), `Any`, `TypeVar`.

   **Keep**: `ConfigFileNotFoundError` is still used in `_scan_single_repo` (the `from gh_manage.config import` line keeps `ConfigError`, `ConfigFileNotFoundError`, `load_config`).

- [ ] **Step 2: Run drift-specific tests**

```bash
uv run pytest tests/unit/cli/test_drift.py -v
```

Expected: all pass.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: 417+ pass.

- [ ] **Step 4: Lint check**

```bash
uvx ruff@0.8.0 check src/gh_manage/commands/drift.py && uvx ruff@0.8.0 format --check src/gh_manage/commands/drift.py
```

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/commands/drift.py
git commit -m "refactor: replace drift.py duplicates with _shared imports (#38)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Replace duplicates in `commands/protection.py`

**Files:**
- Modify: `src/gh_manage/commands/protection.py`

- [ ] **Step 1: Replace imports and remove duplicated code**

In `src/gh_manage/commands/protection.py`:

1. Add import:

```python
from gh_manage.commands._shared import (
    handle_errors,
    resolve_backup_dir,
    resolve_branch_protection_path,
    resolve_profile_path,
)
```

2. Delete: `_F`, `_VALID_PROFILE_NAME_RE`, `_handle_errors`, `_resolve_profile_path`, `_resolve_branch_protection_path`, `_resolve_backup_dir`.

3. Replace all `_`-prefixed references with the shared versions.

4. Remove now-unused imports: `functools`, `re`, `Callable`, `files` (from importlib.resources), `Any`, `TypeVar`.

   **Keep**: `ConfigValidationError` is used in `_load_profile_and_policy`.

- [ ] **Step 2: Run protection-specific tests**

```bash
uv run pytest tests/unit/cli/test_protection_cli.py -v 2>/dev/null || uv run pytest tests/unit/protection_sync/ -v
```

Expected: all pass.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: 417+ pass.

- [ ] **Step 4: Lint check**

```bash
uvx ruff@0.8.0 check src/gh_manage/commands/protection.py && uvx ruff@0.8.0 format --check src/gh_manage/commands/protection.py
```

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/commands/protection.py
git commit -m "refactor: replace protection.py duplicates with _shared imports (#38)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Final verification

**Files:** None (read-only verification)

- [ ] **Step 1: Verify zero private copies remain**

```bash
grep -rn '_resolve_profile_path\|_handle_errors\|_VALID_PROFILE_NAME_RE\|_resolve_templates_root\|_resolve_default_labels_path\|_resolve_branch_protection_path\|_resolve_backup_dir\|_resolve_repos_path\|_format_files_diff' src/gh_manage/commands/init.py src/gh_manage/commands/apply.py src/gh_manage/commands/drift.py src/gh_manage/commands/protection.py
```

Expected: zero matches.

- [ ] **Step 2: Verify `_shared.py` has exactly 1 definition of each**

```bash
grep -c 'def resolve_profile_path' src/gh_manage/commands/_shared.py
grep -c 'def handle_errors' src/gh_manage/commands/_shared.py
grep -c 'def format_files_diff' src/gh_manage/commands/_shared.py
```

Expected: `1` for each.

- [ ] **Step 3: Full test suite + lint**

```bash
uv run pytest tests/ -v --tb=short && uvx ruff@0.8.0 check src/ tests/ && uvx ruff@0.8.0 format --check src/ tests/
```

Expected: all pass, all clean.

---

## Summary

| Task | Type | Files |
|------|------|-------|
| 1. Create `_shared.py` + tests | Create (TDD) | `_shared.py`, `test_shared.py` |
| 2. Deduplicate `init.py` | Modify | `init.py` |
| 3. Deduplicate `apply.py` | Modify | `apply.py` |
| 4. Deduplicate `drift.py` | Modify | `drift.py` |
| 5. Deduplicate `protection.py` | Modify | `protection.py` |
| 6. Final verification | Read-only | None |
