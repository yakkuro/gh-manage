# Phase 2 — TypeScript Reusable PR Gate (Design Spec)

## Metadata

- **Date**: 2026-04-10
- **Size**: Medium
- **Target**: `yakkuro/gh-manage`
- **Related**: [Issue #2](https://github.com/yakkuro/gh-manage/issues/2), [`docs/specs/2026-04-10-gh-manage-design.md`](./2026-04-10-gh-manage-design.md) (§ Components, § Phase 2 Acceptance Criteria), [`docs/plans/2026-04-10-phase-1-reusable-pr-gate-python.md`](../plans/2026-04-10-phase-1-reusable-pr-gate-python.md)
- **Supersedes**: nothing; extends Phase 1

## Sizing Rationale

**Medium**. Phase 2 adds a new language runtime to the 3-layer CI architecture, touching multiple layers: 1 new Layer 3 reusable workflow, 3 new Layer 2 composite actions, 3 new fixture projects, 3 new smoke-test jobs, 1 new usage doc, and 2 small documentation bundles. Design judgement is required on tool pinning strategy (resolved: `pnpm dlx` per Phase 1 precedent) and package-manager scope (resolved: lock to pnpm). This is larger than Small (1-2 file change, no design judgement) but smaller than Large (new repository or new top-level module). A single implementation plan can execute it without sub-decomposition.

## Goal

Ship `yakkuro/gh-manage@v0.2.0` adding a TypeScript counterpart to the Python PR gate from Phase 1, proving the 3-layer architecture supports multiple runtimes without cross-contamination and unblocking Phase 3 (first external consumer adoption) with both Python and TypeScript coverage.

## Acceptance Criteria

Directly from `docs/specs/2026-04-10-gh-manage-design.md` lines 837-843, with Phase 2-internal refinements:

- [ ] `.github/workflows/reusable-pr-gate-typescript.yml` exists with the documented input surface
- [ ] `actions/setup-node-pnpm/action.yml`, `actions/run-eslint/action.yml`, `actions/run-tsc/action.yml` exist; shared `actions/log-gh-manage-version/` is unchanged
- [ ] `tests/fixtures/projects/typescript-sample/` exists and passes `pnpm install --frozen-lockfile && pnpm exec eslint . && pnpm --package="typescript@<pin>" dlx tsc --noEmit && pnpm test` locally and via smoke-test
- [ ] `tests/fixtures/projects/typescript-lint-fail/` triggers a `no-unused-vars` eslint violation; smoke-test negative job is green (outcome + reason verified)
- [ ] `tests/fixtures/projects/typescript-type-fail/` triggers a `TS2322` type error; smoke-test negative job is green (outcome + reason verified)
- [ ] `docs/usage/typescript.md` exists, mirroring the structure of `docs/usage/python.md`
- [ ] `CHANGELOG-reusable.md` has a `[0.2.0]` entry with the shipped additions
- [ ] Annotated tag `v0.2.0` exists on `main`
- [ ] GitHub Release `v0.2.0` published with CHANGELOG excerpt
- [ ] `.gitignore` contains `.claude/`
- [ ] `docs/plans/2026-04-10-phase-1-reusable-pr-gate-python.md` file-count typo fixed (12 → 15)
- [ ] `docs/specs/2026-04-10-gh-manage-design.md` has the v0.2.0 pnpm-only deviation note in the `reusable-pr-gate-typescript.yml` section
- [ ] `docs/usage/typescript.md` Prerequisites section explicitly states "Phase 2 v0.2.0 supports pnpm only; npm and yarn support is planned for a future release"
- [ ] 4-reviewer cross-agent review completed with no open CRITICAL/HIGH findings
- [ ] gh-manage's own `ci.yml` (Python self-dogfood) remains green through the entire PR

## Architecture

### 3-layer mirror of Phase 1

```
Layer 3: Reusable workflows
  └─ .github/workflows/reusable-pr-gate-typescript.yml  (NEW)

Layer 2: Composite actions
  ├─ actions/setup-node-pnpm/action.yml  (NEW)
  ├─ actions/run-eslint/action.yml       (NEW)
  ├─ actions/run-tsc/action.yml          (NEW)
  └─ actions/log-gh-manage-version/      (SHARED with Phase 1, no change)

Layer 1: Shell scripts
  └─ (none for Phase 2)
```

### Inherited invariants from Phase 1 (must not drift)

- **Self-checkout pattern**: Layer 3 workflow extracts the caller-provided gh-manage ref from `github.workflow_ref` and checks out `yakkuro/gh-manage` into `.gh-manage/`. Composite actions are referenced via `./.gh-manage/actions/<name>`. This is load-bearing for cross-repo reuse.
- **Tool pin location (hybrid)**: TypeScript is pinned inside `run-tsc` via `pnpm dlx "typescript@<pin>"` (mirror of Phase 1's `uvx "ruff@<pin>"`; tsc has no peer deps and runs cleanly as a standalone binary). eslint is NOT pinned inside `run-eslint` and instead uses `pnpm exec eslint` against the consumer's `devDependencies` (because eslint 10.x flat config requires peer dependencies like `typescript-eslint` and `@eslint/js` that do not resolve reliably through `pnpm dlx`, and pinning eslint rigidly defeats its plugin-host nature). gh-manage still owns the recommended eslint version via `docs/usage/typescript.md` and the three fixture projects. This hybrid is analogous to Phase 1's `run-ruff` (pinned) vs `run-mypy` (project-environment-aware).
- **Shell discipline**: every shell step opens with `set -euo pipefail`, uses `shell: bash` explicitly, passes inputs through an `env:` block (never `${{ inputs.x }}` directly in the script body), and prints actionable `::error::` messages on failure. No `|| true`, no bare catches.
- **Boolean opt-out**: `lint` and `type-check` inputs are booleans, not tool-selection strings. Consumer cannot swap eslint for another linter — gh-manage's opinionated stance.

### New for Phase 2

- **Consumer contract**: consumer repo must have `package.json`, `pnpm-lock.yaml`, `eslint.config.js` (flat config; eslint 10.x), `tsconfig.json`, and `eslint` / `typescript-eslint` / `@eslint/js` in `devDependencies` at `working-directory`. This is analogous to Phase 1's `pyproject.toml` requirement with the additional eslint peer-dep constraint.
- **pnpm bootstrap order**: `setup-node-pnpm` runs `pnpm/action-setup@v4` *before* `actions/setup-node@v4`. This order is the canonical pnpm+Node pattern and is kept even though v0.2.0 skips `cache: pnpm` (so that adding caching in a follow-up is a one-line addition to the composite).
- **Package manager scope**: v0.2.0 locks to pnpm only. The `package-manager` input from the original design spec (pnpm/npm/yarn) is NOT implemented in this phase; a follow-up phase can add npm/yarn if a consumer demands it. This deviation is recorded in the v0.2.0 CHANGELOG and `docs/usage/typescript.md` prerequisites.

### Non-goals for v0.2.0

- npm/yarn support (package-manager input deferred)
- Matrix-testing multiple Node versions in a single reusable call
- Python tool pin refresh (uv/ruff/mypy) — scheduled for v0.3.0 as a standalone PR
- `docs/versioning.md` stub — Phase 9 deliverable per the main design spec
- Cross-repo empirical validation — deferred to Phase 3 (port-registry adoption)
- Caching `pnpm-lock.yaml` via `setup-node`'s `cache: pnpm` — deferred for path-plumbing reasons documented in the `setup-node-pnpm` component section
- **Non-root `working-directory` testing**: all 3 fixtures live at top-level subdirectories under `tests/fixtures/projects/`; the reusable workflow IS invoked with `working-directory: tests/fixtures/projects/typescript-sample` in the smoke test, so the non-root case IS exercised. But there are no fixtures testing deeper nesting (e.g., monorepo `packages/client/`), nor is the `install-command`/`test-command` interaction with deep paths validated beyond what Phase 1 already tested. Deep-nested working-directory support is deferred to Phase 3 where port-registry will exercise it.
- **Version skew detection**: the spec does NOT test older-pnpm-generated lockfiles with pnpm 10 runtime, nor Node-version / TypeScript-target mismatches (e.g., Node 20 with a newer-than-supported target). These are realistic Phase 3 cross-repo failure modes and are left for hotfix in v0.2.1 if they surface.

### Main design spec deviation to record

The main design spec (`docs/specs/2026-04-10-gh-manage-design.md` line 280) lists `package-manager` (pnpm/npm/yarn, default pnpm) as an input of `reusable-pr-gate-typescript.yml`. Phase 2 v0.2.0 does NOT implement this input. The Phase 2 PR will add a note to the main design spec's § Components / `reusable-pr-gate-typescript.yml` section recording: "v0.2.0 locks to pnpm only; the `package-manager` input is deferred to v0.3.0 or later". This keeps the main spec internally consistent with the shipped behavior.

## Components

### Layer 3: `reusable-pr-gate-typescript.yml`

**Inputs**:

| Input | Type | Default | Required |
|---|---|---|---|
| `node-version` | string | — | ✅ |
| `working-directory` | string | `"."` | |
| `install-command` | string | `"pnpm install --frozen-lockfile"` | |
| `test-command` | string | `"pnpm test"` | |
| `lint` | boolean | `true` | |
| `type-check` | boolean | `true` | |
| `setup-command` | string | `""` | |
| `pnpm-version` | string | exact patch version, hardcoded during plan phase (see below) | |

**pnpm-version default resolution**: The plan author runs `npm view pnpm version` on 2026-04-10 (or at plan start), picks the exact patch (e.g., `10.33.0`), and hardcodes that value as the `default:` in `reusable-pr-gate-typescript.yml` AND in `actions/setup-node-pnpm/action.yml`. No placeholder string (`"latest"`, `""`) is allowed — both defaults must be concrete semver at commit time. Same pattern applies to `typescript-version` in `run-tsc`. There is NO `eslint-version` input (see Tool pin location above — eslint is consumer-owned).

**Node version requirement**: `node-version` is consumer-supplied, but gh-manage's toolchain requires **Node 20 or higher** — this constraint is driven by `vitest 4.x`'s engine requirement (`^20 || ^22 || >=24`). The input description documents this: `"Node.js version (e.g., '20', '22'). Must be 20 or higher."`. Consumers passing older versions will see vitest or install failures with unrelated-looking error messages; this is intentional — gh-manage does not add runtime version guards.

**Pipeline** (preserves Phase 1 order so consumers can reason about both reusables uniformly):

1. Extract gh-manage ref from `github.workflow_ref`
2. Checkout consumer repository (`actions/checkout@v4`, `fetch-depth: 0`)
3. Self-checkout gh-manage into `.gh-manage/` at the extracted ref
4. `log-gh-manage-version` (shared composite)
5. `setup-node-pnpm` (new composite) with `node-version` + `pnpm-version`
6. Install step: inline shell that runs `install-command` inside `working-directory`
7. `run-eslint` if `inputs.lint`
8. `run-tsc` if `inputs.type-check`
9. Setup step: inline shell that runs `setup-command` if non-empty
10. Test step: inline shell that runs `test-command`

`permissions: contents: read` at workflow level; no write scope required.

### Layer 2 composite actions

#### `actions/setup-node-pnpm/action.yml`

- **Inputs**: `node-version` (required, description), `pnpm-version` (default pinned, description)
- **Steps**:
  1. `pnpm/action-setup@v4` with `version: ${{ inputs.pnpm-version }}` — must run before `setup-node` so pnpm is on PATH
  2. `actions/setup-node@v4` with `node-version: ${{ inputs.node-version }}` — **NO `cache: pnpm`** (see caching rationale below)
  3. Inline shell: `node -v && pnpm -v` for traceability
- **Error surface**: step failures propagate; `setup-node`'s errors are surfaced verbatim.
- **Caching rationale (v0.2.0)**: `setup-node`'s `cache: pnpm` feature resolves the lockfile at a path controlled by `cache-dependency-path`, which defaults to the repository root. Because the reusable workflow supports `working-directory` pointing at a subdirectory, resolving the lockfile path generically requires plumbing `working-directory` into the composite action as a `cache-dependency-path` argument. For v0.2.0 the composite action skips caching entirely; a follow-up can add a `cache-dependency-path` input if CI wall time becomes painful. This matches Phase 1's posture: `setup-python-uv` relied on `astral-sh/setup-uv@v4`'s own caching mechanism without injecting a consumer-specific path.

#### `actions/run-eslint/action.yml`

- **Inputs**: `working-directory` (default `"."`)
- **Steps**: one inline shell step
  ```
  set -euo pipefail
  echo "::group::eslint"
  pnpm exec eslint .
  echo "::endgroup::"
  ```
- **Assumes**: consumer has `eslint.config.js` (flat config) in `working-directory` AND has `eslint`, `typescript-eslint`, `@eslint/js` in `devDependencies`. `pnpm install` must have run before this composite. Missing config → eslint exits non-zero with a self-explanatory error.
- **Why not `pnpm dlx`**: eslint 10.x flat config imports `typescript-eslint` and `@eslint/js` as peer dependencies. Stuffing them through `pnpm dlx --package eslint --package typescript-eslint --package @eslint/js` creates a temporary env whose `node_modules` path is not guaranteed to be resolvable from a config file loaded against the consumer's cwd. The `pnpm exec` approach is simpler, matches the main design spec (line 305 of `2026-04-10-gh-manage-design.md`), and is analogous to Phase 1's `run-mypy` using `uv run --with` (which runs inside the project environment). Unlike ruff (standalone binary) and tsc (standalone compiler), eslint is inherently a plugin host, so pinning its version rigidly inside a composite action is unproductive. gh-manage's `docs/usage/typescript.md` recommends specific versions; fixtures pin them in `devDependencies`.

#### `actions/run-tsc/action.yml`

- **Inputs**: `working-directory` (default `"."`), `typescript-version` (default pinned), `tsconfig` (default `"tsconfig.json"`)
- **Steps**: one inline shell step
  ```
  set -euo pipefail
  echo "::group::tsc --noEmit"
  # pnpm 10+: use --package to disambiguate the multi-bin typescript package
  pnpm --package="typescript@${TYPESCRIPT_VERSION}" dlx tsc --noEmit -p "${TSCONFIG}"
  echo "::endgroup::"
  ```
- **Rationale for `-p` explicit**: allows consumers with multiple tsconfigs (e.g., `tsconfig.build.json`) to override via a follow-up input surface if needed. For v0.2.0 the reusable workflow does not expose it; the default is sufficient.

### Fixtures

All under `tests/fixtures/projects/typescript-*/`. Each fixture is a minimal but realistic TS project with:
- `package.json` (name, private, type: module, scripts with `"test": "vitest run"`, devDependencies pinned vitest)
- `pnpm-lock.yaml` (generated by `pnpm install` — committed)
- `eslint.config.js` (flat config using `@eslint/js` recommended preset)
- `tsconfig.json` (strict: true, noEmit: true, target: ES2022, module: ESNext, moduleResolution: Bundler)
- `src/index.ts` — the payload that differs per fixture
- `tests/index.test.ts` — one passing vitest test

#### `typescript-sample/`

- `src/index.ts`:
  ```ts
  export function add(a: number, b: number): number {
    return a + b;
  }
  ```
- `tests/index.test.ts` — vitest test covering `add`
- Expected: eslint clean, tsc clean, vitest passes

#### `typescript-lint-fail/`

- `src/index.ts`:
  ```ts
  export function add(a: number, b: number): number {
    const unused = 42; // triggers no-unused-vars
    return a + b;
  }
  ```
- `tests/index.test.ts` — identical to `typescript-sample`; passes because vitest runtime ignores the unused local
- Expected: **eslint fails** with `no-unused-vars` in stdout; **tsc clean** (strict mode does NOT enable `noUnusedLocals`, so tsc ignores the local); **vitest passes** when run directly
- Rationale: `no-unused-vars` is a core rule in `@eslint/js/recommended`, stable across 9.x and 10.x, and the TS analogue of Phase 1's ruff `F401`. Note: `@typescript-eslint/no-unused-vars` is the effective rule when `typescript-eslint` is active (the plain `no-unused-vars` is disabled in the fixture's eslint.config.js to avoid double reporting). The smoke-test grep targets the substring `no-unused-vars` which matches both rule ids. Placing the unused local inside a function body (not module scope) keeps it from being ambiguous with tsc's optional `noUnusedLocals` check.

#### `typescript-type-fail/`

- `src/index.ts`:
  ```ts
  export function add(a: number, b: number): number {
    const x: number = "string"; // TS2322: type 'string' is not assignable to type 'number'
    return a + b + x;
  }
  ```
- `tests/index.test.ts` — vitest test that imports `add`. Passes because vitest runs uncompiled TS (no type checking at runtime) and `"string"` is coerced at runtime in JS arithmetic, so the function still returns a number-like value. The failing assertion is intentional to be clean on vitest — see the local verification table below for exact behavior.
- Expected: **eslint clean** (the `const x` is used → no-unused-vars does not fire); **tsc fails** with `TS2322` in stdout; **vitest passes** when run directly because vitest strips types
- Rationale: `TS2322` is a fundamental TS error code that has been stable for 10+ years. Using `x` in the return expression keeps it from triggering `no-unused-vars`.
- **Plan-phase verification**: the implementer MUST confirm `pnpm test` exits 0 on this fixture. The primary form uses `x` in the return expression, which causes the runtime value of `add(1, 2)` to be `"3string"` (string concatenation) instead of `3`. If the vitest test asserts `expect(add(1, 2)).toBe(3)`, it will fail. **Recommended fallback form** that keeps runtime behavior clean:
  ```ts
  export function add(a: number, b: number): number {
    const x: string = 42; // TS2322: type 'number' is not assignable to type 'string'
    void x;                // satisfies eslint no-unused-vars without affecting runtime
    return a + b;
  }
  ```
  `void x` is an expression that discards its operand; eslint's `no-unused-vars` rule counts it as a use. tsc still fails with `TS2322` on the `const x` line. vitest runs `add(1, 2)` which returns `3` cleanly. Either form is acceptable; the implementer picks whichever satisfies all 4 L1 verification checks (see § Testing Strategy 5.3).

### `smoke-test.yml` extension

Add 3 new jobs, preserving Phase 1's 3 Python jobs untouched.

- **`positive-typescript-sample`** — calls `./.github/workflows/reusable-pr-gate-typescript.yml` with `node-version: "20"` and `working-directory: tests/fixtures/projects/typescript-sample`. Must be green.
- **`negative-typescript-lint-fail`** — regular job (NOT `uses: .../reusable-*.yml`):
  1. `actions/checkout@v4` with `fetch-depth: 0`
  2. `./actions/setup-node-pnpm` (NOT `./.gh-manage/actions/...` — smoke-test runs in gh-manage's own tree)
  3. `pnpm install --frozen-lockfile` inside the fixture dir
  4. `./actions/run-eslint` with `continue-on-error: true` and `id: eslint`
  5. Assert `steps.eslint.outcome == 'failure'`
  6. Direct tool run: `pnpm exec eslint .` inside fixture dir, grep stdout for `no-unused-vars`, fail if not found
- **`negative-typescript-type-fail`** — regular job, mirror of above but with `./actions/run-tsc` and `TS2322` grep target

Extend the `paths:` filter on `pull_request` and `push` triggers to include:
- `.github/workflows/reusable-pr-gate-typescript.yml`
- `tests/fixtures/projects/typescript-*/**` (or update existing `tests/fixtures/projects/**` if it's already broad)

### Documentation

#### `docs/usage/typescript.md` (new)

Mirror the structure of `docs/usage/python.md`:
- Prerequisites (pnpm, `eslint.config.js`, `tsconfig.json`, pnpm-lock.yaml committed, `gh-manage` access)
- Minimal example (`uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-typescript.yml@v0.2.0`)
- Inputs table
- Tool versions table (pnpm, eslint, typescript, with pinned values)
- Disabling individual checks (`lint: false`, `type-check: false`)
- Setup command for DB/fixture prep
- Versioning (same model as Phase 1; reference `docs/versioning.md` Phase 9 as "coming soon")
- Troubleshooting (reusable workflow not found, missing configs, lockfile drift, pnpm dlx version syntax)

#### `CHANGELOG-reusable.md`

Add to `[Unreleased]`, then promote to `[0.2.0]` at tag time:
- New reusable workflow `reusable-pr-gate-typescript.yml` with documented input surface
- 3 new composite actions (`setup-node-pnpm`, `run-eslint`, `run-tsc`) with pinned tool versions
- 3 new fixture projects
- 3 new smoke-test jobs
- `docs/usage/typescript.md` consumer guide
- Known limitations: pnpm only in v0.2.0, cross-repo not empirically validated, pinned versions diverge from latest (list versions)

#### Bundled small fixes

- `.gitignore` — add `.claude/`
- `docs/plans/2026-04-10-phase-1-reusable-pr-gate-python.md` — correct "12 files per fixture commit" → "15 files per fixture commit"
- `docs/specs/2026-04-10-gh-manage-design.md` — add a note to the `reusable-pr-gate-typescript.yml` Components subsection recording that v0.2.0 ships with pnpm-only (no `package-manager` input)

These are zero-risk and stay in the Phase 2 PR for convenience.

## Data Flow

### Consumer invocation → pipeline execution

Consumer repo's `.github/workflows/ci.yml`:

```yaml
jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-typescript.yml@v0.2.0
    with:
      node-version: "20"
```

Runtime sequence on the GHA runner:

1. GHA resolves the reusable ref (`v0.2.0`) and loads the workflow YAML.
2. `github.workflow_ref = "yakkuro/gh-manage/.github/workflows/reusable-pr-gate-typescript.yml@v0.2.0"`
3. Step `self-ref` parses the substring after `@` → `v0.2.0` → writes to `steps.self-ref.outputs.ref`.
4. Step `Checkout consumer repository` (`actions/checkout@v4`) populates `$GITHUB_WORKSPACE/` with the consumer's code at the triggering SHA.
5. Step `Checkout gh-manage (self)` (`actions/checkout@v4` with `repository: yakkuro/gh-manage`, `ref: v0.2.0`, `path: .gh-manage`) populates `$GITHUB_WORKSPACE/.gh-manage/` with gh-manage's tree at `v0.2.0`.
6. `log-gh-manage-version` composite runs.
7. `setup-node-pnpm` composite runs: `pnpm/action-setup@v4` installs pnpm first, then `actions/setup-node@v4` installs Node. Lockfile caching (`cache: pnpm`) is intentionally NOT configured in v0.2.0 — see the `setup-node-pnpm` component section for the rationale.
8. Inline install step runs `pnpm install --frozen-lockfile` with `working-directory: ${{ inputs.working-directory }}` (consumer's tree).
9. `run-eslint` composite runs if `lint: true`. `working-directory: ${{ inputs.working-directory }}`. Reads `eslint.config.js` from consumer's tree.
10. `run-tsc` composite runs if `type-check: true`. Reads `tsconfig.json` from consumer's tree.
11. Setup-command inline step runs if non-empty.
12. Test-command inline step runs.

### Two-tree isolation (critical)

Two distinct working trees on the runner:
- **Consumer tree**: `$GITHUB_WORKSPACE/` — caller's code; cwd for install/lint/tsc/test
- **gh-manage tree**: `$GITHUB_WORKSPACE/.gh-manage/` — composite action definitions; NEVER a cwd for consumer commands

Composite actions referenced via `./.gh-manage/actions/<name>` resolve their `action.yml` from the gh-manage tree, but the shell steps inside execute with `working-directory: ${{ inputs.working-directory }}` which is resolved against the job's top-level cwd (`$GITHUB_WORKSPACE`, i.e., the consumer tree). This is identical to Phase 1's run-ruff / run-mypy behavior.

### Smoke-test (same-repo) data flow

`smoke-test.yml` runs inside gh-manage's own PRs. The positive TS job calls `./.github/workflows/reusable-pr-gate-typescript.yml` — a LOCAL path — so GHA resolves it against the triggering SHA. The self-checkout step then re-checks-out gh-manage into `.gh-manage/`; this is redundant in same-repo but preserves identical path resolution to cross-repo. The negative jobs bypass the Layer 3 workflow and invoke composite actions directly at `./actions/<name>` (not `./.gh-manage/actions/<name>`) because they execute as regular jobs in gh-manage's own tree, identical to Phase 1's pattern.

### Cross-repo validation: not in Phase 2

As documented in Phase 1's CHANGELOG, cross-repo invocation (consumer outside gh-manage calling the reusable) has never been empirically validated. Phase 2 continues the pattern and also does NOT test cross-repo. Phase 3 (port-registry adoption) will exercise both Python and TypeScript reusables from an external consumer; any issues surface there and are hotfixed in `v0.2.1`.

**Shared risk with Phase 1**: if Phase 3 reveals a fundamental flaw in the self-checkout pattern (e.g., `github.workflow_ref` parsing behaves differently for external callers, or checkout path resolution differs), BOTH the Python and TypeScript reusables are affected. The fix surface is shared: correcting the Layer 3 self-checkout block once in both reusable workflows. The Phase 2 PR does not need to defensively mitigate this — the same risk was already accepted for v0.1.0.

## Error Handling

### Shell discipline (inherited from Phase 1)

Every shell step in every composite action and the reusable workflow:
- Starts with `set -euo pipefail`
- Uses `shell: bash` explicitly
- Passes inputs through an `env:` block (not via `${{ inputs.x }}` interpolation in the script body — prevents shell injection and quoting bugs)
- Prints actionable `::error::` messages on failure
- Never uses `|| true`, bare catches, or suppressed exit codes

### Failure mode taxonomy

| Failure | Detection | Visible message | Outcome |
|---|---|---|---|
| `github.workflow_ref` unparseable | `self-ref` step | `::error::Could not parse gh-manage ref from github.workflow_ref='<value>'` | fail |
| gh-manage self-checkout fails | `actions/checkout@v4` | GHA built-in error; composite actions unavailable for remainder | fail |
| pnpm install fails | inline shell | stderr from pnpm + `::error::install-command failed` | fail |
| eslint reports violation | `run-eslint` step | eslint output (rule ids + file:line) | fail, job red |
| tsc reports type error | `run-tsc` step | tsc output (TS error codes + file:line) | fail, job red |
| setup-command fails | inline shell | `::error::setup-command failed: <cmd>` | fail |
| test-command fails | inline shell | test runner output | fail |
| `pnpm exec eslint` fails to spawn (missing devDep) | `run-eslint` | pnpm stderr — visibly different from "eslint found a bug" because output won't contain rule ids | fail |

### Negative-fixture discipline (Phase 1 learning #4)

This is the highest-leverage error-handling design and MUST be enforced.

Phase 1 nearly shipped a broken composite action because negative fixtures initially only asserted `outcome == 'failure'`, and a bug in `uvx "ruff==0.8.0"` (wrong syntax) caused all composite steps to fail immediately, which the negative fixtures happily accepted.

**Every negative smoke-test job MUST have two assertions**:

1. **Outcome assertion** — after the `continue-on-error: true` composite step, verify `steps.<id>.outcome == 'failure'`. Catches the "composite silently succeeded" bug class.
2. **Reason assertion** — run the underlying tool DIRECTLY (not via the composite action) and `grep` for the specific expected error identifier. Catches the "composite failed, but for the wrong reason" bug class.

Concrete Phase 2 assertions:

- **`negative-typescript-lint-fail`**: direct run `pnpm exec eslint .` in the fixture dir; grep stdout for the literal string `no-unused-vars`.
- **`negative-typescript-type-fail`**: direct run `pnpm --package="typescript@<pin>" dlx tsc --noEmit`; grep stdout for the literal string `TS2322`.

Both identifiers are stable: `no-unused-vars` is a core eslint rule present in `@eslint/js/recommended`; `TS2322` has been the TypeScript type-assignment-mismatch error code since the early versions of tsc. If either the outcome OR reason assertion fails, the smoke-test job fails with a clear `::error::` explaining which check failed and the captured output.

### Consumer-facing troubleshooting

`docs/usage/typescript.md` will document:
- **"reusable workflow not found"** — repo access setting (private gh-manage → allow consumers under `yakkuro` org)
- **"eslint config missing"** — consumer must have `eslint.config.js` (flat config)
- **"tsc: Cannot find tsconfig.json"** — consumer must have `tsconfig.json` at `working-directory`
- **"pnpm-lock.yaml not found"** — consumer must run `pnpm install` and commit the lockfile
- **"type error I don't see locally"** — pinned TS version may differ from consumer's devDep; this is intentional per gh-manage's philosophy; consumer can add the pinned version to their devDeps for parity

## Testing Strategy

### Two-layer testing, mirroring Phase 1

| Layer | What | Where | When |
|---|---|---|---|
| **L1** — fixture local verification | `pnpm install && pnpm exec eslint . && pnpm --package="typescript@<pin>" dlx tsc --noEmit && pnpm test` inside each fixture | developer workstation | manual during plan/implement phase |
| **L2** — smoke-test.yml | Reusable workflow + composite actions via GHA on a PR | CI | every PR touching Phase 2 files |

No L3 (external consumer) test until Phase 3.

### Post-Phase 2 smoke-test job matrix

6 jobs total:

Phase 1 (unchanged):
1. `positive-python-sample`
2. `negative-python-lint-fail`
3. `negative-python-test-fail`

Phase 2 (new):
4. `positive-typescript-sample` — full reusable pipeline, must be green
5. `negative-typescript-lint-fail` — composite step-level + direct-tool reason verification, must be green
6. `negative-typescript-type-fail` — same pattern, reason `TS2322`, must be green

All 6 must be green before merge.

### L1 fixture verification commands

```bash
# typescript-sample (expect all exit 0)
cd tests/fixtures/projects/typescript-sample
pnpm install --frozen-lockfile
pnpm exec eslint .
pnpm --package="typescript@<pin>" dlx tsc --noEmit
pnpm test

# typescript-lint-fail (eslint expected to fail with no-unused-vars)
cd tests/fixtures/projects/typescript-lint-fail
pnpm install --frozen-lockfile
pnpm exec eslint . ; echo "exit=$?"   # expect non-zero + 'no-unused-vars' in output
pnpm --package="typescript@<pin>" dlx tsc --noEmit
pnpm test

# typescript-type-fail (tsc expected to fail with TS2322)
cd tests/fixtures/projects/typescript-type-fail
pnpm install --frozen-lockfile
pnpm exec eslint .
pnpm --package="typescript@<pin>" dlx tsc --noEmit ; echo "exit=$?"   # expect non-zero + 'TS2322' in output
pnpm test
```

**Red verification protocol** (what "confirm fails with specific reason" means operationally):

For each negative fixture, during local L1 verification the implementer MUST:

1. **Exit-code check**: run the tool (`pnpm exec eslint .` or `pnpm --package="typescript@<pin>" dlx tsc --noEmit`) — confirm non-zero exit status.
2. **Reason check**: capture stderr+stdout and `grep` for the expected identifier (`no-unused-vars` or `TS2322`). Confirm the identifier appears in the captured output.
3. **Isolation check**: the OTHER tool (eslint for type-fail, tsc for lint-fail) must exit 0. This proves the fixture's failure is isolated to the intended dimension and isn't leaking into the other check.
4. **Vitest check**: `pnpm test` must exit 0. This proves the fixture's test suite is runnable independent of lint/type errors.

If any of the 4 checks fails, the fixture is broken and must be adjusted before pushing. The smoke-test CI-level assertions (described in § Error Handling 4.3) are a second layer that catches regressions after merge, but L1 is where the fixture is declared correct.

### gh-manage's own CI

`ci.yml` runs only `reusable-pr-gate-python.yml` against gh-manage's Python code. TS fixtures under `tests/fixtures/projects/typescript-*/` are excluded from Python tooling by existing `pyproject.toml` rules:
- `[tool.pytest.ini_options] addopts = [..., "--ignore=tests/fixtures"]` — pytest skips the entire fixtures tree
- `[tool.ruff] extend-exclude = ["tests/fixtures/projects"]` — ruff skips all fixture projects
- `mypy` runs against `src` only (per `run-mypy` composite default) — no fixture path reached

No pyproject.toml changes required for Phase 2.

### PR-level verification gate (mirrors Phase 1 Task 22)

Before claiming Phase 2 complete, tick all Acceptance Criteria above, run the cross-agent review protocol (4 reviewers in parallel per `claude-dotfiles/rules/workflow-review.md`), fix all CRITICAL/HIGH findings, and only then merge.

## Dependencies

### External

- `pnpm/action-setup@v4`
- `actions/setup-node@v4`
- `actions/checkout@v4`
- `@eslint/js` (fixture devDep, not pinned by gh-manage)
- vitest (fixture devDep, not pinned by gh-manage)

### Internal

- `actions/log-gh-manage-version/` (shared with Phase 1, unchanged)
- `actions/checkout@v4` behavior for the self-checkout pattern (inherited from Phase 1)

### Version pins to be resolved in the plan phase

Values were resolved by running `npm view <pkg> version` at the start of Phase 2 implementation on 2026-04-10. Note: these are newer than the initial plan-writing assumptions (which expected eslint 9.x and TypeScript 5.x); the jump is 1 major per tool but the APIs used (flat config via `tseslint.config()`, `moduleResolution: Bundler`) remain backwards compatible. The CHANGELOG records the exact pins chosen.

- pnpm: `10.33.0` (pinned inside `setup-node-pnpm` composite and reusable workflow default)
- eslint: `10.2.0` (fixture devDependencies only; NOT pinned in the `run-eslint` composite action — consumer-owned per the hybrid pin strategy)
- `@eslint/js`: `10.0.1` (fixture devDependencies; co-versioned with eslint)
- `typescript-eslint`: `8.58.1` (fixture devDependencies; peer-dep compat: `eslint ^8.57.0 || ^9.0.0 || ^10.0.0` and `typescript >=4.8.4 <6.1.0` — both satisfied)
- typescript: `6.0.2` (pinned inside `run-tsc` composite action)
- vitest: `4.1.4` (fixture devDependencies only; its engine constraint `^20 || ^22 || >=24` drives the **Node 20+ minimum** for consumers)
- `@types/node`: `22.19.17` (fixture devDependencies; tracks Node 22 LTS line)

## References

- [`docs/specs/2026-04-10-gh-manage-design.md`](./2026-04-10-gh-manage-design.md) — main design spec (§ Components, § Phase 2 Acceptance Criteria, § Layer 2 共通規約)
- [`docs/plans/2026-04-10-phase-1-reusable-pr-gate-python.md`](../plans/2026-04-10-phase-1-reusable-pr-gate-python.md) — Phase 1 plan (structural template for Phase 2 plan)
- [`CHANGELOG-reusable.md`](../../CHANGELOG-reusable.md) — v0.1.0 entry (behavior shipped + known limitations to inherit)
- [`docs/usage/python.md`](../usage/python.md) — template for `docs/usage/typescript.md`
- [`.github/workflows/reusable-pr-gate-python.yml`](../../.github/workflows/reusable-pr-gate-python.yml) — Layer 3 structural template
- [`.github/workflows/smoke-test.yml`](../../.github/workflows/smoke-test.yml) — smoke-test negative-fixture pattern
- [`actions/setup-python-uv/action.yml`](../../actions/setup-python-uv/action.yml), [`actions/run-ruff/action.yml`](../../actions/run-ruff/action.yml), [`actions/run-mypy/action.yml`](../../actions/run-mypy/action.yml) — Layer 2 structural templates
- [Issue #2](https://github.com/yakkuro/gh-manage/issues/2) — Phase 2 handoff context (includes the 7 Phase 1 learnings to embed as warnings in the implementation plan)

## Phase 1 learnings to embed as plan warnings

Reproduced here from Issue #2 so the plan writer can cite them verbatim:

1. **`continue-on-error` at job level does NOT work with `jobs.<id>.uses:`**. Use regular jobs with composite invocations + step-level `continue-on-error`.
2. **`pnpm dlx` version syntax must be verified locally before committing**. Phase 1 lost an iteration on `uvx "ruff==0.8.0"` (wrong, needs `@`). `pnpm dlx` very likely uses `@` too; confirm at plan phase.
3. **gh-manage's own `ci.yml` runs against the entire repo including `tests/fixtures/`**. Python exclusions already cover TS fixtures, but re-verify after adding the new directories.
4. **Negative fixtures that only check `outcome == 'failure'` are unreliable**. Always add a direct-tool reason verification.
5. **Cross-repo self-checkout has NOT been empirically validated**. Same-repo only in Phases 1 and 2; Phase 3 is the first real test.
6. **Feature-branch `.github/workflows/*.yml` files that do not yet exist on `main` cannot be invoked via `gh workflow run`**. Phase 1 worked around this by opening a draft PR to trigger `on: pull_request:`. Phase 2 will hit the same.
7. **Pytest `.pyc` cache staleness after file restoration via `mv`**. Not Phase 2-critical (no Python Red-Green planned) but generally `touch <file>` after restore.
