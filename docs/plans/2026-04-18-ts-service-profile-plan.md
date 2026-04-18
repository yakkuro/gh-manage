# ts-service Profile + nade-nade repos.yml Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `ts-service` profile + `ts-ci.yml` template and move nade-nade's `repos.yml` entry onto `ts-service`, closing #29. Ship as `cli/v1.6.0`. Phase 2 (nade-nade's own `ci.yml` migration) is a separate consumer-side PR, not in this plan.

**Architecture:** Three YAML file changes in `src/gh_manage/data/`: new `profiles/ts-service.yml`, new `templates/ci/ts-ci.yml`, one-line `repos.yml` update. Plus 2 validator tests, a version bump, and a release PR. No Python code changes.

**Tech Stack:** Pydantic v2 (`ReposConfig` validator from cli/v1.5.0), `importlib.resources` for profile discovery, `yaml.safe_load` for YAML parse checks, `pytest` + `pytest-mock`, `ruff@0.8.0`, `mypy`.

**Spec:** [`docs/specs/2026-04-18-ts-service-profile-design.md`](../specs/2026-04-18-ts-service-profile-design.md)

**Related:** Closes [#29](https://github.com/yakkuro/gh-manage/issues/29). Depends on cli/v1.5.0's `ReposConfig` validator ([PR #58](https://github.com/yakkuro/gh-manage/pull/58), [#39](https://github.com/yakkuro/gh-manage/issues/39)).

---

## File structure (locked in by this plan)

**New files:**
- `src/gh_manage/data/profiles/ts-service.yml` — profile YAML (Task 1)
- `src/gh_manage/data/templates/ci/ts-ci.yml` — CI template (Task 2)

**Modified files:**
- `src/gh_manage/data/repos.yml` — nade-nade profile → `ts-service` (Task 3)
- `tests/unit/models/test_repos.py` — 2 new unit tests (Task 4)
- `src/gh_manage/__init__.py`, `pyproject.toml`, `tests/test_sanity.py`, `uv.lock` — version bump to 1.6.0 (Task 6)

**Branch:** `fix/ts-service-profile` (already created; spec commits live on it).

---

## Prerequisite: commit the plan

- [ ] **Step 0.1: Verify branch state**

```bash
cd /home/server160/repos/gh-manage
git branch --show-current
# Expected: fix/ts-service-profile
git log --oneline -3
# Expected HEAD: "docs: address spec-critique round 1 findings" (fc225ae)
#          prior: "docs: spec for ts-service profile + nade-nade repos.yml fix" (6dbe63d)
```

- [ ] **Step 0.2: Commit this plan**

```bash
git add docs/plans/2026-04-18-ts-service-profile-plan.md
git commit -m "docs: add ts-service profile implementation plan"
```

---

## Task 1: Create `ts-service.yml` profile

**Files:**
- Create: `src/gh_manage/data/profiles/ts-service.yml`

- [ ] **Step 1.1: Read the reference python-service.yml**

```bash
cd /home/server160/repos/gh-manage
cat src/gh_manage/data/profiles/python-service.yml
```

Confirm the structure:
```yaml
version: 1
name: python-service
description: "Python service repo (uv + ruff + mypy + pytest)"
files:
  - source: ci/python-ci.yml
    dest: .github/workflows/ci.yml
  - source: claude-md/default.md
    dest: CLAUDE.md
    skip_if_exists: true
protection_policy: solo-default
required_contexts: ["PR Gate / PR Gate"]
```

- [ ] **Step 1.2: Create the ts-service.yml file**

Use the Write tool to create `src/gh_manage/data/profiles/ts-service.yml` with this exact content:

```yaml
version: 1
name: ts-service
description: "TypeScript service repo (npm + eslint + tsc + vitest)"
files:
  - source: ci/ts-ci.yml
    dest: .github/workflows/ci.yml
  - source: claude-md/default.md
    dest: CLAUDE.md
    skip_if_exists: true
protection_policy: solo-default
required_contexts: ["PR Gate / PR Gate"]
```

- [ ] **Step 1.3: Verify YAML parses**

```bash
python3 -c "import yaml; d = yaml.safe_load(open('src/gh_manage/data/profiles/ts-service.yml')); print(d['name'], d['required_contexts'])"
```
Expected output: `ts-service ['PR Gate / PR Gate']`

- [ ] **Step 1.4: Commit**

```bash
git add src/gh_manage/data/profiles/ts-service.yml
git commit -m "feat(profiles): add ts-service profile for TypeScript consumers

Mirrors python-service structure:
- description names the TS toolchain (npm + eslint + tsc + vitest)
- files[] renders ci/ts-ci.yml to .github/workflows/ci.yml
- CLAUDE.md uses the shared default.md (language-agnostic)
- protection_policy: solo-default, same as python-service
- required_contexts: [\"PR Gate / PR Gate\"] — same invariant, works
  because both reusable workflows produce the canonical context name
  when consumers define jobs.pr-gate: { name: \"PR Gate\" }.

Partial (file 1/3) for #29."
```

---

## Task 2: Create `ts-ci.yml` template

**Files:**
- Create: `src/gh_manage/data/templates/ci/ts-ci.yml`

- [ ] **Step 2.1: Read the reference python-ci.yml**

```bash
cat src/gh_manage/data/templates/ci/python-ci.yml
```

Confirm the structure has `name: CI`, the `on:` block, the load-bearing comment about the `"PR Gate / PR Gate"` context invariant (references yakkuro/gh-manage#46), and `jobs.pr-gate: { name: "PR Gate", uses: ..., with: ... }`.

- [ ] **Step 2.2: Create the ts-ci.yml file**

Use the Write tool to create `src/gh_manage/data/templates/ci/ts-ci.yml` with this exact content:

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

# REQUIRED — DO NOT modify the two fields below without also updating branch protection.
#
# GitHub Actions generates a status context of the form
#   "<job.name OR job_id> / <job-step-name-from-reusable-workflow>"
# The bundled branch-protection policy requires the literal context
# "PR Gate / PR Gate", so both `pr-gate` as the job id AND `name: "PR Gate"`
# as the display label must stay as-is.
#
# See yakkuro/gh-manage#46 for the incident where this invariant was broken
# across three repos and caused admin-merges during the v1.1.0 rollout.
jobs:
  pr-gate:
    name: PR Gate
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-typescript.yml@v1.6.0
    with:
      node-version: "20"
      gh-manage-ref: v1.6.0
      install-command: "npm ci"
      test-command: "npm test"
```

- [ ] **Step 2.3: Verify YAML parses**

```bash
python3 -c "import yaml; d = yaml.safe_load(open('src/gh_manage/data/templates/ci/ts-ci.yml')); print(d['jobs']['pr-gate']['name'])"
```
Expected output: `PR Gate`

- [ ] **Step 2.4: Commit**

```bash
git add src/gh_manage/data/templates/ci/ts-ci.yml
git commit -m "feat(templates): add ts-ci.yml consumer CI template

Mirrors python-ci.yml structure. Key differences:
- uses: reusable-pr-gate-typescript.yml@v1.6.0 (vs python variant)
- node-version: \"20\" (LTS) instead of python-version
- install-command: \"npm ci\" (vs pnpm default of the reusable workflow)
- test-command: \"npm test\"

npm default rationale (spec §3): matches nade-nade (sole current TS
consumer), and npm is the most widely used package manager in the TS
ecosystem. Consumers using pnpm override install-command/test-command.

Load-bearing comment about the \"PR Gate / PR Gate\" context invariant
is verbatim-copied from python-ci.yml to preserve the #46 incident
reference.

Partial (file 2/3) for #29."
```

---

## Task 3: Update `repos.yml` (nade-nade → ts-service)

**Files:**
- Modify: `src/gh_manage/data/repos.yml`

- [ ] **Step 3.1: Read current entry**

```bash
grep -B1 -A2 "nade-nade" src/gh_manage/data/repos.yml
```
Expected output:
```
  - name: yakkuro/nade-nade
    profile: python-service
```

- [ ] **Step 3.2: Edit the profile line**

Use the Edit tool on `src/gh_manage/data/repos.yml`. Replace EXACTLY:
```
  - name: yakkuro/nade-nade
    profile: python-service
```
with EXACTLY:
```
  - name: yakkuro/nade-nade
    profile: ts-service
```

- [ ] **Step 3.3: Verify the diff is exactly one line**

```bash
git diff src/gh_manage/data/repos.yml
```
Expected: 1 line removed (`profile: python-service`), 1 line added (`profile: ts-service`). Nothing else.

- [ ] **Step 3.4: Verify load_config accepts the change**

```bash
uv run python -c "
from gh_manage.models.repos import ReposConfig
from gh_manage.config import load_config
from importlib.resources import files
from pathlib import Path

repos_path = Path(str(files('gh_manage.data') / 'repos.yml'))
config = load_config(repos_path, ReposConfig)
nade = next(e for e in config.repos if e.name == 'yakkuro/nade-nade')
print(f'nade-nade profile: {nade.profile}')
"
```
Expected output: `nade-nade profile: ts-service`. If the #39 validator fires with "Unknown profile references", it means Task 1 wasn't committed yet or the file is missing — go back and verify.

- [ ] **Step 3.5: Commit**

```bash
git add src/gh_manage/data/repos.yml
git commit -m "fix(repos.yml): move nade-nade from python-service to ts-service

nade-nade is a TypeScript project (React + vite + vitest, npm-based).
Pre-cli/v1.5.0 this mismatch silently FAILed in drift --all. After
#39's ReposConfig validator it would have been caught at load time
once ts-service existed. This commit makes the switch now that the
profile is available (Tasks 1-2).

Note: nade-nade's remote ci.yml still pins reusable-pr-gate-python.yml
and diverges from the new ts-ci.yml template. The drift scanner will
report this as a finding — intentional, triggers the Phase 2 follow-up
(consumer-side migration PR against nade-nade).

Partial (file 3/3) for #29."
```

---

## Task 4: Add unit tests for ts-service profile

**Files:**
- Modify: `tests/unit/models/test_repos.py`

- [ ] **Step 4.1: Write the failing test + regression guard**

Append to `tests/unit/models/test_repos.py`:

```python


# #29: ts-service profile integration
def test_reposconfig_accepts_ts_service_profile() -> None:
    """ts-service is a bundled profile after this PR — ReposConfig accepts it."""
    config = ReposConfig(
        version=1,
        repos=[RepoEntry(name="yakkuro/foo", profile="ts-service")],
    )
    assert config.repos[0].profile == "ts-service"


def test_bundled_profiles_includes_both_python_and_ts() -> None:
    """Regression guard: both profiles exist in the bundled data dir.
    If the wheel drops ts-service.yml, this test fails in CI instead
    of the validator silently rejecting 'ts-service' at runtime.
    """
    from importlib.resources import files

    profiles_root = files("gh_manage.data.profiles")
    names = {
        p.name.rsplit(".", 1)[0]
        for p in profiles_root.iterdir()
        if p.is_file() and p.name.endswith((".yml", ".yaml"))
    }
    assert "python-service" in names
    assert "ts-service" in names
```

- [ ] **Step 4.2: Run the new tests to confirm they pass (not Red — Task 1 already shipped the profile)**

```bash
uv run pytest tests/unit/models/test_repos.py::test_reposconfig_accepts_ts_service_profile tests/unit/models/test_repos.py::test_bundled_profiles_includes_both_python_and_ts -v
```
Expected: both PASS. The test file is added AFTER the profile exists (Task 1), so there's no Red/Green step — this is a post-hoc regression guard.

If either test fails:
- `test_reposconfig_accepts_ts_service_profile` fails with "Unknown profile references" → `ts-service.yml` isn't bundled correctly. Re-check Task 1.
- `test_bundled_profiles_includes_both_python_and_ts` fails → `ts-service.yml` isn't in the profiles dir.

- [ ] **Step 4.3: Full suite regression check**

```bash
uv run pytest -q
```
Expected: all pass (564 existing + 2 new = 566).

Note: existing `test_bundled_repos_yml_loads` (from cli/v1.5.0) now validates that the nade-nade entry with `profile: ts-service` loads without error — it's an implicit integration check.

- [ ] **Step 4.4: Lint + format**

```bash
uvx ruff@0.8.0 check tests/unit/models/test_repos.py
uvx ruff@0.8.0 format --check tests/unit/models/test_repos.py
```
Expected: clean. If format fails, run `uvx ruff@0.8.0 format tests/unit/models/test_repos.py` and re-check.

- [ ] **Step 4.5: Commit**

```bash
git add tests/unit/models/test_repos.py
git commit -m "test(models): add regression guards for ts-service profile

Two new tests in tests/unit/models/test_repos.py:

- test_reposconfig_accepts_ts_service_profile: verifies the #39
  validator accepts 'ts-service' (proves the profile exists and is
  enumerable via importlib.resources).
- test_bundled_profiles_includes_both_python_and_ts: packaging
  regression guard. If the wheel ever drops data/profiles/*.yml,
  this test catches it in CI before runtime.

Completes the test scaffold for #29."
```

---

## Task 5: Verification (pytest + lint + mypy + self-dogfood)

**Files:** none modified. Pure verification.

- [ ] **Step 5.1: Full pytest**

```bash
uv run pytest -q
```
Expected: 566 tests pass (was 564).

- [ ] **Step 5.2: Ruff + format on full source**

```bash
uvx ruff@0.8.0 check src/ tests/
uvx ruff@0.8.0 format --check src/ tests/
```
Expected: all clean.

- [ ] **Step 5.3: mypy**

```bash
uv run mypy src/
```
Expected: `Success: no issues found`.

- [ ] **Step 5.4: YAML parse check on both new bundled files**

```bash
python3 -c "import yaml; yaml.safe_load(open('src/gh_manage/data/profiles/ts-service.yml')); print('ts-service.yml: ok')"
python3 -c "import yaml; yaml.safe_load(open('src/gh_manage/data/templates/ci/ts-ci.yml')); print('ts-ci.yml: ok')"
```
Expected output: both `ok`.

- [ ] **Step 5.5: Self-dogfood — single repo drift**

```bash
uv run gh-manage drift . --profile python-service
```
Expected: exits 0, reports drift findings on the current gh-manage repo (pre-existing, unrelated). No regression from this PR's changes.

- [ ] **Step 5.6: Self-dogfood — full `drift --all`**

```bash
uv run gh-manage drift --all 2>&1 | tail -30
```
Expected scan-level summary: **22 repos scanned, 0 FAILED, 0 SKIPPED**.

Expected new finding (per spec §5): `yakkuro/nade-nade` reports a drift finding on `profile_files/.github/workflows/ci.yml` with severity `medium` (the consumer's ci.yml diverges from the new ts-ci.yml template). This is intentional — documents the Phase 2 follow-up.

If `drift --all` reports `yakkuro/nade-nade: FAILED (...)` instead of `OK`, stop and investigate — it means the profile load failed or the template couldn't render.

---

## Task 6: Version bump to cli/v1.6.0

**Files:**
- Modify: `src/gh_manage/__init__.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_sanity.py`
- Regenerate: `uv.lock` (via `uv sync`)

- [ ] **Step 6.1: Check current version**

```bash
grep __version__ src/gh_manage/__init__.py
grep '^version' pyproject.toml
grep '__version__ ==' tests/test_sanity.py
```
Expected: all three show `1.5.0`.

- [ ] **Step 6.2: Bump to 1.6.0**

Use the Edit tool on each file:

`src/gh_manage/__init__.py`: replace `__version__ = "1.5.0"` with `__version__ = "1.6.0"`.

`pyproject.toml`: replace `version = "1.5.0"` with `version = "1.6.0"`.

`tests/test_sanity.py`: replace `assert gh_manage.__version__ == "1.5.0"` with `assert gh_manage.__version__ == "1.6.0"`.

- [ ] **Step 6.3: Sync + verify**

```bash
uv sync --quiet
uv run gh-manage --version
```
Expected output: `gh-manage, version 1.6.0`.

- [ ] **Step 6.4: Run the sanity test**

```bash
uv run pytest tests/test_sanity.py -v
```
Expected: 2 passed.

- [ ] **Step 6.5: Commit the version bump**

```bash
git add src/gh_manage/__init__.py pyproject.toml tests/test_sanity.py uv.lock
git commit -m "chore: bump cli version to 1.6.0"
```

---

## Task 7: PR + 4-reviewer + merge + tag cli/v1.6.0

- [ ] **Step 7.1: Push branch**

```bash
git push -u origin fix/ts-service-profile
```

- [ ] **Step 7.2: Open the PR**

```bash
gh pr create --title "feat: add ts-service profile + nade-nade repos.yml fix (cli/v1.6.0)" --body "$(cat <<'PRBODY'
## Summary

Closes #29 by creating the TypeScript counterpart of `python-service`. Spec: [docs/specs/2026-04-18-ts-service-profile-design.md](docs/specs/2026-04-18-ts-service-profile-design.md). Plan: [docs/plans/2026-04-18-ts-service-profile-plan.md](docs/plans/2026-04-18-ts-service-profile-plan.md).

## What ships

- `src/gh_manage/data/profiles/ts-service.yml` — new profile, mirrors `python-service.yml` structure.
- `src/gh_manage/data/templates/ci/ts-ci.yml` — new consumer CI template; npm-centric defaults (`install-command: "npm ci"`, `test-command: "npm test"`), pins `reusable-pr-gate-typescript.yml@v1.6.0`.
- `src/gh_manage/data/repos.yml` — nade-nade moves from `python-service` to `ts-service`.
- 2 new tests in `tests/unit/models/test_repos.py`: validator accepts ts-service, and both profiles are bundled.

## Non-goals (tracked for Phase 2 / elsewhere)

- **nade-nade's own `ci.yml` migration** — Phase 2 follow-up PR against the nade-nade repo (same pattern as #46-class consumer-side fixes).
- **pnpm variant profile** — YAGNI; consumers override `install-command` if they use pnpm.
- **TypeScript-specific CLAUDE.md** — `default.md` is language-agnostic (verified).
- **Broader TS rollout** — other TS repos (codelens, shelf-brain) have bespoke CI carved out of scope.

## Tag model

`cli/v1.6.0` is a single repo-wide tag. Both the `uses:` ref and `gh-manage-ref:` input in ts-ci.yml point to that tag. No separate reusable-workflow versioning — the tag references the entire repo state (reusable workflows + profiles + CLI) at the merge commit.

## Test plan

- [x] Full pytest green (566 tests — was 564, +2 new).
- [x] `uvx ruff@0.8.0 check + format --check src/ tests/` clean.
- [x] `uv run mypy src/` clean.
- [x] Local YAML parse check on both new files.
- [x] Self-dogfood: `drift --all` → 22 repos scanned, 0 FAILED. Expected new finding on nade-nade/ci.yml (Phase 2 trigger, intentional).
- [ ] 4-reviewer protocol clean (Codex + superpowers + SFH + code-reviewer).

## Compatibility

Additive only. Existing `python-service` consumers are unaffected. The nade-nade drift finding is intentional (documents the consumer-side migration Phase 2 must address).

## References

- Closes #29
- Depends on cli/v1.5.0 (#58): `ReposConfig` validator that enumerates profiles via `importlib.resources`
- Reusable workflow: `.github/workflows/reusable-pr-gate-typescript.yml` (unchanged this PR)
- Context-invariant: #46

Generated with [Claude Code](https://claude.ai/code)
PRBODY
)"
```

Capture the PR number.

- [ ] **Step 7.3: Launch 4-reviewer protocol in parallel**

Check diff size:
```bash
git diff main..HEAD --shortstat
```
Expected: ~500 LOC (mostly docs, small YAML/tests). For code-reviewer model selection: ≤500 LOC → haiku; 501-2000 → sonnet.

Dispatch 4 reviewers (single message, 4 tool calls):

1. `bash scripts/codex-review-resilient.sh "<prompt>"` — background. Focus on the new YAML contents + the single-tag model.
2. `Agent(subagent_type="superpowers:code-reviewer", prompt=...)` — pass spec + plan paths; focus on plan coverage.
3. `Agent(subagent_type="pr-review-toolkit:silent-failure-hunter", prompt=...)` — focus: can `drift --all` silently skip nade-nade if ts-service loading fails? Is the intentional finding differentiated from a FAILED scan?
4. `Agent(subagent_type="code-reviewer", model=<haiku or sonnet>, prompt=...)` — project convention check.

Wait for all 4. Address CRITICAL/HIGH before merge. Document MEDIUM/LOW decisions inline.

- [ ] **Step 7.4: Address review findings (if any)**

Common expected items:
- Static-check of ts-ci.yml's `gh-manage-ref: v1.6.0` vs actual tag being pushed (should match — Task 7.7 pushes v1.6.0).
- Verification that the #39 validator fires when a made-up invalid profile is used (covered by prior cli/v1.5.0 tests, but reviewer may ask).
- Whether `default.md` is actually language-agnostic (verified during brainstorming — no Python-specific references).

For each finding:
- CRITICAL/HIGH: fix in new commit, push, re-run the relevant reviewer.
- MEDIUM/LOW: document decision (fix or defer) in the PR comments.

- [ ] **Step 7.5: Watch CI + merge**

```bash
gh pr checks <PR-number> --watch
```
Once green + reviews clean:
```bash
gh pr merge <PR-number> --squash --delete-branch
```

- [ ] **Step 7.6: Tag cli/v1.6.0**

```bash
git fetch origin main
git checkout main
git pull --ff-only
git tag -a cli/v1.6.0 -m "cli/v1.6.0 — ts-service profile + nade-nade fix

- New profile: src/gh_manage/data/profiles/ts-service.yml
- New template: src/gh_manage/data/templates/ci/ts-ci.yml (npm defaults)
- repos.yml: nade-nade python-service → ts-service

Unblocks TypeScript consumers. Phase 2 (nade-nade ci.yml migration)
is a separate consumer-side PR. Closes #29.

Builds on cli/v1.5.0's ReposConfig profile validator (#39)."
git push origin cli/v1.6.0
```

- [ ] **Step 7.7: Create GitHub release**

```bash
gh release create cli/v1.6.0 --title "cli/v1.6.0 — ts-service profile (#29)" --notes "$(cat <<'RNBODY'
See [PR #<N>](https://github.com/yakkuro/gh-manage/pull/<N>) for full details.

## Highlights

- **New `ts-service` profile** (#29): TypeScript counterpart of `python-service`. Ships an npm-centric `ci.yml` template that invokes `reusable-pr-gate-typescript.yml@v1.6.0`.
- **nade-nade repos.yml fix**: moves from `python-service` to `ts-service` (was silently FAILing in drift scans pre-cli/v1.5.0).
- **Tag model**: single repo-wide tag `cli/v1.6.0` covers reusable workflows + profiles + CLI. No separate workflow versioning.

## Compatibility

Additive. Existing `python-service` consumers unaffected. The drift scanner will now report a finding for nade-nade's `ci.yml` (still pins the Python reusable workflow) — intentional Phase 2 trigger.

## Follow-up

- Phase 2: migrate nade-nade's own `ci.yml` to invoke `reusable-pr-gate-typescript.yml@v1.6.0`. Consumer-side PR, separate from this release.

## Depends on

- `cli/v1.5.0` (PR #58) — `ReposConfig` profile validator that enumerates bundled profiles.
RNBODY
)"
```

Replace `<N>` in the release body with the actual PR number.

- [ ] **Step 7.8: Verify #29 is closed**

```bash
gh issue view 29 --repo yakkuro/gh-manage --json state --jq '.state'
```
Expected output: `CLOSED` (GitHub auto-closes via "Closes #29" in the PR body).

---

## Self-review (plan vs. spec)

| Spec section | Covered by task(s) |
|---|---|
| §1 Architecture (3 YAML files in src/gh_manage/data/) | Tasks 1, 2, 3 |
| §2 ts-service.yml content | Task 1.2 (exact content inline) |
| §3 ts-ci.yml content + npm rationale + v1.6.0 pin | Task 2.2 (exact content inline) |
| §3 Tag model clarification | Task 7.6 (tag push) + Task 2 commit message |
| §4 repos.yml change (1-line diff) | Task 3 |
| §4 Post-change drift behavior (finding, not FAILED) | Task 5.6 self-dogfood expected-output |
| §5 Testing (2 new tests + parse checks + self-dogfood) | Task 4 (2 tests) + Task 5.4 (parse) + 5.6 (dogfood) |
| §6 Release (version bump + tag) | Task 6 (bump) + Task 7.6 (tag) + Task 7.7 (release) |
| §7 Risks (tag model, drift finding, reusable-workflow setup) | Addressed in Tasks 5.6 (finding expected), 7 (tag model via tag push flow), and spec §7 itself as documentation |
| §8 Acceptance Criteria (every item) | Tasks 1-7 distribute these — see mapping inline in Task 5 and Task 7 |

Placeholder scan: no "TBD", "TODO", "fill in" in the plan. The `<N>` placeholder for PR number in Task 7.7 release notes is captured at runtime in Task 7.2 and substituted manually — this is acceptable (same pattern used successfully in prior plans).

Type consistency: `ts-service` (profile name) and `ts-ci.yml` (template file) spellings are consistent across Tasks 1-4 and in the spec. `v1.6.0` tag appears in Task 2.2 (template content) and Task 6/7 (version bump + tag push) — matching.

Spec §9 rejections (workflows_version metadata, pnpm optimization, CLAUDE.md audit) are NOT re-introduced as tasks — correctly absent.
