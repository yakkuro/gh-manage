# Phase 4 — CLI Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `cli/v0.1.0` — the first release on gh-manage's CLI tag track. Provides a working `gh manage --version` / `--help` via `gh extension install yakkuro/gh-manage`, scaffolds 6 stub subcommands (`init`, `apply`, `labels`, `protection`, `drift`, `issues`) for Phases 5-8, and establishes the generic config-loader framework with a validated `LabelsConfig` pydantic model.

**Architecture:** Three-layer CLI — `gh-manage` shell wrapper at repo root delegates to `uv run python -m gh_manage`, which enters `src/gh_manage/cli.py` (click Group) which dispatches to one of 6 stub files under `src/gh_manage/commands/`. All 6 commands are stubs that exit 1 with a "scheduled for cli/v0.X.0 (Phase N)" message. Domain logic lives in `src/gh_manage/config.py` (generic YAML loader) and `src/gh_manage/models/labels.py` (pydantic schema for `labels.yml` v1) — these are the ONLY real code units in Phase 4.

**Tech Stack:** Python 3.12 + uv + click 8.x + pydantic v2 + PyYAML 6 + pytest 8 + `click.testing.CliRunner`. No new dependencies — all four runtime deps and three dev deps are already pinned in `pyproject.toml`. The `gh-manage` shell wrapper uses bash with `set -euo pipefail`.

**Spec reference:** `docs/specs/2026-04-10-phase-4-cli-skeleton-design.md` (1022 lines, two rounds of spec-critique applied).

---

## File Structure

New / modified files after Phase 4 merges:

```
gh-manage/
├── gh-manage                              # NEW — executable bash wrapper, 100755
├── src/gh_manage/
│   ├── __init__.py                        # MODIFY — __version__ "0.0.0" → "0.1.0"
│   ├── __main__.py                        # NEW — enables `python -m gh_manage`
│   ├── cli.py                             # MODIFY — add -h alias, subcommand registration
│   ├── config.py                          # NEW — load_config() + ConfigError hierarchy
│   ├── models/
│   │   ├── __init__.py                    # NEW — empty package marker
│   │   └── labels.py                      # NEW — LabelsConfig, CategorySpec, LabelSpec
│   └── commands/
│       ├── __init__.py                    # NEW — empty package marker
│       ├── init.py                        # NEW — stub (scheduled: cli/v0.3.0 Phase 6)
│       ├── apply.py                       # NEW — stub (scheduled: cli/v0.3.0 Phase 6)
│       ├── labels.py                      # NEW — stub (scheduled: cli/v0.2.0 Phase 5)
│       ├── protection.py                  # NEW — stub (scheduled: cli/v0.4.0 Phase 7)
│       ├── drift.py                       # NEW — stub (scheduled: cli/v0.5.0 Phase 8)
│       └── issues.py                      # NEW — stub (scheduled: cli/v0.5.0 Phase 8)
├── tests/
│   ├── test_sanity.py                     # MODIFY — expect __version__ == "0.1.0"
│   ├── unit/                              # NEW package tree
│   │   ├── __init__.py                    # NEW
│   │   ├── cli/
│   │   │   ├── __init__.py                # NEW
│   │   │   └── test_cli_entry.py          # NEW — 5 test functions, 16 cases
│   │   └── config/
│   │       ├── __init__.py                # NEW
│   │       └── test_load_config.py        # NEW — 9 tests
│   └── fixtures/config/                   # NEW — data only, pytest-ignored
│       ├── labels-valid.yml               # NEW
│       ├── labels-invalid-missing-version.yml   # NEW
│       ├── labels-invalid-wrong-version.yml     # NEW
│       ├── labels-invalid-bad-yaml.yml          # NEW
│       ├── labels-invalid-not-mapping.yml       # NEW
│       ├── labels-invalid-bad-color.yml         # NEW
│       └── labels-invalid-empty-category.yml    # NEW
├── pyproject.toml                         # MODIFY — version "0.0.0" → "0.1.0"
├── CHANGELOG-cli.md                       # NEW — CLI tag track, independent from CHANGELOG-reusable.md
└── docs/usage/cli.md                      # NEW — CLI consumer guide
```

**File responsibilities:**

- `gh-manage` (wrapper): single point of contact for `gh extension install`. Checks uv presence + functionality, cd's into extension directory, execs `uv run python -m gh_manage "$@"`. No Python. No state.
- `__init__.py`: package marker + version constant. One line of logic.
- `__main__.py`: three-line module enabling `python -m gh_manage` invocation. Imports `cli.main` and calls it if `__name__ == "__main__"`.
- `cli.py`: click Group definition + subcommand registration. No domain logic.
- `commands/*.py`: one file per subcommand. Each is a 10-line stub in Phase 4. Phases 5-8 will fill each with real code.
- `config.py`: generic YAML loader (`load_config(path, model_cls, supported_versions)`) + 4-level `ConfigError` hierarchy. Handles file existence, YAML parsing, top-level-mapping check, schema version check, pydantic validation. Every error has an actionable message with the absolute path.
- `models/labels.py`: pydantic v2 schema for `labels.yml` version 1. Three classes: `LabelSpec`, `CategorySpec`, `LabelsConfig`. All use `ConfigDict(extra="forbid")`.
- `tests/unit/cli/test_cli_entry.py`: 5 test functions using `click.testing.CliRunner` → 16 total test cases exercising `--version`, `--help`, `-h`, 6 stub fires, 6 stub `--help` pass-throughs, 1 unknown-command.
- `tests/unit/config/test_load_config.py`: 9 pytest functions covering happy path + 6 failure modes + `__cause__` preservation for the validation-error chain.
- `tests/fixtures/config/*.yml`: 7 YAML data files (1 valid + 6 invalid) driving the loader tests. Excluded from pytest collection by the existing `--ignore=tests/fixtures` addopt.
- `CHANGELOG-cli.md`: independent track from `CHANGELOG-reusable.md`. Uses `cli/vX.Y.Z` tag prefix.
- `docs/usage/cli.md`: consumer guide — prerequisites, `gh extension install` instructions, phase roadmap, troubleshooting.

---

## Commit plan overview

Each task produces ONE commit. Conventional commit types are in parentheses.

1. (chore) Bootstrap: version bump + test scaffolding directories
2. (feat) Config domain: fixtures + `LabelsConfig` model + `load_config` + tests
3. (feat) CLI root + 6 command stubs + CLI smoke tests + `__main__.py`
4. (feat) Shell wrapper `gh-manage` with executable bit set in git
5. (docs) `CHANGELOG-cli.md` + `docs/usage/cli.md`
6. Final verification (no new commit): run ruff/mypy/pytest locally, verify git file mode, end-to-end smoke, push branch, open PR

Total: 5 commits. Task 6 is verification only.

---

## Task 1: Bootstrap — version bump + test scaffolding

**Files:**
- Modify: `src/gh_manage/__init__.py`
- Modify: `pyproject.toml` (line 3)
- Modify: `tests/test_sanity.py`
- Create: `tests/unit/__init__.py` (empty)
- Create: `tests/unit/cli/__init__.py` (empty)
- Create: `tests/unit/config/__init__.py` (empty)

- [ ] **Step 1.1: Bump `__version__` in `src/gh_manage/__init__.py`**

Full new file content:

```python
"""gh-manage: GitHub-based CI/CD, Issue management, and operational system."""

__version__ = "0.1.0"
```

- [ ] **Step 1.2: Bump `version` in `pyproject.toml` line 3**

Change line 3 from `version = "0.0.0"` to `version = "0.1.0"`. Do not touch any other lines in the file. Confirm the change with:

```bash
grep -n '^version' pyproject.toml
```

Expected output: `3:version = "0.1.0"`

- [ ] **Step 1.3: Update `tests/test_sanity.py` to expect the new version**

Full new file content (only the `"0.0.0"` literal is changed to `"0.1.0"`):

```python
"""Sanity tests that verify the Phase 0 scaffolding is wired correctly."""

from __future__ import annotations

import gh_manage


def test_package_version_is_defined() -> None:
    assert hasattr(gh_manage, "__version__")
    assert isinstance(gh_manage.__version__, str)
    assert gh_manage.__version__ == "0.1.0"


def test_cli_module_is_importable() -> None:
    from gh_manage import cli

    assert hasattr(cli, "main")
    assert callable(cli.main)
```

- [ ] **Step 1.4: Create the `tests/unit/` package tree**

```bash
mkdir -p tests/unit/cli tests/unit/config
touch tests/unit/__init__.py tests/unit/cli/__init__.py tests/unit/config/__init__.py
```

All three `__init__.py` files remain empty (package markers only).

- [ ] **Step 1.5: Run the sanity tests to confirm the version bump passes**

```bash
uv run pytest tests/test_sanity.py -v
```

Expected: both `test_package_version_is_defined` and `test_cli_module_is_importable` PASS. If `test_package_version_is_defined` fails with `AssertionError: assert '0.0.0' == '0.1.0'`, one of steps 1.1 or 1.3 was not applied correctly — fix and re-run.

- [ ] **Step 1.6: Commit**

```bash
git add src/gh_manage/__init__.py pyproject.toml tests/test_sanity.py tests/unit/
git commit -m "chore(phase-4): bump version to 0.1.0 + scaffold tests/unit/ package tree"
```

---

## Task 2: Config domain — fixtures + `LabelsConfig` model + `load_config` + tests

This task builds the entire config loading subsystem in one commit. Red-Green-Refactor TDD rhythm is preserved internally via step ordering: fixtures first (data), then the failing tests, then the implementation.

**Files:**
- Create: `tests/fixtures/config/labels-valid.yml`
- Create: `tests/fixtures/config/labels-invalid-missing-version.yml`
- Create: `tests/fixtures/config/labels-invalid-wrong-version.yml`
- Create: `tests/fixtures/config/labels-invalid-bad-yaml.yml`
- Create: `tests/fixtures/config/labels-invalid-not-mapping.yml`
- Create: `tests/fixtures/config/labels-invalid-bad-color.yml`
- Create: `tests/fixtures/config/labels-invalid-empty-category.yml`
- Create: `tests/unit/config/test_load_config.py`
- Create: `src/gh_manage/models/__init__.py` (empty marker)
- Create: `src/gh_manage/models/labels.py`
- Create: `src/gh_manage/config.py`

- [ ] **Step 2.1: Create `tests/fixtures/config/labels-valid.yml`**

```yaml
version: 1
categories:
  type:
    description: "Issue type labels"
    labels:
      - name: "bug"
        color: "d73a4a"
        description: "Something is broken"
      - name: "feat"
        color: "a2eeef"
        description: "New feature or request"
```

- [ ] **Step 2.2: Create `tests/fixtures/config/labels-invalid-missing-version.yml`**

```yaml
categories:
  type:
    description: "Issue type labels"
    labels:
      - name: "bug"
        color: "d73a4a"
```

- [ ] **Step 2.3: Create `tests/fixtures/config/labels-invalid-wrong-version.yml`**

```yaml
version: 99
categories:
  type:
    description: "Issue type labels"
    labels:
      - name: "bug"
        color: "d73a4a"
```

- [ ] **Step 2.4: Create `tests/fixtures/config/labels-invalid-bad-yaml.yml`**

```yaml
version: 1
categories:
  type:
    description: "unterminated
    labels:
      - name: bug
```

(This file has an unterminated string literal on the `description:` line — `yaml.safe_load` will raise `yaml.YAMLError`.)

- [ ] **Step 2.5: Create `tests/fixtures/config/labels-invalid-not-mapping.yml`**

```yaml
- version: 1
- categories: {}
```

(Top-level is a YAML sequence, not a mapping — `load_config` must raise `ConfigParseError` with the "must contain a YAML mapping" message.)

- [ ] **Step 2.6: Create `tests/fixtures/config/labels-invalid-bad-color.yml`**

```yaml
version: 1
categories:
  type:
    description: "Issue type labels"
    labels:
      - name: "bug"
        color: "not-a-color"
```

- [ ] **Step 2.7: Create `tests/fixtures/config/labels-invalid-empty-category.yml`**

```yaml
version: 1
categories:
  type:
    description: "Issue type labels"
    labels: []
```

- [ ] **Step 2.8: Create `tests/unit/config/test_load_config.py` with all 9 tests**

Full file content:

```python
"""Tests for gh_manage.config.load_config against LabelsConfig."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gh_manage.config import (
    ConfigFileNotFoundError,
    ConfigParseError,
    ConfigSchemaVersionError,
    ConfigValidationError,
    load_config,
)
from gh_manage.models.labels import LabelsConfig

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "config"


def test_load_valid_labels_yml_returns_typed_model() -> None:
    config = load_config(FIXTURES / "labels-valid.yml", LabelsConfig)
    assert isinstance(config, LabelsConfig)
    assert config.version == 1
    assert "type" in config.categories
    assert all(
        len(label.color) == 6
        for label in config.categories["type"].labels
    )


def test_missing_file_raises_not_found() -> None:
    with pytest.raises(ConfigFileNotFoundError, match="Config file not found"):
        load_config(FIXTURES / "does-not-exist.yml", LabelsConfig)


def test_malformed_yaml_raises_parse_error() -> None:
    with pytest.raises(ConfigParseError, match="Failed to parse YAML"):
        load_config(FIXTURES / "labels-invalid-bad-yaml.yml", LabelsConfig)


def test_top_level_list_raises_parse_error() -> None:
    with pytest.raises(ConfigParseError, match="must contain a YAML mapping"):
        load_config(FIXTURES / "labels-invalid-not-mapping.yml", LabelsConfig)


def test_missing_version_raises_schema_version_error() -> None:
    with pytest.raises(
        ConfigSchemaVersionError, match="missing the required `version:`"
    ):
        load_config(FIXTURES / "labels-invalid-missing-version.yml", LabelsConfig)


def test_unsupported_version_raises_schema_version_error() -> None:
    with pytest.raises(ConfigSchemaVersionError, match="unsupported version"):
        load_config(FIXTURES / "labels-invalid-wrong-version.yml", LabelsConfig)


def test_bad_color_raises_validation_error() -> None:
    with pytest.raises(ConfigValidationError, match="failed validation"):
        load_config(FIXTURES / "labels-invalid-bad-color.yml", LabelsConfig)


def test_empty_category_raises_validation_error() -> None:
    with pytest.raises(ConfigValidationError, match="failed validation"):
        load_config(FIXTURES / "labels-invalid-empty-category.yml", LabelsConfig)


def test_validation_error_preserves_cause() -> None:
    """pydantic's ValidationError should be available via __cause__."""
    with pytest.raises(ConfigValidationError) as excinfo:
        load_config(FIXTURES / "labels-invalid-bad-color.yml", LabelsConfig)
    assert isinstance(excinfo.value.__cause__, ValidationError)
```

- [ ] **Step 2.9: Run the tests to confirm Red (they must fail — the implementation doesn't exist yet)**

```bash
uv run pytest tests/unit/config/test_load_config.py -v
```

Expected: collection error or `ImportError: cannot import name 'load_config' from 'gh_manage.config'`. This confirms the test file is syntactically valid and the import-time failure is the expected Red state. If tests report anything *other* than ImportError or ModuleNotFoundError, debug the test file before continuing.

- [ ] **Step 2.10: Create `src/gh_manage/models/__init__.py` (empty marker)**

The file is literally empty. Create it with:

```bash
: > src/gh_manage/models/__init__.py
```

- [ ] **Step 2.11: Create `src/gh_manage/models/labels.py` with the `LabelsConfig` schema**

Full file content:

```python
"""Pydantic schema for config/labels.yml (version 1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LabelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    color: str = Field(pattern=r"^[0-9a-fA-F]{6}$")
    description: str | None = None


class CategorySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    labels: list[LabelSpec] = Field(min_length=1)


class LabelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    categories: dict[str, CategorySpec] = Field(min_length=1)
```

- [ ] **Step 2.12: Create `src/gh_manage/config.py` with the full `load_config` + exception hierarchy**

Full file content:

```python
"""YAML config loading with pydantic validation."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

_TModel = TypeVar("_TModel", bound=BaseModel)


class ConfigError(Exception):
    """Base exception for config loading failures."""


class ConfigFileNotFoundError(ConfigError):
    """Config file does not exist at the given path."""


class ConfigParseError(ConfigError):
    """YAML syntax error or top-level node is not a mapping."""


class ConfigSchemaVersionError(ConfigError):
    """`version:` field missing or not in supported_versions."""


class ConfigValidationError(ConfigError):
    """pydantic validation failed. Original ValidationError on __cause__."""


def load_config(
    path: Path | str,
    model_cls: type[_TModel],
    supported_versions: tuple[int, ...] = (1,),
) -> _TModel:
    """Load a YAML config file and validate it against `model_cls`.

    Raises a ConfigError subclass with an actionable message on any failure.
    Paths in error messages are always absolute so users can identify the file
    regardless of the current working directory.
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise ConfigFileNotFoundError(
            f"Config file not found: {path}. Check the path and try again."
        )

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigParseError(
            f"Failed to parse YAML in {path}: {e}. "
            f"Check the file for syntax errors."
        ) from e

    if not isinstance(raw, dict):
        raise ConfigParseError(
            f"Config file {path} must contain a YAML mapping at top level, "
            f"got {type(raw).__name__}."
        )

    version = raw.get("version")
    if version is None:
        raise ConfigSchemaVersionError(
            f"Config file {path} is missing the required `version:` field. "
            f"Supported versions: {supported_versions}."
        )
    if version not in supported_versions:
        raise ConfigSchemaVersionError(
            f"Config file {path} uses unsupported version {version!r}. "
            f"This gh-manage release supports versions {supported_versions}. "
            f"Upgrade gh-manage or downgrade the config file's `version:` "
            f"field to one of the supported versions."
        )

    try:
        return model_cls(**raw)
    except ValidationError as e:
        raise ConfigValidationError(
            f"Config file {path} failed validation:\n{e}"
        ) from e
```

- [ ] **Step 2.13: Run the tests to confirm Green**

```bash
uv run pytest tests/unit/config/test_load_config.py -v
```

Expected: all 9 tests PASS. Sample expected output:

```
tests/unit/config/test_load_config.py::test_load_valid_labels_yml_returns_typed_model PASSED
tests/unit/config/test_load_config.py::test_missing_file_raises_not_found PASSED
tests/unit/config/test_load_config.py::test_malformed_yaml_raises_parse_error PASSED
tests/unit/config/test_load_config.py::test_top_level_list_raises_parse_error PASSED
tests/unit/config/test_load_config.py::test_missing_version_raises_schema_version_error PASSED
tests/unit/config/test_load_config.py::test_unsupported_version_raises_schema_version_error PASSED
tests/unit/config/test_load_config.py::test_bad_color_raises_validation_error PASSED
tests/unit/config/test_load_config.py::test_empty_category_raises_validation_error PASSED
tests/unit/config/test_load_config.py::test_validation_error_preserves_cause PASSED
========================= 9 passed in 0.XX s =========================
```

If any test fails, fix the implementation and re-run. Do not proceed until all 9 pass.

- [ ] **Step 2.14: Red-Green verification — temporarily break one line to confirm the test actually catches regressions**

Temporarily comment out the `path = Path(path).resolve()` line in `src/gh_manage/config.py` (or change `Path(path).resolve()` to `Path(path)`) and run:

```bash
uv run pytest tests/unit/config/test_load_config.py::test_missing_file_raises_not_found -v
```

The test should STILL pass because even without `.resolve()`, `is_file()` returns False for a non-existent file. This is expected — path resolution is for error-message clarity, not functionality. Instead, break a different line to prove red-green:

Change line `if version not in supported_versions:` to `if version is not None and False:` and re-run:

```bash
uv run pytest tests/unit/config/test_load_config.py::test_unsupported_version_raises_schema_version_error -v
```

Expected: `FAILED ... DID NOT RAISE ConfigSchemaVersionError`. Revert the break. Re-run:

```bash
uv run pytest tests/unit/config/test_load_config.py -v
```

Expected: all 9 PASS.

- [ ] **Step 2.15: Commit**

```bash
git add tests/fixtures/config/ tests/unit/config/test_load_config.py \
        src/gh_manage/models/ src/gh_manage/config.py
git commit -m "$(cat <<'EOF'
feat(phase-4): add config loader + LabelsConfig pydantic model

- src/gh_manage/config.py: generic load_config(path, model_cls,
  supported_versions) with 4-level ConfigError hierarchy
  (ConfigFileNotFoundError, ConfigParseError, ConfigSchemaVersionError,
  ConfigValidationError). Paths resolved to absolute; files read as UTF-8;
  version mismatches show both found version and supported list.
- src/gh_manage/models/labels.py: LabelsConfig pydantic v2 schema for
  labels.yml v1. Enforces 6-char hex color, non-empty name, min 1 label
  per category, extra="forbid" on all three classes (LabelSpec,
  CategorySpec, LabelsConfig).
- tests/unit/config/test_load_config.py: 9 tests covering happy path +
  6 failure modes + __cause__ preservation.
- tests/fixtures/config/*.yml: 7 YAML fixtures (1 valid + 6 invalid)
  exercising every branch of load_config.
EOF
)"
```

---

## Task 3: CLI root + 6 command stubs + `__main__.py` + smoke tests

**Files:**
- Create: `src/gh_manage/__main__.py`
- Create: `src/gh_manage/commands/__init__.py` (empty marker)
- Create: `src/gh_manage/commands/init.py`
- Create: `src/gh_manage/commands/apply.py`
- Create: `src/gh_manage/commands/labels.py`
- Create: `src/gh_manage/commands/protection.py`
- Create: `src/gh_manage/commands/drift.py`
- Create: `src/gh_manage/commands/issues.py`
- Modify: `src/gh_manage/cli.py`
- Create: `tests/unit/cli/test_cli_entry.py`

- [ ] **Step 3.1: Create `src/gh_manage/__main__.py`**

Full file content:

```python
"""Entry point for `python -m gh_manage`. Delegates to the click CLI."""

from gh_manage.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 3.2: Create `src/gh_manage/commands/__init__.py` (empty marker)**

```bash
: > src/gh_manage/commands/__init__.py
```

- [ ] **Step 3.3: Create `src/gh_manage/commands/init.py`**

Full file content:

```python
"""`gh manage init` — initialize a new repo with a gh-manage profile.

Scheduled for cli/v0.3.0 (Phase 6).
"""

from __future__ import annotations

import sys

import click


@click.command(
    help="Initialize a new repo with a gh-manage profile (not yet implemented)."
)
def init() -> None:
    click.echo(
        "error: `gh manage init` is not yet implemented — "
        "scheduled for cli/v0.3.0 (Phase 6).",
        err=True,
    )
    sys.exit(1)
```

- [ ] **Step 3.4: Create `src/gh_manage/commands/apply.py`**

Full file content:

```python
"""`gh manage apply` — apply a gh-manage profile to existing repos.

Scheduled for cli/v0.3.0 (Phase 6).
"""

from __future__ import annotations

import sys

import click


@click.command(
    help="Apply gh-manage profiles to existing repos (not yet implemented)."
)
def apply() -> None:
    click.echo(
        "error: `gh manage apply` is not yet implemented — "
        "scheduled for cli/v0.3.0 (Phase 6).",
        err=True,
    )
    sys.exit(1)
```

- [ ] **Step 3.5: Create `src/gh_manage/commands/labels.py`**

Full file content:

```python
"""`gh manage labels` — label synchronization.

Scheduled for cli/v0.2.0 (Phase 5).
"""

from __future__ import annotations

import sys

import click


@click.command(
    help="Synchronize GitHub repo labels against config/labels.yml (not yet implemented)."
)
def labels() -> None:
    click.echo(
        "error: `gh manage labels` is not yet implemented — "
        "scheduled for cli/v0.2.0 (Phase 5).",
        err=True,
    )
    sys.exit(1)
```

- [ ] **Step 3.6: Create `src/gh_manage/commands/protection.py`**

Full file content:

```python
"""`gh manage protection` — branch protection synchronization.

Scheduled for cli/v0.4.0 (Phase 7).
"""

from __future__ import annotations

import sys

import click


@click.command(
    help="Synchronize branch protection (not yet implemented)."
)
def protection() -> None:
    click.echo(
        "error: `gh manage protection` is not yet implemented — "
        "scheduled for cli/v0.4.0 (Phase 7).",
        err=True,
    )
    sys.exit(1)
```

- [ ] **Step 3.7: Create `src/gh_manage/commands/drift.py`**

Full file content:

```python
"""`gh manage drift` — config drift scanner.

Scheduled for cli/v0.5.0 (Phase 8).
"""

from __future__ import annotations

import sys

import click


@click.command(
    help="Scan repos for config drift (not yet implemented)."
)
def drift() -> None:
    click.echo(
        "error: `gh manage drift` is not yet implemented — "
        "scheduled for cli/v0.5.0 (Phase 8).",
        err=True,
    )
    sys.exit(1)
```

- [ ] **Step 3.8: Create `src/gh_manage/commands/issues.py`**

Full file content:

```python
"""`gh manage issues` — cross-repo issue listing.

Scheduled for cli/v0.5.0 (Phase 8).
"""

from __future__ import annotations

import sys

import click


@click.command(
    help="Cross-repo issue listing (not yet implemented)."
)
def issues() -> None:
    click.echo(
        "error: `gh manage issues` is not yet implemented — "
        "scheduled for cli/v0.5.0 (Phase 8).",
        err=True,
    )
    sys.exit(1)
```

- [ ] **Step 3.9: Rewrite `src/gh_manage/cli.py` with `-h` alias and subcommand registration**

Full new file content (replaces the Phase 0 scaffolding):

```python
"""Top-level click group for gh-manage."""

from __future__ import annotations

import click

from gh_manage import __version__
from gh_manage.commands import (
    apply as apply_cmd,
    drift as drift_cmd,
    init as init_cmd,
    issues as issues_cmd,
    labels as labels_cmd,
    protection as protection_cmd,
)


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    help=(
        "gh-manage — GitHub-based CI/CD, Issue management, and operations "
        "for yakkuro/* repositories."
    ),
)
@click.version_option(version=__version__, prog_name="gh-manage")
def main() -> None:
    """Root command group. Subcommands are registered below."""


main.add_command(init_cmd.init)
main.add_command(apply_cmd.apply)
main.add_command(labels_cmd.labels)
main.add_command(protection_cmd.protection)
main.add_command(drift_cmd.drift)
main.add_command(issues_cmd.issues)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3.10: Create `tests/unit/cli/test_cli_entry.py` with all 5 test functions (16 cases)**

Full file content:

```python
"""Smoke tests for gh-manage CLI entry: --version, --help, and stub subcommands."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from gh_manage import __version__
from gh_manage.cli import main


def test_version_flag_outputs_semver() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
    assert "gh-manage" in result.output


def test_help_flag_lists_all_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for sub in ("init", "apply", "labels", "protection", "drift", "issues"):
        assert sub in result.output


def test_short_help_flag_works() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["-h"])
    assert result.exit_code == 0
    assert "Usage:" in result.output


@pytest.mark.parametrize(
    "subcommand",
    ["init", "apply", "labels", "protection", "drift", "issues"],
)
def test_stub_subcommand_exits_nonzero(subcommand: str) -> None:
    runner = CliRunner()
    result = runner.invoke(main, [subcommand])
    assert result.exit_code == 1
    assert "not yet implemented" in result.output


def test_unknown_subcommand_exits_with_click_usage_error() -> None:
    """Unknown subcommands should get click's standard usage error (exit code 2)."""
    runner = CliRunner()
    result = runner.invoke(main, ["totally-not-a-command"])
    assert result.exit_code == 2
    assert "No such command" in result.output or "Usage:" in result.output


@pytest.mark.parametrize(
    "subcommand",
    ["init", "apply", "labels", "protection", "drift", "issues"],
)
def test_stub_subcommand_help_shows_help_without_firing_stub(subcommand: str) -> None:
    """`gh manage <stub> --help` must display the subcommand's help text
    (exit 0) instead of firing the "not yet implemented" stub error (exit 1).
    click dispatches --help before invoking the command callback, so the
    stub's `sys.exit(1)` must NOT run."""
    runner = CliRunner()
    result = runner.invoke(main, [subcommand, "--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    # The stub callback must not have run — its error message starts with "error:".
    assert "error:" not in result.output
```

- [ ] **Step 3.11: Run the full CLI test suite to confirm Green**

```bash
uv run pytest tests/unit/cli/ -v
```

Expected: all 16 test cases PASS.

```
tests/unit/cli/test_cli_entry.py::test_version_flag_outputs_semver PASSED
tests/unit/cli/test_cli_entry.py::test_help_flag_lists_all_subcommands PASSED
tests/unit/cli/test_cli_entry.py::test_short_help_flag_works PASSED
tests/unit/cli/test_cli_entry.py::test_stub_subcommand_exits_nonzero[init] PASSED
tests/unit/cli/test_cli_entry.py::test_stub_subcommand_exits_nonzero[apply] PASSED
tests/unit/cli/test_cli_entry.py::test_stub_subcommand_exits_nonzero[labels] PASSED
tests/unit/cli/test_cli_entry.py::test_stub_subcommand_exits_nonzero[protection] PASSED
tests/unit/cli/test_cli_entry.py::test_stub_subcommand_exits_nonzero[drift] PASSED
tests/unit/cli/test_cli_entry.py::test_stub_subcommand_exits_nonzero[issues] PASSED
tests/unit/cli/test_cli_entry.py::test_unknown_subcommand_exits_with_click_usage_error PASSED
tests/unit/cli/test_cli_entry.py::test_stub_subcommand_help_shows_help_without_firing_stub[init] PASSED
tests/unit/cli/test_cli_entry.py::test_stub_subcommand_help_shows_help_without_firing_stub[apply] PASSED
tests/unit/cli/test_cli_entry.py::test_stub_subcommand_help_shows_help_without_firing_stub[labels] PASSED
tests/unit/cli/test_cli_entry.py::test_stub_subcommand_help_shows_help_without_firing_stub[protection] PASSED
tests/unit/cli/test_cli_entry.py::test_stub_subcommand_help_shows_help_without_firing_stub[drift] PASSED
tests/unit/cli/test_cli_entry.py::test_stub_subcommand_help_shows_help_without_firing_stub[issues] PASSED
========================= 16 passed in 0.XX s =========================
```

- [ ] **Step 3.12: Run the full test suite (sanity + cli + config) to confirm nothing regressed**

```bash
uv run pytest -v
```

Expected: all 27 tests PASS (2 sanity + 9 config + 16 CLI). The sanity test for `test_cli_module_is_importable` still passes because `cli.main` still exists and is callable (its shape is richer now, but the name + callable property are preserved).

- [ ] **Step 3.13: Run the CLI directly via `python -m gh_manage` to confirm the module entry works**

```bash
uv run python -m gh_manage --version
```

Expected output: `gh-manage, version 0.1.0` (exit 0)

```bash
uv run python -m gh_manage --help
```

Expected: click usage block listing all 6 subcommands. Exit 0.

```bash
uv run python -m gh_manage labels
```

Expected: `error: ` gh manage labels ` is not yet implemented — scheduled for cli/v0.2.0 (Phase 5).` on stderr, exit code 1. Check with:

```bash
uv run python -m gh_manage labels; echo "exit: $?"
```

Should show `exit: 1`.

- [ ] **Step 3.14: Commit**

```bash
git add src/gh_manage/__main__.py src/gh_manage/commands/ src/gh_manage/cli.py \
        tests/unit/cli/test_cli_entry.py
git commit -m "$(cat <<'EOF'
feat(phase-4): add CLI entry + 6 stub subcommands + smoke tests

- src/gh_manage/__main__.py: enables `python -m gh_manage` by importing
  and calling cli.main().
- src/gh_manage/cli.py: click group with -h/--help alias, --version flag,
  and registration of all 6 subcommands.
- src/gh_manage/commands/{init,apply,labels,protection,drift,issues}.py:
  6 stub subcommands. Each exits 1 with a "not yet implemented — scheduled
  for cli/v0.X.0 (Phase N)" message on stderr. Per-stub scheduled phases
  per the Phase 4 design spec.
- tests/unit/cli/test_cli_entry.py: 5 test functions, 16 total cases —
  --version, --help, -h, 6 stub fires, 1 unknown-command (click exit 2),
  6 stub --help pass-throughs (click dispatches --help before callback).
EOF
)"
```

---

## Task 4: Shell wrapper `gh-manage` with executable bit

**Files:**
- Create: `gh-manage` (repo root, bash script, executable)

- [ ] **Step 4.1: Create `gh-manage` at repo root**

Full file content:

```bash
#!/usr/bin/env bash
# gh-manage: gh CLI extension entry point.
# Delegates to the Python package via uv run, which handles virtualenv
# and dependency resolution automatically from pyproject.toml.
#
# Requires:
#   - uv on PATH and functional (not just present, also executable)
#   - Python 3.12+ resolvable by uv (uv auto-installs if missing)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: 'uv' is required to run gh-manage but was not found on PATH." >&2
  echo "Install via: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  echo "Or: brew install uv" >&2
  exit 1
fi

if ! uv --version >/dev/null 2>&1; then
  echo "error: 'uv' is on PATH but is not functional (uv --version failed)." >&2
  echo "The binary may be corrupted, have wrong permissions, or have a broken install." >&2
  echo "Try reinstalling: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

exec uv run python -m gh_manage "$@"
```

- [ ] **Step 4.2: Mark the wrapper executable on the filesystem**

```bash
chmod +x gh-manage
```

- [ ] **Step 4.3: Mark the executable bit in git's index (required — `chmod +x` only affects the filesystem, not git)**

```bash
git update-index --chmod=+x gh-manage
```

- [ ] **Step 4.4: Verify git will record the executable bit**

```bash
git ls-files --stage gh-manage
```

Expected output starts with `100755` (not `100644`):

```
100755 <hash> 0       gh-manage
```

If it shows `100644`, re-run Step 4.3 or check that `git config core.fileMode` is not set to `false`.

- [ ] **Step 4.5: Manual smoke — run the wrapper end-to-end**

```bash
./gh-manage --version
```

Expected: `gh-manage, version 0.1.0` (exit 0)

```bash
./gh-manage --help
```

Expected: click usage + 6 subcommands listed. Exit 0.

```bash
./gh-manage labels
```

Expected: `error: ` gh manage labels ` is not yet implemented — scheduled for cli/v0.2.0 (Phase 5).` on stderr. Exit 1. Confirm with:

```bash
./gh-manage labels; echo "exit: $?"
```

Should show `exit: 1`.

```bash
./gh-manage labels --help
```

Expected: subcommand help text with "Usage: main labels" and the description. Exit 0. This proves click dispatches `--help` before the stub's `sys.exit(1)`.

- [ ] **Step 4.6: Commit**

```bash
git add gh-manage
git commit -m "$(cat <<'EOF'
feat(phase-4): add gh-manage shell wrapper for gh extension install

Bash wrapper at repo root that gh CLI invokes when the user runs
`gh manage ...`. Delegates to `uv run python -m gh_manage "$@"` so
virtualenv and dep resolution are handled by uv from pyproject.toml.

Two-stage uv check:
1. `command -v uv` — catches "uv not installed"
2. `uv --version` — catches "uv present but binary broken/wrong perms"

Both failure paths print actionable install instructions to stderr.

Executable bit recorded in git's index via `git update-index --chmod=+x`
so `gh extension install` can run it directly after clone.
EOF
)"
```

- [ ] **Step 4.7: Post-commit verification — confirm the commit recorded the executable bit**

```bash
git show --stat HEAD | grep gh-manage
git show HEAD:gh-manage | head -5
```

The diff should reference `100755` mode for the new file.

```bash
git cat-file -p HEAD | grep tree
git ls-tree HEAD gh-manage
```

Expected: `100755 blob <hash>	gh-manage`

---

## Task 5: Documentation — `CHANGELOG-cli.md` + `docs/usage/cli.md`

**Files:**
- Create: `CHANGELOG-cli.md`
- Create: `docs/usage/cli.md`

- [ ] **Step 5.1: Create `CHANGELOG-cli.md`**

Full file content:

```markdown
# Changelog — CLI (src/gh_manage/)

All notable changes to the `gh-manage` Python CLI are documented here. This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The reusable workflow changelog lives in `CHANGELOG-reusable.md` and tracks independently under `v<major>.<minor>.<patch>` tags. CLI tags use the `cli/v<major>.<minor>.<patch>` prefix (see the main design spec's Versioning Strategy section).

## [Unreleased]

_Nothing yet._

## [0.1.0] - 2026-04-10

First release on the CLI track. This is the Phase 4 milestone: establishes the CLI entry point and the command tree for Phases 5-8, but does NOT implement any domain logic. All 6 subcommands are stubs that exit 1 with a "not yet implemented" message pointing at their scheduled phase.

### Added

- **`gh-manage` shell wrapper** at the repo root — executable entry point for `gh extension install`. Delegates to `uv run python -m gh_manage` so Python dependency management is handled by uv. Requires `uv` on the user's `PATH` (see `docs/usage/cli.md` prerequisites).
- **`src/gh_manage/__main__.py`** — enables `python -m gh_manage` invocation.
- **`src/gh_manage/cli.py`** — click group with `--version` and `--help`, registering 6 subcommands.
- **`src/gh_manage/commands/{init,apply,labels,protection,drift,issues}.py`** — 6 stub subcommands, each exiting 1 with a "scheduled for cli/v0.X.0 (Phase N)" message.
- **`src/gh_manage/config.py`** — generic YAML config loader with 4-level exception hierarchy (`ConfigFileNotFoundError`, `ConfigParseError`, `ConfigSchemaVersionError`, `ConfigValidationError`) rooted at `ConfigError`. The `load_config(path, model_cls, supported_versions)` entry point validates files against any pydantic model and raises subclass-typed errors with actionable messages.
- **`src/gh_manage/models/labels.py`** — pydantic schema for `labels.yml` version 1. Enforces 6-character hex color, non-empty label name, at least one label per category, and `extra="forbid"` to catch typos.
- **`tests/unit/cli/test_cli_entry.py`** — smoke tests using `click.testing.CliRunner` for `--version`, `--help`, `-h`, 6 stub subcommands, an unknown-subcommand case, and 6 subcommand `--help` pass-through cases.
- **`tests/unit/config/test_load_config.py`** — 9 tests covering the happy path and every failure mode of `load_config` with `LabelsConfig`.
- **`tests/fixtures/config/*.yml`** — 7 YAML fixture files (1 valid + 6 invalid) driving the config loader tests.
- **`docs/usage/cli.md`** — consumer-facing CLI installation, prerequisites, phase-to-command roadmap, and `--version` / `--help` demo output.
- **`CHANGELOG-cli.md`** — this file; starts the CLI tag track independently from the reusable workflows track (per the main design spec's Versioning Strategy § タグ系統).

### Changed

- **`src/gh_manage/__init__.py`** — `__version__` bumped from `"0.0.0"` to `"0.1.0"`.
- **`pyproject.toml`** — `version` bumped from `"0.0.0"` to `"0.1.0"`.
- **`tests/test_sanity.py`** — expected `__version__` bumped to `"0.1.0"`.

### Known limitations

- **No domain logic**: all subcommands are stubs. Running `gh manage labels` or any other subcommand exits 1 immediately. Real work lands in Phases 5-8.
- **`github_client.py` not yet present**: `gh` CLI subprocess wrapper is deferred to Phase 5 where it is first consumed by `labels sync`.
- **Only `LabelsConfig` is implemented**: `branch-protection.yml`, `repos.yml`, and profile models are deferred to their respective phases. The generic `load_config` framework is designed to accept any pydantic model, so adding each new model is a focused change.
- **`uv` is a hard dependency** on the user's machine. Documented in `docs/usage/cli.md`. The shell wrapper prints an actionable install instruction if uv is missing or non-functional.
- **Tested on Linux and macOS only**. Windows support is not explicitly targeted in v0.1.0.
- **No `gh extension upgrade` contract guarantees** beyond whatever the gh CLI's default behavior provides.

[Unreleased]: https://github.com/yakkuro/gh-manage/compare/cli/v0.1.0...HEAD
[0.1.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v0.1.0
```

- [ ] **Step 5.2: Create `docs/usage/cli.md`**

Full file content:

```markdown
# gh-manage CLI — Consumer Usage

> **Current state (cli/v0.1.0):** the CLI ships as a skeleton. `--version`, `--help`, and per-subcommand `--help` work. Every other subcommand is a stub that exits 1 with a "not yet implemented — scheduled for cli/v0.X.0 (Phase N)" message pointing at the roadmap below. Domain logic lands in Phases 5-8.

## What it is

`gh manage` is a [gh CLI extension](https://docs.github.com/en/github-cli/github-cli/using-github-cli-extensions) that will eventually manage labels, branch protection, issue/PR templates, and drift detection for `yakkuro/*` repositories. Phase 4 ships only the skeleton — see the roadmap below for when each subcommand becomes real.

## Prerequisites

Install all of these **before** running `gh extension install yakkuro/gh-manage`:

- [`uv`](https://docs.astral.sh/uv/) on your `PATH`. Install via `curl -LsSf https://astral.sh/uv/install.sh | sh` (Linux/macOS) or `brew install uv` (macOS). The wrapper will fail with an actionable error if `uv` is missing or non-functional.
- Python 3.12+ resolvable by `uv`. uv auto-installs the required interpreter on first run if it's missing — no manual Python install needed.
- [`gh` CLI](https://cli.github.com/) 2.x or newer. Required for `gh extension install`.
- `git` — required by `gh extension install` under the hood.

**Non-interactive environments (CI, containers, sandboxed shells):** the wrapper's error message tells interactive users how to install uv. CI/CD must provision uv via its own mechanism (e.g., a prior step in the same workflow) — the wrapper cannot self-heal.

**Platform support:** Linux and macOS are the tested platforms. Windows is not explicitly targeted in v0.1.0 (may work via WSL but is untested).

## Installation

```bash
gh extension install yakkuro/gh-manage
```

This clones `yakkuro/gh-manage` into `~/.local/share/gh/extensions/gh-manage/` and registers the `gh-manage` shell wrapper at the root of that clone as a `gh` subcommand.

## Verifying the install

```bash
gh manage --version
```

Expected output (v0.1.0):

```
gh-manage, version 0.1.0
```

```bash
gh manage --help
```

Expected output (truncated):

```
Usage: gh-manage [OPTIONS] COMMAND [ARGS]...

  gh-manage — GitHub-based CI/CD, Issue management, and operations for
  yakkuro/* repositories.

Options:
  --version     Show the version and exit.
  -h, --help    Show this message and exit.

Commands:
  apply       Apply gh-manage profiles to existing repos (not yet implemented).
  drift       Scan repos for config drift (not yet implemented).
  init        Initialize a new repo with a gh-manage profile (not yet implemented).
  issues      Cross-repo issue listing (not yet implemented).
  labels      Synchronize GitHub repo labels against config/labels.yml (not yet implemented).
  protection  Synchronize branch protection (not yet implemented).
```

## Subcommand roadmap

Target versions are planned, not binding — if phase scope shifts, these numbers move with them. The stub error messages in the current release match this table.

| Subcommand | Planned version | Phase | What it will do |
|---|---|---|---|
| `labels` | cli/v0.2.0 | Phase 5 | Synchronize GitHub repo labels against `config/labels.yml` |
| `init` | cli/v0.3.0 | Phase 6 | Initialize a new repo with a gh-manage profile |
| `apply` | cli/v0.3.0 | Phase 6 | Apply a gh-manage profile to an existing repo |
| `protection` | cli/v0.4.0 | Phase 7 | Synchronize branch protection rules |
| `drift` | cli/v0.5.0 | Phase 8 | Scan repos for configuration drift |
| `issues` | cli/v0.5.0 | Phase 8 | Cross-repo issue listing |

## Uninstalling

```bash
gh extension remove gh-manage
```

## Troubleshooting

### `uv` not found

The shell wrapper exits with:

```
error: 'uv' is required to run gh-manage but was not found on PATH.
Install via: curl -LsSf https://astral.sh/uv/install.sh | sh
Or: brew install uv
```

Install uv following the instructions above, then re-run `gh manage ...`.

### `uv` present but non-functional

```
error: 'uv' is on PATH but is not functional (uv --version failed).
```

The `uv` binary is installed but cannot run (wrong permissions, corrupted install, architecture mismatch). Reinstall via the install script in the message.

### `gh extension install` returns 404

Either the repo is private and your `gh auth status` lacks access, or the name is wrong. Confirm with:

```bash
gh repo view yakkuro/gh-manage
```

### "not yet implemented" errors

Every subcommand in v0.1.0 exits 1 with a stub message. This is expected — see the roadmap above for which phase lands each subcommand. Check the current release with `gh manage --version` against the planned version in the roadmap.

## See also

- Main design spec: [`docs/specs/2026-04-10-gh-manage-design.md`](../specs/2026-04-10-gh-manage-design.md)
- Phase 4 design spec: [`docs/specs/2026-04-10-phase-4-cli-skeleton-design.md`](../specs/2026-04-10-phase-4-cli-skeleton-design.md)
- Reusable workflow consumer guides: [`docs/usage/python.md`](./python.md), [`docs/usage/typescript.md`](./typescript.md)
- Changelog: [`CHANGELOG-cli.md`](../../CHANGELOG-cli.md)
```

- [ ] **Step 5.3: Commit**

```bash
git add CHANGELOG-cli.md docs/usage/cli.md
git commit -m "$(cat <<'EOF'
docs(phase-4): add CHANGELOG-cli.md [0.1.0] + docs/usage/cli.md

- CHANGELOG-cli.md: new independent track for the Python CLI, separate
  from CHANGELOG-reusable.md. Keep a Changelog format. Lists all files
  created/modified in Phase 4 and the known limitations (all subcommands
  are stubs, uv is a hard prereq, Linux/macOS only).
- docs/usage/cli.md: consumer guide with prerequisites (uv before
  install, non-interactive env caveat), gh extension install walkthrough,
  verification commands, phase-to-command roadmap table, troubleshooting
  for uv-missing / uv-broken / 404 / not-yet-implemented.
EOF
)"
```

---

## Task 6: Final verification gate (no commits)

This task runs the full reusable gate locally, verifies the git executable bit survived the commits, runs the end-to-end smoke, and opens the PR. No new code is written.

- [ ] **Step 6.1: Run `ruff check` on the full repo**

```bash
uv run ruff check .
```

Expected: `All checks passed!` or equivalent clean output. If violations are reported in any of the Phase 4 files, fix them before proceeding. Likely categories: unused imports, line length, isort ordering.

- [ ] **Step 6.2: Run `ruff format --check`**

```bash
uv run ruff format --check .
```

Expected: clean. If files need reformatting, run `uv run ruff format .` (without `--check`) to apply, inspect the diff, then commit the format-only changes as `style(phase-4): apply ruff format`.

- [ ] **Step 6.3: Run `mypy src`**

```bash
uv run mypy src
```

Expected: `Success: no issues found in X source files`. If mypy reports type errors in the new code:
- For pydantic v2 with BaseModel generics, consider adding `from __future__ import annotations` (already present in all new files).
- For the `TypeVar("_TModel", bound=BaseModel)` in `config.py`, this is standard and should not require any type-ignore.
- Do NOT add `# type: ignore` without a justifying explanation in the comment.

- [ ] **Step 6.4: Run the full test suite**

```bash
uv run pytest -v
```

Expected: **27 tests PASS** (2 sanity + 9 config + 16 CLI).

```
======================== 27 passed in X.XX s ========================
```

- [ ] **Step 6.5: Verify the git executable bit on `gh-manage` survived the subsequent commits**

```bash
git ls-files --stage gh-manage
```

Expected: `100755 <hash> 0	gh-manage`. If it shows `100644`, run `git update-index --chmod=+x gh-manage` and amend the commit that introduced the file (or create a fix-up commit explaining).

- [ ] **Step 6.6: Run the end-to-end smoke via the shell wrapper**

```bash
./gh-manage --version
```

Expected: `gh-manage, version 0.1.0` exit 0.

```bash
./gh-manage --help
```

Expected: click help block with 6 subcommands.

```bash
./gh-manage -h
```

Expected: same as `--help` (short-flag alias).

```bash
for sub in init apply labels protection drift issues; do
  echo "=== gh manage ${sub} ==="
  ./gh-manage "${sub}"
  echo "exit: $?"
done
```

Expected for each: error message on stderr, exit code 1.

```bash
for sub in init apply labels protection drift issues; do
  echo "=== gh manage ${sub} --help ==="
  ./gh-manage "${sub}" --help
  echo "exit: $?"
done
```

Expected for each: click help for the subcommand, exit 0 (no error message).

```bash
./gh-manage totally-not-a-command
echo "exit: $?"
```

Expected: click usage error with `No such command`, exit 2.

Capture the full output of all three loops into a scratch file — the PR body will reference this verification. Suggested:

```bash
{
  echo "### gh-manage shell wrapper smoke (local)"
  ./gh-manage --version
  echo
  ./gh-manage --help
  echo
  for sub in init apply labels protection drift issues; do
    echo "$ ./gh-manage ${sub}"
    ./gh-manage "${sub}" 2>&1 || echo "  (exit $?)"
  done
} > /tmp/phase-4-smoke.txt
cat /tmp/phase-4-smoke.txt
```

- [ ] **Step 6.7: Push the branch to origin**

```bash
git push -u origin feat/phase-4-cli-skeleton
```

Expected: fast-forward push. If push is rejected due to pre-push hook, read the hook output carefully — do NOT use `--no-verify`.

- [ ] **Step 6.8: Confirm dogfood CI started and passes**

```bash
gh pr list --head feat/phase-4-cli-skeleton
```

If no PR exists yet, create one in the next step. If a PR already exists, check its CI:

```bash
gh pr checks feat/phase-4-cli-skeleton --watch
```

Expected: all checks green (the `PR Gate (self-dogfood)` check runs the full reusable gate against the PR head SHA). If red, read the CI logs via `gh run view <run-id> --log-failed` and fix.

- [ ] **Step 6.9: Open the PR**

```bash
gh pr create --title "feat: Phase 4 — CLI skeleton (cli/v0.1.0)" --body "$(cat <<'EOF'
## Summary

Ship `cli/v0.1.0` — the first release on gh-manage's CLI tag track.

- `gh-manage` shell wrapper at repo root + `gh extension install yakkuro/gh-manage` contract
- `src/gh_manage/cli.py` + `__main__.py` + 6 stub subcommands (`init`, `apply`, `labels`, `protection`, `drift`, `issues`)
- `src/gh_manage/config.py` generic YAML loader + 4-level `ConfigError` hierarchy
- `src/gh_manage/models/labels.py` pydantic v2 `LabelsConfig` schema for `labels.yml` v1
- 25 new tests (16 CLI smoke + 9 config loader); 27 total
- `CHANGELOG-cli.md` [0.1.0] + `docs/usage/cli.md` consumer guide
- Zero new dependencies — click/pydantic/pyyaml/pytest already pinned

## Design spec

`docs/specs/2026-04-10-phase-4-cli-skeleton-design.md` (1022 lines, two rounds of spec-critique applied).

## Scope

Strictly a skeleton. All 6 subcommands are stubs that exit 1 with a "scheduled for cli/v0.X.0 (Phase N)" message. No real `labels sync`, no `github_client.py`, no branch-protection / repos / profile models. Those land in Phases 5-8 per the main design spec.

## Local verification

- `uv run ruff check .` — clean
- `uv run ruff format --check .` — clean
- `uv run mypy src` — clean
- `uv run pytest -v` — 27 passed
- `./gh-manage --version` → `gh-manage, version 0.1.0`
- `./gh-manage --help` → lists 6 subcommands
- `./gh-manage labels` → `error: ... not yet implemented — scheduled for cli/v0.2.0 (Phase 5).` exit 1
- `./gh-manage labels --help` → subcommand help, exit 0 (click dispatches --help before stub callback)
- `./gh-manage totally-not-a-command` → click usage error, exit 2
- `git ls-files --stage gh-manage` → `100755` (executable bit recorded)

## Test plan (post-merge)

- [ ] 4-reviewer cross-agent review (Codex + superpowers:code-reviewer + silent-failure-hunter + code-reviewer)
- [ ] Merge to main after CRITICAL/HIGH findings resolved
- [ ] Tag `cli/v0.1.0` on main
- [ ] Create GitHub release `cli/v0.1.0` with `--latest=false` (reusable track's v0.2.1 stays "latest")
- [ ] Smoke test `gh extension install yakkuro/gh-manage` on a clean machine, run `gh manage --version`, remove

Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

Expected: PR URL printed. Save it for the 4-reviewer review task.

- [ ] **Step 6.10: Hand off to Task #47 (4-reviewer review)**

At this point Phase 4 implementation is complete, the PR is open, and CI is running. The next task in the parent TaskList is the 4-reviewer cross-agent review per `claude-dotfiles/rules/workflow-review.md`. That task reviews this plan's output and is NOT part of the writing-plans skill's execution.

---

## Self-Review

Completed against the spec (`docs/specs/2026-04-10-phase-4-cli-skeleton-design.md`). Notes recorded inline:

**1. Spec coverage:**
- All 17 Acceptance Criteria items map to steps in Tasks 1-6 (version bump → Task 1; fixture tests → Task 2; CLI tests → Task 3; `gh-manage` wrapper + executable bit → Task 4; CHANGELOG + docs → Task 5; git ls-files verification + PR + dogfood CI → Task 6).
- All Components in the spec have corresponding create/modify steps with full code shown.
- All error-handling requirements (no silent failures, 4-level exception hierarchy, UTF-8 reading, absolute path resolution, `from e` preservation) are encoded in the exact code shown in Task 2.
- All test cases (9 config + 16 CLI = 25) are shown verbatim in Tasks 2 and 3.
- The Phase-to-command mapping in the spec matches the per-stub error messages in Task 3 (labels → cli/v0.2.0 Phase 5, init/apply → cli/v0.3.0 Phase 6, protection → cli/v0.4.0 Phase 7, drift/issues → cli/v0.5.0 Phase 8).

**2. Placeholder scan:**
- No "TBD", "TODO", "implement later", "fill in details".
- No "add error handling", "add validation", "handle edge cases".
- Every test is fully specified with code.
- No "similar to Task N" — each task has its own complete code (commands are intentionally repeated verbatim across the 6 stub files for mechanical clarity).
- Every `Step X.Y` has a code block or an exact command.

**3. Type consistency:**
- `load_config(path, model_cls, supported_versions)` signature identical in Task 2 code and Task 2 test imports.
- `LabelsConfig` / `CategorySpec` / `LabelSpec` class names match between Task 2 implementation and Task 2 tests.
- `main` (the click Group) is imported the same way in `cli.py`, `__main__.py`, and `test_cli_entry.py`.
- `ConfigError` subclasses match between `config.py` (Task 2.12) and `test_load_config.py` (Task 2.8).
- Each stub subcommand's module name (e.g., `commands/labels.py`) matches the import in `cli.py` (`from gh_manage.commands import labels as labels_cmd`) and the function name (`labels()`).

No issues found. Plan is ready for execution.

---

## Execution handoff

**Plan complete and saved to `docs/plans/2026-04-10-phase-4-cli-skeleton.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, apply the two-stage review (Stage 1: spec compliance, Stage 2: code quality) between tasks, and fast-iterate. Per the user's standing preference (`feedback_execution_mode.md`), this is the default for non-trivial plans.

**2. Inline Execution** — Execute all tasks in this session using `superpowers:executing-plans` with batch execution and checkpoints for review.

Proceeding with **Subagent-Driven** per standing preference unless the user redirects.
