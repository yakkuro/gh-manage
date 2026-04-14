# Changelog — CLI (src/gh_manage/)

All notable changes to the `gh-manage` Python CLI are documented here. This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The reusable workflow changelog lives in `CHANGELOG-reusable.md` and tracks independently under `v<major>.<minor>.<patch>` tags. CLI tags use the `cli/v<major>.<minor>.<patch>` prefix (see the main design spec's Versioning Strategy section).

## [Unreleased]

_Nothing yet._

## [1.0.0] - 2026-04-14

Stable API milestone. No new CLI features; this release graduates the `gh-manage` Python CLI to the v1.0 stability contract. See [`CHANGELOG-reusable.md`](CHANGELOG-reusable.md) v1.0.0 for the reusable-workflow stability promise announced at the same commit. The CLI's subcommand surface (`labels`, `init`, `apply`, `protection`, `drift`, `issues`) and bundled data schemas (`labels.yml`, `branch-protection.yml`, `profile.yml`, `repos.yml`) are frozen under semver — removing or renaming any subcommand, flag, or schema key is a v2.0 break. See [`docs/versioning.md`](docs/versioning.md) for the full stability promise.

### Changed

- **`pyproject.toml`** — `version` bumped from `"0.6.0"` to `"1.0.0"`
- **`src/gh_manage/__init__.py`** — `__version__` bumped from `"0.6.0"` to `"1.0.0"`
- **`tests/test_sanity.py`** — expected `__version__` bumped to `"1.0.0"`
- **`uv.lock`** — regenerated after pyproject.toml bump

### Reference

- Top-level design specification: [`docs/specs/2026-04-10-gh-manage-design.md`](docs/specs/2026-04-10-gh-manage-design.md)
- Stability promise: [`docs/versioning.md`](docs/versioning.md)
- Distribution channels: [`docs/distribution-channels.md`](docs/distribution-channels.md)

## [0.6.0] - 2026-04-12

Phase 8.5 milestone: fully-automated weekly drift scanning with GitHub Issue reporting. Builds on Phase 8's stdout/json/markdown drift reports by adding `--report-mode issue` (creates one open Issue per repo with zero-findings auto-close after a 24-hour double-check), `--all` batch mode driven by bundled `repos.yml`, and a scheduled cron workflow (`drift-scanner.yml`). Shipped in [PR #21](https://github.com/yakkuro/gh-manage/pull/21). Plan: [`docs/plans/2026-04-12-phase-8.5-drift-automation.md`](docs/plans/2026-04-12-phase-8.5-drift-automation.md). Spec: [`docs/specs/2026-04-12-phase-8.5-drift-automation-design.md`](docs/specs/2026-04-12-phase-8.5-drift-automation-design.md).

### Added

- **`src/gh_manage/drift_sync.py` issue-report formatters** — `format_issue_body`, `format_issue_comment`, `parse_zero_findings_timestamps`, `should_close_issue`, `resolve_drift_issue`. 24-hour double-check state machine stored as hidden `<!-- scan:zero-findings:<ISO8601> -->` metadata in comments.
- **`src/gh_manage/github_api/issues.py`** — 7 Issue CRUD functions mirroring `github_api/labels.py` pattern: `search_drift_issue`, `create_issue`, `update_issue_body`, `add_issue_comment`, `close_issue`, `ensure_drift_label` (swallows 422 "already exists"), `get_issue_comments`.
- **`src/gh_manage/models/repos.py`** — `ReposConfig(version: Literal[1], repos: list[RepoEntry])` with `RepoEntry.name` validator enforcing `owner/repo` format.
- **`src/gh_manage/data/repos.yml`** — bundled `repos.yml` v1 schema with a single initial entry (`yakkuro/gh-manage` / `python-service`). Subsequent repos are added as separate follow-up commits, not as part of this release.
- **`.github/workflows/drift-scanner.yml`** — weekly cron (`0 0 * * 1`) + `workflow_dispatch` trigger. Runs `gh-manage drift --all --report-mode issue --severity low` using `GH_MANAGE_TOKEN` secret.
- **`commands/drift.py` `--all` + partial-continue** — `_scan_all_repos` helper catches `(GhError, ConfigError, GitError, ProfileError, ProtectionError, DriftError)` per-repo to keep scanning after one repo fails.

### Known limitations

- **Issue body rewrite on every run** — the Issue body is overwritten each scan rather than diffed. Minor UX cost, acceptable for v0.6.0.
- **24-hour auto-close is timezone-naive** — uses UTC only; consumers in non-UTC timezones see the close after UTC midnight has passed.

## [0.5.0] - 2026-04-12

Phase 8 milestone: drift scanner foundation. Adds `gh manage drift` subcommand with 3 check categories (labels, branch protection, profile files), 3 report formats (stdout, JSON, Markdown), and a check-registry pattern for easy extension. Shipped in [PR #18](https://github.com/yakkuro/gh-manage/pull/18). Plan: [`docs/plans/2026-04-11-phase-8-drift.md`](docs/plans/2026-04-11-phase-8-drift.md). Spec: [`docs/specs/2026-04-11-phase-8-drift-design.md`](docs/specs/2026-04-11-phase-8-drift-design.md).

### Added

- **`src/gh_manage/drift_sync.py`** — `Finding` dataclass (per-item granularity), `ScanContext`, `@register_check` decorator, `run_all_checks` orchestrator, 3 check implementations: `check_labels` (against bundled `labels.yml`), `check_protection` (13 downgrade rules shared with Phase 7), `check_profile_files` (SHA256 content hashing against bundled templates).
- **`src/gh_manage/commands/drift.py`** — click subcommand with `--profile`, `--severity` (`critical`|`high`|`medium`|`low`), `--report-mode` (`stdout`|`json`|`markdown-file`), `--output` flag. `_handle_errors` decorator covers `(GhError, ConfigError, GitError, ProfileError, ProtectionError, DriftError)`.
- **Severity filtering** — `_filter_by_severity` drops findings below the `--severity` threshold before reporting. `gh manage drift` always exits 0 on a successful scan; findings are reports, not errors. A non-zero exit is reserved for scan failures themselves (via `_handle_errors` → `ClickException`).
- **Scenario-driven tests** — `tests/unit/drift_sync/scenarios/` uses YAML fixtures + pytest parametrize to run each check against known-good and known-bad states.

### Known limitations

- **Profile-files check depends on SHA256 exactness** — a whitespace-only change in a consumer's CI workflow triggers a drift finding. Intentional for v0.5.0; a future fuzzy-match mode may relax this.
- **No `--all` flag yet** — single-repo only. Batch mode arrives in Phase 8.5.
- **No Issue reporting** — `--report-mode` supports only file/stdout output in v0.5.0. Issue mode arrives in Phase 8.5.

## [0.4.0] - 2026-04-11

Phase 7 milestone: branch protection sync / diff. Adds `gh manage protection sync` and `gh manage protection diff`, wires `gh-manage init` to auto-apply the profile's protection policy, and replaces the Phase 6 stub of `gh-manage apply --also-protection` with the real implementation. Introduces a 13-rule downgrade detector that blocks `gh-manage` from silently weakening protection. Shipped in [PR #16](https://github.com/yakkuro/gh-manage/pull/16). Plan: [`docs/plans/2026-04-11-phase-7-protection.md`](docs/plans/2026-04-11-phase-7-protection.md). Spec: [`docs/specs/2026-04-11-phase-7-protection-design.md`](docs/specs/2026-04-11-phase-7-protection-design.md).

### Added

- **`src/gh_manage/protection_sync.py`** — `ProtectionFieldChange`, `DowngradeFinding`, `ProtectionDiff` dataclasses; error hierarchy (`ProtectionError`, `ProtectionDowngradeError`, `ProtectionBackupError`, `ProtectionApplyError`, `ProtectionPolicyNotFoundError`); 13 downgrade detection rules in `detect_downgrade`; transactional `apply_protection_diff` with microsecond-precision backup filenames to prevent TOCTOU clobbering.
- **`src/gh_manage/commands/protection.py`** — click group with `sync` and `diff` subcommands. `sync` uses `--downgrade-allowed` plus `--yes` (or TTY interactive confirm) as the downgrade gate. `diff` exits 0 on no changes, 0 on non-downgrade changes, 0 on downgrade with `--downgrade-allowed`, and 1 on detected downgrade without `--downgrade-allowed`.
- **`src/gh_manage/models/branch_protection.py`** — pydantic v2 model matching the GitHub API shape for branch protection settings, with `extra="forbid"` and field-level validation.
- **`src/gh_manage/github_api/protection.py`** — `get_branch_protection`, `put_branch_protection`, `delete_branch_protection`. All go through `github_client.run_gh_api(body=dict)` (Phase 5 stdin path introduced in the checkpoint refactor).
- **`src/gh_manage/data/branch-protection.yml`** — bundled `solo-default` policy: 1 PR approval, linear history, block force-pushes, no required status contexts.

### Changed

- **`src/gh_manage/commands/init.py`** — Phase 6 file placement + labels sync flow is extended to also apply the profile's branch protection policy when `protection_policy` is set on the profile.
- **`src/gh_manage/commands/apply.py`** — `--also-protection` flag replaces the Phase 6 "not yet implemented" stub; now actually invokes `protection_sync.apply_protection_diff`.
- **`src/gh_manage/models/profiles.py`** — `ProfileSpec` gains optional `protection_policy` (str | None) and `required_contexts` (list[str], default empty) fields. These were absent in Phase 6 and are introduced here for the init/apply wiring.

### Known limitations

- **GitHub Pro requirement on private repos** — branch protection API returns 403 on private repos without Pro. gh-manage surfaces the error clearly but cannot work around it.
- **No support for required status contexts yet** — `required_contexts: []` is hardcoded in the policy; future phases may add dynamic contexts.
- **No rollback of apply failures beyond backup files** — if `put_branch_protection` fails mid-way, the backup JSON is on disk for manual restoration.

## [0.3.0] - 2026-04-11

Phase 6 milestone: `gh manage init` and `gh manage apply`. Establishes the profile system (YAML specs that point at bundled templates), the file-placement engine (`profile_sync.py`), and the two user-facing subcommands that bootstrap a new repo and re-apply the profile to drifted files. Branch protection is NOT part of this release (the `apply --also-protection` flag ships as an explicit "not yet implemented" stub that errors out; wired to the real engine in Phase 7 v0.4.0). Shipped in [PR #12](https://github.com/yakkuro/gh-manage/pull/12). Plan: [`docs/plans/2026-04-11-phase-6-init-apply.md`](docs/plans/2026-04-11-phase-6-init-apply.md).

### Added

- **`src/gh_manage/profile_sync.py`** — `compute_files_diff` / `apply_files_diff` pure-function engine with 4 diff entry types (`FileCreate`, `FileOverwrite`, `FileSkipExists`, `FileNoop`), path-traversal defense (pydantic pre-filter + `Path.resolve()` + `is_relative_to()`), transactional apply with TOCTOU re-validation before each write.
- **`src/gh_manage/commands/init.py`** — `gh-manage init --profile python-service <path>`. Applies profile file placements, then labels sync. Branch protection integration arrives in Phase 7 v0.4.0.
- **`src/gh_manage/commands/apply.py`** — `gh-manage apply <path>`. Re-applies the profile to an existing repo to recover from drift. `--force` overrides content conflicts. `--also-protection` is an explicit "not yet implemented" stub that errors out — the real path ships in Phase 7 v0.4.0.
- **`src/gh_manage/git_cli.py`** — minimal subprocess wrapper for `git` with error classification (`GitError` → `GitNotInstalled`, `GitNotRepo`, etc.). Kept separate from `github_client.py` because git calls are local and gh api calls are remote.
- **`src/gh_manage/models/profiles.py`** — `ProfileSpec(version: Literal[1], name, description, files)` with file-entry validation (no absolute paths, no `..` segments). Optional `protection_policy` and `required_contexts` fields are added in Phase 7 v0.4.0, not here.
- **`src/gh_manage/data/profiles/python-service.yml`** — first profile, points at `ci/python-ci.yml` and `claude-md/default.md`.
- **`src/gh_manage/data/templates/ci/python-ci.yml`** — minimal CI workflow template, 20 lines, fully static.
- **`src/gh_manage/data/templates/claude-md/default.md`** — CLAUDE.md template with `skip_if_exists: true`, 24 lines, fully static.

### Changed

- **`src/gh_manage/github_client.py`** — `run_gh_api` gained a `body: dict | None` parameter. When set, the body is JSON-serialized and written to `gh api` via stdin (`--input -`), avoiding shell-escape pitfalls for large bodies. This is load-bearing for Phase 7 branch protection PUT.

### Known limitations

- **Only one profile** — `python-service` is the only shipped profile. Adding new profiles is a config-only change once this foundation is in place.
- **`--force` is all-or-nothing** — no per-file override. If any `overwrites` exist in the diff and `--force` is unset, the whole apply aborts.
- **No template variable substitution** — templates are raw byte copies. This is an explicit design choice; see [`docs/specs/2026-04-14-phase-9-v1-hardening-design.md`](docs/specs/2026-04-14-phase-9-v1-hardening-design.md) section 1 Future Evolution for the migration path if placeholders are ever added.

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

[Unreleased]: https://github.com/yakkuro/gh-manage/compare/cli/v1.0.0...HEAD
[1.0.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v1.0.0
[0.6.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v0.6.0
[0.5.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v0.5.0
[0.4.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v0.4.0
[0.3.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v0.3.0
[0.2.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v0.2.0
[0.1.0]: https://github.com/yakkuro/gh-manage/releases/tag/cli/v0.1.0
