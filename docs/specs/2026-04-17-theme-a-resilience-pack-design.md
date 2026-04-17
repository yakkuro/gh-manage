# Theme A — Resilience Pack Design (classifier + retry + parallel `--all`)

- **Date**: 2026-04-17
- **Size**: Medium
- **Sizing Rationale**: 3+ files touched (`github_client.py` refactor, new retry helpers, `commands/drift.py` parallelism), non-trivial design decisions (retry policy, rate-limit reset handling, thread pool strategy), user-visible behavior change (CLI flag `--concurrency`). Not Large — single coherent subsystem (transport + scanner), no cross-module orchestration. Small would undersell the policy decisions.
- **Target**: `yakkuro/gh-manage`
- **Goal**: Harden gh CLI transport and parallelize `gh-manage drift --all` so 20+ repo scans (Phase 10 target) survive transient GitHub API failures and secondary rate-limit pressure without aborting.

## Background

Roadmap review on 2026-04-17 ([#47](https://github.com/yakkuro/gh-manage/issues/47)) flagged the following Theme A items as blocking Phase 10 scale-up:

1. **Error classification in `src/gh_manage/github_client.py`** uses fragile stderr substring matching (`"rate limit"`, `"http 404"`, `"bad credentials"`). A wording change on GitHub's side silently reclassifies errors.
2. **`GhRateLimitError` is defined at `github_client.py:39` and raised at `:56` but never caught anywhere in `src/`** (verified by grep on 2026-04-17). A single rate-limit flake during `--all` aborts the entire scan.
3. **`_scan_all_repos` at `src/gh_manage/commands/drift.py:147` is a sequential `for` loop over `config.repos`**. 9 repos take ~2 minutes today; 20+ repos will exceed 4 minutes and amplify rate-limit exposure linearly.

PR #53 (doctor + init hardening, merged 2026-04-17) bundled two smaller Theme A items: `git_cli.GitError` stderr preservation and `findings.py` extraction from `drift_sync.py`. This spec addresses the next resilience layer.

Related issues: [#47](https://github.com/yakkuro/gh-manage/issues/47) (Theme A umbrella), [#27](https://github.com/yakkuro/gh-manage/issues/27) (Phase 10 rollout — load-bearing on this work).

## Goals

1. Make error classification robust against GitHub API message wording changes by using HTTP status codes as the primary signal.
2. Automatically recover from transient failures (5xx, network, rate-limit) during `gh api` calls so an `--all` scan completes even when one or two calls flake.
3. Parallelize `gh-manage drift --all` with a configurable worker pool so 20+ repo scans complete in under a minute on typical connections.
4. Preserve full audit trail: every retry attempt logs to stderr so CI artifacts show the remediation history.

## Non-goals

- **File splits for `drift_sync.py` / `protection_sync.py`** (Theme A items 4 + 5). Tracked in [#47](https://github.com/yakkuro/gh-manage/issues/47); this spec does not touch those files' internal structure.
- **Structured logging / run history / metrics** (Theme A item 6). Tracked in [#47](https://github.com/yakkuro/gh-manage/issues/47) / [#50](https://github.com/yakkuro/gh-manage/issues/50). Retry log emission in this spec is ad-hoc stderr text, not structured JSON.
- **Per-repo circuit breaker** (Approach X3). Deferred until fleet size exceeds ~40 repos.
- **Per-repo retry budget** across scans. Single scan, single retry budget per call site.
- **Rate-limit shared state across parallel workers**. Workers retry independently; GitHub rejects all workers simultaneously at rate-limit, so shared state adds complexity for no observable benefit at current scale.
- **#40 label 422 silent swallowing**. Adjacent but separate PR — doctor's PR #53 noted that `.status_code` on `GhError` is prerequisite work; #40's fix consumes the new attribute. Not bundled here to keep PR 1 scope focused.
- **`gh-manage apply` / `init` / `doctor` retry changes**. This spec touches only the transport layer and the `drift --all` command. `apply` is single-repo and interactive, so retry's value is lower there; if needed, added in a follow-up once transport retry is validated.
- **PyPI publishing**, **GitHub Enterprise support**, and other v1.0 non-goals from the top-level design spec.

## Scope (two PRs)

**PR 1 — Transport Resilience** (`cli/v1.3.0`)
- Refactor `github_client._raise_classified_error` to classify by HTTP status code.
- Add `.status_code` attribute to `GhError` subclasses.
- Add retry layer in `run_gh` for transient + rate-limit errors.
- Log retry attempts to stderr.
- env var config only: no CLI flag surface added.

**PR 2 — Parallel `--all` Scan** (`cli/v1.4.0`)
- Refactor `_scan_all_repos` to `concurrent.futures.ThreadPoolExecutor`.
- New `--concurrency N` CLI flag (default 4, clamped to 1–16).
- Stream per-repo results via `as_completed`; summary still ordered by repo.
- Rely on PR 1's retry layer for rate-limit recovery under concurrency pressure.

## §1 — Architecture (PR 1: Transport Resilience)

### Data Model

```python
class GhError(Exception):
    """Base class. status_code is set on construction when HTTP-classified."""
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

class GhAuthError(GhError): ...          # status_code = 401
class GhPermissionError(GhError): ...    # status_code = 403 (non-rate-limit)
class GhNotFoundError(GhError): ...      # status_code = 404

class GhRateLimitError(GhError):
    """429 or 403 rate-limit. reset_at immutable, set at construction."""
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        reset_at: datetime | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.reset_at = reset_at

class GhAPIError(GhError): ...           # status_code set when parseable, else None
class GhTransientError(GhAPIError):      # 5xx + network — retry-eligible subclass
    ...                                  # status_code = 500/502/503/504 or None
```

Immutability contract: `reset_at` is set once at construction and never mutated. The classifier raises `GhRateLimitError(msg)` with `reset_at=None`. The retry layer (§Retry Layer) does NOT mutate the original exception — when it learns the reset timestamp via `_fetch_rate_limit_reset()`, it either sleeps-and-retries the call, or if the wait would exceed `rate_limit_wait_max`, re-raises a fresh `GhRateLimitError(original_msg, status_code=original.status_code, reset_at=fetched_ts) from original`. Callers that see a `GhRateLimitError` propagating past the retry layer can rely on `reset_at` being either None (probe failed) or an accurate immutable timestamp.

Rationale for `GhTransientError` vs flags on `GhAPIError`:
- Retry layer needs a sharp, cheap predicate: `isinstance(e, (GhTransientError, GhRateLimitError))`.
- Subclass inheritance preserves existing `except GhAPIError` callers — `GhTransientError` matches them.
- Network failures (no HTTP response) reuse `GhTransientError` with `status_code=None`.

### Classifier (`_raise_classified_error`)

The classifier distinguishes two distinct scenarios, not a primary path with a fallback. The presence or absence of an HTTP status code in stderr selects the path:

**Path A: HTTP response received** (GitHub returned a response, `gh` surfaced the status).

1. Extract HTTP status code via regex `r"\(HTTP (\d{3})\)"` on stderr. `gh` CLI consistently emits `(HTTP <code>)` in its error output — documented in `gh api` source. If the regex matches, take Path A.
2. Dispatch by code:
   - `401` → `GhAuthError`
   - `403` → inspect stderr for rate-limit markers (`"API rate limit"`, `"secondary rate limit"`, `"abuse detection"`); if matched, `GhRateLimitError`, else `GhPermissionError`
   - `404` → `GhNotFoundError`
   - `429` → `GhRateLimitError`
   - `500`/`502`/`503`/`504` → `GhTransientError`
   - Other (4xx/5xx not listed) → `GhAPIError` with `status_code` populated

**Path B: No HTTP response** (network-level failure, no status in stderr).

1. Only reached when Path A's regex does NOT match.
2. Check stderr against a table of network markers (case-insensitive substring match, priority order):
   - `"dial tcp"` → `GhTransientError` (status_code=None)
   - `"no such host"` → `GhTransientError` (status_code=None)
   - `"connection refused"` → `GhTransientError` (status_code=None)
   - `"i/o timeout"` or `"context deadline exceeded"` → `GhTransientError` (status_code=None)
   - None matched → `GhAPIError` (status_code=None)

Design invariant: Path A and Path B are mutually exclusive and exhaustive; every stderr lands in exactly one. If a future `gh` CLI version changes the HTTP error format such that `(HTTP <code>)` no longer appears, Path A regression breaks all HTTP error classification — this is a sharp failure mode by design. A dual-path with substring fallback would silently re-classify 500s as `GhAPIError` and lose retry eligibility, which is worse than a loud test failure. The classifier test suite includes a canary test asserting `(HTTP 500)` is still parseable from a representative `gh` stderr fixture.

### Retry Layer

New module: `src/gh_manage/github_retry.py` (~100-150 LOC).

```python
def retry_gh(
    fn: Callable[[], T],
    *,
    endpoint: str,
    max_attempts: int = 3,
    rate_limit_wait_max: float = 60.0,
) -> T:
    """Wrap a callable that may raise GhTransientError or GhRateLimitError.

    Policy:
    - GhTransientError: exponential backoff 1s → 2s → 4s with 0-50%
      multiplicative jitter (sleep in [base, base*1.5)).
    - GhRateLimitError: poll `gh api rate_limit` for reset time via
      `_fetch_rate_limit_reset()`. If reset is within
      `rate_limit_wait_max` seconds, sleep for
      `(reset_at - now) + uniform(0, min(10, wait*0.3))` then retry
      ONCE; else re-raise a fresh GhRateLimitError with reset_at
      populated. The extra uniform term is anti-thundering-herd jitter
      so parallel workers wake at staggered times.
    - After max_attempts transient retries, re-raise the last exception.
    - Log every attempt to stderr:
        [retry 1/3] api repos/foo (GhTransientError status=503) wait=1.24s
        [retry 2/3] api repos/foo (GhRateLimitError status=429) wait=47.3s (reset=2026-04-17T10:45:00Z)
        [rate-limit-probe-failed] endpoint=repos/foo fallback_wait=15s reason=<probe_error>
    """
```

**Thundering-herd mitigation**: Under parallel `--all` scan with `--concurrency=N`, all N workers share the same GitHub auth and hit the same rate-limit counter. When the primary quota is exhausted, all workers will see 429 within seconds of each other. Without jitter, they would all sleep for identical durations and retry simultaneously. With the `uniform(0, min(10, wait*0.3))` jitter on the rate-limit wait, workers wake over a window of up to 10 seconds, spreading the retry storm. This matters most for **secondary rate-limit** (short-term abuse detection, typical reset <60s) where the counter is still near-zero when workers wake — the jitter lets the first worker succeed and subsequent ones staggered. For **primary rate-limit** (hourly bucket), the reset is atomic so thundering-herd is harmless — the counter fully refills. The spec optimizes for the worse case (secondary).

Config (env vars, read at retry time, not startup):
- `GH_MANAGE_MAX_RETRIES` (default `3`, min `1`, max `10`)
- `GH_MANAGE_RATE_LIMIT_WAIT_MAX` (default `60.0`, seconds; `0` disables rate-limit wait)

`run_gh` wrapping:

```python
def run_gh(args: list[str], *, stdin_input: str | None = None) -> str:
    def _attempt() -> str:
        # existing body: subprocess.run + classify on non-zero
        ...
    return retry_gh(_attempt, endpoint=" ".join(args))
```

All existing call sites (`run_gh_api`, direct `run_gh` callers) get retry transparently. No caller changes.

### Rate-limit Reset Probe

`retry_gh` on `GhRateLimitError` calls `gh api rate_limit`. This endpoint:
- Is not counted against the primary rate limit (GitHub docs: `rate_limit` is free).
- Returns `{"resources": {"core": {"reset": <unix_ts>, "remaining": <int>, ...}}}`.

Implementation uses a private helper `_fetch_rate_limit_reset()` that returns `datetime | None`. The helper must NOT go through `retry_gh` itself (no recursion). A failure to fetch the rate-limit info is non-fatal: it falls back to a 15s fixed sleep.

### File Layout After PR 1

- `src/gh_manage/github_client.py` — classifier refactor + `GhTransientError`, `run_gh` wrapped. Grows by ~40 LOC.
- `src/gh_manage/github_retry.py` — **new**, retry engine + rate-limit probe. ~120 LOC.
- `tests/unit/test_github_client.py` — classifier unit tests expanded (status-code dispatch, network markers).
- `tests/unit/test_github_retry.py` — **new**, retry policy tests with mocked subprocess.

## §2 — Architecture (PR 2: Parallel `--all` Scan)

### Threading Model

`concurrent.futures.ThreadPoolExecutor(max_workers=N)`.
- gh subprocess is I/O-bound (fork + wait on HTTP response); threads release the GIL while blocked.
- Each worker independently invokes `_scan_single_repo(entry, ...)`.
- `as_completed` yields futures in completion order for streaming output.

### CLI Surface

```
gh-manage drift --all [--concurrency N] [other flags]
```

- `--concurrency` flag, default 4, clamp to `[1, 16]`. Values outside the range error with a clear message.
- Single repo mode (`gh-manage drift <path> --profile ...`) ignores `--concurrency` silently.
- `--concurrency 1` is valid and produces identical behavior to the pre-PR-2 sequential path (useful for debugging).

### Output Behavior

Threading discipline: **only the main thread writes to stdout/stderr**. Workers return their per-repo output as a value from the future; the main thread iterates `as_completed` and emits output serially. This avoids any need for print locks, guarantees line-atomic output, and keeps progress counters single-threaded.

- **Per-repo results** (stdout for stdout/json/markdown-file modes): main-thread emission inside the `as_completed` loop, in completion order. Each worker returns `(repo_name, status, result_str_or_exc)`.
- **Progress indicator** (stderr, only when `--concurrency > 1`): main-thread increments a local counter as futures complete. Example:

  ```
  [drift --all] 9 repos, concurrency=4
  [drift --all] 3/9 scanned
  [drift --all] 7/9 scanned
  [drift --all] 9/9 scanned in 23.7s
  ```

  Progress lines emit on each completion; at `N>20` the implementation may batch (emit every Nth completion) to avoid log spam.
- **Scan summary** (stderr): collected into a dict keyed by repo name, printed in repos.yml order after all workers finish. Deterministic output for diffing across runs.
- **Issue mode** (`--report-mode issue`): unchanged semantics — each finding posts its own Issue; concurrency just parallelizes the posting.

### Error Handling

Each worker's exception (GhError, ConfigError, GitError, etc.) is caught inside the worker and materialized as a `FAILED` summary entry — mirrors the current sequential code's behavior. One failure does not cancel sibling futures. After PR 1, transient/rate-limit errors are already retried inside the worker; what reaches the top-level `except` is a hard failure.

### File Layout After PR 2

- `src/gh_manage/commands/drift.py` — `_scan_all_repos` refactored, `--concurrency` option added. Net +40 LOC.
- `tests/unit/test_commands_drift.py` — parallel path tests with mocked `_scan_single_repo`.

## §3 — Testing Strategy

### PR 1 Tests

- **Classifier** (`tests/unit/test_github_client.py`):
  - Table-driven HTTP tests: for each status code (401/403-perm/403-rate/404/429/500/502/503/504/418/599), assert correct exception subclass and `status_code`. Include a canary fixture from real `gh api` stderr output asserting `(HTTP 500)` is parseable (breaks loudly if `gh` CLI changes format).
  - Table-driven network-marker tests (case-insensitive substring match):
    - `"error: dial tcp ...: connection refused"` → `GhTransientError` (status_code=None)
    - `"error: no such host: api.github.com"` → `GhTransientError` (status_code=None)
    - `"error: connection refused"` → `GhTransientError` (status_code=None)
    - `"error: request i/o timeout"` → `GhTransientError` (status_code=None)
    - `"error: context deadline exceeded"` → `GhTransientError` (status_code=None)
    - `"error: unknown network thing"` → `GhAPIError` (status_code=None, regression guard)
  - Path-A vs Path-B mutual exclusivity: stderr with BOTH `(HTTP 500)` and `"dial tcp"` → Path A wins (GhTransientError with status_code=500).
  - `status_code` attribute present on all classified exceptions (assert via `hasattr` + value).
- **Retry** (`tests/unit/test_github_retry.py`):
  - Mock `subprocess.run` returning 503 three times, then 200 → assert retry + final success, 3 backoff logs on stderr.
  - Mock 503 × (max_attempts + 1) → assert raises `GhTransientError`.
  - Mock 429 + rate-limit reset within 60s → assert one wait + retry; monkey-patched `time.sleep` receives a value in `[wait_duration, wait_duration + 10)` (jitter range).
  - Mock 429 + rate-limit reset beyond 60s → assert raises a FRESH `GhRateLimitError` (not the original object), with `reset_at` populated, chained via `__cause__` to the original.
  - Mock rate-limit probe failures — three scenarios, all must log `[rate-limit-probe-failed]` to stderr:
    - Probe raises network error → fallback to 15s sleep → retry call succeeds.
    - Probe raises GhAuthError → fallback to 15s sleep → retry call fails with original GhRateLimitError (probe failure does not mask).
    - Probe subprocess times out (simulated via `subprocess.TimeoutExpired`) → fallback to 15s sleep → retry succeeds.
  - env var overrides: `GH_MANAGE_MAX_RETRIES=1` → single retry path; `GH_MANAGE_RATE_LIMIT_WAIT_MAX=0` → rate-limit never waits, always re-raises.
  - Non-retriable errors (401/403-perm/404) pass through on first attempt with zero retry log lines.
  - Probe itself does NOT recurse through `retry_gh` (regression: mock subprocess counts invocations, probe path records exactly 1 call).

### PR 2 Tests

- **Parallel execution** (`tests/unit/test_commands_drift.py`):
  - 3 mock repos, `_scan_single_repo` patched to return deterministic strings — assert stdout stream contains all 3, summary in repos.yml order.
  - One repo raises GhError — assert FAILED in summary, other two succeed.
  - `--concurrency 1` path — summary lines (excluding timing) byte-identical to sequential pre-PR-2 snapshot fixture.
  - `--concurrency 0` / `--concurrency 17` → click BadParameter error.
  - **Timed concurrency smoke**: 4 mock repos, each `_scan_single_repo` sleeps 1.0s; with `--concurrency=4` the total wall-clock is < 1.8s (expect ~1.0s + overhead); with `--concurrency=1` wall-clock is > 3.5s. This guards against GIL-bound regressions — if workers don't actually run in parallel (e.g., refactor moves subprocess blocking into Python computation), this test flips.
  - Output ordering: no interleaved lines within a single repo's output (atomicity guaranteed by main-thread-only emission).

### Integration / Regression

- Full `uv run pytest` on PR 1 and PR 2 (currently 496 tests + new ones).
- Manual self-dogfood on each PR:
  - `uv run gh-manage drift . --profile python-service` (single repo, proves transport retry is transparent).
  - `uv run gh-manage drift --all` (9 repos, proves parallel + retry survives real-world usage).
  - `uv run gh-manage drift --all --concurrency 1` (proves backward-compat).
- Coverage target: maintain ≥85% line coverage on `github_client.py` + `github_retry.py`.

## §4 — Observability

Retry log format (stderr, text):

```
[retry 1/3] api repos/yakkuro/slack-agents/branches/main/protection (GhTransientError status=503) wait=1.24s
[retry 2/3] api repos/yakkuro/slack-agents/branches/main/protection (GhRateLimitError status=429) wait=47.3s (reset at 2026-04-17T10:45:00Z)
[retry 3/3] api repos/yakkuro/slack-agents/branches/main/protection (GhTransientError status=502) wait=4.8s
```

- `wait=` is the time the retry layer slept before the next attempt.
- No structured logging in this spec (deferred to Theme A item 6).

Parallel progress hint emission is defined in §2 Output Behavior (main-thread only). Progress lines use plain newlines (no `\r`) for CI log readability.

Future structured logging (post-v1.4.0, Theme A item 6) will emit JSON to stderr with `{"level": "retry", "attempt": 1, "max_attempts": 3, "endpoint": "...", "error": "...", "wait_sec": 1.24}`. The current text format is intentionally human-friendly for CI debugging.

## §5 — Release Plan

- **PR 1** (`feat: transport retry + HTTP status classifier`)
  - Branch: `feat/resilience-pr1-transport-retry`
  - Tag: `cli/v1.3.0`
  - Release notes: "Drift scanner now retries transient API failures automatically. Error classification is HTTP-status-first."
- **PR 2** (`feat: parallel --all drift scan with --concurrency`)
  - Branch: `feat/resilience-pr2-parallel-scan`
  - Tag: `cli/v1.4.0`
  - Release notes: "`gh-manage drift --all` now scans repos in parallel (default 4 workers; `--concurrency N` to tune). `--concurrency 8+` may interact with GitHub secondary rate-limit — use at your own risk."
- Both PRs follow `docs/release-checklist.md` and use the 4-reviewer protocol from `claude-dotfiles/rules/workflow-review.md`.
- PR 2 depends on PR 1 being merged — PR 2 branch is cut from `main` after PR 1 lands.

### Compatibility & Rollback

- `cli/v1.3.0` retry layer is independent of v1.4.0 parallelism. If a critical retry bug is found after release, patch to `cli/v1.3.1` without blocking v1.4.0.
- `cli/v1.4.0` parallelism depends on v1.3.0's retry layer for rate-limit recovery under concurrent load. Users cannot skip v1.3.0 — the `--concurrency` flag without retry will worsen rate-limit failures.
- If `cli/v1.4.0` is rolled back (e.g., `--concurrency` introduces a regression), users pin to `cli/v1.3.0` which remains functional and is the fallback recommended version. No state incompatibility: neither version persists anything outside the target GitHub repo.
- Both tags are additive-only (new errors, new CLI flag, new env vars). No existing callers' catch clauses break: `GhTransientError` inherits `GhAPIError` so existing `except GhAPIError` handlers catch it transparently.

## §6 — Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| HTTP status regex misses a rare `gh` output format | Error falls through to `GhAPIError`, loses classification | `GhAPIError` still works — we only lose retry eligibility for that one call. Add a test case when encountered. |
| Rate-limit reset probe itself hits rate-limit (circular) | Infinite loop | Probe does NOT go through `retry_gh` (non-recursion is a test invariant). On probe failure, fall back to 15s fixed sleep with `[rate-limit-probe-failed]` log line. |
| Parallel workers thundering-herd on rate-limit reset | All workers wake simultaneously, immediately re-hit the rate-limit (especially secondary), extending total wall-clock | Rate-limit wait includes `uniform(0, min(10, wait*0.3))` jitter. Primary rate-limit: harmless since counter refills atomically. Secondary rate-limit: first worker succeeds, others staggered. Under `--concurrency=8+` with persistent secondary rate-limit, multiple retry rounds may still be needed; documented as "use at your own risk" in release notes. |
| Retry masks a real bug (non-idempotent call retried after partial success) | Duplicate writes | All `gh api` calls in gh-manage are idempotent by design: GET, PUT full-state (labels, protection), DELETE. POST-create-once calls (`ensure_drift_label`) already check for 422 "already exists". Retry is safe. |
| Parallel workers trigger GitHub secondary rate-limit at `--concurrency=16` | Users who push the flag hit abuse detection | Default is 4 (known-safe); flag clamp to 16 is a hard ceiling; retry layer handles the secondary rate limit if hit. Document in release notes that `--concurrency 8+` is "use at your own risk". |
| Streaming `as_completed` output looks chaotic (interleaved per-repo reports) | User confusion | Each repo's output is produced atomically inside the worker (single `click.echo(result_str)` per repo); Python's `print`/`click.echo` is thread-safe at the line level on CPython. |
| Existing tests break due to `.status_code` attribute addition | Regression | `status_code` has a default of `None` on the base class; no existing test constructs `GhError` with positional status-code arg. Verified by grep before merging. |

## §7 — Acceptance Criteria

### PR 1 (`cli/v1.3.0`)

- [ ] `uv run pytest -q` green (expect ≥510 tests; PR 1 adds ~15).
- [ ] `uvx ruff@0.8.0 check src/ tests/` clean.
- [ ] `uvx ruff@0.8.0 format --check src/ tests/` clean.
- [ ] `uv run mypy src/gh_manage/github_client.py src/gh_manage/github_retry.py` clean.
- [ ] New classifier tests cover all HTTP status branches (table-driven).
- [ ] Retry tests cover: transient success after N failures, transient max-attempts exhausted, rate-limit reset near/far, env var override.
- [ ] `uv run gh-manage drift . --profile python-service` exits 0 on this repo (self-dogfood smoke).
- [ ] `GhError.status_code` attribute is set for all HTTP-classified errors (grep assertion in tests).
- [ ] `GhRateLimitError` is now caught by retry layer (regression test asserts it does not propagate unchanged for reset-within-60s case).
- [ ] 4-reviewer protocol clean (Codex + superpowers + SFH + code-reviewer).

### PR 2 (`cli/v1.4.0`)

- [ ] `uv run pytest -q` green (expect +5 tests for parallel path).
- [ ] `uvx ruff@0.8.0 check src/ tests/` clean.
- [ ] `uvx ruff@0.8.0 format --check src/ tests/` clean.
- [ ] `uv run gh-manage drift --all --concurrency 4` completes all 9 current repos with zero FAILED entries (self-dogfood).
- [ ] `uv run gh-manage drift --all --concurrency 1` produces summary lines (per-repo OK/SKIPPED/FAILED entries, in repos.yml order) byte-identical to pre-PR-2 `--all`, excluding the timing line (`[drift --all] N/N scanned in X.XXs`) and the progress indicator (which is only emitted for `--concurrency > 1`).
- [ ] `uv run gh-manage drift --all --concurrency 17` errors with a clear clamp message.
- [ ] Parallel smoke test (mocked `_scan_single_repo` with `time.sleep(1)`) finishes in noticeably less wall-clock time than sequential (`concurrency=4 * 3 repos` finishes in under 2s, not 3s).
- [ ] 4-reviewer protocol clean.

### Combined Post-v1.4.0

- [ ] `gh-manage drift --all` on 20+ repos (Phase 10 target state) completes in <60s on standard connection with zero FAILED entries attributable to flakes.
- [ ] Retry log lines appear in CI weekly cron artifacts (proof that retry is earning its keep, not dead code).

## §8 — Open Questions

None at this time — design decisions Q4-Q6 resolved during 2026-04-17 brainstorming session. Spec-critique round 1 findings (CRITICAL + HIGH) folded into §1 (classifier Path A/B, immutable reset_at), §2 (main-thread-only output), §1 retry layer (anti-herd jitter), §3 (expanded probe-failure + network-marker tests), §5 (rollback section), §6 (thundering-herd risk row), §7 (timing-line-excluded acceptance).

## References

- Top-level design spec: `docs/specs/2026-04-10-gh-manage-design.md`
- Theme A umbrella: [#47](https://github.com/yakkuro/gh-manage/issues/47)
- Phase 10 rollout: [#27](https://github.com/yakkuro/gh-manage/issues/27)
- Doctor spec (prior PR #53): `docs/specs/2026-04-17-doctor-guardrail-design.md`
- Release checklist: `docs/release-checklist.md`
- Review protocol: `claude-dotfiles/rules/workflow-review.md`
