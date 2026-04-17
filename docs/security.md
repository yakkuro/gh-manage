# Security Model — Reusable PR Gate Inputs

This page documents the execution mechanism and trust requirements for
the three consumer-supplied shell-command inputs on
`reusable-pr-gate-python.yml` and `reusable-pr-gate-typescript.yml`.
See `CHANGELOG-reusable.md` for release history.

## Trust model

| Input | Execution mechanism | Shell metacharacters | Required source |
|-------|---------------------|----------------------|-----------------|
| `install-command` | `${CMD}` (word splitting) | Quote/`;`/`\|`/`$()`/backtick/redirection: **not interpreted**. Pathname globbing (`*`, `?`, `[...]`): **still expands** against the working directory. | Trusted workflow-author input. Arbitrary untrusted input (PR title, comment body, etc.) is **not** safe — an attacker-controlled filename combined with a glob pattern can still select which binary runs. |
| `test-command` | `${CMD}` (word splitting) | Same as `install-command`. | Same as `install-command`. |
| `setup-command` | `eval "${CMD}"` | **All interpreted** (quotes, `\|`, `$()`, `;`, globs, etc.) | **Trusted source only.** Consumer is responsible for ensuring the value is a static literal and never comes from untrusted input. |

## What MUST NOT be forwarded to `setup-command`

The following sources are user-controlled in a typical GitHub
repository and must never flow into `setup-command`:

- `github.event.pull_request.title`
- `github.event.pull_request.body`
- `github.event.issue.title`
- `github.event.issue.body`
- `github.event.comment.body`
- `github.event.review.body`
- `inputs.*` from `workflow_dispatch` events triggered by non-maintainers
- Values fetched from external URLs, third-party APIs, or other
  repositories

Forwarding any of these to `setup-command` allows remote code execution
inside the PR-gate runner. The runner has `contents: read` on your
repo plus access to any secrets exposed to the workflow call, so the
blast radius is at minimum the workflow run's secret set.

## Safe patterns

The following patterns are safe because they use static literals
defined in the workflow file itself:

```yaml
# Safe: static literal
setup-command: "pip install -e '.[dev,bot]'"
```

```yaml
# Safe: static literal driven by a matrix value (the matrix list is
# defined in the workflow, not user-controlled).
strategy:
  matrix:
    extras: ["dev", "dev,bot", "dev,ml"]
setup-command: "pip install -e '.[${{ matrix.extras }}]'"
```

```yaml
# Safe: secret or input defined at the caller level by a maintainer.
# The value is still trusted because a maintainer authored the workflow
# file and chose what feeds in.
setup-command: "${{ secrets.MAINTAINER_DEFINED_SETUP }}"
```

## Unsafe patterns

```yaml
# UNSAFE: pull request body is attacker-controlled.
setup-command: "echo '${{ github.event.pull_request.body }}'"
```

```yaml
# UNSAFE: comment body is attacker-controlled.
setup-command: "run-${{ github.event.comment.body }}"
```

```yaml
# UNSAFE: workflow_dispatch input may be submitted by anyone with
# actions:write on the repo.
setup-command: "${{ inputs.user-provided-command }}"
```

## Version history

| Release | Behaviour |
|---------|-----------|
| v1.0.x | `install-command`, `test-command`, and `setup-command` all executed via `eval "${CMD}"`. Shell metacharacters in any of the three were interpreted, so forwarding untrusted input to any of them allowed RCE. |
| v1.1.0 (2026-04-XX) | `install-command` and `test-command` switched to `${CMD}` word splitting. `setup-command` still uses `eval` as a documented escape hatch for quote-preservation patterns (e.g., `pip install -e '.[dev,bot]'`). Pathname globbing still expands in all three inputs; hardening via `set -f` is tracked as a follow-up. |

## Reporting a security issue

Do **not** open a public issue for a suspected vulnerability in this
workflow. Instead, use GitHub's private vulnerability reporting on the
`yakkuro/gh-manage` repository (`Security` tab → `Report a
vulnerability`).
