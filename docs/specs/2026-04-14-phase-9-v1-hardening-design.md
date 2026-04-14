# Phase 9 — v1.0 Hardening Design

**Date**: 2026-04-14
**Size**: Medium
**Sizing Rationale**: 11 files + 7 design decisions → on the edge of Medium / Large per `spec-driven.md`. Chose Medium because (a) the work is 90% editorial / documentation with only 1 new test function and zero production-code changes, (b) no new modules or architectural layers are introduced, (c) the brainstorming decisions are about editorial format and release mechanics rather than architectural tradeoffs. The large file count stems from the v1.0 milestone having many small documentation deliverables rather than complex code.
**Target**: `yakkuro/gh-manage`
**Goal**: Graduate `yakkuro/gh-manage` from Phase 8.5 to v1.0.0 by closing the remaining Phase 9 acceptance-criteria gaps (L6 golden test, 5 documentation files, consumers.md backfill, 2 CHANGELOG updates, v1.0 release tags) and formally declaring the reusable workflow + Python CLI API surfaces stable.

## Context

Phase 9 is the **v1.0 release hardening** phase defined in the top-level design spec (`docs/specs/2026-04-10-gh-manage-design.md`, section "Phase 9 (v1.0 release)"). The design spec enumerates 9 acceptance criteria for Phase 9; several are already satisfied by Phases 5 through 8.5, and this spec covers only the remaining gaps.

As of 2026-04-14, the repository state is:

- `main` at `a5412e1` (9 repos in `src/gh_manage/data/repos.yml`)
- 400 tests passing
- `cli/v0.6.0` released (Phase 8.5 drift scanner automation)
- Reusable workflows at `v0.2.1` (last functionally changed 2026-04-10)
- 9 consumer repos running the drift scanner weekly cron with zero HIGH/CRITICAL findings over 4+ days

## Current state of Phase 9 acceptance criteria

| # | Phase 9 AC (from design spec) | Current state |
|---|---|---|
| 1 | L1 coverage 80%, L4 85%, L5 90%, L6 100% | L1: N/A (`scripts/checks/` was never built). L4: **94%** (`src/gh_manage/` total, target 85% ✅). L5: **93%** (`src/gh_manage/commands/drift.py`, target 90% ✅). L6: **gap** — existing `test_golden.py` exercises fixture templates, not the bundled templates in `src/gh_manage/data/templates/`. |
| 2 | `smoke-test.yml` green on all fixtures | ✅ `smoke-test.yml` exists and passes Python (positive + lint-fail + test-fail) and TypeScript (positive + lint-fail + type-fail) fixtures. |
| 3 | L7 manual integration test completed once | **gap** — `yakkuro/gh-manage-test-fixture` repo and `scripts/reset-fixture.sh` do not exist; no L7 run recorded. |
| 4 | `README.md` + `architecture.md` + `quick-start.md` + `versioning.md` + `distribution-channels.md` complete | **gap** — `README.md` is a 23-line stub; the other 4 documents do not exist. |
| 5 | `docs/consumers.md` has 2+ adoption entries | **partial** — 1 entry (llm-kb, full narrative). Phase C added 8 more consumers that are undocumented. |
| 6 | `CHANGELOG-reusable.md` + `CHANGELOG-cli.md` maintained | **gap** — `CHANGELOG-cli.md` last entry is `0.2.0`; Phase 6 through 8.5 (4 releases) are undocumented. `CHANGELOG-reusable.md` last entry is `v0.2.1`; no `v1.0.0` stability entry. |
| 7 | `docs/release-checklist.md` exists | ✅ 96-line checklist exists. Needs one line added for L7 deferral. |
| 8 | 2+ consumer repos running `@v0.x.x` for 1+ week | ✅ 9 repos running `@v0.6.0` (drift scanner only) for 4+ days at time of spec authoring, expected to be 6-7 days by PR merge. |
| 9 | `v1.0.0` and `cli/v1.0.0` tags both exist | **gap** — no v1.0 tags on either track. |

## Non-Goals (explicitly out of scope for this PR)

- **L7 fixture repo + reset script**: `yakkuro/gh-manage-test-fixture` and `scripts/reset-fixture.sh` will NOT be created in this PR. The 9-repo Phase C production rollout (zero HIGH/CRITICAL findings over 4+ days of drift scanning) is treated as sufficient end-to-end validation for v1.0. The deferral is documented with a single line added to `docs/release-checklist.md`. If L7 infrastructure becomes necessary in v1.1+, a GitHub Issue will be opened at that time.
- **Production-code changes beyond the L6 test**: `src/gh_manage/` modules will not be modified. Coverage of L4 at 94% (target 85%) and L5 at 93% (target 90%) is already sufficient; the weaker spots (`protection_sync.py` 92%, `commands/init.py` 87%, `commands/apply.py` 88%) are all above the L4 target and do not require backfill.
- **Reusable workflow functional changes**: no modifications to `reusable-pr-gate-python.yml`, `reusable-pr-gate-typescript.yml`, or `actions/**`. The v1.0.0 tag on the reusable track is a pure stability promise, not a feature release.
- **PyPI publishing**: the CLI will continue to be distributed only via `uv tool install git+...@cli/vX.Y.Z`. PyPI publishing remains deferred per the top-level design spec.
- **Additional consumer rollouts**: no new repos added to `src/gh_manage/data/repos.yml`. The 9 currently tracked are sufficient for v1.0 validation.

## In Scope

### 1. L6 bundled templates golden test

Add a single new test function to `tests/unit/profile_sync/test_golden.py`:

```python
def test_bundled_python_service_package_data_resolves_and_applies(
    tmp_path: Path,
) -> None:
    """L6 golden test per Phase 0 design spec.

    Unique value: proves package-data resolution works for wheel installs.
    The byte-compare is a side effect of profile_sync's raw-copy invariant,
    which is already covered by Phase 6 fixture tests. If a future PR adds
    placeholder substitution, this test and Phase 6 fixture tests will fail
    together — that is the intended failure mode.
    """
```

The test resolves `gh_manage.data.profiles["python-service.yml"]` and `gh_manage.data.templates` via `importlib.resources.files`, loads the profile, runs `compute_files_diff` + `apply_files_diff` against `tmp_path`, and byte-compares each written file against its bundled source. Exactly 2 creates (`ci/python-ci.yml` → `.github/workflows/ci.yml`, `claude-md/default.md` → `CLAUDE.md`), zero overwrites, zero skips.

**Why this test matters**: it is NOT a tautology of `profile_sync.py`'s raw-byte-copy design. Its unique value is verifying that `importlib.resources` correctly resolves package data from a wheel-installed gh-manage (the existing Phase 6 fixture tests use filesystem paths under `tests/fixtures/profile_sync/`, which does not exercise wheel-install package-data resolution). This complements the `docs/release-checklist.md` post-release smoke test for `labels.yml` resolution with equivalent coverage for the `templates/` directory.

**TDD flow**:
1. Red: add the test → expect PASS on first run (the invariant already holds for bundled templates)
2. Red verification: temporarily modify `profile_sync._safe_write` to prepend `b"X"` → confirm FAIL → revert
3. Green: final PASS

### 2. Documentation — 5 files (lightweight tour style)

All 5 files target the "lightweight tour" depth: each file is 80-200 lines, assumes the reader is an external yakkuro org member (or the maintainer 6 months from now), and uses deep links to the design spec / CHANGELOGs / release checklist for readers who need more depth.

#### 2.1 `README.md` (replace existing 23-line stub, target ~100 lines)

Target reader: someone who just landed on `https://github.com/yakkuro/gh-manage` and needs to know what it is and where to go next within 2 minutes.

Sections:
1. **What is gh-manage** — 3-4 sentences. Single-org GitHub CI/CD + operational policy distribution system.
2. **Features** — bullet list: reusable PR gates (Python + TypeScript), CLI extension (labels/init/apply/protection/drift), drift scanner with GitHub Issue reporting, composable profiles.
3. **Quick example** — one consumer `.github/workflows/ci.yml` (minimal), one `uv tool install` command, one `gh-manage` invocation.
4. **Getting started** — single link to `docs/quick-start.md`.
5. **Documentation** — table of links to architecture, versioning, distribution-channels, release-checklist, consumers, design spec.
6. **Status** — v1.0.0 = stable. Next breaking change is v2.0.
7. **License** — MIT (preserve existing line).

#### 2.2 `docs/architecture.md` (new, target ~200 lines)

Target reader: contributor or maintainer who needs to understand the 3-track deliverable model and the CLI's 3-layer pattern without diving into code.

Sections:
1. **Overview** — 3-4 sentences. gh-manage has 3 independent deliverable tracks.
2. **Three tracks diagram** — single mermaid diagram showing Reusable Workflows / Python CLI / Bundled data.
3. **Track 1: Reusable workflows** — what they are, self-checkout pattern, `gh-manage-ref` input rationale, pinned tool versions, smoke-test.yml role.
4. **Track 2: Python CLI layers** — 3-layer diagram (commands → engine pure functions → github_api wrappers), 2 load-bearing constraints ("all gh api calls go through `github_client.py`", "domain engine modules know nothing about subprocess/git/GitHub"), one-line inventory of `labels_sync`, `profile_sync`, `protection_sync`, `drift_sync`.
5. **Track 3: Bundled data** — `src/gh_manage/data/` layout, `importlib.resources` resolution, the "profile points at templates" pattern.
6. **Testing layers L1-L7** — table from the design spec (L1 shell 80%, L4 CLI 85%, L5 drift 90%, L6 templates 100%, L7 manual).
7. **What is NOT in gh-manage** — bullets from the design spec's Non-Goals (Claude runtime, cross-repo dashboard, release management for other repos, Dependabot distribution, PyPI publishing, `act`/nektos, GitHub Enterprise).
8. **Reference** — link to design spec.

#### 2.3 `docs/quick-start.md` (new, target ~150 lines)

Target reader: yakkuro org member who wants to get gh-manage working on their repo in 15 minutes.

Sections: 7 sequential numbered steps (Install CLI → Bootstrap with `gh-manage init` → Apply labels → Apply protection → Add CI workflow → Verify drift → Enroll in weekly drift scan) + troubleshooting subsection covering 3 common errors ("Branch not protected", "Permission denied", `gh-manage-ref` mismatch) + "Next steps" link to `docs/usage/`.

#### 2.4 `docs/versioning.md` (new, target ~150 lines)

Target reader: consumer deciding which tag to pin to, or wondering when the next breaking change will land.

Sections:
1. **Overview** — 3-4 sentences. Two independent release tracks with independent semver.
2. **Two tag tracks** — table comparing `vX.Y.Z` (reusable) vs `cli/vX.Y.Z` (CLI): format, example, contents.
3. **Why two tracks** — 2-3 paragraphs. Concrete example: CLI went v0.3 → v0.6 while reusable stayed at v0.2.1.
4. **Semver policy** — bullets for MAJOR/MINOR/PATCH with one example each.
5. **Stability promise starting v1.0.0** — 4 bullets: reusable workflow input surface frozen, CLI subcommand + flag names frozen, bundled data schemas frozen, internal module APIs NOT stable.
6. **Pinning recommendations** — 3 patterns: production exact pin, development `@main`, floating `@v1` tag (not currently provided, noted as v2+ consideration).
7. **Breaking change protocol** — 1 paragraph. Pre-discussion issue → `[Unreleased]` `**BREAKING**` marker → minimum one minor with deprecation → v2.0 removal.
8. **Reference** — links to both CHANGELOGs.

#### 2.5 `docs/distribution-channels.md` (new, target ~120 lines)

Target reader: consumer asking "how do I install this?", maintainer questioning whether to publish to PyPI.

Sections:
1. **Overview** — 2-3 sentences. Two deliverables, two distribution channels.
2. **Channels table** — 4 columns: What / Where / How consumer uses / Why this channel. Three rows: Reusable workflows (Git tags, `uses:`), Python CLI (Git tags, `uv tool install git+...`), Bundled data (inside CLI wheel, `importlib.resources`).
3. **Why NOT PyPI** — 4 bullets: internal tool, semver 1:1 with git tags, avoided release-workflow complexity, `uv tool install git+` is simple enough.
4. **Why NOT Homebrew / GitHub Releases binary** — 1-2 bullets: single OS target, uv handles dependencies.
5. **Future distribution channels** — 1 paragraph. Conditional on external adoption growth; none planned at v1.0.
6. **Install verification** — `gh-manage --version` as the trusted check.
7. **Reference** — links to `release-checklist.md` and `versioning.md`.

### 3. `CHANGELOG-cli.md` — 4 new entries in `[Unreleased]`

Each entry targets ~18 lines (half of the existing `0.2.0` entry's 34 lines). Template structure per entry:

```
## [X.Y.Z] - <date-of-merged-PR>

<1-3 sentence summary of what this Phase enabled.>
Phase N milestone. Shipped in PR #<N>. Plan: <link>, Spec: <link>.

### Added
- <3-5 bullet points for the most important new modules / subcommands>

### Changed (if applicable)
- <1-3 bullets for non-breaking behavior changes>

### Known limitations
- <2-3 bullets for representative gaps / deferred items>
```

Sourcing content:
- Merged PR body via `gh pr view <N> --json body`
- `docs/plans/2026-04-XX-phase-N-*.md` AC section
- `git log` for the merged commit's patch summary
- `docs/specs/2026-04-XX-phase-N-*.md` design decisions

Four entries to add (in reverse chronological order within `[Unreleased]`):

| Entry | Phase | Source plan path | Primary modules |
|---|---|---|---|
| `[0.6.0] - 2026-04-12` | Phase 8.5 drift automation | `docs/plans/2026-04-12-phase-8.5-drift-automation.md` | `drift_sync.py` (issue mode), `github_api/issues.py`, `models/repos.py`, `data/repos.yml`, `drift-scanner.yml` workflow |
| `[0.5.0] - 2026-04-11` | Phase 8 drift scanner | `docs/plans/2026-04-11-phase-8-drift.md` | `drift_sync.py` (3 checks + stdout/json/md reports), `commands/drift.py` |
| `[0.4.0] - 2026-04-11` | Phase 7 branch protection | `docs/plans/2026-04-11-phase-7-protection.md` | `protection_sync.py`, `commands/protection.py`, `models/branch_protection.py`, `github_api/protection.py`, `data/branch-protection.yml` |
| `[0.3.0] - 2026-04-11` | Phase 6 init + apply | `docs/plans/2026-04-11-phase-6-init-apply.md` | `profile_sync.py`, `commands/init.py`, `commands/apply.py`, `git_cli.py`, `models/profiles.py`, `data/profiles/python-service.yml`, `data/templates/` |

Total addition: **~72 lines** in `CHANGELOG-cli.md`.

### 4. `CHANGELOG-reusable.md` — 1 new entry in `[Unreleased]`

Single `v1.0.0` entry describing a stability promise, not functional changes. Structure (from brainstorming Q6 Option C):

- **Lead paragraph**: "Stable API milestone. No functional changes since v0.2.1." Explain that the reusable workflows and composite actions have been unchanged since v0.2.1 (2026-04-10), have been validated across 9 consumer repositories over 4+ days of production use, and that v1.0.0 makes the input surface a load-bearing contract.
- **"What is contract-stable starting v1.0.0"**: enumerate 4 guaranteed surfaces:
  - Inputs on both reusable workflows
  - Composite action names and their `inputs.*` fields (7 composite actions)
  - Required `gh-manage-ref` input semantics
  - Pinned tool versions (uv 0.5.0, ruff 0.8.0, mypy 1.12.0, pnpm 10.33.0, typescript 6.0.2)
- **"What is NOT stable (internal)"**: 3 bullets clarifying that `tests/fixtures/projects/**`, `.github/workflows/smoke-test.yml`, and composite action internal step implementations can change freely.
- **"v0.x lessons rolled into v1.0"**: 3 recap bullets for v0.2.0 (TypeScript track added, latent parser bug), v0.2.1 (CRITICAL `github.workflow_ref` fix), and the 2026-04-10 visibility flip to public.
- **"Known limitations (carried forward from v0.2.1)"**: pnpm only, eslint pinning recommendation-only, Node 20+, no `cache: pnpm`, non-root `working-directory` shallow-tested, no version skew detection, pinned tool versions may lag upstream.
- **Reference**: design spec, `docs/distribution-channels.md`, `docs/versioning.md`.

Total addition: **~55 lines** in `CHANGELOG-reusable.md`.

### 5. `docs/consumers.md` — Phase C section

The existing llm-kb narrative (77 lines) is preserved unchanged. After it, add a new section:

- Heading: `## Phase C — drift-scanner bulk rollout (2026-04-13)`
- Introductory paragraph explaining that the `repos.yml` expanded from 1 to 9 repos as production-scale validation of the weekly cron workflow, and that all 8 additions were zero-touch adoptions (drift scanner only, PR gates not yet adopted).
- Markdown table with 4 columns (Repo, Adopted, Profile, Domain) and 9 rows (including gh-manage self-hosted dogfood, and llm-kb with a "already documented above" note).
- "What Phase C validated" subsection — 3 bullets covering the `--all` flag, `--report-mode issue`, and the GitHub Pro upgrade.
- "Discoveries" subsection — a single paragraph noting "none to report at v1.0.0, the scanner has run N cron invocations over M+ days with zero HIGH/CRITICAL findings" (N and M to be filled in from actual workflow run data at implementation time).
- Existing "Adding your repo" section preserved unchanged.

Total addition: **~45 lines** in `docs/consumers.md`.

### 6. `docs/release-checklist.md` — 1 line addition

Add a single line under the "Post-release smoke test" section (or equivalent) noting that for v1.0.0, the L7 manual integration test (10 steps against `yakkuro/gh-manage-test-fixture`) was deferred in favor of the 9-repo Phase C production dogfood run (4+ days, zero HIGH/CRITICAL findings). Future issues that demand L7 infrastructure will be opened as GitHub Issues at that time.

## Implementation-Time Placeholders

The spec contains several intentional placeholders that must be resolved during the implementation plan phase (not during the spec phase). Listed here so the plan author can fill them in one pass.

| Placeholder | Where | How to resolve |
|---|---|---|
| `PR #<N>` in `CHANGELOG-cli.md` entries (×4) | Section 3 template | `gh pr list --state merged --search "Phase 6|Phase 7|Phase 8|Phase 8.5" --json number,title,mergedAt --limit 50` and match by phase name |
| `<date-of-merged-PR>` in `CHANGELOG-cli.md` entries (×4) | Section 3 template | Same `gh pr list` command, use `mergedAt` field, format as `YYYY-MM-DD` |
| `N cron invocations over M+ days` in `docs/consumers.md` Phase C discoveries paragraph | Section 5 | `gh run list --workflow=drift-scanner.yml --json createdAt,status --limit 50` to count runs; compute M from `createdAt` of the earliest run vs today |
| Spec / plan path links in `CHANGELOG-cli.md` entries (×4) | Section 3 template | Use the existing file paths under `docs/specs/` and `docs/plans/` as listed in the "Four entries to add" table |
| `(domain TBD)` for `nade-nade` and `picshop` in the consumers table | Section 5 | Check each repo's `README.md` or `pyproject.toml description` via `gh repo view yakkuro/<name> --json description` |

None of these placeholders are ambiguous scope: they are all mechanical lookups the plan author performs once with shell commands at plan time.

## Release Mechanics — Two PR Flow (brainstorming Q7 Option B)

### 6.1 Feature PR: `feat/phase-9-v1-hardening`

Branch from `main`. Files changed (11 total plus the spec and plan):

| File | Action | Approx LOC delta |
|---|---|---|
| `README.md` | replace | +80 / -23 |
| `docs/architecture.md` | new | +200 |
| `docs/quick-start.md` | new | +150 |
| `docs/versioning.md` | new | +150 |
| `docs/distribution-channels.md` | new | +120 |
| `docs/consumers.md` | append | +45 |
| `CHANGELOG-cli.md` | append to `[Unreleased]` | +72 |
| `CHANGELOG-reusable.md` | append to `[Unreleased]` | +55 |
| `docs/release-checklist.md` | 1-line note | +1 |
| `tests/unit/profile_sync/test_golden.py` | append 1 test function | +30 |
| `docs/specs/2026-04-14-phase-9-v1-hardening-design.md` | new (this document) | — |
| `docs/plans/2026-04-14-phase-9-v1-hardening.md` | new (writing-plans output) | — |

Total content delta: **~+900 lines** (excluding the spec and plan).

**PR description requirements**: Summary, what changed table, Phase 9 AC mapping table (from this spec), verification commands, explicit Non-Goals list.

**Review protocol**: per `workflow-review.md`, run all 4 reviewers (Codex + `superpowers:code-reviewer` + `pr-review-toolkit:silent-failure-hunter` + `code-reviewer`). Docs-heavy diff: `code-reviewer` should run with `model: sonnet` (diff is ~900 lines, on the upper edge of haiku's sweet spot).

**Verification before marking complete**:
- `uv run pytest` — all 401 tests pass (400 existing + 1 new L6 test)
- `uv run ruff check src/ tests/` — clean
- `uv run mypy src/` — no new errors
- `uv run pytest --cov=src/gh_manage --cov-report=term` — L4/L5 thresholds still met
- Smoke-test.yml CI green (reusable workflow job)
- Manual read-through of the 5 new docs files for dead links and typos

### 6.2 Bump PR: `chore/bump-cli-v1.0.0`

Created immediately after the feature PR merges and CI is green on `main`. Files changed (6 total):

| File | Change |
|---|---|
| `pyproject.toml` | `version = "0.6.0"` → `"1.0.0"` under `[project]` |
| `src/gh_manage/__init__.py` | `__version__ = "0.6.0"` → `"1.0.0"` |
| `tests/test_sanity.py` | `test_package_version_is_defined` assertion updated to `"1.0.0"` |
| `CHANGELOG-cli.md` | Rename `[Unreleased]` section header to `[1.0.0] - 2026-04-14`, add new empty `[Unreleased]` section at the top, update bottom compare-link anchors |
| `CHANGELOG-reusable.md` | Rename `[Unreleased]` section header to `[1.0.0] - 2026-04-14`, add new empty `[Unreleased]` section, update bottom compare-link anchors |
| `uv.lock` | Auto-updated by `uv sync` after pyproject.toml bump |

Total content delta: **~+12 lines** (version bumps are trivial, most change is the CHANGELOG section rename which is just moving a heading).

**Review protocol**: per `release-checklist.md`, bump PRs are single-file-value-change equivalent and qualify for cross-agent review skip per `workflow-review.md`'s skip conditions. Merge directly after CI green.

### 6.3 Release flow (bump PR merge → tags + GitHub releases)

After the bump PR merges and `main` is updated:

```bash
git checkout main && git pull --ff-only
BUMP_SHA=$(git log -1 --format=%H)

git tag v1.0.0     $BUMP_SHA
git tag cli/v1.0.0 $BUMP_SHA
git push origin v1.0.0 cli/v1.0.0

gh release create v1.0.0 \
  --title "v1.0.0 — Reusable Workflows stability milestone" \
  --notes-file /tmp/release-notes-reusable.md

gh release create cli/v1.0.0 \
  --title "cli/v1.0.0 — Python CLI stability milestone" \
  --notes-file /tmp/release-notes-cli.md
```

Release notes are derived from the corresponding CHANGELOG entries. The reusable release notes mirror the new `CHANGELOG-reusable.md` `v1.0.0` entry in full. The CLI release notes summarize the 4 new `CHANGELOG-cli.md` entries (0.3.0 through 0.6.0) plus a 1.0 stability preamble.

Post-release smoke test per `release-checklist.md`:

```bash
uv tool install --force --reinstall git+https://github.com/yakkuro/gh-manage@cli/v1.0.0
gh-manage --version   # must print "gh-manage, version 1.0.0"
cd /tmp && gh-manage labels show gh-manage   # verify labels.yml package-data resolution
```

If `gh-manage --version` prints any other version, STOP and re-run the bump PR before announcing the release.

## Acceptance Criteria

This PR is complete when all of the following are true, verified with the listed commands.

1. **L6 bundled templates coverage 100%**
   - Command: `uv run pytest tests/unit/profile_sync/test_golden.py::test_bundled_python_service_package_data_resolves_and_applies -v`
   - Expected: test passes
   - Command: `uv run pytest --cov=src/gh_manage --cov-report=term`
   - Expected: total coverage ≥ 94% (no regression from baseline)

2. **L4 + L5 coverage thresholds preserved**
   - Command: `uv run pytest --cov=src/gh_manage --cov-report=term`
   - Expected: `src/gh_manage/` total ≥ 85%, `src/gh_manage/commands/drift.py` line ≥ 90%

3. **All 5 documentation files exist and are internally linked**
   - Command: `ls -la README.md docs/architecture.md docs/quick-start.md docs/versioning.md docs/distribution-channels.md`
   - Expected: all 5 files present, non-empty, and within 80-250 LOC each
   - Verification: manual read-through — each of the 5 files contains at least 2 relative-path markdown links (`](../...md)`, `](./...md)`, or similar) pointing at other files within `yakkuro/gh-manage` (not external URLs). A grep is insufficient because it cannot distinguish relative-path doc links from external URLs like `https://example.com/foo.md`.

4. **`CHANGELOG-cli.md` has 4 new entries**
   - Command: `grep -c '^## \[0\.[3-6]\.0\]' CHANGELOG-cli.md`
   - Expected: `4` (the `[0.3.0]`, `[0.4.0]`, `[0.5.0]`, `[0.6.0]` headings exist)

5. **`CHANGELOG-reusable.md` has 1 new v1.0.0 entry**
   - In the feature PR: the `[Unreleased]` section contains the v1.0.0 content
   - After the bump PR merges: `grep -c '^## \[1\.0\.0\]' CHANGELOG-reusable.md` returns `1`

6. **`docs/consumers.md` has the Phase C section covering all 9 repos in `repos.yml`**
   - Command: `grep -c '^## Phase C' docs/consumers.md`
   - Expected: `1`
   - Verification: the Phase C markdown table has exactly 9 rows, one for each repo currently listed in `src/gh_manage/data/repos.yml`. The 9 rows are: `yakkuro/gh-manage` (self-hosted dogfood), `yakkuro/slack-agents`, `yakkuro/llm-kb` (with "already documented above" note linking back to the detailed Phase 3 narrative), `yakkuro/rtvc-bench`, `yakkuro/scenario-engine`, `yakkuro/tts`, `yakkuro/vox-speak`, `yakkuro/nade-nade`, `yakkuro/picshop`. This matches the output of `awk '$1 == "-" && /name:/ {print $3}' src/gh_manage/data/repos.yml | sort` (9 entries).

7. **`docs/release-checklist.md` has the L7 deferral note**
   - Command: `grep -c 'Phase C production' docs/release-checklist.md`
   - Expected: `≥ 1`

8. **Feature PR CI all green**
   - GitHub Actions: `ci.yml` + `smoke-test.yml` + any drift-scanner runs triggered by the PR
   - Expected: all green, including the 4-reviewer cross-agent review

9. **Bump PR exists, merges cleanly, and `gh-manage --version` reports 1.0.0**
   - Command (after bump PR merges): `uv tool install --force --reinstall git+https://github.com/yakkuro/gh-manage@cli/v1.0.0 && gh-manage --version`
   - Expected: `gh-manage, version 1.0.0`

10. **Both v1.0.0 tags exist on `main` bump commit**
    - Command: `git tag -l 'v1.0.0' 'cli/v1.0.0' && git log -1 v1.0.0 --format=%H && git log -1 cli/v1.0.0 --format=%H`
    - Expected: both tags print, same SHA

11. **Both GitHub releases are published (not draft)**
    - Command: `gh release list --limit 5`
    - Expected: `v1.0.0` and `cli/v1.0.0` both appear, neither marked draft

12. **Post-release package-data smoke test passes**
    - Commands (after tag push + release create):
      ```
      uv tool install --force --reinstall git+https://github.com/yakkuro/gh-manage@cli/v1.0.0
      gh-manage --version
      cd /tmp && gh-manage labels show gh-manage
      ```
    - Expected: `--version` prints `1.0.0`, `labels show` lists the expected labels (14 labels as of v0.2.0)

## Reference

- Top-level design spec: [`docs/specs/2026-04-10-gh-manage-design.md`](./2026-04-10-gh-manage-design.md)
- Release checklist: [`docs/release-checklist.md`](../release-checklist.md)
- Existing CHANGELOG-cli: [`CHANGELOG-cli.md`](../../CHANGELOG-cli.md)
- Existing CHANGELOG-reusable: [`CHANGELOG-reusable.md`](../../CHANGELOG-reusable.md)
- Existing consumers doc: [`docs/consumers.md`](../consumers.md)
- Phase 8.5 spec (immediate predecessor): [`docs/specs/2026-04-12-phase-8.5-drift-automation-design.md`](./2026-04-12-phase-8.5-drift-automation-design.md)
- Global rules: `~/.claude/rules/workflow-review.md` (4-reviewer protocol), `~/.claude/rules/spec-driven.md` (spec template requirements)
