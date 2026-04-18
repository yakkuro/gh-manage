# Consumer CI Job-Shape Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open, merge, and verify 3 consumer-repo PRs (`yakkuro/tg-commander`, `yakkuro/repo-init`, `yakkuro/deep-research`) that normalize each repo's `.github/workflows/ci.yml` to produce the status-check context `PR Gate / PR Gate` their branch protection already requires — eliminating the need for `--admin` merge on every future bump PR.

**Architecture:** Three independent per-repo PRs run in parallel. Each edits only `.github/workflows/ci.yml`: rename the `jobs.<id>` key to `pr-gate` and add `name: PR Gate`. No other file, no gh-manage repo changes. Validation uses `gh-manage doctor` pre/post (also serves as real-world validation of PR #53's shape checks).

**Tech Stack:** `gh` CLI for PR lifecycle, `git` for branch/commit, YAML hand-edited (no yaml.dump round-trip to preserve formatting), `gh-manage doctor` for validation.

**Spec:** [`docs/specs/2026-04-17-consumer-ci-job-shape-fix-design.md`](../specs/2026-04-17-consumer-ci-job-shape-fix-design.md)

**Related issues:** [`yakkuro/gh-manage#27`](https://github.com/yakkuro/gh-manage/issues/27) (Phase 10), [`#46`](https://github.com/yakkuro/gh-manage/issues/46) (root-cause, closed by doctor PR #53).

---

## File structure (locked in by this plan)

**In gh-manage repo:** `docs/plans/2026-04-17-consumer-ci-job-shape-fix-plan.md` (this file). No other change.

**In each consumer repo** (3 separate repos outside `gh-manage`):
- Modify: `.github/workflows/ci.yml` — surgical edit (2 field changes, no other field touched)

**Scratch workspace** (cleaned up at end):
- `/tmp/fix-ci-shape/yakkuro-tg-commander/`
- `/tmp/fix-ci-shape/yakkuro-repo-init/`
- `/tmp/fix-ci-shape/yakkuro-deep-research/`

---

## Prerequisite: branch setup on gh-manage side

- [ ] **Step 0.1: Confirm you're on the spec branch with the plan committed**

```bash
cd /home/server160/repos/gh-manage
git branch --show-current
# Expected: docs/consumer-ci-job-shape-spec
git log --oneline -3
# Expected: HEAD = "docs: address spec-critique round 1 findings" (5df9aa8)
#                  "docs: spec for consumer ci.yml job-shape fix (Phase 10 close-out)" (f35be2d)
```

- [ ] **Step 0.2: Add the plan document to the branch**

```bash
git add docs/plans/2026-04-17-consumer-ci-job-shape-fix-plan.md
git commit -m "docs: add consumer ci.yml job-shape fix implementation plan"
```

The `docs/consumer-ci-job-shape-spec` branch is a docs-only PR for `yakkuro/gh-manage`. It is NOT where the actual fixes live — those live in 3 separate consumer-repo PRs (Tasks 2-4). This branch will be merged to `gh-manage` main AFTER the 3 consumer PRs succeed, so the spec + plan record the fix that actually shipped.

---

## Task 1: Baseline — verify doctor detects the bug on all 3 repos

**Purpose:** Exercise `gh-manage doctor` as the pre-fix detector. This is the "Red" step of TDD equivalence — we prove the detector fires on known-broken consumers BEFORE changing anything. If doctor does NOT report critical on any of the 3, abort the plan and file a doctor bug (spec §6 risk row: "doctor false negative").

**Files:** none modified. Read-only commands against GitHub API.

- [ ] **Step 1.1: Run doctor against tg-commander**

```bash
cd /home/server160/repos/gh-manage
uv run gh-manage doctor yakkuro/tg-commander --profile python-service
```
Expected output: includes a finding with severity `critical`, check id `shape/job-shape-coherence`, and a message noting the context mismatch (`test / PR Gate` vs. required `PR Gate / PR Gate`). Exit code is non-zero (doctor exits 1 on critical unless `--exit-zero`).

If the finding is not present: **STOP**. Re-read the audit output in the spec §Background. Either the audit is stale (repo state changed) or doctor has a regression. Do not proceed.

- [ ] **Step 1.2: Run doctor against repo-init**

```bash
uv run gh-manage doctor yakkuro/repo-init --profile python-service
```
Expected: same — `shape/job-shape-coherence` critical, `call-pr-gate / PR Gate` ≠ `PR Gate / PR Gate`.

- [ ] **Step 1.3: Run doctor against deep-research**

```bash
uv run gh-manage doctor yakkuro/deep-research --profile python-service
```
Expected: same — `shape/job-shape-coherence` critical, `pr-gate / PR Gate` (lowercase label) ≠ `PR Gate / PR Gate`.

- [ ] **Step 1.4: Record baseline**

No git operation — this is purely a mental / verbal checkpoint. Write a one-line summary of the 3 doctor runs in your reasoning so you can later diff pre vs. post.

---

## Task 2: Fix `yakkuro/tg-commander`

**Files** (in the scratch clone, NOT in the gh-manage repo):
- Modify: `/tmp/fix-ci-shape/yakkuro-tg-commander/.github/workflows/ci.yml`

**Current state** (from spec §Background audit):
```yaml
jobs:
  test:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
    with:
      python-version: "3.12"
      gh-manage-ref: v1.1.0
      install-command: "uv sync --group dev"
      type-check: false
```

**Target state**:
```yaml
jobs:
  pr-gate:
    name: PR Gate
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
    with:
      python-version: "3.12"
      gh-manage-ref: v1.1.0
      install-command: "uv sync --group dev"
      type-check: false
```

- [ ] **Step 2.1: Clone the repo into scratch workspace**

```bash
mkdir -p /tmp/fix-ci-shape
cd /tmp/fix-ci-shape
gh repo clone yakkuro/tg-commander yakkuro-tg-commander
cd yakkuro-tg-commander
git status
# Expected: "On branch main", "nothing to commit"
```

- [ ] **Step 2.2: Create the fix branch**

```bash
git checkout -b fix/ci-job-shape
```

- [ ] **Step 2.3: Read the current ci.yml to confirm state matches spec**

```bash
cat .github/workflows/ci.yml
```
Expected: starts with `name: CI` + `on:` block, then `jobs:` / `test:` (no `name:` attribute under `test:`). If current state diverges from spec §Background, STOP and re-read — someone may have landed an unrelated change since the audit.

- [ ] **Step 2.4: Edit ci.yml**

Use the Edit tool to change the following in `/tmp/fix-ci-shape/yakkuro-tg-commander/.github/workflows/ci.yml`:

Replace the exact string:
```
jobs:
  test:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
```
with:
```
jobs:
  pr-gate:
    name: PR Gate
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
```

This is a surgical 2-line change. The `with:` block below must remain byte-identical.

- [ ] **Step 2.5: Verify the diff is exactly 2 field changes**

```bash
git diff
```
Expected: 1 removal (`test:`), 2 additions (`pr-gate:` + `name: PR Gate`). If the diff shows more, revert and redo the Edit — you may have accidentally reformatted unrelated lines.

- [ ] **Step 2.6: Verify the YAML still parses**

```bash
python3 -c "import yaml; print(yaml.safe_load(open('.github/workflows/ci.yml'))['jobs']['pr-gate']['name'])"
```
Expected: `PR Gate`

- [ ] **Step 2.7: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "fix(ci): use jobs.pr-gate + name: \"PR Gate\" for branch protection match

Normalize this repo's ci.yml to produce the status-check context
\"PR Gate / PR Gate\" that its branch protection already requires.

Pre-fix: job id was \`test\` with no \`name:\` attribute, producing
context \`test / PR Gate\`, which the protection rule never matches —
forcing \`gh pr merge --admin\` on every version bump PR.

Post-fix: job id is \`pr-gate\` with \`name: \"PR Gate\"\`, producing
the exact context the protection rule requires.

Functional CI content (what gets installed / tested / linted) is
unchanged. Only the status check name is affected.

Relates: yakkuro/gh-manage#46, yakkuro/gh-manage#27."
```

- [ ] **Step 2.8: Push and open PR**

```bash
git push -u origin fix/ci-job-shape
gh pr create \
  --title "fix(ci): normalize pr-gate job to match PR Gate branch protection" \
  --body "$(cat <<'PRBODY'
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
PRBODY
)"
```

Capture the PR URL + number from the command output.

- [ ] **Step 2.9: Record PR number**

Note the PR number (e.g., `yakkuro/tg-commander#N`). You'll need it in Task 5.

---

## Task 3: Fix `yakkuro/repo-init`

**Files** (scratch clone):
- Modify: `/tmp/fix-ci-shape/yakkuro-repo-init/.github/workflows/ci.yml`

**Current state**:
```yaml
jobs:
  call-pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
    with:
      python-version: "3.12"
      gh-manage-ref: v1.1.0
      install-command: "uv sync"
      test-command: "uv run pytest"
      lint: true
      type-check: false
```

**Target state**:
```yaml
jobs:
  pr-gate:
    name: PR Gate
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
    with:
      python-version: "3.12"
      gh-manage-ref: v1.1.0
      install-command: "uv sync"
      test-command: "uv run pytest"
      lint: true
      type-check: false
```

- [ ] **Step 3.1: Clone**

```bash
cd /tmp/fix-ci-shape
gh repo clone yakkuro/repo-init yakkuro-repo-init
cd yakkuro-repo-init
git status
```
Expected: clean, on `main`.

- [ ] **Step 3.2: Create branch**

```bash
git checkout -b fix/ci-job-shape
```

- [ ] **Step 3.3: Read current ci.yml**

```bash
cat .github/workflows/ci.yml
```
Confirm the `jobs.call-pr-gate:` id matches the spec audit. STOP if it differs.

- [ ] **Step 3.4: Edit ci.yml**

Replace the exact string:
```
jobs:
  call-pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
```
with:
```
jobs:
  pr-gate:
    name: PR Gate
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
```

- [ ] **Step 3.5: Diff check**

```bash
git diff
```
Expected: 1 removal (`call-pr-gate:`), 2 additions. Nothing else.

- [ ] **Step 3.6: YAML parse check**

```bash
python3 -c "import yaml; print(yaml.safe_load(open('.github/workflows/ci.yml'))['jobs']['pr-gate']['name'])"
```
Expected: `PR Gate`

- [ ] **Step 3.7: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "fix(ci): use jobs.pr-gate + name: \"PR Gate\" for branch protection match

Normalize this repo's ci.yml to produce the status-check context
\"PR Gate / PR Gate\" that its branch protection already requires.

Pre-fix: job id was \`call-pr-gate\` with no \`name:\` attribute,
producing context \`call-pr-gate / PR Gate\`, which the protection
rule never matches — forcing \`gh pr merge --admin\` on every version
bump PR.

Post-fix: job id is \`pr-gate\` with \`name: \"PR Gate\"\`, producing
the exact context the protection rule requires.

Functional CI content (what gets installed / tested / linted) is
unchanged. Only the status check name is affected.

Relates: yakkuro/gh-manage#46, yakkuro/gh-manage#27."
```

- [ ] **Step 3.8: Push and open PR**

```bash
git push -u origin fix/ci-job-shape
gh pr create \
  --title "fix(ci): normalize pr-gate job to match PR Gate branch protection" \
  --body "$(cat <<'PRBODY'
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
PRBODY
)"
```

- [ ] **Step 3.9: Record PR number**

---

## Task 4: Fix `yakkuro/deep-research`

**Files** (scratch clone):
- Modify: `/tmp/fix-ci-shape/yakkuro-deep-research/.github/workflows/ci.yml`

**Current state**:
```yaml
jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
    with:
      python-version: "3.12"
      gh-manage-ref: "v1.1.0"
      install-command: "uv sync --extra bench --extra dev"
      type-check: false
      setup-command: "uv run mypy packages/"
      test-command: "uv run pytest tests/ -q"
```

**Target state** (job id `pr-gate` already correct, only add `name:`):
```yaml
jobs:
  pr-gate:
    name: PR Gate
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
    with:
      python-version: "3.12"
      gh-manage-ref: "v1.1.0"
      install-command: "uv sync --extra bench --extra dev"
      type-check: false
      setup-command: "uv run mypy packages/"
      test-command: "uv run pytest tests/ -q"
```

- [ ] **Step 4.1: Clone**

```bash
cd /tmp/fix-ci-shape
gh repo clone yakkuro/deep-research yakkuro-deep-research
cd yakkuro-deep-research
git status
```

- [ ] **Step 4.2: Create branch**

```bash
git checkout -b fix/ci-job-shape
```

- [ ] **Step 4.3: Read current ci.yml**

```bash
cat .github/workflows/ci.yml
```
Confirm `jobs.pr-gate:` id is present and there is NO `name:` line directly under it.

- [ ] **Step 4.4: Edit ci.yml**

Insert `name: PR Gate` as a new line immediately after `pr-gate:` and before `uses:`. Use Edit to replace:
```
jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
```
with:
```
jobs:
  pr-gate:
    name: PR Gate
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
```

- [ ] **Step 4.5: Diff check**

```bash
git diff
```
Expected: 1 addition (`name: PR Gate`), 0 removals.

- [ ] **Step 4.6: YAML parse check**

```bash
python3 -c "import yaml; print(yaml.safe_load(open('.github/workflows/ci.yml'))['jobs']['pr-gate']['name'])"
```
Expected: `PR Gate`

- [ ] **Step 4.7: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "fix(ci): add name: \"PR Gate\" to pr-gate job for branch protection match

Normalize this repo's ci.yml to produce the status-check context
\"PR Gate / PR Gate\" that its branch protection already requires.

Pre-fix: job id was \`pr-gate\` (correct) but with no \`name:\`
attribute, producing context \`pr-gate / PR Gate\` (lowercase job id
used as label). The protection rule never matches — forcing
\`gh pr merge --admin\` on every version bump PR.

Post-fix: job now carries \`name: \"PR Gate\"\`, producing the exact
context the protection rule requires.

Functional CI content (what gets installed / tested / linted) is
unchanged. Only the status check name is affected.

Relates: yakkuro/gh-manage#46, yakkuro/gh-manage#27."
```

- [ ] **Step 4.8: Push and open PR**

```bash
git push -u origin fix/ci-job-shape
gh pr create \
  --title "fix(ci): normalize pr-gate job to match PR Gate branch protection" \
  --body "$(cat <<'PRBODY'
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
PRBODY
)"
```

- [ ] **Step 4.9: Record PR number**

---

## Task 5: Watch CI + merge (independent per repo)

**Purpose:** Each PR's CI runs. The core acceptance test is that `gh pr merge <N> --squash --delete-branch` succeeds WITHOUT `--admin`. That proves the emitted context now matches the required context.

**Files:** none — only `gh` commands.

**Important:** Tasks 2-4 may have opened PRs in any order. Task 5 sub-steps run per repo as that repo's CI completes. Do NOT serialize (no "wait for all 3 before merging any"). Also do NOT admin-merge even if tempted — admin-merge defeats the entire test.

- [ ] **Step 5.1: Watch tg-commander CI**

Using the PR number captured in Step 2.9 (call it `$PR1`):
```bash
cd /tmp/fix-ci-shape/yakkuro-tg-commander
gh pr checks $PR1 --watch
```
Expected: `PR Gate / PR Gate   pass   ...`. Previously-seen `test / PR Gate` should NOT appear (the old context name is obsolete once the workflow runs under the new job name).

If the context is still `test / PR Gate` after CI completes: **STOP**. Something went wrong in the edit. Go back to Step 2.4 and re-read the diff. Do NOT `--admin` merge as a workaround (spec §6 risk row).

- [ ] **Step 5.2: Merge tg-commander**

```bash
gh pr merge $PR1 --squash --delete-branch
```
Expected: succeeds silently (no prompt). If prompt requests admin override: STOP — the fix did not land. Abort and investigate.

- [ ] **Step 5.3: Watch repo-init CI**

Using the PR number from Step 3.9 (call it `$PR2`):
```bash
cd /tmp/fix-ci-shape/yakkuro-repo-init
gh pr checks $PR2 --watch
```
Expected: `PR Gate / PR Gate   pass   ...`

- [ ] **Step 5.4: Merge repo-init**

```bash
gh pr merge $PR2 --squash --delete-branch
```
Expected: succeeds without `--admin`.

- [ ] **Step 5.5: Watch deep-research CI**

Using the PR number from Step 4.9 (call it `$PR3`):
```bash
cd /tmp/fix-ci-shape/yakkuro-deep-research
gh pr checks $PR3 --watch
```
Expected: `PR Gate / PR Gate   pass   ...`

- [ ] **Step 5.6: Merge deep-research**

```bash
gh pr merge $PR3 --squash --delete-branch
```
Expected: succeeds without `--admin`.

---

## Task 6: Post-merge validation

**Purpose:** Confirm doctor now reports clean on all 3 repos and that no new drift was introduced by the change.

**Files:** none modified. Read-only `gh-manage` commands.

- [ ] **Step 6.1: Doctor on tg-commander (post-fix)**

```bash
cd /home/server160/repos/gh-manage
uv run gh-manage doctor yakkuro/tg-commander --profile python-service
```
Expected: NO finding with id `shape/job-shape-coherence`. Other findings unrelated to this fix may still be present (drift, etc.) — that's fine. Exit code should be 0 if no critical/high findings remain.

- [ ] **Step 6.2: Doctor on repo-init (post-fix)**

```bash
uv run gh-manage doctor yakkuro/repo-init --profile python-service
```
Expected: same — `shape/job-shape-coherence` absent/clean.

- [ ] **Step 6.3: Doctor on deep-research (post-fix)**

```bash
uv run gh-manage doctor yakkuro/deep-research --profile python-service
```
Expected: same.

- [ ] **Step 6.4: Full-fleet drift scan**

```bash
uv run gh-manage drift --all
```
Expected: all 22 repos report `OK` in the summary; no repo reports `FAILED`. Findings above severity `low` may still be reported per repo (they're existing drift items, unchanged by this plan), but no repo should newly FAIL because of the changes.

If any of the 3 target repos newly regresses in drift: STOP. Investigate — the fix may have inadvertently changed behavior.

---

## Task 7: Cleanup

- [ ] **Step 7.1: Remove scratch clones**

```bash
rm -rf /tmp/fix-ci-shape
```

- [ ] **Step 7.2: Verify the gh-manage working tree is still on the spec branch**

```bash
cd /home/server160/repos/gh-manage
git branch --show-current
# Expected: docs/consumer-ci-job-shape-spec
git status
# Expected: clean
```

---

## Task 8: Post + update issues, close out

**Files:** none in git. GitHub comment bodies only.

- [ ] **Step 8.1: Comment on #27 with the completion record**

Run:
```bash
cd /home/server160/repos/gh-manage
gh issue comment 27 --body "$(cat <<'EOF'
## #46 class follow-up complete

All 3 consumer repos that required admin-merge during v1.1.0 rollout now carry the canonical `jobs.pr-gate: { name: "PR Gate" }` shape. Their next bump PR will merge normally.

| Repo | PR | Old job / name | New shape | Merge flag |
|---|---|---|---|---|
| yakkuro/tg-commander | #<PR1> | `test:` / missing | `pr-gate: name: "PR Gate"` | squash (non-admin) |
| yakkuro/repo-init | #<PR2> | `call-pr-gate:` / missing | `pr-gate: name: "PR Gate"` | squash (non-admin) |
| yakkuro/deep-research | #<PR3> | `pr-gate:` / missing | `pr-gate: name: "PR Gate"` | squash (non-admin) |

### Doctor validation

Pre-fix: `gh-manage doctor` reported `shape/job-shape-coherence` critical on all 3. Post-fix: clean on all 3. Real-world validation of the PR #53 shape-check framework.

### Phase 10 AC②

No change — still waiting on the 2026-04-20 weekly drift cron. If green, close Phase 10.

### Related

- Spec: `docs/specs/2026-04-17-consumer-ci-job-shape-fix-design.md`
- Plan: `docs/plans/2026-04-17-consumer-ci-job-shape-fix-plan.md`
EOF
)"
```

Before running, replace `<PR1>`, `<PR2>`, `<PR3>` with the actual PR numbers captured in Steps 2.9 / 3.9 / 4.9. Use `sed` inline OR edit the heredoc manually — the plan can't predict the PR numbers.

- [ ] **Step 8.2: Push the gh-manage spec+plan branch**

```bash
cd /home/server160/repos/gh-manage
git push -u origin docs/consumer-ci-job-shape-spec
```

- [ ] **Step 8.3: Open the gh-manage docs PR**

```bash
gh pr create \
  --title "docs: spec + plan for consumer ci.yml job-shape fix" \
  --body "$(cat <<'PRBODY'
## Summary

Records the spec + plan for normalizing the 3 consumer repos (tg-commander, repo-init, deep-research) whose `ci.yml` produced wrong status check contexts during the v1.1.0 rollout. Consumer-side fixes have already shipped as 3 separate PRs (see comments on #27). This PR only adds the design + plan documents to the gh-manage repo for traceability.

## What ships

- `docs/specs/2026-04-17-consumer-ci-job-shape-fix-design.md` (Small spec)
- `docs/plans/2026-04-17-consumer-ci-job-shape-fix-plan.md` (implementation plan)

## No code change in this PR

All behavior change lives in the consumer repos. This is a docs-only follow-up to preserve the reasoning.

## References

- #27 (Phase 10 umbrella)
- #46 (root-cause thread, closed by #53)
- #53 (doctor guardrail — this spec is its first real-world validation)
PRBODY
)"
```

- [ ] **Step 8.4: Merge the gh-manage docs PR**

CI should be trivial (docs-only). Once green:
```bash
gh pr merge <N> --squash --delete-branch
```
Use normal (non-admin) merge. gh-manage's own ci.yml is correctly shaped (`pr-gate` + `name: "PR Gate (self-dogfood)"`), so no block.

---

## Self-review (plan vs. spec)

| Spec section | Covered by task(s) |
|---|---|
| §1 Architecture (3 parallel per-repo PRs) | Tasks 2, 3, 4 |
| §2 Fix pattern (canonical shape + per-repo diff summary) | Tasks 2.4, 3.4, 4.4 |
| §3 Workflow (clone → edit → PR → CI → merge + async SLA) | Tasks 2, 3, 4 (steps 1-9 each), Task 5 (CI watch + merge) |
| §4 PR metadata (3 concrete bodies) | Tasks 2.8, 3.8, 4.8 |
| §5 Validation (pre-fix doctor, post-fix doctor, drift --all) | Task 1 (pre), Task 6 (post) |
| §6 Risks (doctor false negative, wrong context post-CI, admin-merge avoidance) | Tasks 1.1/1.2/1.3 (abort on no critical), 5.1/5.3/5.5 (abort on wrong context), 5.2/5.4/5.6 (non-admin merge mandate) |
| §7 Acceptance Criteria (3 PRs open, CI green, non-admin merge, doctor clean, drift OK, scratch cleaned) | Tasks 2-4 open + Tasks 5 merge + Task 6 validate + Task 7.1 cleanup |

Spec-to-plan coverage complete. No placeholders remaining — PR numbers (captured at runtime) are the only TBD, and each task that consumes them says "captured in Step X.9". Type consistency: `gh-manage doctor yakkuro/<repo> --profile python-service` signature is identical in Tasks 1 and 6.
