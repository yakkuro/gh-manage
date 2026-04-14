# Changelog — Reusable Workflows and Composite Actions

All notable changes to `yakkuro/gh-manage`'s reusable workflows and composite actions are documented here. This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The CLI changelog lives in `CHANGELOG-cli.md`.

## [Unreleased]

## [1.0.0] - 2026-04-14

Stable API milestone. No functional changes since v0.2.1.

This release is a formal stability promise, not a new feature drop. The reusable workflows (`reusable-pr-gate-python.yml`, `reusable-pr-gate-typescript.yml`) and composite actions (`actions/**`) have been unchanged since v0.2.1 (2026-04-10) and have been validated across 9 consumer repositories over 4+ days of production use (see [`docs/consumers.md`](docs/consumers.md)). This v1.0.0 tag makes the input surface a load-bearing contract that future releases will not break without bumping to v2.0.

### What is contract-stable starting v1.0.0

- **Inputs on both reusable workflows** — every `inputs.*` field on `reusable-pr-gate-python.yml` and `reusable-pr-gate-typescript.yml` (name, type, default, required flag) is frozen. Adding new optional inputs is a MINOR bump. Removing or renaming any input is a MAJOR bump.
- **Composite action names and their `inputs.*` fields** — the 7 composite actions `log-gh-manage-version`, `setup-python-uv`, `run-ruff`, `run-mypy`, `setup-node-pnpm`, `run-eslint`, `run-tsc`. Renaming a composite or changing its input surface is a MAJOR break.
- **Required `gh-manage-ref` input semantics** — consumers must pass the same `@<ref>` they used on the `uses:` line. This is load-bearing for cross-repo self-checkout (see the v0.2.1 fix below).
- **Pinned tool versions** — `uv 0.5.0`, `ruff 0.8.0`, `mypy 1.12.0`, `pnpm 10.33.0`, `typescript 6.0.2`. Upgrading a pinned tool in a way that breaks consumer CI is a MAJOR break and requires a v2.0 bump.

### What is NOT stable (internal)

- **`tests/fixtures/projects/**`** — smoke-test fixtures are internal and may be restructured without a version bump.
- **`.github/workflows/smoke-test.yml`** — internal to gh-manage's own CI.
- **Composite action step implementations** — only the declared `inputs.*` surface is stable. The steps inside `action.yml` files can be refactored freely.

### v0.x lessons rolled into v1.0

- **v0.2.0** — TypeScript track added alongside the Phase 1 Python gate. Latent `github.workflow_ref` parser bug fixed pre-emptively (longest-prefix strip truncated refs containing `@`).
- **v0.2.1** — **CRITICAL** cross-repo self-checkout fix. The `github.workflow_ref` context variable does NOT reflect the called reusable's ref in cross-repo contexts; it returns the top-level caller's ref. Same-repo dogfood in Phase 1-2 masked this bug. The fix replaced implicit `github.workflow_ref` parsing with an explicit `gh-manage-ref` required input. This fix is load-bearing for every consumer and is now frozen in the v1.0 contract.
- **Visibility flip to public (2026-04-10)** — cross-repo `actions/checkout@v4` of a private gh-manage would require PAT plumbing on every consumer's runner; flipping gh-manage's visibility to public eliminated the consumer-side setup burden. gh-manage remains public at v1.0 for this reason.

### Known limitations (carried forward from v0.2.1)

All v0.2.0 + v0.2.1 known limitations still apply at v1.0.0:

- **pnpm only** (TypeScript track) — `npm` and `yarn` consumers are not supported.
- **eslint pinning is recommendation-only** — gh-manage documents recommended eslint family versions but does not enforce them.
- **Minimum Node 20** — driven by vitest 4.x engine constraint.
- **No `cache: pnpm`** — `setup-node-pnpm` intentionally skips the cache for now; cold installs run on every job.
- **Non-root `working-directory` is shallow-tested** — smoke test covers `tests/fixtures/projects/typescript-sample`, but no deep monorepo path fixture.
- **No version skew detection** — older pnpm-generated lockfiles vs pnpm 10 runtime, Node-version / TypeScript-target mismatches.
- **Pinned tool versions may lag upstream** — `uv 0.5.0`, `ruff 0.8.0`, `mypy 1.12.0`, etc. Upgrading these will happen in future MINOR releases.

### Reference

- Top-level design specification: [`docs/specs/2026-04-10-gh-manage-design.md`](docs/specs/2026-04-10-gh-manage-design.md)
- Distribution channels: [`docs/distribution-channels.md`](docs/distribution-channels.md)
- Versioning policy: [`docs/versioning.md`](docs/versioning.md)

## [0.2.1] - 2026-04-10

Hotfix release. The Phase 3 first-external-consumer test (yakkuro/llm-kb) discovered that v0.2.0's self-checkout pattern is fundamentally broken for cross-repo invocation. v0.2.1 replaces the implicit `github.workflow_ref` parsing with an explicit `gh-manage-ref` input that the consumer must specify.

### Fixed

- **Cross-repo self-checkout** (CRITICAL) — both `reusable-pr-gate-python.yml` and `reusable-pr-gate-typescript.yml` previously parsed `github.workflow_ref` to determine which gh-manage ref to check out for Layer-2 composite actions. The assumption was that `github.workflow_ref` reflects the called reusable workflow's ref. **It does not.** GitHub Actions populates `github.workflow_ref` with the **top-level caller's** workflow ref, not the called reusable's ref. In same-repo dogfood (Phases 1 and 2), the consumer ref happened to coincide with the gh-manage ref, masking the bug. In cross-repo (Phase 3), the parser returned the consumer's PR merge ref (e.g., `refs/pull/14/merge`), which the gh-manage repo does not contain, and the self-checkout step failed with `fatal: couldn't find remote ref refs/pull/14/merge`.

  **Fix**: replace the implicit parser with a new required input `gh-manage-ref`. Consumers MUST pass the same `@<ref>` they used in `uses:`. The duplication is required because GitHub Actions does not allow dynamic values in `uses:` lines, and there is no built-in context variable that exposes the called workflow's own ref.

  Affected: every cross-repo consumer of v0.2.0. Workaround: pin to v0.2.1 and add the new required input. Same-repo dogfood and smoke-test now pass `${{ github.sha }}`.

### Added

- **`gh-manage-ref` input on both reusable workflows** — required, string. See the input description in `reusable-pr-gate-{python,typescript}.yml` for the full rationale, or `docs/usage/{python,typescript}.md` for consumer-facing examples.

### Changed

- **`docs/usage/python.md` and `docs/usage/typescript.md`** — minimal example, Inputs table, Disabling checks, and Setup command examples all updated to show the new `gh-manage-ref` input. Bumped pin references from `@v0.1.0` / `@v0.2.0` to `@v0.2.1`.
- **`gh-manage` repository visibility** — `yakkuro/gh-manage` was switched from private to public on 2026-04-10 to enable cross-repo `actions/checkout@v4` from consumer runners. The default `GITHUB_TOKEN` of a consumer repo can clone public repositories without additional configuration; private would have required PAT setup for every consumer. This is a one-time visibility change documented here for traceability.

### Known limitations (carried forward from v0.2.0)

All v0.2.0 known limitations still apply (pnpm only, eslint pinning recommendation-only, Node 20+ minimum, no `cache: pnpm`, non-root working-directory test gap, version skew detection gap, Python tool refresh deferred).

## [0.2.0] - 2026-04-10

Second release. Adds the TypeScript PR gate alongside the Phase 1 Python gate and fixes a latent `github.workflow_ref` parser bug shared by both reusables.

### Added

- **Reusable workflow `reusable-pr-gate-typescript.yml`** (Layer 3) — `install → lint → type-check → setup → test` pipeline for TypeScript/Node projects using `pnpm`. Inputs: `node-version` (required), `working-directory`, `install-command`, `test-command`, `lint`, `type-check`, `setup-command`, `pnpm-version`. Mirrors the `reusable-pr-gate-python.yml` structural pattern including the self-checkout block.
- **Composite action `setup-node-pnpm`** (Layer 2) — installs a requested Node.js version and a pinned `pnpm` release. Pinned `pnpm` version: `10.33.0`. `setup-node`'s `cache: pnpm` feature is intentionally skipped in v0.2.0 (path-plumbing for non-root working-directory is deferred to a follow-up).
- **Composite action `run-eslint`** (Layer 2) — runs `pnpm exec eslint .` using the consumer's `devDependencies`. Unlike Phase 1's `run-ruff` (which pins ruff via `uvx`), `run-eslint` does NOT pin eslint because eslint 10.x flat config requires peer dependencies (`typescript-eslint`, `@eslint/js`) that do not resolve cleanly through `pnpm dlx`. gh-manage recommends specific eslint family versions in `docs/usage/typescript.md` and the fixture `devDependencies`.
- **Composite action `run-tsc`** (Layer 2) — runs `tsc --noEmit -p tsconfig.json` via `pnpm --package="typescript@<pinned>" dlx tsc`. Pinned `typescript` version: `6.0.2`. Uses the `pnpm --package=` form (not `pnpm dlx typescript@<ver> tsc`) because the `typescript` package ships multiple binaries (`tsc` and `tsserver`) and pnpm 10+ requires explicit disambiguation. This composite is the TypeScript analogue of Phase 1's `run-ruff` (standalone tool, pinned at gh-manage level).
- **TypeScript fixture projects** — 3 new projects under `tests/fixtures/projects/`:
  - `typescript-sample` — positive fixture; passes eslint + tsc + vitest cleanly
  - `typescript-lint-fail` — negative fixture; triggers `@typescript-eslint/no-unused-vars` (grepped as `no-unused-vars` in smoke test)
  - `typescript-type-fail` — negative fixture; triggers `TS2322` via a `const x: string = 42; void x;` pattern that keeps vitest runtime clean
- **Smoke test workflow** — extended `.github/workflows/smoke-test.yml` with 3 new jobs mirroring the Phase 1 Python pattern:
  - `positive-typescript-sample` uses the full reusable workflow via `./.github/workflows/reusable-pr-gate-typescript.yml`
  - `negative-typescript-lint-fail` and `negative-typescript-type-fail` are regular jobs (not reusable calls) that invoke the composite actions with step-level `continue-on-error`, then verify BOTH the outcome is `failure` AND the direct-tool output contains the expected rule id / error code (`no-unused-vars` and `TS2322` respectively). This two-assertion pattern is inherited from Phase 1 learning #4.
- **Consumer usage documentation** at `docs/usage/typescript.md` — prerequisites (eslint.config.js, tsconfig.json, pnpm-lock.yaml, eslint family devDeps), minimal example, input surface, tool versions (hybrid pinning explanation), example configs, disabling checks, troubleshooting, versioning.

### Known limitations

- **pnpm only**: Phase 2 v0.2.0 locks to `pnpm`. `npm` and `yarn` consumers are not supported in this release. The `package-manager` input from the main design spec is deferred to a future release.
- **eslint pinning is recommendation-only**: gh-manage recommends eslint / typescript-eslint / @eslint/js versions via docs and fixture devDeps but does NOT enforce them. If a consumer's pins drift significantly, behavior may differ from gh-manage's smoke tests.
- **Minimum Node 20**: driven by vitest 4.x engine constraint (`^20 || ^22 || >=24`). Consumers on Node 18 cannot use the fixture test runner, but may override `test-command` if their own test runner supports older Node.
- **No `cache: pnpm`**: `setup-node-pnpm` intentionally skips `actions/setup-node`'s `cache: pnpm` feature in v0.2.0 because path-plumbing for non-root `working-directory` adds complexity. Cold pnpm installs run on every job; caching can be added in a follow-up if CI wall time becomes painful.
- **Non-root `working-directory` in composites is not deeply tested**: the smoke test exercises `working-directory: tests/fixtures/projects/typescript-sample`, but no fixture exercises deep monorepo paths like `packages/client/`.
- **Version skew detection**: Phase 2 does NOT test older-pnpm-generated lockfiles with pnpm 10 runtime, nor Node-version / TypeScript-target mismatches.
- **Cross-repo invocation** has NOT been empirically validated in v0.2.0 (same constraint as Phase 1). Phase 3 (port-registry adoption) will be the first real cross-repo test for BOTH Python and TypeScript reusables. If issues arise, they will be hotfixed in v0.2.1 or v0.3.0.
- **Pinned tool versions as of 2026-04-10**: `pnpm` `10.33.0`, `typescript` `6.0.2`. Fixture devDep recommendations: `eslint` `10.2.0`, `typescript-eslint` `8.58.1`, `@eslint/js` `10.0.1`, `vitest` `4.1.4`, `@types/node` `22.19.17`.
- **Python tool refresh (uv / ruff / mypy) is deferred to v0.3.0**: Phase 1 pins from v0.1.0 remain active.

### Fixed

- **`github.workflow_ref` parser in both reusables** — `reusable-pr-gate-python.yml` and `reusable-pr-gate-typescript.yml` previously used `${VAR##*@}` (longest-prefix strip) to extract the gh-manage ref from `github.workflow_ref`. This truncated refs containing `@` (e.g., `release@candidate`), silently checking out the wrong ref. Replaced with `${VAR#*.yml@}` (shortest prefix) plus an explicit `*.yml@*` format check that fails fast with a clear `::error::` message. The Phase 1 workflow is patched as part of this release even though the bug was introduced in v0.1.0, because the fix is load-bearing for Phase 3 (port-registry adoption) cross-repo testing. Reported by Codex cross-agent review during PR #3.

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

[Unreleased]: https://github.com/yakkuro/gh-manage/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/yakkuro/gh-manage/releases/tag/v0.2.1
[0.2.0]: https://github.com/yakkuro/gh-manage/releases/tag/v0.2.0
[0.1.0]: https://github.com/yakkuro/gh-manage/releases/tag/v0.1.0
