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
- **`pyproject.toml`** — `version` bumped from `"0.0.0"` to `"0.1.0"`. `types-PyYAML>=6.0` added to `[dependency-groups] dev` so mypy resolves stubs for the new `import yaml`.
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
