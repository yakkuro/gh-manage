# Versioning

gh-manage uses two independent release tracks — one for reusable GitHub Actions workflows, one for the Python CLI — each with its own semver.

## At a glance

- **Two independent tracks.** Reusable workflows use `vX.Y.Z` tags; the Python CLI uses `cli/vX.Y.Z` tags. Both share the same Git repository.
- **Strict semver 2.0.** MAJOR breaks, MINOR adds, PATCH fixes. No exceptions.
- **v1.0.0 = stability milestone.** All consumer-visible surfaces (workflow inputs, CLI subcommands, bundled schemas, pinned tool versions) are contract-stable starting at v1.0.0.
- **Production pins use exact tags.** Consumers pin `@v1.0.0` or `@cli/v1.0.0`, not floating tags.
- **Breaks announced with deprecation runway.** A v2.0 ships no sooner than 1 minor release after the break is announced.

The rest of this document expands each of those points with the full rules.

## Why two tracks?

Reusable workflows and the Python CLI are versioned **independently** because they evolve on different schedules.

- A bug fix in `reusable-pr-gate-python.yml` should be releasable without cutting a new CLI release.
- A new CLI subcommand should be releasable without bumping the reusable workflow ref every consumer pins.

Concrete example: during Phase 5 through Phase 8.5, the CLI shipped 6 releases (`cli/v0.1.0` → `cli/v0.6.0`) while the reusable track stayed at `v0.2.1`. Decoupled tracks made this possible without forcing consumers to re-pin their workflow refs.

## Two tag tracks

| Track | Tag format | Current | Contents |
|---|---|---|---|
| Reusable workflows | `vX.Y.Z` | `v1.0.0` | `.github/workflows/reusable-*.yml`, `actions/**` |
| Python CLI | `cli/vX.Y.Z` | `cli/v1.0.0` | `src/gh_manage/` (CLI module + bundled data), `pyproject.toml` |

Both tracks share the same Git repository (`yakkuro/gh-manage`). Tag prefixes disambiguate them. A single commit may carry both a `v<X.Y.Z>` and a `cli/v<X.Y.Z>` tag (the v1.0.0 release does exactly this).

## Semver policy

Both tracks follow [semver 2.0](https://semver.org/spec/v2.0.0.html) strictly:

- **MAJOR** (e.g., `v1.0.0` → `v2.0.0`) — removing or renaming a reusable workflow input, removing a CLI subcommand, changing a bundled data schema in a way that breaks existing configs.
- **MINOR** (e.g., `v1.0.0` → `v1.1.0`) — adding a new optional input to a reusable workflow, adding a new CLI subcommand, adding a new profile without touching existing ones.
- **PATCH** (e.g., `v1.0.0` → `v1.0.1`) — bug fixes that do not change any input surface or behavior guarantee, including pinned-tool-version upgrades that do not cause consumer CI to fail.

## Stability promise (starting v1.0.0)

What gh-manage guarantees NOT to break without a MAJOR bump:

- **Reusable workflow input surfaces** — every `inputs.*` field on `reusable-pr-gate-python.yml` and `reusable-pr-gate-typescript.yml` (name, type, default, required flag) is frozen.
- **CLI subcommand and flag names** — `gh manage {labels, init, apply, protection, drift, issues}` and their flags are frozen. Adding new subcommands or flags is MINOR-compatible.
- **Bundled data schemas** — `labels.yml`, `branch-protection.yml`, `profile.yml`, and `repos.yml` all freeze their top-level keys, `version:` field support, and validation rules.
- **Composite action names and inputs** — the 7 composite actions (`log-gh-manage-version`, `setup-python-uv`, `run-ruff`, `run-mypy`, `setup-node-pnpm`, `run-eslint`, `run-tsc`) and their input surfaces are frozen.
- **Pinned tool versions in reusable workflows** — `uv 0.5.0`, `ruff 0.8.0`, `mypy 1.12.0`, `pnpm 10.33.0`, `typescript 6.0.2`. Upgrading a pinned tool in a way that breaks consumer CI is a MAJOR break.

What is explicitly NOT part of the stability promise (internal):

- Module-level Python APIs inside `src/gh_manage/` (e.g., `compute_files_diff` signature). Refactoring is free.
- Test fixtures under `tests/fixtures/`.
- `smoke-test.yml` structure.
- Composite action step implementations (only the declared `inputs.*` surface is frozen).

## Pinning recommendations

| Use case | Recommended pin | Rationale |
|---|---|---|
| Production consumer | `@v1.0.0` (exact) | Deterministic, audited version in every CI run |
| Contributor developing against gh-manage | `@main` | Pulls the latest changes, faster feedback during contribution |
| CI float testing | `@v1` (not yet provided) | Would catch patch-level regressions automatically but requires gh-manage to maintain a floating tag |

**Note on `@v1` floating tag:** gh-manage does NOT currently publish a floating `@v1` tag. Consumers relying on "always get the latest 1.x" must manually update their `@<tag>` pin. If more than one major version coexists in the wild (after v2.0 ships), gh-manage will introduce a floating `@v1` tag convention at that time.

## Breaking change protocol

A v2.0 candidate is announced in this order:

1. **Discussion issue** on `yakkuro/gh-manage` explaining the problem and proposed break.
2. **`[Unreleased]` CHANGELOG entry** marked `**BREAKING**:` under the next MAJOR heading.
3. **At least one minor release** with a **deprecation warning** for the affected surface (e.g., `gh-manage` CLI prints a `::warning::` line to the GitHub Actions log; deprecated input still works).
4. **MAJOR release** that removes the deprecated surface.

In practice this means v2.0 will not ship sooner than 1 minor (v1.1) after a break is announced. Consumers get at least one minor release worth of warning before their pins need updating.

## Reference

- [`CHANGELOG-reusable.md`](../CHANGELOG-reusable.md) — reusable workflow releases (`v<X.Y.Z>` tags)
- [`CHANGELOG-cli.md`](../CHANGELOG-cli.md) — Python CLI releases (`cli/v<X.Y.Z>` tags)
- [`distribution-channels.md`](distribution-channels.md) — how consumers install each track
- [`release-checklist.md`](release-checklist.md) — pre-release / tagging / post-release procedures
