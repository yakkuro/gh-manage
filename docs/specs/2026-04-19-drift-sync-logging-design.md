# drift_sync Structured Logging Design

- **Date**: 2026-04-19
- **Size**: Medium
- **Sizing Rationale**: Greenfield logging infrastructure (no existing `logging` usage in `src/`) but limited scope (drift_sync/ + commands/drift.py). Introduces a new dep (`python-json-logger`), a new module (`gh_manage.logging_config`), a root Click option, ~8 log points across 4 modules, and 2 new test files. Not Small because a new dep + new root CLI option touch surfaces other than the files being modified. Not Large because no existing output is being migrated (drift_sync/ has zero `print`/`click.echo`) and all commands except `drift` are out of scope.
- **Target**: `yakkuro/gh-manage`
- **Goal**: Introduce standard-library `logging` to `drift_sync/` + `commands/drift.py` with a hybrid format (plain text for humans, JSON via env var for agents/cron), a root-group `--log-level` flag, and concrete log points that address [#62](https://github.com/yakkuro/gh-manage/issues/62) HIGH #3 (malformed-timestamp warning) and HIGH #5 (unexpected-exception traceback). Closes Theme A item 6 from [#47](https://github.com/yakkuro/gh-manage/issues/47).

## Background

`gh-manage` has zero `logging` usage in `src/` as of cli/v1.7.0. Developer-oriented signal currently has nowhere to go — warnings that don't warrant a user-facing error (malformed zero-findings timestamps, unexpected exceptions in parallel workers) are silently swallowed (`continue`) or surface as cryptic error strings stripped of their traceback. PR #61 reviewers flagged three such instances in [#62](https://github.com/yakkuro/gh-manage/issues/62); the HIGH items #3 and #5 are the minimal set a structured-logging rollout can fix at the same time as establishing the infrastructure.

The cli/v1.7.0 `drift_sync` split ([PR #61](https://github.com/yakkuro/gh-manage/pull/61)) separated 6 concerns into dedicated submodules, which is the prerequisite for module-scoped loggers: `logging.getLogger(__name__)` yields `gh_manage.drift_sync.checks`, `gh_manage.drift_sync.issue_state`, etc., making log filtering by concern trivial.

User intent (2026-04-19 brainstorming): "logging は正直エージェントに探索しやすいフォーマットが望ましい" — the primary consumers of logs are (a) humans running `gh-manage drift .` locally and (b) Claude Code agents investigating cron failures. A hybrid format satisfies both without forcing JSON on humans tailing stderr.

## Goals

1. Stand up a minimal, correct `logging` configuration module (`gh_manage.logging_config`) that the CLI entry point invokes once, before any subcommand runs.
2. Emit concrete log events at appropriate levels from every `drift_sync/` submodule and from `commands/drift.py`, including the #62 HIGH #3/#5 fixes.
3. Support both plain-text (default) and JSON (opt-in via `GH_MANAGE_LOG_JSON=1`) output on stderr with no runtime-reading format branches in log call sites.
4. Preserve all existing `click.echo`/`click.secho` user-facing output unchanged (logging is additive, not a migration).
5. New regression tests covering (a) the configuration module, (b) each new log point, (c) the format-switch env var.

## Non-goals

- **Logging rollout to other commands** (`apply`, `labels`, `protection`, `init`, `doctor`). Tracked separately — see §9 Follow-ups.
- **Scan correlation (`scan_id` UUID threaded via `LoggerAdapter`)**. YAGNI for single-repo scans; `--all` parallelism interleaves output but `repo` already appears in `_scan_single_repo` messages. Tracked separately.
- **`--log-file` destination flag**. stderr is sufficient; users can redirect. Tracked separately.
- **Migration of existing `click.echo` calls to logging**. Those are user-facing UI output, not logs. They stay.
- **#62's non-scope-A items** (CRITICAL #1/#2, HIGH #4, MEDIUM #6/#7). Still tracked in #62.
- **Log rotation, log aggregation, Slack/Grafana integration**. Out of scope; the env-var hook makes future JSON consumers straightforward.
- **`structlog` as the implementation**. `python-json-logger` is smaller, tighter stdlib interop, and doesn't require rewriting log call sites with `log.bind(...)`-style API.

## §1 — Architecture

### 1.1 Module layout

```
src/gh_manage/
├── logging_config.py         # NEW — ~60 LOC
├── cli.py                    # MODIFY — root group option, call configure_logging()
├── drift_sync/
│   ├── checks.py             # MODIFY — add log points
│   ├── issue_state.py        # MODIFY — add log points (incl. #62 HIGH #3)
│   ├── registry.py           # MODIFY — add log points
│   └── ... (context, adapters, formatters unchanged)
└── commands/
    └── drift.py              # MODIFY — add log points (incl. #62 HIGH #5)
```

### 1.2 Configuration flow

```
gh-manage [--log-level X] <subcommand> [...]
    └── cli.py:main group callback
         └── configure_logging(level=X_or_default, json=bool(GH_MANAGE_LOG_JSON))
              ├── handler = logging.StreamHandler(sys.stderr)
              ├── formatter = JsonFormatter(...) if json else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
              ├── root_logger = logging.getLogger("gh_manage")
              ├── root_logger.setLevel(level); root_logger.addHandler(handler)
              └── (idempotent — safe to call multiple times)

Each module: log = logging.getLogger(__name__)
    → gh_manage.drift_sync.checks
    → gh_manage.drift_sync.issue_state
    → gh_manage.commands.drift
```

Only the `gh_manage` root is configured — third-party libraries (`click`, `pydantic`, `httpx`, etc.) keep their own loggers untouched. No `logging.basicConfig()` call is made (that would affect every package).

### 1.3 New dependency

`python-json-logger` added to `[project].dependencies` in `pyproject.toml`. Rationale: small (~2kLOC pure Python), stdlib-compatible (`JsonFormatter` is a drop-in `logging.Formatter` subclass), and doesn't require call-site changes (contrast with `structlog` which wants `log.bind(event="x", repo=y)` throughout).

## §2 — Configuration contract

### 2.1 `configure_logging(level, json=False)` signature

```python
# src/gh_manage/logging_config.py
from __future__ import annotations

import logging
import os
import sys
from typing import IO, Literal

LogLevel = Literal["debug", "info", "warning", "error"]
_LOG_LEVELS: dict[LogLevel, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def configure_logging(
    level: LogLevel = "warning",
    json: bool | None = None,
    stream: IO[str] | None = None,
) -> None:
    """Configure gh_manage's root logger. Idempotent.

    - level: log level for the `gh_manage` logger tree. Third-party
      packages' loggers are untouched.
    - json: tri-state. Precedence: explicit `json=True/False` wins
      over env var. If `json is None` (default), read
      `GH_MANAGE_LOG_JSON` env var; truthy values ("1", "true", "yes",
      case-insensitive) → JSON, everything else → plain. No env var +
      no explicit arg → plain.
    - stream: destination for log output. Defaults to sys.stderr.
      Production callers (cli.py) should omit this argument. Unit
      tests pass a StringIO to capture output without touching real
      stderr (addresses spec-critique round 1 HIGH).

    Side effect: clears existing handlers on the `gh_manage` logger and
    replaces them with a single StreamHandler bound to `stream`.
    Callers should invoke this exactly once, at CLI entry.

    Immutability: the plain and JSON formatter strings (including
    datefmt) are fixed by this module — not runtime-configurable.
    Changing them requires editing logging_config.py, so `caplog`-based
    tests can rely on the record shape. This is intentional: runtime
    format customization would bloat the contract without real user
    demand (addresses spec-critique round 2 MEDIUM #2).
    """
```

**Format strings** (frozen):
- Plain: `"%(asctime)s %(levelname)s %(name)s: %(message)s"` with `datefmt="%Y-%m-%d %H:%M:%S"`.
- JSON: `pythonjsonlogger.jsonlogger.JsonFormatter` with explicit `datefmt="%Y-%m-%dT%H:%M:%S"` and format string `"%(asctime)s %(levelname)s %(name)s %(message)s"` so the JSON output contains `timestamp`, `level`, `name`, `message` fields plus any `extra={...}` passed by callers. ISO-8601 without microseconds for jq/grep stability (addresses spec-critique MEDIUM #3).

**Idempotency**: called at CLI entry, the function clears any prior handlers attached to the `gh_manage` logger and adds a single fresh one. This avoids duplicate output if the function is somehow called twice (e.g., a test harness that invokes the CLI group callback).

### 2.2 CLI integration

```python
# src/gh_manage/cli.py (shape sketch)
@click.group()
@click.option(
    "--log-level",
    type=click.Choice(["debug", "info", "warning", "error"], case_sensitive=False),
    envvar="GH_MANAGE_LOG_LEVEL",
    default="warning",
    show_default=True,
    help="Logging verbosity for gh_manage modules.",
)
@click.pass_context
def main(ctx: click.Context, log_level: str) -> None:
    """..."""
    from gh_manage.logging_config import configure_logging

    configure_logging(level=log_level.lower())  # type: ignore[arg-type]
```

Env-var precedence: Click's `envvar=` gives `GH_MANAGE_LOG_LEVEL` automatic fallback if `--log-level` is not passed. `GH_MANAGE_LOG_JSON` is read inside `configure_logging` directly (simpler than a separate flag for now).

Defaults matrix:

| Invocation | Effective level | Format |
|---|---|---|
| `gh-manage drift .` | WARNING | plain |
| `gh-manage --log-level info drift .` | INFO | plain |
| `GH_MANAGE_LOG_LEVEL=debug gh-manage drift .` | DEBUG | plain |
| `GH_MANAGE_LOG_JSON=1 gh-manage drift .` | WARNING | JSON |
| `GH_MANAGE_LOG_JSON=1 gh-manage --log-level info drift .` | INFO | JSON |

## §3 — Log points

All log calls use `log = logging.getLogger(__name__)` at module top. Concrete events:

### 3.1 `drift_sync/registry.py`

| Level | When | Example (plain) |
|---|---|---|
| DEBUG | Each check entry | `2026-04-19 10:23:00 DEBUG gh_manage.drift_sync.registry: running check: check_labels` |
| DEBUG | Each check exit w/ count | `DEBUG gh_manage.drift_sync.registry: check_labels returned 2 findings` |

No WARN+ here — registry orchestration is expected to succeed or propagate.

### 3.2 `drift_sync/checks.py`

| Level | When | Example |
|---|---|---|
| DEBUG | `check_labels` calls `labels_api.list_labels(repo)` | `DEBUG gh_manage.drift_sync.checks: fetching labels for yakkuro/llm-kb` |
| WARNING | `check_protection` catches `GhNotFoundError` → treats as empty | `WARNING gh_manage.drift_sync.checks: branch protection not configured on yakkuro/llm-kb@main; treating as empty` (new behavior — previously silent via `except GhNotFoundError: current = {}`) |
| ERROR | `_read_template_content` raises `DriftError` | `ERROR gh_manage.drift_sync.checks: failed to read bundled template 'ci/python-ci.yml'` (emitted alongside the existing `raise DriftError(...)` — caller still sees the exception) |

Note: the WARNING in `check_protection` is a **behavior addition** — it surfaces a previously-silent 404 as a warning. This is a minimal deviation from "no behavior change" but is the explicit point of the logging rollout. The findings produced are unchanged.

### 3.3 `drift_sync/issue_state.py`

| Level | When | Example |
|---|---|---|
| WARNING | **#62 HIGH #3 FIX**: `parse_zero_findings_timestamps` catches `ValueError` | `WARNING gh_manage.drift_sync.issue_state: malformed zero-findings timestamp 'abc123ZZZ' skipped: Invalid isoformat string` |
| INFO | `resolve_drift_issue` creates new issue | `INFO gh_manage.drift_sync.issue_state: created drift issue #42 on yakkuro/llm-kb (5 findings)` |
| INFO | `resolve_drift_issue` updates existing | `INFO gh_manage.drift_sync.issue_state: updated drift issue #42 on yakkuro/llm-kb (5 findings)` |
| INFO | `resolve_drift_issue` auto-closes | `INFO gh_manage.drift_sync.issue_state: closed drift issue #42 on yakkuro/llm-kb (24h zero-drift rule)` |

### 3.4 `commands/drift.py`

| Level | When | Example |
|---|---|---|
| INFO | `_scan_single_repo` start | `INFO gh_manage.commands.drift: scanning yakkuro/llm-kb (profile=python-service)` |
| INFO | `_scan_single_repo` complete | `INFO gh_manage.commands.drift: scan complete for yakkuro/llm-kb: 5 findings (1 high, 3 medium, 1 low)` |
| ERROR | **#62 HIGH #5 FIX**: `_worker` catch-all branch | `log.exception("unexpected error scanning %s", entry.name)` — emits full traceback at ERROR |

The existing `click.echo` user-facing summary output is **not** touched. Logging sits alongside it.

### 3.5 JSON output example

`python-json-logger`'s `JsonFormatter` derives field names from the format string tokens: `%(asctime)s` → `asctime`, `%(levelname)s` → `levelname`, `%(name)s` → `name`, `%(message)s` → `message`. These are the actual keys in the emitted JSON; agent consumers filter on them directly.

```
$ GH_MANAGE_LOG_JSON=1 gh-manage --log-level info drift yakkuro/llm-kb 2>&1 >/dev/null | jq .
{"asctime": "2026-04-19T10:23:00", "levelname": "INFO", "name": "gh_manage.commands.drift", "message": "scanning yakkuro/llm-kb (profile=python-service)"}
{"asctime": "2026-04-19T10:23:02", "levelname": "INFO", "name": "gh_manage.drift_sync.issue_state", "message": "updated drift issue #42 on yakkuro/llm-kb (5 findings)"}
```

Agent queries enabled by JSON:
- `jq 'select(.levelname=="ERROR") | .name + ": " + .message'`
- `jq 'select(.message | contains("yakkuro/llm-kb"))'`
- Combined with `jq -s 'group_by(.levelname) | map({level: .[0].levelname, count: length})'` for severity buckets

## §4 — Deviation from "pure additive"

**One intentional behavior change**: `check_protection` currently swallows `GhNotFoundError` silently (`except GhNotFoundError: current = {}`). After this change, it emits a WARNING log before the swallow. The returned findings and exit code are unchanged; only the log output differs.

All other log points are genuinely additive — they sit alongside existing code without altering control flow.

Full rationale + risk mitigation in [§7](#7--risks--mitigations) under "Behavior change in `check_protection`".

## §5 — Testing strategy

### 5.1 New test files

**`tests/unit/test_logging_config.py`** (new, ~70 LOC):

- `test_configure_logging_default_level_is_warning`: after calling `configure_logging()`, `logging.getLogger("gh_manage").level == WARNING`.
- `test_configure_logging_sets_explicit_level`: `configure_logging(level="info")` → INFO.
- `test_configure_logging_plain_formatter_by_default`: formatter class is `logging.Formatter`.
- `test_configure_logging_json_via_env`: `GH_MANAGE_LOG_JSON=1` + `configure_logging()` → formatter class is `pythonjsonlogger.jsonlogger.JsonFormatter`.
- `test_configure_logging_json_explicit_arg`: `configure_logging(json=True)` → JSON regardless of env var.
- `test_configure_logging_idempotent`: call twice, assert exactly one handler on the `gh_manage` logger.
- `test_configure_logging_does_not_affect_third_party_loggers`: `logging.getLogger("click").handlers` unchanged; `logging.getLogger("gh_manage.drift_sync").handlers` inherits from `gh_manage`.

**`tests/unit/drift/test_logging_events.py`** (new, ~90 LOC):

Each uses pytest's `caplog` fixture. Tests:
- `test_check_protection_warns_on_not_found`: mock `protection_api.get_branch_protection` to raise `GhNotFoundError`; assert `WARNING` record at `gh_manage.drift_sync.checks` with `"branch protection not configured"` in message.
- `test_parse_zero_findings_warns_on_malformed`: pass a comment with `<!-- scan:zero-findings:NOT_A_DATE -->`; assert `WARNING` at `gh_manage.drift_sync.issue_state`. **This is the #62 HIGH #3 regression guard.**
- `test_resolve_drift_issue_logs_created_event`: mock `issues_api.create_issue` → assert `INFO` record with `"created drift issue"`.
- `test_resolve_drift_issue_logs_updated_event`: similar.
- `test_resolve_drift_issue_logs_closed_event`: similar, include the 24h-rule stubbing.
- `test_worker_logs_exception_with_traceback`: patch `gh_manage.commands.drift._scan_single_repo` with `mocker.patch(..., side_effect=TypeError("sentinel"))`; invoke `_worker` directly with a stub `RepoEntry`; assert `caplog.records[-1].levelno == logging.ERROR`, `caplog.records[-1].name == "gh_manage.commands.drift"`, `caplog.records[-1].exc_info is not None`, and `caplog.records[-1].exc_info[0] is TypeError`. **This is the #62 HIGH #5 regression guard.**
- `test_debug_events_hidden_at_warning_level`: `configure_logging(level="warning")`, run `check_labels` against empty mock, assert no DEBUG records were propagated (verify default quiet behavior).

### 5.2 Integration verification

After implementation:
- `gh-manage drift .` emits nothing at default level (WARNING floor, no WARNs from a clean repo).
- `gh-manage --log-level info drift .` emits the INFO `scan complete ...` line on stderr.
- `GH_MANAGE_LOG_JSON=1 gh-manage drift . 2>&1 >/dev/null | head -1 | jq .` returns valid JSON.
- `gh-manage drift --all 2>&1 | grep -c ERROR` returns 0 on a clean cron.

### 5.3 Existing suite impact

No existing test modifications required. caplog's default propagation behavior means tests that don't check log output are unaffected.

## §6 — Release plan

- **Tag**: `cli/v1.8.0` — CLI-track minor. Additive (new dep, new CLI option, new log output). No public API removed, no test mock paths changed, no existing output migrated.
- **Release notes** call out: new dep, new `--log-level` option + env vars, JSON opt-in, #62 HIGH #3/#5 resolved.
- **Cron workflow update (separate PR, not this one)**: the daily drift scan reusable workflow (`.github/workflows/reusable-pr-gate.yml`?) should set `GH_MANAGE_LOG_JSON=1` and `GH_MANAGE_LOG_LEVEL=info` so the next cron's logs are structured. Tracked as a follow-up — this spec only ships the CLI capability.

## §7 — Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `configure_logging` called before `sys.stderr` is fully initialized (edge case in testing harness) | StreamHandler binds to wrong stream | `configure_logging` accepts a `stream` parameter (default `None` → `sys.stderr` resolved at call time). Unit tests pass a `StringIO`; the signature is part of the contract (§2.1). |
| `python-json-logger` maintenance lapse | New dep becomes stale | Minor risk — package is stable, last update 2025, low surface area. Pin to `>=2.0,<3.0` initially. |
| Library consumers (not applicable yet) importing `gh_manage.drift_sync` and inheriting our logger config | Pollution of their log setup | We only configure `gh_manage` logger tree, not root. Library consumers calling into our code will see our `gh_manage.*` loggers propagate to their root — standard Python behavior. If they configure a root handler, output appears there; if not, our handler is silent (only fires when `configure_logging` is called by the CLI entry). |
| **Behavior change in `check_protection`** (silent 404 → WARNING) surprises a test | Test fails, or users perceive "scope creep" | **Justification**: swallowing `GhNotFoundError` silently defeats the entire point of adding logging — the path that most warrants operational visibility (branch protection absent on a repo we expect it on) is exactly where drift_sync previously emitted no signal. The change is strictly log-side: findings, returned tuples, and exit codes are unchanged. **Coverage**: `test_check_protection_warns_on_not_found` (§5.1) asserts the WARNING; no existing tests assert log silence on this path (verified by grep). **Scope**: this is the ONLY behavior change in the PR; all other logging is additive. Called out in §4 so reviewers can accept it upfront. |
| Log output on stderr interferes with tests that capture stderr | Test output noise | pytest caplog captures at the logger level, not via stderr capture, so normal test stderr capture is unaffected. |
| `_worker`'s broad `except Exception` + new `log.exception` duplicates output | Console spam on parallel failures | `log.exception` + the `FAILED ({exc})` user-facing summary are complementary (log is detailed, summary is compact). Accept the minor duplication. |

## §8 — Acceptance Criteria

- [ ] `src/gh_manage/logging_config.py` exists, ≤100 LOC, with the signature from §2.1.
- [ ] `pyproject.toml` adds `python-json-logger` to `[project].dependencies`; `uv sync` regenerates `uv.lock`.
- [ ] `cli.py`'s root group accepts `--log-level` with `envvar="GH_MANAGE_LOG_LEVEL"` and default `"warning"`.
- [ ] Each `drift_sync/` submodule and `commands/drift.py` has `log = logging.getLogger(__name__)` at module top.
- [ ] The 8 log points from §3 are emitted at the specified levels.
- [ ] `uv run pytest -q` passes — baseline + ~14 new tests across 2 new files.
- [ ] `uvx ruff@0.8.0 check src/ tests/` clean.
- [ ] `uv run mypy src/` clean.
- [ ] Manual: `gh-manage drift .` produces no log output (WARNING floor on a clean local repo).
- [ ] Manual: `gh-manage --log-level debug drift .` emits DEBUG lines for each check entry/exit.
- [ ] Manual: `GH_MANAGE_LOG_JSON=1 gh-manage drift . 2>&1 >/dev/null | jq .` returns valid JSON for every line.
- [ ] Manual: crafting an Issue comment with a malformed `<!-- scan:zero-findings:XXX -->` and running scan emits the WARNING (#62 HIGH #3).
- [ ] Manual: forcing a `TypeError` in `_scan_single_repo` via a deliberate bug reproduces `log.exception` with full traceback on stderr (#62 HIGH #5).
- [ ] Version bumped to `1.8.0` across `__init__.py`, `pyproject.toml`, `test_sanity.py`, `uv.lock`.
- [ ] PR open, 4-reviewer protocol clean, merged, `cli/v1.8.0` tagged + released.
- [ ] 3 follow-up Issues filed: (a) other-commands logging, (b) scan_id correlation, (c) `--log-file` flag.

## §9 — Follow-ups (out of scope, filed as separate Issues)

Before this spec is marked done:
- **Issue A**: "Roll out structured logging to remaining gh-manage commands" — apply/labels/protection/init/doctor. Pattern is set by cli/v1.8.0; follow-up is mechanical.
- **Issue B**: "Add scan_id correlation to drift_sync logs" — `LoggerAdapter` or `ContextVar` thread of a UUID4 through the scan, visible in every log record's `extra`. Enables per-scan log filtering in JSON mode.
- **Issue C**: "Add `--log-file` flag to gh-manage CLI" — write logs to a file instead of (or in addition to) stderr. Useful for long cron runs.

After this spec ships:
- **Cron workflow update**: set `GH_MANAGE_LOG_JSON=1` and `GH_MANAGE_LOG_LEVEL=info` in the daily `drift --all` cron so cron run artifacts are structured. Separate consumer-side PR.

## §10 — Open Questions

None. Design decisions resolved during 2026-04-19 brainstorming:
- Scope: drift_sync/ + commands/drift.py only (per user).
- Format: hybrid (plain default, JSON via `GH_MANAGE_LOG_JSON` env var).
- Level config: `--log-level` Click option + `GH_MANAGE_LOG_LEVEL` env var; default `WARNING`.
- Dep: `python-json-logger` (rejected `structlog` as over-engineered for this scope).
- `check_protection` GhNotFoundError WARNING: intentional behavior addition, flagged in §4.
- scan_id correlation, `--log-file`, other-commands rollout: all deferred to follow-up Issues.

## References

- Theme A umbrella: [`#47`](https://github.com/yakkuro/gh-manage/issues/47) (item 6 = this spec).
- Follow-up to drift_sync split: [`#61`](https://github.com/yakkuro/gh-manage/pull/61) / [`cli/v1.7.0`](https://github.com/yakkuro/gh-manage/releases/tag/cli/v1.7.0).
- Pre-existing error-handling Issue: [`#62`](https://github.com/yakkuro/gh-manage/issues/62) (this spec resolves HIGH #3 and HIGH #5).
- `python-json-logger`: https://github.com/madzak/python-json-logger
- Current `drift_sync.py` tree: `src/gh_manage/drift_sync/{checks,issue_state,registry}.py` at `b6a5047` on main.
- Current CLI entry: `src/gh_manage/cli.py`.
