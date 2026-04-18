# Hygiene Bundle (4a) — `set -f` + 422 silent-failure + profile validation

- **Date**: 2026-04-18
- **Size**: Small (but 3 fixes — borderline Small/Medium; Small chosen because each fix is self-contained ≤50 LOC and the 3 do not interact)
- **Sizing Rationale**: 3 independent fixes, each small and well-designed already in their respective issue threads. Mostly implementation with minor design decisions (GET-first vs parse-body for #40; model_validator vs pre-scan for #39). Single plan covers all 3 with separate tasks per issue.
- **Target**: `yakkuro/gh-manage`
- **Goal**: Close 3 known-risk issues from Theme A/roadmap: #44 (reusable workflow glob injection defence), #40 (label setup silent-failure), #39 (fail-fast on invalid repos.yml profile references). Ship as a single `cli/v1.5.0` + reusable workflow follow-up release.

## Background

Roadmap items from [#47 Theme A](https://github.com/yakkuro/gh-manage/issues/47) and rollout-adjacent follow-ups:

- **[#44](https://github.com/yakkuro/gh-manage/issues/44)**: PR #43 (v1.1.0) neutralised quote / `;` / `|` / `$()` injection on `install-command` + `test-command` by switching from `eval` to word-splitting. Bash pathname expansion (globbing) still runs during word splitting — an attacker who can commit a file + route untrusted input could use a glob like `echo*` to hijack execution. `set -f` disables globbing in the shell, closing this residual vector.
- **[#40](https://github.com/yakkuro/gh-manage/issues/40)**: `ensure_drift_label` in `src/gh_manage/github_api/issues.py:98` catches 422 via string match `"422" in str(e) or "already_exists" in str(e)`. HTTP 422 covers multiple failure modes (validation failure, resource limits, etc.) — the current check silently ignores ALL of them, masking real failures during drift scanner setup. Now that PR #54 added `.status_code` to `GhError`, a cleaner idempotent pattern is available.
- **[#39](https://github.com/yakkuro/gh-manage/issues/39)**: `repos.yml` entries have `profile: str` with no load-time validation. A typo or wrong profile (e.g., `nade-nade: profile: python-service` but it's actually TypeScript) silently FAILs at scan time — the scanner reports "22 repos scanned, 1 FAILED" with the failure buried in per-repo summary. No fail-fast for config mistakes.

All 3 are independent, same hygiene class, similar small-LOC scope. Bundling them into one PR gives a single review cycle and a single `cli/v1.5.0` release.

## Goals

1. Close the glob-expansion attack surface in the reusable PR gate workflows (defence-in-depth on top of PR #43).
2. Eliminate silent 422 swallowing in `ensure_drift_label` — replace with an idempotent GET-first pattern.
3. Surface invalid `repos.yml` profile references at config load time with a clear, aggregated error.

## Non-goals

- **`setup-command` shell hardening** (in the same reusable workflows). It intentionally uses `eval` for flexibility; different trust model. Out of scope — separate issue if needed.
- **Error body parsing in `github_client.run_gh_api`**. #40's GET-first approach avoids needing this. Keep transport body-parse-free for now.
- **Runtime re-validation of `repos.yml` profile existence after startup** (e.g., when profiles are added/removed during a long session). #39 only validates at load time — profiles don't change mid-process in practice.
- **Audit of all 22 consumer repos for glob usage in `install-command` / `test-command`**. The 3 fix-shape consumers (#46 follow-up) were audited during Phase 10 rollout; none used globs. No new audit required — the v1.1.0 word-splitting change already assumed consumers don't rely on glob patterns and no consumer has complained since.
- **`#29` (ts-service profile creation)** — handled as a separate 4b PR per user's 4a/4b split.
- **`#56` (markdown-file race)** — unrelated, tracked separately.

## §1 — Architecture

Three independent fixes, each in its own commit within one PR. No cross-cutting concerns. Separation aids focused review and per-fix revertability.

```
┌───────────────────────────────────────────────────────────────────┐
│ PR: hygiene bundle (cli/v1.5.0 + reusable workflow follow-up)    │
├───────────────────────────────────────────────────────────────────┤
│ commit 1 — #44: `set -f` in install + test steps                 │
│   .github/workflows/reusable-pr-gate-python.yml                  │
│   .github/workflows/reusable-pr-gate-typescript.yml              │
├───────────────────────────────────────────────────────────────────┤
│ commit 2 — #40: GET-first `ensure_drift_label`                   │
│   src/gh_manage/github_api/issues.py                             │
│   tests/unit/github_api/test_issues.py                           │
├───────────────────────────────────────────────────────────────────┤
│ commit 3 — #39: ReposConfig profile model_validator              │
│   src/gh_manage/models/repos.py                                  │
│   tests/unit/models/test_repos.py (or existing test file)        │
├───────────────────────────────────────────────────────────────────┤
│ commit 4 — chore: bump cli to 1.5.0 (__init__.py, pyproject,     │
│   test_sanity.py, release notes)                                 │
└───────────────────────────────────────────────────────────────────┘
```

Each commit is independently buildable and testable.

## §2 — Fix #44 (`set -f`)

### What changes

In BOTH `.github/workflows/reusable-pr-gate-python.yml` and `.github/workflows/reusable-pr-gate-typescript.yml`, add `set -f` immediately after the existing `set -euo pipefail` in the Install and Run tests steps.

**Current (python, install step — line 89-94)**:
```yaml
        run: |
          set -euo pipefail
          echo "::group::install"
          echo "Running install-command: ${INSTALL_CMD}"
          ${INSTALL_CMD}
          echo "::endgroup::"
```

**Target**:
```yaml
        run: |
          set -euo pipefail
          set -f  # disable pathname expansion; closes glob injection vector (#44)
          echo "::group::install"
          echo "Running install-command: ${INSTALL_CMD}"
          ${INSTALL_CMD}
          echo "::endgroup::"
```

Identical pattern applied to 3 more spots: python test step, TypeScript install, TypeScript test. The `setup-command` step (uses `eval`) is deliberately untouched — different trust model.

### Why this is safe for consumers

Bash `set -f` disables pathname expansion only for the current shell. It does NOT affect:
- Commands inside `${INSTALL_CMD}` that explicitly invoke glob expansion (e.g., `find`, shell commands in sub-shells that `set +f` themselves)
- Tools like `pytest` that handle their own file globbing via argparse

What it breaks:
- `install-command: "uv sync && pip install package*.whl"` — `package*.whl` would not expand. No consumer uses this pattern.
- `test-command: "pytest tests/*.py"` — `tests/*.py` would not expand. Consumers all use `pytest` without globs or use explicit paths.

Audit summary (from Phase 10 rollout + consumer survey): 22 consumers. None use glob patterns in `install-command` or `test-command`. `set -f` is a safe, strict defence upgrade.

### Testing

No unit tests on reusable workflows (they're YAML). Validation:
- Push to `gh-manage` main triggers `doctor-smoke.yml` + self-dogfood — both exercise the reusable-pr-gate-python workflow locally.
- v1.5.0 bump PR CI runs against the updated workflow.
- Post-merge: `gh-manage drift --all` on 22 consumers (all pinned to v1.1.0) is unaffected (their CI doesn't run the new workflow until they bump pin; no regression risk on v1.1.0).

## §3 — Fix #40 (`ensure_drift_label` GET-first)

### What changes

Replace the string-match 422 swallow in `src/gh_manage/github_api/issues.py:80-100` with an idempotent GET-first pattern:

```python
def ensure_drift_label(repo: str) -> None:
    """Ensure the `gh-manage:drift` label exists on the repo.

    Uses a GET-first pattern to avoid silent-failure classes:
    1. GET /repos/{repo}/labels/{name} — if 200, label already exists; return.
    2. If 404, POST to create.
    3. On any other error (GET or POST), raise — no silent swallow.

    Idempotent: safe to call repeatedly; 2 API calls in the common case
    (label already exists, returns after step 1).
    """
    try:
        existing = run_gh_api(f"repos/{repo}/labels/{_DRIFT_LABEL}")
        if existing is not None:
            # GET returned the label (dict) — exists, nothing to do.
            return
    except GhNotFoundError:
        # Label does not exist — proceed to create.
        pass

    # At this point, GET either returned None (no body on 404 via run_gh_api
    # semantics) or raised GhNotFoundError. Either way, label missing.
    run_gh_api(
        f"repos/{repo}/labels",
        method="POST",
        body={
            "name": _DRIFT_LABEL,
            "color": _DRIFT_LABEL_COLOR,
            "description": _DRIFT_LABEL_DESCRIPTION,
        },
    )
```

### Why GET-first

Alternative: POST + parse 422 body for `errors[].code == "already_exists"`. Requires:
- Capturing error response body in `run_gh_api` (currently only stderr is captured)
- JSON-parsing error stderr (fragile)
- Matching against GitHub's error schema (tied to API contract)

GET-first:
- 1 extra API call in create case (rare — once per repo lifetime)
- 1 API call in exists case (same as before POST-and-swallow)
- Zero body parsing, no transport changes
- Transparent behavior: caller sees `GhError` subclasses only, never masked failures
- Idempotent by construction — not by error-swallowing

### Behavior under GET race

The race window (label created between our GET and POST) is extremely narrow because `ensure_drift_label` is only called from the drift scanner's single-repo code path. But for defensiveness:

If the POST hits 422 because someone created the label between our GET and POST, we currently let it propagate. This is acceptable for now (extremely rare, loud failure signals a real concurrency issue worth investigating). If production observability later shows this happening, extend the function with one retry GET.

### Testing

New tests in `tests/unit/github_api/test_issues.py` (3 cases):

1. `test_ensure_drift_label_exists_no_post` — mock GET returns a label dict → function returns without calling POST.
2. `test_ensure_drift_label_missing_then_created` — mock GET raises `GhNotFoundError` → POST is called with correct payload.
3. `test_ensure_drift_label_unexpected_get_error_propagates` — mock GET raises `GhAuthError` (401) → propagates (no swallow).
4. `test_ensure_drift_label_unexpected_post_error_propagates` — mock GET raises 404, POST raises `GhPermissionError` (403) → propagates (no swallow).

Regression test for the fix: no test should assert that 422 is silently ignored. If an existing test did that, it is removed.

## §4 — Fix #39 (`ReposConfig` profile model_validator)

### What changes

Add `@model_validator(mode='after')` to `ReposConfig` that:
1. Discovers available profiles via `importlib.resources.files("gh_manage.data.profiles")` — enumerate `*.yml` stems.
2. For each `RepoEntry`, check `entry.profile in <available_profiles>`.
3. Collect all invalid entries; raise a single `ValueError` listing all offenders and the available set.

```python
# in src/gh_manage/models/repos.py

from importlib.resources import files
from pydantic import model_validator


class ReposConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    repos: list[RepoEntry]

    @model_validator(mode="after")
    def _validate_profile_names(self) -> "ReposConfig":
        available = {
            p.stem
            for p in files("gh_manage.data.profiles").iterdir()
            if p.name.endswith(".yml")
        }
        invalid = [
            (e.name, e.profile)
            for e in self.repos
            if e.profile not in available
        ]
        if invalid:
            msg_lines = [
                f"Unknown profile references in repos.yml:",
            ]
            for repo, profile in invalid:
                msg_lines.append(f"  - {repo}: profile={profile!r}")
            msg_lines.append(f"Available profiles: {sorted(available)}")
            raise ValueError("\n".join(msg_lines))
        return self
```

### Why `mode='after'`

Needs access to instantiated `RepoEntry` objects. `mode='before'` operates on raw dict, which would require re-implementing list parsing. `after` is the natural fit — validation happens once, after all entries are constructed.

### Why aggregate all errors

Without aggregation, a user with 3 typos sees errors one by one (fix 1 → rerun → fix 2 → rerun → fix 3). Aggregation surfaces all in one shot. Pydantic's built-in error collection doesn't easily aggregate across custom validator logic, so we collect manually and raise once.

### Behavior change

Before: invalid profile → silent per-repo FAIL at scan time, buried in summary.
After: invalid profile → `load_config(repos_path, ReposConfig)` raises `ConfigError` wrapping the `ValueError` at startup of `drift --all` (or any caller that loads repos.yml).

This is a **breaking change for callers of `load_config` on malformed repos.yml** — but those were already broken in practice (invisibly). `_scan_all_repos` is the only caller in the codebase, and its existing `except ConfigError` path already handles the new early failure correctly.

### Testing

Modify or add test file under `tests/unit/models/` — check existing structure first. Test cases:

1. `test_valid_profile_names_pass` — `repos: [{name: "a/b", profile: "python-service"}]` validates successfully (python-service is bundled).
2. `test_invalid_profile_name_fails` — `repos: [{name: "a/b", profile: "pytohn-service"}]` (typo) → ValidationError matching "pytohn-service" and "Available profiles".
3. `test_multiple_invalid_profiles_aggregated` — 3 entries with bad profile → single error mentioning all 3.
4. `test_mixed_valid_invalid` — 2 valid + 1 invalid → error mentions only the invalid one.

## §5 — Release Plan

### Version bump

cli/v1.5.0 (minor — behavior change: load-time validation fail-fast; idempotent label setup; hardened install/test steps in reusable workflow).

Files:
- `src/gh_manage/__init__.py` — `__version__ = "1.5.0"`
- `pyproject.toml` — `version = "1.5.0"`
- `tests/test_sanity.py` — assert version

### Release notes

- Hygiene bundle closing #44, #40, #39.
- `ensure_drift_label` now uses GET-first pattern — no more silent 422 swallowing.
- `repos.yml` profile references are validated at load time; typos surface immediately.
- Reusable PR gate workflows (Python + TypeScript) add `set -f` to install + test steps, closing the glob-injection vector (residual from v1.1.0 word-splitting fix per #36 / PR #43).

### Compatibility

- `ensure_drift_label`: behavior-identical in the happy path (label exists or gets created). Improves on the error path (propagates real failures).
- `ReposConfig`: Newly rejects invalid profile references. `load_config` callers must handle `ConfigError` — existing CLI `_scan_all_repos` already does.
- Reusable workflows: `set -f` is a subtle behavior change for any consumer using glob patterns in `install-command` / `test-command`. None audited (22 consumers). Consumers that encounter breakage have a clear workaround: inline `set +f` inside their command string.

### Deployment

Single gh-manage PR. After merge + `cli/v1.5.0` tag, the reusable workflow changes are immediately visible to consumers pinning `@main`. Consumers pinned to `@v1.1.0` are unaffected until they bump.

## §6 — Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| A consumer uses globs in `install-command` / `test-command` that we didn't audit | Their CI breaks on next run (if pinned to main or newly bumped) | Release note + workaround: inline `set +f` in their command string. No audit found any such usage. |
| `ensure_drift_label` GET-first adds 2 API calls in exists case | Trivial latency increase (~100ms) | Cached GitHub API, insignificant next to the full drift scan work. |
| `ReposConfig` validator performs filesystem IO at load time (reads profiles dir) | Slower load; can fail if profiles dir missing | `importlib.resources` handles packaged data files; test verifies the dir is accessible from an installed wheel. If it fails, `load_config` raises a clear error (not a silent bypass). |
| Bundle has 3 concurrent fixes — one regression blocks release of other 2 | Delayed ship | Per-commit separation allows `git revert <commit>` if one fix turns out problematic. Each fix has independent tests. |
| `set -f` breaks a specific `setup-command` edge case (even though setup-command itself is unchanged) | Consumer CI regresses | Not possible — `setup-command` is in its own step with its own shell (different `run:` block). `set -f` is scoped to the step's run block only. |
| Pydantic `model_validator` raises ValidationError, not ConfigError | `_scan_all_repos` expects ConfigError | `load_config` wraps ValidationError into ConfigError already (existing pattern); verify in implementation. If not, add the wrap. |

## §7 — Acceptance Criteria

- [ ] `.github/workflows/reusable-pr-gate-python.yml` — `set -f` added to install step (line ~90) and test step (line ~130).
- [ ] `.github/workflows/reusable-pr-gate-typescript.yml` — `set -f` added to install step and test step (verify line numbers in implementation).
- [ ] `src/gh_manage/github_api/issues.py` — `ensure_drift_label` uses GET-first pattern; no string-match `"422" in str(e)` code remains.
- [ ] `tests/unit/github_api/test_issues.py` — 4 new test cases added; no test asserts silent 422 swallowing.
- [ ] `src/gh_manage/models/repos.py` — `ReposConfig` has `@model_validator(mode='after')` that validates profile references.
- [ ] `tests/unit/models/test_repos.py` (or equivalent) — 4 new test cases added.
- [ ] `uv run pytest -q` all green (expect ~560 tests, +~10 new).
- [ ] `uvx ruff@0.8.0 check src/ tests/` clean.
- [ ] `uvx ruff@0.8.0 format --check src/ tests/` clean.
- [ ] `uv run mypy src/` clean.
- [ ] Version bumped to `1.5.0` in `__init__.py`, `pyproject.toml`, `test_sanity.py` sync.
- [ ] Self-dogfood: `uv run gh-manage drift --all` on 22 repos reports 0 FAILED; doctor-smoke CI green.
- [ ] 4-reviewer protocol clean (Codex + superpowers + SFH + code-reviewer).
- [ ] PR merged → `cli/v1.5.0` tagged and released.
- [ ] 3 closing issues (#44, #40, #39) closed on merge (via "Closes" / "Fixes" keywords in PR body).

## §8 — Open Questions

None. All design decisions resolved during 2026-04-18 brainstorming.

## References

- Theme A umbrella: [#47](https://github.com/yakkuro/gh-manage/issues/47)
- Transport retry (PR #54 → cli/v1.3.0): introduced `.status_code` on GhError subclasses — enables #40's cleaner pattern.
- Reusable workflow (v1.1.0 eval hardening, PR #43): the predecessor to #44.
- Phase 10 rollout ([#27](https://github.com/yakkuro/gh-manage/issues/27)): close-out in progress.
