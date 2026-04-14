# gh-manage

**Status:** v1.0 stable — reusable workflows and CLI are production-used across the `yakkuro` organization.

GitHub-based CI/CD, Issue management, and operational system for `yakkuro/*` repositories. `gh-manage` distributes reusable GitHub Actions workflows, composite actions, Issue/PR templates, label definitions, and branch protection policies across multiple repositories under a single declarative source.

## Three tracks

gh-manage ships three independent deliverables, each consumed in a different way. Reading them in order helps clarify what you are installing and why.

### 1. Reusable GitHub Actions workflows

- **Python PR gate** and **TypeScript PR gate** workflows that run `install → lint → type-check → setup → test` against consumer repos.
- Consumed via a `uses:` line in the consumer's `.github/workflows/ci.yml`:
  ```yaml
  uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.0.0
  ```
- Versioned independently at `v<major>.<minor>.<patch>` (currently `v1.0.0`).
- No installation required on the consumer side beyond adding the `uses:` line and specifying the `gh-manage-ref` input.

### 2. Python CLI (`gh-manage`)

- A `click`-based CLI with 6 subcommands: `labels`, `init`, `apply`, `protection`, `drift`, `issues`.
- Consumed via `uv tool install`:
  ```bash
  uv tool install git+https://github.com/yakkuro/gh-manage@cli/v1.0.0
  ```
- Versioned independently at `cli/v<major>.<minor>.<patch>` (currently `cli/v1.0.0`).
- Requires `uv` and `gh` CLI on the user's machine.

### 3. Bundled configuration and templates

- Label definitions, branch protection policies, profile specifications, and file templates shipped inside the CLI wheel.
- Consumed transparently through CLI subcommands (never accessed directly); `importlib.resources` resolves package data from the installed wheel.
- Versioned together with the CLI (`cli/v<major>.<minor>.<patch>`).

## Quick example

Install the CLI:

```bash
uv tool install git+https://github.com/yakkuro/gh-manage@cli/v1.0.0
gh-manage --version
```

Bootstrap a Python repo:

```bash
cd path/to/your-repo
gh-manage init --profile python-service .
```

Add the reusable PR gate to `.github/workflows/ci.yml`:

```yaml
name: CI
on:
  pull_request:
    branches: [main]
jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.0.0
    with:
      python-version: "3.12"
      gh-manage-ref: "v1.0.0"
```

## Getting started

Walk through [`docs/quick-start.md`](docs/quick-start.md) for a 15-minute onboarding from zero to green PR gate.

## Documentation

| Document | Purpose |
|---|---|
| [`docs/quick-start.md`](docs/quick-start.md) | 15-minute hands-on walkthrough |
| [`docs/architecture.md`](docs/architecture.md) | 3-track deliverable model + CLI 3-layer architecture |
| [`docs/versioning.md`](docs/versioning.md) | Semver policy, stability promise, pinning recommendations |
| [`docs/distribution-channels.md`](docs/distribution-channels.md) | Why Git tags, why not PyPI, install verification |
| [`docs/consumers.md`](docs/consumers.md) | Adoption examples and case studies |
| [`docs/release-checklist.md`](docs/release-checklist.md) | Pre-release / tagging / post-release procedures |
| [`docs/specs/2026-04-10-gh-manage-design.md`](docs/specs/2026-04-10-gh-manage-design.md) | Top-level design specification |
| [`CHANGELOG-reusable.md`](CHANGELOG-reusable.md) | Changelog for reusable workflows (`v<X.Y.Z>` tags) |
| [`CHANGELOG-cli.md`](CHANGELOG-cli.md) | Changelog for the Python CLI (`cli/v<X.Y.Z>` tags) |

## Scope boundaries

gh-manage is a focused operational tool, not a general-purpose platform. See the design spec's `## Non-Goals` section for the authoritative list. Not included: Claude runtime workflows, cross-repo dashboard UI, release management for other repos, Dependabot distribution, GitHub Enterprise support, PyPI publishing, `act`/nektos local execution.

## License

MIT. See [LICENSE](LICENSE).
