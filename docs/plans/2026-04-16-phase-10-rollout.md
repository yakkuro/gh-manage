# Phase 10 Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Roll out `reusable-pr-gate-python.yml@v1.0.0` to 20+ active Python repos and observe 2 consecutive weeks of zero-critical drift findings — completing the v1.0 release cycle.

**Architecture:** Sequential operational rollout: pre-scan classifies repos → setup PR fixes gh-manage internal defects → canary validates the recipe on 1-2 repos → post-canary updates profile for CI enforcement → batched subagent teams adopt remaining repos → observation phase waits for drift scanner validation.

**Tech Stack:** Python 3.12, uv, gh CLI, GitHub Actions, ruff 0.8.0, mypy 1.12, pytest

**Spec:** `docs/specs/2026-04-16-phase-10-rollout-design.md`

---

## File Map

### gh-manage repo files (created/modified)

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/gh_manage/data/repos.yml` | Fix nade-nade profile + add adopted repos per batch |
| Modify | `src/gh_manage/data/templates/ci/python-ci.yml` | Fix template bug: add `gh-manage-ref`, pin `@v1.0.0` |
| Modify | `src/gh_manage/data/profiles/python-service.yml` | Add `required_contexts` (post-canary; exact context name from Task 3 Step 7) |
| Modify | `tests/unit/protection_sync/test_golden.py` | Update golden test for new `required_contexts` |
| Create | `docs/phase-10-tier-list.md` | Pre-scan output: classified repo list |
| Create | `docs/phase-10-canary-log.md` | Canary execution log + edge cases |
| Modify | `docs/consumers.md` | Phase 10 adoption record |
| Modify | `CHANGELOG-reusable.md` | Phase 10 rollout entry |
| Modify | `CHANGELOG-cli.md` | cli/v1.0.2 entry (template + profile fixes) |

### Per-consumer repo files (created by canary/batch)

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `.github/workflows/ci.yml` | Reusable PR gate invocation |
| Modify | `**/*.py` (conditional) | `ruff --fix` + `ruff format` auto-corrections |

---

## Task 1: Pre-scan — classify candidate repos

**Delegation:** Dispatch a single read-only Explore subagent. Main session spot-checks results.

**Files:**
- Create: `docs/phase-10-tier-list.md`

- [ ] **Step 1: Dispatch pre-scan subagent**

Spawn an Explore subagent with this prompt (adapt as needed):

```
You are classifying yakkuro org Python repos for Phase 10 rollout of gh-manage's
reusable PR gate. For each non-archived Python repo, determine its tier.

**Steps per repo:**
1. `gh repo clone yakkuro/<name> /tmp/phase-10-scan/<name> --depth=1`
2. Check: does `pyproject.toml` exist? Does it have a `[project]` section?
3. Check: does `uv.lock` exist?
4. Check: does `src/` directory exist?
5. Check: does `tests/` have at least one `test_*.py`?
6. Run: `cd /tmp/phase-10-scan/<name> && uvx ruff@0.8.0 check --output-format=json .`
   Record total violations and auto-fixable count.
7. Run: `uvx ruff@0.8.0 format --check .`
   Record whether format is clean.
8. If pyproject.toml has [tool.mypy]: run `uvx --with mypy@1.12 mypy src/`
   Record error count.
9. Classify (Tier 1 if ALL defaults work; Tier 1.5 if needs type-check:false or
   working-directory override; Tier 2 if needs code fixes; Tier 3 if missing pyproject/tests/src).

**Repos to skip:** nade-nade (TypeScript), gh-manage (self-dogfood, out of scope),
plus all non-Python repos.

**Already in repos.yml (included in count but skip scanning):**
slack-agents, llm-kb, rtvc-bench, scenario-engine, tts, vox-speak, picshop

**Output format:** Create /tmp/phase-10-tier-list.md with:
- Summary table (Tier 1/1.5/2/3/Excluded counts)
- Per-tier tables with columns: Rank, Repo, pyproject, uv.lock, src/, tests, Ruff, Format, Mypy, Notes
- Cleanliness score per Tier 1 repo
- repos.yml profile corrections section (nade-nade: python-service → ts-service)
```

- [ ] **Step 2: Spot-check 2-3 Tier 1 results**

Pick the top-ranked and bottom-ranked Tier 1 repos. Independently verify:

```bash
gh repo clone yakkuro/<top-repo> /tmp/phase-10-verify/<top-repo> --depth=1
cd /tmp/phase-10-verify/<top-repo>
ls pyproject.toml uv.lock src/ tests/test_*.py
uvx ruff@0.8.0 check .
uvx ruff@0.8.0 format --check .
```

Expected: classification matches subagent output. If mismatch, investigate and correct tier-list.

- [ ] **Step 3: Confirm Tier 1 + Tier 1.5 total ≥ 20**

```bash
# Count from the tier list (subtract 7 already-in-repos.yml + nade-nade)
# Already adopted: slack-agents, llm-kb, rtvc-bench, scenario-engine, tts, vox-speak, picshop = 7
# Need: 20 - 7 = 13 more from pre-scan Tier 1 + 1.5
```

If total < 13 new repos: evaluate Tier 2 salvage candidates. If still insufficient, post AC renegotiation to Issue #27 and await user input.

- [ ] **Step 4: Copy tier-list to repo**

```bash
cp /tmp/phase-10-tier-list.md /home/server160/repos/gh-manage/docs/phase-10-tier-list.md
```

- [ ] **Step 5: Note canary candidates**

Record the top 2 Tier 1 repos by cleanliness score. These become `CANARY_1` and `CANARY_2` for Task 3-4.

---

## Task 2: Phase 10 setup PR

**Delegation:** Main session only. Contains code changes requiring TDD + 4-reviewer protocol.

**Files:**
- Modify: `src/gh_manage/data/repos.yml`
- Modify: `src/gh_manage/data/templates/ci/python-ci.yml`
- Create: `tests/unit/data/test_template_python_ci.py`
- Create: `docs/phase-10-tier-list.md` (from Task 1)
- Create: `docs/phase-10-canary-log.md` (skeleton)

- [ ] **Step 1: Create feature branch**

```bash
cd /home/server160/repos/gh-manage
git checkout main && git pull origin main
git checkout -b chore/phase-10-setup
```

- [ ] **Step 2: Write failing test for template bug**

Create `tests/unit/data/test_template_python_ci.py`:

```python
"""Verify bundled python-ci.yml template matches reusable workflow requirements."""

from __future__ import annotations

from importlib.resources import files

import yaml


def test_python_ci_template_has_gh_manage_ref() -> None:
    """LOAD-BEARING: reusable workflow requires gh-manage-ref input.
    Without this, any consumer using `gh manage init/apply` gets broken CI."""
    content = (files("gh_manage.data.templates") / "ci" / "python-ci.yml").read_text()
    parsed = yaml.safe_load(content)
    job = parsed["jobs"]["pr-gate"]
    assert "gh-manage-ref" in job["with"], (
        "python-ci.yml template missing required 'gh-manage-ref' input"
    )


def test_python_ci_template_pins_v1() -> None:
    """Template must pin to a release tag, not @main."""
    content = (files("gh_manage.data.templates") / "ci" / "python-ci.yml").read_text()
    parsed = yaml.safe_load(content)
    uses = parsed["jobs"]["pr-gate"]["uses"]
    assert "@v1.0.0" in uses, f"Template uses '{uses}', expected @v1.0.0 pin"
    assert "@main" not in uses, f"Template still uses @main: {uses}"


def test_python_ci_template_has_python_version() -> None:
    """Template must specify python-version (required input)."""
    content = (files("gh_manage.data.templates") / "ci" / "python-ci.yml").read_text()
    parsed = yaml.safe_load(content)
    job = parsed["jobs"]["pr-gate"]
    assert "python-version" in job["with"]
```

- [ ] **Step 3: Run test — confirm RED**

```bash
uv run pytest tests/unit/data/test_template_python_ci.py -v
```

Expected: 2 failures (`test_python_ci_template_has_gh_manage_ref`, `test_python_ci_template_pins_v1`). `test_python_ci_template_has_python_version` passes (already in template).

- [ ] **Step 4: Fix the template**

Replace `src/gh_manage/data/templates/ci/python-ci.yml` with:

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

- [ ] **Step 5: Run test — confirm GREEN**

```bash
uv run pytest tests/unit/data/test_template_python_ci.py -v
```

Expected: all 3 pass.

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: all pass. If `test_golden.py` or `test_profile_sync.py` break, investigate — they should NOT break from a template-only change.

- [ ] **Step 7: Fix nade-nade profile in repos.yml**

In `src/gh_manage/data/repos.yml`, change:

```yaml
  - name: yakkuro/nade-nade
    profile: python-service
```

to:

```yaml
  - name: yakkuro/nade-nade
    profile: ts-service
```

- [ ] **Step 8: Verify repos.yml model still loads**

```bash
uv run python -c "
from importlib.resources import files
from gh_manage.config import load_config
from gh_manage.models.repos import ReposConfig
from pathlib import Path
cfg = load_config(Path(str(files('gh_manage.data') / 'repos.yml')), ReposConfig)
print(f'Loaded {len(cfg.repos)} repos')
for r in cfg.repos:
    print(f'  {r.name}: {r.profile}')
"
```

Expected: 9 repos listed, nade-nade shows `ts-service`.

- [ ] **Step 9: Add tier-list and canary-log skeleton**

```bash
cp /tmp/phase-10-tier-list.md docs/phase-10-tier-list.md
```

Create `docs/phase-10-canary-log.md`:

```markdown
# Phase 10 Canary Log

## Canary repos
1. TBD (populated during canary phase)
2. TBD (populated during canary phase)

## Recipe execution log
(populated during canary phase)

## Edge cases encountered
(populated during canary phase)

## Recipe refinements for batch phase
(populated during canary phase)

## Deferred repos
(populated during batch phase — repos that failed adoption and were skipped/demoted)

## Status check context name
(populated during canary — the exact string for branch protection required_contexts)
```

- [ ] **Step 10: Lint check**

```bash
uvx ruff@0.8.0 check src/ tests/ && uvx ruff@0.8.0 format --check src/ tests/
```

Expected: clean. If not, run `uvx ruff@0.8.0 format src/ tests/` to fix.

- [ ] **Step 11: Commit**

```bash
git add src/gh_manage/data/repos.yml \
        src/gh_manage/data/templates/ci/python-ci.yml \
        tests/unit/data/test_template_python_ci.py \
        docs/phase-10-tier-list.md \
        docs/phase-10-canary-log.md
git commit -m "chore: Phase 10 setup — nade-nade profile fix + template bug fix

Fix two pre-existing defects surfaced during Phase 10 spec:
- python-ci.yml template: add missing gh-manage-ref, pin @v1.0.0
- repos.yml: change nade-nade from python-service to ts-service

Also adds Phase 10 tier list (pre-scan output) and canary log skeleton.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

- [ ] **Step 12: Push and open PR**

```bash
git push -u origin chore/phase-10-setup
gh pr create --base main \
  --title "chore: Phase 10 setup — nade-nade profile + template bug fix" \
  --body "$(cat <<'EOF'
## Summary
- Fix `python-ci.yml` template: add missing `gh-manage-ref` input, pin `@v1.0.0` (was `@main`)
- Fix `repos.yml`: change nade-nade profile from `python-service` to `ts-service`
- Add `docs/phase-10-tier-list.md` (pre-scan classification output)
- Add `docs/phase-10-canary-log.md` (skeleton, populated during canary)
- Add template validation tests

Part of Phase 10 rollout (Issue #27).

## Test plan
- [ ] `uv run pytest tests/unit/data/test_template_python_ci.py -v` — 3 pass
- [ ] `uv run pytest tests/ -v` — full suite green
- [ ] `uvx ruff@0.8.0 check src/ tests/` — clean

Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

- [ ] **Step 13: Run 4-reviewer protocol, address findings, merge**

Per `workflow-review.md`: launch Codex + superpowers:code-reviewer + silent-failure-hunter + code-reviewer in parallel. Fix CRITICAL/HIGH. Then merge:

```bash
gh pr merge <N> --squash --delete-branch
git checkout main && git pull origin main
```

---

## Task 3: Canary — adopt first repo

**Delegation:** Main session only (manual, per spec).

**Prerequisite:** Task 2 merged to main.

**Substitution:** Replace `CANARY_1` below with the repo name from Task 1 Step 5 (Tier 1 Rank 1).

- [ ] **Step 1: Clone and branch**

```bash
gh repo clone yakkuro/CANARY_1 /tmp/phase-10-adopt/CANARY_1
cd /tmp/phase-10-adopt/CANARY_1
git checkout -b feat/adopt-gh-manage-pr-gate
```

- [ ] **Step 2: Create CI workflow file**

Create `.github/workflows/ci.yml` (ensure `.github/workflows/` directory exists):

```bash
mkdir -p .github/workflows
```

Write `.github/workflows/ci.yml`:

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

**For Tier 1.5 repos only:** add `type-check: false` or `working-directory:` to the `with:` block as needed.

- [ ] **Step 3: Run ruff --fix if needed**

```bash
uvx ruff@0.8.0 check --fix .
uvx ruff@0.8.0 format .
```

Record output. If no changes, skip commit 2/3.

- [ ] **Step 4: Run pytest locally (smoke check)**

```bash
uv sync 2>/dev/null || pip install -e . 2>/dev/null
uv run pytest 2>/dev/null || python -m pytest
```

If tests fail (not due to our changes), record in canary log as edge case. Proceed anyway — CI will determine the real outcome.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: adopt gh-manage reusable PR gate (v1.0.0)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

If ruff produced changes:

```bash
git add -A
git commit -m "style: apply ruff --fix + format (auto)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

- [ ] **Step 6: Push and open PR**

```bash
git push -u origin feat/adopt-gh-manage-pr-gate
gh pr create --base main \
  --title "ci: adopt gh-manage reusable PR gate (v1.0.0)" \
  --body "$(cat <<'EOF'
## Summary
- Add `.github/workflows/ci.yml` calling `yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.0.0`
- Auto-apply `ruff --fix` + `ruff format` if needed

Part of yakkuro org Phase 10 rollout (yakkuro/gh-manage#27).

## Test plan
- [ ] CI passes green on this PR

Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

- [ ] **Step 7: Watch CI and record status check context name**

```bash
gh pr checks <N> --watch --repo yakkuro/CANARY_1
```

Once CI finishes, extract the exact context name:

```bash
RUN_ID=$(gh run list --repo yakkuro/CANARY_1 --branch feat/adopt-gh-manage-pr-gate --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "$RUN_ID" --repo yakkuro/CANARY_1 --json jobs --jq '.jobs[] | .name'
```

Expected output: something like `PR Gate / PR Gate`. Record this exact string in `docs/phase-10-canary-log.md` under "Status check context name".

- [ ] **Step 8: Merge (if CI green)**

```bash
gh pr merge <N> --squash --delete-branch --repo yakkuro/CANARY_1
```

If CI fails: debug, fix, re-push. Record failure details in canary log.

- [ ] **Step 9: Update canary log**

Edit `docs/phase-10-canary-log.md` in the gh-manage repo with:
- Canary repo name, PR URL, merge SHA
- All recipe steps with observations
- Edge cases encountered
- Status check context name

---

## Task 4: Canary — adopt second repo

**Delegation:** Main session only.

Repeat Task 3 exactly for `CANARY_2` (Tier 1 Rank 2 from Task 1 Step 5). Record all observations in the canary log alongside `CANARY_1` results.

---

## Task 5: Post-canary fix-up

**Delegation:** Main session only. Contains code changes (profile fix) requiring TDD.

**Prerequisite:** Task 3 + 4 complete. Exact status check context name known.

**Files:**
- Modify: `src/gh_manage/data/profiles/python-service.yml`
- Modify: `tests/unit/protection_sync/test_golden.py`
- Modify: `src/gh_manage/data/repos.yml` (add canary repos)
- Modify: `docs/phase-10-canary-log.md` (finalize)

### Sub-task 5A: Update python-service profile (TDD)

- [ ] **Step 1: Create branch**

```bash
cd /home/server160/repos/gh-manage
git checkout main && git pull origin main
git checkout -b fix/python-service-required-contexts
```

- [ ] **Step 2: Update golden test — make it expect the new context**

In `tests/unit/protection_sync/test_golden.py`, substitute `CONTEXT_NAME` with the actual context string from canary (e.g., `"PR Gate / PR Gate"`):

Change line 28:

```python
    assert profile.required_contexts == []
```

to:

```python
    assert profile.required_contexts == ["CONTEXT_NAME"]
```

Change line 44:

```python
            "contexts": [],  # profile.required_contexts override
```

to:

```python
            "contexts": ["CONTEXT_NAME"],  # profile.required_contexts override
```

- [ ] **Step 3: Run test — confirm RED**

```bash
uv run pytest tests/unit/protection_sync/test_golden.py -v
```

Expected: `test_production_data_loads` fails (profile asserts `[]` but now test expects `["CONTEXT_NAME"]`).

- [ ] **Step 4: Update python-service profile**

In `src/gh_manage/data/profiles/python-service.yml`, change:

```yaml
required_contexts: []
```

to:

```yaml
required_contexts: ["CONTEXT_NAME"]
```

- [ ] **Step 5: Run test — confirm GREEN**

```bash
uv run pytest tests/unit/protection_sync/test_golden.py -v
```

Expected: all pass.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: all pass. Check that `test_protection_sync.py` tests with empty contexts still pass (they use their own fixtures, not the production data).

- [ ] **Step 7: Lint check**

```bash
uvx ruff@0.8.0 check src/ tests/ && uvx ruff@0.8.0 format --check src/ tests/
```

- [ ] **Step 8: Commit, push, PR**

```bash
git add src/gh_manage/data/profiles/python-service.yml \
        tests/unit/protection_sync/test_golden.py
git commit -m "fix: python-service profile required_contexts for PR gate enforcement

Set required_contexts to the empirically confirmed context name from
Phase 10 canary. Without this, gh manage protection apply is a no-op
for status check enforcement.

Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin fix/python-service-required-contexts
gh pr create --base main \
  --title "fix: python-service profile required_contexts for pr-gate enforcement" \
  --body "$(cat <<'EOF'
## Summary
- Update `python-service.yml` profile: set `required_contexts` to the canary-confirmed context
- Update golden test to match

Part of Phase 10 post-canary fix-up (Issue #27).

## Test plan
- [ ] `uv run pytest tests/unit/protection_sync/test_golden.py -v` — pass
- [ ] `uv run pytest tests/ -v` — full suite green

Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

- [ ] **Step 9: 4-reviewer protocol, fix findings, merge**

```bash
gh pr merge <N> --squash --delete-branch
git checkout main && git pull origin main
```

### Sub-task 5B: Add canary repos to repos.yml + protection apply

- [ ] **Step 10: Create branch for repos.yml update**

```bash
git checkout -b chore/phase-10-canary-repos
```

- [ ] **Step 11: Add canary repos to repos.yml**

Append to `src/gh_manage/data/repos.yml`:

```yaml
  - name: yakkuro/CANARY_1
    profile: python-service
  - name: yakkuro/CANARY_2
    profile: python-service
```

- [ ] **Step 12: Commit, push, PR, merge**

```bash
git add src/gh_manage/data/repos.yml
git commit -m "chore: add Phase 10 canary repos to repos.yml

Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin chore/phase-10-canary-repos
gh pr create --base main \
  --title "chore: add Phase 10 canary repos to repos.yml" \
  --body "Adds CANARY_1, CANARY_2 for drift scanner coverage. Part of Phase 10 (Issue #27)."
gh pr merge <N> --squash --delete-branch
git checkout main && git pull origin main
```

- [ ] **Step 13: Apply branch protection to canary repos**

```bash
uv run gh-manage protection apply --repo yakkuro/CANARY_1
uv run gh-manage protection apply --repo yakkuro/CANARY_2
```

- [ ] **Step 14: Verify protection was applied correctly**

```bash
gh api repos/yakkuro/CANARY_1/branches/main/protection --jq '.required_status_checks.contexts'
gh api repos/yakkuro/CANARY_2/branches/main/protection --jq '.required_status_checks.contexts'
```

Expected: `["CONTEXT_NAME"]` for both repos.

- [ ] **Step 15: Verify sequential gate before batch phase**

```bash
gh api repos/yakkuro/gh-manage/contents/src/gh_manage/data/profiles/python-service.yml --jq '.content' | base64 -d | grep -q 'required_contexts: \["'
echo $?
```

Expected: `0` (grep found the non-empty required_contexts). If `1`, STOP — profile update did not merge.

- [ ] **Step 16: Manual drift scan for canary repos**

```bash
uv run gh-manage drift --repo yakkuro/CANARY_1
uv run gh-manage drift --repo yakkuro/CANARY_2
```

Expected: zero HIGH/CRITICAL findings.

- [ ] **Step 17: Commit canary log updates**

```bash
cd /home/server160/repos/gh-manage
git checkout main && git pull origin main
git checkout -b docs/phase-10-canary-log-final
# Edit docs/phase-10-canary-log.md with all findings
git add docs/phase-10-canary-log.md
git commit -m "docs: finalize Phase 10 canary log

Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin docs/phase-10-canary-log-final
gh pr create --base main --title "docs: finalize Phase 10 canary log" --body "Phase 10 canary complete (Issue #27)."
gh pr merge <N> --squash --delete-branch
git checkout main && git pull origin main
```

- [ ] **Step 18: Post canary progress to Issue #27**

```bash
gh issue comment 27 --body "$(cat <<'EOF'
## Phase 10 canary complete

- **Canary 1**: yakkuro/CANARY_1 — PR merged, CI green, protection applied
- **Canary 2**: yakkuro/CANARY_2 — PR merged, CI green, protection applied
- **Status check context name**: `CONTEXT_NAME`
- **Profile update**: merged (required_contexts set)
- **Drift scan**: zero findings for both canary repos

Proceeding to batch phase.
EOF
)"
```

---

## Task 6: Batch adoption (repeatable per batch)

**Delegation:** Subagent team (1 agent per repo). Main session coordinates.

**Prerequisite:** Task 5 complete (sequential gate verified at Step 15).

This task is a **recipe template** — repeat for each batch of 4-5 repos from the Tier 1 residual list (after removing canary repos and the 7 already-in-repos.yml repos).

### Per-batch recipe

- [ ] **Step 1: Select batch repos**

From `docs/phase-10-tier-list.md`, take the next 4-5 Tier 1 repos (in cleanliness score order) that have not been adopted yet.

- [ ] **Step 2: Spawn subagent team**

Spawn one Agent per repo with `model: "sonnet"`. Each agent gets this prompt (substitute `REPO_NAME`):

```
You are adopting yakkuro/REPO_NAME for the gh-manage Phase 10 reusable PR gate rollout.

**File Ownership:** You may ONLY modify files in /tmp/phase-10-adopt/REPO_NAME/
Do NOT edit gh-manage repo files, other repos, or shared state.

**Recipe:**
1. `gh repo clone yakkuro/REPO_NAME /tmp/phase-10-adopt/REPO_NAME`
2. `cd /tmp/phase-10-adopt/REPO_NAME && git checkout -b feat/adopt-gh-manage-pr-gate`
3. `mkdir -p .github/workflows`
4. Create `.github/workflows/ci.yml` with EXACTLY this content:
   [PASTE THE CI YAML TEMPLATE — same as Task 3 Step 2]
   [For Tier 1.5: add the specific override noted in the tier list]
5. `uvx ruff@0.8.0 check --fix . && uvx ruff@0.8.0 format .`
6. `git add -A && git commit -m "ci: adopt gh-manage reusable PR gate (v1.0.0)\n\nCo-Authored-By: Claude <noreply@anthropic.com>"`
   If ruff produced changes: separate commit: `git commit -m "style: apply ruff --fix + format (auto)\n\nCo-Authored-By: Claude <noreply@anthropic.com>"`
7. `git push -u origin feat/adopt-gh-manage-pr-gate`
8. `gh pr create --repo yakkuro/REPO_NAME --base main --title "ci: adopt gh-manage reusable PR gate (v1.0.0)" --body "Part of yakkuro org Phase 10 rollout (yakkuro/gh-manage#27)."`
9. `gh pr checks <N> --watch --repo yakkuro/REPO_NAME`
10. If CI green: `gh pr merge <N> --squash --delete-branch --repo yakkuro/REPO_NAME`
    If CI fails after 1 fix attempt: report NEEDS_CONTEXT with raw error output.

**Acceptance Criteria:**
Return the raw output of:
- `gh pr view <N> --repo yakkuro/REPO_NAME --json mergedAt --jq .mergedAt`
- `gh pr checks <N> --repo yakkuro/REPO_NAME --json conclusion --jq '[.[] | .conclusion] | all(. == "SUCCESS")'`
```

- [ ] **Step 3: Trust-but-verify (main session)**

For each subagent result, independently verify:

```bash
gh pr view <N> --repo yakkuro/REPO_NAME --json state,mergedAt,baseRefName
```

Expected: `state: MERGED`, `mergedAt: <timestamp>`, `baseRefName: main`.

- [ ] **Step 4: Handle failures**

For any subagent that returned `NEEDS_CONTEXT`:
1. Close the unmerged PR: `gh pr close <N> --repo yakkuro/REPO_NAME --comment "Deferred from Phase 10 batch"`
2. Delete the branch: `gh api -X DELETE repos/yakkuro/REPO_NAME/git/refs/heads/feat/adopt-gh-manage-pr-gate`
3. Log in `docs/phase-10-canary-log.md` "Deferred repos" section
4. Pull next Tier 1 repo as replacement (if needed for 20+ count)

- [ ] **Step 5: Update repos.yml for this batch**

```bash
cd /home/server160/repos/gh-manage
git checkout main && git pull origin main
git checkout -b chore/phase-10-batch-N-repos
```

Append successfully adopted repos to `src/gh_manage/data/repos.yml`:

```yaml
  - name: yakkuro/REPO_1
    profile: python-service
  - name: yakkuro/REPO_2
    profile: python-service
  # ... etc
```

```bash
git add src/gh_manage/data/repos.yml
git commit -m "chore: add Phase 10 batch N repos to repos.yml

Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin chore/phase-10-batch-N-repos
gh pr create --base main --title "chore: add Phase 10 batch N repos to repos.yml" --body "Phase 10 batch N (Issue #27)."
gh pr merge <N> --squash --delete-branch
git checkout main && git pull origin main
```

- [ ] **Step 6: Apply protection to batch repos**

```bash
for repo in REPO_1 REPO_2 REPO_3 REPO_4 REPO_5; do
  uv run gh-manage protection apply --repo "yakkuro/$repo"
  echo "Applied protection to $repo"
done
```

Verify:

```bash
for repo in REPO_1 REPO_2 REPO_3 REPO_4 REPO_5; do
  echo -n "$repo: "
  gh api "repos/yakkuro/$repo/branches/main/protection" --jq '.required_status_checks.contexts'
done
```

Expected: `["CONTEXT_NAME"]` for each.

- [ ] **Step 7: Post batch progress to Issue #27**

```bash
gh issue comment 27 --body "## Phase 10 batch N complete

Adopted: REPO_1, REPO_2, REPO_3, REPO_4, REPO_5
Deferred: <list or 'none'>
Total adopted (incl. canary + prior batches): X/20+
repos.yml entries: Y
Protection applied: all"
```

- [ ] **Step 8: Repeat for next batch**

Return to Step 1 with the next set of Tier 1 repos. Continue until 20+ total repos adopted (counting the 7 existing + canary + all batches).

---

## Task 7: Observation monitoring

**Delegation:** Main session. This is a passive time-gated phase.

**Prerequisite:** All batches complete. ≥20 Python service entries in `repos.yml`.

- [ ] **Step 1: Run initial sanity check**

```bash
uv run gh-manage drift --all
```

Expected: zero HIGH/CRITICAL for all repos. If findings exist, fix immediately (this resets the 2-week counter).

- [ ] **Step 2: Verify repo count**

```bash
uv run python -c "
from importlib.resources import files
from gh_manage.config import load_config
from gh_manage.models.repos import ReposConfig
from pathlib import Path
cfg = load_config(Path(str(files('gh_manage.data') / 'repos.yml')), ReposConfig)
python_count = sum(1 for r in cfg.repos if r.profile == 'python-service')
print(f'Python service repos: {python_count}')
assert python_count >= 20, f'Only {python_count} python-service repos — need 20+'
print('AC① PASS')
"
```

- [ ] **Step 3: Wait for first weekly cron (week 1)**

Drift scanner runs Monday 09:00 JST (`0 0 * * 1` UTC). After it runs, check:

```bash
# Check for any drift Issues created in the past week
gh issue list --repo yakkuro/gh-manage --label drift --state open --json title,createdAt --jq '.[] | select(.createdAt > "2026-04-XX") | .title'
```

Expected: no new drift issues. If an issue was created, fix the finding, then the counter resets to 0 (next Monday starts week 1 again).

- [ ] **Step 4: Wait for second weekly cron (week 2)**

Repeat the same check the following Monday. If zero findings for 2 consecutive Mondays:

```bash
echo "AC② PASS — 2 consecutive zero-critical drift findings confirmed"
```

---

## Task 8: Close-out

**Delegation:** Main session.

**Prerequisite:** Task 7 Steps 3-4 pass (both ACs met).

- [ ] **Step 1: Create close-out branch**

```bash
cd /home/server160/repos/gh-manage
git checkout main && git pull origin main
git checkout -b chore/phase-10-closeout
```

- [ ] **Step 2: Update CHANGELOG-reusable.md**

Append under the latest version section:

```markdown
## 2026-XX-XX — Phase 10 Rollout

- Rolled out `reusable-pr-gate-python.yml@v1.0.0` to 20+ active Python repos in the yakkuro org
- Achieved 2 consecutive weeks of zero HIGH/CRITICAL drift findings across all monitored repos
- Applied branch protection (required status check) to all adopted repos
```

- [ ] **Step 3: Update CHANGELOG-cli.md**

Add a `cli/v1.0.2` section:

```markdown
## cli/v1.0.2 — 2026-XX-XX

### Fixed
- `python-ci.yml` template: add missing `gh-manage-ref` input, pin `@v1.0.0` (was `@main`)
- `python-service` profile: set `required_contexts` for PR gate enforcement (was empty `[]`)

### Changed
- `repos.yml`: fix nade-nade profile from `python-service` to `ts-service`
- `repos.yml`: expand from 9 to 20+ entries for Phase 10 adoption
```

- [ ] **Step 4: Update docs/consumers.md**

Add a Phase 10 adoption table (same format as the existing Phase C section). Include per-repo PR link, merge date, Tier classification.

- [ ] **Step 5: Bump CLI version to 1.0.2**

Follow `docs/release-checklist.md` to bump `src/gh_manage/__init__.py` (or `pyproject.toml`) version to `1.0.2`.

- [ ] **Step 6: Commit, push, PR, review, merge**

```bash
git add -A
git commit -m "chore: Phase 10 close-out — CHANGELOG + consumers.md + cli/v1.0.2

Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin chore/phase-10-closeout
gh pr create --base main \
  --title "chore: Phase 10 close-out — CHANGELOG + consumers.md + cli/v1.0.2" \
  --body "Completes Phase 10 (Issue #27). Closes #27."
```

4-reviewer protocol. Fix findings. Merge.

- [ ] **Step 7: Tag cli/v1.0.2**

```bash
git checkout main && git pull origin main
git tag cli/v1.0.2
git push origin cli/v1.0.2
```

- [ ] **Step 8: Close Issue #27**

```bash
gh issue close 27 --comment "$(cat <<'EOF'
## Phase 10 complete

- ✅ AC①: 20+ active Python repos running reusable PR gate
- ✅ AC②: 2 consecutive weeks zero HIGH/CRITICAL drift findings
- ✅ Branch protection applied to all adopted repos
- ✅ python-service profile required_contexts set
- ✅ Template bug fixed, cli/v1.0.2 tagged

See `docs/phase-10-tier-list.md` and `docs/phase-10-canary-log.md` for details.
v1.0 release cycle is now closed.
EOF
)"
```

- [ ] **Step 9: Clean up temp directories**

```bash
rm -rf /tmp/phase-10-scan /tmp/phase-10-adopt /tmp/phase-10-verify
```

---

## Summary

| Task | Type | Delegation | Estimated effort |
|------|------|-----------|-----------------|
| 1. Pre-scan | Research | Subagent (Explore) | 30-60 min |
| 2. Setup PR | Code (TDD) | Main session | 1-2 hours (incl. review) |
| 3. Canary #1 | Ops | Main session | 30-60 min |
| 4. Canary #2 | Ops | Main session | 30-60 min |
| 5. Post-canary | Code (TDD) + Ops | Main session | 1-2 hours (incl. review) |
| 6. Batches (×4-5) | Ops | Subagent teams | 1-2 hours per batch |
| 7. Observation | Passive | Main session (monitoring) | 2 weeks |
| 8. Close-out | Docs | Main session | 30-60 min |
