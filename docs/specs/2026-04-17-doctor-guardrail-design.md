# `gh-manage doctor` — Consumer-Shape Guardrail Design

- **Date**: 2026-04-17
- **Size**: Medium
- **Sizing Rationale**: 3+ modules touched (new `doctor/` package, `commands/doctor.py`, `commands/init.py`, `drift/doctor_bridge.py`, tests), non-trivial design judgments (bridge pattern, severity model, enforcement policy). Not Large — single coherent subsystem, no cross-module orchestration beyond registry wiring.
- **Target**: `yakkuro/gh-manage`
- **Goal**: Add a pre-flight check surface (`gh-manage doctor`) that detects consumer-repo `ci.yml` shape mismatches before they block merges. Eliminate the class of breakage seen in the v1.1.0 rollout (3/11 repos required admin merge because `jobs.<id>` + missing `name:` produced a status context the branch protection didn't recognise).

## Background

On 2026-04-17, v1.1.0 of the reusable workflows rolled out across 11 consumer repos. Three needed `gh pr merge --admin` because their `.github/workflows/ci.yml` used job ids and/or missing `name:` attributes that produced a status context not matching what branch protection required:

| Repo | Job id | `name:` | Produced context | Required context |
|---|---|---|---|---|
| tg-commander | `test` | (missing) | `test / PR Gate` | `PR Gate / PR Gate` |
| repo-init | `call-pr-gate` | (missing) | `call-pr-gate / PR Gate` | `PR Gate / PR Gate` |
| deep-research | `pr-gate` | (missing) | `pr-gate / PR Gate` | `PR Gate / PR Gate` |

See follow-up issue #46. The mismatch is pre-existing, not caused by v1.1.0, but every future bump PR hits the same wall until we detect and prevent it.

This spec focuses on **Theme B (guardrails)** from the 2026-04-17 roadmap review, plus load-bearing portions of **Theme A (internal hygiene)** — specifically subprocess stderr capture so doctor produces actionable error messages.

## Goals

1. Detect consumer `ci.yml` / branch-protection shape mismatches before they block merges.
2. Make fresh `gh-manage init` runs produce repos that pass the checks by default.
3. Surface findings both on-demand (CLI) and on schedule (drift scanner), without adding a new PR-blocking gate.
4. Ship the framework + an initial set of 3 checks; new checks are single-function additions.

## Non-goals

- Repairing the 3 known broken repos (tracked in #46 as a separate rollout).
- Auto-fix (`--fix`). Diagnose-only for this spec.
- Drift scanner cron health, PAT scope, parallelisation (Theme A / D — #47, #50).
- Splitting `drift_sync.py` or `protection_sync.py` further than required for the `Finding` extraction in §1. The rest stays in #47.
- Implementing `gh-manage apply --strict`. `apply` adds warnings only.
- Additional checks beyond the initial α set (metachar detection, prompt-injection linter, pin-drift). Tracked in #48's checklist.

## §1 — Architecture

```
                         ┌─────────────┐
                         │  Finding    │ (shared dataclass)
                         │  Severity   │
                         └──────┬──────┘
                                │
                  ┌─────────────┴─────────────┐
                  │  doctor/checks.py         │ individual check functions
                  │  doctor/registry.py       │ @register_check
                  │  doctor/report.py         │ stdout / json / markdown
                  └──────┬──────────┬─────────┘
                         │          │
          ┌──────────────┘          └────────────────┐
          ▼                                          ▼
┌─────────────────────┐                    ┌─────────────────────────┐
│ commands/doctor.py  │                    │ drift/doctor_bridge.py  │
│ CLI `gh-manage      │                    │ registers drift "shape" │
│ doctor …`           │                    │ check that calls doctor │
└─────────────────────┘                    └─────────────────────────┘
          ▲                                          ▲
          │                                          │
     (on-demand)                              (weekly cron)

          ┌──────────────── separate enforcement path ──────────────┐
          ▼                                                         ▼
┌─────────────────────┐                              ┌─────────────────────┐
│ commands/init.py    │                              │ commands/apply.py   │
│ runs doctor after   │                              │ runs doctor, emits  │
│ copy; criticals     │                              │ warnings; does NOT  │
│ abort + rollback    │                              │ block               │
└─────────────────────┘                              └─────────────────────┘
```

### Module layout

- `src/gh_manage/findings.py` — **new**. Extracts `Finding` dataclass + `Severity` enum from `drift/drift_sync.py` so both packages can import. First concrete step of the future drift_sync.py split (#47).
- `src/gh_manage/doctor/__init__.py` — public API (`run_checks`, `run_on_path`, `run_on_remote`).
- `src/gh_manage/doctor/registry.py` — `@register_check(name, severity)` decorator; registry iteration.
- `src/gh_manage/doctor/checks.py` — the three α check functions (§3).
- `src/gh_manage/doctor/context.py` — `CheckContext` dataclass (repo info, parsed ci.yml, profile, protection spec).
- `src/gh_manage/doctor/report.py` — `format_stdout`, `format_json`, `format_markdown`.
- `src/gh_manage/commands/doctor.py` — Click CLI wiring.
- `src/gh_manage/drift/doctor_bridge.py` — registers a `"shape"` check in drift's registry that translates a drift `ScanContext` → doctor `CheckContext` → aggregated `Finding` list.
- Modified: `src/gh_manage/commands/init.py` (post-copy doctor call + rollback), `src/gh_manage/commands/apply.py` (post-apply warning), `src/gh_manage/git_cli.py` (stderr capture in `GitError`).

### Finding sharing

`Finding` dataclass moves to `src/gh_manage/findings.py`. Both `drift/` and `doctor/` import from there. `severity` enum becomes the single source of truth. The existing `drift_sync.py::Finding` alias is kept as a re-export for one release (`cli/v1.2.0`), then removed in `cli/v1.3.0` or during the drift_sync split in #47 (whichever comes first).

## §2 — CLI surface

```
gh-manage doctor <path-or-repo> [OPTIONS]
```

**Positional**: local path (`.`) or `owner/repo`.

**Options**:

| Option | Default | Purpose |
|---|---|---|
| `--profile NAME` | inferred from repos.yml | Validate against this profile |
| `--check NAME` | all registered | Run only named check (repeatable) |
| `--severity LEVEL` | all | Filter findings (critical/high/medium/low) |
| `--report-mode MODE` | stdout | stdout / json / markdown-file |
| `--output PATH` | — | Required for json / markdown-file modes |
| `--exit-zero` | off | Always exit 0 even when findings present |

### Exit code contract

| Condition | Exit |
|---|---|
| No findings | 0 |
| Findings but all below `--severity` filter | 0 |
| Findings include critical or high | 1 |
| Findings but only medium/low | 0 |
| `--exit-zero` set | always 0 (overrides all other rules — precedes `--severity`) |

### Profile inference

Three modes:
- **Path mode (`.` or absolute path)**: read `.git/config` at the path, extract origin's `owner/repo`, look up in bundled `repos.yml`. Use that profile.
- **Remote mode (`owner/repo`)**: look up `owner/repo` directly in bundled `repos.yml`. No git config read.
- **Explicit `--profile NAME`** overrides inference in both modes.

If inference fails (repo not in `repos.yml` and `--profile` omitted): exit with a clear error listing available profiles from `src/gh_manage/data/profiles/` and the canonical `--profile` flag to use. Never guess silently.

### Missing-file behaviour

If `.github/workflows/ci.yml` does not exist at the target path or remote repo, doctor does NOT fail hard. The `shape/reusable-adoption` check fires (medium, per §3) and the other shape checks emit zero findings (nothing to analyse). Exit code stays 0 unless the user also passes `--severity medium` or stricter.

### Remote source fetch

For `owner/repo` invocations: `ci.yml` is fetched via `gh api repos/{repo}/contents/.github/workflows/ci.yml`, protection via `gh api repos/{repo}/branches/main/protection`. Both go through the existing `github_client.py` transport so rate-limit and error handling match the rest of the CLI.

## §3 — Initial α checks

All checks share signature `(ctx: CheckContext) -> list[Finding]` and are registered via decorator.

### check 1: `shape/job-shape-coherence` — severity: critical

Detects cases where a consumer's reusable-pr-gate job produces a status context that branch protection doesn't require.

**Job-matching rule**: a job is considered a "reusable-pr-gate job" iff its `uses:` value matches the regex `yakkuro/gh-manage/\.github/workflows/reusable-pr-gate-(python|typescript)\.yml@.+`. Indirection through another composite / callable workflow is **not** traced. Jobs that invoke local composite actions wrapping the reusable are out of scope — doctor treats them as bespoke and check 2 (`shape/reusable-adoption`) applies instead.

Algorithm:
1. For each job in `ci.yml` matching the rule above:
2. Determine produced context: `f"{job.name or job_id} / PR Gate"`
3. If produced context not in `protection.required_status_checks.contexts`, emit finding.
4. Remediation text proposes either renaming the job or updating protection.

Detects all 3 of tg-commander, repo-init, deep-research.

### check 2: `shape/reusable-adoption` — severity: medium

Flags repos listed in `repos.yml` but not actually using a `reusable-pr-gate-*.yml`. Catches shelf-brain (postgres service bespoke) and codelens (`make ci` bespoke).

Severity is medium because bespoke is sometimes the right answer — but the repos.yml/ci.yml mismatch should be made explicit, not silent.

Remediation: adopt the reusable workflow, or remove from `repos.yml` with an `excluded: true` annotation (the excluded-marker is a future `repos.yml` schema extension; not in this spec — just mentioned in the remediation text).

### check 3: `shape/required-contexts-match` — severity: high (missing) / medium (extra)

Diffs profile's declared `required_contexts` (from `profiles/python-service.yml`) against the repo's actual branch-protection `required_status_checks.contexts`.

- **Missing** (profile declares, protection lacks): severity high. The profile says "this context is load-bearing" but protection doesn't enforce it. This is a silent gate-bypass.
- **Extra** (protection requires, profile doesn't declare): severity medium. The repo has an undocumented invariant. Not broken, but a doc gap.

## §4 — Drift scanner integration

New file `src/gh_manage/drift/doctor_bridge.py`:

```python
from gh_manage.doctor import run_checks as doctor_run_checks
from gh_manage.doctor.context import CheckContext
from gh_manage.drift.registry import register_check as register_drift_check
from gh_manage.findings import Finding

@register_drift_check("shape")
def drift_check_shape(ctx: ScanContext) -> list[Finding]:
    doctor_ctx = CheckContext.from_scan_context(ctx)
    return doctor_run_checks(doctor_ctx)
```

This follows the existing drift registry pattern. `ScanContext` and `CheckContext` share most fields; the `from_scan_context` constructor does the adapter work (parses `ci.yml` content that `ScanContext` holds as bytes, reads profile, reads protection).

**Error propagation**: if a doctor check raises `DoctorCheckError` (e.g., malformed `ci.yml`), the bridge catches it and converts it to a `Finding(severity=medium, check="shape/check-error", message=str(exc))`. It never re-raises into drift's orchestration loop — one misbehaving repo should not abort the scan of the other 21. Bugs (non-`DoctorCheckError` exceptions) propagate normally and abort the drift scan with a clear traceback.

**Context-adapter regression test**: `tests/unit/drift/test_context_adapter.py` asserts that every field `doctor.CheckContext` consumes is produced by `ScanContext`. If `ScanContext`'s fields drift away, the test fails before the adapter silently breaks.

### Reporting integration

Drift scanner's existing report modes (`stdout`, `json`, `markdown-file`, `issue`) all work unchanged — shape findings are just additional entries in the `list[Finding]`. No changes to drift's report formatters beyond accepting the new `shape/*` check-name prefix in their severity-bucketing logic.

### Performance

Each shape check on a single repo adds one `ci.yml` fetch + one `branches/main/protection` fetch. `--all` with 22 repos adds 44 API calls. Since drift scanner already fetches protection for its existing `protection` check, the `ScanContext` caches the protection response so doctor doesn't re-fetch. `ci.yml` is new work: 22 GET requests, ~5 seconds over GitHub's rate limit.

### Cron health and rate limiting

Out of scope. This spec only adds a check. The cron is 4-days stale as of writing (#47/#50) and that's tracked separately. If the scan's new `ci.yml` fetches push the run past GitHub's rate limit, the scanner emits a single `shape/rate-limit-hit` finding (medium severity, one per scan) and continues with partial results rather than aborting. Proper backoff and chunking strategy is tracked in #47.

## §5 — `init` hardening

Three changes to `init`:

### A. Bundled-template shape test (test-time)

New `tests/unit/data/test_template_shapes.py`:

```python
def test_bundled_ci_templates_pass_shape_check():
    for tmpl_path in list_bundled_templates():
        parsed = parse_ci_yml_bytes(read_template(tmpl_path))
        findings = run_doctor_on_parsed(parsed, expected_profile=infer_profile(tmpl_path))
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert not critical, f"{tmpl_path}: {critical}"
```

If a template is edited to produce a broken shape, the test fails before the template ships.

### B. Post-copy doctor run (run-time)

`commands/init.py`:

```python
copied = copy_profile_files(...)
findings = run_doctor(target_path, profile=profile_name)
critical = [f for f in findings if f.severity == Severity.CRITICAL]
if critical:
    rollback_copied_files(copied)
    raise ClickException(format_findings(critical, header="init aborted"))
```

**Rollback semantics**:
- `copy_profile_files` returns `list[tuple[Path, PathState]]` where `PathState` is `CREATED` (file did not exist before) or `OVERWROTE` (file existed; original content saved in a tempdir under `$target/.gh-manage-init-backup-<timestamp>/`).
- On rollback: `CREATED` paths are `os.unlink`'d; `OVERWROTE` paths are restored from the backup tempdir; the backup tempdir is removed last.
- Parent directories created during copy are left in place (git ignores empty dirs; cleaning them risks racing with user's concurrent activity).
- Rollback is best-effort: if a restore fails (disk full, permission, etc.), init raises with both the original doctor-finding and the rollback error, surfacing both so the user knows manual cleanup may be needed.

### C. Template-source comments

`src/gh_manage/data/templates/ci/python-ci.yml` gets a header comment:

```yaml
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
    name: "PR Gate"
    uses: ...
```

Same comment will apply to any future `typescript-ci.yml` template when ts-service profile is added — not in this spec.

### Enforcement scope

- `init`: critical findings abort + rollback.
- `apply`: critical and high findings print warnings to stderr (not stdout, so structured tools piping `apply` output are unaffected); do not block. Reserves space for a future `--strict` flag.
- `drift` / `doctor`: report only. No enforcement.

## §6 — Testing and acceptance

### Test layout

- **Unit** (mocked):
  - `tests/unit/doctor/test_checks.py` — each check with a hand-built `CheckContext`.
  - `tests/unit/doctor/test_registry.py` — registration and iteration.
  - `tests/unit/doctor/test_report.py` — stdout, json, markdown formatters.
- **Integration** (gh API mocked):
  - `tests/unit/commands/test_doctor_cli.py` — option parsing, exit codes, `--check` filtering.
  - `tests/unit/commands/test_init.py` extensions — post-copy doctor + rollback.
  - `tests/unit/drift/test_doctor_bridge.py` — bridge calls doctor correctly from a ScanContext.
- **Fixture-based regression**:
  - `tests/fixtures/broken_consumers/` with the 3 today-broken repos' `ci.yml` + `protection.json` + `expected_findings.json`. The test does `run_doctor(fixture) == expected_findings`. Promotes #46's root cause into permanent regression coverage.
- **Smoke** (workflow):
  - New `.github/workflows/doctor-smoke.yml` runs doctor against bundled templates + self-dogfood. Green on `gh-manage` itself proves no self-inflicted shape drift.

### Acceptance criteria (verification commands)

| # | Check | Command | Expected |
|---|---|---|---|
| 1 | Self-dogfood | `gh-manage doctor .` | 0 critical / 0 high |
| 2 | Broken repo — tg-commander | `gh-manage doctor yakkuro/tg-commander --report-mode json` | Contains `shape/job-shape-coherence` critical |
| 3 | Broken repo — repo-init | `gh-manage doctor yakkuro/repo-init --report-mode json` | Contains `shape/job-shape-coherence` critical |
| 4 | Broken repo — deep-research | `gh-manage doctor yakkuro/deep-research --report-mode json` | Contains `shape/job-shape-coherence` critical |
| 5 | Drift integration | `gh-manage drift . --check shape` | shape check runs, drift-formatted output |
| 6 | Init hardening | `gh-manage init /tmp/test-repo --profile python-service && gh-manage doctor /tmp/test-repo` | 0 critical / 0 high |
| 7 | Template validity | `uv run pytest tests/unit/data/test_template_shapes.py -v` | Pass |
| 8 | Broken-consumer regression | `uv run pytest tests/unit/doctor/test_broken_consumer_fixtures.py -v` | Pass |

### PR review process (outside implementation scope)

- Four-reviewer protocol (Codex + superpowers:code-reviewer + silent-failure-hunter + code-reviewer) required before merge, per `claude-dotfiles/rules/workflow-review.md`. This is a PR-gate concern, not an implementation acceptance criterion — it lives here as a reminder, not a test that the implementer writes.

### Release version

- **CLI track**: `cli/v1.2.0` (feature-level addition: new `doctor` subcommand).
- **Reusable track**: unchanged at v1.1.0.
- **Bundled data**: template comment additions ride `cli/v1.2.0`.
