# Changelog — CLI (src/gh_manage/)

All notable changes to the `gh-manage` Python CLI are documented here. This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The reusable workflow changelog lives in `CHANGELOG-reusable.md` and tracks independently under `v<major>.<minor>.<patch>` tags. CLI tags use the `cli/v<major>.<minor>.<patch>` prefix (see the main design spec's Versioning Strategy section).

## [Unreleased]

_Nothing yet._

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

[Unreleased]: https://github.com/yakkuro/gh-manage/compare/cli/v0.2.0...HEAD
[0.2.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v0.2.0
[0.1.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v0.1.0
