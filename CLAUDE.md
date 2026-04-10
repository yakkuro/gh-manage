# gh-manage — Local Claude Rules

This file provides project-specific Claude Code instructions for the `gh-manage` repository. It does NOT replace the global rules in `~/.claude/CLAUDE.md` (maintained in `claude-dotfiles`); it supplements them with gh-manage-specific conventions.

## Project overview

`gh-manage` is the GitHub-based CI/CD, Issue management, and operational system for `yakkuro/*` repositories. It distributes reusable workflows, composite actions, Issue/PR templates, label definitions, and branch protection policies. See [the design spec](docs/specs/2026-04-10-gh-manage-design.md) for full architecture.

## Portability principle (load-bearing)

`gh-manage` must NOT depend on `claude-dotfiles` at runtime. The reverse direction is allowed: `claude-dotfiles` may reference `gh-manage` documentation, but `gh-manage` is self-contained and must remain installable and operable without any Claude harness.

Do not add runtime dependencies on `claude-dotfiles` scripts, rules, or skills. If you find yourself reaching into `~/repos/claude-dotfiles/`, pause and reconsider.

## Tech stack (locked in Phase 0)

- Python 3.12, managed by `uv`
- `hatchling` build backend, src layout (`src/gh_manage/`)
- `click` 8.x for CLI
- `pydantic` v2 for schema validation
- `pyyaml` for config files
- `pytest` 8 + `pytest-cov` + `pytest-mock`
- `gh` CLI (subprocess) for GitHub API interactions — no direct REST client

## Development conventions

- **TDD is mandatory.** Write the failing test first, confirm Red, write the implementation, confirm Green, then refactor. This inherits the `superpowers:test-driven-development` rules from the global claude-dotfiles harness.
- **No silent failures.** Bare `except: pass` and swallowed errors are forbidden. Every exception must be handled explicitly with user-visible context.
- **Error messages must be actionable.** Every error should describe what happened AND what the user should do next.
- **All `gh api` calls go through `src/gh_manage/github_client.py`** — this constraint takes effect when Phase 4 adds the CLI, but plan code accordingly from the start.
- **All composite action shell scripts must start with `set -euo pipefail`** — this constraint takes effect when Phase 1 adds composite actions.

## Git and PR workflow

- Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `ci:`, `build:`.
- Branch from `main` using `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, etc.
- **Direct commits to `main` are forbidden.** Always use a PR (enforced by branch protection starting in Phase 7).
- **PR review is required before merge:** the Codex + three-reviewer-agent protocol defined in `claude-dotfiles/rules/workflow-review.md` runs against every PR. That review is a Claude runtime workflow and lives in `claude-dotfiles` — do NOT port it into `gh-manage`.
- PR titles follow Conventional Commits.

## Scope boundaries (do not implement in gh-manage)

These belong elsewhere or are explicitly deferred. Do not add them without updating the design spec:

- Claude runtime workflows (subagents, skills, hooks, rules/workflow-review.md)
- Cross-repo dashboard UI (domain F, deferred)
- Release management for other repos (domain G, deferred)
- Dependency management / Dependabot distribution (domain H, deferred)
- GitHub Enterprise support (out of scope — yakkuro org only)
- PyPI publishing (deferred until post v1.0)
- `act` / nektos local Actions execution

See the design spec's `## Non-Goals` section for the authoritative list.

## Reference documents

- Design spec: `docs/specs/2026-04-10-gh-manage-design.md`
- Phase 0 plan: `docs/plans/2026-04-10-phase-0-foundation.md`
- Global rules: `~/.claude/CLAUDE.md` (from `claude-dotfiles`)
