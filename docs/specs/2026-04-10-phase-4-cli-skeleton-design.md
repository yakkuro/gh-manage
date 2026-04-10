# Phase 4 — CLI Skeleton (Design Spec)

## Metadata

- **Date**: 2026-04-10
- **Size**: Medium
- **Target**: `yakkuro/gh-manage`
- **Related**: [`docs/specs/2026-04-10-gh-manage-design.md`](./2026-04-10-gh-manage-design.md) (§ Python CLI, § Phase 4 Acceptance Criteria, § Versioning Strategy)
- **Supersedes**: nothing; first release on the CLI track

## Sizing Rationale

**Medium**. Phase 4 bootstraps a new Python CLI surface that will grow across Phases 5-8. It touches multiple layers: a new `src/gh_manage/commands/` package with 6 subcommand stubs, a new `src/gh_manage/config.py` + `models/labels.py` generic config-loader framework, a new `src/gh_manage/__main__.py` entry, a new `gh-manage` shell wrapper at repo root (for `gh extension install`), new test suites under `tests/unit/cli/` and `tests/unit/config/` with YAML fixtures, a new `CHANGELOG-cli.md` track, and a new `docs/usage/cli.md` consumer guide. Design judgement is required on distribution mechanism (resolved: uv-backed shell wrapper), scope boundary (resolved: scaffold all 6 subcommand stubs), config-loader generality (resolved: generic loader + labels model only), and deferral of `github_client.py` (resolved: defer to Phase 5). Larger than Small (single file, no design judgement) but smaller than Large (new repository or new top-level module). A single implementation plan can execute it without sub-decomposition.

## Goal

Ship `cli/v0.1.0` — the first release on gh-manage's CLI tag track. Provide a working `gh manage --version` and `gh manage --help` via `gh extension install yakkuro/gh-manage`, scaffold the command tree for Phases 5-8, and establish the generic config-loader framework with a validated `LabelsConfig` pydantic model. No command does real work yet (all subcommands are stubs that error out); the point is to lock in the directory layout, entry points, error semantics, and test scaffolding so Phase 5+ can focus on domain logic rather than plumbing.

## Acceptance Criteria

Direct mapping from `docs/specs/2026-04-10-gh-manage-design.md` lines 850-858, with Phase 4-internal refinements:

- [ ] `gh extension install yakkuro/gh-manage` succeeds as a **manual post-tag smoke test** (not a CI gate — see § Testing Strategy → "gh extension install smoke"). Runs locally after `cli/v0.1.0` is pushed, on a machine with `uv` on PATH, `gh` CLI 2.x+, `git`, and network access. Documented in `docs/usage/cli.md` prerequisites. If the smoke fails, cut a hotfix `cli/v0.1.1`
- [ ] `gh manage --version` outputs `gh-manage, version 0.1.0` and exits 0
- [ ] `gh manage -h` and `gh manage --help` both display the subcommand list (6 entries: `init`, `apply`, `labels`, `protection`, `drift`, `issues`) and exit 0
- [ ] Each of the 6 stubbed subcommands errors with `error: \`gh manage <name>\` is not yet implemented — scheduled for cli/v0.X.0 (Phase N).` on stderr and exits 1
- [ ] `uv run pytest tests/unit/config` passes — all `LabelsConfig` validation tests including a valid fixture and 5+ invalid fixture patterns (missing version, wrong version, bad YAML, top-level list, bad hex color, empty category)
- [ ] `uv run pytest tests/unit/cli` passes — all CLI smoke tests for `--version`, `--help`, `-h`, each of the 6 stub subcommands (stub fires with exit 1), each of the 6 subcommand `--help` flows (click's help dispatches before the stub, exit 0), and an unknown-subcommand case (click usage error, exit 2)
- [ ] `uv run pytest` passes in total (existing `tests/test_sanity.py` + new unit tests)
- [ ] Invalid `labels.yml` produces an actionable error message (path, reason, suggested fix) from the `ConfigError` exception hierarchy
- [ ] `src/gh_manage/__init__.py` has `__version__ = "0.1.0"`
- [ ] `pyproject.toml` has `version = "0.1.0"` (bumped from `"0.0.0"`)
- [ ] `CHANGELOG-cli.md` exists with `[0.1.0] - 2026-04-10` entry
- [ ] `docs/usage/cli.md` exists with installation prerequisites, `gh extension install` instructions, phase-to-command roadmap, and expected output demos
- [ ] `gh-manage` executable shell wrapper exists at repo root with the executable bit set in git — verify via `git ls-files --stage gh-manage` and confirm the mode starts with `100755` (not `100644`). PR template includes this as a reviewer checklist item.
- [ ] Annotated tag `cli/v0.1.0` exists on `main` after merge
- [ ] GitHub Release `cli/v0.1.0` published with CHANGELOG excerpt
- [ ] 4-reviewer cross-agent review complete with no open CRITICAL/HIGH findings
- [ ] gh-manage's own `ci.yml` (Python self-dogfood via `reusable-pr-gate-python.yml`) remains green through the entire PR — the full reusable gate (ruff + ruff format --check + mypy on `src/` + pytest) must pass on the new code

## Architecture

### Directory layout after Phase 4

```
gh-manage/
├── gh-manage                              # NEW — executable shell wrapper (repo root)
├── src/gh_manage/
│   ├── __init__.py                        # MODIFY — __version__ "0.0.0" → "0.1.0"
│   ├── __main__.py                        # NEW — python -m gh_manage → cli.main()
│   ├── cli.py                             # MODIFY — add 6 subcommand registrations
│   ├── config.py                          # NEW — generic YAML loader + pydantic validation
│   ├── models/
│   │   ├── __init__.py                    # NEW — empty package marker
│   │   └── labels.py                      # NEW — LabelsConfig, CategorySpec, LabelSpec
│   └── commands/
│       ├── __init__.py                    # NEW — empty package marker
│       ├── init.py                        # NEW — stub
│       ├── apply.py                       # NEW — stub
│       ├── labels.py                      # NEW — stub
│       ├── protection.py                  # NEW — stub
│       ├── drift.py                       # NEW — stub
│       └── issues.py                      # NEW — stub
├── tests/
│   ├── test_sanity.py                     # MODIFY — bump expected __version__ to "0.1.0"
│   └── unit/
│       ├── __init__.py                    # NEW
│       ├── cli/
│       │   ├── __init__.py                # NEW
│       │   └── test_cli_entry.py          # NEW — CliRunner smoke tests
│       └── config/
│           ├── __init__.py                # NEW
│           └── test_load_config.py        # NEW — load_config + LabelsConfig tests
├── tests/fixtures/config/                 # NEW — YAML fixtures (data, not tests)
│   ├── labels-valid.yml
│   ├── labels-invalid-missing-version.yml
│   ├── labels-invalid-wrong-version.yml
│   ├── labels-invalid-bad-yaml.yml
│   ├── labels-invalid-not-mapping.yml
│   ├── labels-invalid-bad-color.yml
│   └── labels-invalid-empty-category.yml
├── pyproject.toml                         # MODIFY — version bump to 0.1.0
├── CHANGELOG-cli.md                       # NEW — CLI tag track (separate from CHANGELOG-reusable.md)
└── docs/usage/cli.md                      # NEW — CLI consumer guide
```

### 3-layer CLI design

```
Layer 3: CLI entry (cli.py)
  └─ click.Group, version_option, subcommand registration.
     No business logic — only argv routing.

Layer 2: Commands (commands/*.py)
  └─ One file per subcommand. Each @click.command() is the thin shell
     that parses its own options and delegates to Layer 1 domain logic.
     In Phase 4 all 6 commands are stubs that print and exit.

Layer 1: Domain logic (config.py, models/, future github_client.py)
  └─ Pure Python, no click. Independently testable without CliRunner.
     Phase 4 ships config.py + models/labels.py. Phase 5 adds
     github_client.py and starts filling in the command bodies.
```

### gh extension distribution contract

`gh extension install yakkuro/gh-manage` follows gh CLI's "non-precompiled extension" model: it clones the repo into `~/.local/share/gh/extensions/gh-manage/` and expects a `gh-<name>` executable at the root. We ship a shell wrapper that delegates to `uv run python -m gh_manage`, pushing Python dependency resolution to uv.

Runtime invocation sequence for `gh manage --version`:

1. User runs `gh manage --version`
2. gh CLI resolves `manage` → extension directory
3. gh execs `gh-manage --version` (the wrapper)
4. Wrapper opens with `set -euo pipefail`, cd's into `$(dirname "${BASH_SOURCE[0]}")`
5. Wrapper checks `command -v uv`; missing → stderr error + exit 1 with install instructions
6. Wrapper `exec uv run python -m gh_manage "$@"`
7. uv reads `pyproject.toml`, creates `.venv` if missing, installs pinned deps from `uv.lock`, runs the Python command
8. `python -m gh_manage` imports `src/gh_manage/__main__.py`, calls `cli.main()`
9. click parses `--version`, prints `gh-manage, version 0.1.0`, exits 0

### Hard requirements for the user machine

- `uv` on `PATH` (Phase 0 already documented this as a first-class dependency of gh-manage)
- Python 3.12+ resolvable by uv (uv auto-installs if missing)
- `gh` CLI 2.x+ (for extension install)
- `git` (gh extension install uses git under the hood)

These are documented in `docs/usage/cli.md` prerequisites.

### Non-goals for cli/v0.1.0

- Real work in any subcommand (all 6 are stubs; domain logic lands in Phase 5-8)
- `github_client.py` (deferred to Phase 5 where labels sync first needs it)
- pydantic models for `branch-protection.yml`, `repos.yml`, or profiles (deferred to Phases 6-8 as each is first consumed)
- CHANGELOG promotion automation; promoted manually before tag, same flow as the reusable track
- `gh extension upgrade` guarantees beyond the default gh CLI behavior
- Binary distribution (PyInstaller, shiv) — uv is the single supported runner
- Windows support beyond whatever uv + Python 3.12 + gh CLI provide (we target Linux/macOS primarily; no hostile testing on Windows)
- **Config file discovery strategy** — Phase 4 ships `load_config(path, model_cls)` which takes an explicit path. How commands locate their config files (e.g., `--config <path>`, `./labels.yml`, repo root search) is a decision for each command when it becomes non-stub in Phase 5+. Phase 4 deliberately does not prescribe a search strategy so Phase 5+ can pick per-command based on actual needs.
- **i18n / localization** — all help text, error messages, and docs are English-only in v0.1.0. Not planned for v0.x.y.

## Components

### `gh-manage` shell wrapper (repo root, executable)

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

Marked executable via `chmod +x gh-manage` AND committed with the executable bit using `git update-index --chmod=+x gh-manage` so gh CLI can run it directly after clone.

### `src/gh_manage/__init__.py` (modify)

```python
"""gh-manage: GitHub-based CI/CD, Issue management, and operational system."""

__version__ = "0.1.0"
```

### `src/gh_manage/__main__.py` (new)

```python
"""Entry point for `python -m gh_manage`. Delegates to the click CLI."""

from gh_manage.cli import main

if __name__ == "__main__":
    main()
```

### `src/gh_manage/cli.py` (modify)

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
```

### `src/gh_manage/commands/*.py` (6 stubs, identical pattern)

Each stub is ~10 lines. Example — `src/gh_manage/commands/labels.py`:

```python
"""`gh manage labels` — label synchronization. Scheduled for cli/v0.2.0 (Phase 5)."""

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

Phase-to-command mapping. The versions listed are *planned targets*, not currently-released tags. The mapping is non-binding — if Phase 5 splits or merges a command, these numbers shift, and the stub strings are updated in that phase's PR.

| Subcommand | Stub message | Scheduled phase |
|---|---|---|
| `labels` | scheduled for cli/v0.2.0 (Phase 5) | Phase 5 — label sync |
| `init` | scheduled for cli/v0.3.0 (Phase 6) | Phase 6 — init/apply |
| `apply` | scheduled for cli/v0.3.0 (Phase 6) | Phase 6 — init/apply |
| `protection` | scheduled for cli/v0.4.0 (Phase 7) | Phase 7 — protection sync |
| `drift` | scheduled for cli/v0.5.0 (Phase 8) | Phase 8 — drift scanner |
| `issues` | scheduled for cli/v0.5.0 (Phase 8) | Phase 8 — cross-repo issues |

Stubs are verbatim copies except for the subcommand name, help text, and scheduled phase reference. `docs/usage/cli.md` links to the same roadmap table so users who see the stub error can find the authoritative "when".

### `src/gh_manage/config.py` (new)

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
    # Normalize to an absolute path so error messages are unambiguous even
    # when the caller passes a relative path.
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

Explicit contract:

- **Paths are resolved to absolute** before use (`Path(path).resolve()`) so that error messages always show the fully-qualified file path regardless of the user's current working directory. Tests use absolute fixture paths already and therefore don't change behavior.
- **Files are read as UTF-8** (`read_text(encoding="utf-8")`) to avoid locale-dependent encoding bugs on Windows or non-UTF-8 systems.
- **Version mismatch errors include both the found version and the supported list** so the user can choose between upgrading gh-manage or editing the config file.

**Schema evolution strategy (forward-looking note).** `load_config` accepts a `supported_versions: tuple[int, ...]` parameter defaulted to `(1,)` so a future `cli/v0.3.0` can pass `(1, 2)` and temporarily support both versions during a migration window. The concrete migration path (how v1 configs are converted to v2, deprecation warnings, CLI `gh manage config migrate` subcommand) is a Phase 5+ decision and is deliberately out of scope for Phase 4. Phase 4 only commits to: (a) the `supported_versions` parameter exists, (b) the error message on mismatch clearly names both the found version and the supported set.

### `src/gh_manage/models/labels.py` (new)

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

`extra="forbid"` enforces that unknown fields cause validation errors. `pattern=r"^[0-9a-fA-F]{6}$"` enforces 6-character hex color. `min_length=1` on category list forbids empty `labels:`.

### `pyproject.toml` (modify)

Bump `version = "0.0.0"` to `version = "0.1.0"`. No other changes — click, pydantic, pyyaml are already in `dependencies`, and pytest + pytest-cov + pytest-mock are in `[dependency-groups.dev]`.

### `CHANGELOG-cli.md` (new)

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
- **`tests/unit/cli/test_cli_entry.py`** — smoke tests using `click.testing.CliRunner` for `--version`, `--help`, `-h`, and all 6 stub subcommands.
- **`tests/unit/config/test_load_config.py`** — 8+ tests covering the happy path and every failure mode of `load_config` with `LabelsConfig`.
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
- **`uv` is a hard dependency** on the user's machine. Documented in `docs/usage/cli.md`. The shell wrapper prints an actionable install instruction if uv is missing.
- **Tested on Linux and macOS only**. Windows support is not explicitly targeted in v0.1.0.
- **No `gh extension upgrade` contract guarantees** beyond whatever the gh CLI's default behavior provides.

[Unreleased]: https://github.com/yakkuro/gh-manage/compare/cli/v0.1.0...HEAD
[0.1.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v0.1.0
```

### `docs/usage/cli.md` (new)

Structural outline (exact text drafted during writing-plans phase):

- **Title**: "gh-manage CLI — Consumer Usage"
- **What it is**: 2-3 sentence summary
- **Prerequisites**: `uv` installed and on `PATH` **before** running `gh extension install`, Python 3.12+ resolvable by uv (uv auto-installs if missing), `gh` CLI 2.x+, `git`. Explicit note: non-interactive environments (CI, sandboxed shells) must install uv first via their own provisioning step — the wrapper's error message is for interactive users only and cannot self-heal.
- **Installation**: `gh extension install yakkuro/gh-manage`
- **Phase 4 scope / current state**: all subcommands are stubs, only `--version` and `--help` do real work
- **Minimal example**: `gh manage --version` + expected output block
- **Subcommand roadmap**: table showing scheduled phase for each subcommand
- **Uninstalling**: `gh extension remove gh-manage`
- **Troubleshooting**: `uv` not found, `gh extension install` 404 (repo visibility / auth), "not yet implemented" errors (link to roadmap)
- **See also**: reusable workflow usage docs (`python.md`, `typescript.md`), main design spec

## Data Flow

### CLI invocation sequence (`gh manage --version`)

```
1. User runs: gh manage --version
2. gh CLI resolves "manage" → ~/.local/share/gh/extensions/gh-manage/
3. gh exec's the gh-manage wrapper with args=["--version"]
4. Wrapper: set -euo pipefail; cd SCRIPT_DIR; check uv; exec uv run python -m gh_manage --version
5. uv reads pyproject.toml, ensures .venv, runs the module
6. Python: import src/gh_manage/__main__.py → cli.main()
7. click parses --version, matches @click.version_option
8. Output to stdout: gh-manage, version 0.1.0
9. Process exits 0
```

### `gh manage --help` output (stdout)

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

Exit 0. click sorts commands alphabetically by default.

### Stub subcommand invocation (e.g. `gh manage labels`)

```
1-7. (same as --version flow up through cli.main())
8. click dispatches to commands.labels.labels() function
9. labels() prints to stderr: "error: `gh manage labels` is not yet implemented — scheduled for cli/v0.2.0 (Phase 5)."
10. labels() calls sys.exit(1)
11. Process exits 1
```

### Config loading flow (internal, exercised by tests)

```
1. Test calls: load_config(tests/fixtures/config/labels-valid.yml, LabelsConfig)
2. load_config:
   a. path.is_file() → True → proceed
   b. yaml.safe_load(path.read_text()) → dict
   c. isinstance(raw, dict) → True
   d. raw["version"] → 1, in supported_versions (1,) → proceed
   e. LabelsConfig(**raw) → validated instance
   f. Returns validated LabelsConfig
3. Test asserts instance type and field values
```

Invalid file flow (e.g., `labels-invalid-bad-color.yml`):

```
1-2d. Same as above
2e. LabelsConfig(**raw) → ValidationError (color does not match regex)
2f. load_config wraps: raise ConfigValidationError(...) from ValidationError
3. Test asserts ConfigValidationError is raised, __cause__ is ValidationError
```

### Test discovery and execution flow

```
1. CI: gh-manage's ci.yml invokes reusable-pr-gate-python.yml
2. Reusable runs: uv sync → ruff check → ruff format --check → mypy src → uv run pytest
3. pytest discovers:
   - tests/test_sanity.py (existing, Phase 0 sanity tests)
   - tests/unit/cli/test_cli_entry.py (new)
   - tests/unit/config/test_load_config.py (new)
4. pytest SKIPS tests/fixtures/ via the existing --ignore=tests/fixtures addopt
5. Each test runs; CliRunner tests are in-process (fast), config loader tests read fixture files
6. Exit 0 if all pass; reusable workflow reports the result
```

## Error Handling

### Exit code convention

| Code | Meaning | Stream | Example |
|---|---|---|---|
| 0 | Success | stdout | `gh manage --version` → `gh-manage, version 0.1.0`; `gh manage labels --help` → help text |
| 1 | Stubbed subcommand OR runtime error | stderr | `gh manage labels` → `error: gh manage labels is not yet implemented — scheduled for cli/v0.2.0 (Phase 5).` |
| 2 | User error (click's convention: invalid argv, missing required option, unknown subcommand) | stderr | `gh manage --unknown-flag` or `gh manage totally-not-a-command` → click's `Usage: ... Error: No such command ...` |

click handles code 2 automatically. Phase 4 code explicitly emits code 1 from stubs via `sys.exit(1)`. Successful CLI exits (code 0) do not need explicit `sys.exit(0)` — click returns normally.

### Wrapper-layer errors (shell)

`gh-manage` shell wrapper opens with `set -euo pipefail`. It checks `command -v uv` and fails fast with an actionable message if uv is missing:

```
error: 'uv' is required to run gh-manage.
Install via: curl -LsSf https://astral.sh/uv/install.sh | sh
Or: brew install uv
```

No silent failures. No `|| true`. No bare catches.

### Config loading exception hierarchy

```
ConfigError (base)
├── ConfigFileNotFoundError       # file missing
├── ConfigParseError              # YAML syntax error OR top-level not a mapping
├── ConfigSchemaVersionError      # version field missing or unsupported
└── ConfigValidationError         # pydantic validation failed (__cause__ preserved)
```

Every exception's `__str__` contains (in order):

1. **What happened** — concrete description referencing the operation (`Config file ... failed validation:`)
2. **Where** — the file path
3. **Why** — pydantic error detail for validation errors; exception message for parse errors
4. **How to fix** — actionable next step (`Check the file for syntax errors`, `Upgrade gh-manage or downgrade the config`, `Check the path and try again`)

ValidationError chaining: `ConfigValidationError` uses `raise ... from e` to preserve the original `pydantic.ValidationError` on `__cause__`, so debuggers and pytest's `pytest.raises` assertions can inspect the underlying error.

### Stub subcommand error format (standardized)

All 6 stubs use a verbatim format so Phase 5+ can find and replace them mechanically:

```
error: `gh manage <command>` is not yet implemented — scheduled for cli/v0.X.0 (Phase N).
```

Emitted to stderr via `click.echo(..., err=True)` followed by `sys.exit(1)`. Tests assert the substring `not yet implemented` in the CliRunner result output.

### No silent failures

Per gh-manage's `CLAUDE.md`: "No silent failures. Bare `except: pass` and swallowed errors are forbidden." Phase 4 code has zero `except: pass`, zero `except Exception: pass`. Every boundary either returns a value, raises a typed exception, or propagates the underlying error via `raise ... from e`. The shell wrapper uses `set -euo pipefail` throughout.

### Consumer-facing errors (not exercised in Phase 4)

Real commands (labels sync, protection sync, drift scan) will need to handle authentication failures, rate limiting, network errors, and API schema drift. All of these are deferred to Phase 5+ when the relevant commands become non-stubs and `github_client.py` is introduced.

## Testing Strategy

### Test organization

```
tests/
├── __init__.py                           # existing
├── test_sanity.py                        # existing — __version__ assertion bumped to 0.1.0
└── unit/
    ├── __init__.py                       # NEW
    ├── cli/
    │   ├── __init__.py                   # NEW
    │   └── test_cli_entry.py             # NEW — 10+ CLI smoke tests
    └── config/
        ├── __init__.py                   # NEW
        └── test_load_config.py           # NEW — 8+ load_config + LabelsConfig tests

tests/fixtures/config/                    # NEW — data, excluded from pytest collection
├── labels-valid.yml
├── labels-invalid-missing-version.yml
├── labels-invalid-wrong-version.yml
├── labels-invalid-bad-yaml.yml
├── labels-invalid-not-mapping.yml
├── labels-invalid-bad-color.yml
└── labels-invalid-empty-category.yml
```

The `tests/fixtures/` directory is already excluded from pytest collection via the existing `[tool.pytest.ini_options] addopts = [..., "--ignore=tests/fixtures"]` setting in `pyproject.toml`. Phase 4 adds `config/` subdirectory of fixtures but does not need to modify the exclusion.

### Test fixture contents

Exact content of each YAML fixture under `tests/fixtures/config/`. Implementers should copy these verbatim.

**`labels-valid.yml`** — minimal happy-path fixture with one category + two labels:

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

**`labels-invalid-missing-version.yml`** — no `version:` field:

```yaml
categories:
  type:
    description: "Issue type labels"
    labels:
      - name: "bug"
        color: "d73a4a"
```

**`labels-invalid-wrong-version.yml`** — `version: 99` (not in supported tuple):

```yaml
version: 99
categories:
  type:
    description: "Issue type labels"
    labels:
      - name: "bug"
        color: "d73a4a"
```

**`labels-invalid-bad-yaml.yml`** — unclosed quote, YAML syntax error:

```yaml
version: 1
categories:
  type:
    description: "unterminated
    labels:
      - name: bug
```

**`labels-invalid-not-mapping.yml`** — top-level is a YAML list, not a mapping:

```yaml
- version: 1
- categories: {}
```

**`labels-invalid-bad-color.yml`** — color is not 6-char hex:

```yaml
version: 1
categories:
  type:
    description: "Issue type labels"
    labels:
      - name: "bug"
        color: "not-a-color"
```

**`labels-invalid-empty-category.yml`** — category with empty `labels:` list (violates `Field(min_length=1)`):

```yaml
version: 1
categories:
  type:
    description: "Issue type labels"
    labels: []
```

All fixture files are **data**, not tests — pytest ignores them via the existing `--ignore=tests/fixtures` addopt, but `tests/unit/config/test_load_config.py` loads them by path at test time.

### CLI smoke tests (`tests/unit/cli/test_cli_entry.py`)

Using `click.testing.CliRunner` (in-process, no subprocess, deterministic):

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

5 test functions, two parametrized across 6 subcommands → 16 total test cases.

### Config loader tests (`tests/unit/config/test_load_config.py`)

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

9 tests.

### Total new test count

- 16 CLI smoke tests (4 non-parametrized + 2 × 6 parametrized: stub-fires + stub-help + 1 unknown-command)
- 9 config loader tests
- 2 existing sanity tests (1 updated to expect `"0.1.0"`)

= **25 new tests, 27 total** after Phase 4 merges.

### End-to-end smoke (manual, during PR)

```bash
# From repo root, after uv sync
chmod +x gh-manage
./gh-manage --version              # → gh-manage, version 0.1.0 (exit 0)
./gh-manage --help                 # → lists 6 subcommands (exit 0)
./gh-manage labels                 # → "not yet implemented" (exit 1)
./gh-manage init --help            # → subcommand help (exit 0)
./gh-manage -h                     # → short help flag (exit 0)
```

The PR description includes the output of each of these commands.

### gh extension install smoke (manual, after cli/v0.1.0 tag is pushed)

```bash
gh extension install yakkuro/gh-manage   # should succeed
gh manage --version                      # → gh-manage, version 0.1.0
gh manage --help                          # → subcommand list
gh manage labels                          # → "not yet implemented", exit 1
gh extension remove gh-manage             # cleanup
```

This verifies the full distribution contract. If it fails, the tag is still valid but `gh extension install` might need a hotfix (release `cli/v0.1.1`).

### Dogfood CI coverage

gh-manage's own `ci.yml` runs `reusable-pr-gate-python.yml` at `${{ github.sha }}`, which executes:

1. `uv sync` (installs click, pydantic, pyyaml, pytest, etc.)
2. `ruff check .` — catches style issues
3. `ruff format --check .` — catches formatting drift
4. `mypy src` — catches type errors in the new source files
5. `uv run pytest` — runs all tests (including the 18 new ones)

Phase 4 must not regress any of these. In particular:
- **mypy strict**: the new `config.py`, `models/labels.py`, `cli.py`, `commands/*.py` must be clean against mypy's default strictness
- **ruff**: new code must pass `ruff check` and `ruff format --check`
- **import sorting**: ruff's isort compat rules enforce stable import order

### PR-level verification gate

Before the PR is ready for merge, the implementer walks the Phase 4 AC checklist and confirms each item by running the relevant command or reading the relevant file. The verification output is pasted into a PR comment as a self-review checklist.

## Dependencies

### External (runtime)

- `click` (>=8.1, <9) — already in `pyproject.toml`
- `pydantic` (>=2.5, <3) — already in `pyproject.toml`
- `pyyaml` (>=6.0, <7) — already in `pyproject.toml`
- `uv` on user's machine (installed separately, not a Python dep)

### External (dev)

- `pytest` (>=8.0, <9) — already in `[dependency-groups.dev]`
- `pytest-cov` — already present
- `pytest-mock` — already present (not used in Phase 4 but retained)

No new dependencies are introduced by Phase 4. Version pins remain as specified in the existing `pyproject.toml`.

### Internal

- Existing Phase 0 `src/gh_manage/__init__.py` and `src/gh_manage/cli.py` (modified, not replaced)
- Existing Phase 0 `tests/test_sanity.py` (one line changed to match the new `__version__`)
- Existing Phase 1 `ci.yml` self-dogfood via `reusable-pr-gate-python.yml` — exercises the full gate against Phase 4 code with no changes needed

## Release Flow

1. Implementation on `feat/phase-4-cli-skeleton` branch
2. Commits are logically separated (one per component or per logical change)
3. CI green throughout (reusable gate passes on every commit)
4. 4-reviewer cross-agent review before ready
5. Promote `CHANGELOG-cli.md` `[Unreleased]` → `[0.1.0] - 2026-04-10` pre-merge
6. Squash merge to `main`
7. On main: `git tag -a cli/v0.1.0 -m "..."` and `git push origin cli/v0.1.0`
8. `gh release create cli/v0.1.0 --notes "$(awk ...CHANGELOG excerpt...)" --latest=false`
   - Note: `--latest=false` because the reusable workflow track's `v0.2.1` is the "latest" from the reusable POV, and we do not want the CLI release to hide it on the Releases page. The CLI tag is separate but related.
   - Alternative: both tracks are "latest" simultaneously, and we rely on the `cli/` prefix to disambiguate. Decision deferred to release time — lean toward `--latest=false` for first CLI release.
9. Smoke test: `gh extension install yakkuro/gh-manage`, run `gh manage --version`, `--help`, then remove
10. Update `docs/consumers.md` with a brief note about the CLI availability (optional, could defer to Phase 5 when the CLI actually does something consumer-facing)

## References

- [`docs/specs/2026-04-10-gh-manage-design.md`](./2026-04-10-gh-manage-design.md) — main design spec (§ Python CLI src/gh_manage/, § Phase 4 Acceptance Criteria, § Versioning Strategy § タグ系統, § Error Handling 全体方針)
- [`pyproject.toml`](../../pyproject.toml) — existing dependency pins
- [`CHANGELOG-reusable.md`](../../CHANGELOG-reusable.md) — the companion track for reusable workflows (read to confirm the CHANGELOG structure we are mirroring)
- [`docs/usage/python.md`](../usage/python.md) — consumer guide template to mirror for `docs/usage/cli.md`
- [Click 8 docs](https://click.palletsprojects.com/en/8.1.x/) — for `@click.group`, `@click.command`, `@click.version_option`, `context_settings`, `help_option_names`, `CliRunner`
- [Pydantic v2 docs](https://docs.pydantic.dev/2.5/) — for `BaseModel`, `Field`, `ConfigDict(extra="forbid")`, `ValidationError`
- [gh CLI extensions docs](https://docs.github.com/en/github-cli/github-cli/creating-github-cli-extensions) — for the `gh extension install` contract and the shell-wrapper entry point pattern
- [uv docs — running commands](https://docs.astral.sh/uv/guides/projects/#running-commands) — for the `uv run python -m <module>` pattern the shell wrapper uses

## Appendix: Scope guard against common overreach

A non-exhaustive list of things NOT to do in Phase 4, to keep the PR focused:

- Do NOT implement `github_client.py` — deferred to Phase 5
- Do NOT write real `labels sync` logic — deferred to Phase 5
- Do NOT add `branch-protection.yml`, `repos.yml`, or profile pydantic models — deferred to Phases 6-8
- Do NOT add `config/labels.yml` with real labels — that is a Phase 5 deliverable (the fixture files under `tests/fixtures/config/` are sufficient for Phase 4 tests)
- Do NOT touch `pyproject.toml` beyond the version bump — no new dependencies. Note: `requires-python = ">=3.12"` is already set from Phase 0 (pyproject.toml line 7) and does not need to be re-added.
- Do NOT modify the reusable workflows or smoke tests — those are Phase 1-3 artifacts and stable
- Do NOT refactor existing Phase 0 code beyond the `__version__` bump and the `cli.py` modifications required to register subcommands
- Do NOT add Python `__init__.py` level imports that re-export from submodules unless genuinely needed (YAGNI — keep imports explicit)
- Do NOT add type: ignore comments without a justifying explanation

## Appendix: spec-critique findings rejected with rationale

The spec went through two rounds of `spec-critique`. Most findings were accepted and addressed inline; the following were **rejected** after analysis. Recording them here so future reviewers don't re-raise the same points.

- **"Config file discovery strategy must be designed in Phase 4"** (rejected as premature). Phase 4 intentionally ships `load_config(path, model_cls)` with an explicit path parameter. Each command's config-file location is a Phase 5+ decision driven by real command semantics (e.g., `labels sync --config <path>` vs. repo-root `labels.yml` discovery). Prescribing a uniform strategy now would be speculative and risk being wrong for the first real consumer. Documented explicitly in § Non-goals.
- **"ConfigError subclasses should all chain `__cause__` consistently"** (rejected as already correct). `ConfigParseError` chains the underlying `yaml.YAMLError` via `raise ... from e`, and `ConfigValidationError` chains the underlying `pydantic.ValidationError` via `raise ... from e`. `ConfigFileNotFoundError` and `ConfigSchemaVersionError` have no underlying exception to chain — they are raised from boolean checks, not from wrapping an exception. Adding `from None` is not required and would only add noise.
- **"Version field might be nested in fixture files causing test mismatch"** (rejected as non-issue). All LabelsConfig fixtures have `version:` at the top level (see § Test fixture contents for exact file contents). The pydantic model defines `version: int` at the LabelsConfig root. No nesting mismatch is possible.
- **"pyproject.toml requires-python should be shown in the spec"** (rejected as already done in Phase 0). `requires-python = ">=3.12"` is at `pyproject.toml` line 7, added in Phase 0. Phase 4 does not modify this line.
- Do NOT add coverage thresholds or mutation testing — Phase 4 is too small to set meaningful numbers
