# Structured Logging Follow-ups Implementation Plan (cli/v1.9.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task has Red → Green → Commit cycle; do not skip the Red phase.

**Goal:** Ship cli/v1.9.0 bundling Issues #63 (command rollout), #64 (scan_id ContextVar), #65 (`--log-file` flag + fail-fast validate).

**Architecture:** Additive to cli/v1.8.0 baseline. Extend `logging_config.py` with dual handler + `_ScanIdJsonFormatter`; add `scan_id_var` ContextVar in `drift_sync/context.py`; wrap `_scan_single_repo` body with set/reset; add log points to 5 commands (`apply`, `labels`, `protection`, `init`, `doctor`); add `--log-file` root option with fail-fast validate.

**Tech Stack:** Python 3.12, `uv` for deps, `click` 8.x, `pydantic` v2, `pytest` 8 + `pytest-mock`, `ruff` pinned at 0.8.0, `python-json-logger >=2.0,<3.0` (already installed via cli/v1.8.0).

**Spec:** `docs/specs/2026-04-20-structured-logging-followups-design.md`

---

## Pre-flight

Branch `feat/structured-logging-followups-spec` already exists (spec committed at `c3f4c67`). Continue implementation on the same branch.

Verify clean state:

```bash
git status                         # expect clean
git log --oneline main..HEAD       # expect: c3f4c67 (critique fixes), 154cb93 (spec)
uv run pytest -q 2>&1 | tail -3    # expect baseline: 587 passed
```

If any of the above is not satisfied, stop and resolve before starting Task 1.

---

## Task 1: Add `scan_id_var` ContextVar

**Files:**
- Modify: `src/gh_manage/drift_sync/context.py`
- Modify: `src/gh_manage/drift_sync/__init__.py`
- Create: `tests/unit/drift/test_context.py`

**Spec ref:** §2.1

- [ ] **Step 1: Write failing test**

Create `tests/unit/drift/test_context.py`:

```python
"""Tests for drift_sync/context.py — scan_id ContextVar."""

from __future__ import annotations

from contextvars import copy_context

from gh_manage.drift_sync.context import scan_id_var


def test_scan_id_var_defaults_to_empty_string():
    ctx = copy_context()
    assert ctx.run(scan_id_var.get) == ""


def test_scan_id_var_set_and_reset():
    token = scan_id_var.set("test-uuid")
    try:
        assert scan_id_var.get() == "test-uuid"
    finally:
        scan_id_var.reset(token)
    assert scan_id_var.get() == ""


def test_scan_id_var_importable_from_drift_sync_namespace():
    from gh_manage.drift_sync import scan_id_var as exported

    assert exported is scan_id_var
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/drift/test_context.py -v
```

Expected: `ImportError: cannot import name 'scan_id_var'` (or AttributeError).

- [ ] **Step 3: Implement ContextVar in context.py**

In `src/gh_manage/drift_sync/context.py`, add `from contextvars import ContextVar` to the imports (keep existing `from dataclasses import dataclass`, etc.), then append at module level after the `DriftOutputError` class:

```python
scan_id_var: ContextVar[str] = ContextVar("scan_id", default="")
```

- [ ] **Step 4: Re-export from `drift_sync/__init__.py`**

Read `src/gh_manage/drift_sync/__init__.py`. Find the existing `from gh_manage.drift_sync.context import ...` line (it re-exports `ScanContext`, `DriftError`, `DriftOutputError`). Add `scan_id_var` to that import:

```python
from gh_manage.drift_sync.context import (
    DriftError,
    DriftOutputError,
    ScanContext,
    scan_id_var,
)
```

If an `__all__` list exists in the module, add `"scan_id_var"` to it.

- [ ] **Step 5: Run — expect PASS**

```bash
uv run pytest tests/unit/drift/test_context.py -v
```

Expected: 3 PASSED.

- [ ] **Step 6: Full suite regression check**

```bash
uv run pytest -q 2>&1 | tail -3
```

Expected: 590 passed (587 baseline + 3 new).

- [ ] **Step 7: Commit**

```bash
git add src/gh_manage/drift_sync/context.py src/gh_manage/drift_sync/__init__.py tests/unit/drift/test_context.py
git commit -m "$(cat <<'EOF'
feat(drift_sync): add scan_id_var ContextVar

Per-scan correlation id; default empty string means not inside a scan.
Re-exported from drift_sync namespace.

Refs #64

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `_ScanIdJsonFormatter` class

**Files:**
- Modify: `src/gh_manage/logging_config.py`
- Modify: `tests/unit/test_logging_config.py`

**Spec ref:** §2.3

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_logging_config.py` (read it first to see the existing imports/fixtures, then append):

```python

# ---- scan_id injection tests (cli/v1.9.0) ----

import io as _io
import json as _json
import logging as _logging

from gh_manage.drift_sync.context import scan_id_var
from gh_manage.logging_config import configure_logging as _configure_logging


def _parse_first_json(stream: _io.StringIO) -> dict:
    text = stream.getvalue().strip()
    assert text, "expected at least one log line"
    return _json.loads(text.splitlines()[0])


def test_json_formatter_includes_scan_id_when_set():
    stream = _io.StringIO()
    _configure_logging(level="info", json=True, stream=stream)
    token = scan_id_var.set("test-uuid-123")
    try:
        _logging.getLogger("gh_manage.test").info("hello")
    finally:
        scan_id_var.reset(token)
    assert _parse_first_json(stream)["scan_id"] == "test-uuid-123"


def test_json_formatter_omits_scan_id_when_unset():
    stream = _io.StringIO()
    _configure_logging(level="info", json=True, stream=stream)
    _logging.getLogger("gh_manage.test").info("hello")
    assert "scan_id" not in _parse_first_json(stream)


def test_plain_formatter_omits_scan_id():
    stream = _io.StringIO()
    _configure_logging(level="info", json=False, stream=stream)
    token = scan_id_var.set("would-be-visible-if-not-omitted")
    try:
        _logging.getLogger("gh_manage.test").info("hello")
    finally:
        scan_id_var.reset(token)
    assert "would-be-visible" not in stream.getvalue()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_logging_config.py -v -k "scan_id or plain_formatter_omits"
```

Expected: 3 FAILED.

- [ ] **Step 3: Implement `_ScanIdJsonFormatter`**

Edit `src/gh_manage/logging_config.py`:

Change the existing import line from:

```python
from pythonjsonlogger.jsonlogger import JsonFormatter
```

to:

```python
from pythonjsonlogger.jsonlogger import JsonFormatter as _BaseJsonFormatter

from gh_manage.drift_sync.context import scan_id_var
```

Add the class definition after the `_TRUTHY` constant and before `_env_says_json`:

```python
class _ScanIdJsonFormatter(_BaseJsonFormatter):
    """JSON formatter that injects the current scan_id ContextVar.

    When called outside a drift scan, scan_id_var.get() returns the
    default empty string, and the field is omitted from the JSON
    output. See docs/specs/2026-04-20-structured-logging-followups-design.md §2.
    """

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        sid = scan_id_var.get()
        if sid:
            log_record["scan_id"] = sid
```

Update the formatter-selection branch inside `configure_logging`:

```python
    formatter: logging.Formatter
    if json:
        formatter = _ScanIdJsonFormatter(_JSON_FORMAT, datefmt=_JSON_DATEFMT)
    else:
        formatter = logging.Formatter(_PLAIN_FORMAT, datefmt=_PLAIN_DATEFMT)
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/test_logging_config.py -v
```

Expected: all pass (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/logging_config.py tests/unit/test_logging_config.py
git commit -m "$(cat <<'EOF'
feat(logging): _ScanIdJsonFormatter auto-injects scan_id

JSON output gets scan_id field when the ContextVar is set (inside a
drift scan). Plain-text formatter never includes scan_id.

Refs #64

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `configure_logging` log_file kwarg + dual handler

**Files:**
- Modify: `src/gh_manage/logging_config.py`
- Modify: `tests/unit/test_logging_config.py`

**Spec ref:** §3.3

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_logging_config.py`:

```python

# ---- log_file + dual handler tests (cli/v1.9.0) ----

from pathlib import Path as _Path


def test_configure_logging_with_log_file_adds_file_handler(tmp_path):
    log_path = tmp_path / "x.log"
    _configure_logging(level="info", log_file=log_path)
    handlers = _logging.getLogger("gh_manage").handlers
    assert len(handlers) == 2
    types = {type(h).__name__ for h in handlers}
    assert types == {"StreamHandler", "FileHandler"}


def test_log_file_mode_is_append(tmp_path):
    log_path = tmp_path / "x.log"
    log_path.write_text("pre-existing\n", encoding="utf-8")
    _configure_logging(level="info", log_file=log_path)
    _logging.getLogger("gh_manage.test").info("new-entry")
    for h in _logging.getLogger("gh_manage").handlers:
        h.flush()
    content = log_path.read_text(encoding="utf-8")
    assert content.startswith("pre-existing\n")
    assert "new-entry" in content


def test_log_file_encoding_is_utf8(tmp_path):
    log_path = tmp_path / "x.log"
    _configure_logging(level="info", log_file=log_path)
    _logging.getLogger("gh_manage.test").info("日本語テスト")
    for h in _logging.getLogger("gh_manage").handlers:
        h.flush()
    content = log_path.read_bytes().decode("utf-8")
    assert "日本語テスト" in content


def test_log_file_and_stderr_get_same_record(tmp_path):
    log_path = tmp_path / "x.log"
    stream = _io.StringIO()
    _configure_logging(level="info", log_file=log_path, stream=stream)
    _logging.getLogger("gh_manage.test").info("dual-msg")
    for h in _logging.getLogger("gh_manage").handlers:
        h.flush()
    assert "dual-msg" in stream.getvalue()
    assert "dual-msg" in log_path.read_text(encoding="utf-8")


def test_file_handler_inherits_scan_id_formatter(tmp_path):
    log_path = tmp_path / "x.log"
    _configure_logging(level="info", json=True, log_file=log_path)
    token = scan_id_var.set("file-scan-id")
    try:
        _logging.getLogger("gh_manage.test").info("msg")
    finally:
        scan_id_var.reset(token)
    for h in _logging.getLogger("gh_manage").handlers:
        h.flush()
    first_line = log_path.read_text(encoding="utf-8").splitlines()[0]
    assert _json.loads(first_line)["scan_id"] == "file-scan-id"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_logging_config.py -v -k "log_file or inherits_scan_id"
```

Expected: FAIL with `TypeError: ... got an unexpected keyword argument 'log_file'`.

- [ ] **Step 3: Extend `configure_logging`**

Edit `src/gh_manage/logging_config.py`:

Add `from pathlib import Path` to imports if not already present.

Update `configure_logging` signature to:

```python
def configure_logging(
    level: LogLevel = "warning",
    json: bool | None = None,
    stream: IO[str] | None = None,
    log_file: Path | None = None,
) -> None:
```

Replace the docstring entirely with:

```python
    """Configure gh_manage's root logger tree.

    Handler-replacement semantics (not merge-idempotent across
    differing args): each call replaces the existing handler list on
    the `gh_manage` logger with a fresh set built from the arguments.
    Calling twice with the same arguments produces the same resulting
    configuration (end-state idempotent), but calling twice with
    different log_file values does NOT merge — the second call
    replaces the first. The CLI invokes this exactly once per process.

    - level: log level for the `gh_manage` logger tree. Third-party
      packages' loggers are untouched.
    - json: tri-state. Explicit True/False wins over env var
      GH_MANAGE_LOG_JSON; None reads env.
    - stream: destination for stderr handler. Defaults to sys.stderr.
      Tests pass a StringIO to capture output.
    - log_file: optional destination for a FileHandler (append mode,
      utf-8). When set, a FileHandler is added alongside the stderr
      StreamHandler; both handlers share the same formatter. Caller is
      responsible for validating the path (cli.py uses _validate_log_file).

    Immutability: the plain and JSON formatter strings (including
    datefmt) are fixed by this module — not runtime-configurable.
    """
```

Replace the handler-construction block with:

```python
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

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/test_logging_config.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/logging_config.py tests/unit/test_logging_config.py
git commit -m "$(cat <<'EOF'
feat(logging): configure_logging log_file kwarg (dual stderr+file)

Optional FileHandler (append, utf-8) attached alongside stderr when
log_file is set. Docstring clarifies handler-replacement semantics.

Refs #65

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `_validate_log_file` function

**Files:**
- Modify: `src/gh_manage/cli.py`
- Create: `tests/unit/test_cli_log_file.py`

**Spec ref:** §3.2

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_cli_log_file.py`:

```python
"""Tests for cli.py --log-file validation and option wiring."""

from __future__ import annotations

import os
import stat

import click
import pytest

from gh_manage.cli import _validate_log_file


def test_validate_log_file_rejects_missing_parent(tmp_path):
    missing = tmp_path / "nonexistent-dir" / "x.log"
    with pytest.raises(click.UsageError) as exc:
        _validate_log_file(missing)
    assert "parent directory does not exist" in str(exc.value)


def test_validate_log_file_rejects_unwritable(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root bypasses permission bits")
    tmp_path.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        target = tmp_path / "x.log"
        with pytest.raises(click.UsageError) as exc:
            _validate_log_file(target)
        assert "Cannot write" in str(exc.value)
    finally:
        tmp_path.chmod(stat.S_IRWXU)


def test_validate_log_file_accepts_new_path(tmp_path):
    target = tmp_path / "new.log"
    assert not target.exists()
    _validate_log_file(target)
    assert target.exists()


def test_validate_log_file_accepts_existing_path(tmp_path):
    target = tmp_path / "existing.log"
    target.write_text("pre-existing content\n", encoding="utf-8")
    _validate_log_file(target)
    assert target.read_text(encoding="utf-8") == "pre-existing content\n"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_cli_log_file.py -v
```

Expected: `ImportError: cannot import name '_validate_log_file' from 'gh_manage.cli'`.

- [ ] **Step 3: Implement `_validate_log_file`**

Edit `src/gh_manage/cli.py`:

Add `from pathlib import Path` to imports.

Add the function just before the `@click.group(...)` decorator:

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

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/test_cli_log_file.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/cli.py tests/unit/test_cli_log_file.py
git commit -m "$(cat <<'EOF'
feat(cli): _validate_log_file fail-fast validator

Rejects missing parent and unwritable paths with UsageError before any
subcommand runs.

Refs #65

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `--log-file` option wired into root group

**Files:**
- Modify: `src/gh_manage/cli.py`
- Modify: `tests/unit/test_cli_log_file.py`

**Spec ref:** §3.1

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_cli_log_file.py`:

```python

# ---- CLI integration tests (Task 5) ----

from pathlib import Path as _Path

from click.testing import CliRunner

from gh_manage.cli import main


def test_cli_log_file_env_var_honored(tmp_path, monkeypatch):
    log_path = tmp_path / "x.log"
    monkeypatch.setenv("GH_MANAGE_LOG_FILE", str(log_path))
    runner = CliRunner()
    # Invoke --help to trigger the root callback once the option has
    # defaulted from envvar. --help short-circuits subcommand dispatch
    # but the root callback still fires in click.
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    # _validate_log_file touched the file via open("a").
    assert log_path.exists()


def test_cli_log_file_rejects_bad_path(tmp_path):
    bad = tmp_path / "nonexistent-parent" / "x.log"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--log-file", str(bad), "labels", "show", "owner/repo"],
    )
    assert result.exit_code != 0
    combined = result.output + (str(result.exception) if result.exception else "")
    assert "parent directory does not exist" in combined


def test_cli_log_file_env_var_rejects_bad_path(tmp_path, monkeypatch):
    bad = tmp_path / "nonexistent-parent" / "x.log"
    monkeypatch.setenv("GH_MANAGE_LOG_FILE", str(bad))
    runner = CliRunner()
    result = runner.invoke(main, ["labels", "show", "owner/repo"])
    assert result.exit_code != 0
    combined = result.output + (str(result.exception) if result.exception else "")
    assert "parent directory does not exist" in combined
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_cli_log_file.py -v -k "env_var or rejects_bad"
```

Expected: FAIL — `--log-file` option not yet wired in root group.

- [ ] **Step 3: Wire `--log-file` into root group**

Edit `src/gh_manage/cli.py`. Find the `@click.group(...)` decorator stack on `main` and the `def main(log_level: str) -> None:` signature.

Add a new `@click.option("--log-file", ...)` decorator between `--log-level` and `def main`:

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
    """Root command group. Subcommands are registered below."""
    level: LogLevel = log_level.lower()  # type: ignore[assignment]
    if log_file is not None:
        _validate_log_file(log_file)
    configure_logging(level=level, log_file=log_file)
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/test_cli_log_file.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/cli.py tests/unit/test_cli_log_file.py
git commit -m "$(cat <<'EOF'
feat(cli): --log-file root option + GH_MANAGE_LOG_FILE envvar

Wires _validate_log_file into the root group callback; invalid paths
from either flag or envvar exit with UsageError before subcommand dispatch.

Refs #65

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: scan_id set/reset in `_scan_single_repo`

**Files:**
- Modify: `src/gh_manage/commands/drift.py`
- Create: `tests/unit/drift/test_scan_id_propagation.py`

**Spec ref:** §2.2, §5.3

- [ ] **Step 1: Write failing tests**

Create `tests/unit/drift/test_scan_id_propagation.py`:

```python
"""Tests for scan_id ContextVar propagation via _scan_single_repo."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from gh_manage.drift_sync.context import scan_id_var


@pytest.fixture
def mock_scan_deps(monkeypatch):
    """Patch heavy dependencies of _scan_single_repo."""
    from gh_manage.commands import drift as drift_cmd

    mock_profile = MagicMock(protection_policy=None)
    mock_labels_config = MagicMock()

    monkeypatch.setattr(
        drift_cmd.repo_info, "get_default_branch", lambda repo: "main"
    )
    monkeypatch.setattr(
        drift_cmd,
        "load_config",
        lambda path, cls: (
            mock_profile if "profile" in str(path) else mock_labels_config
        ),
    )
    monkeypatch.setattr(
        drift_cmd, "resolve_profile_path", lambda name: "/tmp/fake-profile.yml"
    )
    monkeypatch.setattr(
        drift_cmd, "resolve_default_labels_path", lambda: "/tmp/fake-labels.yml"
    )
    monkeypatch.setattr(
        drift_cmd.drift_sync, "format_stdout_report", lambda findings: "report"
    )
    monkeypatch.setattr(
        drift_cmd.drift_sync, "_filter_by_severity", lambda findings, sev: findings
    )
    return drift_cmd


def _make_capturing_stub(captured: dict, key: str):
    def _stub(ctx):
        captured[key] = scan_id_var.get()
        return ()

    return _stub


def test_scan_id_set_at_single_repo_entry(mock_scan_deps, monkeypatch):
    drift_cmd = mock_scan_deps
    captured: dict = {}
    monkeypatch.setattr(
        drift_cmd.drift_sync, "run_all_checks", _make_capturing_stub(captured, "a")
    )
    drift_cmd._scan_single_repo(
        "owner/repo", "python-service", "low", "stdout", None,
        skip_profile_check=True,
    )
    sid = captured["a"]
    uuid.UUID(sid, version=4)


def test_scan_id_reset_after_single_repo_exit(mock_scan_deps, monkeypatch):
    drift_cmd = mock_scan_deps
    monkeypatch.setattr(drift_cmd.drift_sync, "run_all_checks", lambda ctx: ())
    drift_cmd._scan_single_repo(
        "owner/repo", "python-service", "low", "stdout", None,
        skip_profile_check=True,
    )
    assert scan_id_var.get() == ""


def test_scan_id_reset_even_on_exception(mock_scan_deps, monkeypatch):
    drift_cmd = mock_scan_deps

    def _raise(ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(drift_cmd.drift_sync, "run_all_checks", _raise)
    with pytest.raises(RuntimeError, match="boom"):
        drift_cmd._scan_single_repo(
            "owner/repo", "python-service", "low", "stdout", None,
            skip_profile_check=True,
        )
    assert scan_id_var.get() == ""


def test_scan_id_differs_across_sequential_scans_in_same_thread(
    mock_scan_deps, monkeypatch
):
    drift_cmd = mock_scan_deps
    captured: dict = {}
    monkeypatch.setattr(
        drift_cmd.drift_sync, "run_all_checks", _make_capturing_stub(captured, "seq")
    )
    drift_cmd._scan_single_repo(
        "owner/repo-1", "python-service", "low", "stdout", None,
        skip_profile_check=True,
    )
    first = captured["seq"]
    drift_cmd._scan_single_repo(
        "owner/repo-2", "python-service", "low", "stdout", None,
        skip_profile_check=True,
    )
    second = captured["seq"]
    assert first != second
    uuid.UUID(first, version=4)
    uuid.UUID(second, version=4)


def test_scan_id_isolated_per_worker_thread(mock_scan_deps, monkeypatch):
    drift_cmd = mock_scan_deps
    captured: dict = {}
    lock = threading.Lock()
    counter = {"n": 0}

    def _stub(ctx):
        with lock:
            counter["n"] += 1
            key = f"worker_{counter['n']}"
        captured[key] = scan_id_var.get()
        return ()

    monkeypatch.setattr(drift_cmd.drift_sync, "run_all_checks", _stub)

    def _call():
        drift_cmd._scan_single_repo(
            "owner/repo", "python-service", "low", "stdout", None,
            skip_profile_check=True,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_call) for _ in range(2)]
        for f in futures:
            f.result()

    vals = list(captured.values())
    assert len(vals) == 2
    assert vals[0] != vals[1]
    for v in vals:
        uuid.UUID(v, version=4)
    assert scan_id_var.get() == ""
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/drift/test_scan_id_propagation.py -v
```

Expected: FAIL — `scan_id_var.get()` returns `""` (set/reset not yet wired).

- [ ] **Step 3: Wrap `_scan_single_repo` body with set/reset**

Edit `src/gh_manage/commands/drift.py`:

Add imports near existing imports:

```python
from uuid import uuid4

from gh_manage.drift_sync.context import scan_id_var
```

Refactor `_scan_single_repo` so its entire body runs inside `try:` with `finally: scan_id_var.reset(token)`. The existing function signature and return value are unchanged.

Exact transform — before:

```python
def _scan_single_repo(
    owner_repo: str,
    profile_name: str,
    severity: str,
    report_mode: str,
    output: Path | None,
    skip_profile_check: bool = False,
) -> str:
    """..."""
    log.info("scanning %s (profile=%s)", owner_repo, profile_name)
    # Get default branch
    default_branch = repo_info.get_default_branch(owner_repo)
    # ... ~70 more lines ending in match statement returning a string ...
```

After:

```python
def _scan_single_repo(
    owner_repo: str,
    profile_name: str,
    severity: str,
    report_mode: str,
    output: Path | None,
    skip_profile_check: bool = False,
) -> str:
    """..."""
    token = scan_id_var.set(str(uuid4()))
    try:
        log.info("scanning %s (profile=%s)", owner_repo, profile_name)
        # Get default branch
        default_branch = repo_info.get_default_branch(owner_repo)
        # ... ~70 more lines, indented one additional level ...
        # ... ending at the `match report_mode:` block ...
        match report_mode:
            case "stdout":
                rendered = drift_sync.format_stdout_report(filtered)
                return rendered
            case "json":
                rendered = drift_sync.format_json_report(filtered)
                return rendered
            case "markdown-file":
                # ... existing branch body ...
                return f"Report written to {output}"
            case "issue":
                # ... existing branch body ...
                return status
            case _:
                raise ValueError(f"Unknown report mode: {report_mode!r}")
    finally:
        scan_id_var.reset(token)
```

Indent every existing body line by exactly 4 spaces. Do NOT change any logic. Verify by eye that `return` statements are now 12-space-indented instead of 8-space.

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/drift/test_scan_id_propagation.py -v
```

Expected: 5 PASSED.

- [ ] **Step 5: Regression check — existing drift tests**

```bash
uv run pytest tests/ -v -k "drift" 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/gh_manage/commands/drift.py tests/unit/drift/test_scan_id_propagation.py
git commit -m "$(cat <<'EOF'
feat(drift): set/reset scan_id_var in _scan_single_repo

Per-scan UUID4 via try/finally; covers single-repo and --all paths.
Reset on exception guarantees no leakage across sequential or parallel
scans.

Closes #64

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `apply.py` log points

**Files:**
- Modify: `src/gh_manage/commands/apply.py`
- Create: `tests/unit/commands/__init__.py` (if missing)
- Create: `tests/unit/commands/test_apply_logging.py`

**Spec ref:** §4.2 (apply row)

- [ ] **Step 1: Ensure test dir exists**

```bash
test -d tests/unit/commands || mkdir -p tests/unit/commands
touch tests/unit/commands/__init__.py
```

- [ ] **Step 2: Write failing tests**

Create `tests/unit/commands/test_apply_logging.py`:

```python
"""caplog-based regression tests for commands/apply.py log points."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from gh_manage.cli import main


@pytest.fixture
def mock_apply_deps(monkeypatch):
    monkeypatch.setattr(
        "gh_manage.git_cli.get_origin_owner_repo", lambda p: "owner/repo"
    )
    fake_profile = MagicMock(protection_policy=None)
    fake_profile.name = "python-service"
    monkeypatch.setattr(
        "gh_manage.commands.apply.load_config",
        lambda path, cls: fake_profile,
    )
    monkeypatch.setattr(
        "gh_manage.commands.apply.resolve_profile_path",
        lambda name: "/tmp/fake.yml",
    )
    monkeypatch.setattr(
        "gh_manage.commands.apply.resolve_templates_root",
        lambda: "/tmp/templates",
    )
    fake_diff = MagicMock(
        creates=[], overwrites=[], skipped=[], noops=[], is_empty=True,
    )
    monkeypatch.setattr(
        "gh_manage.profile_sync.compute_files_diff",
        lambda *a, **kw: fake_diff,
    )


def test_apply_logs_invocation_at_info(mock_apply_deps, caplog, tmp_path):
    runner = CliRunner()
    with caplog.at_level(logging.INFO, logger="gh_manage.commands.apply"):
        runner.invoke(
            main,
            ["--log-level", "info", "apply", str(tmp_path),
             "--profile", "python-service"],
        )
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.apply"]
    assert any("apply invoked" in m and "owner/repo" in m for m in msgs), msgs


def test_apply_logs_completion_at_info(
    mock_apply_deps, caplog, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "gh_manage.profile_sync.apply_files_diff",
        lambda *a, **kw: [],
    )
    monkeypatch.setattr(
        "gh_manage.doctor.run_on_path",
        lambda *a, **kw: (),
    )
    runner = CliRunner()
    with caplog.at_level(logging.INFO, logger="gh_manage.commands.apply"):
        runner.invoke(
            main,
            ["--log-level", "info", "apply", str(tmp_path),
             "--profile", "python-service", "--apply"],
        )
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.apply"]
    assert any("apply complete" in m for m in msgs), msgs


def test_apply_logs_warning_on_ghnotfound_protection_fallback(
    caplog, tmp_path, monkeypatch
):
    from gh_manage.github_client import GhNotFoundError

    monkeypatch.setattr(
        "gh_manage.git_cli.get_origin_owner_repo", lambda p: "owner/repo"
    )
    fake_profile = MagicMock()
    fake_profile.name = "python-service"
    fake_profile.protection_policy = "standard"
    fake_bp = MagicMock(policies={"standard": MagicMock()})

    def _load(path, cls):
        return fake_profile if "profile" in str(path) else fake_bp

    monkeypatch.setattr("gh_manage.commands.apply.load_config", _load)
    monkeypatch.setattr(
        "gh_manage.commands.apply.resolve_profile_path",
        lambda name: "/tmp/fake.yml",
    )
    monkeypatch.setattr(
        "gh_manage.commands.apply.resolve_templates_root",
        lambda: "/tmp/templates",
    )
    monkeypatch.setattr(
        "gh_manage.commands.apply.resolve_branch_protection_path",
        lambda: "/tmp/bp.yml",
    )
    monkeypatch.setattr(
        "gh_manage.commands.apply.resolve_default_labels_path",
        lambda: "/tmp/labels.yml",
    )
    monkeypatch.setattr(
        "gh_manage.profile_sync.compute_files_diff",
        lambda *a, **kw: MagicMock(
            creates=[], overwrites=[], skipped=[], noops=[], is_empty=True,
        ),
    )

    def _raise_404(*a, **kw):
        raise GhNotFoundError("404")

    monkeypatch.setattr(
        "gh_manage.github_api.protection.get_branch_protection", _raise_404
    )
    monkeypatch.setattr(
        "gh_manage.protection_sync.compute_protection_diff",
        lambda *a, **kw: MagicMock(
            is_empty=True, changes=(), has_downgrades=False,
        ),
    )

    runner = CliRunner()
    with caplog.at_level(logging.WARNING, logger="gh_manage.commands.apply"):
        runner.invoke(
            main,
            ["apply", str(tmp_path), "--profile", "python-service",
             "--also-protection"],
        )
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.apply"]
    assert any(
        "branch protection not configured" in m and "owner/repo" in m
        for m in msgs
    ), msgs
```

- [ ] **Step 3: Run — expect FAIL**

```bash
uv run pytest tests/unit/commands/test_apply_logging.py -v
```

Expected: FAIL (no records captured).

- [ ] **Step 4: Add log points to apply.py**

Edit `src/gh_manage/commands/apply.py`:

Add at top-level imports (after the click import):

```python
import logging
```

Add after the imports block:

```python
log = logging.getLogger(__name__)
```

Inside `apply()`, immediately after `owner_repo = git_cli.get_origin_owner_repo(target)`:

```python
    log.info(
        "apply invoked: repo=%s profile=%s apply=%s also_labels=%s also_protection=%s",
        owner_repo, profile_name, apply_flag, also_labels, also_protection,
    )
```

Inside the existing `except GhNotFoundError:` block that precedes `current_protection = {}`:

```python
        except GhNotFoundError:
            log.warning(
                "branch protection not configured on %s@main; treating as empty",
                owner_repo,
            )
            current_protection = {}
```

Inside the existing `except DoctorCheckError as exc:` block (before the click.echo):

```python
    except DoctorCheckError as exc:
        log.warning("post-apply doctor check failed: %s", exc)
        click.echo(f"WARNING: post-apply doctor check failed: {exc}", err=True)
        findings = ()
```

Immediately after the final `click.echo(f"\nApplied {n_file_changes} file changes" ...)` (before the post-apply doctor comment block):

```python
    click.echo(
        f"\nApplied {n_file_changes} file changes"
        + (f" + {n_label_changes} label changes" if also_labels else "")
        + "."
    )

    log.info(
        "apply complete: repo=%s file_changes=%d label_changes=%d protection_changes=%d",
        owner_repo, n_file_changes, n_label_changes, n_protection_changes,
    )

    # Post-apply doctor warnings ...
```

- [ ] **Step 5: Run — expect PASS**

```bash
uv run pytest tests/unit/commands/test_apply_logging.py -v
```

Expected: 3 PASSED.

- [ ] **Step 6: Full suite regression**

```bash
uv run pytest -q 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/gh_manage/commands/apply.py tests/unit/commands/__init__.py tests/unit/commands/test_apply_logging.py
git commit -m "$(cat <<'EOF'
feat(apply): log points (invocation, completion, 404 fallback, doctor)

INFO on entry/exit; WARNING on silent GhNotFoundError protection
fallback and DoctorCheckError catch.

Refs #63

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `labels.py` log points + decorator consolidation

**Files:**
- Modify: `src/gh_manage/commands/labels.py`
- Create: `tests/unit/commands/test_labels_logging.py`

**Spec ref:** §4.2 (labels row), §4.3

- [ ] **Step 1: Write failing tests**

Create `tests/unit/commands/test_labels_logging.py`:

```python
"""caplog-based regression tests for commands/labels.py log points."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

import gh_manage.commands.labels as labels_mod
from gh_manage.cli import main
from gh_manage.config import ConfigError
from gh_manage.github_client import GhError


def test_labels_uses_shared_handle_errors():
    assert not hasattr(labels_mod, "_handle_errors"), (
        "commands/labels.py should use _shared.handle_errors; "
        "remove the local _handle_errors decorator."
    )


@pytest.fixture
def mock_labels_deps(monkeypatch):
    monkeypatch.setattr(
        "gh_manage.github_api.labels.list_labels", lambda repo: ()
    )
    monkeypatch.setattr(
        "gh_manage.commands.labels.load_config",
        lambda path, cls: MagicMock(labels=[]),
    )
    monkeypatch.setattr(
        "gh_manage.labels_sync.compute_diff",
        lambda *a, **kw: MagicMock(
            is_empty=True, total_changes=0,
            creates=[], updates=[], renames=[], deletes=[],
        ),
    )


def test_labels_sync_logs_invocation(mock_labels_deps, caplog):
    runner = CliRunner()
    with caplog.at_level(logging.INFO, logger="gh_manage.commands.labels"):
        runner.invoke(
            main, ["--log-level", "info", "labels", "sync", "owner/repo"]
        )
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.labels"]
    assert any("labels sync invoked" in m and "owner/repo" in m
               for m in msgs), msgs


def test_labels_show_logs_invocation(mock_labels_deps, caplog):
    runner = CliRunner()
    with caplog.at_level(logging.INFO, logger="gh_manage.commands.labels"):
        runner.invoke(
            main, ["--log-level", "info", "labels", "show", "owner/repo"]
        )
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.labels"]
    assert any("labels show invoked" in m and "owner/repo" in m
               for m in msgs), msgs


def test_labels_diff_logs_invocation(mock_labels_deps, caplog):
    runner = CliRunner()
    with caplog.at_level(logging.INFO, logger="gh_manage.commands.labels"):
        runner.invoke(
            main, ["--log-level", "info", "labels", "diff", "owner/repo"]
        )
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.labels"]
    assert any("labels diff invoked" in m and "owner/repo" in m
               for m in msgs), msgs


@pytest.mark.parametrize(
    "exc_factory",
    [
        lambda: GhError("upstream api failed"),
        lambda: ConfigError("config invalid"),
    ],
    ids=["GhError", "ConfigError"],
)
def test_labels_exception_behavior_preserved_after_decorator_swap(
    monkeypatch, exc_factory
):
    exc = exc_factory()

    def _raise(*a, **kw):
        raise exc

    monkeypatch.setattr("gh_manage.github_api.labels.list_labels", _raise)
    runner = CliRunner()
    result = runner.invoke(main, ["labels", "show", "owner/repo"])
    assert result.exit_code != 0
    assert str(exc) in result.output
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/commands/test_labels_logging.py -v
```

Expected: most FAIL (no log records; `_handle_errors` still present).

- [ ] **Step 3: Edit `labels.py` — remove local decorator, add log points**

Edit `src/gh_manage/commands/labels.py`. Replace the entire file header up to `def _format_diff` with:

```python
"""gh manage labels — sync, diff, show GitHub repo labels."""

from __future__ import annotations

import logging
import sys
from importlib.resources import files
from pathlib import Path

import click

from gh_manage import labels_sync
from gh_manage.commands._shared import handle_errors
from gh_manage.config import load_config
from gh_manage.github_api import labels as labels_api
from gh_manage.labels_sync import LabelsDiff
from gh_manage.models.labels import LabelsConfig
from gh_manage.repo_ref import parse_repo

DEFAULT_CONFIG_PATH = Path(str(files("gh_manage.data") / "labels.yml"))

log = logging.getLogger(__name__)
```

Delete the `_F = TypeVar(...)` line, `_handle_errors` decorator definition (L50–63), and the now-unused `functools`/`TypeVar`/`Callable`/`Any` imports.

Keep `_format_diff` unchanged.

Replace `@_handle_errors` with `@handle_errors` on the three commands (`sync`, `diff_cmd`, `show`).

Add log.info at the top of `sync()` body, after the `if apply_flag and dry_run: raise`:

```python
    log.info(
        "labels sync invoked: repo=%s apply=%s prune=%s",
        repo, apply_flag, prune,
    )
```

Add log.info just before the final `click.echo(f"\nApplied {diff.total_changes} changes.")`:

```python
    log.info(
        "labels sync complete: repo=%s changes=%d",
        qualified, diff.total_changes,
    )
    click.echo(f"\nApplied {diff.total_changes} changes.")
```

Add log.info at the top of `diff_cmd()` body:

```python
    log.info("labels diff invoked: repo=%s prune=%s", repo, prune)
```

Add log.info at the top of `show()` body:

```python
    log.info("labels show invoked: repo=%s", repo)
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/commands/test_labels_logging.py -v
```

Expected: all pass.

- [ ] **Step 5: Regression check**

```bash
uv run pytest tests/ -v -k "label" 2>&1 | tail -20
```

Expected: all pre-existing label tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/gh_manage/commands/labels.py tests/unit/commands/test_labels_logging.py
git commit -m "$(cat <<'EOF'
feat(labels): log points + consolidate handle_errors onto _shared

INFO on sync/diff/show invocation + sync completion. Delete local
_handle_errors in favor of _shared.handle_errors (wider _DOMAIN_ERRORS
catch). Exception preservation verified by parametrized test.

Refs #63

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: `protection.py` log points

**Files:**
- Modify: `src/gh_manage/commands/protection.py`
- Create: `tests/unit/commands/test_protection_logging.py`

**Spec ref:** §4.2 (protection row)

- [ ] **Step 1: Write failing tests**

Create `tests/unit/commands/test_protection_logging.py`:

```python
"""caplog-based regression tests for commands/protection.py log points."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from gh_manage.cli import main
from gh_manage.github_client import GhNotFoundError


@pytest.fixture
def mock_protection_deps(monkeypatch):
    fake_profile = MagicMock()
    fake_profile.name = "python-service"
    fake_profile.protection_policy = "standard"
    fake_policy = MagicMock()
    fake_bp_config = MagicMock(policies={"standard": fake_policy})

    def _load(path, cls):
        if "profile" in str(path):
            return fake_profile
        return fake_bp_config

    monkeypatch.setattr("gh_manage.commands.protection.load_config", _load)
    monkeypatch.setattr(
        "gh_manage.commands.protection.resolve_profile_path",
        lambda name: "/tmp/fake-profile.yml",
    )
    monkeypatch.setattr(
        "gh_manage.commands.protection.resolve_branch_protection_path",
        lambda: "/tmp/fake-bp.yml",
    )
    monkeypatch.setattr(
        "gh_manage.git_cli.get_origin_owner_repo", lambda p: "owner/repo"
    )
    monkeypatch.setattr(
        "gh_manage.protection_sync.compute_protection_diff",
        lambda *a, **kw: MagicMock(
            is_empty=True, changes=(), has_downgrades=False, downgrades=[],
        ),
    )
    monkeypatch.setattr(
        "gh_manage.github_api.protection.get_branch_protection",
        lambda *a, **kw: {},
    )


def test_protection_sync_logs_invocation(
    mock_protection_deps, caplog, tmp_path
):
    runner = CliRunner()
    with caplog.at_level(logging.INFO,
                         logger="gh_manage.commands.protection"):
        runner.invoke(
            main,
            ["--log-level", "info", "protection", "sync", str(tmp_path),
             "--profile", "python-service"],
        )
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.protection"]
    assert any("protection sync invoked" in m and "owner/repo" in m
               for m in msgs), msgs


def test_protection_diff_logs_invocation(
    mock_protection_deps, caplog, tmp_path
):
    runner = CliRunner()
    with caplog.at_level(logging.INFO,
                         logger="gh_manage.commands.protection"):
        runner.invoke(
            main,
            ["--log-level", "info", "protection", "diff", str(tmp_path),
             "--profile", "python-service"],
        )
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.protection"]
    assert any("protection diff invoked" in m and "owner/repo" in m
               for m in msgs), msgs


def test_protection_logs_warning_on_ghnotfound(
    mock_protection_deps, caplog, tmp_path, monkeypatch
):
    def _raise(*a, **kw):
        raise GhNotFoundError("404")

    monkeypatch.setattr(
        "gh_manage.github_api.protection.get_branch_protection", _raise
    )
    runner = CliRunner()
    with caplog.at_level(logging.WARNING,
                         logger="gh_manage.commands.protection"):
        runner.invoke(
            main,
            ["protection", "sync", str(tmp_path),
             "--profile", "python-service"],
        )
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.protection"]
    assert any("branch protection not configured" in m and "owner/repo" in m
               for m in msgs), msgs
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/commands/test_protection_logging.py -v
```

Expected: FAIL.

- [ ] **Step 3: Add log points to protection.py**

Edit `src/gh_manage/commands/protection.py`:

Add `import logging` to imports.

Add module-level `log = logging.getLogger(__name__)` after imports.

Inside `sync()`, after `owner_repo = git_cli.get_origin_owner_repo(target)`:

```python
    log.info(
        "protection sync invoked: repo=%s profile=%s apply=%s downgrade_allowed=%s",
        owner_repo, profile_name, apply_flag, downgrade_allowed,
    )
```

Both `except GhNotFoundError:` blocks in `sync()` and `diff_cmd()`:

```python
    except GhNotFoundError:
        log.warning(
            "branch protection not configured on %s@main; treating as empty",
            owner_repo,
        )
        current = {}
```

Inside the `if diff.has_downgrades and downgrade_allowed:` branch of `sync()`, immediately before `backup_dir = resolve_backup_dir()`:

```python
        log.warning(
            "applying protection downgrade on %s@main: %d field(s) weakened",
            owner_repo, len(diff.downgrades),
        )
```

Just before the final `click.echo(f"\nDone. Protection updated for {owner_repo}:main.")` in `sync()`:

```python
    log.info(
        "protection apply complete: repo=%s fields=%d",
        owner_repo, len(diff.changes),
    )
    click.echo(f"\nDone. Protection updated for {owner_repo}:main.")
```

Inside `diff_cmd()`, after `owner_repo = git_cli.get_origin_owner_repo(target)`:

```python
    log.info(
        "protection diff invoked: repo=%s profile=%s",
        owner_repo, profile_name,
    )
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/commands/test_protection_logging.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/commands/protection.py tests/unit/commands/test_protection_logging.py
git commit -m "$(cat <<'EOF'
feat(protection): log points (invocation, completion, 404, downgrade)

Refs #63

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: `init.py` log points

**Files:**
- Modify: `src/gh_manage/commands/init.py`
- Create: `tests/unit/commands/test_init_logging.py`

**Spec ref:** §4.2 (init row)

- [ ] **Step 1: Write failing tests**

Create `tests/unit/commands/test_init_logging.py`:

```python
"""caplog-based regression tests for commands/init.py log points."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from gh_manage.cli import main
from gh_manage.github_client import GhNotFoundError


@pytest.fixture
def mock_init_deps(monkeypatch):
    fake_profile = MagicMock()
    fake_profile.name = "python-service"
    fake_profile.protection_policy = None

    monkeypatch.setattr(
        "gh_manage.commands.init.load_config",
        lambda path, cls: (
            fake_profile if "profile" in str(path) else MagicMock()
        ),
    )
    monkeypatch.setattr(
        "gh_manage.commands.init.resolve_profile_path",
        lambda name: "/tmp/fake.yml",
    )
    monkeypatch.setattr(
        "gh_manage.commands.init.resolve_default_labels_path",
        lambda: "/tmp/labels.yml",
    )
    monkeypatch.setattr(
        "gh_manage.commands.init.resolve_templates_root",
        lambda: "/tmp/tmpl",
    )
    monkeypatch.setattr(
        "gh_manage.git_cli.get_origin_owner_repo",
        lambda p: "owner/repo",
    )
    monkeypatch.setattr(
        "gh_manage.github_api.labels.list_labels", lambda repo: ()
    )
    monkeypatch.setattr(
        "gh_manage.labels_sync.compute_diff",
        lambda *a, **kw: MagicMock(
            is_empty=True, total_changes=0,
            creates=[], updates=[], renames=[],
        ),
    )
    monkeypatch.setattr(
        "gh_manage.profile_sync.compute_files_diff",
        lambda *a, **kw: MagicMock(
            creates=[], overwrites=[], skipped=[], noops=[], is_empty=True,
        ),
    )


def test_init_logs_invocation(mock_init_deps, caplog, tmp_path):
    runner = CliRunner()
    with caplog.at_level(logging.INFO, logger="gh_manage.commands.init"):
        runner.invoke(
            main,
            ["--log-level", "info", "init", str(tmp_path),
             "--profile", "python-service"],
        )
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.init"]
    assert any("init invoked" in m and "owner/repo" in m for m in msgs), msgs


def test_init_logs_completion(
    mock_init_deps, caplog, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "gh_manage.profile_sync.apply_files_diff",
        lambda *a, **kw: [],
    )
    monkeypatch.setattr(
        "gh_manage.labels_sync.apply_diff",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "gh_manage.doctor.run_on_path",
        lambda *a, **kw: (),
    )
    runner = CliRunner()
    with caplog.at_level(logging.INFO, logger="gh_manage.commands.init"):
        runner.invoke(
            main,
            ["--log-level", "info",
             "init", str(tmp_path),
             "--profile", "python-service", "--apply"],
        )
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.init"]
    assert any("init complete" in m for m in msgs), msgs


def test_init_logs_warning_on_ghnotfound(
    caplog, tmp_path, monkeypatch
):
    fake_profile = MagicMock()
    fake_profile.name = "python-service"
    fake_profile.protection_policy = "standard"
    fake_bp = MagicMock(policies={"standard": MagicMock()})

    def _load(path, cls):
        p = str(path)
        if "profile" in p:
            return fake_profile
        if "bp" in p or "branch" in p:
            return fake_bp
        return MagicMock()

    monkeypatch.setattr("gh_manage.commands.init.load_config", _load)
    monkeypatch.setattr(
        "gh_manage.commands.init.resolve_profile_path",
        lambda name: "/tmp/fake.yml",
    )
    monkeypatch.setattr(
        "gh_manage.commands.init.resolve_branch_protection_path",
        lambda: "/tmp/bp.yml",
    )
    monkeypatch.setattr(
        "gh_manage.commands.init.resolve_default_labels_path",
        lambda: "/tmp/labels.yml",
    )
    monkeypatch.setattr(
        "gh_manage.commands.init.resolve_templates_root",
        lambda: "/tmp/tmpl",
    )
    monkeypatch.setattr(
        "gh_manage.git_cli.get_origin_owner_repo",
        lambda p: "owner/repo",
    )
    monkeypatch.setattr(
        "gh_manage.github_api.labels.list_labels", lambda repo: ()
    )
    monkeypatch.setattr(
        "gh_manage.labels_sync.compute_diff",
        lambda *a, **kw: MagicMock(
            is_empty=True, total_changes=0,
            creates=[], updates=[], renames=[],
        ),
    )
    monkeypatch.setattr(
        "gh_manage.profile_sync.compute_files_diff",
        lambda *a, **kw: MagicMock(
            creates=[], overwrites=[], skipped=[], noops=[], is_empty=True,
        ),
    )

    def _raise_404(*a, **kw):
        raise GhNotFoundError("404")

    monkeypatch.setattr(
        "gh_manage.github_api.protection.get_branch_protection", _raise_404
    )
    monkeypatch.setattr(
        "gh_manage.protection_sync.compute_protection_diff",
        lambda *a, **kw: MagicMock(
            is_empty=True, has_downgrades=False, changes=(),
        ),
    )
    runner = CliRunner()
    with caplog.at_level(logging.WARNING,
                         logger="gh_manage.commands.init"):
        runner.invoke(
            main,
            ["init", str(tmp_path), "--profile", "python-service"],
        )
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.init"]
    assert any("branch protection not configured" in m for m in msgs), msgs
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/commands/test_init_logging.py -v
```

Expected: FAIL.

- [ ] **Step 3: Add log points to init.py**

Edit `src/gh_manage/commands/init.py`:

Add `import logging` to imports, `log = logging.getLogger(__name__)` at module level.

Inside `init()`, after `owner_repo = git_cli.get_origin_owner_repo(target)`:

```python
    log.info(
        "init invoked: repo=%s profile=%s apply=%s",
        owner_repo, profile_name, apply_flag,
    )
```

Inside the `except GhNotFoundError:` block:

```python
        except GhNotFoundError:
            log.warning(
                "branch protection not configured on %s@main; treating as empty",
                owner_repo,
            )
            current_protection = {}
```

Inside the `if critical:` block, at the very start (before the existing `click.echo("", err=True)`):

```python
    if critical:
        log.warning(
            "init aborting: critical doctor findings=%d, rolling back %d file(s)",
            len(critical), len(created_paths),
        )
        click.echo("", err=True)
```

Inside the `except OSError as roll_err:` block:

```python
            except OSError as roll_err:
                log.warning(
                    "init rollback: cannot delete %s: %s", p, roll_err,
                )
                failed_deletes.append((p, roll_err))
```

Immediately before `click.echo("\nDone. Next steps:")` at the bottom of `init()`:

```python
    n_protection_changes_final = (
        len(protection_diff.changes) if protection_diff is not None else 0
    )
    log.info(
        "init complete: repo=%s file_changes=%d label_changes=%d protection_changes=%d",
        owner_repo,
        len(files_diff.creates) + len(files_diff.overwrites),
        labels_diff.total_changes,
        n_protection_changes_final,
    )
    click.echo("\nDone. Next steps:")
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/commands/test_init_logging.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/commands/init.py tests/unit/commands/test_init_logging.py
git commit -m "$(cat <<'EOF'
feat(init): log points (invocation, 404, rollback warnings, completion)

Refs #63

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: `doctor.py` log points

**Files:**
- Modify: `src/gh_manage/commands/doctor.py`
- Create: `tests/unit/commands/test_doctor_logging.py`

**Spec ref:** §4.2 (doctor row)

- [ ] **Step 1: Write failing tests**

Create `tests/unit/commands/test_doctor_logging.py`:

```python
"""caplog-based regression tests for commands/doctor.py log points."""

from __future__ import annotations

import logging

import pytest
from click.testing import CliRunner

from gh_manage.cli import main


@pytest.fixture
def mock_doctor_deps(monkeypatch):
    monkeypatch.setattr(
        "gh_manage.doctor.run_on_path", lambda *a, **kw: ()
    )
    monkeypatch.setattr(
        "gh_manage.doctor.run_on_remote", lambda *a, **kw: ()
    )
    monkeypatch.setattr(
        "gh_manage.git_cli.get_origin_owner_repo",
        lambda p: "owner/repo",
    )


def test_doctor_logs_invocation(mock_doctor_deps, caplog, tmp_path):
    runner = CliRunner()
    with caplog.at_level(logging.INFO, logger="gh_manage.commands.doctor"):
        runner.invoke(main, ["--log-level", "info",
                             "doctor", str(tmp_path), "--exit-zero"])
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.doctor"]
    assert any("doctor invoked" in m for m in msgs), msgs


def test_doctor_logs_completion(mock_doctor_deps, caplog, tmp_path):
    runner = CliRunner()
    with caplog.at_level(logging.INFO, logger="gh_manage.commands.doctor"):
        runner.invoke(main, ["--log-level", "info",
                             "doctor", str(tmp_path), "--exit-zero"])
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.doctor"]
    assert any("doctor complete" in m for m in msgs), msgs


def test_doctor_logs_warning_on_label_derivation_error(
    caplog, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "gh_manage.doctor.run_on_path", lambda *a, **kw: ()
    )

    def _raise(p):
        raise RuntimeError("no git origin")

    monkeypatch.setattr("gh_manage.git_cli.get_origin_owner_repo", _raise)
    runner = CliRunner()
    with caplog.at_level(logging.WARNING,
                         logger="gh_manage.commands.doctor"):
        runner.invoke(main, ["doctor", str(tmp_path), "--exit-zero"])
    msgs = [r.message for r in caplog.records
            if r.name == "gh_manage.commands.doctor"]
    assert any("could not derive owner/repo" in m for m in msgs), msgs
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/commands/test_doctor_logging.py -v
```

Expected: FAIL.

- [ ] **Step 3: Add log points to doctor.py**

Edit `src/gh_manage/commands/doctor.py`:

Add `import logging`, `log = logging.getLogger(__name__)`.

At the very top of `doctor_cmd()` body (before the `if _looks_like_owner_repo(...):` branch):

```python
    log.info(
        "doctor invoked: target=%s profile=%s report_mode=%s",
        target, profile_name, report_mode,
    )
```

In `_derive_repo_label`, modify the except clause:

```python
def _derive_repo_label(path: Path, *, fallback: str) -> str:
    from gh_manage import git_cli

    try:
        return git_cli.get_origin_owner_repo(path)
    except Exception as e:
        log.warning("could not derive owner/repo from path %s: %s", path, e)
        return fallback
```

Immediately before `if exit_zero: return`:

```python
    blocking_count = sum(
        1 for f in findings if f.severity in _BLOCKING_SEVERITIES
    )
    log.info(
        "doctor complete: target=%s findings=%d blocking=%d",
        target, len(findings), blocking_count,
    )

    if exit_zero:
        return
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/commands/test_doctor_logging.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/commands/doctor.py tests/unit/commands/test_doctor_logging.py
git commit -m "$(cat <<'EOF'
feat(doctor): log points (invocation, completion, label derivation warning)

Refs #63

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Version bump to 1.9.0 + quality gates

**Files:**
- Modify: `src/gh_manage/__init__.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_sanity.py`
- Regenerate: `uv.lock`

- [ ] **Step 1: Bump __init__.py**

Read `src/gh_manage/__init__.py` (likely just contains `__version__ = "1.8.0"`).

Replace `"1.8.0"` with `"1.9.0"`.

- [ ] **Step 2: Bump pyproject.toml**

Read `pyproject.toml`, locate the `version = "1.8.0"` line in `[project]` section.

Replace with `version = "1.9.0"`.

- [ ] **Step 3: Bump test_sanity.py**

Read `tests/test_sanity.py`, locate the version assertion (e.g., `assert __version__ == "1.8.0"` or similar).

Replace `"1.8.0"` with `"1.9.0"`.

- [ ] **Step 4: Regenerate uv.lock**

```bash
uv sync
```

- [ ] **Step 5: Full test suite**

```bash
uv run pytest -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 6: Lint + format + type check**

```bash
uvx ruff@0.8.0 check src/ tests/
uvx ruff@0.8.0 format --check src/ tests/
uv run mypy src/
```

Expected: all clean.

If `format --check` fails, run `uvx ruff@0.8.0 format src/ tests/` and re-run `format --check` to verify clean.

If `check` fails, inspect and fix. Do NOT suppress — fix root causes.

- [ ] **Step 7: Commit**

```bash
git add src/gh_manage/__init__.py pyproject.toml tests/test_sanity.py uv.lock
git commit -m "$(cat <<'EOF'
chore(release): bump to cli/v1.9.0

Structured logging follow-ups: #63 (command rollout), #64 (scan_id
ContextVar), #65 (--log-file + fail-fast validate).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Push, PR, 4-reviewer protocol, merge, tag

**Files:** N/A (orchestration)

**Spec ref:** §6.2, §7, §8

- [ ] **Step 1: Integration smoke (manual, local)**

These are not automated — run them by hand to verify the feature works end-to-end:

```bash
# 1. dual output
gh-manage --log-level info --log-file /tmp/ghm-smoke.log labels show yakkuro/gh-manage 2>&1 | head -5
grep 'labels show invoked' /tmp/ghm-smoke.log
# Expected: stderr has an INFO line; file has the same INFO line.

# 2. scan_id in JSON mode, proportional to repos.yml
ENABLED=$(uv run python -c "
from gh_manage.config import load_config
from gh_manage.models.repos import ReposConfig
from gh_manage.commands._shared import resolve_repos_path
cfg = load_config(resolve_repos_path(), ReposConfig)
print(sum(1 for r in cfg.repos if r.enabled))
")
echo "enabled repos: $ENABLED"
GH_MANAGE_LOG_JSON=1 gh-manage --log-level info drift --all 2>&1 >/dev/null \
  | jq -s 'group_by(.scan_id) | map({scan: .[0].scan_id, count: length}) | length'
# Expected: equals $ENABLED

# 3. Fail-fast on bad --log-file
gh-manage --log-file /nonexistent-dir/x.log apply .
# Expected: exit 2, "parent directory does not exist"

# 4. Plain mode does NOT leak scan_id
gh-manage --log-level info drift . 2>&1 | grep -c 'scan_id' || true
# Expected: 0
```

If any smoke test fails, fix before pushing.

- [ ] **Step 2: Push branch**

```bash
git push -u origin feat/structured-logging-followups-spec
```

- [ ] **Step 3: Create PR**

```bash
gh pr create --title "feat: structured logging follow-ups (cli/v1.9.0) — #63 #64 #65" --body "$(cat <<'EOF'
## Summary

Bundles three structured-logging follow-ups from PR #66 / cli/v1.8.0 into one cli/v1.9.0 release.

- **#63** (command rollout): INFO/WARNING coverage across `apply`, `labels`, `protection`, `init`, `doctor`
- **#64** (scan_id): ContextVar-based UUID4 per scan; `_ScanIdJsonFormatter` auto-attaches `scan_id` field to JSON output; plain-text unchanged
- **#65** (`--log-file`): dual stderr+file output; `GH_MANAGE_LOG_FILE` envvar; fail-fast validate at CLI startup with `UsageError`

Side cleanup: `labels.py` local `_handle_errors` consolidated onto `_shared.handle_errors` (wider exception catch; parametrized preservation test included).

## Design

- Spec: `docs/specs/2026-04-20-structured-logging-followups-design.md`
- Plan: `docs/plans/2026-04-20-structured-logging-followups-plan.md`
- Decisions from brainstorming Q1–Q4: single PR, ContextVar with JsonFormatter auto-attach, dual output, fail-fast validate.

## Test plan

- [x] `uv run pytest -q` — baseline 587 + ~44 new tests pass (~631 total)
- [x] `uvx ruff@0.8.0 check src/ tests/` clean
- [x] `uvx ruff@0.8.0 format --check src/ tests/` clean
- [x] `uv run mypy src/` clean
- [x] Manual: `gh-manage --log-file /tmp/x.log --log-level info` → dual stderr+file output for a command invocation
- [x] Manual: `GH_MANAGE_LOG_JSON=1 gh-manage drift --all` → distinct UUID4 scan_id per parallel worker, count matches enabled repos in repos.yml
- [x] Manual: `gh-manage --log-file /nonexistent/x.log apply .` → exits with UsageError
- [x] Manual: invocation INFO visible for each of apply/labels/protection/init/doctor at `--log-level info`

Closes #63
Closes #64
Closes #65
Refs #47

Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

Capture the returned PR number for the next steps (assume `$PR` = PR number).

- [ ] **Step 4: Run 4-reviewer protocol in parallel**

Per `~/.claude/rules/workflow-review.md`, run all 4 reviewers concurrently by sending one message with 4 Agent tool calls. Give each reviewer:

- The PR diff (`git diff main..HEAD`)
- The plan path (`docs/plans/2026-04-20-structured-logging-followups-plan.md`) — for superpowers:code-reviewer
- The spec path (`docs/specs/2026-04-20-structured-logging-followups-design.md`) — for all reviewers

Reviewers:
1. **Codex** — `bash scripts/codex-review-resilient.sh "review PR #<PR>"` OR `/codex:review` plugin (background)
2. **superpowers:code-reviewer** via `Agent(subagent_type="superpowers:code-reviewer", ...)` — verify plan-spec alignment
3. **pr-review-toolkit:silent-failure-hunter** via `Agent(subagent_type="pr-review-toolkit:silent-failure-hunter", ...)` — surface suppressed exceptions, silent fallbacks
4. **code-reviewer (project conventions)** via `Agent(subagent_type="code-reviewer", model="sonnet", ...)` — diff size likely ~1000-1500 LOC, sonnet appropriate per model-routing rule

- [ ] **Step 5: Address CRITICAL/HIGH findings**

Per convergence across reviewers:
- Any CRITICAL: stop, fix, re-run only the affected reviewer(s).
- Any HIGH: fix before merge.
- MEDIUM / LOW: triage — fix if quick, otherwise defer to a follow-up Issue.

Push fixes with descriptive commit messages referencing the finding.

- [ ] **Step 6: Watch CI**

```bash
gh pr checks $PR --watch
```

Expected: all checks green. Fix any CI failures.

- [ ] **Step 7: Merge (squash) after all reviews clean + CI green**

```bash
gh pr merge $PR --squash --delete-branch
```

- [ ] **Step 8: Tag release**

```bash
git checkout main && git pull
git tag -a cli/v1.9.0 -m "cli/v1.9.0: structured logging follow-ups (#63, #64, #65)"
git push origin cli/v1.9.0
```

- [ ] **Step 9: GitHub release**

```bash
gh release create cli/v1.9.0 --title "cli/v1.9.0" --notes "$(cat <<'EOF'
## cli/v1.9.0 — structured logging follow-ups

Closes #63, #64, #65.

### Added
- `--log-file PATH` / `GH_MANAGE_LOG_FILE` envvar: write logs to a file in addition to stderr. Fail-fast validate at startup if the path is invalid.
- `scan_id` correlation id in JSON log output: per-scan UUID4, auto-attached to every log record emitted during a drift scan. Plain-text output unchanged.
- Structured logging now covers `apply`, `labels`, `protection`, `init`, `doctor` (cli/v1.8.0 was drift-only).

### Internal
- Consolidate `commands/labels.py` error decorator onto `_shared.handle_errors` (wider `_DOMAIN_ERRORS` catch; no visible behavior change, verified by parametrized preservation test).

### Migration
None. Defaults preserve cli/v1.8.0 behavior (WARNING floor, stderr only, no scan_id unless in JSON mode).
EOF
)"
```

- [ ] **Step 10: Close issues with reference**

```bash
gh issue close 63 64 65 --comment "Resolved in cli/v1.9.0 (PR #$PR)."
```

- [ ] **Step 11: Verify post-merge state**

```bash
git log --oneline main | head -5
# Expected: top commit is the squash-merge of the PR
git tag --list 'cli/v1.*' | tail -3
# Expected: cli/v1.9.0 present
gh issue list --state open --search "label:\"cli/v1.8.0-followup\""
# Expected: #63, #64, #65 not in list (closed)
```

---

## Self-review

Post-drafting sanity pass:

- **Spec coverage**:
  - §2 scan_id: Task 1 (ContextVar), Task 2 (formatter), Task 6 (propagation) ✓
  - §3 --log-file: Task 3 (configure_logging kwarg), Task 4 (validator), Task 5 (CLI wire) ✓
  - §4 rollout: Tasks 7–11 (apply, labels, protection, init, doctor) ✓
  - §4.3 decorator cleanup: Task 8 (labels) ✓
  - §5 testing: every task has caplog/regression tests; §5.5 integration smoke is Task 13 Step 1 ✓
  - §6 risks: addressed by tests (ContextVar thread isolation, labels exception preservation) ✓
  - §7 release: Task 12 (version) + Task 13 (PR/reviews/tag/release notes) ✓
  - §8 acceptance: covered across Tasks 1–13 ✓

- **Placeholder scan**: no "TBD", "TODO", "similar to Task N". All code concrete.

- **Type consistency**:
  - `scan_id_var: ContextVar[str]` consistent in Task 1 test, Task 1 impl, Task 2 formatter, Task 6 set/reset
  - `log_file: Path | None` consistent in Task 3 kwarg, Task 4 validator, Task 5 CLI option (all use `Path`)
  - Log message templates match §4.2 spec tables exactly
  - Commit subjects use Conventional Commits (`feat(apply):`, `chore(release):` etc.)

No placeholders, types consistent, coverage complete.

---

## Execution handoff

Per user's `feedback_subagent_driven_default` + `feedback_execution_mode`: **skip the choice gate and proceed directly to `superpowers:subagent-driven-development`**. No "inline vs subagent" prompt.
