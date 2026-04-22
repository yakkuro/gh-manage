# Theme B Guardrails — Prevention Layer Design (cli/v1.10.0)

- **Date**: 2026-04-22
- **Size**: Medium
- **Sizing Rationale**: Two pre-apply doctor integrations (init, apply), one new semantic-filter module, one new unit-test file for template invariance, plus minor registry/decorator augmentation on `doctor/checks.py`. Estimated ~150 LOC production, ~250 LOC tests, ~5 files modified + 3 new files. Not Small because it changes the exit-code contract of `init --apply` and `apply --apply` (new blocking gate), which is user-visible and requires release-notes coordination. Not Large because no schema migration, no reusable-workflow change, and the doctor framework from PR #53 is reused as-is.
- **Target**: `yakkuro/gh-manage`
- **Goal**: Close the #46-class admin-merge gap by installing a pre-apply guardrail in `init` and `apply` that refuses to mutate repository state when the planned change would leave blocking-severity doctor findings unresolved. This is the "Prevention" half of roadmap Theme B (#48). The "Detection/Security" half (workflow YAML prompt-injection linter, Theme B item 3) is deferred to cli/v1.11 — see Non-Goals.

## Background

PR #53 (cli/v1.3.0) landed the `gh-manage doctor` framework with three `shape/*` checks:

- `shape/job-shape-coherence` (critical) — produced status context must equal protection's required context
- `shape/reusable-adoption` (medium) — repos.yml-listed repos must use a reusable-pr-gate workflow
- `shape/required-contexts-match` (high / medium) — profile's declared `required_contexts` must match live protection

In the v1.1.0 consumer rollout (2026-04-17, tracked in #46), three of eleven bump PRs required `admin-merge` because the consumer ci.yml shape pre-dated the canonical `jobs.pr-gate: { name: "PR Gate" }` convention. The doctor framework was introduced to *detect* that class of mismatch. It detects but does not *prevent*: a user can still run `gh-manage apply --also-protection` against a repo whose shape is mismatched and end up with branch protection that references a status context the ci.yml will never produce.

Phase 10 closeout (#27, closed 2026-04-22) surfaced the same class of issue: 8 pre-existing repos (slack-agents, llm-kb, rtvc-bench, scenario-engine, tts, vox-speak, nade-nade, picshop) sit in `repos.yml` with `profile: python-service` declared but have never adopted the reusable workflow. They emit 8 HIGH findings from `shape/required-contexts-match` on every drift scan. The findings are correct — the repos *are* mis-declared — but the drift scanner is a detector, not a preventer, so the mismatch persisted unremediated for months.

### Brainstorming decisions (2026-04-22)

User intent: build the minimum prevention layer that would have blocked the #46 incident at source without adding YAGNI scope. Explicit decisions during brainstorming:

- Q1 (Bundle scope) → **Bundle 1**: init template hardening + apply precondition checks. Workflow prompt-injection linter and drift-only profile are separate tracks.
- Q2 (Within Bundle 1) → **(a)+(b)+(d)**: upgrade apply's post-apply doctor to block, add pre-apply doctor to apply, add template-invariance unit test. Skip (c) init pre-apply because the fresh-repo ROI is low.
- Q3 (Block severity) → **Option B**: critical + high, with `--allow-blocking` override. Critical-only would miss the #46 high-severity class.
- Q4 (First-time adoption) → **Option 1**: semantic filter — exclude findings that this apply invocation is about to resolve. Avoids blocking legitimate first-time `apply --also-protection`.
- Q5 (init / apply unification) → **Option α**: both commands run pre-apply doctor, same severity threshold, same override flag. `init`'s existing post-apply CRITICAL rollback is retired in favor of pre-apply block. Post-apply doctor remains as a warning-only sanity check.
- Q6-1 (override flag name) → `--allow-blocking` (explicit, doesn't collide with existing `--force` / `--downgrade-allowed`).
- Q6-2 (template test scope) → 3 assertions × 2 templates (python-ci, ts-ci): YAML-parseable, `jobs.pr-gate.name == "PR Gate"`, `uses:` matches reusable-pr-gate-<lang> regex.
- Q6-3 (release boundary) → CLI-only, `cli/v1.10.0`. No reusable workflow YAML change.

## Goals

1. **Pre-apply guardrail**: `init --apply` and `apply --apply` run the doctor framework before any mutation; critical/high findings that will not be resolved by this invocation cause a `ClickException` with zero side-effects.
2. **Semantic filter correctness**: first-time adoption (`apply --also-protection` on a repo with empty protection) does NOT block — the filter recognizes that the upcoming apply will install the missing contexts.
3. **UX consistency**: init, apply, and doctor standalone all treat critical+high as blocking, all have a single-flag override (`--allow-blocking` for init/apply, `--exit-zero` for doctor is the existing semantically-equivalent escape hatch).
4. **Template invariance gate**: bundled ci.yml templates are regression-tested on every CI run — a PR that accidentally breaks the canonical `jobs.pr-gate: { name: "PR Gate" }` shape fails CI before merging.
5. **No silent behavior change for drift scanner**: drift_sync findings are not consumed by init/apply's pre-apply doctor. Doctor and drift_sync remain separate registries (as established in PR #53).
6. **Backward-compat for `apply` without `--allow-blocking`**: existing CI pipelines that ran `gh-manage apply --apply` on a clean repo continue to succeed. The new gate only fires when a blocking finding exists that this apply will not resolve.

## Non-Goals

- **Workflow YAML prompt-injection linter (#48 item 3)**. Detection of `${{ github.event.* }}` expressions embedded inside `run:` blocks is a separate spec. The suppress/exception mechanism (allowlist, inline `# gh-manage:allow` comments) needs its own design pass. Tracked as follow-up for cli/v1.11.
- **`drift-only` lightweight profile (#75 Track B Option 1)**. The 8 pre-existing repos' profile mismatch will be resolved operationally in #75 — either by adopting reusable-pr-gate, removing them from `repos.yml`, or introducing a new profile. That selection is out of scope here because it is a repo-list editing decision, not a CLI feature.
- **`drift/*` checks in pre-apply doctor**. `init --apply` and `apply --apply` only consult `shape/*` checks (the doctor registry). `labels` / `protection` / `profile_files` / `template-hash` drift findings from `drift_sync.py` are intentionally not plumbed in. Rationale: those three drift check classes are *handled* by apply (label sync, protection sync, file sync) as a side-effect of running, so including them in pre-apply would create a false block.
- **Apply post-apply rollback mechanism**. `apply` retains its current no-rollback semantics (pre-apply guards, post-apply is warning-only). Adding rollback to `apply` was considered and rejected: it would duplicate `init`'s soon-to-be-deleted rollback code without a concrete incident calling for it. If a post-apply critical/high surfaces in practice, the operator fixes forward.
- **`--doctor-threshold` configurability**. A single critical+high threshold suffices. If operators want "block only on critical", they can pass `--allow-blocking` and review findings manually. Fine-grained threshold would add YAGNI config surface.
- **Reusable workflow YAML changes**. `cli/v1.10.0` is CLI-only. `.github/workflows/reusable-pr-gate-*.yml` is untouched. Consumers that floating-ref on `@main` see no breaking change.
- **Migration action for existing consumers**. After `cli/v1.10.0` is released, existing consumer repos' CI invocations of `gh-manage apply` either (a) still pass if the repo state was already coherent, or (b) fail with a blocking-doctor message directing the operator to run `gh-manage doctor` and fix. No pre-release migration PR fleet is required.

## §1 — Architecture overview

### 1.1 Module-level surface

```
src/gh_manage/
├── doctor/
│   ├── checks.py                        MODIFY  add resolves_with kwarg to @register_check calls
│   ├── registry.py                      MODIFY  expose resolves_with + per-check exception isolation in run_checks
│   ├── semantic_filter.py               NEW     ApplyScope + filter_pre_apply_findings
├── commands/
│   ├── init.py                          MODIFY  pre-apply doctor, delete post-apply rollback
│   ├── apply.py                         MODIFY  pre-apply doctor, --allow-blocking flag
│   └── _shared.py                       MODIFY  add run_pre_apply_doctor helper
tests/
├── unit/
│   ├── doctor/
│   │   ├── test_semantic_filter.py      NEW     all ApplyScope × check combinations
│   │   └── test_registry.py             NEW/EXT per-check exception isolation + resolves_with getter
│   ├── data/
│   │   └── test_ci_templates.py         NEW     canonical shape regression gate
│   └── commands/
│       ├── test_init.py                 MODIFY  replace rollback tests with pre-apply tests
│       └── test_apply.py                MODIFY  add pre-apply tests, --allow-blocking tests
docs/
├── specs/2026-04-22-theme-b-guardrails-prevention-layer-design.md  NEW (this file)
└── versioning.md                        MODIFY  cli/v1.10.0 entry
```

### 1.2 Data flow

```
               ┌─────────────────────────┐
               │  init / apply invoked    │
               └────────────┬────────────┘
                            │
              ┌─────────────▼──────────────┐
              │  1. Compute diffs           │
              │  (files, labels, protection)│
              └─────────────┬──────────────┘
                            │
              ┌─────────────▼──────────────┐
              │  2. PRE-APPLY DOCTOR (new) │
              │  a. doctor.run_on_path()   │
              │  b. ApplyScope from args   │
              │  c. semantic_filter drop   │
              │     findings that this     │
              │     apply will resolve      │
              │  d. if any critical/high   │
              │     remain & not           │
              │     --allow-blocking:      │
              │     raise ClickException   │
              │     (zero side-effects)    │
              └─────────────┬──────────────┘
                            │ pass
              ┌─────────────▼──────────────┐
              │  3. Existing gates          │
              │     (protection downgrade)  │
              └─────────────┬──────────────┘
                            │
              ┌─────────────▼──────────────┐
              │  4. Apply mutations         │
              │  (files → labels → prot.)  │
              └─────────────┬──────────────┘
                            │
              ┌─────────────▼──────────────┐
              │  5. POST-APPLY DOCTOR      │
              │  warning-only (stderr)     │
              │  exit code unchanged       │
              └────────────────────────────┘
```

## §2 — Semantic filter

### 2.1 `ApplyScope`

```python
# src/gh_manage/doctor/semantic_filter.py

from dataclasses import dataclass

@dataclass(frozen=True)
class ApplyScope:
    """The set of repository-state domains that this invocation will mutate.

    A doctor finding is pre-apply-filterable iff every domain in the
    check's `resolves_with` tuple is True in this scope — i.e., this
    apply invocation will (attempt to) resolve the finding as a
    side-effect of running. Findings outside scope remain blocking.

    Frozen to prevent mutation during filter iteration and to enable
    safe sharing if filtering is ever parallelized.

    Domain semantics:
    - sync_files=True: ci.yml and other profile files will be rewritten
      from bundled templates. shape/* checks about ci.yml content are
      resolved by this action.
    - sync_labels=True: label set will be synchronized to labels.yml.
      Label-domain drift checks (drift_sync, not doctor) would be
      resolved by this action — currently no doctor check uses this
      domain but it is reserved for future use.
    - sync_protection=True: branch protection will be synchronized.
      shape/required-contexts-match findings are resolved by this
      action. NOTE: a profile where `protection_policy is None` cannot
      have sync_protection=True because init/apply refuses to touch
      protection in that case — findings from shape/required-contexts-
      match (if any) will NOT be filtered and remain blocking.
    """

    sync_files: bool
    sync_labels: bool
    sync_protection: bool
```

Construction sites:

- `init`: `ApplyScope(sync_files=True, sync_labels=True, sync_protection=(profile.protection_policy is not None))`
  - init always syncs files + labels (unconditional, per init.py Q1 design decision).
  - `sync_protection` is True **only when the profile declares a protection_policy**. A profile without protection_policy means "this profile does not manage branch protection"; findings from protection checks therefore remain blocking and the operator must resolve them before init succeeds (correct behavior — the profile is implicitly asserting it does not fix protection drift).
- `apply`: `ApplyScope(sync_files=True, sync_labels=also_labels, sync_protection=also_protection)`
  - apply always syncs files (per apply.py current behavior).
  - Labels/protection gated on the existing CLI flags. `--also-protection` without `--also-labels` is legal; scope reflects exactly what will be touched.

### 2.2 Check registration

Each `@register_check` decorator gains a `resolves_with` kwarg:

```python
@register_check(
    "shape/job-shape-coherence",
    resolves_with=("sync_files",),
)
def check_job_shape_coherence(ctx): ...

@register_check(
    "shape/reusable-adoption",
    resolves_with=("sync_files",),
)
def check_reusable_adoption(ctx): ...

@register_check(
    "shape/required-contexts-match",
    resolves_with=("sync_protection",),
)
def check_required_contexts_match(ctx): ...
```

The registry (`doctor/registry.py`) stores `resolves_with` alongside the existing `__doctor_check_name__` attribute, and exposes `get_check_resolves_with(name: str) -> tuple[str, ...]` for the filter to consume.

### 2.3 Filter semantics

```python
def filter_pre_apply_findings(
    findings: tuple[Finding, ...],
    scope: ApplyScope,
) -> tuple[Finding, ...]:
    """Drop findings whose resolving-domain tuple is fully covered by scope.

    Conservative: a check without a registered resolves_with tuple is
    NEVER filtered (always blocking). Adding a new check without also
    declaring resolves_with fails closed, not open.
    """
    kept: list[Finding] = []
    scope_map = {
        "sync_files": scope.sync_files,
        "sync_labels": scope.sync_labels,
        "sync_protection": scope.sync_protection,
    }
    for f in findings:
        resolves = get_check_resolves_with(f.check)
        if resolves and all(scope_map[d] for d in resolves):
            continue  # this apply will resolve it — not blocking
        kept.append(f)
    return tuple(kept)
```

### 2.4 Invariants

1. **Conservative default**: `resolves_with=()` (or unset) means the check is never filtered — pre-apply always blocks on it. A new check added without a `resolves_with` kwarg fails CLOSED (blocking), not open.
2. **AND over domains**: a check that declares `resolves_with=("sync_files", "sync_protection")` is only filtered when *both* domains are in scope.
3. **Severity is applied AFTER filtering, not before**: `filter_pre_apply_findings` operates on the `check` name regardless of severity. Pipeline order:

   ```
   findings → filter_pre_apply_findings(filter by check) → blocking = [f for f in filtered if f.severity in ("critical","high")]
   ```

   A low-severity finding from a check with matching `resolves_with` is still filtered, but would not have blocked anyway (low not in blocking set). This is semantically a no-op at the block gate, but matters if a future consumer enumerates `filtered` for non-blocking purposes (e.g., reporting "this apply will resolve N findings").
4. **Skipped checks emit zero findings or a low diagnostic**: if `shape/job-shape-coherence` skips due to unreadable protection, it returns a single `low` diagnostic (`"unreadable"`). That low has `resolves_with=("sync_files",)` but won't block because `low not in ("critical", "high")`.
5. **Per-check exception isolation**: if a check raises `CiYmlParseError` or `DoctorCheckError`, the registry's `run_checks` **does not abort the iteration**. Instead it emits a synthetic LOW finding (`check="shape/check-error:<original_check_name>"`, `resolves_with=<original.resolves_with>`) and continues to the next check. This prevents a single broken ci.yml or malfunctioning check from silently dropping findings from all other checks. See §3.1 and §5.1 for full exception taxonomy.

## §3 — Pre-apply integration in init / apply

### 3.1 Shared helper

```python
# src/gh_manage/commands/_shared.py

def run_pre_apply_doctor(
    target: Path,
    profile_name: str,
    scope: ApplyScope,
    allow_blocking: bool,
) -> None:
    """Block the caller if pre-apply doctor finds unresolved blocking findings.

    Raises click.ClickException on block. Returns None on pass. Emits a
    WARNING log line and stderr message on `allow_blocking=True` even
    when findings exist — the override is loud.

    Exception handling model:
    - Per-check exceptions (CiYmlParseError, DoctorCheckError) are
      caught INSIDE registry.run_checks (see §2.4 invariant 5). The
      failing check contributes a synthetic LOW diagnostic finding;
      other checks' findings are preserved. No special handling
      required in this helper.
    - Setup errors (DoctorError subclasses raised from
      `run_on_path` itself — profile missing, repos.yml corrupt,
      git_cli failure, GitHub API error before any check runs)
      propagate to handle_errors. They are user-actionable and not
      recoverable by proceeding with apply.
    """
    findings = doctor.run_on_path(target, profile_name=profile_name)

    filtered = filter_pre_apply_findings(findings, scope)
    blocking = tuple(f for f in filtered if f.severity in ("critical", "high"))
    log.info(
        "pre-apply doctor: findings=%d filtered=%d blocking=%d allow_blocking=%s",
        len(findings),
        len(findings) - len(filtered),
        len(blocking),
        allow_blocking,
    )
    if not blocking:
        return
    if allow_blocking:
        click.echo(
            f"WARNING: --allow-blocking: proceeding despite {len(blocking)} "
            f"blocking finding(s).",
            err=True,
        )
        return
    raise click.ClickException(
        _format_blocking_message(blocking, target)
    )
```

`_format_blocking_message()` produces the user-facing message described in §3.3.

### 3.1.1 `registry.run_checks` per-check isolation

To support invariant 5 (§2.4), `doctor/registry.py::run_checks` gains per-check exception handling:

```python
# src/gh_manage/doctor/registry.py

def run_checks(ctx: CheckContext) -> tuple[Finding, ...]:
    """Run every registered check, isolating per-check exceptions.

    If a check raises CiYmlParseError or DoctorCheckError, its output
    is replaced with a single synthetic LOW finding
    (check='shape/check-error:<original_name>',
    resolves_with=<original_resolves_with>) and iteration continues.

    Other exception classes (DoctorError subclasses OTHER than the two
    above; GhError, GitError, etc.) are NOT caught here — they
    propagate to run_on_path's caller.
    """
    all_findings: list[Finding] = []
    for fn in _CHECKS:
        check_name = getattr(fn, "__doctor_check_name__", "<unknown>")
        resolves_with = getattr(fn, "__doctor_resolves_with__", ())
        try:
            all_findings.extend(fn(ctx))
        except (CiYmlParseError, DoctorCheckError) as exc:
            all_findings.append(
                Finding(
                    severity="low",
                    check=f"shape/check-error:{check_name}",
                    repo=ctx.repo,
                    field_path=check_name,
                    current_value="check_error",
                    desired_value="check_passes",
                    message=(
                        f"Doctor check {check_name!r} failed to run: {exc}. "
                        f"Other checks continued; pre-apply filter treats "
                        f"this as if {check_name!r} emitted no findings."
                    ),
                    remediation=(
                        f"Fix the underlying cause of the check failure. "
                        f"For ci.yml parse errors, either repair the YAML "
                        f"manually or proceed with apply (which rewrites "
                        f"ci.yml from the profile template)."
                    ),
                )
            )
    return tuple(all_findings)
```

The synthetic finding carries the **original check's** `resolves_with` so the semantic filter handles it consistently: if `shape/job-shape-coherence` raises `CiYmlParseError`, the synthetic diagnostic has `resolves_with=("sync_files",)`, and init/apply with `sync_files=True` filter it out (correct — the broken ci.yml will be overwritten).

### 3.2 Invocation sites

**`init.py`** (pseudo-diff):

```
- # old: post-apply doctor with CRITICAL rollback (30+ LOC)
+ # new: pre-apply doctor (before any side-effect)
+ if apply_flag:
+     scope = ApplyScope(
+         sync_files=True,
+         sync_labels=True,
+         sync_protection=(profile.protection_policy is not None),
+     )
+     run_pre_apply_doctor(
+         target, profile_name=profile_name,
+         scope=scope, allow_blocking=allow_blocking,
+     )

  # existing diff/downgrade/apply logic continues unchanged
  # post-apply doctor: demoted to warning-only (matches apply.py)
```

The current post-apply block (lines 209-255 of init.py) is replaced with the same warning-style post-apply as `apply.py`. Concretely, post-apply for init will emit this format on stderr (identical to apply's existing format):

```
WARNING: post-apply doctor surfaced blocking-severity findings:

  [CRITICAL] shape/job-shape-coherence
    path: .github/workflows/ci.yml:jobs.<id>
    ...full Finding display via doctor.report.format_stdout...

Not failing init — run `gh-manage doctor` to review.
```

Exit code remains 0. If a post-apply CRITICAL appears (which would be unexpected given pre-apply passed), the operator is notified and can re-run `gh-manage doctor` for the full picture. This is informational, not blocking — the pre-apply gate is the enforcement point.

**`apply.py`** (pseudo-diff):

```
+ if apply_flag:
+     scope = ApplyScope(
+         sync_files=True,
+         sync_labels=also_labels,
+         sync_protection=also_protection,
+     )
+     run_pre_apply_doctor(
+         target, profile_name=profile_name,
+         scope=scope, allow_blocking=allow_blocking,
+     )

  # existing logic, including warning-only post-apply, unchanged
```

### 3.3 User-facing block message

```
Pre-apply doctor found blocking-severity finding(s) that this invocation
will not resolve:

  [HIGH] shape/required-contexts-match
    path: branches/*/protection:required_status_checks.contexts[PR Gate / PR Gate]
    Profile 'python-service' declares required context 'PR Gate / PR Gate'
    but branch protection is not enforcing it. PRs can merge without this gate.
    Fix: gh-manage protection sync <owner>/<repo> --profile python-service --apply

To proceed anyway (not recommended), re-run with --allow-blocking.
To see all findings (including non-blocking), run:
    gh-manage doctor <path> --profile <name>
```

The message is constructed from `doctor.report.format_stdout(blocking, repo=...)` reused as-is, with a prefix paragraph and suffix guidance.

### 3.4 Dry-run behavior

When `--apply` is not set (dry-run), pre-apply doctor is NOT invoked. Rationale:

- Dry-run's purpose is to show "what would change". Doctor findings are available via `gh-manage doctor` as a separate introspection tool.
- Running doctor in dry-run doubles the GitHub API cost (live protection lookup) for a preview command.
- The block gate only makes sense for `--apply`; in dry-run there is nothing to block.

Users who want combined preview run `gh-manage doctor <path> --profile <name>` and `gh-manage apply <path> --profile <name> --dry-run` separately. Their outputs are independent.

#### 3.4.1 Flag combination validation

`--allow-blocking` is only meaningful with `--apply` (since dry-run does not invoke the gate). Passing both `--dry-run` and `--allow-blocking`, or passing `--allow-blocking` without any apply flag, should fail fast with a `click.UsageError`:

```
Error: --allow-blocking requires --apply; it has no effect in dry-run mode.
```

Rationale: silently ignoring `--allow-blocking` in dry-run would let CI scripts copy-paste flag sets between apply and dry-run invocations without notice, masking a broken expectation. Explicit error is cheaper than a debug session.

Same validation applies to `init` (symmetry with `apply`).

### 3.5 CLI flag surface

```
init:
  --profile NAME           (existing)
  --dry-run                (existing)
  --apply                  (existing)
  --force                  (existing)
  --allow-blocking         NEW — skip pre-apply doctor block

apply:
  --profile NAME           (existing)
  --dry-run                (existing)
  --apply                  (existing)
  --force                  (existing)
  --also-labels            (existing)
  --also-protection        (existing)
  --allow-blocking         NEW — skip pre-apply doctor block
```

## §4 — Template invariance

### 4.1 Gate rationale

The canonical `jobs.pr-gate: { name: "PR Gate" }` shape is enforced in two places:

1. `reusable-pr-gate-*.yml` produces a status step named "PR Gate".
2. `data/templates/ci/*-ci.yml` wraps that reusable in a job named "PR Gate".

Concatenation produces the status context `PR Gate / PR Gate`, which is hard-coded in `data/profiles/*-service.yml` as `required_contexts`. If any link in that chain drifts, new consumer repos produced by `init` would immediately fail `shape/job-shape-coherence` — the exact #46 incident class.

### 4.2 Test assertions

```python
# tests/unit/data/test_ci_templates.py

import re
import yaml
from importlib.resources import files
import pytest

_REUSABLE_USES_PY = re.compile(
    r"^yakkuro/gh-manage/\.github/workflows/reusable-pr-gate-python\.yml@.+$"
)
_REUSABLE_USES_TS = re.compile(
    r"^yakkuro/gh-manage/\.github/workflows/reusable-pr-gate-typescript\.yml@.+$"
)

@pytest.mark.parametrize(
    "filename, uses_re",
    [
        ("python-ci.yml", _REUSABLE_USES_PY),
        ("ts-ci.yml", _REUSABLE_USES_TS),
    ],
)
def test_bundled_ci_template_preserves_canonical_shape(filename, uses_re):
    text = files("gh_manage.data.templates.ci").joinpath(filename).read_text(
        encoding="utf-8"
    )
    parsed = yaml.safe_load(text)

    assert isinstance(parsed, dict), f"{filename}: top-level must be a mapping"
    assert "jobs" in parsed and "pr-gate" in parsed["jobs"], (
        f"{filename}: must declare jobs.pr-gate — see spec "
        f"docs/specs/2026-04-22-theme-b-guardrails-prevention-layer-design.md"
    )
    pr_gate = parsed["jobs"]["pr-gate"]
    assert pr_gate.get("name") == "PR Gate", (
        f"{filename}: jobs.pr-gate.name must be exactly 'PR Gate' to produce "
        f"status context 'PR Gate / PR Gate'. See yakkuro/gh-manage#46."
    )
    assert uses_re.match(pr_gate.get("uses", "")), (
        f"{filename}: jobs.pr-gate.uses must reference reusable-pr-gate; got "
        f"{pr_gate.get('uses')!r}"
    )
```

### 4.3 Scope notes

Covered:

- YAML parseability of each bundled template.
- `jobs.pr-gate.name == "PR Gate"` exact match.
- `jobs.pr-gate.uses` matches reusable-pr-gate-`<lang>` regex (version ref allowed to vary).

Out of scope (existing tests handle these or they are irrelevant):

- Workflow `permissions:` contents.
- Workflow `on:` triggers.
- `skip_if_exists` behavior on non-ci templates (e.g., `claude-md/default.md`).
- Custom profiles added post-v1.10.0: they are expected to add their own template-invariance tests if relevant.

## §5 — Error handling

### 5.1 Exception taxonomy

| Exception class | Source | Pre-apply handling |
|---|---|---|
| `DoctorError` (setup layer: profile missing, repos.yml corrupt, token scope missing) | `doctor.run_on_path` — before any check executes | Propagate — `handle_errors` turns it into `ClickException`; apply aborts with clear message before any mutation |
| `CiYmlParseError` (per-check: malformed ci.yml YAML) | inside one check | Caught in `registry.run_checks`; synthetic LOW finding emitted with `resolves_with` copied from the original check; other checks continue (see §2.4 invariant 5, §3.1.1) |
| `DoctorCheckError` (per-check: unexpected check failure) | inside one check | Same as CiYmlParseError |
| `GhError` / `GhNotFoundError` | GitHub API layer, during `run_on_path` setup | Propagate — same path as setup `DoctorError` |
| `GitError` | `git_cli.get_origin_owner_repo` | Propagate (this would already have fired during owner/repo derivation before pre-apply doctor is invoked) |
| `ClickException` (raised by `run_pre_apply_doctor` itself on block) | this module | Exits with code 1 and prints the formatted block message — standard Click behavior |

Rationale for the per-check isolation pattern: a malformed ci.yml or a malfunctioning single check must not silently drop findings from *other* checks that ran successfully. Before this spec, `run_checks` used `chain.from_iterable` which aborts iteration on the first exception — meaning one broken check could mask blocking findings elsewhere. The new pattern ensures every check contributes either its findings or a clearly-labeled diagnostic, so the block gate evaluates against complete information.

Secondary benefit: for the specific case of a broken ci.yml where `sync_files=True` (the common init/apply case), the synthetic LOW diagnostic carries `resolves_with=("sync_files",)` from the original `shape/job-shape-coherence` check. The semantic filter correctly drops it as "this apply will resolve it", so pre-apply proceeds and rewrites the ci.yml from the canonical template. The repo is healed without operator intervention.

### 5.2 `--allow-blocking` semantics

- Pre-apply doctor still runs (findings are still computed and logged).
- `ClickException` is suppressed.
- A stderr line is emitted: `WARNING: --allow-blocking: proceeding despite N blocking finding(s).`
- Post-apply doctor warning output is unchanged.

### 5.3 State guarantees on block

| Scenario | State after pre-apply block |
|---|---|
| `init --apply` blocks | No files written, no labels mutated, no protection changed. Working tree unchanged. |
| `apply --apply` blocks | Same. |
| `apply --apply --also-protection` blocks | Same. |

This is stronger than the existing post-apply-rollback guarantee in init: pre-apply never enters any mutation code path.

### 5.4 Log fields

- `log.info("pre-apply doctor: findings=%d filtered=%d blocking=%d allow_blocking=%s", ...)` — single INFO line, structured for the cli/v1.8.0 JSON formatter.
- `log.warning(...)` inside `registry.run_checks` per-check catch, emitted alongside the synthetic LOW finding.

## §6 — Test plan

### 6.1 New test files

**`tests/unit/doctor/test_semantic_filter.py`** — covers all filter decisions:

| Test | Setup | Expected |
|---|---|---|
| `test_filter_keeps_unscoped_findings` | finding with `resolves_with=("sync_files",)`, scope `sync_files=False` | finding kept |
| `test_filter_drops_fully_scoped_finding` | same finding, scope `sync_files=True` | finding dropped |
| `test_filter_requires_all_domains` | finding with `resolves_with=("sync_files","sync_protection")`, scope `sync_files=True, sync_protection=False` | finding kept |
| `test_filter_unknown_check_never_dropped` | finding with check name not in registry | finding kept (conservative default) |
| `test_filter_empty_scope_keeps_all` | scope with all False | no findings dropped |
| `test_filter_full_scope_drops_registered_resolvable` | scope with all True | all findings with non-empty `resolves_with` dropped |
| `test_filter_preserves_severity_ordering` | mixed critical/high/medium/low, scope filters out the high | remaining findings preserve their original order |
| `test_apply_scope_is_frozen` | attempt to mutate `ApplyScope` instance | raises `FrozenInstanceError` |

**`tests/unit/data/test_ci_templates.py`** — as described in §4.2. Parametrized over `python-ci.yml` and `ts-ci.yml`. Includes an in-test comment noting that any future bundled template must be added to the parametrize list manually.

**`tests/unit/doctor/test_registry.py`** (new or extended) — per-check exception isolation:

| Test | Setup | Expected |
|---|---|---|
| `test_run_checks_isolates_ci_yml_parse_error` | register a mock check that raises `CiYmlParseError`; register a second check that returns a HIGH finding | both a synthetic LOW diagnostic AND the second check's HIGH finding are in the result |
| `test_run_checks_isolates_doctor_check_error` | mock check raises `DoctorCheckError` | synthetic LOW diagnostic emitted; other checks' findings preserved |
| `test_run_checks_propagates_non_check_errors` | mock check raises `ValueError` (not `DoctorCheckError`) | exception propagates (we do NOT catch arbitrary exceptions — only the two known per-check classes) |
| `test_synthetic_finding_carries_original_resolves_with` | mock check has `resolves_with=("sync_files",)`, raises `CiYmlParseError` | synthetic Finding's lookup via `get_check_resolves_with("shape/check-error:<name>")` returns `("sync_files",)` |
| `test_get_check_resolves_with_for_registered_check` | happy-path lookup | returns the tuple declared in the decorator |
| `test_get_check_resolves_with_for_unknown_check` | unregistered check name | returns `()` (conservative default) |

### 6.2 Modified test files

**`tests/unit/commands/test_init.py`**:

- DELETE tests covering post-apply CRITICAL rollback + orphan-file cleanup.
- ADD `test_init_apply_blocks_on_blocking_finding`: simulate pre-apply doctor returning a critical finding for a check whose `resolves_with` is NOT covered by init's scope (edge case — verifies the filter doesn't over-exclude for init).
- ADD `test_init_apply_first_time_adoption_succeeds`: profile declares `required_contexts`, live protection is empty → pre-apply doctor returns high `shape/required-contexts-match`, but filter drops it because init scope includes `sync_protection`. Apply proceeds.
- ADD `test_init_apply_with_allow_blocking_proceeds`: same blocking finding as first test, but with `--allow-blocking` → stderr warning, apply proceeds.
- ADD `test_init_dry_run_skips_pre_apply_doctor`: `--dry-run` path does NOT invoke doctor (assert via mock).

**`tests/unit/commands/test_apply.py`**:

- ADD `test_apply_without_also_protection_blocks_on_protection_finding`: apply without `--also-protection`, fixture produces a HIGH `shape/required-contexts-match` finding. Scope is `sync_protection=False`, so the finding is NOT filtered → block with ClickException; verify side-effects = 0.
- ADD `test_apply_also_protection_first_time_succeeds`: same HIGH finding but with `--also-protection`. Scope is `sync_protection=True` → filtered → apply proceeds and writes files / syncs protection.
- ADD `test_apply_allow_blocking_bypasses_block`: same setup as the blocking case above, add `--allow-blocking`. Assert stderr WARNING message is emitted, apply proceeds, no ClickException raised.
- ADD `test_apply_dry_run_skips_pre_apply_doctor`: `--dry-run` (without `--apply`) — assert `doctor.run_on_path` is NOT called (use mock to verify).
- ADD `test_apply_dry_run_with_allow_blocking_raises_usage_error`: both `--dry-run` and `--allow-blocking` set → expect `click.UsageError`. Covers §3.4.1 flag validation.
- ADD `test_apply_post_apply_warning_unchanged`: pre-apply passes, apply runs, post-apply doctor finds a residual finding → verify stderr warning, exit code 0, no behavior change from pre-v1.10 post-apply warning format.
- ADD `test_apply_malformed_ci_yml_heals`: fixture repo has malformed ci.yml. `shape/job-shape-coherence` raises `CiYmlParseError` inside `run_checks`; registry converts to synthetic LOW with `resolves_with=("sync_files",)`; filter drops it (sync_files=True); apply proceeds, rewrites ci.yml from template. Post-apply doctor passes. (Verifies §3.1.1 + §5.1 integration.)

### 6.2.1 Cross-cutting: conservative-default test

- ADD in `test_semantic_filter.py` (also applicable to commands): `test_filter_never_drops_check_without_resolves_with` — register a mock check with `resolves_with=()`, emit a high finding, run filter with full scope (`sync_files=sync_labels=sync_protection=True`). Assert the finding is kept. This is the explicit regression gate for invariant 1 (§2.4) — if a future developer forgets to pass `resolves_with`, the test must catch that the finding remains blocking.

### 6.3 TDD ordering

Per CLAUDE.md "TDD is mandatory":

1. **Red 1** — `test_semantic_filter.py` against not-yet-existent `semantic_filter.py`. Assert import fails / module missing.
2. **Green 1** — implement `ApplyScope`, `filter_pre_apply_findings`, registry `resolves_with` support. Tests pass.
3. **Red 2** — `test_ci_templates.py` → expect Green immediately because existing templates already comply. This test exists as a regression gate; its failure mode is future template edits.
4. **Red 3** — modified `test_init.py` and `test_apply.py` with pre-apply block cases. These fail because init/apply don't call `run_pre_apply_doctor` yet.
5. **Green 3** — implement `run_pre_apply_doctor` in `_shared.py`, wire into init and apply. Delete init post-apply rollback block. Tests pass.
6. **Full suite** — confirm no regression: `uv run pytest`, `uvx ruff@0.8.0 format --check`, `uv run mypy src/`.

### 6.4 Coverage targets

- `doctor/semantic_filter.py`: 100% branch coverage (small module, all branches meaningful).
- `doctor/registry.py`: new `get_check_resolves_with` branch covered.
- `commands/_shared.py` new helper: 100% branch coverage (allow_blocking path, block path, pass path). Per-check exception coverage is tested in `test_registry.py` (new or extended).
- `commands/init.py` + `commands/apply.py`: new pre-apply integration paths 100%.

### 6.5 No E2E changes

The existing `CliRunner`-based integration tests in `tests/unit/commands/` suffice. No new `tests/integration/` or live-GitHub E2E is added: all doctor calls are mockable via the existing `doctor.run_on_path` seam.

## §7 — Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Filter incorrectly drops a finding that `apply` won't actually resolve, letting mismatched state land | High | (a) conservative default — unregistered checks never drop; (b) resolves_with explicitly declared per check; (c) unit-test-per-combination; (d) post-apply warning remains as sanity check |
| New `--allow-blocking` flag becomes a default habit in CI scripts, defeating the gate | Medium | (a) flag name is intentionally verbose and negative ("allow blocking" reads badly in a CI script), (b) WARNING line on stderr when used, (c) release notes emphasize "do not set this flag by default" |
| Existing consumer CI pipelines running `gh-manage apply --apply` fail silently in CI after v1.10 bump | Medium | (a) Pre-v1.10 release: run `gh-manage doctor --all` offline against the 22 consumer repos; ensure at most the known Track B 8 repos have blocking findings; (b) cli/v1.10.0 release notes document the new gate with migration instructions; (c) the block message points users to `gh-manage doctor` |
| Template invariance test fires false-positive on legitimate template edit | Low | Test failure message explicitly names the file and the expected shape; the fix is to update the test's regex/assertion at the same time as the template edit (one PR) |
| `init` post-apply rollback code removal leaves behind orphan files when a bug elsewhere triggers partial failure | Low | The pre-apply block guarantees no partial state from doctor-detectable issues. Other partial-failure sources (label API flake, protection API transient error) are unchanged from current behavior; error messages already recommend `git status` + manual cleanup |
| `doctor/checks.py` decorator change (resolves_with kwarg) breaks external callers | Negligible | The doctor module is internal to gh-manage; no public API contract. Kwarg defaults to `()` for backward compat inside the codebase |

## §8 — Implementation sequencing

Phase-by-phase plan (to be expanded by the writing-plans step):

1. **Phase 1**: Semantic filter module + registry augmentation.
   - `doctor/semantic_filter.py`, `doctor/registry.py` update, `doctor/checks.py` decorator updates.
   - `test_semantic_filter.py` (Red → Green).
   - No user-visible change yet.

2. **Phase 2**: Template invariance gate.
   - `test_ci_templates.py` — Green immediately on existing templates.
   - Regression-only, independent of Phase 1.

3. **Phase 3**: `_shared.py` helper `run_pre_apply_doctor`.
   - Unit test via `test_shared_pre_apply_doctor.py` (new).
   - Still no user-visible change (helper is unwired).

4. **Phase 4**: `apply.py` integration.
   - Wire `run_pre_apply_doctor` into `apply --apply`.
   - Add `--allow-blocking` flag.
   - `test_apply.py` new tests Red → Green.
   - User-visible behavior change starts here.

5. **Phase 5**: `init.py` integration.
   - Wire `run_pre_apply_doctor` into `init --apply`.
   - Delete post-apply rollback code.
   - Add `--allow-blocking` flag.
   - `test_init.py` test rewrite.

6. **Phase 6**: Release prep.
   - `docs/versioning.md` cli/v1.10.0 entry.
   - Release notes draft.
   - Run `gh-manage doctor --all` against all 22 consumer repos; record expected block sites for #75.
   - 4-agent PR review per `workflow-review.md`.

7. **Phase 7**: Release.
   - `cli/v1.10.0` tag via existing release workflow.

## §9 — Release notes (draft)

```
## cli/v1.10.0 — Prevention-layer guardrails (Theme B)

### Breaking-ish behavior change

`gh-manage init --apply` and `gh-manage apply --apply` now run the
doctor framework before mutating any repository state. If any
`critical` or `high` severity finding remains after the semantic
filter (which drops findings the current invocation is about to
resolve), the command aborts with exit code 1 and zero side-effects.

To proceed past the new gate when the finding is known and intentional,
pass `--allow-blocking`.

### What changed

- Added `--allow-blocking` flag to `init` and `apply`.
- Pre-apply doctor integration in both commands.
- `init`'s post-apply CRITICAL rollback removed — pre-apply gate
  subsumes its guarantee.
- New regression test that bundled `ci/*.yml` templates preserve
  `jobs.pr-gate: { name: "PR Gate" }`.

### Migration

If your CI runs `gh-manage apply --apply` and starts failing after
this release:

1. Run `gh-manage doctor <path> --profile <name>` to see the
   blocking findings.
2. Apply the suggested `Fix:` remediation, OR
3. If intentional (rare), re-run `apply` with `--allow-blocking`.

### Non-changes

- Reusable workflow YAML unchanged.
- Drift scanner behavior unchanged.
- Doctor standalone command unchanged.
```

## §10 — Acceptance criteria

- [ ] `uv run pytest` green after every phase.
- [ ] `uvx ruff@0.8.0 format --check src/ tests/` passes.
- [ ] `uv run mypy src/` passes.
- [ ] `gh-manage init --apply --profile python-service` on a fresh repo with no prior state succeeds (first-time adoption does not block).
- [ ] `gh-manage apply --apply --also-protection --profile python-service` against a repo with live mismatched context blocks with clear message; same command with `--allow-blocking` proceeds with warning.
- [ ] `gh-manage apply --apply --profile python-service` (no `--also-protection`) against one of the 8 pre-existing repos (Track B) blocks with expected message (pre-release verification step in Phase 6).
- [ ] Bundled ci.yml template regression test passes; a local edit that breaks `name: "PR Gate"` causes CI to fail.
- [ ] `init`'s post-apply rollback code path is deleted; grep for "rollback" in init.py returns no matches.
- [ ] Release notes draft in §9 is published as the cli/v1.10.0 GitHub Release body.
- [ ] 4-agent PR review per `claude-dotfiles/rules/workflow-review.md` completes with no unresolved HIGH findings.
