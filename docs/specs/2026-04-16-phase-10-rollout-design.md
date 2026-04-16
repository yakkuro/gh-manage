---
date: 2026-04-16
size: Large
target: yakkuro/gh-manage
goal: Complete Phase 10 by rolling out `reusable-pr-gate-python.yml@v1.0.0` to 20+ active Python repos in the yakkuro org, then observe 2 consecutive weeks of zero HIGH/CRITICAL drift findings to close the v1.0 release cycle.
phase: 10
tracks: [ops, rollout]
---

# Phase 10 — Rollout design

## Sizing rationale

**Large** — the rollout touches 20+ external repos (one PR each), plus two gh-manage docs artifacts (`phase-10-tier-list.md`, `phase-10-canary-log.md`), plus `repos.yml` updates, plus branch protection application, plus a 2-week observation phase. Although no new gh-manage module is introduced, the cross-repo nature and multi-phase execution model (pre-scan → canary → batch → observation) warrants the larger spec template. Per `spec-driven.md`, when uncertain, size up.

## Goal

Complete the two acceptance criteria of the top-level design spec's **Phase 10 (Rollout)** section (`docs/specs/2026-04-10-gh-manage-design.md` line 906-909):

1. yakkuro org の active 20 リポ以上で gh-manage の reusable workflow が稼働
2. drift scanner が weekly 実行され、critical finding ゼロ状態が 2 週連続

Phase 10 is the final AC of the v1.0 release cycle. Completing it closes Issue #27 and marks gh-manage as a stable, battle-tested platform for yakkuro-org-wide CI/CD.

## Background

**Current state (2026-04-16)**:
- Releases: `v1.0.0` (reusable workflows, stable), `cli/v1.0.1` (Python CLI)
- `src/gh_manage/data/repos.yml` contains 9 repos, all using **drift scanner only**. None currently invoke `reusable-pr-gate-python.yml@v1.0.0`.
- Drift scanner: weekly cron (`0 0 * * 1` JST), zero HIGH/CRITICAL findings since 2026-04-13 across the current 9.
- Active non-archived yakkuro Python repos: ~31 candidates.
- Active TypeScript repos: ~10 candidates (explicitly deferred to Phase 11).
- Known defect: `nade-nade` is listed as `python-service` in `repos.yml` but is actually a TypeScript project. This mislabel has been dormant because drift scanner has not flagged it as HIGH/CRITICAL yet.

**What Phase 10 changes**:
- Brings 20+ new Python repos under gh-manage's full PR gate (ruff 0.8.0 + mypy 1.12 + pytest)
- Applies branch protection (required status check: canary-confirmed context, tentatively `"PR Gate / PR Gate"`) to all adopted repos
- Expands `repos.yml` from 9 → 20+ entries so drift scanner covers the full adoption set
- Corrects the `nade-nade` profile mislabel
- Fixes two pre-existing gh-manage defects surfaced during spec writing: bundled `python-ci.yml` template missing `gh-manage-ref`, and `python-service` profile has empty `required_contexts`

**What Phase 10 does NOT change**:
- No new CLI features (e.g., `gh manage ci add`) — this would violate v1.0 stability promise
- No reusable workflow spec changes — `reusable-pr-gate-python.yml@v1.0.0` is frozen
- No TypeScript rollout — deferred to Phase 11
- No gh-manage self-dogfood profile fix — Issue #20 territory, out of scope

## Scope

### In scope

1. **Pre-scan subagent**: classify ~31 Python candidates into Tier 1 / Tier 2 / Tier 3, produce `docs/phase-10-tier-list.md`
2. **`repos.yml` nade-nade fix**: change `python-service` → `ts-service` as Phase 10 setup commit (before canary)
3. **Bundled template bug fix** (`src/gh_manage/data/templates/ci/python-ci.yml`): add missing `gh-manage-ref` input, pin to `@v1.0.0` (bundled with Phase 10 setup PR)
4. **python-service profile `required_contexts` update**: canary determines the exact status check context string, then separate PR updates the profile (bundled into `cli/v1.0.2` at Phase 10 completion)
5. **Canary phase**: main-session manual adoption of 1-2 cleanest Tier 1 repos, producing `docs/phase-10-canary-log.md`
6. **Batch phase**: subagent-driven adoption of remaining Tier 1 repos in batches of 4-5, with main-session coordination
7. **Branch protection apply**: `gh manage protection apply` per repo after adoption PR merges (meaningful only after step 4 lands)
8. **`repos.yml` expansion**: per-batch PR on gh-manage adding newly adopted repos
9. **Observation phase**: wait for drift scanner weekly cron to observe 2 consecutive zero-critical weeks across the full expanded repo set
10. **Progress tracking**: Issue #27 comments per batch, `docs/consumers.md` update at completion

### Out of scope

- TypeScript repo rollout (Phase 11)
- `gh manage ci add` or other new CLI features
- Reusable workflow feature changes (v1.0 stability promise)
- `yakkuro/gh-manage` self-dogfood profile fix (Issue #20)
- Cross-repo dashboard UI (design spec domain F, deferred)
- Release management for other repos (domain G, deferred)
- Dependabot distribution (domain H, deferred)
- PyPI publishing

## Key decisions (brainstorming record)

| # | Question | Decision | Rationale |
|---|---|---|---|
| Q1 | Scope | **Python-only**, TS → Phase 11 | Protect v1.0 stability; TS workflow has no dogfood experience yet |
| Q2 | Rollout strategy | **Canary (1-2) → batched (4-5/batch)** | Canary absorbs edge cases; batch accelerates via subagents |
| Q3 | Repo selection criteria | **PR gate ready filter**: `pyproject.toml` + `tests/test_*.py` + Python 3.12 compat | Pre-screen ensures high batch success rate |
| Q4 | Consumer-side prep | **Auto-fix only**: include repos where `ruff --fix` suffices; manual `mypy` judgment per-repo | Balances effort vs completion |
| Q5 | `repos.yml` sync | **Sync** — new repos added to `repos.yml` as batches complete; included in drift scanner | Single source of truth; matches AC② phrasing |
| Q6 | Completion criteria | **C-1**: 20+ adopted + all repos 2 consecutive weeks zero HIGH/CRITICAL; findings reset counter to detection/fix cycle | Realistic observation protocol |
| Q7a | Branch protection apply | **Yes** — `gh manage protection apply` runs after adoption merge | Fully completes "CI enforcement" for adopted repos |
| Q7b | nade-nade mislabel fix | **Yes** — corrected as Phase 10 setup commit | Trivial fix, logically belongs here |

## Execution model

### Phase overview

```
Pre-scan (1 subagent)
    ↓
Phase 10 setup PR (main session, 4-reviewer):
  - Fix nade-nade profile in repos.yml
  - Fix bundled template bug (add gh-manage-ref, pin @v1.0.0)
  - Commit phase-10-tier-list.md
  - Commit phase-10-canary-log.md skeleton
    ↓
Canary (main session, 1-2 repos, 4-reviewer protocol)
  - Adopt top 2 cleanest Tier 1 repos manually
  - Record edge cases + exact status check context name in canary log
    ↓
Post-canary fix-up (main session):
  - Update python-service profile required_contexts with canary-confirmed string (separate PR, 4-reviewer)
  - Add canary repos to repos.yml (separate PR, Codex-only review)
  - Run gh manage protection apply for canary repos; verify via gh api
  - Trigger manual drift scan; confirm zero findings for canary repos
    ↓
Batch loop (subagent-driven, 4-5 repos/batch):
  For each batch:
    - Main session selects next batch from Tier 1 residual
    - Spawn subagent team (1 agent = 1 repo)
    - Each subagent runs adoption recipe autonomously
    - Main session verifies (trust-but-verify) all PRs merged green
    - Main session opens ONE gh-manage PR adding batch to repos.yml, merges (Codex-only review)
    - Main session runs gh manage protection apply per repo
    - Main session posts batch progress to Issue #27
    ↓
Observation (passive, 2 weeks minimum):
  - Weekly drift scanner cron observes full expanded repo set
  - Zero HIGH/CRITICAL required for 2 consecutive weeks
  - Findings trigger fix + counter reset (Q6 C-1)
    ↓
Completion:
  - All AC items satisfied (see Acceptance criteria section)
  - Issue #27 closed
  - CHANGELOG-reusable.md + CHANGELOG-cli.md updated
  - docs/consumers.md updated
  - cli/v1.0.2 tagged
  - Memory updated
```

### Phase 10 setup commits (gh-manage side, before canary)

Before any canary adoption starts, land the following preparation commits on `yakkuro/gh-manage` via a single PR (title: `chore: Phase 10 setup — nade-nade profile + template bug fix`):

1. **`repos.yml` nade-nade fix**: change `nade-nade` entry profile from `python-service` to `ts-service` (it is actually TypeScript)

2. **Bundled template bug fix** (`src/gh_manage/data/templates/ci/python-ci.yml`):
   - Current (broken): `uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@main` with no `gh-manage-ref` → fails validation because `gh-manage-ref` is REQUIRED
   - Fixed: add `gh-manage-ref: v1.0.0`, pin `uses: ...@v1.0.0`, add `workflow_dispatch` trigger, add `permissions: contents: read` — aligns with the spec's Interface Contract template above
   - This fix is technically a `cli/v1.0.2` patch but is bundled into Phase 10 setup since `gh manage init/apply` would otherwise be unusable for future Python consumers
3. **Tier list artifact**: commit `docs/phase-10-tier-list.md` (output from pre-scan, see next subsection)
4. **Canary log skeleton**: commit `docs/phase-10-canary-log.md` with template headers (populated during canary)

**Deferred to post-canary** (because context name must be empirically confirmed):

5. **python-service profile update** (`src/gh_manage/data/profiles/python-service.yml`): change `required_contexts: []` to `required_contexts: ["PR Gate / PR Gate"]` (or whatever exact string canary reveals). This commits as a separate PR titled `fix: python-service profile required_contexts for pr-gate enforcement` after canary determines the exact context name. Until this lands, `gh manage protection apply --repo <name>` for python-service is a no-op for status check enforcement.

**Review**: the Phase 10 setup PR (items 1-4) gets full 4-reviewer protocol. The post-canary profile update PR (item 5) gets full 4-reviewer as it changes enforcement semantics for ALL python-service repos.

**cli version bump**: since item 2 and item 5 modify bundled data files (`src/gh_manage/data/`), they warrant a `cli/v1.0.2` bump at Phase 10 completion (or earlier if published). This is separate from Phase 10 ACs but is a natural side effect — note in release checklist.

### Pre-scan details

**Execution**: main session spawns a single read-only subagent.

**Input**: `gh repo list yakkuro --no-archived --limit 50 --json name,primaryLanguage,updatedAt,isPrivate`

**Steps per candidate repo** (Python repos only):
1. `gh repo clone yakkuro/<name> /tmp/phase-10-scan/<name> --depth=1`
2. Check `pyproject.toml` exists; read Python version constraint
3. `Glob("tests/test_*.py")` — must have ≥1 match
4. `uvx ruff@0.8.0 check --output-format=json .` — record total violations, auto-fixable count
5. `uvx ruff@0.8.0 format --check .` — record diff presence
6. If `pyproject.toml` declares a `[tool.mypy]` section: `uvx --with mypy@1.12 mypy <src>` — record error count
7. Classify per rules below

**Reusable workflow prerequisites** (derived from `.github/workflows/reusable-pr-gate-python.yml`):

The reusable workflow hardcodes several assumptions the consumer must satisfy to run with default inputs:
- `install-command` default is `uv sync` → consumer MUST commit `uv.lock`
- `test-command` default is `uv run pytest` → consumer MUST have pytest as a dev dep resolvable via `uv sync`
- `mypy` action runs on `src/` → consumer MUST use src layout (or disable type-check via `type-check: false`)
- `ruff` action uses a fixed internal pin (ruff 0.8.0) → consumer's code must pass `ruff check` and `ruff format --check` as-is (after optional auto-fix)
- `python-version` is a REQUIRED input — the consumer's ci.yml MUST pass it explicitly

**Classification rules** (revised to match these prerequisites):

| Tier | Conditions |
|---|---|
| Tier 1 (ready, default inputs) | `pyproject.toml` ✅ + `[project]` section with python-requires compatible with 3.12 (or unspecified — see note below) ✅ + `uv.lock` committed ✅ + `src/` directory exists ✅ + `tests/test_*.py` ≥1 ✅ + `uvx ruff@0.8.0 check` clean OR `--fix` resolves all violations ✅ + `uvx ruff@0.8.0 format --check` clean OR format application safe ✅ + `uvx --with mypy@1.12 mypy src` passes OR `[tool.mypy]` explicitly disables checking ✅ |
| Tier 1.5 (ready, custom inputs) | Same as Tier 1 but requires **EXACTLY ONE** of these whitelisted overrides ONLY: `type-check: false` (flat-layout repos without `src/`), OR `working-directory: <subdir>` (monorepos with Python project in a subdir). Any repo requiring `install-command` override MUST be Tier 2 — no exceptions. |
| Tier 2 (manual fix needed) | Has pyproject + tests + src layout, but: ruff/mypy require non-auto-fixable code changes, OR missing `uv.lock`, OR requires `install-command` override, OR requires >1 of the whitelisted input overrides |
| Tier 3 (not ready) | Missing `pyproject.toml` OR missing `[project]` section OR no `tests/test_*.py` OR Python explicitly <3.12 OR neither `src/` nor viable flat layout |
| Excluded | TypeScript/Go/Shell/Makefile/none, archived, or upstream fork |

**Python version fallback rule** (ambiguity resolution when `pyproject.toml` lacks `python-requires`):
- If `pyproject.toml` missing `[project]` section → Tier 3 (not ready, needs structural fix)
- If `[project]` present but no `python-requires` field → check `.github/workflows/**` and `tox.ini` for declared Python version; if 3.12 or unspecified, assume compatible (Tier 1 eligible); if <3.12, Tier 3
- If still ambiguous after both checks → Tier 2 (manual review needed)

**Priority for Phase 10 selection**:
1. Tier 1 first (identical CI yaml across all, highest automation potential)
2. Tier 1.5 second (mechanical but per-repo override needed)
3. Tier 2 only as salvage if Tier 1 + 1.5 total < 20

**Pre-scan output**: `docs/phase-10-tier-list.md`

```markdown
# Phase 10 Tier List — 2026-04-16

## Summary
- Tier 1: N repos (target ≥20)
- Tier 2: M repos
- Tier 3 / Excluded: K repos

## Tier 1 — ready for adoption (ordered by cleanliness score)
| Rank | Repo | pyproject | tests | Ruff | Format | Mypy | Notes |
|---|---|---|---|---|---|---|---|
| 1 | researcher | ✅ | 12 | clean | clean | skip | canary candidate |
| 2 | git-digest | ✅ | 4 | clean | clean | clean | canary candidate |
| 3 | polyagent | ✅ | 8 | 3 auto-fix | needs format | clean | auto-fix OK |
| ... | ... | ... | ... | ... | ... | ... | ... |

## Tier 2 — needs manual fix (fallback pool)
| Repo | Issue | Estimated work |
|---|---|---|

## Tier 3 — excluded
| Repo | Reason |
|---|---|

## repos.yml profile corrections
- nade-nade: `python-service` → `ts-service` (actually TypeScript)
```

**Cleanliness score** (for ranking within Tier 1; "clean" means PASSES without any `--fix` application):

`score = (ruff_check_passes_without_fix ? 2 : 0) + (ruff_format_check_passes ? 1 : 0) + (mypy_scoring_pass ? 1 : 0) + min(test_file_count, 10) / 10`

**`mypy_scoring_pass` definition** (explicit):
- `mypy src` returns 0 errors → pass (1 point)
- `mypy src` returns >0 errors → fail (0 points)
- `[tool.mypy]` in pyproject.toml explicitly disables checking (e.g., `ignore_errors = true`, or mypy commented out entirely) → pass (1 point, repo explicitly opted out)
- No `[tool.mypy]` section AND mypy produces errors → fail (0 points)

A Tier 1 repo that is fully clean (no `--fix` needed) scores at least 3.0. A Tier 1 repo that only needs `--fix` scores around 1.0-1.5 (it still qualifies for Tier 1 because `--fix` resolves it, but ranks lower). Higher score = better canary / early batch candidate.

### Canary phase

**Canary selection**: top 2 entries from Tier 1 by cleanliness score.

**Execution**: main session runs the adoption recipe **manually** (no subagents), recording every step.

**Adoption recipe**:
1. `gh repo clone yakkuro/<repo> /tmp/phase-10-adopt/<repo>` → `git checkout -b feat/adopt-gh-manage-pr-gate`
2. Create `.github/workflows/ci.yml` with the exact template below
3. If needed: `uvx ruff@0.8.0 check --fix .` and/or `uvx ruff@0.8.0 format .`
4. `uv run pytest` local smoke check (if possible in the repo's environment)
5. Commit structure:
   - commit 1: `ci: adopt gh-manage reusable PR gate (v1.0.0)` — ci.yml only
   - commit 2 (conditional): `style: apply ruff --fix (auto)` — only if ruff-fix produced diff
   - commit 3 (conditional): `style: apply ruff format (auto)` — only if format produced diff
6. `gh pr create --base main --title "ci: adopt gh-manage reusable PR gate (v1.0.0)"`
7. `gh pr checks <N> --watch` until CI green
8. `gh pr merge <N> --squash --delete-branch` (squash rationale: all adoption PRs are mechanical single logical changes; squashing keeps consumer `main` history clean. Individual commits are preserved in the PR conversation, so no traceability loss.)

**CI yaml template** (Tier 1 Interface Contract; aligned with gh-manage's internal `src/gh_manage/data/templates/ci/python-ci.yml` once the template bug fix lands):

```yaml
name: CI

on:
  pull_request:
    branches:
      - main
  push:
    branches:
      - main
  workflow_dispatch:

permissions:
  contents: read

jobs:
  pr-gate:
    name: PR Gate
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.0.0
    with:
      python-version: "3.12"
      gh-manage-ref: v1.0.0
```

**Expected status check context** (tentative, empirically confirmed during canary): `PR Gate / PR Gate`. This is the composition of caller-job display name (`jobs.pr-gate.name: PR Gate`) and callee-job display name (from reusable workflow `jobs.test.name: PR Gate`). The canary phase MUST confirm this exact string via `gh api repos/<canary>/actions/runs/<N>/jobs --jq '.jobs[].name'` before the python-service profile's `required_contexts` is updated.

**Tier 1.5 overrides** (append to `with:` block when one customization is needed):

```yaml
      type-check: false        # flat-layout repos without src/
      working-directory: pkg   # monorepos with Python project in a subdir
      install-command: "pip install -e ."  # repos without uv.lock — AVOID, prefer Tier 2 salvage
```

Tier 1 requires ZERO overrides — the ci.yml is byte-identical across all Tier 1 consumers.

**Version pinning strategy** (important for in-flight Phase 10):
- All Phase 10 adoption PRs (canary + batch) hardcode `@v1.0.0` and `gh-manage-ref: v1.0.0`
- If `cli/v1.0.2` (template + profile fix bundle) is released DURING Phase 10 execution, the release is on the CLI track (`cli/` tag prefix), NOT the reusable workflow track (`v1.x.x`). The reusable workflow itself remains at `v1.0.0`. Therefore adoption PRs should stay pinned to `@v1.0.0` regardless of CLI release timing
- If a `v1.0.1` reusable workflow release is ever needed mid-Phase 10 (emergency patch), STOP the batch phase, update the adoption recipe to reference whatever tag is current, re-run canary on 1 repo, then resume. Halt-and-adjust is mandatory — do NOT continue with a stale recipe
- Rationale: adopted repos pin to the reviewed and validated reusable workflow version. Post-Phase 10, repo owners can bump as needed.

**Why manually author instead of `gh manage apply`**:
1. `gh manage apply` uses the bundled template which has a **pre-existing bug** (missing `gh-manage-ref`, uses `@main` instead of `@v1.0.0`) — this bug is fixed as part of Phase 10 setup (see below), but for Phase 10 adoption we author the ci.yml directly to avoid coupling
2. `gh manage apply` also installs `CLAUDE.md` from the python-service profile. Many consumer repos may not have CLAUDE.md, and Phase 10 should NOT be adding one unilaterally (scope creep)
3. Manual authoring gives the subagent deterministic control over exactly what ends up in the PR diff (important for the review-skip audit trail)

**Canary review protocol**: Full 4-reviewer protocol per `workflow-review.md`:
- Codex (`codex-review-resilient.sh`)
- `superpowers:code-reviewer`
- `silent-failure-hunter`
- `code-reviewer` (custom, model selection per diff size)

**Canary output**: `docs/phase-10-canary-log.md`

```markdown
# Phase 10 Canary Log — <date>

## Canary repos
1. yakkuro/<repo-1> — PR #<N>
2. yakkuro/<repo-2> — PR #<N>

## Recipe execution log
### yakkuro/<repo-1>
- Clone: <observation>
- pyproject: <observation>
- ruff --fix: <# fixes applied> / <# remaining>
- pytest: <result>
- Commits: <sha> <sha> <sha>
- PR: <url>
- CI runs: <results>
- Merge: <sha on main>

## Edge cases encountered
- <issue> — <resolution> — <how to avoid in batch>
- ...

## Recipe refinements for batch phase
- <addition> — <reason>
- ...
```

**Canary success criteria**:
- Both canary PRs merged green
- Exact status check context name recorded in `docs/phase-10-canary-log.md` (via `gh run view <run-id> --json jobs --jq '.jobs[] | .name'`)
- After python-service profile update (see below): `gh api repos/yakkuro/<name>/branches/main/protection --jq '.required_status_checks.contexts'` returns the expected context
- Next drift scanner run (manual trigger or weekly cron) shows zero HIGH/CRITICAL for canary repos

**Post-canary sequence** (main session):
1. **Determine exact context name**: inspect canary CI run job names, confirm the tentative `"PR Gate / PR Gate"` guess (or record actual string)
2. **Update python-service profile**: open gh-manage PR updating `required_contexts: ["<confirmed context>"]`, 4-reviewer protocol, merge
3. **Update `repos.yml`**: separate gh-manage PR adding canary repos, merge
4. **Apply protection**: `gh manage protection apply --repo yakkuro/<name>` for each canary — verify via `gh api` that the required context is now set
5. **Trigger drift scanner manually** (or wait for next weekly cron): confirm zero findings for canary repos

Only after all 5 post-canary steps succeed does the batch phase begin.

**Sequential gate (non-parallelizable, non-negotiable)**:

Batch phase MUST NOT start until ALL of the following are complete and merged to `main` on `yakkuro/gh-manage`:

1. Phase 10 setup PR merged (nade-nade fix + template bug fix + tier-list + canary-log skeleton)
2. Canary adoption PRs merged on consumer repos + exact status check context name recorded in canary log
3. **python-service profile update PR merged** (`required_contexts: ["<confirmed context>"]`)
4. Canary `repos.yml` PR merged (canary repos listed)
5. Canary `gh manage protection apply` runs verified via `gh api` — required contexts confirmed set
6. Canary drift scan confirmed zero HIGH/CRITICAL

**Why this ordering is non-negotiable**: if batch `repos.yml` PRs merge before step 3 (profile update), the `gh manage protection apply` step for batch repos will set `required_contexts: []` (profile is still empty). The protection WILL be applied but WILL NOT enforce any status check, producing silent no-op state. The error is not visible until a PR merges without CI. To prevent this, main session MUST verify step 3 is merged before spawning batch subagents.

**Enforcement**: before spawning any batch subagent team, main session runs:
```bash
gh api repos/yakkuro/gh-manage/contents/src/gh_manage/data/profiles/python-service.yml --jq '.content' | base64 -d | grep -q 'required_contexts: \["'
```
If grep returns false, batch phase is BLOCKED. Main session re-runs post-canary step 1 (profile update).

### Batch phase

**Batch coordination** (main session):
1. Select next 4-5 repos from Tier 1 residual (in cleanliness score order)
2. Spawn a subagent team where each subagent is assigned one repo
3. Pass each subagent the complete adoption recipe + canary log edge cases + ci.yml template
4. Wait for all subagents to report completion (or failure)
5. Trust-but-verify: main session independently verifies each claimed merge via `gh pr view`
6. Open one gh-manage PR adding the batch's repos to `repos.yml`, merge
7. Run `gh manage protection apply --repo <name>` for each repo in the batch
8. Post batch progress comment on Issue #27
9. Loop to next batch

**Subagent contract** (per `multi-agent.md`):

- **Model**: `sonnet` (default). Haiku is insufficient for the judgment calls around lint diffs and test failures; Opus is overkill for mechanical adoption.
- **File Ownership**: `/tmp/phase-10-adopt/<assigned-repo>/**` ONLY. Subagent MUST NOT edit gh-manage repo, other consumer repos, or any shared state.
- **Interface Contract**:
  1. The ci.yml template (exact, verbatim)
  2. The full adoption recipe (steps 1-8)
  3. The canary log edge case appendix
  4. Explicit list of `gh` CLI commands allowed (`clone`, `pr create`, `pr checks --watch`, `pr merge --squash --delete-branch`, `pr view`)
- **Acceptance Criteria**:
  - `gh pr view <N> --json mergedAt --jq .mergedAt` returns non-null timestamp
  - `gh pr checks <N> --json conclusion --jq '[.[] | .conclusion] | all(. == "SUCCESS")'` returns true
  - Subagent returns **raw command output** (not "DONE") so main session can independently verify
- **Failure modes**:
  - If CI fails, subagent attempts at most ONE fix (e.g., rerun `ruff --fix` or `ruff format`)
  - If still failing after one fix attempt, subagent returns `NEEDS_CONTEXT` with the raw error output and stops
  - Main session decides: fix manually, demote to Tier 2, or skip

- **Cleanup contract (mandatory)**: when main session decides to SKIP or DEMOTE after a subagent `NEEDS_CONTEXT`:
  1. Main session MUST close the unmerged PR on the consumer repo: `gh pr close <N> --comment "Deferred from Phase 10 batch — will retry in future phase"`
  2. Main session MUST delete the consumer-side branch: `gh api -X DELETE repos/yakkuro/<repo>/git/refs/heads/feat/adopt-gh-manage-pr-gate` (or `git push origin --delete feat/adopt-gh-manage-pr-gate` from a local clone)
  3. Main session MUST remove the local clone: `rm -rf /tmp/phase-10-adopt/<repo>`
  4. The skipped repo is logged in `docs/phase-10-canary-log.md` under a new "Deferred repos" section with the reason and the Tier demotion (if any)
  5. The same repo MUST NOT be re-spawned to a subagent within the same Phase 10 without explicit user re-authorization (documented via Issue #27 comment)
  6. Rationale: prevents orphaned branches, duplicate PRs, or repeated failed attempts from inflating noise in consumer repos

**Review protocol at scale**:
- **Canary PRs** (1-2 total): FULL 4-reviewer protocol
- **Batch adoption PRs** (machine-generated, template-identical): **review SKIP authorized** per this spec, under these conditions:
  - Diff contains only: `.github/workflows/ci.yml` addition + (optional) `ruff --fix` auto-generated diff + (optional) `ruff format` auto-generated diff
  - No changes to source logic, tests, pyproject.toml, or any other file
  - CI green before merge
  - Audit trail: adoption PR URL + canary log reference recorded in Issue #27 batch comment
  - Main session final verification via `gh pr view` confirms diff structure before merge
- **gh-manage `repos.yml` batch PRs** (1 per batch, 1 file / N lines): Codex review only (1 reviewer of 4). Scope is 1 line per repo, 4-reviewer is overkill.

### repos.yml sync strategy

Per-batch synchronization (NOT pre-loaded):

- Repos are added to `repos.yml` ONLY AFTER their consumer-side adoption PR is merged
- This prevents drift scanner from observing repos that don't yet have the workflow installed (which would trigger false HIGH findings during rollout)
- Each batch produces ONE gh-manage repo PR with N lines added
- Canary batch: 1 PR with 2 lines added (or 1 line if single canary)
- Batch N: 1 PR with 4-5 lines added
- Total: ~5-6 gh-manage repos.yml PRs during Phase 10

### Branch protection apply

Executed post-merge, per repo, after `repos.yml` entry exists:

```bash
gh manage protection apply --repo yakkuro/<name>
```

This command reads `repos.yml` to determine the profile and applies the corresponding protection rules. For the `python-service` profile, the rule set (after Phase 10 post-canary profile update) requires the canary-confirmed context (tentatively `"PR Gate / PR Gate"`) as a status check. Protection apply is a no-op for status check enforcement until the profile update lands.

**Sequence**: consumer adoption PR merged → `repos.yml` PR merged → `gh manage protection apply` → done.

**Failure handling**: if `gh manage protection apply` fails due to pre-existing broken protection state on the consumer repo, file an Issue on gh-manage (out of scope for Phase 10 fix), count the CI adoption as successful, but mark the repo as "protection deferred" in the Issue #27 batch comment.

## Failure modes & mitigations

| Failure case | Mitigation |
|---|---|
| Pre-scan: Tier 1 < 20 | Fall back to Tier 2 salvage (repos where manual fix ≤30 min). If still <20, escalate to user via Issue #27 for AC renegotiation. |
| Canary: CI fails on first attempt | Main session debugs manually, records fix in canary log, considers if it applies to other repos. |
| Canary: edge case not in recipe | Update adoption recipe in-spec, amend canary log, potentially re-run canary if fundamental. |
| Batch subagent: 1 fix attempt fails | Return `NEEDS_CONTEXT` with raw output; main session demotes repo to Tier 2, pulls next Tier 1 repo. |
| Batch subagent: merges PR against wrong base | Impossible by contract (`--base main` hardcoded in recipe); main session still verifies via `gh pr view --json baseRefName`. |
| `gh manage protection apply` fails | File Issue, count CI adoption as success, mark "protection deferred" for post-Phase 10 cleanup. |
| Canary reveals status check context name ≠ tentative `PR Gate / PR Gate` | Update the python-service profile PR with the actual string before merging. No rollback needed. |
| Template bug fix breaks existing `gh manage apply` consumers | Low risk: no known existing consumers use `gh manage apply` for CI installation (the 9 bundled consumers use drift scanner only, not full apply). Verify by searching consumer repos for `gh-manage/...@main` references before merging fix. |
| `ruff --fix` breaks tests | Indicates the repo's code depends on behavior that ruff "fix" changed. Demote to Tier 2 (manual intervention needed), do NOT force through. |
| Observation: HIGH/CRITICAL finding appears | Analyze cause (config regression, profile mismatch, etc.), fix, reset 2-week counter from fix date. |
| Observation: ≥3 counter resets | Escalate to user — Phase 10 definition may need revision. |
| Candidate selection process excludes a repo the user cares about | User can override by explicit Issue #27 comment; subagent team adds that repo to current batch. |

## Acceptance criteria

Phase 10 is complete when ALL of the following are true:

- [ ] `src/gh_manage/data/repos.yml` contains ≥20 Python service entries (excluding nade-nade which is now `ts-service`)
- [ ] Each adopted repo's latest CI run on `main` is green (verified via `gh run list --repo <name> --branch main --limit 1`)
- [ ] `src/gh_manage/data/profiles/python-service.yml` has `required_contexts: ["<canary-confirmed context>"]` (no longer empty)
- [ ] Each adopted repo has the canary-confirmed status check as a required context in branch protection (verified via `gh api repos/<name>/branches/main/protection --jq '.required_status_checks.contexts'`)
- [ ] `src/gh_manage/data/templates/ci/python-ci.yml` has the template bug fixed (`gh-manage-ref` included, pinned to `@v1.0.0`)
- [ ] Drift scanner weekly cron has observed zero HIGH/CRITICAL findings across all entries in `repos.yml` for **2 consecutive cron executions** (reset counter applies per Q6 C-1; see Observation phase details below for strict definition)
- [ ] `docs/phase-10-tier-list.md` committed
- [ ] `docs/phase-10-canary-log.md` committed with recipe execution log + exact context name recorded
- [ ] Issue #27 closed
- [ ] `CHANGELOG-reusable.md` has a "Phase 10 rollout completed" entry
- [ ] `CHANGELOG-cli.md` has a `cli/v1.0.2` entry covering the template and profile fixes
- [ ] `docs/consumers.md` updated with Phase 10 adoption record (same format as Phase C)

## Testing strategy

**Pre-scan verification** (before spending time on canary):
- Main session spot-checks 2-3 tier-1 repos: independently clone, run `ruff@0.8.0 check/format` and mypy, confirm classification matches subagent output
- Confirm Tier 1 total ≥20; if not, trigger Tier 2 salvage flow immediately

**Canary verification**:
- For each canary PR: confirm all 8 recipe steps succeed
- `gh pr view <N> --json state,mergedAt,mergeCommit` returns `MERGED` with non-null mergedAt
- Exact status check context name extracted from `gh run view <run-id> --json jobs --jq '.jobs[] | .name'` and recorded in canary log
- After python-service profile update merges: `gh api repos/yakkuro/<name>/branches/main/protection --jq '.required_status_checks.contexts'` returns the canary-confirmed context
- Manual drift scan via `gh manage drift --repo yakkuro/<name>` returns zero findings

**Batch verification** (per subagent completion):
- Trust-but-verify: main session independently runs `gh pr view <N>` and `gh pr checks <N>` for each reported PR
- After `repos.yml` update PR merges: `gh manage apply --repo yakkuro/<name> --dry-run` returns "no changes needed" for each repo (confirms repos.yml entry matches reality)
- Batch-wide sanity check: `gh manage drift --all` reports zero HIGH/CRITICAL immediately after batch completion

**End-to-end verification** (before declaring Phase 10 complete):
- `gh manage drift --all` reports zero HIGH/CRITICAL on newly adopted repos specifically (pre-existing original-9 repos are not affected by Phase 10 and their drift status is unchanged)
- Gap analysis: `gh repo list yakkuro --no-archived --language python --json name` vs `repos.yml` — log the non-adopted Python repos with reasons (mostly Tier 3 exclusions)
- `docs/consumers.md` Phase 10 section includes a per-repo status table

### Observation phase details (strict definitions)

- **Drift scanner cron schedule**: `0 0 * * 1` UTC = Monday 09:00 JST
- **"2 consecutive zero-critical weeks" definition**: 2 consecutive drift scanner cron executions (weekly), both returning zero HIGH/CRITICAL findings across the full expanded `repos.yml`
- **Counter reset rules** (Q6 C-1, strict):
  - T0 = timestamp when fix PR for a HIGH/CRITICAL finding is merged
  - Next cron after T0 must confirm the finding is resolved
  - Counter resets: the cron that confirms resolution becomes "cron run 0" (counter at 0)
  - The subsequent weekly cron (T0 + ~7 days) becomes "cron run 1"
  - The cron after that (T0 + ~14 days) becomes "cron run 2" — AC② satisfied
  - Edge case: if the fix merges and the scanner re-runs within the same week (e.g., via manual trigger), treat the manual re-run as cron run 0
- **Counter initial state**: at the moment the LAST batch adoption completes and the final `repos.yml` PR merges, counter is initialized to 0. The next weekly cron that observes the full expanded repo set with zero findings counts as "cron run 1"
- **Manual scanner trigger**: allowed for validation and acceleration, but counts identically to scheduled cron runs in the counter
- **Phase 10 observation minimum duration**: at least 2 full weeks after the final batch merge (= 2 cron runs), potentially longer if resets occur

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Tier 1 < 20 | Cannot meet AC① literally | Tier 2 salvage → if still short, user-approved AC renegotiation via Issue #27 |
| Batch adoption PR review skip authorization misused | Broken CI slips to main | Strict diff-structure check before skip; canary log audit trail; main session is personally accountable |
| Observation phase counter keeps resetting | Phase 10 never completes | Escalation after 3 resets; investigate systemic issue (scanner false positives? broken profile?) |
| `gh manage protection apply` discovers pre-existing broken state | Time lost fixing unrelated issues | Mark "protection deferred"; file Issue; do NOT block Phase 10 completion on unrelated repo state fixes |
| Consumer repo owner complains about unsolicited PR | Social friction | Adoption PRs on private yakkuro repos only; user is sole owner; low risk |
| Weekly cron skips observation (infrastructure outage) | Timeline slips | Manual `gh manage drift --all` fallback; document outage in Issue #27 |
| CLI `gh manage protection apply` has latent bug against specific profile | Halts rollout | Pre-checked during Phase 7; if bug emerges, file cli/v1.0.2 fix Issue and proceed with workaround (manual `gh api` protection set) |

## Post-completion activities

After all AC items are checked:

1. **Close Issue #27** with a summary comment linking the canary log, tier list, and final drift scanner run
2. **Update `CHANGELOG-reusable.md`** with a `## 2026-MM-DD — Phase 10 Rollout` entry summarizing repos adopted, canary findings, and final drift state
3. **Update `docs/consumers.md`** with Phase 10 adoption table (per-repo PR link, merge date, Tier classification)
4. **Update memory** (`project_gh_manage_state.md`) to reflect Phase 10 completion and close out of the v1.0 release cycle
5. **Capture lessons** in `tasks/lessons.md`:
   - Optimal batch size observed vs planned (was 4-5 right?)
   - Review-skip audit trail effectiveness
   - Subagent failure rate (how often did `NEEDS_CONTEXT` fire?)
   - Drift scanner observation reliability (any cron skips? false positives?)
6. **Phase 11 candidate Issues** (informational, not blocking):
   - Phase 11 TS rollout (`reusable-pr-gate-typescript.yml`)
   - `gh manage ci add <repo>` CLI feature (if lesson learned: automation would have saved substantial time)
   - Issue #20 self-dogfood profile fix
   - Dependabot distribution (design spec domain H)

## References

- Top-level design spec: `docs/specs/2026-04-10-gh-manage-design.md` (Phase 10 section, line 906-909)
- Issue #27: [Phase 10: reusable workflow rollout to 20+ active repos + 2-week zero-critical drift validation](https://github.com/yakkuro/gh-manage/issues/27)
- Phase 7 spec: `docs/specs/2026-04-11-phase-7-protection-design.md`
- Phase 8 spec: `docs/specs/2026-04-11-phase-8-drift-design.md`
- Phase 8.5 spec: `docs/specs/2026-04-12-phase-8.5-drift-automation-design.md`
- Phase 9 spec: `docs/specs/2026-04-14-phase-9-v1-hardening-design.md`
- v1.0.x cleanup spec: `docs/specs/2026-04-14-v1.0.x-cleanup-design.md`
- Consumer documentation: `docs/consumers.md`
- Release checklist: `docs/release-checklist.md`
- Versioning policy: `docs/versioning.md`
- Workflow-review protocol: `~/.claude/rules/workflow-review.md` (external to gh-manage; referenced for canary)
- Reusable workflow: `.github/workflows/reusable-pr-gate-python.yml`
