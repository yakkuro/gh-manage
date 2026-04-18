# Consumer CI `pr-gate` Job-Shape Fix Design

- **Date**: 2026-04-17
- **Size**: Small
- **Sizing Rationale**: 3 consumer repos (all outside `gh-manage`), surgical YAML edit (rename job id + add `name:` attribute), no functional change. Well-specified by existing `gh-manage#46` comment thread. No new design judgments beyond pattern unification.
- **Target**: consumer repos `yakkuro/tg-commander`, `yakkuro/repo-init`, `yakkuro/deep-research` (NOT `yakkuro/gh-manage` itself — the fix lives in the consumer repos)
- **Goal**: Normalize the 3 consumer repos' `.github/workflows/ci.yml` to produce the status-check context `PR Gate / PR Gate` that their branch protection already requires, eliminating the need for `--admin` merge on every future version bump PR.

## Background

During `gh-manage` v1.1.0 rollout (2026-04-17), three consumer bump PRs required `gh pr merge --admin` because their CI produced a status context that did not match the context their branch protection required. See `gh-manage#46`, `#27` close-out comment, and the PR #53 (doctor guardrail) spec for the detailed root-cause analysis.

Current state (audit of all 22 repos in `src/gh_manage/data/repos.yml`):

| Repo | Job id | `name:` | Produced context | Required context |
|---|---|---|---|---|
| tg-commander | `test` | (missing) | `test / PR Gate` | `PR Gate / PR Gate` |
| repo-init | `call-pr-gate` | (missing) | `call-pr-gate / PR Gate` | `PR Gate / PR Gate` |
| deep-research | `pr-gate` | (missing) | `pr-gate / PR Gate` | `PR Gate / PR Gate` |
| (all other 19 Python consumers) | `pr-gate` | `PR Gate` | `PR Gate / PR Gate` ✓ | `PR Gate / PR Gate` ✓ |

Audit complete — only these 3 offenders. `codelens` and `shelf-brain` use bespoke CI (no reusable workflow) and are out of Phase 10 scope.

## Goals

1. Align `ci.yml` job shape in 3 consumer repos to produce `PR Gate / PR Gate` context.
2. Exercise `gh-manage doctor` in real-world use: pre-fix doctor flags `shape/job-shape-coherence` as critical, post-fix doctor is clean on these 3 repos.
3. Close out the remaining Phase 10 (`gh-manage#27`) overhang: after these fixes, next bump PR cycle completes without admin merge.

## Non-goals

- Fixing `codelens` (bespoke CI, not using reusable workflow — out of scope; `docs/consumers.md` Phase 3 follow-up).
- Fixing `shelf-brain` (bespoke CI with postgres service block — out of scope, same reason).
- Migrating `gh-manage` self-dogfood job `name: "PR Gate (self-dogfood)"` to match — intentional asymmetry (self-dogfood uses in-repo path `./.github/workflows/reusable-pr-gate-python.yml` and has its own protection rule).
- Updating `gh-manage` branch-protection profile (`src/gh_manage/data/branch-protection.yml`). No gh-manage repo changes at all.
- Version bumps in `uses:` pin. All 3 repos already pin `@v1.1.0`.
- Changes to test content, lint configs, `pyproject.toml`, or any non-`ci.yml` file in the consumer repos.

## §1 — Architecture

Three independent per-consumer-repo PRs, opened in parallel.

```
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│ yakkuro/tg-commander │     │   yakkuro/repo-init  │     │ yakkuro/deep-research │
│                      │     │                      │     │                       │
│ feat/ci-job-shape    │     │ feat/ci-job-shape    │     │ feat/ci-job-shape     │
│ → edit ci.yml        │     │ → edit ci.yml        │     │ → edit ci.yml         │
│ → 1 commit           │     │ → 1 commit           │     │ → 1 commit            │
│ → PR → CI → merge    │     │ → PR → CI → merge    │     │ → PR → CI → merge     │
└──────────────────────┘     └──────────────────────┘     └──────────────────────┘
```

Each repo's workflow is file-ownership-independent (different repos). No coordination needed between them.

## §2 — The Fix (per repo)

The `.github/workflows/ci.yml` in each repo ends up in this canonical shape:

```yaml
name: CI

on:
  <existing triggers, unchanged>

jobs:
  pr-gate:
    name: PR Gate
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
    with:
      <existing inputs, unchanged>
```

Only two fields change: the top-level `jobs.<id>` key (renamed to `pr-gate`) and the addition of `name: PR Gate`. Everything else (`on:`, `uses:`, `with:`, any `permissions:` / `secrets:` / `concurrency:` blocks, and every existing input value) is preserved byte-for-byte.

Per-repo diff summary:

**tg-commander** (current `jobs.test:` without `name:`):
- Rename `test:` → `pr-gate:`
- Add `name: PR Gate`

**repo-init** (current `jobs.call-pr-gate:` without `name:`):
- Rename `call-pr-gate:` → `pr-gate:`
- Add `name: PR Gate`

**deep-research** (current `jobs.pr-gate:` without `name:`):
- Add `name: PR Gate` (job id already correct)

## §3 — Workflow per repo

1. Clone repo to `/tmp/yakkuro-<name>` (scratch, removed after merge).
2. `git checkout -b fix/ci-job-shape`.
3. Edit `.github/workflows/ci.yml` per §2.
4. `git commit -m "fix(ci): normalize pr-gate job to match PR Gate branch protection"` (commit message in §4).
5. `git push -u origin fix/ci-job-shape`.
6. `gh pr create` with title + body from §4.
7. Wait for CI (the reusable PR gate workflow runs and produces the new `PR Gate / PR Gate` context).
8. `gh pr merge <N> --squash --delete-branch` — the test is that this succeeds without `--admin`. Admin-merge indicates the fix did not land correctly.
9. Remove the scratch clone.

Steps 1-6 run in parallel across the 3 repos. Steps 7-8 are independent per repo — each PR merges as soon as its own CI goes green; no repo waits for the others. If one PR's CI fails while the other two succeed, the successful ones still merge; the failed one is investigated in isolation.

**Async SLA**: Expect each PR's CI to complete within 5-10 minutes (the reusable PR gate runs ruff + mypy + pytest — ~2-3 min for a typical consumer). If CI has not finished 15 minutes after `gh pr create`, check `gh run view --repo yakkuro/<repo>` for the triggered workflow run status and investigate any stall (GitHub Actions queue, runner unavailability, etc.) before blocking on other tasks.

## §4 — PR metadata (identical for all 3)

**Branch**: `fix/ci-job-shape`

**Commit message**:
```
fix(ci): use jobs.pr-gate + name: "PR Gate" for branch protection match

Normalize this repo's ci.yml to produce the status-check context
"PR Gate / PR Gate" that its branch protection already requires.

Pre-fix: job id was `<old-id>` with no `name:` attribute, producing
context `<old-id> / PR Gate`, which the protection rule never matches —
forcing `gh pr merge --admin` on every version bump PR.

Post-fix: job id is `pr-gate` with `name: "PR Gate"`, producing the
exact context the protection rule requires.

Functional CI content (what gets installed / tested / linted) is
unchanged. Only the status check name is affected.

Relates: yakkuro/gh-manage#46, yakkuro/gh-manage#27.
```

**PR title**: `fix(ci): normalize pr-gate job to match PR Gate branch protection`

**Per-repo PR body** (concrete, not templated — each repo has its own prior PR number and old-id):

**tg-commander PR body**:
```markdown
## Problem

This repo's branch protection requires status check `PR Gate / PR Gate`, but `.github/workflows/ci.yml` previously defined the job as `jobs.test:` (without a `name:` attribute), producing context `test / PR Gate`. The two never match, so the required check never fires — and every version bump PR hits the protection wall despite green CI.

The v1.1.0 rollout (yakkuro/gh-manage#27) had to admin-merge this repo's bump PR (#2). This fix makes the existing protection functional.

## Fix

- Job id: `test` → `pr-gate`
- Added `name: PR Gate`
- Everything else (`on:`, `uses:`, `with:`) is byte-identical.

No functional CI change — same installer, same tests, same lint config. Only the status check name.

## Merge test

This PR itself is the acceptance test: if it merges without `--admin`, the fix works.

## References

- yakkuro/gh-manage#46 — root-cause analysis across 3 affected repos
- yakkuro/gh-manage#27 — Phase 10 rollout context
- yakkuro/gh-manage#53 — `gh-manage doctor` detects this class of shape mismatch
```

**repo-init PR body**:
```markdown
## Problem

This repo's branch protection requires status check `PR Gate / PR Gate`, but `.github/workflows/ci.yml` previously defined the job as `jobs.call-pr-gate:` (without a `name:` attribute), producing context `call-pr-gate / PR Gate`. The two never match, so the required check never fires — and every version bump PR hits the protection wall despite green CI.

The v1.1.0 rollout (yakkuro/gh-manage#27) had to admin-merge this repo's bump PR (#3). This fix makes the existing protection functional.

## Fix

- Job id: `call-pr-gate` → `pr-gate`
- Added `name: PR Gate`
- Everything else (`on:`, `uses:`, `with:`) is byte-identical.

No functional CI change — same installer, same tests, same lint config. Only the status check name.

## Merge test

This PR itself is the acceptance test: if it merges without `--admin`, the fix works.

## References

- yakkuro/gh-manage#46 — root-cause analysis across 3 affected repos
- yakkuro/gh-manage#27 — Phase 10 rollout context
- yakkuro/gh-manage#53 — `gh-manage doctor` detects this class of shape mismatch
```

**deep-research PR body**:
```markdown
## Problem

This repo's branch protection requires status check `PR Gate / PR Gate`, but `.github/workflows/ci.yml` previously defined the job as `jobs.pr-gate:` WITHOUT a `name:` attribute, producing context `pr-gate / PR Gate` (lowercase job id used as label). The two never match, so the required check never fires — and every version bump PR hits the protection wall despite green CI.

The v1.1.0 rollout (yakkuro/gh-manage#27) had to admin-merge this repo's bump PR (#14). This fix makes the existing protection functional.

## Fix

- Added `name: PR Gate` (job id `pr-gate` was already correct).
- Everything else (`on:`, `uses:`, `with:`) is byte-identical.

No functional CI change — same installer, same tests, same lint config. Only the status check name.

## Merge test

This PR itself is the acceptance test: if it merges without `--admin`, the fix works.

## References

- yakkuro/gh-manage#46 — root-cause analysis across 3 affected repos
- yakkuro/gh-manage#27 — Phase 10 rollout context
- yakkuro/gh-manage#53 — `gh-manage doctor` detects this class of shape mismatch
```

## §5 — Validation strategy

### Pre-fix validation (per repo)

```bash
uv run gh-manage doctor yakkuro/<repo> --profile python-service
```
Expected output: `shape/job-shape-coherence` reports **critical**, with a message describing the produced-vs-required context mismatch. This confirms the bug exists and that doctor's detection is working on real-world offenders.

### Post-fix validation (per repo, AFTER merge + main-branch CI completes)

```bash
uv run gh-manage doctor yakkuro/<repo> --profile python-service
```
Expected output: `shape/job-shape-coherence` is **clean** (or absent). Other findings (drift, etc.) may remain; those are out of scope.

**Timing**: `doctor` reads the current protection and CI shape from the GitHub API. The `shape/job-shape-coherence` check flips as soon as the fix is on the default branch — no wait for main-branch CI to complete. If doctor still reports the mismatch after merge, either (a) the squash-merge commit diverged from the PR head (inspect `git show <squash-sha>` on main), or (b) a second CI-file-owning PR landed concurrently. Run doctor a second time 5 minutes later to rule out API cache; if still bad, investigate. Do NOT re-push a duplicate fix without understanding the root cause.

### Close-out validation

```bash
uv run gh-manage drift --all
```
Expected: all 22 repos report OK. No new FAILED entries introduced by the 3 changed repos.

## §6 — Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Branch protection was actually set to a different context name (audit wrong) | PR blocks indefinitely on green CI | Protection settings were read during #46 analysis and confirmed in `gh api repos/<repo>/branches/main/protection`. If mismatch is found during doctor pre-check, abort and escalate. |
| CI itself fails (pre-existing broken test) | PR can't merge without fixing CI | All 3 repos have shipped prior bump PRs successfully (via admin merge) — CI content is green. If CI fails, it's a new regression; abort and investigate. |
| Workflow triggers (`on:`) get reformatted by YAML library | Unintended change | Use Read/Edit tools (not yaml.dump round-trip). Preserve existing YAML formatting character-for-character outside the 2 target fields. |
| `jobs.pr-gate` name collides with another job in the same workflow | YAML parse error | Audit confirms each of the 3 repos has exactly ONE `jobs.<id>:` entry. No collision risk. |
| CI runs but produces a different context name than expected | Fix didn't work — protection still blocks | Before merging, verify the actual context name via `gh pr checks <PR>` output. If it's still `<old-id> / PR Gate`, something went wrong in step 3 (edit). Abort the merge, re-read the edit diff, and redo steps 3-6 on a fresh branch. Do NOT merge with `--admin` as a workaround — that defeats the test. |
| Doctor pre-check reports `shape/job-shape-coherence` as **clean** on an unfixed repo | False negative — audit disagrees with doctor | Double-check with `gh api repos/yakkuro/<repo>/branches/main/protection --jq '.required_status_checks.contexts'` vs. `gh api repos/yakkuro/<repo>/contents/.github/workflows/ci.yml` (decode + grep). If audit + API agree but doctor disagrees, file a doctor bug and pause the fix (doctor's real-world validation was a goal — if it regresses here, PR #53 wasn't ready). |
| Parallel PRs interact (they won't — different repos) | (N/A) | Each PR is in a different repo; no shared state. |

## §7 — Acceptance Criteria

- [ ] 3 PRs open in tg-commander, repo-init, deep-research — each with 1 commit on branch `fix/ci-job-shape`.
- [ ] Each PR's CI turns green with status context `PR Gate / PR Gate` (verified via `gh pr checks <N>`).
- [ ] Each PR is merged via `gh pr merge <N> --squash --delete-branch` WITHOUT `--admin` flag. (This is the core test.)
- [ ] After each merge, `uv run gh-manage doctor yakkuro/<repo> --profile python-service` reports `shape/job-shape-coherence` as clean (or absent).
- [ ] `uv run gh-manage drift --all` continues to report all 22 repos OK post-merge.
- [ ] Scratch clones in `/tmp/` removed.

## §8 — Open Questions

None. All design decisions resolved during the 2026-04-17 brainstorming conversation. Spec-critique round 1 findings (2 HIGH, 3 MEDIUM, 1 LOW) folded into §3 (async SLA), §5 (post-fix timing + fallback), §6 (abort/redo on mismatch + doctor false-negative row), §4 (3 concrete per-repo PR bodies instead of placeholder template).

## References

- Root-cause issue: [`yakkuro/gh-manage#46`](https://github.com/yakkuro/gh-manage/issues/46) (closed 2026-04-17 with PR #53)
- Phase 10 umbrella: [`yakkuro/gh-manage#27`](https://github.com/yakkuro/gh-manage/issues/27)
- Doctor guardrail (detector): [`yakkuro/gh-manage#53`](https://github.com/yakkuro/gh-manage/pull/53) + spec `docs/specs/2026-04-17-doctor-guardrail-design.md`
- Canary convention reference: `docs/phase-10-canary-log.md`
