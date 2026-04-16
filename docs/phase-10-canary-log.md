# Phase 10 Canary Log

## Canary repos
1. yakkuro/shorts-factory (Tier 1, Rank 1, Score 4.0) — PR yakkuro/shorts-factory#2, merged 2026-04-16T01:46:40Z (018b0fe)
2. yakkuro/polyagent (Tier 1, Rank 2, Score 4.0) — PR yakkuro/polyagent#5, merged 2026-04-16T01:55:05Z (fdb394b)

## Recipe execution log

### Canary #1: shorts-factory
- Cloned, branched, created `.github/workflows/ci.yml`
- Inputs: `python-version: "3.12"`, `gh-manage-ref: v1.0.0`, `type-check: false`
- ruff check/format: already clean (no changes)
- CI result: **all green**
- Merge: squash-merge to main

### Canary #2: polyagent
- Cloned, branched, created `.github/workflows/ci.yml`
- Inputs: `python-version: "3.12"`, `gh-manage-ref: v1.0.0`, `type-check: false`, `install-command: "uv sync --all-extras"`, `test-command` with `--ignore` for 3 DB-dependent test files
- ruff check/format: already clean (no changes)
- CI result: **all green** (CI, PR Gate, Integration Gate, AI Review)
- Merge: squash-merge to main

## Edge cases encountered

1. **mypy fails on untyped third-party libs** (canary #1)
   - Repos using moviepy, yaml, google-* libs have no type stubs
   - **Resolution**: `type-check: false` as default for all adoption PRs

2. **PostgreSQL service dependency** (canary #2)
   - polyagent's conftest.py defines a `db_pool` fixture requiring PostgreSQL (via asyncpg)
   - Only `test_memory.py` uses the real DB fixture; `test_integration.py` and `test_lifecycle.py` use `MockMemoryStore`
   - Reusable workflow cannot declare `services:` block (workflow_call limitation)
   - **Resolution**: `test-command` with `--ignore=tests/test_memory.py`; existing pr-gate.yml covers full suite
   - **Note**: Adoption PR conservatively ignored all 3 files; a follow-up can narrow to `test_memory.py` only

3. **Optional dev dependencies** (canary #2)
   - polyagent uses `[project.optional-dependencies]` for dev tools
   - Default `uv sync` doesn't install pytest/ruff
   - **Resolution**: `install-command: "uv sync --all-extras"`

## Recipe refinements for batch phase

- Default all adoption PRs with `type-check: false`
- Check for `[project.optional-dependencies]` → use `install-command: "uv sync --extra dev"` if dev extras exist (prefer targeted extras over `--all-extras` to avoid pulling unnecessary dependencies)
- Check for service dependencies (PostgreSQL, Redis, etc.) → customize `test-command` with `--ignore` for dependent tests
- Tier 1 repos (batch 1) are expected to be simpler (no services), but verify during batch

## Deferred repos
(populated during batch phase — repos that failed adoption and were skipped/demoted)

## Status check context name
`PR Gate / PR Gate` (confirmed from shorts-factory canary CI run)
