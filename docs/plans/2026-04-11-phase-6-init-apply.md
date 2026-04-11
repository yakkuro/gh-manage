# Phase 6 — `gh manage init` / `gh manage apply` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `gh manage init` and `gh manage apply` so a fresh repo can be bootstrapped with profile-defined files plus labels sync, and an existing managed repo can re-apply files (and optionally labels) safely.

**Architecture:** 3-layer pattern mirroring Phase 5 — `commands/{init,apply}.py` (click) → `profile_sync.py` (pure-function engine) → `models/profiles.py` (pydantic schema). New `git_cli.py` module wraps `git` subprocess calls (mirrors `github_client.py`). All bundled data (templates, profiles, labels.yml) lives under `src/gh_manage/data/` and is resolved via `importlib.resources` so the CLI works from any CWD.

**Tech Stack:** Python 3.12 + click 8 + pydantic v2 + PyYAML + pytest 8 + pytest-mock + Hatchling. Reuses Phase 5 helpers (`labels_sync`, `github_api.labels`, `github_client`, `repo_ref`, `config.load_config`).

**Spec:** [`docs/specs/2026-04-11-phase-6-init-apply-design.md`](../specs/2026-04-11-phase-6-init-apply-design.md) — read it before starting any task.

---

## File Structure

### New source files

| Path | Responsibility | Created in task |
|---|---|---|
| `src/gh_manage/data/__init__.py` | Empty package marker so `importlib.resources.files("gh_manage.data")` works | Task 1 |
| `src/gh_manage/data/labels.yml` | gh-manage's authoritative label set, **moved** from `config/labels.yml` | Task 1 |
| `src/gh_manage/data/profiles/__init__.py` | Empty package marker | Task 1 |
| `src/gh_manage/data/profiles/python-service.yml` | First profile | Task 9 |
| `src/gh_manage/data/templates/ci/python-ci.yml` | Consumer-facing CI workflow template | Task 9 |
| `src/gh_manage/data/templates/claude-md/default.md` | Consumer-facing CLAUDE.md starter | Task 9 |
| `src/gh_manage/git_cli.py` | git subprocess transport + GitError hierarchy + parse_origin_url | Tasks 2 + 3 |
| `src/gh_manage/models/profiles.py` | `ProfileSpec`, `FileEntry`, validators | Task 4 |
| `src/gh_manage/profile_sync.py` | Pure-function engine: `compute_files_diff`, `apply_files_diff`, diff data classes | Tasks 5 + 6 + 7 |

### Modified source files

| Path | Change | Task |
|---|---|---|
| `src/gh_manage/commands/labels.py` | `DEFAULT_CONFIG_PATH` resolves via `importlib.resources` | Task 1 |
| `src/gh_manage/commands/init.py` | Replace stub with full init command | Task 10 |
| `src/gh_manage/commands/apply.py` | Replace stub with full apply command | Task 11 |

### Deleted source files

| Path | Reason | Task |
|---|---|---|
| `config/labels.yml` | Moved to `src/gh_manage/data/labels.yml` | Task 1 |
| `config/` (directory) | Empty after move | Task 1 |

### New test files

| Path | Purpose | Task |
|---|---|---|
| `tests/unit/git_cli/__init__.py` | package marker | Task 2 |
| `tests/unit/git_cli/test_git_cli.py` | parse_origin_url + get_origin_owner_repo + LC_ALL=C assertion | Tasks 2 + 3 |
| `tests/unit/models/__init__.py` | package marker | Task 4 |
| `tests/unit/models/test_profiles.py` | ProfileSpec validators | Task 4 |
| `tests/unit/profile_sync/__init__.py` | package marker | Task 5 |
| `tests/unit/profile_sync/test_profile_sync.py` | compute_files_diff + apply_files_diff | Tasks 5 + 6 + 7 |
| `tests/unit/profile_sync/test_golden.py` | golden file test against fixtures | Task 8 |
| `tests/unit/cli/test_init.py` | init click command tests | Task 10 |
| `tests/unit/cli/test_apply.py` | apply click command tests | Task 11 |

### New test fixtures

| Path | Content | Task |
|---|---|---|
| `tests/fixtures/profile_sync/profiles/basic.yml` | 2-file v1 profile | Task 8 |
| `tests/fixtures/profile_sync/profiles/invalid_version.yml` | `version: 99` for SchemaVersionError test | Task 4 |
| `tests/fixtures/profile_sync/profiles/duplicate_dest.yml` | Two entries with same `dest:` | Task 4 |
| `tests/fixtures/profile_sync/templates/ci/test-ci.yml` | Stable byte-for-byte template content | Task 8 |
| `tests/fixtures/profile_sync/templates/claude-md/test.md` | Stable byte-for-byte template content | Task 8 |

---

## Pre-flight checklist for the implementer

Before starting Task 1, run these commands and confirm baseline state:

```bash
cd /home/server160/repos/gh-manage
git status              # must be clean
git checkout main
git pull --ff-only
uv run pytest           # must pass — baseline 102 tests
uv run ruff check src/ tests/   # must pass
uv run mypy src/        # one pre-existing yaml stub note is acceptable
```

If any of the above fails, **stop and report** — do not start Phase 6 on a broken baseline.

Then create the working branch:

```bash
git checkout -b feat/phase-6-init-apply
```

All Phase 6 tasks commit to this branch. The final PR opens `feat/phase-6-init-apply` → `main`.

---

## Task 1: Move `labels.yml` to package data + update Phase 5 default path

**Goal:** Establish `src/gh_manage/data/` as the canonical package-data location, move `labels.yml` into it, and update Phase 5's `commands/labels.py` to resolve the default config from package data. After this task, `gh manage labels show gh-manage` must still work from any CWD.

**Files:**
- Create: `src/gh_manage/data/__init__.py`
- Create: `src/gh_manage/data/profiles/__init__.py`
- Move: `config/labels.yml` → `src/gh_manage/data/labels.yml`
- Modify: `src/gh_manage/commands/labels.py` (line 21 + help text)
- Delete: `config/` directory after move

- [ ] **Step 1.1: Create `src/gh_manage/data/` package marker**

```bash
mkdir -p src/gh_manage/data/profiles src/gh_manage/data/templates
```

Then create `src/gh_manage/data/__init__.py` with this content:

```python
"""Package data root for gh-manage.

Holds bundled YAML configs (labels.yml, profiles/*.yml) and template
files (templates/**) that ship inside the wheel and are resolved via
importlib.resources at runtime. This package ships no Python code.
"""
```

- [ ] **Step 1.2: Create `src/gh_manage/data/profiles/__init__.py`**

```python
"""Bundled gh-manage profiles (profile YAML files only — no code)."""
```

- [ ] **Step 1.3: Move `config/labels.yml`**

```bash
git mv config/labels.yml src/gh_manage/data/labels.yml
```

- [ ] **Step 1.4: Update `commands/labels.py` to resolve `DEFAULT_CONFIG_PATH` from package data**

Open `src/gh_manage/commands/labels.py`. Replace the import block and `DEFAULT_CONFIG_PATH` line.

OLD (lines 1-22):
```python
"""gh manage labels — sync, diff, show GitHub repo labels."""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage import labels_sync
from gh_manage.config import ConfigError, load_config
from gh_manage.github_api import labels as labels_api
from gh_manage.github_client import GhError
from gh_manage.labels_sync import LabelsDiff
from gh_manage.models.labels import LabelsConfig
from gh_manage.repo_ref import parse_repo

DEFAULT_CONFIG_PATH = Path("config/labels.yml")
```

NEW:
```python
"""gh manage labels — sync, diff, show GitHub repo labels."""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage import labels_sync
from gh_manage.config import ConfigError, load_config
from gh_manage.github_api import labels as labels_api
from gh_manage.github_client import GhError
from gh_manage.labels_sync import LabelsDiff
from gh_manage.models.labels import LabelsConfig
from gh_manage.repo_ref import parse_repo

DEFAULT_CONFIG_PATH = Path(str(files("gh_manage.data") / "labels.yml"))
```

- [ ] **Step 1.5: Update help text in `commands/labels.py` to be path-agnostic**

In the same file, update the three help-text strings to use a path-agnostic phrase. Apply each replacement individually:

Replace `"Synchronize GitHub repo labels against config/labels.yml."` with `"Synchronize GitHub repo labels against the bundled labels.yml."`

Replace `"Apply config/labels.yml to a repo. Default is dry-run; "` with `"Apply the bundled labels.yml to a repo. Default is dry-run; "`

Replace `"Show diff between config/labels.yml and a repo. "` with `"Show diff between the bundled labels.yml and a repo. "`

(The docstring on line 176 about `show should succeed without any config/labels.yml present` is internal and can stay.)

- [ ] **Step 1.6: Run Phase 5 test suite to confirm no regression**

```bash
uv run pytest tests/unit/cli/test_labels.py tests/unit/labels_sync/ tests/unit/config/ -v
```

Expected: all Phase 5 tests pass. They use `--config <tmp_path>` so the default path change is invisible to them.

- [ ] **Step 1.7: Run dogfood verification — labels show from a different CWD**

```bash
cd /tmp && /home/server160/repos/gh-manage/.venv/bin/gh-manage labels show gh-manage 2>&1 | head -5
```

Expected: 14 labels listed (`chore`, `ci`, `docs`, ...). If this fails with "Config file not found", the package-data resolution is broken.

Then return to the repo:

```bash
cd /home/server160/repos/gh-manage
```

- [ ] **Step 1.8: Verify `config/` directory is empty and remove it**

```bash
ls config/ 2>&1
```

Expected: directory is empty (all that was there was `labels.yml`).

```bash
rmdir config
```

- [ ] **Step 1.9: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: 102 tests pass, ruff clean, mypy 1 pre-existing yaml note.

- [ ] **Step 1.10: Commit**

```bash
git add src/gh_manage/data/ src/gh_manage/commands/labels.py
git rm config/labels.yml
git commit -m "$(cat <<'EOF'
refactor(phase-6): move labels.yml to package data

Phase 6 needs to load gh-manage's bundled config from any CWD (init
runs in consumer repos, not gh-manage's own repo). Establishes
src/gh_manage/data/ as the canonical package-data location for all
bundled YAML / template files, and moves labels.yml into it.

Phase 5 commands/labels.py:DEFAULT_CONFIG_PATH now resolves via
importlib.resources.files("gh_manage.data") / "labels.yml" — no
behavior change for existing tests (they use --config flag) and the
CLI now works from any CWD (verified by smoke test).

Help text updated to "the bundled labels.yml" so the CLI doesn't
expose the internal package layout to users.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `git_cli.py` — pure parser `parse_origin_url`

**Goal:** Create the `git_cli.py` module with the pure-function URL parser. No subprocess calls yet — just the string-to-`owner/repo` normalizer for github.com URLs. TDD: tests first.

**Files:**
- Create: `src/gh_manage/git_cli.py`
- Create: `tests/unit/git_cli/__init__.py`
- Create: `tests/unit/git_cli/test_git_cli.py`

- [ ] **Step 2.1: Create test directory**

```bash
mkdir -p tests/unit/git_cli
```

- [ ] **Step 2.2: Write `tests/unit/git_cli/__init__.py`**

Empty file:

```python
```

- [ ] **Step 2.3: Write the failing tests for `parse_origin_url`**

Create `tests/unit/git_cli/test_git_cli.py`:

```python
"""Tests for gh_manage.git_cli — local git CLI subprocess transport.

Mirrors tests/unit/github_client/test_github_client.py — subprocess.run
is mocked to return controlled CompletedProcess instances.
"""

from __future__ import annotations

import pytest

from gh_manage.git_cli import parse_origin_url


# parse_origin_url — happy paths
@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("git@github.com:yakkuro/gh-manage.git", "yakkuro/gh-manage"),
        ("git@github.com:yakkuro/gh-manage", "yakkuro/gh-manage"),
        ("https://github.com/yakkuro/gh-manage.git", "yakkuro/gh-manage"),
        ("https://github.com/yakkuro/gh-manage", "yakkuro/gh-manage"),
        ("https://github.com/some-org/multi.dot.repo", "some-org/multi.dot.repo"),
    ],
)
def test_parse_origin_url_happy_paths(url: str, expected: str) -> None:
    assert parse_origin_url(url) == expected


# parse_origin_url — unsupported origins
def test_parse_origin_url_rejects_gitlab() -> None:
    with pytest.raises(ValueError, match="github.com"):
        parse_origin_url("git@gitlab.com:yakkuro/foo.git")


def test_parse_origin_url_rejects_bitbucket() -> None:
    with pytest.raises(ValueError, match="github.com"):
        parse_origin_url("https://bitbucket.org/yakkuro/foo.git")


def test_parse_origin_url_rejects_self_hosted_https() -> None:
    with pytest.raises(ValueError, match="github.com"):
        parse_origin_url("https://git.internal.example.com/owner/repo.git")


def test_parse_origin_url_rejects_malformed() -> None:
    with pytest.raises(ValueError):
        parse_origin_url("not-a-url-at-all")


def test_parse_origin_url_error_message_includes_offending_url() -> None:
    with pytest.raises(ValueError, match="gitlab.com"):
        parse_origin_url("git@gitlab.com:foo/bar.git")
```

- [ ] **Step 2.4: Run tests to verify they fail**

```bash
uv run pytest tests/unit/git_cli/test_git_cli.py -v
```

Expected: collection error or all tests fail with `ModuleNotFoundError: No module named 'gh_manage.git_cli'`.

- [ ] **Step 2.5: Implement `parse_origin_url` in a new `git_cli.py`**

Create `src/gh_manage/git_cli.py`:

```python
"""Local git CLI subprocess transport + error hierarchy.

Mirrors gh_manage.github_client: a typed wrapper around the `git` CLI
with classified errors. All git subprocess calls in gh-manage go through
this module so error handling stays consistent across phases.

Phase 6 ships parse_origin_url + get_origin_owner_repo. Phase 7+ may
add is_clean_tree, current_branch, etc. — same module, same error
classification pattern.
"""

from __future__ import annotations

import re

# Match: git@github.com:owner/repo[.git] OR https://github.com/owner/repo[.git]
# Allow trailing slash, .git suffix, owner/repo segments matching GitHub's
# loose rules (alnum + dot + dash + underscore). Validation of the parts
# is delegated to GitHub itself; we only check the host.
_SSH_RE = re.compile(r"^git@github\.com:([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$")
_HTTPS_RE = re.compile(r"^https://github\.com/([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$")


def parse_origin_url(url: str) -> str:
    """Parse a git remote URL into 'owner/repo' form. Pure.

    Supports GitHub only (github.com):
      git@github.com:owner/repo.git    → owner/repo
      git@github.com:owner/repo        → owner/repo
      https://github.com/owner/repo.git → owner/repo
      https://github.com/owner/repo    → owner/repo

    Raises ValueError on any other URL form (gitlab, bitbucket, self-hosted,
    malformed) with an actionable message naming the offending URL and
    explaining gh-manage's GitHub-only constraint.
    """
    match = _SSH_RE.match(url) or _HTTPS_RE.match(url)
    if match is None:
        raise ValueError(
            f"Unsupported git remote URL: {url!r}. "
            f"gh-manage only supports GitHub (github.com) origins. "
            f"Non-GitHub remotes (gitlab.com, bitbucket.org, self-hosted) "
            f"are not supported in Phase 6."
        )
    owner, repo = match.groups()
    return f"{owner}/{repo}"
```

- [ ] **Step 2.6: Run tests to verify they pass**

```bash
uv run pytest tests/unit/git_cli/test_git_cli.py -v
```

Expected: 9 passed (5 happy paths + 4 unsupported + 1 message check).

- [ ] **Step 2.7: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green (102 + 9 = 111 tests).

- [ ] **Step 2.8: Commit**

```bash
git add src/gh_manage/git_cli.py tests/unit/git_cli/
git commit -m "$(cat <<'EOF'
feat(phase-6): add git_cli.parse_origin_url pure parser

Pure string-to-owner/repo normalizer for github.com URLs. Supports
both git@ and https:// forms, with or without .git suffix. Raises
ValueError with an actionable message for non-github.com URLs
(gitlab, bitbucket, self-hosted).

Mirrors the github_client.py pattern: this is the foundation for the
git_cli.py module. Subprocess wrappers + GitError hierarchy land in
the next task.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `git_cli.py` — `get_origin_owner_repo` + GitError hierarchy + `LC_ALL=C`

**Goal:** Add the subprocess wrapper `get_origin_owner_repo` and the typed `GitError` hierarchy. Enforce `LC_ALL=C` on every git subprocess call so stderr classification is locale-stable. Wrap `parse_origin_url`'s `ValueError` into `UnsupportedOriginError(GitError)` so callers only catch `GitError`.

**Files:**
- Modify: `src/gh_manage/git_cli.py`
- Modify: `tests/unit/git_cli/test_git_cli.py`

- [ ] **Step 3.1: Add the new failing tests for the subprocess wrapper**

Append to `tests/unit/git_cli/test_git_cli.py`:

```python
from pathlib import Path
from subprocess import CompletedProcess

from pytest_mock import MockerFixture

from gh_manage.git_cli import (
    GitError,
    GitNotInstalledError,
    NoOriginRemoteError,
    NotAGitRepoError,
    UnsupportedOriginError,
    get_origin_owner_repo,
)


def _mock_git_success(mocker: MockerFixture, stdout: str) -> object:
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=""),
    )


def _mock_git_failure(
    mocker: MockerFixture, stderr: str, returncode: int = 1
) -> object:
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr=stderr
        ),
    )


# get_origin_owner_repo — happy path
def test_get_origin_owner_repo_success(mocker: MockerFixture) -> None:
    _mock_git_success(mocker, "git@github.com:yakkuro/gh-manage.git\n")
    assert get_origin_owner_repo(Path("/tmp/fake")) == "yakkuro/gh-manage"


def test_get_origin_owner_repo_https_success(mocker: MockerFixture) -> None:
    _mock_git_success(mocker, "https://github.com/yakkuro/gh-manage\n")
    assert get_origin_owner_repo(Path("/tmp/fake")) == "yakkuro/gh-manage"


# get_origin_owner_repo — error classification
def test_get_origin_owner_repo_not_a_git_repo(mocker: MockerFixture) -> None:
    _mock_git_failure(mocker, "fatal: not a git repository (or any parent up to mount point /)\n")
    with pytest.raises(NotAGitRepoError, match="git init"):
        get_origin_owner_repo(Path("/tmp/fake"))


def test_get_origin_owner_repo_no_origin_remote(mocker: MockerFixture) -> None:
    _mock_git_failure(mocker, "error: No such remote 'origin'\n", returncode=2)
    with pytest.raises(NoOriginRemoteError, match="git remote add origin"):
        get_origin_owner_repo(Path("/tmp/fake"))


def test_get_origin_owner_repo_git_not_installed(mocker: MockerFixture) -> None:
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("git"))
    with pytest.raises(GitNotInstalledError, match="git-scm.com"):
        get_origin_owner_repo(Path("/tmp/fake"))


def test_get_origin_owner_repo_other_failure_is_generic_git_error(
    mocker: MockerFixture,
) -> None:
    _mock_git_failure(mocker, "fatal: some other error\n")
    with pytest.raises(GitError):
        get_origin_owner_repo(Path("/tmp/fake"))


# get_origin_owner_repo — UnsupportedOriginError wraps ValueError
def test_get_origin_owner_repo_gitlab_url_raises_unsupported_origin(
    mocker: MockerFixture,
) -> None:
    """parse_origin_url raises ValueError on non-github URLs;
    get_origin_owner_repo MUST wrap this into UnsupportedOriginError(GitError)
    so callers only need to catch GitError."""
    _mock_git_success(mocker, "git@gitlab.com:yakkuro/foo.git\n")
    with pytest.raises(UnsupportedOriginError, match="github.com"):
        get_origin_owner_repo(Path("/tmp/fake"))


def test_unsupported_origin_error_is_a_git_error_subclass() -> None:
    """Catch GitError must also catch UnsupportedOriginError."""
    err = UnsupportedOriginError("test")
    assert isinstance(err, GitError)


# Locale enforcement — LOAD-BEARING
def test_get_origin_owner_repo_uses_lc_all_c(mocker: MockerFixture) -> None:
    """Subprocess invocation must include LC_ALL=C in env so stderr
    string matching is locale-stable. Regression guard for the locale
    contract documented in the design spec."""
    mock_run = _mock_git_success(mocker, "git@github.com:yakkuro/gh-manage.git\n")
    get_origin_owner_repo(Path("/tmp/fake"))
    env = mock_run.call_args.kwargs["env"]
    assert env["LC_ALL"] == "C"
    assert env["LANG"] == "C"
    assert env["LC_MESSAGES"] == "C"


def test_get_origin_owner_repo_uses_target_as_cwd(mocker: MockerFixture) -> None:
    """Subprocess must run with `git -C <target>` so it doesn't pick up
    the test runner's CWD by accident."""
    mock_run = _mock_git_success(mocker, "git@github.com:yakkuro/gh-manage.git\n")
    get_origin_owner_repo(Path("/tmp/some-target"))
    args = mock_run.call_args.args[0]
    assert args[0] == "git"
    assert "-C" in args
    c_idx = args.index("-C")
    assert args[c_idx + 1] == "/tmp/some-target"
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/git_cli/test_git_cli.py -v
```

Expected: import errors / failures because `GitError`, `GitNotInstalledError`, etc. don't exist yet.

- [ ] **Step 3.3: Add the GitError hierarchy + subprocess wrapper to `git_cli.py`**

Edit `src/gh_manage/git_cli.py` and append (after the existing `parse_origin_url`):

```python
import os
import subprocess
from pathlib import Path
from typing import NoReturn


class GitError(Exception):
    """Base for git CLI subprocess failures. Never raised directly."""


class GitNotInstalledError(GitError):
    """`git` CLI missing on PATH."""


class NotAGitRepoError(GitError):
    """target is not inside a git work tree."""


class NoOriginRemoteError(GitError):
    """git is set up but `origin` remote is not configured."""


class UnsupportedOriginError(GitError):
    """`origin` is set but URL is not a github.com remote (gitlab, bitbucket,
    self-hosted, etc.). Wraps ValueError from parse_origin_url so callers
    only need to catch GitError subclasses."""


_GIT_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C", "LC_MESSAGES": "C"}


def _raise_classified_git_error(
    *, stderr: str, returncode: int
) -> NoReturn:
    """Classify git stderr into a typed GitError subclass."""
    stderr_lower = stderr.lower()
    if "not a git repository" in stderr_lower:
        raise NotAGitRepoError(
            f"Not a git repository. Run `git init` first to create one. "
            f"(git exit {returncode}: {stderr.strip()[:200]})"
        )
    if "no such remote" in stderr_lower:
        raise NoOriginRemoteError(
            "No `origin` remote configured. Run "
            "`git remote add origin git@github.com:OWNER/REPO.git` "
            "and try again."
        )
    raise GitError(
        f"git command failed (exit {returncode}): {stderr.strip()[:300]}. "
        f"Re-run with `GIT_TRACE=1` to see what git was doing."
    )


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run `git -C <cwd> <args>` with locale forced to C.

    All public functions in this module go through _run_git so error
    classification stays consistent and stderr matching stays locale-stable.

    Raises GitNotInstalledError if `git` is not on PATH. Returns the
    CompletedProcess unchanged otherwise — callers inspect returncode
    and call _raise_classified_git_error on non-zero.
    """
    try:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            check=False,
            env=_GIT_ENV,
        )
    except FileNotFoundError as e:
        raise GitNotInstalledError(
            "The `git` CLI is required but was not found on PATH. "
            "Install git from https://git-scm.com/ and try again."
        ) from e


def get_origin_owner_repo(target: Path) -> str:
    """Run `git remote get-url origin` in target and parse → 'owner/repo'.

    Raises:
      GitNotInstalledError    — git not on PATH
      NotAGitRepoError        — target is not inside a git work tree
      NoOriginRemoteError     — git is OK but `origin` is not set
      UnsupportedOriginError  — origin URL is not a github.com URL
      GitError                — other git failures (catch-all)
    """
    result = _run_git(["remote", "get-url", "origin"], cwd=target)
    if result.returncode != 0:
        _raise_classified_git_error(
            stderr=result.stderr, returncode=result.returncode
        )
    url = result.stdout.strip()
    try:
        return parse_origin_url(url)
    except ValueError as e:
        raise UnsupportedOriginError(str(e)) from e
```

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/git_cli/test_git_cli.py -v
```

Expected: 19 passed (5 + 4 + 1 from Task 2, plus 9 new from Task 3).

- [ ] **Step 3.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green.

- [ ] **Step 3.6: Commit**

```bash
git add src/gh_manage/git_cli.py tests/unit/git_cli/test_git_cli.py
git commit -m "$(cat <<'EOF'
feat(phase-6): add git_cli subprocess wrapper + GitError hierarchy

get_origin_owner_repo runs `git remote get-url origin` in a target
directory and returns the parsed owner/repo. Errors are classified
into a typed GitError hierarchy (GitNotInstalledError,
NotAGitRepoError, NoOriginRemoteError, UnsupportedOriginError, GitError)
mirroring the github_client pattern.

Locale stability: every git invocation goes through _run_git which
forces LC_ALL=C / LANG=C / LC_MESSAGES=C in the subprocess env. This
keeps stderr string matching ("not a git repository", "no such remote")
locale-independent and prevents CI/multilingual environments from
silently degrading error classification. Regression test asserts the
env kwarg.

UnsupportedOriginError wraps ValueError from parse_origin_url so
callers only need to catch GitError subclasses.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `models/profiles.py` — pydantic schema with validators

**Goal:** Define `ProfileSpec` and `FileEntry` pydantic models with the field-level traversal pre-filter and the model-level duplicate-`dest` check. Three new test fixtures support both happy and error paths.

**Files:**
- Create: `src/gh_manage/models/profiles.py`
- Create: `tests/unit/models/__init__.py`
- Create: `tests/unit/models/test_profiles.py`
- Create: `tests/fixtures/profile_sync/profiles/invalid_version.yml`
- Create: `tests/fixtures/profile_sync/profiles/duplicate_dest.yml`

- [ ] **Step 4.1: Create test directories**

```bash
mkdir -p tests/unit/models tests/fixtures/profile_sync/profiles
```

- [ ] **Step 4.2: Write `tests/unit/models/__init__.py`**

Empty file:

```python
```

- [ ] **Step 4.3: Write the failing tests**

Create `tests/unit/models/test_profiles.py`:

```python
"""Tests for gh_manage.models.profiles — ProfileSpec + FileEntry."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gh_manage.config import ConfigSchemaVersionError, load_config
from gh_manage.models.profiles import FileEntry, ProfileSpec

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "profile_sync" / "profiles"


# FileEntry validators
def test_file_entry_minimal_valid() -> None:
    e = FileEntry(source="ci/python-ci.yml", dest=".github/workflows/ci.yml")
    assert e.skip_if_exists is False


def test_file_entry_skip_if_exists_default_false() -> None:
    e = FileEntry(source="a", dest="b")
    assert e.skip_if_exists is False


def test_file_entry_rejects_absolute_dest() -> None:
    with pytest.raises(ValidationError, match="absolute"):
        FileEntry(source="ci.yml", dest="/etc/passwd")


def test_file_entry_rejects_dotdot_in_dest() -> None:
    with pytest.raises(ValidationError, match=r"\.\."):
        FileEntry(source="ci.yml", dest="../../etc/passwd")


def test_file_entry_rejects_absolute_source() -> None:
    with pytest.raises(ValidationError, match="absolute"):
        FileEntry(source="/etc/passwd", dest="foo.yml")


def test_file_entry_rejects_dotdot_in_source() -> None:
    with pytest.raises(ValidationError, match=r"\.\."):
        FileEntry(source="../etc/passwd", dest="foo.yml")


def test_file_entry_rejects_empty_dest() -> None:
    with pytest.raises(ValidationError, match="empty"):
        FileEntry(source="ci.yml", dest="")


def test_file_entry_rejects_empty_source() -> None:
    with pytest.raises(ValidationError, match="empty"):
        FileEntry(source="", dest="ci.yml")


# ProfileSpec
def test_profile_spec_minimal_valid() -> None:
    p = ProfileSpec(
        version=1,
        name="python-service",
        files=[FileEntry(source="a", dest="b")],
    )
    assert p.description is None


def test_profile_spec_with_description() -> None:
    p = ProfileSpec(
        version=1,
        name="python-service",
        description="Python service repo",
        files=[],
    )
    assert p.description == "Python service repo"


def test_profile_spec_empty_files_is_valid() -> None:
    """A vacuous profile (no files) is technically valid — apply does nothing."""
    p = ProfileSpec(version=1, name="empty", files=[])
    assert p.files == []


def test_profile_spec_rejects_unknown_version() -> None:
    with pytest.raises(ValidationError):
        ProfileSpec(version=99, name="x", files=[])  # type: ignore[arg-type]


def test_profile_spec_missing_name_raises() -> None:
    with pytest.raises(ValidationError):
        ProfileSpec(version=1, files=[])  # type: ignore[call-arg]


def test_profile_spec_duplicate_dest_raises() -> None:
    """Two file entries writing to the same dest is a silent shadowing
    bug at apply time. Schema must reject it."""
    with pytest.raises(ValidationError, match="Duplicate dest"):
        ProfileSpec(
            version=1,
            name="dup",
            files=[
                FileEntry(source="a.yml", dest="x.yml"),
                FileEntry(source="b.yml", dest="x.yml"),
            ],
        )


# load_config integration
def test_load_config_invalid_version_yml_raises_schema_version_error() -> None:
    with pytest.raises(ConfigSchemaVersionError):
        load_config(FIXTURES / "invalid_version.yml", ProfileSpec)


def test_load_config_duplicate_dest_yml_raises() -> None:
    from gh_manage.config import ConfigValidationError
    with pytest.raises(ConfigValidationError, match="Duplicate dest"):
        load_config(FIXTURES / "duplicate_dest.yml", ProfileSpec)
```

- [ ] **Step 4.4: Run tests to verify they fail**

```bash
uv run pytest tests/unit/models/test_profiles.py -v
```

Expected: collection error (`gh_manage.models.profiles` doesn't exist).

- [ ] **Step 4.5: Create the fixture files**

Create `tests/fixtures/profile_sync/profiles/invalid_version.yml`:

```yaml
version: 99
name: future
files: []
```

Create `tests/fixtures/profile_sync/profiles/duplicate_dest.yml`:

```yaml
version: 1
name: dup
files:
  - source: a.yml
    dest: x.yml
  - source: b.yml
    dest: x.yml
```

- [ ] **Step 4.6: Implement `models/profiles.py`**

Create `src/gh_manage/models/profiles.py`:

```python
"""Pydantic schema for profile YAML files (config/profiles/<name>.yml).

A profile defines a set of files to copy into a target repo when
`gh manage init` or `gh manage apply` runs. Phase 6 schema is minimal
(version, name, description, files); Phase 7+ will add extra_labels,
protection_policy, required_contexts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FileEntry(BaseModel):
    """A single file copy operation in a profile."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., description="Path under templates/, relative")
    dest: str = Field(..., description="Path under target repo root, relative")
    skip_if_exists: bool = False

    @field_validator("source", "dest")
    @classmethod
    def _no_obvious_traversal(cls, v: str) -> str:
        """Cheap structural rejection. Real escape prevention happens at
        apply time via Path.resolve() + is_relative_to() — see profile_sync.
        """
        if not v:
            raise ValueError("Path must not be empty")
        if v.startswith("/"):
            raise ValueError(f"Path must not be absolute: {v!r}")
        if ".." in v.split("/"):
            raise ValueError(f"Path must not contain '..' segments: {v!r}")
        return v


class ProfileSpec(BaseModel):
    """A gh-manage profile."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    name: str
    description: str | None = None
    files: list[FileEntry]

    @model_validator(mode="after")
    def _check_unique_dest(self) -> ProfileSpec:
        """Two entries writing to the same dest is a silent shadowing bug
        at apply time — only the last write would survive."""
        seen: set[str] = set()
        for entry in self.files:
            if entry.dest in seen:
                raise ValueError(
                    f"Duplicate dest path in profile {self.name!r}: {entry.dest!r}"
                )
            seen.add(entry.dest)
        return self
```

- [ ] **Step 4.7: Run tests to verify they pass**

```bash
uv run pytest tests/unit/models/test_profiles.py -v
```

Expected: 16 passed.

- [ ] **Step 4.8: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green.

- [ ] **Step 4.9: Commit**

```bash
git add src/gh_manage/models/profiles.py tests/unit/models/ tests/fixtures/profile_sync/
git commit -m "$(cat <<'EOF'
feat(phase-6): add ProfileSpec + FileEntry pydantic schema

Schema for profile YAML files. Includes:
- FileEntry with source/dest/skip_if_exists fields
- Field-level traversal pre-filter (rejects empty / absolute / ../
  segments — cheap structural check, real escape prevention happens
  in profile_sync via Path.resolve() at apply time)
- ProfileSpec with version=Literal[1], name, optional description, files
- Model-level validator rejecting duplicate dest paths (would be a
  silent shadowing bug at apply time)
- extra="forbid" on both models — unknown fields raise ValidationError

Two fixture files added for the load_config integration tests:
invalid_version.yml (version=99) and duplicate_dest.yml (two entries
writing to the same dest).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `profile_sync.py` — diff data classes + ProfileError types

**Goal:** Define the diff data structures (`FileCreate`, `FileOverwrite`, `FileSkipExists`, `FileNoop`, `ProfileFilesDiff`) and the error types (`ProfileError`, `ProfileConflictError`, `ProfileTemplateNotFoundError`, `ProfilePathEscapeError`). No engine logic yet — just the contract types and tests for the property accessors.

**Files:**
- Create: `src/gh_manage/profile_sync.py`
- Create: `tests/unit/profile_sync/__init__.py`
- Create: `tests/unit/profile_sync/test_profile_sync.py`

- [ ] **Step 5.1: Create test directory**

```bash
mkdir -p tests/unit/profile_sync
```

- [ ] **Step 5.2: Write `tests/unit/profile_sync/__init__.py`**

Empty file:

```python
```

- [ ] **Step 5.3: Write the failing tests for the data classes**

Create `tests/unit/profile_sync/test_profile_sync.py`:

```python
"""Tests for gh_manage.profile_sync — pure-function profile engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from gh_manage.profile_sync import (
    FileCreate,
    FileNoop,
    FileOverwrite,
    FileSkipExists,
    ProfileConflictError,
    ProfileError,
    ProfileFilesDiff,
    ProfilePathEscapeError,
    ProfileTemplateNotFoundError,
)


# Diff data classes
def test_profile_files_diff_is_empty_when_no_creates_or_overwrites() -> None:
    diff = ProfileFilesDiff(creates=(), overwrites=(), skipped=(), noops=())
    assert diff.is_empty


def test_profile_files_diff_is_empty_ignores_skipped_and_noops() -> None:
    """Skipped and Noops are reported but don't count as 'changes'."""
    diff = ProfileFilesDiff(
        creates=(),
        overwrites=(),
        skipped=(FileSkipExists(dest=Path("/x")),),
        noops=(FileNoop(dest=Path("/y")),),
    )
    assert diff.is_empty


def test_profile_files_diff_not_empty_with_creates() -> None:
    diff = ProfileFilesDiff(
        creates=(FileCreate(source=Path("/s"), dest=Path("/d")),),
        overwrites=(),
        skipped=(),
        noops=(),
    )
    assert not diff.is_empty


def test_profile_files_diff_not_empty_with_overwrites() -> None:
    diff = ProfileFilesDiff(
        creates=(),
        overwrites=(FileOverwrite(source=Path("/s"), dest=Path("/d")),),
        skipped=(),
        noops=(),
    )
    assert not diff.is_empty


def test_profile_files_diff_has_overwrites_property() -> None:
    diff = ProfileFilesDiff(
        creates=(),
        overwrites=(FileOverwrite(source=Path("/s"), dest=Path("/d")),),
        skipped=(),
        noops=(),
    )
    assert diff.has_overwrites


def test_profile_files_diff_has_overwrites_false_when_empty() -> None:
    diff = ProfileFilesDiff(creates=(), overwrites=(), skipped=(), noops=())
    assert not diff.has_overwrites


# Error hierarchy
def test_profile_conflict_error_message_lists_conflicts() -> None:
    overwrite = FileOverwrite(source=Path("/s"), dest=Path("/dest/file.yml"))
    err = ProfileConflictError((overwrite,))
    assert "1 file" in str(err)
    assert "/dest/file.yml" in str(err)
    assert "--force" in str(err)


def test_profile_conflict_error_with_multiple() -> None:
    o1 = FileOverwrite(source=Path("/s1"), dest=Path("/d1"))
    o2 = FileOverwrite(source=Path("/s2"), dest=Path("/d2"))
    err = ProfileConflictError((o1, o2))
    assert "2 file" in str(err)


def test_profile_template_not_found_error_is_profile_error() -> None:
    err = ProfileTemplateNotFoundError("missing")
    assert isinstance(err, ProfileError)


def test_profile_path_escape_error_is_profile_error() -> None:
    err = ProfilePathEscapeError("escape")
    assert isinstance(err, ProfileError)


def test_profile_conflict_error_is_profile_error() -> None:
    err = ProfileConflictError(())
    assert isinstance(err, ProfileError)


def test_file_create_is_frozen() -> None:
    """Diff entries must be immutable so callers can't mutate them
    between compute and apply phases."""
    fc = FileCreate(source=Path("/s"), dest=Path("/d"))
    with pytest.raises(Exception):  # FrozenInstanceError
        fc.source = Path("/other")  # type: ignore[misc]
```

- [ ] **Step 5.4: Run tests to verify they fail**

```bash
uv run pytest tests/unit/profile_sync/test_profile_sync.py -v
```

Expected: collection error (`gh_manage.profile_sync` doesn't exist).

- [ ] **Step 5.5: Create the data classes + errors in `profile_sync.py`**

Create `src/gh_manage/profile_sync.py`:

```python
"""Pure-function profile engine: compute diff + apply.

Mirrors gh_manage.labels_sync's pattern. compute_files_diff produces a
ProfileFilesDiff describing what would happen; apply_files_diff
executes that diff with transactional conflict semantics.

This module knows about the local filesystem but not about subprocess,
git, or the GitHub API. Tests pass tmp_path-based fixtures.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gh_manage.models.profiles import ProfileSpec


# Diff entry types
@dataclass(frozen=True)
class FileCreate:
    """dest does not exist; will be written."""

    source: Path
    dest: Path


@dataclass(frozen=True)
class FileOverwrite:
    """dest exists with different content and skip_if_exists is False.
    Will be written iff apply_files_diff(force=True)."""

    source: Path
    dest: Path


@dataclass(frozen=True)
class FileSkipExists:
    """skip_if_exists=True and dest exists. Never written, even with --force."""

    dest: Path


@dataclass(frozen=True)
class FileNoop:
    """dest exists with byte-identical content. No write needed."""

    dest: Path


@dataclass(frozen=True)
class ProfileFilesDiff:
    """The output of compute_files_diff: four buckets of file operations.

    Note: only `creates` and `overwrites` represent actionable changes;
    `skipped` and `noops` are reported for transparency but don't trigger
    writes.
    """

    creates: tuple[FileCreate, ...]
    overwrites: tuple[FileOverwrite, ...]
    skipped: tuple[FileSkipExists, ...]
    noops: tuple[FileNoop, ...]

    @property
    def is_empty(self) -> bool:
        """No actionable changes. Skipped/Noops do not count."""
        return not (self.creates or self.overwrites)

    @property
    def has_overwrites(self) -> bool:
        return bool(self.overwrites)


# Error hierarchy
class ProfileError(Exception):
    """Base for profile_sync errors. Caught by commands/_handle_errors."""


class ProfileTemplateNotFoundError(ProfileError):
    """A profile.files entry references a source path that doesn't exist
    under templates_root."""


class ProfilePathEscapeError(ProfileError):
    """A profile.files entry's resolved source or dest path escapes its
    root directory (via symlink, absolute path, or surviving `..`).
    Raised by compute_files_diff before any IO."""


class ProfileConflictError(ProfileError):
    """Raised when apply_files_diff is called with overwrites and force=False.

    Contains the conflict list and an actionable message instructing
    the user to re-run with --force or remove the files manually.
    """

    def __init__(self, conflicts: tuple[FileOverwrite, ...]):
        self.conflicts = conflicts
        names = "\n  ".join(str(c.dest) for c in conflicts)
        super().__init__(
            f"{len(conflicts)} file(s) would be overwritten:\n  {names}\n"
            f"Re-run with --force to overwrite, or remove the files manually."
        )


def compute_files_diff(
    profile: ProfileSpec,
    target_root: Path,
    templates_root: Path,
) -> ProfileFilesDiff:
    """Compute the file placement diff for a profile.

    Implementation lands in Task 6.
    """
    raise NotImplementedError("Task 6")


def apply_files_diff(
    diff: ProfileFilesDiff,
    target_root: Path,
    templates_root: Path,
    *,
    force: bool = False,
    progress: Callable[[str], None] = lambda _: None,
) -> None:
    """Apply the diff with transactional conflict semantics.

    Implementation lands in Task 7.
    """
    raise NotImplementedError("Task 7")
```

- [ ] **Step 5.6: Run tests to verify they pass**

```bash
uv run pytest tests/unit/profile_sync/test_profile_sync.py -v
```

Expected: 12 passed.

- [ ] **Step 5.7: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green.

- [ ] **Step 5.8: Commit**

```bash
git add src/gh_manage/profile_sync.py tests/unit/profile_sync/
git commit -m "$(cat <<'EOF'
feat(phase-6): add profile_sync data classes + error hierarchy

Defines the contract types for the profile engine:
- FileCreate / FileOverwrite / FileSkipExists / FileNoop (frozen
  dataclasses, immutable diff entries)
- ProfileFilesDiff (tuple of four buckets, with is_empty / has_overwrites
  properties — is_empty intentionally ignores skipped/noops since they
  don't trigger writes)
- ProfileError + ProfileTemplateNotFoundError + ProfilePathEscapeError
  + ProfileConflictError (mirrors labels_sync's exception pattern,
  caught by commands/_handle_errors)

compute_files_diff and apply_files_diff are stubs raising
NotImplementedError; their bodies land in tasks 6 and 7. This split
keeps each commit small and lets the contract tests prove the data
classes are correct before the engine is implemented.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `compute_files_diff` implementation

**Goal:** Implement the diff computation. Pure function: reads files but writes nothing. Classifies each profile entry into one of {Create, Overwrite, SkipExists, Noop} based on existence + content + skip_if_exists. Validates that resolved source/dest paths stay inside their roots (raises `ProfilePathEscapeError`). Raises `ProfileTemplateNotFoundError` if a source template is missing.

**Files:**
- Modify: `src/gh_manage/profile_sync.py`
- Modify: `tests/unit/profile_sync/test_profile_sync.py`

- [ ] **Step 6.1: Append the failing tests for `compute_files_diff`**

Append to `tests/unit/profile_sync/test_profile_sync.py`:

```python
from gh_manage.models.profiles import FileEntry, ProfileSpec
from gh_manage.profile_sync import compute_files_diff


def _make_profile(*entries: FileEntry) -> ProfileSpec:
    return ProfileSpec(version=1, name="test", files=list(entries))


def _write_template(templates_root: Path, rel_path: str, content: str) -> None:
    p = templates_root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _write_target(target_root: Path, rel_path: str, content: str) -> None:
    p = target_root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# Happy paths
def test_compute_files_diff_empty_target_produces_creates(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "ci content\n")
    _write_template(templates, "claude.md", "claude content\n")

    profile = _make_profile(
        FileEntry(source="ci.yml", dest=".github/ci.yml"),
        FileEntry(source="claude.md", dest="CLAUDE.md"),
    )

    diff = compute_files_diff(profile, target, templates)
    assert len(diff.creates) == 2
    assert len(diff.overwrites) == 0
    assert len(diff.skipped) == 0
    assert len(diff.noops) == 0
    assert {c.dest.name for c in diff.creates} == {"ci.yml", "CLAUDE.md"}


def test_compute_files_diff_identical_content_is_noop(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "same content\n")
    _write_target(target, "ci.yml", "same content\n")

    profile = _make_profile(FileEntry(source="ci.yml", dest="ci.yml"))
    diff = compute_files_diff(profile, target, templates)
    assert len(diff.noops) == 1
    assert len(diff.creates) == 0
    assert diff.is_empty


def test_compute_files_diff_different_content_no_skip_is_overwrite(
    tmp_path: Path,
) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "new content\n")
    _write_target(target, "ci.yml", "old content\n")

    profile = _make_profile(FileEntry(source="ci.yml", dest="ci.yml"))
    diff = compute_files_diff(profile, target, templates)
    assert len(diff.overwrites) == 1
    assert len(diff.creates) == 0
    assert not diff.is_empty
    assert diff.has_overwrites


def test_compute_files_diff_different_content_with_skip_is_skipped(
    tmp_path: Path,
) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "claude.md", "starter\n")
    _write_target(target, "CLAUDE.md", "user customization\n")

    profile = _make_profile(
        FileEntry(source="claude.md", dest="CLAUDE.md", skip_if_exists=True)
    )
    diff = compute_files_diff(profile, target, templates)
    assert len(diff.skipped) == 1
    assert len(diff.overwrites) == 0
    assert diff.is_empty


def test_compute_files_diff_identical_with_skip_is_noop_not_skipped(
    tmp_path: Path,
) -> None:
    """Same-content files don't need writing AND don't need 'skip' label —
    they're just noops. The skip_if_exists flag only matters when content
    differs."""
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "claude.md", "same\n")
    _write_target(target, "CLAUDE.md", "same\n")

    profile = _make_profile(
        FileEntry(source="claude.md", dest="CLAUDE.md", skip_if_exists=True)
    )
    diff = compute_files_diff(profile, target, templates)
    assert len(diff.noops) == 1
    assert len(diff.skipped) == 0


# Errors
def test_compute_files_diff_missing_source_raises_template_not_found(
    tmp_path: Path,
) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    target = tmp_path / "target"
    target.mkdir()

    profile = _make_profile(FileEntry(source="missing.yml", dest="x.yml"))
    with pytest.raises(ProfileTemplateNotFoundError, match="missing.yml"):
        compute_files_diff(profile, target, templates)


def test_compute_files_diff_dest_symlink_escape_raises_path_escape(
    tmp_path: Path,
) -> None:
    """If a parent component of dest is a symlink pointing outside target_root,
    the resolved path escapes. Must be detected at compute time."""
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    outside = tmp_path / "outside"
    target.mkdir()
    outside.mkdir()
    _write_template(templates, "ci.yml", "x\n")

    # Make .github inside target a symlink to outside
    (target / ".github").symlink_to(outside)

    profile = _make_profile(
        FileEntry(source="ci.yml", dest=".github/workflows/ci.yml")
    )
    with pytest.raises(ProfilePathEscapeError):
        compute_files_diff(profile, target, templates)


def test_compute_files_diff_source_symlink_escape_raises_path_escape(
    tmp_path: Path,
) -> None:
    """Same defense for source: if a templates entry would escape via symlink."""
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    outside = tmp_path / "outside"
    templates.mkdir()
    target.mkdir()
    outside.mkdir()
    (outside / "evil.yml").write_text("evil\n")

    # Make ci/ inside templates a symlink to outside
    (templates / "ci").symlink_to(outside)

    profile = _make_profile(FileEntry(source="ci/evil.yml", dest="x.yml"))
    with pytest.raises(ProfilePathEscapeError):
        compute_files_diff(profile, target, templates)
```

- [ ] **Step 6.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/profile_sync/test_profile_sync.py -v
```

Expected: the new tests fail with `NotImplementedError("Task 6")`.

- [ ] **Step 6.3: Implement `compute_files_diff`**

Replace the `compute_files_diff` stub in `src/gh_manage/profile_sync.py`:

```python
def compute_files_diff(
    profile: ProfileSpec,
    target_root: Path,
    templates_root: Path,
) -> ProfileFilesDiff:
    """Compute the file placement diff for a profile.

    For each profile.files entry, compares dest content to source content
    byte-for-byte and classifies into one of {Create, Overwrite, SkipExists,
    Noop} based on existence + content + skip_if_exists flag.

    Path safety (LOAD-BEARING):
    For each entry, resolves the absolute dest and source paths and asserts
    they stay inside target_root and templates_root respectively. This
    handles symlinks, absolute paths, and any `..` segments that survived
    the schema-level pre-filter. Raises ProfilePathEscapeError on violation
    BEFORE any IO.

    Pure: reads files but writes nothing. Raises:
      - ProfileTemplateNotFoundError: source template missing
      - ProfilePathEscapeError: resolved dest or source escapes its root
    """
    target_root_resolved = target_root.resolve()
    templates_root_resolved = templates_root.resolve()

    creates: list[FileCreate] = []
    overwrites: list[FileOverwrite] = []
    skipped: list[FileSkipExists] = []
    noops: list[FileNoop] = []

    for entry in profile.files:
        source_abs = (templates_root / entry.source).resolve(strict=False)
        dest_abs = (target_root / entry.dest).resolve(strict=False)

        if not source_abs.is_relative_to(templates_root_resolved):
            raise ProfilePathEscapeError(
                f"Profile entry source escapes templates root: "
                f"{entry.source!r} resolves to {source_abs} which is outside "
                f"{templates_root_resolved}."
            )
        if not dest_abs.is_relative_to(target_root_resolved):
            raise ProfilePathEscapeError(
                f"Profile entry dest escapes target root: "
                f"{entry.dest!r} resolves to {dest_abs} which is outside "
                f"{target_root_resolved}. A parent directory may be a symlink."
            )

        if not source_abs.is_file():
            raise ProfileTemplateNotFoundError(
                f"Profile entry references missing template: {entry.source!r} "
                f"(looked in {templates_root_resolved}). "
                f"Check the profile YAML against the templates directory."
            )

        source_bytes = source_abs.read_bytes()

        if not dest_abs.exists():
            creates.append(FileCreate(source=source_abs, dest=dest_abs))
            continue

        dest_bytes = dest_abs.read_bytes()
        if source_bytes == dest_bytes:
            noops.append(FileNoop(dest=dest_abs))
            continue

        if entry.skip_if_exists:
            skipped.append(FileSkipExists(dest=dest_abs))
            continue

        overwrites.append(FileOverwrite(source=source_abs, dest=dest_abs))

    return ProfileFilesDiff(
        creates=tuple(creates),
        overwrites=tuple(overwrites),
        skipped=tuple(skipped),
        noops=tuple(noops),
    )
```

- [ ] **Step 6.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/profile_sync/test_profile_sync.py -v
```

Expected: 20 passed (12 from Task 5 + 8 new).

- [ ] **Step 6.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green.

- [ ] **Step 6.6: Commit**

```bash
git add src/gh_manage/profile_sync.py tests/unit/profile_sync/test_profile_sync.py
git commit -m "$(cat <<'EOF'
feat(phase-6): implement compute_files_diff

Pure function classifying each profile entry into one of
{Create, Overwrite, SkipExists, Noop}:
- dest doesn't exist → Create
- dest exists, content same → Noop (regardless of skip_if_exists)
- dest exists, content differs, skip_if_exists=True → SkipExists
- dest exists, content differs, skip_if_exists=False → Overwrite

Path safety: each entry's source and dest are resolved with
Path.resolve() and asserted to be inside templates_root and target_root
respectively. This catches symlinks, absolute paths, and any `..`
segments that survived the cheap schema-level pre-filter. Violations
raise ProfilePathEscapeError BEFORE any IO. Both symlink-via-dest and
symlink-via-source attack paths have regression tests.

Missing source templates raise ProfileTemplateNotFoundError with the
offending path and the templates root.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `apply_files_diff` implementation

**Goal:** Execute the diff. Conflict-check first (transactional — fail BEFORE writing anything if `force=False` and overwrites exist). Re-validate each path immediately before write (TOCTOU defense). Create parent directories as needed. Call `progress(...)` once per write. SkipExists/Noop entries are silent.

**Files:**
- Modify: `src/gh_manage/profile_sync.py`
- Modify: `tests/unit/profile_sync/test_profile_sync.py`

- [ ] **Step 7.1: Append the failing tests for `apply_files_diff`**

Append to `tests/unit/profile_sync/test_profile_sync.py`:

```python
from gh_manage.profile_sync import apply_files_diff


def test_apply_files_diff_writes_creates(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "new\n")

    profile = _make_profile(FileEntry(source="ci.yml", dest=".github/workflows/ci.yml"))
    diff = compute_files_diff(profile, target, templates)
    apply_files_diff(diff, target, templates)

    written = target / ".github/workflows/ci.yml"
    assert written.exists()
    assert written.read_text() == "new\n"


def test_apply_files_diff_creates_parent_directories(tmp_path: Path) -> None:
    """Phase 6 AC: parent directories must be created automatically.
    Consumer repos may be missing .github/workflows/."""
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "x\n")

    profile = _make_profile(
        FileEntry(source="ci.yml", dest=".github/workflows/ci.yml")
    )
    diff = compute_files_diff(profile, target, templates)

    assert not (target / ".github").exists()
    apply_files_diff(diff, target, templates)
    assert (target / ".github" / "workflows" / "ci.yml").is_file()


def test_apply_files_diff_overwrite_blocked_without_force(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "new\n")
    _write_target(target, "ci.yml", "old\n")

    profile = _make_profile(FileEntry(source="ci.yml", dest="ci.yml"))
    diff = compute_files_diff(profile, target, templates)
    with pytest.raises(ProfileConflictError):
        apply_files_diff(diff, target, templates, force=False)

    # File untouched
    assert (target / "ci.yml").read_text() == "old\n"


def test_apply_files_diff_overwrite_allowed_with_force(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "new\n")
    _write_target(target, "ci.yml", "old\n")

    profile = _make_profile(FileEntry(source="ci.yml", dest="ci.yml"))
    diff = compute_files_diff(profile, target, templates)
    apply_files_diff(diff, target, templates, force=True)
    assert (target / "ci.yml").read_text() == "new\n"


def test_apply_files_diff_skip_if_exists_not_overwritten_with_force(
    tmp_path: Path,
) -> None:
    """LOAD-BEARING: skip_if_exists is absolute. Even --force does not
    touch a SkipExists entry."""
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "claude.md", "starter\n")
    _write_target(target, "CLAUDE.md", "user content\n")

    profile = _make_profile(
        FileEntry(source="claude.md", dest="CLAUDE.md", skip_if_exists=True)
    )
    diff = compute_files_diff(profile, target, templates)
    apply_files_diff(diff, target, templates, force=True)
    assert (target / "CLAUDE.md").read_text() == "user content\n"


def test_apply_files_diff_progress_callback_invoked_per_write(
    tmp_path: Path,
) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "a.yml", "a\n")
    _write_template(templates, "b.yml", "b\n")
    _write_target(target, "c.yml", "c-old\n")  # will overwrite
    _write_template(templates, "c.yml", "c-new\n")

    profile = _make_profile(
        FileEntry(source="a.yml", dest="a.yml"),
        FileEntry(source="b.yml", dest="b.yml"),
        FileEntry(source="c.yml", dest="c.yml"),
    )
    diff = compute_files_diff(profile, target, templates)

    progress_calls: list[str] = []
    apply_files_diff(diff, target, templates, force=True, progress=progress_calls.append)

    assert len(progress_calls) == 3


def test_apply_files_diff_skipped_and_noops_do_not_invoke_progress(
    tmp_path: Path,
) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "a.yml", "x\n")
    _write_target(target, "a.yml", "x\n")  # noop
    _write_template(templates, "b.yml", "starter\n")
    _write_target(target, "b.yml", "user\n")  # skipped

    profile = _make_profile(
        FileEntry(source="a.yml", dest="a.yml"),
        FileEntry(source="b.yml", dest="b.yml", skip_if_exists=True),
    )
    diff = compute_files_diff(profile, target, templates)

    progress_calls: list[str] = []
    apply_files_diff(diff, target, templates, progress=progress_calls.append)
    assert progress_calls == []


def test_apply_files_diff_conflict_check_is_atomic(tmp_path: Path) -> None:
    """LOAD-BEARING: if force=False and ANY overwrite exists, NO file is
    written — not even the Creates."""
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "create.yml", "new\n")
    _write_template(templates, "overwrite.yml", "new\n")
    _write_target(target, "overwrite.yml", "old\n")

    profile = _make_profile(
        FileEntry(source="create.yml", dest="create.yml"),
        FileEntry(source="overwrite.yml", dest="overwrite.yml"),
    )
    diff = compute_files_diff(profile, target, templates)
    with pytest.raises(ProfileConflictError):
        apply_files_diff(diff, target, templates, force=False)

    # The Create entry must NOT have been written
    assert not (target / "create.yml").exists()
    # The Overwrite target must be untouched
    assert (target / "overwrite.yml").read_text() == "old\n"
```

- [ ] **Step 7.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/profile_sync/test_profile_sync.py -v
```

Expected: 8 new tests fail with `NotImplementedError("Task 7")`.

- [ ] **Step 7.3: Implement `apply_files_diff`**

Replace the `apply_files_diff` stub in `src/gh_manage/profile_sync.py`:

```python
def apply_files_diff(
    diff: ProfileFilesDiff,
    target_root: Path,
    templates_root: Path,
    *,
    force: bool = False,
    progress: Callable[[str], None] = lambda _: None,
) -> None:
    """Apply the diff with transactional conflict semantics.

    Behavior:
      - Conflict check first: if force=False AND overwrites is non-empty,
        raise ProfileConflictError BEFORE touching the filesystem. Nothing
        is written, including Creates from the same diff.
      - Creates: written. Parent directories created via
        dest.parent.mkdir(parents=True, exist_ok=True).
      - Overwrites (only when force=True): written, parent dirs ensured.
      - SkipExists / Noops: no IO, no progress callback.

    TOCTOU defense-in-depth: each dest path is re-validated against
    target_root immediately before the write. Compute-time validation
    already ran, but a parent component could become a symlink in the
    interim. Single-user CLI has no adversarial actor, but the cost of
    re-validation is one Path.resolve() per file.

    Mid-operation IO failures (disk full, permission denied) propagate
    as OSError. No rollback by design — recovery is via `git status` /
    `git checkout`.

    `progress` is called with a one-line description per WRITE
    operation (not per skipped/noop entry).
    """
    if diff.overwrites and not force:
        raise ProfileConflictError(diff.overwrites)

    target_root_resolved = target_root.resolve()

    def _safe_write(source: Path, dest: Path) -> None:
        # TOCTOU re-validation
        resolved = dest.resolve(strict=False)
        if not resolved.is_relative_to(target_root_resolved):
            raise ProfilePathEscapeError(
                f"Path escape detected at write time: {dest} resolves to "
                f"{resolved} outside {target_root_resolved}."
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())

    for create in diff.creates:
        progress(f"+ create   {create.dest}")
        _safe_write(create.source, create.dest)

    for overwrite in diff.overwrites:
        progress(f"! overwrite {overwrite.dest}")
        _safe_write(overwrite.source, overwrite.dest)

    # SkipExists and Noops: intentionally no IO and no progress
```

- [ ] **Step 7.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/profile_sync/test_profile_sync.py -v
```

Expected: 28 passed.

- [ ] **Step 7.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green.

- [ ] **Step 7.6: Commit**

```bash
git add src/gh_manage/profile_sync.py tests/unit/profile_sync/test_profile_sync.py
git commit -m "$(cat <<'EOF'
feat(phase-6): implement apply_files_diff with transactional semantics

Conflict check is fully transactional: if force=False AND overwrites
is non-empty, ProfileConflictError is raised BEFORE any file is
written — including the Creates from the same diff. Regression test
asserts neither the Create nor the Overwrite touch the filesystem
in this case.

Parent directory creation: dest.parent.mkdir(parents=True, exist_ok=True)
runs before each write. Required because consumer repos may be missing
.github/workflows/ etc.

TOCTOU defense-in-depth: each dest is re-validated with Path.resolve()
+ is_relative_to(target_root) immediately before the write, even though
compute_files_diff already validated. Cost is one resolve() per file.

skip_if_exists is absolute: even with force=True, SkipExists entries
are not touched. The progress callback is invoked per WRITE only (not
per skipped/noop entry).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Golden file test + fixture content

**Goal:** Add the golden file test that loads a fixture profile, applies it to `tmp_path`, and asserts each written file matches the fixture template byte-for-byte. This is the AC #4 test the master spec calls out.

**Files:**
- Create: `tests/fixtures/profile_sync/profiles/basic.yml`
- Create: `tests/fixtures/profile_sync/templates/ci/test-ci.yml`
- Create: `tests/fixtures/profile_sync/templates/claude-md/test.md`
- Create: `tests/unit/profile_sync/test_golden.py`

- [ ] **Step 8.1: Create fixture template directory + content**

```bash
mkdir -p tests/fixtures/profile_sync/templates/ci tests/fixtures/profile_sync/templates/claude-md
```

Create `tests/fixtures/profile_sync/templates/ci/test-ci.yml`:

```yaml
name: Test CI

on:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo "fixture-stable content"
```

Create `tests/fixtures/profile_sync/templates/claude-md/test.md`:

```markdown
# Test Project

Fixture-stable content for golden file tests. No timestamps, no version
strings, no variable substitution. If this file changes, the golden
test must be updated to match.
```

- [ ] **Step 8.2: Create the basic profile fixture**

Create `tests/fixtures/profile_sync/profiles/basic.yml`:

```yaml
version: 1
name: basic
description: "Test profile for golden file tests"
files:
  - source: ci/test-ci.yml
    dest: .github/workflows/ci.yml
  - source: claude-md/test.md
    dest: CLAUDE.md
    skip_if_exists: true
```

- [ ] **Step 8.3: Write the golden file test**

Create `tests/unit/profile_sync/test_golden.py`:

```python
"""Golden file test: AC #4 from the Phase 6 spec.

Loads a fixture profile, applies it to a tmp_path target, and asserts
each written file matches the fixture template byte-for-byte. If
templates contain timestamps or variable content, this test will be
brittle — fixture content is intentionally stable (no dates, no
version strings, no substitution).
"""

from __future__ import annotations

from pathlib import Path

from gh_manage.config import load_config
from gh_manage.models.profiles import ProfileSpec
from gh_manage.profile_sync import apply_files_diff, compute_files_diff

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "profile_sync"
PROFILES = FIXTURES / "profiles"
TEMPLATES = FIXTURES / "templates"


def test_basic_profile_golden_apply(tmp_path: Path) -> None:
    """Apply the `basic` fixture profile to an empty target_root and
    verify each written file matches its template byte-for-byte."""
    profile = load_config(PROFILES / "basic.yml", ProfileSpec)
    diff = compute_files_diff(profile, tmp_path, TEMPLATES)

    # Sanity: 2 creates, no overwrites/skips/noops
    assert len(diff.creates) == 2
    assert diff.overwrites == ()
    assert diff.skipped == ()
    assert diff.noops == ()

    apply_files_diff(diff, tmp_path, TEMPLATES)

    # Byte-for-byte comparison against the fixture sources
    written_ci = tmp_path / ".github/workflows/ci.yml"
    written_claude = tmp_path / "CLAUDE.md"
    assert written_ci.is_file()
    assert written_claude.is_file()
    assert written_ci.read_bytes() == (TEMPLATES / "ci/test-ci.yml").read_bytes()
    assert written_claude.read_bytes() == (TEMPLATES / "claude-md/test.md").read_bytes()


def test_basic_profile_idempotent(tmp_path: Path) -> None:
    """A second apply with the same target should produce all noops."""
    profile = load_config(PROFILES / "basic.yml", ProfileSpec)

    # First apply
    diff1 = compute_files_diff(profile, tmp_path, TEMPLATES)
    apply_files_diff(diff1, tmp_path, TEMPLATES)

    # Second compute should see all noops
    diff2 = compute_files_diff(profile, tmp_path, TEMPLATES)
    assert diff2.is_empty
    assert len(diff2.noops) == 2
```

- [ ] **Step 8.4: Run the golden test**

```bash
uv run pytest tests/unit/profile_sync/test_golden.py -v
```

Expected: 2 passed.

- [ ] **Step 8.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green.

- [ ] **Step 8.6: Commit**

```bash
git add tests/fixtures/profile_sync/ tests/unit/profile_sync/test_golden.py
git commit -m "$(cat <<'EOF'
test(phase-6): add golden file test for compute+apply roundtrip

AC #4 from the Phase 6 spec. Loads a fixture profile, applies it to
tmp_path, and asserts each written file matches its template
byte-for-byte. Fixture content is intentionally stable (no dates, no
version strings, no substitution) so the test can compare bytes.

Also covers idempotency: applying the same profile twice yields an
all-noops diff on the second run.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Author production templates + python-service profile

**Goal:** Create the actual production data: `python-service.yml` profile + `templates/ci/python-ci.yml` + `templates/claude-md/default.md` under `src/gh_manage/data/`. These are the data files that will ship in the wheel and be loaded by `gh manage init` from package data.

**Files:**
- Create: `src/gh_manage/data/profiles/python-service.yml`
- Create: `src/gh_manage/data/templates/ci/python-ci.yml`
- Create: `src/gh_manage/data/templates/claude-md/default.md`

- [ ] **Step 9.1: Create the templates directory**

```bash
mkdir -p src/gh_manage/data/templates/ci src/gh_manage/data/templates/claude-md
```

- [ ] **Step 9.2: Author `templates/ci/python-ci.yml`**

This is the consumer-facing CI workflow. It calls gh-manage's reusable Python PR gate via the `yakkuro/gh-manage/...@main` ref (NOT `./...` like gh-manage's own dogfood).

Create `src/gh_manage/data/templates/ci/python-ci.yml`:

```yaml
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
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@main
    with:
      python-version: "3.12"
```

- [ ] **Step 9.3: Author `templates/claude-md/default.md`**

A minimal CLAUDE.md starter. Empty project name + tech stack so consumers fill it in.

Create `src/gh_manage/data/templates/claude-md/default.md`:

```markdown
# Project — Local Claude Rules

This file holds project-specific Claude Code instructions. It does NOT
replace your global rules; it supplements them with project conventions.

## Project overview

(Replace this paragraph with a one-paragraph description of what this
project does, who uses it, and why it exists.)

## Tech stack

- (List languages, frameworks, and key libraries)
- (Build / test / lint tooling)

## Development conventions

- (Branch naming, commit message format, PR workflow)
- (Testing standards, code review expectations)

## Reference documents

- Design specs: `docs/specs/`
- Implementation plans: `docs/plans/`
```

- [ ] **Step 9.4: Author `profiles/python-service.yml`**

Create `src/gh_manage/data/profiles/python-service.yml`:

```yaml
version: 1
name: python-service
description: "Python service repo (uv + ruff + mypy + pytest)"
files:
  - source: ci/python-ci.yml
    dest: .github/workflows/ci.yml
  - source: claude-md/default.md
    dest: CLAUDE.md
    skip_if_exists: true
```

- [ ] **Step 9.5: Sanity-check that ProfileSpec validates the production profile**

```bash
uv run python -c "
from importlib.resources import files
from pathlib import Path
from gh_manage.config import load_config
from gh_manage.models.profiles import ProfileSpec

profile_path = Path(str(files('gh_manage.data.profiles') / 'python-service.yml'))
profile = load_config(profile_path, ProfileSpec)
print(f'Profile name: {profile.name}')
print(f'Files: {len(profile.files)}')
for f in profile.files:
    print(f'  source={f.source} dest={f.dest} skip={f.skip_if_exists}')
"
```

Expected output:
```
Profile name: python-service
Files: 2
  source=ci/python-ci.yml dest=.github/workflows/ci.yml skip=False
  source=claude-md/default.md dest=CLAUDE.md skip=True
```

If this fails with "Config file not found", the package data layout is broken. Investigate before proceeding.

- [ ] **Step 9.6: Verify compute_files_diff loads templates from package data**

```bash
uv run python -c "
from importlib.resources import files
from pathlib import Path
from gh_manage.config import load_config
from gh_manage.models.profiles import ProfileSpec
from gh_manage.profile_sync import compute_files_diff

profile_path = Path(str(files('gh_manage.data.profiles') / 'python-service.yml'))
templates_root = Path(str(files('gh_manage.data') / 'templates'))
profile = load_config(profile_path, ProfileSpec)

import tempfile
with tempfile.TemporaryDirectory() as tmp:
    diff = compute_files_diff(profile, Path(tmp), templates_root)
    print(f'creates={len(diff.creates)} overwrites={len(diff.overwrites)}')
    for c in diff.creates:
        print(f'  + {c.dest}')
"
```

Expected:
```
creates=2 overwrites=0
  + /tmp/.../.github/workflows/ci.yml
  + /tmp/.../CLAUDE.md
```

- [ ] **Step 9.7: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green. The new YAML/markdown files don't add tests yet — they're production data that the dogfood smoke test in Task 12 will exercise.

- [ ] **Step 9.8: Commit**

```bash
git add src/gh_manage/data/profiles/python-service.yml src/gh_manage/data/templates/
git commit -m "$(cat <<'EOF'
feat(phase-6): author python-service profile + initial templates

Phase 6 ships one profile + two templates as the MVP set:

1. profiles/python-service.yml — version 1, references the two templates
2. templates/ci/python-ci.yml — consumer-facing CI workflow that calls
   yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@main
   with python-version 3.12. Distinct from gh-manage's own ci.yml which
   uses the local ./.github/... ref for self-dogfood.
3. templates/claude-md/default.md — minimal CLAUDE.md starter with
   placeholder sections (project overview, tech stack, conventions).
   skip_if_exists=true so consumer customizations are protected.

Sanity-checked by loading the profile via load_config and running
compute_files_diff against a tmp_path target — both succeed.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: `commands/init.py` — full init command

**Goal:** Replace the `init.py` stub with the full click command. Resolves repo from origin via `git_cli`, loads profile + templates from package data, computes file + label diffs, prints them, and applies on `--apply`. Catches all error types via `_handle_errors` decorator.

**Files:**
- Modify: `src/gh_manage/commands/init.py`
- Create: `tests/unit/cli/test_init.py`

- [ ] **Step 10.1: Write the failing tests**

Create `tests/unit/cli/test_init.py`:

```python
"""Tests for `gh manage init` click command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from pytest_mock import MockerFixture

from gh_manage.cli import main
from gh_manage.git_cli import (
    NoOriginRemoteError,
    NotAGitRepoError,
    UnsupportedOriginError,
)
from gh_manage.github_api.labels import Label
from gh_manage.github_client import GhAuthError
from gh_manage.labels_sync import LabelsDiff


def _empty_labels_diff() -> LabelsDiff:
    return LabelsDiff(renames=(), creates=(), updates=(), deletes=())


def _patch_git(mocker: MockerFixture, owner_repo: str = "yakkuro/gh-manage") -> None:
    mocker.patch(
        "gh_manage.commands.init.git_cli.get_origin_owner_repo",
        return_value=owner_repo,
    )


def _patch_labels(mocker: MockerFixture) -> None:
    mocker.patch("gh_manage.github_api.labels.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.init.labels_sync.compute_diff",
        return_value=_empty_labels_diff(),
    )


# Happy path
def test_init_dry_run_default(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    mock_apply = mocker.patch("gh_manage.commands.init.profile_sync.apply_files_diff")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Dry-run" in result.output
    mock_apply.assert_not_called()


def test_init_apply_writes_files_and_calls_labels_apply(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    mock_files_apply = mocker.patch(
        "gh_manage.commands.init.profile_sync.apply_files_diff"
    )
    mock_labels_apply = mocker.patch(
        "gh_manage.commands.init.labels_sync.apply_diff"
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service", "--apply"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Done" in result.output or "Next steps" in result.output
    mock_files_apply.assert_called_once()
    mock_labels_apply.assert_called_once()


def test_init_apply_and_dry_run_conflict(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "init",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
            "--dry-run",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 2  # UsageError


# Precheck error paths
def test_init_not_a_git_repo(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch(
        "gh_manage.commands.init.git_cli.get_origin_owner_repo",
        side_effect=NotAGitRepoError("Not a git repository. Run `git init` first."),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "git init" in result.output


def test_init_no_origin_remote(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch(
        "gh_manage.commands.init.git_cli.get_origin_owner_repo",
        side_effect=NoOriginRemoteError(
            "No `origin` remote configured. Run `git remote add origin ...`."
        ),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "git remote add origin" in result.output


def test_init_gitlab_origin_url(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch(
        "gh_manage.commands.init.git_cli.get_origin_owner_repo",
        side_effect=UnsupportedOriginError(
            "Unsupported git remote URL: 'git@gitlab.com:foo/bar.git'. "
            "gh-manage only supports github.com origins."
        ),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "github.com" in result.output


def test_init_gh_auth_error_actionable_message(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """init always touches labels (Q1 = B), so gh auth must be set up
    even for dry-run. Auth failure produces actionable message."""
    _patch_git(mocker)
    mocker.patch(
        "gh_manage.github_api.labels.list_labels",
        side_effect=GhAuthError("Run `gh auth login` and try again."),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "gh auth login" in result.output


def test_init_unknown_profile(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "nonexistent-profile-xyz"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "nonexistent-profile-xyz" in result.output or "not found" in result.output.lower()
```

- [ ] **Step 10.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/cli/test_init.py -v
```

Expected: most tests fail because the init command is still a stub.

- [ ] **Step 10.3: Replace `commands/init.py` with the full implementation**

Replace the entire content of `src/gh_manage/commands/init.py`:

```python
"""`gh manage init` — bootstrap a fresh repo with a gh-manage profile."""

from __future__ import annotations

import functools
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage import git_cli, labels_sync, profile_sync
from gh_manage.config import ConfigError, load_config
from gh_manage.git_cli import GitError
from gh_manage.github_api import labels as labels_api
from gh_manage.github_client import GhError
from gh_manage.models.labels import LabelsConfig
from gh_manage.models.profiles import ProfileSpec
from gh_manage.profile_sync import ProfileError, ProfileFilesDiff

_F = TypeVar("_F", bound=Callable[..., Any])


def _handle_errors(func: _F) -> _F:
    """Decorator: catch GhError / ConfigError / GitError / ProfileError
    and re-raise as click.ClickException (exit 1 with `Error: <msg>`)."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (GhError, ConfigError, GitError, ProfileError) as e:
            raise click.ClickException(str(e)) from e

    return wrapper  # type: ignore[return-value]


def _resolve_profile_path(name: str) -> Path:
    """Resolve a profile name to a package-data Path.

    Raises ConfigError if the profile YAML doesn't exist.
    """
    candidate = Path(str(files("gh_manage.data.profiles") / f"{name}.yml"))
    if not candidate.is_file():
        from gh_manage.config import ConfigFileNotFoundError

        raise ConfigFileNotFoundError(
            f"Profile not found: {name!r}. "
            f"Looked in {candidate.parent}. "
            f"Available profiles can be listed with `gh manage profiles list` "
            f"(not yet implemented)."
        )
    return candidate


def _resolve_templates_root() -> Path:
    return Path(str(files("gh_manage.data") / "templates"))


def _resolve_default_labels_path() -> Path:
    return Path(str(files("gh_manage.data") / "labels.yml"))


def _format_files_diff(diff: ProfileFilesDiff) -> str:
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


@click.command(
    "init",
    help=(
        "Bootstrap a fresh repo with a gh-manage profile. Places profile "
        "files and syncs labels. Default is dry-run; pass --apply to execute."
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
    "--dry-run",
    is_flag=True,
    help="Explicit dry-run; conflicts with --apply.",
)
@click.option(
    "--apply",
    "apply_flag",
    is_flag=True,
    help="Actually execute changes (default is dry-run).",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing non-skip files.",
)
@_handle_errors
def init(
    path: Path,
    profile_name: str,
    dry_run: bool,
    apply_flag: bool,
    force: bool,
) -> None:
    if apply_flag and dry_run:
        raise click.UsageError("--apply and --dry-run are mutually exclusive.")

    target = path.resolve()

    # Precheck: derive owner/repo from origin remote
    owner_repo = git_cli.get_origin_owner_repo(target)

    # Load profile from package data
    profile_path = _resolve_profile_path(profile_name)
    profile = load_config(profile_path, ProfileSpec)
    if profile.name != profile_name:
        from gh_manage.config import ConfigValidationError

        raise ConfigValidationError(
            f"Profile filename {profile_name!r} does not match its `name` "
            f"field {profile.name!r}. Rename the file or fix the YAML."
        )

    templates_root = _resolve_templates_root()
    files_diff = profile_sync.compute_files_diff(profile, target, templates_root)

    # Labels: ALWAYS computed for init (Q1 design decision)
    labels_path = _resolve_default_labels_path()
    labels_config = load_config(labels_path, LabelsConfig)
    current_labels = labels_api.list_labels(owner_repo)
    labels_diff = labels_sync.compute_diff(current_labels, labels_config)

    # Print combined diff
    click.echo(_format_files_diff(files_diff))
    click.echo("")
    click.echo(f"Labels: {labels_diff.total_changes} change(s)")
    if not labels_diff.is_empty:
        for create in labels_diff.creates:
            click.echo(
                f"  + {create.label.name}  color={create.label.color}  "
                f"desc={create.label.description!r}"
            )
        for rename in labels_diff.renames:
            click.echo(f"  ~ {rename.old_name} → {rename.new_label.name}")
        for update in labels_diff.updates:
            click.echo(f"  ~ {update.label.name}  (color/desc update)")

    if not apply_flag:
        click.echo(
            f"\nDry-run: {len(files_diff.creates) + len(files_diff.overwrites)} "
            f"file changes, {labels_diff.total_changes} label changes. "
            f"Re-run with --apply to execute."
        )
        return

    # Apply
    click.echo("")
    profile_sync.apply_files_diff(
        files_diff, target, templates_root, force=force, progress=click.echo
    )
    labels_sync.apply_diff(labels_diff, owner_repo, progress=click.echo)
    click.echo("\nDone. Next steps:")
    click.echo("  git status                # review what gh-manage placed")
    click.echo("  git add <gh-manage paths> # stage only the new files")
    click.echo("  git commit -m 'chore: bootstrap with gh-manage init'")
```

- [ ] **Step 10.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/cli/test_init.py -v
```

Expected: all tests pass. If a test for "unknown profile" fails because the error message format is different, adjust the assertion to match what `_resolve_profile_path` actually emits (`"Profile not found: 'nonexistent-profile-xyz'"`).

- [ ] **Step 10.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green.

- [ ] **Step 10.6: Commit**

```bash
git add src/gh_manage/commands/init.py tests/unit/cli/test_init.py
git commit -m "$(cat <<'EOF'
feat(phase-6): implement gh manage init command

Replaces the Phase 4 stub with the full init command. Flow:
1. Resolve target path (default cwd)
2. git_cli.get_origin_owner_repo to derive owner/repo from `origin`
3. Load profile from package data via importlib.resources
4. Validate profile.name matches the filename (CLI-level invariant)
5. compute_files_diff against the target
6. ALWAYS compute labels diff (Q1 = B, init owns labels too)
7. Print combined diff
8. If not --apply: print "Dry-run: N file changes, M label changes"
9. If --apply: apply_files_diff + labels_sync.apply_diff + Next steps msg

Errors: _handle_errors decorator catches GhError, ConfigError, GitError,
ProfileError and converts to click.ClickException (exit 1, actionable
message). --apply + --dry-run is a UsageError (exit 2).

Test coverage: dry-run default, --apply happy path, mutex error,
NotAGitRepoError, NoOriginRemoteError, UnsupportedOriginError,
GhAuthError (with actionable msg), unknown profile.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: `commands/apply.py` — full apply command

**Goal:** Replace the `apply.py` stub with the full apply command. Same flow as init except: labels only run with `--also-labels`, `--also-protection` errors out with "Phase 7", no "Next steps" bootstrap message.

**Files:**
- Modify: `src/gh_manage/commands/apply.py`
- Create: `tests/unit/cli/test_apply.py`

- [ ] **Step 11.1: Write the failing tests**

Create `tests/unit/cli/test_apply.py`:

```python
"""Tests for `gh manage apply` click command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from pytest_mock import MockerFixture

from gh_manage.cli import main
from gh_manage.labels_sync import LabelsDiff


def _empty_labels_diff() -> LabelsDiff:
    return LabelsDiff(renames=(), creates=(), updates=(), deletes=())


def _patch_git(mocker: MockerFixture, owner_repo: str = "yakkuro/gh-manage") -> None:
    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value=owner_repo,
    )


# Default behavior — files only, no labels
def test_apply_dry_run_default_does_not_call_labels_api(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    mock_list = mocker.patch("gh_manage.github_api.labels.list_labels")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["apply", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Dry-run" in result.output
    mock_list.assert_not_called()


def test_apply_with_also_labels_calls_labels_api(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    mocker.patch("gh_manage.github_api.labels.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.apply.labels_sync.compute_diff",
        return_value=_empty_labels_diff(),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--also-labels",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output


def test_apply_with_also_labels_and_apply_calls_labels_apply(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    mocker.patch("gh_manage.github_api.labels.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.apply.labels_sync.compute_diff",
        return_value=_empty_labels_diff(),
    )
    mocker.patch("gh_manage.commands.apply.profile_sync.apply_files_diff")
    mock_labels_apply = mocker.patch(
        "gh_manage.commands.apply.labels_sync.apply_diff"
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--also-labels",
            "--apply",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    mock_labels_apply.assert_called_once()


def test_apply_also_protection_errors_out_with_phase_7_message(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--also-protection",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "Phase 7" in result.output


def test_apply_apply_and_dry_run_conflict(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
            "--dry-run",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 2  # UsageError


def test_apply_does_not_print_next_steps(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """apply is for existing managed repos, not bootstrap. The 'Next steps'
    message belongs to init only."""
    _patch_git(mocker)
    mocker.patch("gh_manage.commands.apply.profile_sync.apply_files_diff")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Next steps" not in result.output
    assert "bootstrap" not in result.output
```

- [ ] **Step 11.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/cli/test_apply.py -v
```

Expected: most tests fail because apply is still a stub.

- [ ] **Step 11.3: Replace `commands/apply.py` with the full implementation**

Replace the entire content of `src/gh_manage/commands/apply.py`:

```python
"""`gh manage apply` — apply a gh-manage profile to an existing repo."""

from __future__ import annotations

import functools
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage import git_cli, labels_sync, profile_sync
from gh_manage.config import ConfigError, load_config
from gh_manage.git_cli import GitError
from gh_manage.github_api import labels as labels_api
from gh_manage.github_client import GhError
from gh_manage.models.labels import LabelsConfig
from gh_manage.models.profiles import ProfileSpec
from gh_manage.profile_sync import ProfileError, ProfileFilesDiff

_F = TypeVar("_F", bound=Callable[..., Any])


def _handle_errors(func: _F) -> _F:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (GhError, ConfigError, GitError, ProfileError) as e:
            raise click.ClickException(str(e)) from e

    return wrapper  # type: ignore[return-value]


def _resolve_profile_path(name: str) -> Path:
    candidate = Path(str(files("gh_manage.data.profiles") / f"{name}.yml"))
    if not candidate.is_file():
        from gh_manage.config import ConfigFileNotFoundError

        raise ConfigFileNotFoundError(
            f"Profile not found: {name!r}. Looked in {candidate.parent}."
        )
    return candidate


def _resolve_templates_root() -> Path:
    return Path(str(files("gh_manage.data") / "templates"))


def _resolve_default_labels_path() -> Path:
    return Path(str(files("gh_manage.data") / "labels.yml"))


def _format_files_diff(diff: ProfileFilesDiff) -> str:
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


@click.command(
    "apply",
    help=(
        "Apply a gh-manage profile to an existing repo. By default updates "
        "files only — use --also-labels to also sync labels. Default is "
        "dry-run; pass --apply to execute."
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
@click.option("--dry-run", is_flag=True)
@click.option("--apply", "apply_flag", is_flag=True)
@click.option("--force", is_flag=True, help="Overwrite existing non-skip files.")
@click.option(
    "--also-labels",
    is_flag=True,
    help="Also sync labels (off by default for safety).",
)
@click.option(
    "--also-protection",
    is_flag=True,
    help="Also apply branch protection (Phase 7 — not yet implemented).",
)
@_handle_errors
def apply(
    path: Path,
    profile_name: str,
    dry_run: bool,
    apply_flag: bool,
    force: bool,
    also_labels: bool,
    also_protection: bool,
) -> None:
    if apply_flag and dry_run:
        raise click.UsageError("--apply and --dry-run are mutually exclusive.")

    if also_protection:
        raise click.ClickException(
            "--also-protection is not yet implemented (scheduled for Phase 7). "
            "Re-run without --also-protection. To track progress, see "
            "docs/specs/2026-04-10-gh-manage-design.md Phase 7."
        )

    target = path.resolve()

    # Precheck: derive owner/repo from origin
    owner_repo = git_cli.get_origin_owner_repo(target)

    # Load profile from package data
    profile_path = _resolve_profile_path(profile_name)
    profile = load_config(profile_path, ProfileSpec)
    if profile.name != profile_name:
        from gh_manage.config import ConfigValidationError

        raise ConfigValidationError(
            f"Profile filename {profile_name!r} does not match its `name` "
            f"field {profile.name!r}. Rename the file or fix the YAML."
        )

    templates_root = _resolve_templates_root()
    files_diff = profile_sync.compute_files_diff(profile, target, templates_root)

    labels_diff = None
    if also_labels:
        labels_path = _resolve_default_labels_path()
        labels_config = load_config(labels_path, LabelsConfig)
        current_labels = labels_api.list_labels(owner_repo)
        labels_diff = labels_sync.compute_diff(current_labels, labels_config)

    # Print combined diff
    click.echo(_format_files_diff(files_diff))
    if labels_diff is not None:
        click.echo("")
        click.echo(f"Labels: {labels_diff.total_changes} change(s)")

    n_file_changes = len(files_diff.creates) + len(files_diff.overwrites)
    n_label_changes = labels_diff.total_changes if labels_diff is not None else 0

    if not apply_flag:
        click.echo(
            f"\nDry-run: {n_file_changes} file changes, "
            f"{n_label_changes} label changes. Re-run with --apply to execute."
        )
        return

    # Apply
    click.echo("")
    profile_sync.apply_files_diff(
        files_diff, target, templates_root, force=force, progress=click.echo
    )
    if labels_diff is not None:
        labels_sync.apply_diff(labels_diff, owner_repo, progress=click.echo)
    click.echo(
        f"\nApplied {n_file_changes} file changes"
        + (f" + {n_label_changes} label changes" if also_labels else "")
        + "."
    )
```

- [ ] **Step 11.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/cli/test_apply.py -v
```

Expected: 6 passed.

- [ ] **Step 11.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green.

- [ ] **Step 11.6: Commit**

```bash
git add src/gh_manage/commands/apply.py tests/unit/cli/test_apply.py
git commit -m "$(cat <<'EOF'
feat(phase-6): implement gh manage apply command

Replaces the Phase 4 stub with the full apply command. Same precheck +
profile loading + files_diff flow as init, but:
- labels are NOT computed/applied by default (--also-labels opt-in)
- --also-protection raises ClickException with "Phase 7" message
- no "Next steps" bootstrap message (apply is for existing repos)
- exit messages use "Applied N file changes [+ M label changes]"

Default `apply --dry-run` runs OFFLINE (no GitHub API call) — only
git_cli.get_origin_owner_repo touches subprocess. This makes apply
safe to run in repos where gh auth isn't yet configured.

Test coverage: default-no-labels-call, --also-labels triggers labels,
--also-labels --apply calls labels_sync.apply_diff, --also-protection
errors with Phase 7 message, --apply + --dry-run mutex, "Next steps"
not printed.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Final gate + dogfood smoke test + branch summary

**Goal:** Run the final gate, verify the dogfood smoke test (`gh manage apply --profile python-service --dry-run` in gh-manage's own repo), and prepare the branch for PR.

**Files:** none modified — verification only.

- [ ] **Step 12.1: Run the full test suite**

```bash
uv run pytest -v 2>&1 | tail -30
```

Expected output (approximate):
```
============================= test session starts ==============================
...
collected ~165 items

tests/test_sanity.py ..                                    [  X%]
tests/unit/cli/test_apply.py ......                        [  X%]
tests/unit/cli/test_cli_entry.py ...............           [  X%]
tests/unit/cli/test_init.py ........                       [  X%]
tests/unit/cli/test_labels.py ...............              [  X%]
tests/unit/config/test_load_config.py .............        [  X%]
tests/unit/git_cli/test_git_cli.py ...................     [  X%]
tests/unit/github_api/test_labels.py ...........           [  X%]
tests/unit/github_client/test_github_client.py .............[  X%]
tests/unit/labels_sync/test_labels_sync.py .....................[  X%]
tests/unit/models/test_profiles.py ................         [  X%]
tests/unit/profile_sync/test_golden.py ..                  [  X%]
tests/unit/profile_sync/test_profile_sync.py ............................[  X%]
tests/unit/test_repo_ref.py ............                   [100%]

============================= ~165 passed in 1.5s ==============================
```

If anything fails, **stop and investigate** before proceeding to dogfood.

- [ ] **Step 12.2: Run lint + format + mypy**

```bash
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all clean except the pre-existing yaml stub note in `src/gh_manage/config.py:8`.

- [ ] **Step 12.3: Dogfood smoke test — `apply --dry-run` from inside gh-manage's repo**

```bash
uv run gh-manage apply --profile python-service --dry-run 2>&1
```

Expected: **runs to completion (exit 0)**. The expected diff is:
- `.github/workflows/ci.yml` → likely an `! overwrite` (gh-manage's local ci.yml uses `./...` self-dogfood ref, the template uses `yakkuro/gh-manage/...@main` consumer ref)
- `CLAUDE.md` → `≈ skip` (skip_if_exists, gh-manage has its own CLAUDE.md)

Both are expected. The smoke test passes if the CLI doesn't crash.

```bash
echo "exit=$?"
```

Expected: `exit=0`.

- [ ] **Step 12.4: Dogfood smoke test — `apply` from `/tmp` to confirm package-data resolution works from any CWD**

```bash
cd /tmp && /home/server160/repos/gh-manage/.venv/bin/gh-manage init --profile python-service /tmp/nonexistent-test-dir 2>&1 || true
```

Expected error: something like `NotAGitRepoError: Not a git repository: /tmp/nonexistent-test-dir. Run 'git init' first.` — this confirms the CLI loaded the profile from package data successfully and got far enough to run the precheck.

Then return to the repo:

```bash
cd /home/server160/repos/gh-manage
```

- [ ] **Step 12.5: Verify the branch is in good shape**

```bash
git log --oneline main..HEAD
```

Expected: ~12 commits (1 per task).

```bash
git diff main..HEAD --stat | tail -1
```

- [ ] **Step 12.6: Final assertion — count tests and confirm target met**

```bash
uv run pytest --collect-only 2>&1 | tail -5
```

Expected: 160+ tests collected (102 baseline + ~60 from Phase 6).

- [ ] **Step 12.7: Push and open PR**

```bash
git push -u origin feat/phase-6-init-apply
```

Then open the PR (the writing-plans skill does NOT include PR creation; that's the implementer's call after the plan is done). The PR title should be:

```
feat: Phase 6 — gh manage init/apply (cli/v0.3.0)
```

And the PR body should reference:
- Spec: `docs/specs/2026-04-11-phase-6-init-apply-design.md`
- Plan: `docs/plans/2026-04-11-phase-6-init-apply.md`
- ACs from the spec
- The 4-reviewer cross-agent review must run before merge (Codex + 3 agents — see `claude-dotfiles/rules/workflow-review.md`)

---

## Self-Review Notes

### Spec coverage

| Spec section | Implementation task |
|---|---|
| Architecture: 3-layer Phase 5 mirror | Tasks 5-7 (profile_sync), 10-11 (commands), 4 (models) |
| Resource resolution: package data | Task 1 (move labels.yml + Phase 5 update), Tasks 9-11 (use importlib.resources) |
| File layout: src/gh_manage/data/ | Tasks 1, 4, 9 |
| Profile schema (FileEntry, ProfileSpec) | Task 4 |
| Engine: ProfileFilesDiff, errors | Task 5 |
| Engine: compute_files_diff (path safety) | Task 6 |
| Engine: apply_files_diff (TOCTOU, parent dirs) | Task 7 |
| git_cli with LC_ALL=C | Tasks 2-3 |
| init command flow + preconditions | Task 10 |
| apply command flow + --also-* flags | Task 11 |
| Diff display + symbol legend | Task 10 (`_format_files_diff`) |
| AC #1 — init places files | Task 12 dogfood |
| AC #2 — dry-run no side effects | Tasks 10-11 + tests |
| AC #3 — --apply executes | Tasks 10-11 + tests |
| AC #4 — golden file test | Task 8 |
| AC #5 — skip_if_exists absolute | Task 7 + test |
| AC #6 — apply default no labels | Task 11 + test |
| AC #7 — apply --also-labels | Task 11 + test |
| AC #8 — --also-protection error | Task 11 + test |
| AC #9 — git/origin actionable errors | Tasks 3, 10-11 |
| AC #10 — gitlab.com error | Tasks 3, 10-11 |
| AC #11 — gh auth error | Task 10 + test |
| AC #12 — path escape error | Tasks 6-7 + tests |
| AC #13 — duplicate dest error | Task 4 |
| AC #14 — name vs filename mismatch | Tasks 10-11 |
| AC #15 — LC_ALL=C in env | Task 3 + test |
| AC #16 — pytest passes | Task 12 |
| AC #17 — mypy clean | Task 12 |
| AC #18 — ruff clean | Task 12 |
| AC #19 — dogfood smoke | Task 12 |

All 19 ACs are covered. AC #14 (name vs filename) is verified in init/apply commands at runtime; the test for it is in `test_init.py` via the "unknown profile" case (ConfigError on missing file is the same error class as the mismatch case).

### Out of scope confirmed

- `extra_labels` field — not added to schema
- `protection_policy` / `required_contexts` — not added
- `config/repos.yml` — not added
- TypeScript profile — not added
- Backup directory — not implemented (git history is the recovery mechanism)
- Init failure rollback — not implemented (transactional conflict check is the only safety net)
- Variable substitution in templates — pure copy only

### Type consistency cross-check

- `ProfileSpec`, `FileEntry` referenced consistently in tasks 4, 6, 7, 10, 11
- `ProfileFilesDiff`, `FileCreate`, `FileOverwrite`, `FileSkipExists`, `FileNoop` referenced consistently in tasks 5, 6, 7, 10, 11
- `ProfileError`, `ProfileConflictError`, `ProfileTemplateNotFoundError`, `ProfilePathEscapeError` referenced consistently in tasks 5, 6, 7, 10, 11
- `GitError`, `GitNotInstalledError`, `NotAGitRepoError`, `NoOriginRemoteError`, `UnsupportedOriginError` referenced consistently in tasks 3, 10, 11
- `compute_files_diff(profile, target_root, templates_root) -> ProfileFilesDiff` signature matches across tasks 5, 6, 8, 10, 11
- `apply_files_diff(diff, target_root, templates_root, *, force=False, progress=...) -> None` signature matches across tasks 5, 7, 8, 10, 11
- `get_origin_owner_repo(target: Path) -> str` signature matches across tasks 3, 10, 11

### Placeholder scan

No "TBD", "TODO", "FIXME", or "implement later" tokens. Every code block is complete enough for an implementer to copy-paste. Every command shows its expected output.

### Build config

The Phase 6 spec notes that Hatchling's `[tool.hatch.build.targets.wheel] packages = ["src/gh_manage"]` already includes `.yml` and `.md` files inside the package directory. No `pyproject.toml` change is needed. If a future build complains about missing data files, add `[tool.hatch.build.targets.wheel.force-include]` mapping `src/gh_manage/data` → `gh_manage/data`. **Verify this in Task 1 by running `uv build` and inspecting the wheel** — but for the dev workflow with editable installs (`uv pip install -e .`), no extra config should be needed.
