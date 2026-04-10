# Python PR Gate — Consumer Usage

This guide shows how to use `yakkuro/gh-manage`'s reusable Python PR gate in your own repository.

## Prerequisites

- Your project uses `uv` for dependency management and has a valid `pyproject.toml` at the working-directory root.
- Your project has type hints on public functions (mypy will check `src/` by default).
- Your code formatting matches `ruff format` defaults (the reusable runs `ruff format --check`).
- **`yakkuro/gh-manage` access is enabled for your repository.** Because gh-manage is currently a private repository, your calling repo must be allowed to consume its reusable workflows. On the gh-manage repo, go to `Settings → Actions → General → Access` and set `"Accessible from repositories owned by the user 'yakkuro'"`. Without this, your workflow run fails with a "reusable workflow not found" error before the job starts.

## Minimal example

Create `.github/workflows/ci.yml` in your repository:

```yaml
name: CI

on:
  pull_request:
    branches: [main]

jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v0.1.0
    with:
      python-version: "3.12"
```

That's it. The workflow will:

1. Check out your repository
2. Install Python 3.12 and the pinned `uv` version
3. Run `uv sync` to install dependencies
4. Run `ruff check .` and `ruff format --check .`
5. Run `mypy src/`
6. Run `uv run pytest`

## Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `python-version` | string | **required** | Python version to install (e.g., `"3.12"`). |
| `working-directory` | string | `"."` | Project directory inside the repo. Set this if your Python project lives in a subdirectory. |
| `install-command` | string | `"uv sync"` | Dependency install command. |
| `test-command` | string | `"uv run pytest"` | Test command. |
| `lint` | boolean | `true` | Run `ruff check` and `ruff format --check`. |
| `type-check` | boolean | `true` | Run `mypy src/`. |
| `setup-command` | string | `""` | Optional shell command executed after install, before tests. |
| `uv-version` | string | `"0.5.0"` | `uv` release pin. Override only if you need a newer release. |

## Tool versions

gh-manage pins tool versions inside its composite actions for reproducibility:

| Tool | Version |
|---|---|
| `uv` | 0.5.0 |
| `ruff` | 0.8.0 |
| `mypy` | 1.12.0 |

These are pinned at the gh-manage level — consumers do not need to pin them in their own `pyproject.toml`. To upgrade a pinned tool, gh-manage must release a new version.

## Disabling individual checks

If your project can't pass `mypy` yet (or you don't want it), disable it:

```yaml
jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v0.1.0
    with:
      python-version: "3.12"
      type-check: false
```

Same applies to `lint: false`. Disabling both is possible but defeats the purpose — consider whether you should be using this gate at all.

## Setup command for database or filesystem prep

If your tests need a database or filesystem initialization step:

```yaml
jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v0.1.0
    with:
      python-version: "3.12"
      setup-command: "uv run python scripts/init_db.py"
```

The command runs after `install-command` and before `test-command`. Failure aborts the job with a clear error.

## Versioning

`@v0.1.0` is the initial stable reusable workflow release. During the v0.x phase, use immutable version tags (`@v0.1.0`, `@v0.2.0`, etc.). A moving `@v1` tag will exist once gh-manage reaches v1.0.0.

Pin to a specific immutable tag for production repositories. Use `@main` only for gh-manage development or deliberate tracking of the latest changes.

## Troubleshooting

**ruff format --check fails but my code looks fine** — run `uvx "ruff@0.8.0" format .` locally to see the diff ruff proposes, and commit the result.

**mypy reports missing stubs** — gh-manage's `run-mypy` composite action uses `uv run --with mypy==1.12.0 mypy src`, which sees your project's installed dependencies. If a dependency lacks type stubs, add the stubs to your `dev` dependency group or set `ignore_missing_imports = true` under `[tool.mypy]` in your `pyproject.toml`.

**The reusable can't find my project** — double-check `working-directory` matches the path containing `pyproject.toml`.

**I need a newer ruff/mypy than gh-manage pins** — open an issue on `yakkuro/gh-manage` asking for a pin bump. Do not fork.

## See also

- Design spec: `docs/specs/2026-04-10-gh-manage-design.md`
- Versioning strategy: `docs/versioning.md` (Phase 9 deliverable)
