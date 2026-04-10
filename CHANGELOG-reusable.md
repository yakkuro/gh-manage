# Changelog — Reusable Workflows and Composite Actions

All notable changes to `yakkuro/gh-manage`'s reusable workflows and composite actions are documented here. This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The CLI changelog lives in `CHANGELOG-cli.md`.

## [Unreleased]

_Nothing yet._

## [0.1.0] - 2026-04-10

First public release. This marks the initial usable state of gh-manage's Python PR gate.

### Added

- **Reusable workflow `reusable-pr-gate-python.yml`** (Layer 3) — `install → lint → type-check → setup → test` pipeline for Python projects using `uv`. Inputs: `python-version` (required), `working-directory`, `install-command`, `test-command`, `lint`, `type-check`, `setup-command`, `uv-version`.
- **Self-checkout pattern** — The reusable workflow extracts its own ref from `github.workflow_ref` and checks out gh-manage into `.gh-manage/` before invoking its Layer-2 composite actions via `./.gh-manage/actions/<name>`. This is required because GitHub Actions resolves `./<path>` references in reusable workflows against the runner's current workspace, which (after `actions/checkout` of the caller) contains the caller's repository — not gh-manage's. Without self-checkout, cross-repo consumers would fail to locate the composite actions.
- **Composite action `log-gh-manage-version`** (Layer 2) — emits gh-manage version info to workflow logs for traceability.
- **Composite action `setup-python-uv`** (Layer 2) — installs a requested Python version and a pinned `uv` release. Pinned uv version: `0.5.0`.
- **Composite action `run-ruff`** (Layer 2) — runs `ruff check .` and `ruff format --check .` with a pinned ruff release. Pinned ruff version: `0.8.0`. Uses `uvx "ruff@<version>"` for installation.
- **Composite action `run-mypy`** (Layer 2) — runs `mypy src/` via `uv run --with` with a pinned mypy release. Pinned mypy version: `1.12.0`.
- **Smoke test workflow `.github/workflows/smoke-test.yml`** — verifies the reusable workflow against three fixture projects (`python-sample`, `python-lint-fail`, `python-test-fail`). Positive fixture uses the full reusable workflow call. Negative fixtures use a regular job that invokes the composite action with step-level `continue-on-error` AND additionally runs the underlying tool directly to verify the specific failure reason (ruff F401 for `python-lint-fail`, pytest `AssertionError` for `python-test-fail`). The outcome-only assertion is insufficient on its own because any failure (including a broken composite action) would look the same.
- **Self-dogfood CI `.github/workflows/ci.yml`** — gh-manage's own PRs run through `reusable-pr-gate-python.yml` at the current feature branch.
- **Consumer usage documentation** at `docs/usage/python.md`.

### Fixed

_N/A — first release._

### Known limitations

- Only Python 3.12+ is supported. Python 3.11 and below may work but are untested.
- `mypy` is run against `src/` only. Projects that need to type-check other paths should disable `type-check` and add their own step.
- The reusable does not currently support matrix-testing multiple Python versions in a single call.
- Go, Rust, Java, and other runtimes are not supported in this release — only Python and (planned) TypeScript.
- The `run-ruff` composite action uses `uvx "ruff@<version>"` syntax; `ruff==<version>` is NOT supported by `uvx` and will fail with an invalid package name error.
- **Cross-repo consumption from private `yakkuro/gh-manage`** requires enabling `Settings → Actions → General → Access` to `"Accessible from repositories owned by the user 'yakkuro'"` on the gh-manage repo. Without this, callers outside gh-manage cannot resolve the reusable workflow.
- **Cross-repo self-checkout has NOT been empirically validated** in v0.1.0 — the same-repo dogfood (gh-manage's own `ci.yml`) and smoke-test are the only tested invocation paths. Phase 3 (port-registry adoption) will be the first real cross-repo test. If issues arise, they will be fixed in v0.1.1 or v0.2.0.
- **Pinned tool versions are not the latest available** as of 2026-04-10. `uv` is pinned at 0.5.0 (latest: 0.11.6), `ruff` at 0.8.0 (latest: 0.15.10), `mypy` at 1.12.0 (latest: 1.20.0). Tool version refresh is scheduled for v0.2.0.

[Unreleased]: https://github.com/yakkuro/gh-manage/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yakkuro/gh-manage/releases/tag/v0.1.0
