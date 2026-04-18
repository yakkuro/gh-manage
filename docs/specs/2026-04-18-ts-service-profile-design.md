# ts-service Profile + nade-nade repos.yml Fix Design

- **Date**: 2026-04-18
- **Size**: Small
- **Sizing Rationale**: 2 new files (ts-service.yml, ts-ci.yml) + 1 config change (repos.yml 1-line profile rename). All YAML, all mirrors an existing pattern (python-service). Design judgements limited to 2 decisions (npm vs pnpm default, Phase 1/2 split). Test coverage is a light addition to an existing test file.
- **Target**: `yakkuro/gh-manage`
- **Goal**: Close [#29](https://github.com/yakkuro/gh-manage/issues/29) by creating a `ts-service` profile + matching CI template and correcting nade-nade's `repos.yml` entry. This unlocks the TypeScript side of the gh-manage profile system (previously Python-only) without attempting the consumer-side migration of nade-nade's own `ci.yml` (Phase 2 follow-up).

## Background

[#29](https://github.com/yakkuro/gh-manage/issues/29) was filed during Phase 10 pre-scan: `yakkuro/nade-nade` is listed in `src/gh_manage/data/repos.yml` as `profile: python-service` but is actually a TypeScript project (React + vite + vitest, npm-based). Cannot change the profile value to `ts-service` because `src/gh_manage/data/profiles/ts-service.yml` does not exist yet. Originally deferred to "Phase 11 (TypeScript rollout)" but the blocker was the missing profile file, not the timing.

Current TypeScript infrastructure audit:

| Component | State |
|---|---|
| `reusable-pr-gate-typescript.yml` | ✅ exists, production (v1.5.0), defaults to pnpm |
| `ts-service` profile YAML | ❌ missing |
| `ci/ts-ci.yml` consumer template | ❌ missing |
| TypeScript consumers currently using the reusable workflow | 0 (nade-nade is mis-pinned to `reusable-pr-gate-python.yml@main`; codelens / shelf-brain have bespoke CI, out of gh-manage scope) |

After cli/v1.5.0's `ReposConfig` validator (#39), the current repos.yml state would fail to load if nade-nade's profile were renamed without the `ts-service.yml` file existing — this spec ships the profile first, the rename second, in a single atomic PR.

## Goals

1. Create a `ts-service` profile mirroring `python-service` in structure, with TypeScript-appropriate content.
2. Create a `ts-ci.yml` consumer template that invokes `reusable-pr-gate-typescript.yml` with npm-centric defaults.
3. Update `repos.yml` to move nade-nade from `python-service` to `ts-service` — this only changes metadata; the actual consumer-side `ci.yml` migration is Phase 2 (separate nade-nade PR).
4. Exercise #39's validator: the new profile is discovered via `importlib.resources` and validates at load time.

## Non-goals

- **nade-nade's `ci.yml` migration** — Phase 2 follow-up consumer-side PR (same pattern as #46-class fixes in tg-commander / repo-init / deep-research). Keeps this spec narrowly focused on the gh-manage repo.
- **pnpm variant profile** — `ts-service.yml` defaults to npm. pnpm consumers override `install-command: "pnpm install --frozen-lockfile"` in their own `ci.yml`. YAGNI; no pnpm consumer exists today.
- **`reusable-pr-gate-typescript.yml` cleanup** — the existing workflow installs pnpm via `setup-node-pnpm` even when `install-command` is npm-based (unused overhead). Tracked separately if it causes friction during Phase 2.
- **TypeScript-specific CLAUDE.md template** — `claude-md/default.md` is language-agnostic (sections: tech stack, conventions, references). Reuse verbatim; no ts-specific variant.
- **`ts-service` adoption for new consumers** — Phase 10 is Python-only; opening ts-service adoption PRs in other yakkuro TS repos is out of scope. Phase 2 handles nade-nade specifically; broader rollout is future work.
- **Documentation updates** — `docs/consumers.md` references Python onboarding. A TypeScript-specific consumer guide is a follow-up; this spec does not bundle it.
- **Codelens / shelf-brain migration** — both have bespoke CI (make ci / postgres service) explicitly carved out of Phase 10. Out of scope.

## §1 — Architecture

Three file changes, all YAML, all isolated to `src/gh_manage/data/`:

```
src/gh_manage/data/
├── profiles/
│   ├── python-service.yml       (existing, unchanged)
│   └── ts-service.yml           ← NEW
├── templates/
│   └── ci/
│       ├── python-ci.yml        (existing, unchanged)
│       └── ts-ci.yml            ← NEW
└── repos.yml                    ← MODIFIED (1 line)
```

The profile YAML is the authoritative mapping from profile name → files to render, policies, and required contexts. The template YAML is the consumer-facing `ci.yml` skeleton written during `gh-manage init`. `repos.yml` is the drift-scanner's list of what to scan with which profile.

No Python code changes. No test code changes beyond adding a ts-service validation test (see §5).

## §2 — `ts-service.yml` content

File: `src/gh_manage/data/profiles/ts-service.yml`

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

Structural mirror of `python-service.yml` — same schema keys in same order. Differences: `name`, `description` (wording), `source` (`ci/ts-ci.yml` vs `ci/python-ci.yml`). Everything else (`protection_policy`, `required_contexts`, `files[1]` CLAUDE.md entry) is intentionally identical.

Rationale for `required_contexts: ["PR Gate / PR Gate"]`: both the Python and TypeScript reusable workflows produce the context `"<caller-job.name> / PR Gate"` when the caller defines `jobs.pr-gate: { name: "PR Gate", uses: ... }`. This makes the single protection policy work for both languages without a ts-specific variant.

## §3 — `ts-ci.yml` content

File: `src/gh_manage/data/templates/ci/ts-ci.yml`

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

Structural mirror of `python-ci.yml`. Comment is copy-verbatim (load-bearing warning about the `"PR Gate / PR Gate"` context invariant). Differences limited to the `uses:` pin, `node-version` (20, LTS), and npm-centric install/test defaults.

### Why npm defaults

- Current sole TS consumer (nade-nade) uses npm — zero migration cost.
- npm is the TypeScript ecosystem's default package manager (most generator tools — create-react-app, create-next-app, create-vite — emit npm by default).
- pnpm consumers override via `install-command: "pnpm install --frozen-lockfile"` + `test-command: "pnpm test"`.
- The reusable workflow's `pnpm-version` input still has a default (10.33.0) that's ignored when npm is used — non-breaking.

### Why `v1.6.0` pin

This spec ships alongside the version bump to `cli/v1.6.0`. Both the `uses:` ref and the `gh-manage-ref:` input are pinned to the tag this spec will produce. Consumers who run `gh-manage init --profile ts-service` AFTER v1.6.0 is tagged will get a template that correctly references the version they installed. Pre-v1.6.0 installs cannot use `--profile ts-service` because the profile doesn't exist yet.

## §4 — `repos.yml` change

File: `src/gh_manage/data/repos.yml`

```diff
   - name: yakkuro/nade-nade
-    profile: python-service
+    profile: ts-service
```

One-line change. All other entries unchanged.

### Post-change drift-scanner behavior

After this PR:
- `gh-manage drift --all` runs — now sees nade-nade with `profile: ts-service`.
- Scanner resolves profile path → finds `ts-service.yml` → loads it (ReposConfig validator passes).
- Scanner evaluates nade-nade's remote state: `ci.yml` currently pins `reusable-pr-gate-python.yml@main` (the misconfig from Phase 10 pre-scan).
- Drift finding emitted: `profile_files/.github/workflows/ci.yml has drifted from template ci/ts-ci.yml` — expected, documents the Phase 2 follow-up.

This is the correct outcome: the drift scanner now REPORTS the misconfig instead of silently skipping (which was the original #29 symptom). Phase 2 (nade-nade PR) closes the drift.

## §5 — Testing

### New unit tests

In `tests/unit/models/test_repos.py` (file exists, has the #39 validator tests — add to the same suite):

```python
def test_reposconfig_accepts_ts_service_profile() -> None:
    """ts-service is a bundled profile after this PR — ReposConfig accepts it."""
    config = ReposConfig(
        version=1,
        repos=[RepoEntry(name="yakkuro/foo", profile="ts-service")],
    )
    assert config.repos[0].profile == "ts-service"


def test_bundled_profiles_includes_both_python_and_ts() -> None:
    """Regression guard: both profiles exist in the bundled data dir."""
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

### Existing tests that should keep passing

- `test_bundled_repos_yml_loads` (`tests/unit/models/test_repos.py`) — loads `repos.yml` and asserts it parses. After this PR, it parses with 22 entries, 1 of which (nade-nade) references `ts-service` — the #39 validator checks this exists and passes.
- `test_profiles_dir_accessible_via_importlib_resources` — still valid, `ts-service.yml` is now also enumerated.

### Template YAML parse check

Add a lightweight local check (no new test file — just documented in the implementation plan):

```bash
python3 -c "import yaml; yaml.safe_load(open('src/gh_manage/data/templates/ci/ts-ci.yml'))"
```

Must exit 0. Mirrors the #44 local YAML parse discipline.

### Self-dogfood

After merge:
```bash
uv run gh-manage drift --all
```
Expected: 22 repos scanned, 0 FAILED. Findings now include drift on `yakkuro/nade-nade` for `profile_files/.github/workflows/ci.yml` (expected — Phase 2 will close).

## §6 — Release

Tag `cli/v1.6.0`. Additive-only release: new profile + new template, no behavior change to existing consumers.

Files:
- `src/gh_manage/__init__.py` — `__version__ = "1.6.0"`
- `pyproject.toml` — `version = "1.6.0"`
- `tests/test_sanity.py` — assertion updated

Release notes summary: "Adds `ts-service` profile for TypeScript consumers. nade-nade moves from python-service to ts-service in the drift scanner roster."

## §7 — Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `ts-ci.yml` pins `@v1.6.0` but consumers running pre-v1.6.0 `gh-manage init` would get a broken template | (Impossible — the ts-service profile doesn't exist pre-v1.6.0, so `--profile ts-service` rejects with the #39 validator's "Unknown profile" error) | Invariant preserved by design: template + profile + tag are one release unit. |
| nade-nade's drift-scanner output grows noisier after this PR (new finding for ci.yml drift) | 1 additional MEDIUM-severity finding per weekly cron, buried in existing 13-finding-total summary | Expected and desired — the finding IS the Phase 2 trigger. `drift --all` summary still reports 0 FAILED. |
| reusable-pr-gate-typescript.yml's pnpm setup fails on npm-only repos (setup-node-pnpm composite action may not tolerate missing pnpm-lock.yaml) | Phase 2 migration fails | Phase 2 surfaces this if it happens; not a Phase 1 blocker because Phase 1 ships no consumer migration. Tracked as a separate TS rollout concern if it materializes. |
| New `ts-service` profile ships with `required_contexts: ["PR Gate / PR Gate"]` but a consumer adopting ts-service without the canonical `pr-gate: { name: "PR Gate" }` shape hits the #46 class | Future admin-merge bug | PR #53's doctor catches this pre-merge. Consumer adoption PRs should run `gh-manage doctor <repo> --profile ts-service` as part of rollout — same discipline as Python repos. |
| `gh-manage-ref: v1.6.0` in ts-ci.yml points to a tag that does not yet exist at PR-open time | Template inside unreleased PR looks inconsistent | Acceptable — tag is pushed immediately post-merge (Task 5 of the plan). The template is never `gh-manage init`-ed from main between merge and tag (and the PR branch itself pins v1.6.0 which is consistent with the chore commit in the same PR). |

## §8 — Acceptance Criteria

- [ ] `src/gh_manage/data/profiles/ts-service.yml` exists with content from §2.
- [ ] `src/gh_manage/data/templates/ci/ts-ci.yml` exists with content from §3.
- [ ] `src/gh_manage/data/repos.yml` has nade-nade on `profile: ts-service`.
- [ ] `uv run pytest -q` green (expect 564 existing + 2 new = 566).
- [ ] `test_reposconfig_accepts_ts_service_profile` + `test_bundled_profiles_includes_both_python_and_ts` added and passing.
- [ ] `uvx ruff@0.8.0 check + format --check src/ tests/` clean.
- [ ] `uv run mypy src/` clean.
- [ ] Local `yaml.safe_load` parse check on `ts-ci.yml` and `ts-service.yml` both exit 0.
- [ ] Self-dogfood `uv run gh-manage drift --all` reports 22 repos scanned, 0 FAILED.
- [ ] Version bumped to `1.6.0` (`__init__.py`, `pyproject.toml`, `test_sanity.py`, `uv.lock`).
- [ ] 4-reviewer protocol clean (Codex + superpowers + SFH + code-reviewer).
- [ ] PR merged → `cli/v1.6.0` tagged + released.
- [ ] #29 auto-closed via PR body `Closes #29`.

## §9 — Open Questions

None. Design decisions resolved during 2026-04-18 brainstorming:
- npm default (vs pnpm): npm wins (§3 rationale).
- Phase 1 vs Phase 2 scope split: Phase 1 = gh-manage repo only; nade-nade ci.yml migration is Phase 2 (separate PR, out of this spec).

## References

- Root-cause issue: [yakkuro/gh-manage#29](https://github.com/yakkuro/gh-manage/issues/29)
- Profile validator (unblocks this PR): [PR #58 (cli/v1.5.0)](https://github.com/yakkuro/gh-manage/pull/58), [`#39`](https://github.com/yakkuro/gh-manage/issues/39)
- Doctor guardrail: [PR #53](https://github.com/yakkuro/gh-manage/pull/53)
- Context-name invariant incident: [`#46`](https://github.com/yakkuro/gh-manage/issues/46)
- Phase 10 umbrella: [`#27`](https://github.com/yakkuro/gh-manage/issues/27)
- Existing Python-side reference: `src/gh_manage/data/profiles/python-service.yml`, `src/gh_manage/data/templates/ci/python-ci.yml`
