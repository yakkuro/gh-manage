# Structured Logging Follow-ups Design (cli/v1.9.0)

- **Date**: 2026-04-20
- **Size**: Medium
- **Sizing Rationale**: Three follow-up Issues (#63 rollout, #64 scan_id, #65 `--log-file`) bundled into one CLI-track minor release. Scope: extend `logging_config.py`, add a ContextVar-based correlation id, add a root-group CLI option + validator, and wire `log = getLogger(__name__)` + concrete log points across 5 remaining commands (apply/labels/protection/init/doctor). Estimated ~200 LOC production, ~400 LOC tests, ~10 files modified + ~6 new test files. Not Small because it touches both shared infrastructure (logging_config, cli.py) and command surface, with one new cross-module concept (scan_id ContextVar). Not Large because no breaking change, no schema migration, and the `logging_config.py` baseline from cli/v1.8.0 is reused as-is for format strings.
- **Target**: `yakkuro/gh-manage`
- **Goal**: Close out the structured-logging story the cli/v1.8.0 PR (#66) opened — Issues #63, #64, #65 — as a single `cli/v1.9.0` release. Provide (a) consistent INFO/WARNING coverage across every `commands/*.py` module, (b) per-scan correlation via a `scan_id` UUID4 that flows through JSON output, and (c) a `--log-file` destination with fail-fast validation for cron use.

## Background

cli/v1.8.0 (PR #66, commit `e71a9a8`) landed the structured-logging baseline:

- `gh_manage.logging_config.configure_logging(level, json, stream)` — idempotent, stderr-only
- root `--log-level` Click option + `GH_MANAGE_LOG_LEVEL` / `GH_MANAGE_LOG_JSON` envvars
- hybrid plain / JSON formatter (immutable format strings so caplog tests remain stable)
- 8 concrete log points across `drift_sync/` + `commands/drift.py`
- `_scan_worker` emits `log.warning` for domain errors and `log.exception` for unknown exceptions

Three follow-up Issues were filed alongside that PR:

- **#63** Roll out logging to remaining commands (`apply`, `labels`, `protection`, `init`, `doctor`)
- **#64** Add scan_id correlation (UUID4) to drift_sync logs
- **#65** Add `--log-file` destination flag + `GH_MANAGE_LOG_FILE` envvar

They are independent on the code level (non-overlapping files on most points) but share the same logging infrastructure. Bundling them into one spec/PR/release keeps the story coherent, the release-notes audience singular, and the review cost amortized. The tradeoff (larger single PR) is mitigated by per-Issue test isolation — `tests/unit/test_cli_log_file.py`, `tests/unit/drift/test_scan_id_propagation.py`, and `tests/unit/commands/test_<cmd>_logging.py` can be reviewed independently.

User intent (2026-04-20 brainstorming): the three Issues are the natural conclusion of the cli/v1.8.0 work; no new scope. Explicit decisions:

- Q1 (PR structure) → **A: single PR, cli/v1.9.0**
- Q2 (scan_id mechanism) → **C: ContextVar with JSON formatter auto-attach**
- Q3 (`--log-file` output) → **A: dual output (stderr + file)**
- Q4 (file validation) → **A: fail-fast validate at CLI startup → `UsageError`**

## Goals

1. **#63 coverage**: every `commands/{apply,labels,protection,init,doctor}.py` module has `log = getLogger(__name__)`, entry/exit INFO, and WARNING on silent-fallback branches (404 treated as empty, silent exception catches).
2. **#64 correlation**: drift scans (both single-repo and `--all` parallel) attach a per-scan UUID4 to every log record; JSON output includes the `scan_id` field; plain output is unchanged; non-drift commands are unaffected.
3. **#65 destination**: `gh-manage --log-file PATH` (and `GH_MANAGE_LOG_FILE` envvar) write to `PATH` **in addition to** stderr; invalid path (missing parent, no write permission) exits with `UsageError` at startup before any subcommand runs.
4. **No behavior regression**: existing `click.echo` / `click.secho` user-facing output is unchanged; cli/v1.8.0 test suite + drift_sync tests continue to pass.
5. **Regression coverage**: each new log point has a caplog-based test; each validator branch has a test; scan_id propagation across threads has a test.

## Non-Goals

- **`scan_id` correlation for non-drift commands** (`apply`, `labels`, `protection`, `init`, `doctor`). No operational need today — a single-shot `apply .` has no natural "scan boundary" to correlate against. Tracked as an ad-hoc Issue only if demand arises.
- **Log rotation, size limits, retention policies**. External tools (logrotate, GitHub Actions artifact retention, systemd journal) handle this. `configure_logging` does not add `RotatingFileHandler`.
- **Migration of existing `click.echo` output to logging**. The two layers are intentionally distinct: `click.echo` is user-facing UI, `logging` is operational signal. No migration in this PR.
- **Silent fallback on `--log-file` write failure**. Q4 rejected — fail-fast is the thought-out position.
- **Rolling out INFO verbosity granularity** (DEBUG per-check, per-field diff). YAGNI — the current 8 drift log points proved sufficient in PR #66 operational testing.
- **`issues.py`** remains a stub (pre-v0.5.0). No log added there.
- **Refactoring shared helpers** beyond the one-file decorator cleanup described in §4.3. No broader cleanup.

## §1 — Architecture overview

### 1.1 Module-level surface

```
src/gh_manage/
├── logging_config.py                  MODIFY (+~30 LOC)
│   └── _ScanIdJsonFormatter (new)    # subclass of JsonFormatter
│   └── configure_logging(..., log_file=None)  # new kwarg
├── cli.py                             MODIFY (+~15 LOC)
│   └── --log-file option + envvar    # root click group
│   └── _validate_log_file(path)      # fail-fast validator
├── drift_sync/
│   ├── context.py                    MODIFY (+~5 LOC)
│   │   └── scan_id_var: ContextVar   # shared across drift_sync
│   └── __init__.py                   MODIFY (+~1 LOC)
│       └── re-export scan_id_var
├── commands/
│   ├── drift.py                      MODIFY (+~5 LOC)
│   │   └── scan_id_var.set/reset in _scan_single_repo
│   ├── apply.py                      MODIFY (+~15 LOC, log points)
│   ├── labels.py                     MODIFY (+~20 LOC, log + decorator cleanup)
│   ├── protection.py                 MODIFY (+~15 LOC, log points)
│   ├── init.py                       MODIFY (+~15 LOC, log points)
│   └── doctor.py                     MODIFY (+~10 LOC, log points)

tests/unit/
├── test_logging_config.py             EXTEND (+~60 LOC)
├── test_cli_log_file.py               NEW     (~50 LOC)
├── drift/
│   └── test_scan_id_propagation.py    NEW     (~60 LOC)
└── commands/
    ├── test_apply_logging.py          NEW     (~50 LOC)
    ├── test_labels_logging.py         NEW     (~50 LOC)
    ├── test_protection_logging.py     NEW     (~50 LOC)
    ├── test_init_logging.py           NEW     (~40 LOC)
    └── test_doctor_logging.py         NEW     (~40 LOC)
```

Estimated total: ~200 LOC production, ~400 LOC tests, 10 files modified + 6 new test files.

### 1.2 Independence across the three Issues

| Concern (Issue) | Files touched | Conflicts with |
|---|---|---|
| scan_id (#64) | `drift_sync/context.py`, `drift_sync/__init__.py`, `commands/drift.py`, `logging_config.py` (formatter only) | — |
| `--log-file` (#65) | `logging_config.py` (configure_logging kwarg), `cli.py` | — |
| rollout (#63) | `commands/{apply,labels,protection,init,doctor}.py` | — |

Only `logging_config.py` is touched by both #64 and #65, but they hit disjoint sections (`_ScanIdJsonFormatter` class vs `configure_logging` handler list). Implementation order is free.

### 1.3 Invocation flow (after this spec ships)

```
$ gh-manage --log-level info --log-file /tmp/ghm.log drift --all
    └── cli.py:main(log_level, log_file)
         ├── _validate_log_file(Path("/tmp/ghm.log"))  # UsageError on failure
         └── configure_logging(level="info", log_file=Path("/tmp/ghm.log"))
              ├── formatter = _ScanIdJsonFormatter(...) if $GH_MANAGE_LOG_JSON else Formatter(...)
              ├── handlers = [StreamHandler(stderr), FileHandler("/tmp/ghm.log", "a")]
              └── gh_logger.handlers = handlers

    └── drift.py:_scan_all_repos → ThreadPoolExecutor
         └── _scan_worker(entry) (per thread)
              └── _scan_single_repo(entry.name, ...)
                   ├── scan_id_var.set(str(uuid4()))   # per-repo UUID
                   ├── log.info("scanning ...")        # scan_id auto-attached
                   ├── run_all_checks(ctx)             # every sub-log inherits scan_id
                   └── scan_id_var.reset(token)        # cleanup
```

## §2 — scan_id propagation (#64)

### 2.1 ContextVar definition

In `src/gh_manage/drift_sync/context.py` (lowest-layer drift_sync module, imports only stdlib + `gh_manage.models.*`):

```python
from contextvars import ContextVar

# Per-scan correlation id, set at the entry of _scan_single_repo and
# reset on exit (including exception paths). Default empty string means
# "not inside a scan" — the JSON formatter skips the field in that case.
scan_id_var: ContextVar[str] = ContextVar("scan_id", default="")
```

Re-exported via `src/gh_manage/drift_sync/__init__.py` for external access (tests, future cross-module consumers).

Rationale for `context.py` placement: `logging_config.py` needs to read `scan_id_var` from its formatter. Putting the ContextVar in `drift_sync/context.py` (which has zero downstream drift_sync dependencies) keeps the import DAG one-directional: `logging_config → drift_sync.context`. Placing it in `logging_config.py` would invert the DAG and require lazy imports.

### 2.2 Set/reset at scan entry

In `src/gh_manage/commands/drift.py:_scan_single_repo`:

```python
from uuid import uuid4
from gh_manage.drift_sync.context import scan_id_var


def _scan_single_repo(owner_repo, ...):
    token = scan_id_var.set(str(uuid4()))
    try:
        log.info("scanning %s (profile=%s)", owner_repo, profile_name)
        # ... existing body unchanged ...
    finally:
        scan_id_var.reset(token)
```

Key decisions:

- **`_scan_single_repo` (not `_scan_worker`)**: single-repo mode (`gh-manage drift .`) bypasses `_scan_worker`. Setting in `_scan_single_repo` covers both paths.
- **Full UUID4 (36 chars, hyphenated)**: enough entropy for any conceivable scale (22 repos × N scans/day for years). Hyphenated form is human-scannable in log output and `jq`-friendly.
- **`try/finally` around set/reset**: guarantees ContextVar cleanup even when a check raises; prevents a stale scan_id from bleeding into subsequent unrelated log calls made in the same thread (relevant to tests, not production since CLI exits after scan).

### 2.3 JSON formatter auto-attach

In `src/gh_manage/logging_config.py`, subclass `JsonFormatter` to read `scan_id_var` at record-format time:

```python
from pythonjsonlogger.jsonlogger import JsonFormatter as _BaseJsonFormatter
from gh_manage.drift_sync.context import scan_id_var


class _ScanIdJsonFormatter(_BaseJsonFormatter):
    """JSON formatter that injects the current scan_id ContextVar.

    When called outside a drift scan (e.g., from `apply` / `labels` /
    etc.), scan_id_var.get() returns the default empty string, and the
    field is omitted from the JSON output.
    """
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        sid = scan_id_var.get()
        if sid:
            log_record["scan_id"] = sid
```

`configure_logging` switches to `_ScanIdJsonFormatter` in JSON mode (replaces the current `JsonFormatter`). Plain-text mode uses the stdlib `logging.Formatter` unchanged — scan_id is intentionally not included in plain output (the user-intent "agent-friendly format" lives in JSON).

### 2.4 Thread propagation guarantee

`ThreadPoolExecutor.submit` in Python ≥3.9 copies the caller's context to the worker thread at submit time. Our design sets `scan_id_var` **inside** the worker (in `_scan_single_repo`), not in the caller. This means each worker thread's local context holds its own independent value; parallel `--all` runs do not interleave scan_ids.

The test `test_scan_id_isolated_per_worker_thread` (§5.3) asserts this empirically.

### 2.5 Example JSON output

```
$ GH_MANAGE_LOG_JSON=1 gh-manage --log-level info drift --all 2>&1 >/dev/null | jq .
{
  "asctime": "2026-04-20T10:23:00",
  "levelname": "INFO",
  "name": "gh_manage.commands.drift",
  "message": "scanning yakkuro/llm-kb (profile=python-service)",
  "scan_id": "550e8400-e29b-41d4-a716-446655440000"
}
{
  "asctime": "2026-04-20T10:23:02",
  "levelname": "INFO",
  "name": "gh_manage.drift_sync.issue_state",
  "message": "updated drift issue #42 on yakkuro/llm-kb (5 findings)",
  "scan_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Useful agent queries:

```bash
# Find all records for one scan
jq 'select(.scan_id == "550e8400-...")' logs.ndjson

# Count records per scan
jq -s 'group_by(.scan_id) | map({scan: .[0].scan_id, count: length})' logs.ndjson

# Find scans with ERROR records
jq -s 'group_by(.scan_id) | map(select(any(.; .levelname == "ERROR")))' logs.ndjson
```

## §3 — `--log-file` flag (#65)

### 3.1 Root click option

In `src/gh_manage/cli.py`:

```python
@click.option(
    "--log-file",
    type=click.Path(dir_okay=False, path_type=Path),
    envvar="GH_MANAGE_LOG_FILE",
    default=None,
    help=(
        "Write logs to this file in addition to stderr. Also honours "
        "GH_MANAGE_LOG_FILE. Parent directory must exist and be writable; "
        "otherwise the command exits with a usage error."
    ),
)
def main(log_level: str, log_file: Path | None) -> None:
    level: LogLevel = log_level.lower()  # type: ignore[assignment]
    if log_file is not None:
        _validate_log_file(log_file)
    configure_logging(level=level, log_file=log_file)
```

### 3.2 Fail-fast validator

```python
def _validate_log_file(path: Path) -> None:
    """Raise UsageError if the log file cannot be written to.

    Runs at CLI startup, before any subcommand. Rejects missing parent
    directory and write-permission failures with actionable messages.
    Creating the file (0-byte touch via append-open) is intentional —
    users who pass --log-file have opted into file creation.
    """
    parent = path.parent.resolve()
    if not parent.is_dir():
        raise click.UsageError(
            f"--log-file parent directory does not exist: {parent}. "
            f"Create it or choose a different path."
        )
    try:
        with path.open("a", encoding="utf-8"):
            pass
    except OSError as e:
        raise click.UsageError(
            f"Cannot write to --log-file {path}: {e}. "
            f"Check permissions and disk space."
        ) from e
```

### 3.3 `configure_logging` dual-handler extension

```python
def configure_logging(
    level: LogLevel = "warning",
    json: bool | None = None,
    stream: IO[str] | None = None,
    log_file: Path | None = None,
) -> None:
    """Configure gh_manage's logger tree. Idempotent.

    New kwarg in cli/v1.9.0:
    - log_file: if not None, a FileHandler (append mode, utf-8) is added
      alongside the stderr StreamHandler. Both handlers share the same
      formatter. Caller is responsible for validating the path before
      calling this function (cli.py uses _validate_log_file).
    """
    if json is None:
        json = _env_says_json()
    if stream is None:
        stream = sys.stderr

    formatter: logging.Formatter = (
        _ScanIdJsonFormatter(_JSON_FORMAT, datefmt=_JSON_DATEFMT)
        if json
        else logging.Formatter(_PLAIN_FORMAT, datefmt=_PLAIN_DATEFMT)
    )

    handlers: list[logging.Handler] = [logging.StreamHandler(stream=stream)]
    if log_file is not None:
        handlers.append(
            logging.FileHandler(str(log_file), mode="a", encoding="utf-8")
        )
    for h in handlers:
        h.setFormatter(formatter)

    gh_logger = logging.getLogger("gh_manage")
    gh_logger.handlers[:] = handlers
    gh_logger.setLevel(_LOG_LEVELS[level])
    gh_logger.propagate = False
```

### 3.4 Decisions table

| Decision | Choice | Rationale |
|---|---|---|
| FileHandler mode | `"a"` (append) | daily cron appends to existing log; logrotate `copytruncate` compatible |
| Format for file | same as stderr (plain or JSON) | unified decision; no per-destination formatter |
| Encoding | `utf-8` | consistent with existing `_shared.format_files_diff`, `DriftOutputError` |
| Thread safety | rely on `logging.FileHandler` internal lock | 22-repo parallel `--all` uses a single handler; writes are serialized |
| Log rotation / retention | **out of scope** | external tools (logrotate, GHA artifact retention) |
| Validation failure | `UsageError` at startup (fail-fast) | Q4 decision |
| `--log-file` without `--log-level info` | file still receives WARNING floor | same level applies to both handlers (no per-destination level) |

### 3.5 Defaults matrix

| Invocation | stderr | file |
|---|---|---|
| `gh-manage drift .` | WARNING+ plain | — |
| `gh-manage --log-file /tmp/x.log drift .` | WARNING+ plain | WARNING+ plain |
| `GH_MANAGE_LOG_JSON=1 gh-manage --log-file /tmp/x.log drift .` | JSON | JSON |
| `GH_MANAGE_LOG_FILE=/tmp/x.log gh-manage drift --all` | plain | plain (22 scan_ids interleaved) |
| `gh-manage --log-file /nonexistent/x.log apply .` | — | — (`UsageError`, exit 2) |

## §4 — Command rollout (#63)

### 4.1 Pattern

Every `commands/*.py` module (except `issues.py` stub):

1. `log = logging.getLogger(__name__)` at module top
2. **Entry INFO**: one line at the start of each click command body (after input validation), recording key args
3. **Completion INFO**: one line before successful return (summary: how many changes applied, etc.)
4. **WARNING**: existing silent-fallback branches (404 treated as empty, silent `except`)
5. **No ERROR**: domain errors bubble to `@handle_errors` which converts to `ClickException` (stderr "Error: ..." + exit 1). A second log.error would be duplicative.

### 4.2 Per-command log points

**`commands/apply.py`**

| Level | Location | Message template |
|---|---|---|
| INFO | `apply()` after UsageError check | `apply invoked: repo=%s profile=%s apply=%s also_labels=%s also_protection=%s` |
| WARNING | `except GhNotFoundError: current_protection = {}` (L123) | `branch protection not configured on %s@main; treating as empty` |
| WARNING | `except DoctorCheckError` (L213) | `post-apply doctor check failed: %s` (alongside existing click.echo) |
| INFO | end of successful body (L195 area) | `apply complete: repo=%s file_changes=%d label_changes=%d protection_changes=%d` |

**`commands/labels.py`**

| Level | Location | Message template |
|---|---|---|
| INFO | `sync()` entry | `labels sync invoked: repo=%s apply=%s prune=%s` |
| INFO | `sync()` after apply_diff | `labels sync complete: repo=%s changes=%d` |
| INFO | `diff_cmd()` entry | `labels diff invoked: repo=%s prune=%s` |
| INFO | `show()` entry | `labels show invoked: repo=%s` |
| — | (no WARNING — label ops have no silent fallbacks) | — |

**`commands/protection.py`**

| Level | Location | Message template |
|---|---|---|
| INFO | `sync()` entry | `protection sync invoked: repo=%s profile=%s apply=%s downgrade_allowed=%s` |
| WARNING | `except GhNotFoundError: current = {}` (L152, L240) | `branch protection not configured on %s@main; treating as empty` |
| WARNING | downgrade path entered with `--apply` | `applying protection downgrade on %s@main: %d field(s) weakened` |
| INFO | `sync()` successful return (L204) | `protection apply complete: repo=%s fields=%d` |
| INFO | `diff_cmd()` entry | `protection diff invoked: repo=%s profile=%s` |

**`commands/init.py`**

| Level | Location | Message template |
|---|---|---|
| INFO | `init()` after UsageError check | `init invoked: repo=%s profile=%s apply=%s` |
| WARNING | `except GhNotFoundError: current_protection = {}` (L119) | `branch protection not configured on %s@main; treating as empty` |
| WARNING | critical findings triggered rollback (L201) | `init aborting: critical doctor findings=%d, rolling back %d file(s)` |
| WARNING | rollback `unlink` failure (L213) | `init rollback: cannot delete %s: %s` |
| INFO | end of successful body (L233) | `init complete: repo=%s file_changes=%d label_changes=%d protection_changes=%d` |

**`commands/doctor.py`**

| Level | Location | Message template |
|---|---|---|
| INFO | `doctor_cmd()` entry | `doctor invoked: target=%s profile=%s report_mode=%s` |
| WARNING | `_derive_repo_label` `except Exception` (L43) | `could not derive owner/repo from path %s: %s` |
| INFO | before final exit decision | `doctor complete: target=%s findings=%d blocking=%d` |

**`commands/issues.py`**: stub (exits 1 "not implemented"). Do not log — the stub will be replaced in cli/v0.5.0 work.

### 4.3 Decorator cleanup in `labels.py`

`src/gh_manage/commands/labels.py` defines its own `_handle_errors` decorator (L50–63) that is functionally identical to `_shared.handle_errors` (imported by every other command). Under the umbrella of this rollout:

- Delete the local `_handle_errors` (L50–63) and its `_F` TypeVar import (L24)
- Import `from gh_manage.commands._shared import handle_errors`
- Replace `@_handle_errors` decorators on `sync`, `diff_cmd`, `show` with `@handle_errors`
- Delete now-unused imports: `functools`, `TypeVar`, `Callable`, `Any`

Scope limit: only this decorator consolidation. No migration of `click.echo` to `log.info`, no reorganization of `labels.py`, no touching `_format_diff`.

Rationale: (1) Issue #38 extracted `_shared.handle_errors` specifically to remove this duplication; `labels.py` was missed in that sweep. (2) Noticed naturally while reading for log point placement. (3) Rollout touches every `commands/` file anyway — cleanup cost is marginal.

### 4.4 Issue labels ignored for log messages

Log messages do not interpolate `Finding.severity`, `DriftIssue.state`, or any other pattern-matched enum. Interpolation uses only plain strings (`repo`, `profile`, counts). This keeps log emission cheap and avoids coupling log format to domain types.

## §5 — Testing strategy

### 5.1 `tests/unit/test_logging_config.py` (extend, +~60 LOC)

| Test name | Assertion |
|---|---|
| `test_configure_logging_with_log_file_adds_file_handler` | after `configure_logging(log_file=tmp_path/"x.log")`, `getLogger("gh_manage").handlers` has exactly 2 entries (StreamHandler + FileHandler) |
| `test_log_file_mode_is_append` | write "existing\n" to file, call configure_logging + log a message, assert final file content starts with "existing\n" |
| `test_log_file_encoding_is_utf8` | log a message containing "日本語テスト", read file as bytes, decode as utf-8, assert substring present |
| `test_log_file_and_stderr_get_same_record` | StringIO stream + tmp file, log one message, assert both contain the message |
| `test_json_formatter_includes_scan_id_when_set` | set `scan_id_var`, configure JSON, log → parse output line as JSON, assert `scan_id` field equals the set value |
| `test_json_formatter_omits_scan_id_when_unset` | ContextVar default, configure JSON, log → parse, assert `"scan_id" not in parsed` |
| `test_plain_formatter_omits_scan_id` | set `scan_id_var`, configure plain, log → assert scan_id string not present in output |
| `test_file_handler_inherits_json_formatter` | configure with log_file + GH_MANAGE_LOG_JSON=1 → file handler's formatter is `_ScanIdJsonFormatter` |

### 5.2 `tests/unit/test_cli_log_file.py` (new, ~50 LOC)

| Test name | Assertion |
|---|---|
| `test_validate_log_file_rejects_missing_parent` | `_validate_log_file(Path("/nonexistent/dir/x.log"))` → `UsageError` mentioning "parent directory does not exist" |
| `test_validate_log_file_rejects_unwritable` | tmp dir with `chmod 0o555`, child path → `UsageError` mentioning "Cannot write" |
| `test_validate_log_file_accepts_new_path` | `tmp_path / "new.log"` → no error, file exists after call (0-byte) |
| `test_validate_log_file_accepts_existing_path` | pre-existing file → no error, content preserved |
| `test_env_var_log_file_honored_via_cli` | CliRunner invoke `gh-manage` with `env={"GH_MANAGE_LOG_FILE": str(tmp_path/"x.log")}`, no `--log-file` flag → file gets records |
| `test_cli_flag_overrides_env_var` | both set with different paths → flag wins (`click.Option(envvar=...)` semantics; assert flag path has records, env path does not) |

### 5.3 `tests/unit/drift/test_scan_id_propagation.py` (new, ~60 LOC)

| Test name | Assertion |
|---|---|
| `test_scan_id_set_at_single_repo_entry` | mock `run_all_checks` to capture `scan_id_var.get()` during scan; assert captured value is UUID4 format (`uuid.UUID(captured)` succeeds) |
| `test_scan_id_reset_after_single_repo_exit` | call `_scan_single_repo(...)` (with full mocks), after call assert `scan_id_var.get() == ""` |
| `test_scan_id_reset_even_on_exception` | make `run_all_checks` raise; after the raise propagates, assert `scan_id_var.get() == ""` |
| `test_scan_id_in_nested_check_logs` | mock a check that captures `scan_id_var.get()`; run via full `_scan_single_repo` path; assert the captured value matches the set UUID |
| `test_scan_id_isolated_per_worker_thread` | run `_scan_all_repos` with 2 mocked entries + mocked inner functions that capture per-thread scan_id; assert 2 distinct UUID values, both well-formed |

### 5.4 `tests/unit/commands/test_<cmd>_logging.py` (5 new files, ~40–50 LOC each)

Template (applied per command):

| Test name | Assertion |
|---|---|
| `test_<cmd>_logs_invocation_at_info` | run command via `CliRunner` at `--log-level info`; caplog has at least one INFO record at `gh_manage.commands.<cmd>` matching "... invoked: ..." |
| `test_<cmd>_logs_completion_at_info` | run successful command; caplog has INFO at completion matching "... complete: ..." |
| `test_<cmd>_logs_warning_on_ghnotfound_fallback` | (apply / protection / init) mock `protection_api.get_branch_protection` to raise `GhNotFoundError`; caplog has WARNING "branch protection not configured" |
| `test_<cmd>_logs_warning_on_doctor_check_error` | (apply only) mock `_doctor.run_on_path` to raise `DoctorCheckError`; caplog has WARNING "post-apply doctor check failed" |
| `test_<cmd>_logs_warning_on_rollback` | (init only) force rollback path via mocked critical findings; caplog has WARNING "init aborting: critical doctor findings" |
| `test_<cmd>_logs_warning_on_repo_label_derivation` | (doctor only) pass a path where `get_origin_owner_repo` raises; caplog has WARNING |
| `test_labels_uses_shared_handle_errors` | (labels only) `assert not hasattr(gh_manage.commands.labels, "_handle_errors")` |

Total new tests: ~25–30 across 5 files.

### 5.5 Integration smoke (manual, pre-merge checklist)

```bash
# 1. dual output
gh-manage --log-level info --log-file /tmp/ghm.log drift .
grep 'scanning' /tmp/ghm.log   # file received records
# stderr already showed them

# 2. scan_id in JSON mode
GH_MANAGE_LOG_JSON=1 gh-manage --log-level info drift --all 2>&1 >/dev/null \
  | jq -s 'group_by(.scan_id) | map({scan: .[0].scan_id, count: length}) | length'
# Expected: 22 (one scan_id per enabled repo)

# 3. Plain mode does not leak scan_id
gh-manage --log-level info drift . 2>&1 | grep -c 'scan_id'
# Expected: 0

# 4. Fail-fast on bad --log-file
gh-manage --log-file /nonexistent/x.log apply .
# Expected: exit 2, stderr contains "Usage" + "parent directory does not exist"

# 5. Rollout coverage
gh-manage --log-level info apply . --profile python-service --dry-run 2>&1 | grep 'apply invoked'
gh-manage --log-level info labels show yakkuro/llm-kb 2>&1 | grep 'labels show invoked'
# Similar for protection, init, doctor
```

### 5.6 Existing test impact

- `tests/unit/drift/test_logging_events.py` (added in PR #66): no change required; records still have the same shape plus optional `scan_id` attribute that existing tests do not assert.
- `tests/unit/test_logging_config.py`: existing tests pass unchanged; new kwargs default to `None`.
- Any existing command tests using `CliRunner`: unaffected (no new required option).

## §6 — Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| ContextVar not propagating into ThreadPoolExecutor workers | scan_ids leak/collide across parallel scans | Set inside the worker (`_scan_single_repo`), not the main thread. Test `test_scan_id_isolated_per_worker_thread` verifies. |
| `--log-file` validation breaks existing CI/cron that passes a bad path | CI goes red on the first cron after upgrade | Document in release notes: "verify GH_MANAGE_LOG_FILE path is writable before upgrading cron workflows." Validation message is actionable. |
| `logging_config.py → drift_sync.context` introduces an import cycle | ImportError at startup | `drift_sync/context.py` imports only stdlib + `gh_manage.models.*`. No logging import. DAG: `logging_config → drift_sync.context` (one-way). |
| `labels.py` decorator consolidation changes exception behavior | Silently swallow / newly propagate errors | `_shared.handle_errors` catches the full `_DOMAIN_ERRORS` superset (GhError, ConfigError, GitError, ProfileError, ProtectionError, DriftError, DoctorError). Local `_handle_errors` caught only `(GhError, ConfigError)`. Widened catch → no newly-raised exceptions; potentially newly-caught exceptions produce `ClickException` with better message. Verified by `test_labels_uses_shared_handle_errors` + existing label tests. |
| FileHandler append-mode leaves stale `scan_id` records in long-running log files that confuse future jq queries | operational noise | Out of scope (logrotate). Release notes call out "consider logrotate for `--log-file` destinations". |
| New INFO/WARNING emit on commands that previously produced zero stderr (e.g., `labels show`) | users scripting against "empty stderr = success" break | INFO is above the default WARNING floor — no change at default level. WARNING additions are in pre-existing silent-fallback branches (e.g., 404 treated as empty) where adding a log line is the correct behavior. Default-level `labels show yakkuro/llm-kb` continues to emit zero stderr. |
| `_scan_single_repo` `try/finally` around body shadows internal exceptions | harder to debug | `scan_id_var.reset(token)` cannot raise (documented in contextvars). No suppression risk. |

## §7 — Release plan

- **Tag**: `cli/v1.9.0` — CLI-track minor. Additive: new option, new optional field in JSON output, new INFO/WARNING records.
- **Release notes** (cli/v1.9.0):
  - Add `--log-file PATH` + `GH_MANAGE_LOG_FILE` envvar for dual stderr+file output; fail-fast validation at startup
  - Add `scan_id` correlation id to drift scan logs (UUID4 per scan, appears in JSON mode only)
  - Structured logging now covers `apply`, `labels`, `protection`, `init`, `doctor` (was drift-only in cli/v1.8.0)
  - Internal: consolidate `labels.py` error decorator onto `_shared.handle_errors` (no behavior change visible to users)
  - Closes #63, #64, #65
- **Migration notes**: none. Defaults preserve cli/v1.8.0 behavior (WARNING floor, stderr only, no scan_id in output).
- **Cron workflow update**: separate consumer-side PR (not this spec) — enable `GH_MANAGE_LOG_FILE` + `GH_MANAGE_LOG_JSON=1` in the daily `drift --all` job so artifacts are durable and machine-readable.

## §8 — Acceptance Criteria

Production code:

- [ ] `src/gh_manage/drift_sync/context.py`: `scan_id_var: ContextVar[str]` defined with default=""
- [ ] `src/gh_manage/drift_sync/__init__.py`: `scan_id_var` re-exported
- [ ] `src/gh_manage/logging_config.py`: `_ScanIdJsonFormatter` class; `configure_logging` has `log_file: Path | None = None` kwarg; dual-handler logic
- [ ] `src/gh_manage/cli.py`: `--log-file` option + envvar; `_validate_log_file` function; called from root group callback
- [ ] `src/gh_manage/commands/drift.py:_scan_single_repo`: `scan_id_var.set/reset` wrapping the body
- [ ] `src/gh_manage/commands/{apply,labels,protection,init,doctor}.py`: module-level `log = logging.getLogger(__name__)`; §4.2 log points implemented; §4.3 decorator consolidation in `labels.py`

Tests:

- [ ] `tests/unit/test_logging_config.py` extended with 8 new tests
- [ ] `tests/unit/test_cli_log_file.py` (new) with 6 tests
- [ ] `tests/unit/drift/test_scan_id_propagation.py` (new) with 5 tests
- [ ] `tests/unit/commands/test_{apply,labels,protection,init,doctor}_logging.py` (5 new) with ~25 tests total
- [ ] `uv run pytest -q` all pass (baseline 587 + ~44 new ≈ 631 tests)

Quality gates:

- [ ] `uvx ruff@0.8.0 check src/ tests/` clean
- [ ] `uvx ruff@0.8.0 format --check src/ tests/` clean
- [ ] `uv run mypy src/` clean

Integration:

- [ ] §5.5 manual smoke steps all pass
- [ ] `gh-manage drift --all 2>&1 | grep -c ERROR` returns 0 on clean fleet

Release:

- [ ] Version bump to `1.9.0` in `__init__.py`, `pyproject.toml`, `tests/test_sanity.py`, `uv.lock`
- [ ] PR open, 4-reviewer protocol complete, CRITICAL/HIGH findings addressed
- [ ] `cli/v1.9.0` tag + GitHub release with notes per §7
- [ ] Issues #63, #64, #65 closed with reference to this PR

## §9 — Open Questions

None. Q1–Q4 (2026-04-20 brainstorming) resolved all design decisions:

- **Q1** (PR structure): A — single cli/v1.9.0 PR bundling all three Issues
- **Q2** (scan_id mechanism): C — ContextVar + `_ScanIdJsonFormatter` auto-attach
- **Q3** (--log-file output): A — dual stderr + file, shared formatter
- **Q4** (validation failure): A — fail-fast at startup via `UsageError`

## References

- Baseline PR: [#66](https://github.com/yakkuro/gh-manage/pull/66) (`cli/v1.8.0`)
- Issues addressed: [#63](https://github.com/yakkuro/gh-manage/issues/63), [#64](https://github.com/yakkuro/gh-manage/issues/64), [#65](https://github.com/yakkuro/gh-manage/issues/65)
- Related Theme A umbrella: [#47](https://github.com/yakkuro/gh-manage/issues/47)
- cli/v1.8.0 design spec: `docs/specs/2026-04-19-drift-sync-logging-design.md`
- `python-json-logger`: https://github.com/madzak/python-json-logger (pinned `>=2.0,<3.0` in cli/v1.8.0)
- `contextvars` in ThreadPoolExecutor: PEP 567, Python 3.9+ context copy at submit
- Current baseline: commit `e71a9a8` on `main`
