# TypeScript PR Gate — Consumer Usage

This guide shows how to use `yakkuro/gh-manage`'s reusable TypeScript PR gate in your own repository.

## Prerequisites

- Your project uses `pnpm` for dependency management and has a valid `package.json` at the working-directory root.
- Your project has `pnpm-lock.yaml` committed.
- Your project has an `eslint.config.js` (flat config; eslint 10.x) at the working-directory root.
- Your project has a `tsconfig.json` at the working-directory root.
- Your project's `devDependencies` include `eslint`, `typescript-eslint`, and `@eslint/js`. See the Tool versions table below for recommended versions.
- **Minimum Node version: 20.** This is driven by vitest 4.x's engine constraint (`^20 || ^22 || >=24`).
- **`yakkuro/gh-manage` access is enabled for your repository.** Because gh-manage is currently a private repository, your calling repo must be allowed to consume its reusable workflows. On the gh-manage repo, go to `Settings → Actions → General → Access` and set `"Accessible from repositories owned by the user 'yakkuro'"`. Without this, your workflow run fails with a "reusable workflow not found" error before the job starts.
- **Phase 2 v0.2.0 supports pnpm only.** `npm` and `yarn` support is planned for a future release.

## Minimal example

Create `.github/workflows/ci.yml` in your repository:

```yaml
name: CI

on:
  pull_request:
    branches: [main]

jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-typescript.yml@v0.2.0
    with:
      node-version: "20"
```

That's it. The workflow will:

1. Check out your repository
2. Install Node.js 20 and the pinned `pnpm` version (10.33.0)
3. Run `pnpm install --frozen-lockfile` to install your dependencies
4. Run `pnpm exec eslint .` (uses your devDependencies — you pin eslint and its peer deps)
5. Run `pnpm --package="typescript@6.0.2" dlx tsc --noEmit -p tsconfig.json` (gh-manage pins TypeScript)
6. Run `pnpm test`

## Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `node-version` | string | **required** | Node.js version to install (e.g., `"20"`, `"22"`). Must be 20 or higher. |
| `working-directory` | string | `"."` | Project directory inside the repo. Set this if your TypeScript project lives in a subdirectory. |
| `install-command` | string | `"pnpm install --frozen-lockfile"` | Dependency install command. |
| `test-command` | string | `"pnpm test"` | Test command. |
| `lint` | boolean | `true` | Run `pnpm exec eslint .` against your devDependencies. |
| `type-check` | boolean | `true` | Run `tsc --noEmit` using the pinned TypeScript version. |
| `setup-command` | string | `""` | Optional shell command executed after install, before tests. |
| `pnpm-version` | string | `"10.33.0"` | `pnpm` release pin. Override only if you need a specific release. |

## Tool versions (v0.2.0)

gh-manage uses a **hybrid pinning strategy** — some tools are pinned inside the composite actions, others are consumer-owned:

| Tool | Version | Pinning scope |
|---|---|---|
| `pnpm` | `10.33.0` | Pinned inside `setup-node-pnpm` composite action |
| `typescript` | `6.0.2` | Pinned inside `run-tsc` composite action via `pnpm --package` |
| `eslint` | `10.2.0` (recommended) | NOT pinned inside the composite — you pin in `devDependencies` |
| `typescript-eslint` | `8.58.1` (recommended) | NOT pinned — you pin in `devDependencies` |
| `@eslint/js` | `10.0.1` (recommended) | NOT pinned — you pin in `devDependencies` |

**Why the hybrid?** `tsc` is a self-contained compiler with no peer dependencies, so pinning it inside gh-manage is clean and reproducible (the direct analogue of Phase 1's pinned `ruff`). `eslint` 10.x flat config imports `typescript-eslint` and `@eslint/js` as peer dependencies that must resolve from the same `node_modules` — running eslint through `pnpm dlx` creates a temporary env whose path is not guaranteed to resolve peer deps correctly. gh-manage therefore uses `pnpm exec eslint .` and asks you to pin eslint and its peer deps in your own `devDependencies`. This is analogous to Phase 1's `run-mypy` using `uv run --with`, which similarly delegates to the project environment.

To upgrade `pnpm` or `typescript`, gh-manage must release a new version. To upgrade `eslint` family tools, update your own `devDependencies` — gh-manage will consume whatever you have installed.

## Example `eslint.config.js`

gh-manage does not provide a default `eslint.config.js` — that's your project's concern. A minimal working example:

```javascript
// @ts-check
import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    files: ['src/**/*.ts', 'tests/**/*.ts'],
    extends: [
      eslint.configs.recommended,
      ...tseslint.configs.recommended,
    ],
  },
  {
    ignores: ['node_modules/**', 'dist/**'],
  },
);
```

## Example `tsconfig.json`

Also your project's concern. A minimal example compatible with bundler-based test runners like vitest:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "isolatedModules": true
  },
  "include": ["src/**/*", "tests/**/*"]
}
```

## Disabling individual checks

If your project can't pass `tsc` yet (or you don't want it), disable it:

```yaml
jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-typescript.yml@v0.2.0
    with:
      node-version: "20"
      type-check: false
```

Same applies to `lint: false`. Disabling both is possible but defeats the purpose — consider whether you should be using this gate at all.

## Setup command for database or filesystem prep

If your tests need a database or filesystem initialization step:

```yaml
jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-typescript.yml@v0.2.0
    with:
      node-version: "20"
      setup-command: "pnpm exec tsx scripts/init-db.ts"
```

The command runs after `install-command` and before `test-command`. Failure aborts the job with a clear error.

## Versioning

`@v0.2.0` is the initial stable TypeScript reusable workflow release. During the v0.x phase, use immutable version tags (`@v0.1.0`, `@v0.2.0`, etc.). A moving `@v1` tag will exist once gh-manage reaches v1.0.0.

Pin to a specific immutable tag for production repositories. Use `@main` only for gh-manage development or deliberate tracking of the latest changes.

`docs/versioning.md` with the full versioning policy is a Phase 9 deliverable.

## Troubleshooting

**"reusable workflow not found"** — your repo doesn't have access to the private gh-manage. See the Prerequisites section above for the repo access setting.

**"Cannot find module 'typescript-eslint'"** — your project is missing `typescript-eslint` in `devDependencies`. Add it via `pnpm add -D typescript-eslint`.

**"Cannot find module '@eslint/js'"** — same as above for `@eslint/js`.

**"eslint.config.js not found"** — your project is missing the flat config file. Create one at the working-directory root. See the example above.

**"tsc: Cannot find tsconfig.json"** — your project is missing `tsconfig.json` at the working-directory root. Create one.

**"pnpm-lock.yaml not found" or "lockfile drift"** — your project hasn't committed `pnpm-lock.yaml`, or it's out of sync. Run `pnpm install` locally and commit the result.

**"Type error I don't see locally"** — the pinned TypeScript version (`6.0.2`) may differ from your project's `devDependencies`. gh-manage intentionally pins a specific TypeScript version inside its `run-tsc` composite; if you want exact parity between local and CI, add the same version to your `devDependencies`.

**"I need a newer eslint / typescript-eslint / @eslint/js"** — these are NOT pinned by gh-manage. Upgrade them in your own `devDependencies`. gh-manage's recommendations are guidance, not enforcement.

**"I need a newer TypeScript than gh-manage pins"** — open an issue on `yakkuro/gh-manage` asking for a pin bump. Do not fork.

**"My tests need Node 18 or earlier"** — v0.2.0 is supported on **Node 20 or higher only**. This is driven by vitest 4.x's engine constraint (`^20 || ^22 || >=24`), which is what the fixture test runner uses and what drives the smoke-test matrix. Passing `node-version: "18"` is NOT a supported configuration: `actions/setup-node@v4` will install Node 18, but `pnpm install --frozen-lockfile` for most modern TS projects will fail because of transitive engine constraints. If you need Node 18 support, open an issue on `yakkuro/gh-manage`; the minimum may be lowered in a future release once a Node-18-compatible test runner is adopted.

## See also

- Design spec: [`docs/specs/2026-04-10-gh-manage-design.md`](../specs/2026-04-10-gh-manage-design.md)
- Phase 2 design spec: [`docs/specs/2026-04-10-phase-2-typescript-design.md`](../specs/2026-04-10-phase-2-typescript-design.md)
- Python PR gate guide: [`docs/usage/python.md`](./python.md)
- Versioning strategy: `docs/versioning.md` (Phase 9 deliverable)
