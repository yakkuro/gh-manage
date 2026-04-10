# gh-manage CLI — Consumer Usage

> **Current state (cli/v0.1.0):** the CLI ships as a skeleton. `--version`, `--help`, and per-subcommand `--help` work. Every other subcommand is a stub that exits 1 with a "not yet implemented — scheduled for cli/v0.X.0 (Phase N)" message pointing at the roadmap below. Domain logic lands in Phases 5-8.

## What it is

`gh manage` is a [gh CLI extension](https://docs.github.com/en/github-cli/github-cli/using-github-cli-extensions) that will eventually manage labels, branch protection, issue/PR templates, and drift detection for `yakkuro/*` repositories. Phase 4 ships only the skeleton — see the roadmap below for when each subcommand becomes real.

## Prerequisites

Install all of these **before** running `gh extension install yakkuro/gh-manage`:

- [`uv`](https://docs.astral.sh/uv/) on your `PATH`. Install via `curl -LsSf https://astral.sh/uv/install.sh | sh` (Linux/macOS) or `brew install uv` (macOS). The wrapper will fail with an actionable error if `uv` is missing or non-functional.
- Python 3.12+ resolvable by `uv`. uv auto-installs the required interpreter on first run if it's missing — no manual Python install needed.
- [`gh` CLI](https://cli.github.com/) 2.x or newer. Required for `gh extension install`.
- `git` — required by `gh extension install` under the hood.

**Non-interactive environments (CI, containers, sandboxed shells):** the wrapper's error message tells interactive users how to install uv. CI/CD must provision uv via its own mechanism (e.g., a prior step in the same workflow) — the wrapper cannot self-heal.

**Platform support:** Linux and macOS are the tested platforms. Windows is not explicitly targeted in v0.1.0 (may work via WSL but is untested).

## Installation

```bash
gh extension install yakkuro/gh-manage
```

This clones `yakkuro/gh-manage` into `~/.local/share/gh/extensions/gh-manage/` and registers the `gh-manage` shell wrapper at the root of that clone as a `gh` subcommand.

## Verifying the install

```bash
gh manage --version
```

Expected output (v0.1.0):

```
gh-manage, version 0.1.0
```

```bash
gh manage --help
```

Expected output (truncated):

```
Usage: gh-manage [OPTIONS] COMMAND [ARGS]...

  gh-manage — GitHub-based CI/CD, Issue management, and operations for
  yakkuro/* repositories.

Options:
  --version     Show the version and exit.
  -h, --help    Show this message and exit.

Commands:
  apply       Apply gh-manage profiles to existing repos (not yet implemented).
  drift       Scan repos for config drift (not yet implemented).
  init        Initialize a new repo with a gh-manage profile (not yet implemented).
  issues      Cross-repo issue listing (not yet implemented).
  labels      Synchronize GitHub repo labels against config/labels.yml (not yet implemented).
  protection  Synchronize branch protection (not yet implemented).
```

## Subcommand roadmap

Target versions are planned, not binding — if phase scope shifts, these numbers move with them. The stub error messages in the current release match this table.

| Subcommand | Planned version | Phase | What it will do |
|---|---|---|---|
| `labels` | **cli/v0.2.0** ✅ | Phase 5 | Synchronize GitHub repo labels against `config/labels.yml` (sync/diff/show subcommands) |
| `init` | cli/v0.3.0 | Phase 6 | Initialize a new repo with a gh-manage profile |
| `apply` | cli/v0.3.0 | Phase 6 | Apply a gh-manage profile to an existing repo |
| `protection` | cli/v0.4.0 | Phase 7 | Synchronize branch protection rules |
| `drift` | cli/v0.5.0 | Phase 8 | Scan repos for configuration drift |
| `issues` | cli/v0.5.0 | Phase 8 | Cross-repo issue listing |

## labels

Shipped in `cli/v0.2.0`. Synchronizes GitHub repository labels against `config/labels.yml` (the source of truth).

### Commands

- **`gh manage labels sync <repo>`** — Compute and optionally apply label changes.
  - Default: dry-run (shows the plan, exits 0)
  - `--apply` — execute the plan
  - `--prune` — include deletes in the plan (labels not in config get deleted; requires `--apply` to take effect)
  - `--dry-run` — explicit dry-run (conflicts with `--apply`)
  - `--config PATH` — path to labels.yml (default: `config/labels.yml`)

- **`gh manage labels diff <repo>`** — Show diff without applying.
  - Exits 0 if no diff, 1 if diff present (`git diff --quiet` style)
  - `--prune` — include would-be deletes in diff
  - `--config PATH` — same as sync

- **`gh manage labels show <repo>`** — List current labels on the repo (read-only). No config loaded.

### Repo argument format

Both bare name and `owner/repo` are accepted:

```bash
gh manage labels sync gh-manage               # expands to yakkuro/gh-manage
gh manage labels sync yakkuro/gh-manage       # explicit
gh manage labels sync other-org/other-repo    # non-yakkuro org
```

### Walkthrough: gh-manage self-dogfood

```bash
# 1. Dry-run: see the planned changes
$ gh manage labels diff gh-manage
~ bug → fix
    color=d73a4a  desc='Bug fix (fix:)'
~ documentation → docs
    color=0075ca  desc='Documentation changes (docs:)'
~ enhancement → feat
    color=a2eeef  desc='New feature (feat:)'
+ chore  color=e1e7eb  desc='Maintenance / housekeeping (chore:)'
+ refactor  color=ffd866  desc='Refactor without behavior change (refactor:)'
+ test  color=c5def5  desc='Test additions / changes (test:)'
+ ci  color=b4a5ff  desc='CI/CD changes (ci:)'
+ perf  color=5319e7  desc='Performance improvements (perf:)'
# Exit code: 1 (diff present)

# 2. Apply the changes
$ gh manage labels sync gh-manage --apply
# Same diff output, followed by progress lines and "Applied 8 changes."

# 3. Verify idempotency
$ gh manage labels diff gh-manage
No diff.
# Exit code: 0

# 4. Show the final state
$ gh manage labels show gh-manage
chore  color=e1e7eb  desc='Maintenance / housekeeping (chore:)'
ci  color=b4a5ff  desc='CI/CD changes (ci:)'
docs  color=0075ca  desc='Documentation changes (docs:)'
duplicate  color=cfd3d7  desc='This issue or PR already exists'
feat  color=a2eeef  desc='New feature (feat:)'
fix  color=d73a4a  desc='Bug fix (fix:)'
good first issue  color=7057ff  desc='Good for newcomers'
help wanted  color=008672  desc='Extra attention is needed'
invalid  color=e4e669  desc='Not actionable'
perf  color=5319e7  desc='Performance improvements (perf:)'
question  color=d876e3  desc='Further information is requested'
refactor  color=ffd866  desc='Refactor without behavior change (refactor:)'
test  color=c5def5  desc='Test additions / changes (test:)'
wontfix  color=ffffff  desc='This will not be worked on'
```

### Error messages

All error messages include actionable remediation. Examples:

**Unauthenticated:**
```
$ gh manage labels sync gh-manage
Error: The `gh` CLI is not authenticated or the token is invalid. Run `gh auth login` (or `gh auth refresh`) and try again.
# Exit code: 1
```

**Nonexistent repo:**
```
$ gh manage labels sync yakkuro/does-not-exist
Error: GitHub API returned 404 for repos/yakkuro/does-not-exist/labels. Check the resource name and your auth status with `gh auth status`.
# Exit code: 1
```

**Insufficient scope:**
```
$ gh manage labels sync yakkuro/gh-manage --apply
Error: Permission denied on repos/yakkuro/gh-manage/labels. Your `gh` token may lack the required scope. Run `gh auth refresh -s repo` to add `repo` scope.
# Exit code: 1
```

## Uninstalling

```bash
gh extension remove gh-manage
```

## Troubleshooting

### `uv` not found

The shell wrapper exits with:

```
error: 'uv' is required to run gh-manage but was not found on PATH.
Install via: curl -LsSf https://astral.sh/uv/install.sh | sh
Or: brew install uv
```

Install uv following the instructions above, then re-run `gh manage ...`.

### `uv` present but non-functional

```
error: 'uv' is on PATH but is not functional (uv --version failed).
```

The `uv` binary is installed but cannot run (wrong permissions, corrupted install, architecture mismatch). Reinstall via the install script in the message.

### `gh extension install` returns 404

Either the repo is private and your `gh auth status` lacks access, or the name is wrong. Confirm with:

```bash
gh repo view yakkuro/gh-manage
```

### "not yet implemented" errors

Every subcommand in v0.1.0 exits 1 with a stub message. This is expected — see the roadmap above for which phase lands each subcommand. Check the current release with `gh manage --version` against the planned version in the roadmap.

## See also

- Main design spec: [`docs/specs/2026-04-10-gh-manage-design.md`](../specs/2026-04-10-gh-manage-design.md)
- Phase 4 design spec: [`docs/specs/2026-04-10-phase-4-cli-skeleton-design.md`](../specs/2026-04-10-phase-4-cli-skeleton-design.md)
- Reusable workflow consumer guides: [`docs/usage/python.md`](./python.md), [`docs/usage/typescript.md`](./typescript.md)
- Changelog: [`CHANGELOG-cli.md`](../../CHANGELOG-cli.md)
