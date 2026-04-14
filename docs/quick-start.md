# Quick Start

Adopt gh-manage on a new or existing yakkuro-org repository in about 15 minutes. This walkthrough assumes you have `uv`, `gh`, and `git` installed, and that `gh auth status` shows you are logged in to GitHub.

If you want to understand what you are installing before running commands, read [`architecture.md`](architecture.md) first.

## Prerequisites

- Python 3.12 or later
- `uv` on your `PATH` (install with `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- `gh` CLI logged in to the `yakkuro` org
- An existing GitHub repository you can push to (we will call it `your-repo` below)

## Step 1: Install the CLI

```bash
uv tool install git+https://github.com/yakkuro/gh-manage@cli/v1.0.0
```

Verify the install:

```bash
gh-manage --version
```

Expected output: `gh-manage, version 1.0.0`.

If the install fails, see [`distribution-channels.md`](distribution-channels.md) for troubleshooting.

## Step 2: Bootstrap a Python repo

From your repo's root:

```bash
cd path/to/your-repo
gh-manage init --profile python-service .
```

The `init` subcommand will:

1. Apply the `python-service` profile's file placements (adds `.github/workflows/ci.yml` from a bundled template, adds `CLAUDE.md` if one does not already exist).
2. Apply the default label set (8 Conventional Commits labels + 6 meta labels).
3. Apply the `solo-default` branch protection policy (requires GitHub Pro for private repos — see Step 4).

On success you will see progress lines for each operation. If `init` fails partway, see the "Troubleshooting" section below.

## Step 3: Sync labels (if you did not run `init`)

If your repo already has a CI workflow and you only want labels:

```bash
gh-manage labels sync your-repo --apply
```

Without `--apply` the command is a dry run that prints the diff. `--prune` adds label deletions to the diff; without it, existing labels are left alone.

## Step 4: Apply branch protection

```bash
gh-manage protection sync your-repo --apply
```

**Private repo constraint:** GitHub requires **Pro** (`$4/month`) to enable branch protection on private repos. If you see `Upgrade to GitHub Pro to enable this feature`, upgrade your account (or make the repo public). Once Pro is active, re-run the command.

The `solo-default` policy requires 1 PR approval, enforces linear history, and blocks force pushes to `main`. See `src/gh_manage/data/branch-protection.yml` in the gh-manage repo for the exact schema.

## Step 5: Add the CI workflow

If `init` already wrote `.github/workflows/ci.yml`, skip this step. Otherwise, create the file manually:

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.0.0
    with:
      python-version: "3.12"
      gh-manage-ref: "v1.0.0"
```

Two things to note:

- The `@v1.0.0` ref appears TWICE — once on the `uses:` line and once as the `gh-manage-ref` input. They must match. This duplication is unavoidable (see [`architecture.md`](architecture.md) "Why gh-manage-ref is a required input").
- If your dev dependencies live in `[project.optional-dependencies]` (PEP 621) instead of `[dependency-groups]` (PEP 735), also add `install-command: "uv sync --extra dev"` to the `with:` block.

Commit the file and push it to a feature branch, open a PR, and watch the PR gate run.

## Step 6: Verify drift scanner reports green

```bash
gh-manage drift your-repo
```

Expected: `No drift detected. (9 checks passed across 3 check categories)` or similar. If you see HIGH or CRITICAL findings, fix them before proceeding (see the output for the actionable message per finding).

## Step 7: Enroll in the weekly drift scan

Once your repo has zero drift, open a PR against `yakkuro/gh-manage` adding your repo to `src/gh_manage/data/repos.yml`:

```yaml
# (inside src/gh_manage/data/repos.yml)
  - name: yakkuro/your-repo
    profile: python-service
```

And add a row to [`consumers.md`](consumers.md) under the appropriate adoption section. The weekly cron (`drift-scanner.yml`) will pick up your repo on the next Monday 00:00 UTC run.

## Troubleshooting

### `Branch not protected` when running `gh-manage protection sync`

For public repos this usually means the branch does not yet exist on the remote. Push at least one commit to `main`, then re-run.

For private repos this usually means you need GitHub Pro (see Step 4).

### `Permission denied` or 403 errors from `gh api`

Run `gh auth status` and confirm you are logged in as a user who has `write` access to the target repo. If you are logged in under a wrong account, `gh auth login` with the correct one.

### `gh-manage-ref` mismatch

The GitHub Actions error looks like `fatal: couldn't find remote ref refs/...`. The `gh-manage-ref` input must match the `@<ref>` on the `uses:` line exactly. Re-check both values in `.github/workflows/ci.yml`.

## Next steps

- Consumer-specific usage details: [`usage/python.md`](usage/python.md) and [`usage/typescript.md`](usage/typescript.md)
- CLI subcommand reference: [`usage/cli.md`](usage/cli.md)
- Release cadence and pinning: [`versioning.md`](versioning.md)
- Architecture and contribution guide: [`architecture.md`](architecture.md)
