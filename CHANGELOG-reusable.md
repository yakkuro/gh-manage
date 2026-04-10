# Changelog — Reusable Workflows and Composite Actions

All notable changes to `yakkuro/gh-manage`'s reusable workflows and composite actions are documented here. This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The CLI changelog lives in `CHANGELOG-cli.md`.

## [Unreleased]

_Nothing yet._

## [0.1.0] - 2026-04-10

First public release. This marks the initial usable state of gh-manage's Python PR gate.

### Added

- **Reusable workflow `reusable-pr-gate-python.yml`** (Layer 3) — `install → lint → type-check → setup → test` pipeline for Python projects using `uv`. Inputs: `python-version` (required), `working-directory`, `install-command`, `test-command`, `lint`, `type-check`, `setup-command`, `uv-version`.
- **Composite action `log-gh-manage-version`** (Layer 2) — emits gh-manage version info to workflow logs for traceability.
- **Composite action `setup-python-uv`** (Layer 2) — installs a requested Python version and a pinned `uv` release. Pinned uv version: `0.5.0`.
- **Composite action `run-ruff`** (Layer 2) — runs `ruff check .` and `ruff format --check .` with a pinned ruff release. Pinned ruff version: `0.8.0`. Uses `uvx "ruff@<version>"` for installation.
- **Composite action `run-mypy`** (Layer 2) — runs `mypy src/` via `uv run --with` with a pinned mypy release. Pinned mypy version: `1.12.0`.
- **Smoke test workflow `.github/workflows/smoke-test.yml`** — verifies the reusable workflow against three fixture projects (`python-sample`, `python-lint-fail`, `python-test-fail`). Positive fixture uses the full reusable workflow call; negative fixtures use a regular job that invokes the composite action with step-level `continue-on-error` and asserts failure via `steps.<id>.outcome`. This pattern was chosen because GitHub Actions does not support job-level `continue-on-error` on reusable workflow calls.
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

[Unreleased]: https://github.com/yakkuro/gh-manage/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yakkuro/gh-manage/releases/tag/v0.1.0
