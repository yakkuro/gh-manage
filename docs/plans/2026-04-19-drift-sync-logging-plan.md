# drift_sync Structured Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `logging` into `drift_sync/` + `commands/drift.py` with a hybrid plain/JSON format, a root Click `--log-level` option, and 8 concrete log points that resolve [#62](https://github.com/yakkuro/gh-manage/issues/62) HIGH #3 (malformed-timestamp WARNING) and HIGH #5 (unexpected-exception traceback). Ship as `cli/v1.8.0`.

**Architecture:** Single `gh_manage.logging_config.configure_logging()` entrypoint configures the `gh_manage` logger tree (not root); called once from `cli.py`'s root group callback. Format switches on `GH_MANAGE_LOG_JSON` env var or explicit `json=` arg. Each module uses `log = logging.getLogger(__name__)` so loggers are named `gh_manage.drift_sync.checks` etc. Formatters and datefmts are frozen inside `logging_config.py` to keep caplog record shape stable. Tests use pytest's `caplog` fixture.

**Tech Stack:** Python 3.12, `uv`, `pytest 8`, `pytest-mock`, `click`, `python-json-logger` (NEW dep), `ruff@0.8.0`, `mypy`.

**Spec reference:** `docs/specs/2026-04-19-drift-sync-logging-design.md` (approved 2026-04-19 after spec-critique rounds 1 + 2).

**Branch:** `feat/drift-sync-logging` (already created at 1b66f62; this plan continues on that branch).

---

## File Structure

**Create:**
- `src/gh_manage/logging_config.py` — `configure_logging()` + `LogLevel` type alias.
- `tests/unit/test_logging_config.py` — 7 tests covering the config module.
- `tests/unit/drift/test_logging_events.py` — 7 tests covering log emission points.

**Modify:**
- `pyproject.toml` — add `python-json-logger>=2.0,<3.0` to `[project].dependencies`; bump version to `1.8.0`.
- `uv.lock` — regenerated via `uv sync`.
- `src/gh_manage/__init__.py` — bump `__version__` to `1.8.0`.
- `tests/test_sanity.py` — update version assertion to `1.8.0`.
- `src/gh_manage/cli.py` — add `--log-level` option, call `configure_logging()`.
- `src/gh_manage/drift_sync/registry.py` — 2 DEBUG log points.
- `src/gh_manage/drift_sync/checks.py` — 2 DEBUG + 1 WARNING + 1 ERROR log points.
- `src/gh_manage/drift_sync/issue_state.py` — 1 WARNING (+ 3 INFO) log points (#62 HIGH #3).
- `src/gh_manage/commands/drift.py` — 2 INFO + 1 `log.exception` (#62 HIGH #5).

---

## Pre-flight

### Task 0: Baseline + branch check

**Files:** none (verification only).

- [ ] **Step 1: Confirm branch and clean tree**

```bash
cd /home/server160/repos/gh-manage
git status
git log --oneline -3
```

Expected: on `feat/drift-sync-logging`, clean, HEAD = `1b66f62` (spec round-2 response). If `main` is ahead via a merge, rebase: `git fetch origin && git rebase origin/main`.

- [ ] **Step 2: Record baseline pytest count**

```bash
uv run pytest -q 2>&1 | tail -3
```

Expected: `572 passed` (cli/v1.7.0 baseline). All subsequent tasks end on this count + whatever they add.

---

## Task 1: Add python-json-logger dependency

**Files:**
- Modify: `pyproject.toml` (add dependency only; version bump happens later in Task 9).
- Modify: `uv.lock` (regenerated).

- [ ] **Step 1: Read current dependencies block**

```bash
```

Use Read on `pyproject.toml` to locate the `[project].dependencies` list.

- [ ] **Step 2: Add `python-json-logger` to dependencies**

Use Edit to append `"python-json-logger>=2.0,<3.0",` to the dependencies list (preserve alphabetical ordering if the file maintains it).

- [ ] **Step 3: Regenerate lockfile**

```bash
uv sync
```

Expected: "Prepared 1 package" for `python-json-logger` (≈2.0.7 or later). Install succeeds.

- [ ] **Step 4: Verify import works**

```bash
uv run python -c "from pythonjsonlogger.jsonlogger import JsonFormatter; print(JsonFormatter.__module__)"
```

Expected: `pythonjsonlogger.jsonlogger`.

- [ ] **Step 5: Confirm suite still green**

```bash
uv run pytest -q 2>&1 | tail -3
```

Expected: 572 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
chore(deps): add python-json-logger for structured logging

Prereq for cli/v1.8.0 drift_sync logging rollout. Range `>=2.0,<3.0`
pins a stable major; the dep is a single-module stdlib-compatible
Formatter subclass.

Refs #47 (Theme A item 6), spec docs/specs/2026-04-19-drift-sync-logging-design.md.
EOF
)"
```

---

## Task 2: Implement `logging_config.py` (TDD)

**Files:**
- Create: `tests/unit/test_logging_config.py`
- Create: `src/gh_manage/logging_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_logging_config.py` with this exact content:

```python
"""Tests for gh_manage.logging_config.

All tests clean up the `gh_manage` logger's handler state after each run
so tests don't interfere with each other or with pytest's own logger.
"""

from __future__ import annotations

import io
import logging
import os

import pytest


@pytest.fixture(autouse=True)
def _reset_gh_manage_logger():
    """Save/restore the gh_manage logger state around each test."""
    gh_logger = logging.getLogger("gh_manage")
    saved_handlers = list(gh_logger.handlers)
    saved_level = gh_logger.level
    yield
    gh_logger.handlers[:] = saved_handlers
    gh_logger.setLevel(saved_level)


def test_configure_logging_default_level_is_warning() -> None:
    from gh_manage.logging_config import configure_logging

    configure_logging()
    assert logging.getLogger("gh_manage").level == logging.WARNING


def test_configure_logging_sets_explicit_level() -> None:
    from gh_manage.logging_config import configure_logging

    configure_logging(level="info")
    assert logging.getLogger("gh_manage").level == logging.INFO


def test_configure_logging_plain_formatter_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_MANAGE_LOG_JSON", raising=False)
    from gh_manage.logging_config import configure_logging

    configure_logging()
    handler = logging.getLogger("gh_manage").handlers[0]
    # Plain-text formatter is the stdlib class, not JsonFormatter.
    assert type(handler.formatter).__name__ == "Formatter"


def test_configure_logging_json_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MANAGE_LOG_JSON", "1")
    from gh_manage.logging_config import configure_logging
    from pythonjsonlogger.jsonlogger import JsonFormatter

    configure_logging()
    handler = logging.getLogger("gh_manage").handlers[0]
    assert isinstance(handler.formatter, JsonFormatter)


def test_configure_logging_json_explicit_arg_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Env says yes; explicit arg says no. Explicit wins.
    monkeypatch.setenv("GH_MANAGE_LOG_JSON", "1")
    from gh_manage.logging_config import configure_logging

    configure_logging(json=False)
    handler = logging.getLogger("gh_manage").handlers[0]
    assert type(handler.formatter).__name__ == "Formatter"


def test_configure_logging_idempotent() -> None:
    from gh_manage.logging_config import configure_logging

    configure_logging(level="info")
    configure_logging(level="debug")
    gh_logger = logging.getLogger("gh_manage")
    assert len(gh_logger.handlers) == 1
    assert gh_logger.level == logging.DEBUG


def test_configure_logging_writes_to_stream_argument() -> None:
    """Stream override is how unit tests isolate from real stderr."""
    from gh_manage.logging_config import configure_logging

    buf = io.StringIO()
    configure_logging(level="info", stream=buf)
    logging.getLogger("gh_manage.test").info("sentinel-msg-xyz")
    assert "sentinel-msg-xyz" in buf.getvalue()


def test_configure_logging_does_not_add_handler_to_root_logger() -> None:
    from gh_manage.logging_config import configure_logging

    root_handlers_before = list(logging.getLogger().handlers)
    configure_logging()
    root_handlers_after = list(logging.getLogger().handlers)
    assert root_handlers_before == root_handlers_after, (
        "configure_logging must not touch the root logger — only the "
        "`gh_manage` tree."
    )
```

- [ ] **Step 2: Run tests — confirm they FAIL**

```bash
uv run pytest tests/unit/test_logging_config.py -v 2>&1 | tail -15
```

Expected: 8 collection/import errors (`ModuleNotFoundError: gh_manage.logging_config`). This is the Red phase.

- [ ] **Step 3: Write `logging_config.py`**

Create `src/gh_manage/logging_config.py` with this content:

```python
"""Central logging configuration for gh_manage.

Invoked once from cli.py's root group callback. Configures only the
`gh_manage` logger tree — third-party packages' loggers (click,
pydantic, httpx, etc.) are left alone. Output goes to stderr by
default; tests pass a StringIO via the `stream` argument.

Format is selected at configuration time and cannot be changed at
runtime. This keeps the caplog record shape stable for tests. To
change a format, edit this module.

See docs/specs/2026-04-19-drift-sync-logging-design.md §2.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import IO, Literal

from pythonjsonlogger.jsonlogger import JsonFormatter

LogLevel = Literal["debug", "info", "warning", "error"]

_LOG_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

_PLAIN_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_PLAIN_DATEFMT = "%Y-%m-%d %H:%M:%S"
_JSON_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_JSON_DATEFMT = "%Y-%m-%dT%H:%M:%S"

_TRUTHY = {"1", "true", "yes"}


def _env_says_json() -> bool:
    raw = os.environ.get("GH_MANAGE_LOG_JSON", "").strip().lower()
    return raw in _TRUTHY


def configure_logging(
    level: LogLevel = "warning",
    json: bool | None = None,
    stream: IO[str] | None = None,
) -> None:
    """Configure gh_manage's root logger tree. Idempotent.

    See module docstring and spec §2 for rationale and full contract.
    """
    if json is None:
        json = _env_says_json()

    if stream is None:
        stream = sys.stderr

    formatter: logging.Formatter
    if json:
        formatter = JsonFormatter(_JSON_FORMAT, datefmt=_JSON_DATEFMT)
    else:
        formatter = logging.Formatter(_PLAIN_FORMAT, datefmt=_PLAIN_DATEFMT)

    handler = logging.StreamHandler(stream=stream)
    handler.setFormatter(formatter)

    gh_logger = logging.getLogger("gh_manage")
    # Drop prior handlers so repeat calls (idempotent contract) don't stack.
    gh_logger.handlers[:] = [handler]
    gh_logger.setLevel(_LOG_LEVELS[level])
    # Don't propagate to the root logger — otherwise a user who
    # configures a root handler for third-party logs would see our
    # records duplicated.
    gh_logger.propagate = False
```

- [ ] **Step 4: Run tests — confirm they PASS**

```bash
uv run pytest tests/unit/test_logging_config.py -v 2>&1 | tail -15
```

Expected: 8 passed. (Green phase.)

- [ ] **Step 5: Full suite + lint + types**

```bash
uv run pytest -q 2>&1 | tail -3
uvx ruff@0.8.0 check src/ tests/
uvx ruff@0.8.0 format --check src/ tests/
uv run mypy src/
```

Expected: 580 passed (572 + 8), ruff clean, mypy clean.

- [ ] **Step 6: Commit**

```bash
git add src/gh_manage/logging_config.py tests/unit/test_logging_config.py
git commit -m "$(cat <<'EOF'
feat(logging): add gh_manage.logging_config module

Central configure_logging(level, json, stream) that sets up the
`gh_manage` logger tree — not the root — with a stderr handler and a
frozen format string (plain default, JSON via GH_MANAGE_LOG_JSON env
or explicit json= arg). Idempotent.

8 tests covering level default + override, plain/JSON format switch,
env-vs-arg precedence, idempotency, stream override, and root-logger
isolation.

No call sites yet — wired in cli.py in next commit.

Refs #47 (Theme A item 6), spec docs/specs/2026-04-19-drift-sync-logging-design.md.
EOF
)"
```

---

## Task 3: Wire `configure_logging` into CLI entry

**Files:**
- Modify: `src/gh_manage/cli.py`

- [ ] **Step 1: Update cli.py**

Replace the current `@click.group(...)` decorator and `main` function with the following (the rest of the file stays unchanged):

```python
"""Top-level click group for gh-manage."""

from __future__ import annotations

import click

from gh_manage import __version__
from gh_manage.commands import (
    apply as apply_cmd,
    doctor as doctor_cmd,
    drift as drift_cmd,
    init as init_cmd,
    issues as issues_cmd,
    labels as labels_cmd,
    protection as protection_cmd,
)
from gh_manage.logging_config import LogLevel, configure_logging


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    help=(
        "gh-manage — GitHub-based CI/CD, Issue management, and operations "
        "for yakkuro/* repositories."
    ),
)
@click.version_option(version=__version__, prog_name="gh-manage")
@click.option(
    "--log-level",
    type=click.Choice(["debug", "info", "warning", "error"], case_sensitive=False),
    envvar="GH_MANAGE_LOG_LEVEL",
    default="warning",
    show_default=True,
    help=(
        "Logging verbosity for gh_manage modules. Also honours "
        "GH_MANAGE_LOG_LEVEL. For JSON output, set GH_MANAGE_LOG_JSON=1."
    ),
)
def main(log_level: str) -> None:
    """Root command group. Subcommands are registered below."""
    configure_logging(level=log_level.lower())  # type: ignore[arg-type]


main.add_command(init_cmd.init)
main.add_command(apply_cmd.apply)
main.add_command(doctor_cmd.doctor_cmd)
main.add_command(labels_cmd.labels)
main.add_command(protection_cmd.protection)
main.add_command(drift_cmd.drift)
main.add_command(issues_cmd.issues)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manual smoke — default and explicit levels**

```bash
# No log output expected at default WARNING level.
uv run gh-manage drift . --profile python-service 2>/tmp/stderr.default >/dev/null
wc -l /tmp/stderr.default
# Expected: 0 lines of log output (click.echo progress still prints, but there
# are no INFO/WARN/ERROR loggers emitting at default level in a clean scan).

# Explicit --log-level info shows INFO records we'll add in later tasks.
# At this point no log points exist yet, so the INFO stream is empty too —
# that's fine, this task only verifies the CLI wires up.
uv run gh-manage --log-level info drift . --profile python-service 2>/tmp/stderr.info >/dev/null
cat /tmp/stderr.info | head -5
# Expected: runs without error. No log output until Task 4+ adds log points.

# Help text shows the new option.
uv run gh-manage --help | grep -A 2 log-level
# Expected: "--log-level [debug|info|warning|error]" visible in help output.
```

- [ ] **Step 3: Verify**

```bash
uv run pytest -q 2>&1 | tail -3
uvx ruff@0.8.0 check src/
uv run mypy src/
```

Expected: 580 passed, ruff clean, mypy clean.

- [ ] **Step 4: Commit**

```bash
git add src/gh_manage/cli.py
git commit -m "$(cat <<'EOF'
feat(cli): wire --log-level root option + configure_logging on startup

Adds --log-level to the root Click group with envvar GH_MANAGE_LOG_LEVEL
and default "warning". The group callback invokes configure_logging()
once so every subcommand benefits without needing per-command setup.

For JSON output, users set GH_MANAGE_LOG_JSON=1 (documented in --help).

Log points will be added in subsequent commits (drift_sync + commands/drift).

Refs #47 (Theme A item 6).
EOF
)"
```

---

## Task 4: Add log points in `drift_sync/registry.py`

**Files:**
- Modify: `src/gh_manage/drift_sync/registry.py`

- [ ] **Step 1: Update registry.py**

Add a module-level logger and two DEBUG log lines around each check invocation. Edit the file so it reads:

```python
"""Check registry + severity filter.

Layer 2 of the drift_sync package. Depends on context (for ScanContext)
and on gh_manage.findings (for Finding/Severity). Does NOT depend on
adapters, checks, formatters, or issue_state.

The module-level _CHECKS list is the single source of truth for which
drift checks run. @register_check mutates _CHECKS at import time; every
submodule that defines a @register_check-decorated function must be
imported by __init__.py for the check to be registered.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from itertools import chain

from gh_manage.drift_sync.context import ScanContext
from gh_manage.findings import Finding, Severity

log = logging.getLogger(__name__)

CheckFn = Callable[["ScanContext"], tuple[Finding, ...]]
_CHECKS: list[CheckFn] = []


def register_check(fn: CheckFn) -> CheckFn:
    """Decorator: register a check function in the global registry.

    Intended usage:

        @register_check
        def check_labels(ctx: ScanContext) -> tuple[Finding, ...]:
            ...

    Order of registration determines order of execution in
    run_all_checks. Phase 8 registers check_labels, check_protection,
    check_profile_files in that order.
    """
    _CHECKS.append(fn)
    return fn


def run_all_checks(ctx: ScanContext) -> tuple[Finding, ...]:
    """Run every registered check in order and concatenate findings.

    Fail-fast: if a check raises, the exception propagates and no
    further checks run. MVP does not have a --continue-on-error flag;
    that is filed as a Phase 8.5+ Issue.
    """
    all_findings: list[Finding] = []
    for check in _CHECKS:
        log.debug("running check: %s", check.__name__)
        findings = check(ctx)
        log.debug("check %s returned %d findings", check.__name__, len(findings))
        all_findings.extend(findings)
    return tuple(all_findings)


_SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def _filter_by_severity(
    findings: tuple[Finding, ...], min_severity: Severity
) -> tuple[Finding, ...]:
    """Filter findings to those with severity >= min_severity.

    Hierarchy (highest to lowest): critical > high > medium > low.
    Input order is preserved for stable reporting.
    """
    threshold = _SEVERITY_RANK[min_severity]
    return tuple(f for f in findings if _SEVERITY_RANK[f.severity] >= threshold)
```

Note the change to `run_all_checks`: previously it used `tuple(chain.from_iterable(check(ctx) for check in _CHECKS))`, which is a single expression. The new implementation uses an explicit loop so `log.debug` can bracket each check.

- [ ] **Step 2: Verify imports still clean (chain no longer used)**

```bash
uvx ruff@0.8.0 check src/gh_manage/drift_sync/registry.py 2>&1 | tail -5
```

Expected: `All checks passed!`. If `chain` is flagged as unused, remove the `from itertools import chain` line (it's no longer needed — the new `for`-loop replaced `chain.from_iterable`).

- [ ] **Step 3: Full verify**

```bash
uv run pytest -q 2>&1 | tail -3
uv run mypy src/
```

Expected: 580 passed, mypy clean.

- [ ] **Step 4: Manual — DEBUG visible at debug level**

```bash
uv run gh-manage --log-level debug drift . --profile python-service 2>&1 | grep -E "DEBUG.+check" | head -6
```

Expected: 6 lines (3 checks × 2 DEBUG lines each: entry + exit). E.g.:

```
2026-04-19 10:23:00 DEBUG gh_manage.drift_sync.registry: running check: check_labels
2026-04-19 10:23:01 DEBUG gh_manage.drift_sync.registry: check check_labels returned 1 findings
...
```

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/drift_sync/registry.py
git commit -m "$(cat <<'EOF'
feat(drift_sync/registry): DEBUG-level logs around each check call

run_all_checks now logs entry + finding-count-exit for every registered
check. Loop replaces the `chain.from_iterable` one-liner so log.debug
can bracket each call. No behavior change to findings output.

Refs #47 (Theme A item 6).
EOF
)"
```

---

## Task 5: Add log points in `drift_sync/checks.py`

**Files:**
- Modify: `src/gh_manage/drift_sync/checks.py`

- [ ] **Step 1: Update imports + add logger at module top**

At the top of `checks.py`, add `import logging` to the stdlib block and `log = logging.getLogger(__name__)` below the imports (before the `@register_check` decorators). The file currently starts:

```python
from __future__ import annotations

import hashlib
from importlib.resources import files as _package_files
from pathlib import Path
...
```

Change the stdlib imports block to include `logging`:

```python
from __future__ import annotations

import hashlib
import logging
from importlib.resources import files as _package_files
from pathlib import Path
```

Then after all imports but before the first function, add:

```python
log = logging.getLogger(__name__)
```

- [ ] **Step 2: Instrument `check_labels`**

Inside `check_labels`, add a DEBUG line before the API call. Before:

```python
    current = labels_api.list_labels(ctx.repo)
```

After:

```python
    log.debug("fetching labels for %s", ctx.repo)
    current = labels_api.list_labels(ctx.repo)
```

- [ ] **Step 3: Instrument `check_protection`**

Inside the `try`/`except GhNotFoundError` block, add a WARNING log before the existing `current = {}` fallback. Before:

```python
    try:
        current = protection_api.get_branch_protection(ctx.repo, ctx.default_branch)
    except GhNotFoundError:
        current = {}
```

After:

```python
    try:
        current = protection_api.get_branch_protection(ctx.repo, ctx.default_branch)
    except GhNotFoundError:
        log.warning(
            "branch protection not configured on %s@%s; treating as empty",
            ctx.repo,
            ctx.default_branch,
        )
        current = {}
```

This is the **one intentional behavior change** called out in spec §4 / §7.

- [ ] **Step 4: Instrument `_read_template_content`**

Add a `log.error` *before* the existing `raise DriftError(...)` (not instead — callers still need the exception). Before:

```python
    except OSError as e:
        raise DriftError(
            f"Cannot read bundled template {source!r} at {template_path}: {e}. "
            f"This may indicate a packaging bug — the template should be "
            f"bundled in gh_manage.data.templates."
        ) from e
```

After:

```python
    except OSError as e:
        log.error(
            "failed to read bundled template %r at %s: %s", source, template_path, e
        )
        raise DriftError(
            f"Cannot read bundled template {source!r} at {template_path}: {e}. "
            f"This may indicate a packaging bug — the template should be "
            f"bundled in gh_manage.data.templates."
        ) from e
```

- [ ] **Step 5: Verify**

```bash
uvx ruff@0.8.0 check src/gh_manage/drift_sync/checks.py 2>&1 | tail -3
uv run pytest -q 2>&1 | tail -3
uv run mypy src/
```

Expected: ruff clean, 580 passed, mypy clean.

- [ ] **Step 6: Commit**

```bash
git add src/gh_manage/drift_sync/checks.py
git commit -m "$(cat <<'EOF'
feat(drift_sync/checks): log DEBUG/WARNING/ERROR on fetch + guarded paths

- check_labels: DEBUG before labels_api.list_labels.
- check_protection: WARNING before the existing GhNotFoundError → empty
  fallback (intentional behavior change per spec §4 — the findings
  tuple and exit code are unchanged; only a new log line).
- _read_template_content: ERROR before the existing `raise DriftError`
  so packaging bugs leave an operational breadcrumb even when the
  exception propagates through.

Refs #47 (Theme A item 6).
EOF
)"
```

---

## Task 6: Add log points in `drift_sync/issue_state.py` (#62 HIGH #3)

**Files:**
- Modify: `src/gh_manage/drift_sync/issue_state.py`

- [ ] **Step 1: Add logger at module top**

Edit the imports block to add `import logging` and below it, `log = logging.getLogger(__name__)`:

```python
from __future__ import annotations

import logging
import re as _re
from datetime import datetime, timedelta
from typing import Any

from gh_manage.drift_sync.formatters import format_issue_body, format_issue_comment
from gh_manage.findings import Finding
from gh_manage.github_api import issues as issues_api

log = logging.getLogger(__name__)
```

- [ ] **Step 2: #62 HIGH #3 — log malformed timestamps**

In `parse_zero_findings_timestamps`, replace the silent `continue` with a WARNING. Before:

```python
            try:
                ts = datetime.fromisoformat(match.group(1))
                timestamps.append(ts)
            except ValueError:
                # Malformed timestamp — skip
                continue
```

After:

```python
            try:
                ts = datetime.fromisoformat(match.group(1))
                timestamps.append(ts)
            except ValueError as e:
                log.warning(
                    "malformed zero-findings timestamp %r skipped: %s",
                    match.group(1),
                    e,
                )
                continue
```

- [ ] **Step 3: Instrument `resolve_drift_issue` — create/update/close**

Edit `resolve_drift_issue` so each terminal branch logs INFO before returning. Replace the whole function with:

```python
def resolve_drift_issue(
    findings: tuple[Finding, ...],
    repo: str,
    scan_time: str,
) -> str:
    """Issue state machine: search → create/update/close.

    Returns a human-readable status string for CLI output.
    """
    issues_api.ensure_drift_label(repo)
    existing = issues_api.search_drift_issue(repo)
    has_findings = len(findings) > 0

    if existing is None:
        # No open Issue
        if not has_findings:
            return f"No drift detected for {repo}. No Issue created."
        # Create new Issue
        body = format_issue_body(findings, repo, scan_time)
        comment = format_issue_comment(findings, scan_time)
        title = _DRIFT_ISSUE_TITLE_TEMPLATE.format(repo=repo)
        issue = issues_api.create_issue(repo, title, body, [_DRIFT_LABEL])
        issues_api.add_issue_comment(repo, issue["number"], comment)
        log.info(
            "created drift issue #%d on %s (%d findings)",
            issue["number"],
            repo,
            len(findings),
        )
        return f"Created issue #{issue['number']} on {repo} ({len(findings)} findings)"

    issue_number = existing["number"]

    # Update existing Issue
    body = format_issue_body(findings, repo, scan_time)
    comment = format_issue_comment(findings, scan_time)
    issues_api.update_issue_body(repo, issue_number, body)
    issues_api.add_issue_comment(repo, issue_number, comment)

    if not has_findings:
        # Check 24h close rule
        comments = issues_api.get_issue_comments(repo, issue_number, per_page=5)
        if should_close_issue(comments):
            issues_api.close_issue(repo, issue_number)
            issues_api.add_issue_comment(
                repo,
                issue_number,
                f"## Auto-closed — {scan_time}\n\n"
                f"Zero drift detected on 2 consecutive scans ≥24h apart. "
                f"If drift recurs, a new Issue will be created.",
            )
            log.info(
                "closed drift issue #%d on %s (24h zero-drift rule)",
                issue_number,
                repo,
            )
            return f"Closed issue #{issue_number} on {repo} (zero drift, 24h rule satisfied)"

    log.info(
        "updated drift issue #%d on %s (%d findings)",
        issue_number,
        repo,
        len(findings),
    )
    return f"Updated issue #{issue_number} on {repo} ({len(findings)} findings)"
```

- [ ] **Step 4: Verify**

```bash
uvx ruff@0.8.0 check src/gh_manage/drift_sync/issue_state.py 2>&1 | tail -3
uv run pytest -q 2>&1 | tail -3
uv run mypy src/
```

Expected: ruff clean, 580 passed, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/drift_sync/issue_state.py
git commit -m "$(cat <<'EOF'
feat(drift_sync/issue_state): WARN malformed timestamps + INFO state transitions

- parse_zero_findings_timestamps: malformed ISO8601 timestamps now emit
  WARNING with the raw value and ValueError detail, then continue as
  before. Resolves #62 HIGH #3.
- resolve_drift_issue: INFO logs for each create / update / close
  transition, including finding count. Useful for cron audit trails
  in JSON mode.

No behavior change beyond the new log lines.

Refs #47 (Theme A item 6), closes part of #62 (HIGH #3).
EOF
)"
```

---

## Task 7: Add log points in `commands/drift.py` (#62 HIGH #5)

**Files:**
- Modify: `src/gh_manage/commands/drift.py`

- [ ] **Step 1: Add logger at module top**

Add `import logging` to the stdlib imports block and `log = logging.getLogger(__name__)` below the imports:

```python
# Near the top of commands/drift.py (existing imports preserved).
import logging
# ... existing imports ...

log = logging.getLogger(__name__)
```

- [ ] **Step 2: Instrument `_scan_single_repo` — start + complete**

Find `_scan_single_repo` (it's the per-repo helper). At the entry add an INFO with repo + profile; at the exit (before the final return / before the summary string is built) add an INFO with the finding count. Use Read + Edit: the existing function body looks like:

```python
def _scan_single_repo(
    repo: str,
    profile_name: str,
    ...,
) -> str:
    # ... existing logic ...
    findings = run_all_checks(ctx)
    # ... format + return ...
```

Add at function entry (first statement):

```python
    log.info("scanning %s (profile=%s)", repo, profile_name)
```

And directly after `findings = run_all_checks(ctx)`:

```python
    log.info(
        "scan complete for %s: %d findings", repo, len(findings)
    )
```

(If you can't cleanly identify "first statement" vs "after findings =" due to surrounding control flow, use Read first to get the exact structure.)

- [ ] **Step 3: #62 HIGH #5 — log.exception in `_worker` catch-all**

Inside `_worker` (commands/drift.py:178-208), add `log.exception(...)` in the broad `except Exception` branch. Before:

```python
        except Exception as e:  # noqa: BLE001 — parallel isolation, spec §2
            return (entry.name, "FAILED", e)
```

After:

```python
        except Exception as e:  # noqa: BLE001 — parallel isolation, spec §2
            log.exception(
                "unexpected error scanning %s (%s: %s)",
                entry.name,
                type(e).__name__,
                e,
            )
            return (entry.name, "FAILED", e)
```

`log.exception` automatically attaches the current exception's traceback, which is exactly the operational breadcrumb #62 HIGH #5 requested.

- [ ] **Step 4: Verify**

```bash
uvx ruff@0.8.0 check src/gh_manage/commands/drift.py 2>&1 | tail -3
uv run pytest -q 2>&1 | tail -3
uv run mypy src/
```

Expected: ruff clean, 580 passed, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/commands/drift.py
git commit -m "$(cat <<'EOF'
feat(commands/drift): INFO scan lifecycle + log.exception for unexpected worker errors

- _scan_single_repo: INFO at start (repo + profile) and completion
  (finding count). Useful for human and agent observation of parallel
  --all runs.
- _worker: the catch-all `except Exception` branch now calls
  log.exception before materializing the exception as FAILED. Captures
  full traceback in logs without disturbing parallel isolation
  semantics. Resolves #62 HIGH #5.

No behavior change to findings output or exit codes.

Refs #47 (Theme A item 6), closes part of #62 (HIGH #5).
EOF
)"
```

---

## Task 8: Event-emission regression tests

**Files:**
- Create: `tests/unit/drift/test_logging_events.py`

- [ ] **Step 1: Write the test file**

Create `tests/unit/drift/test_logging_events.py`:

```python
"""Regression guards for the log points added in cli/v1.8.0.

Each test uses pytest's caplog fixture (which captures records
regardless of stream or handler, so tests don't need configure_logging).
These tests pin each log point's logger name, level, and key content,
so future refactors that silently drop a log emission will fail.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def _propagate_gh_manage_logger():
    """caplog captures records via the root logger. configure_logging
    disables propagation on `gh_manage` to avoid duplicate output in
    production. Re-enable propagation inside tests so caplog sees our
    records.
    """
    gh_logger = logging.getLogger("gh_manage")
    prev = gh_logger.propagate
    gh_logger.propagate = True
    yield
    gh_logger.propagate = prev


def _make_scan_context(tmp_path: Path):
    from gh_manage.drift_sync import ScanContext
    from gh_manage.models.labels import CategorySpec, LabelSpec, LabelsConfig
    from gh_manage.models.profiles import ProfileSpec

    labels_config = LabelsConfig(
        version=1,
        categories={
            "sentinel": CategorySpec(
                description="test category",
                labels=[LabelSpec(name="sentinel", color="ffffff")],
            ),
        },
    )
    profile = ProfileSpec(
        version=1,
        name="python-service",
        description="test",
        files=[],
        protection_policy=None,
    )
    return ScanContext(
        path=tmp_path,
        repo="yakkuro/sentinel-repo",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=None,
    )


def test_check_protection_warns_on_not_found(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """check_protection: GhNotFoundError fallback now emits WARNING
    (spec §4 behavior change; new log line, unchanged findings)."""
    from gh_manage.drift_sync import ScanContext
    from gh_manage.drift_sync.checks import check_protection
    from gh_manage.github_client import GhNotFoundError
    from gh_manage.models.branch_protection import (
        BranchProtectionConfig,
        ProtectionPolicy,
    )
    from gh_manage.models.profiles import ProfileSpec
    from gh_manage.models.labels import CategorySpec, LabelSpec, LabelsConfig

    # Profile WITH a protection policy, so the code reaches the API call.
    policy = ProtectionPolicy(
        require_pull_request=True,
        require_status_checks=True,
        required_status_checks=["PR Gate / PR Gate"],
        require_approvals=0,
        dismiss_stale_reviews=False,
        require_code_owner_reviews=False,
        allow_force_pushes=False,
        allow_deletions=False,
        enforce_admins=False,
    )
    bp_config = BranchProtectionConfig(version=1, policies={"solo-default": policy})
    profile = ProfileSpec(
        version=1,
        name="python-service",
        description="test",
        files=[],
        protection_policy="solo-default",
    )
    labels_config = LabelsConfig(
        version=1,
        categories={
            "sentinel": CategorySpec(
                description="test",
                labels=[LabelSpec(name="sentinel", color="ffffff")],
            ),
        },
    )
    ctx = ScanContext(
        path=tmp_path,
        repo="yakkuro/sentinel-repo",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=bp_config,
    )

    mocker.patch(
        "gh_manage.drift_sync.checks.protection_api.get_branch_protection",
        side_effect=GhNotFoundError("not found"),
    )

    with caplog.at_level(logging.WARNING, logger="gh_manage.drift_sync.checks"):
        check_protection(ctx)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "branch protection not configured" in r.getMessage() for r in warnings
    ), f"expected WARNING about branch protection, got: {[r.getMessage() for r in warnings]}"


def test_parse_zero_findings_warns_on_malformed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#62 HIGH #3 regression guard: malformed timestamps no longer
    silently swallowed."""
    from gh_manage.drift_sync.issue_state import parse_zero_findings_timestamps

    comments = [
        {"body": "<!-- scan:zero-findings:2026-04-19T09:00:00 -->"},
        {"body": "<!-- scan:zero-findings:NOT_A_DATE -->"},
    ]
    with caplog.at_level(logging.WARNING, logger="gh_manage.drift_sync.issue_state"):
        result = parse_zero_findings_timestamps(comments)

    # Only the valid timestamp survives.
    assert len(result) == 1

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "expected a WARNING for the malformed timestamp"
    assert "malformed" in warnings[0].getMessage().lower()
    assert "NOT_A_DATE" in warnings[0].getMessage()


def test_resolve_drift_issue_logs_created_event(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from gh_manage.drift_sync.issue_state import resolve_drift_issue
    from gh_manage.findings import Finding

    mocker.patch("gh_manage.drift_sync.issues_api.ensure_drift_label")
    mocker.patch(
        "gh_manage.drift_sync.issues_api.search_drift_issue", return_value=None
    )
    mocker.patch(
        "gh_manage.drift_sync.issues_api.create_issue", return_value={"number": 42}
    )
    mocker.patch("gh_manage.drift_sync.issues_api.add_issue_comment")

    findings = (
        Finding(
            severity="high",
            check="labels",
            repo="yakkuro/sentinel",
            field_path="labels[x]",
            current_value=None,
            desired_value="x",
            message="missing",
            remediation=None,
        ),
    )
    with caplog.at_level(logging.INFO, logger="gh_manage.drift_sync.issue_state"):
        resolve_drift_issue(findings, "yakkuro/sentinel", "2026-04-19T10:00:00")

    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("created drift issue #42" in m for m in msgs)


def test_resolve_drift_issue_logs_updated_event(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from gh_manage.drift_sync.issue_state import resolve_drift_issue
    from gh_manage.findings import Finding

    mocker.patch("gh_manage.drift_sync.issues_api.ensure_drift_label")
    mocker.patch(
        "gh_manage.drift_sync.issues_api.search_drift_issue",
        return_value={"number": 99},
    )
    mocker.patch("gh_manage.drift_sync.issues_api.update_issue_body")
    mocker.patch("gh_manage.drift_sync.issues_api.add_issue_comment")

    findings = (
        Finding(
            severity="medium",
            check="labels",
            repo="yakkuro/sentinel",
            field_path="labels[y]",
            current_value=None,
            desired_value="y",
            message="drifted",
            remediation=None,
        ),
    )
    with caplog.at_level(logging.INFO, logger="gh_manage.drift_sync.issue_state"):
        resolve_drift_issue(findings, "yakkuro/sentinel", "2026-04-19T10:00:00")

    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("updated drift issue #99" in m for m in msgs)


def test_resolve_drift_issue_logs_closed_event(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from gh_manage.drift_sync.issue_state import resolve_drift_issue

    mocker.patch("gh_manage.drift_sync.issues_api.ensure_drift_label")
    mocker.patch(
        "gh_manage.drift_sync.issues_api.search_drift_issue",
        return_value={"number": 7},
    )
    mocker.patch("gh_manage.drift_sync.issues_api.update_issue_body")
    mocker.patch("gh_manage.drift_sync.issues_api.add_issue_comment")
    mocker.patch(
        "gh_manage.drift_sync.issues_api.get_issue_comments",
        return_value=[
            {"body": "<!-- scan:zero-findings:2026-04-19T10:00:00 -->"},
            {"body": "<!-- scan:zero-findings:2026-04-18T09:59:00 -->"},
        ],
    )
    mocker.patch("gh_manage.drift_sync.issues_api.close_issue")

    with caplog.at_level(logging.INFO, logger="gh_manage.drift_sync.issue_state"):
        resolve_drift_issue((), "yakkuro/sentinel", "2026-04-19T10:00:00")

    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("closed drift issue #7" in m for m in msgs)


def test_worker_logs_exception_with_traceback(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#62 HIGH #5 regression guard: unexpected exceptions in the
    parallel worker now leave a traceback in the logs."""
    from gh_manage.commands.drift import _worker
    from gh_manage.models.repos import RepoEntry

    mocker.patch(
        "gh_manage.commands.drift._scan_single_repo",
        side_effect=TypeError("sentinel"),
    )
    entry = RepoEntry(name="yakkuro/sentinel-repo", profile="python-service")

    with caplog.at_level(logging.ERROR, logger="gh_manage.commands.drift"):
        name, status, payload = _worker(entry)

    assert name == "yakkuro/sentinel-repo"
    assert status == "FAILED"
    assert isinstance(payload, TypeError)

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors, "expected an ERROR record for the unexpected exception"
    last = errors[-1]
    assert last.name == "gh_manage.commands.drift"
    assert last.exc_info is not None
    assert last.exc_info[0] is TypeError


def test_debug_events_hidden_at_warning_level(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """At default WARNING level, DEBUG events from registry/checks are
    not captured. This is a floor sanity check; if it fails, every
    `gh-manage drift .` invocation would spew debug output."""
    from gh_manage.drift_sync import run_all_checks

    mocker.patch(
        "gh_manage.drift_sync.checks.labels_api.list_labels", return_value=[]
    )
    mocker.patch(
        "gh_manage.drift_sync.checks.protection_api.get_branch_protection",
        return_value={},
    )

    ctx = _make_scan_context(tmp_path)

    with caplog.at_level(logging.WARNING, logger="gh_manage.drift_sync"):
        run_all_checks(ctx)

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert not debug_records, (
        "DEBUG records were captured at WARNING level — logger config "
        "is letting them through. Records: "
        f"{[r.getMessage() for r in debug_records]}"
    )
```

- [ ] **Step 2: Run the new tests**

```bash
uv run pytest tests/unit/drift/test_logging_events.py -v 2>&1 | tail -15
```

Expected: 7 passed. If `_propagate_gh_manage_logger` isn't enough to get caplog to see records (some test runners require `-p logging`), inspect the first failing test's output — the fixture ensures `gh_manage`'s `propagate=False` (set by `configure_logging`) is flipped back on for the duration of each test.

- [ ] **Step 3: Full verify**

```bash
uv run pytest -q 2>&1 | tail -3
uvx ruff@0.8.0 check src/ tests/
uv run mypy src/
```

Expected: 587 passed (572 + 8 logging_config + 7 logging_events), ruff clean, mypy clean.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/drift/test_logging_events.py
git commit -m "$(cat <<'EOF'
test(drift): 7 regression guards for logging event emission

- test_check_protection_warns_on_not_found (§4 behavior change)
- test_parse_zero_findings_warns_on_malformed (#62 HIGH #3 guard)
- test_resolve_drift_issue_logs_created_event
- test_resolve_drift_issue_logs_updated_event
- test_resolve_drift_issue_logs_closed_event
- test_worker_logs_exception_with_traceback (#62 HIGH #5 guard)
- test_debug_events_hidden_at_warning_level

All use caplog. Autouse fixture re-enables gh_manage logger propagation
so caplog's root-level capture sees our records (configure_logging
disables propagation in production to avoid third-party duplication).

Refs #47 (Theme A item 6).
EOF
)"
```

---

## Task 9: Integration verification + version bump

**Files:**
- Modify: `pyproject.toml` (version), `src/gh_manage/__init__.py`, `tests/test_sanity.py`, `uv.lock`.

- [ ] **Step 1: Manual AC — default, debug, JSON modes**

```bash
# 1. Default: no log output (WARNING floor on clean repo). click.echo summary still prints.
uv run gh-manage drift . --profile python-service 2> /tmp/default.stderr > /tmp/default.stdout
grep -E "INFO|DEBUG|WARNING|ERROR" /tmp/default.stderr | head -5
# Expected: possibly 1-2 WARNINGs (e.g., branch protection not configured on the
# gh-manage repo itself). Zero INFO or DEBUG.

# 2. --log-level info: INFO lines from scan lifecycle + issue state appear.
uv run gh-manage --log-level info drift . --profile python-service 2>&1 | grep -E "INFO gh_manage" | head -5
# Expected: at least 2 INFO lines (scanning ..., scan complete ...).

# 3. --log-level debug: check-entry/exit DEBUG visible.
uv run gh-manage --log-level debug drift . --profile python-service 2>&1 | grep -E "DEBUG.+registry" | head -6
# Expected: 6 lines (3 checks × 2 debug logs).

# 4. JSON mode: every log line parses as JSON.
GH_MANAGE_LOG_JSON=1 uv run gh-manage --log-level info drift . --profile python-service 2>&1 | \
  grep -E "^\{" | head -3 | jq . > /tmp/json-out
cat /tmp/json-out
# Expected: valid JSON records with keys: timestamp, level, name, message.
```

- [ ] **Step 2: Full-fleet scan — no unexpected errors, no regressions**

```bash
uv run gh-manage drift --all --concurrency 4 2>&1 | grep -E "scanned|FAILED" | tail -5
```

Expected: `22/22 scanned`, no FAILED. Logs from the parallel workers appear interleaved; that's fine.

- [ ] **Step 3: Bump version**

Use Edit to change these three strings:

- `src/gh_manage/__init__.py`: `__version__ = "1.7.0"` → `"1.8.0"`
- `pyproject.toml`: `version = "1.7.0"` → `"1.8.0"`
- `tests/test_sanity.py`: `== "1.7.0"` → `== "1.8.0"`

- [ ] **Step 4: Regenerate lockfile**

```bash
uv sync
```

- [ ] **Step 5: Full verify**

```bash
uv run pytest -q 2>&1 | tail -3
uvx ruff@0.8.0 check src/ tests/
uv run mypy src/
```

Expected: 587 passed (baseline + 15 new logging tests), clean.

- [ ] **Step 6: Commit**

```bash
git add src/gh_manage/__init__.py pyproject.toml tests/test_sanity.py uv.lock
git commit -m "$(cat <<'EOF'
chore(release): bump to cli/v1.8.0

Adds structured logging to drift_sync/ + commands/drift.py with a
hybrid plain/JSON format, a root Click --log-level option, and two
fixes from #62 (HIGH #3 malformed-timestamp WARNING, HIGH #5
unexpected-exception traceback).

Additive: no public API removed, no existing output changed.

Refs #47 (Theme A item 6), closes part of #62.
EOF
)"
```

---

## Task 10: File 3 follow-up Issues

**Files:** none (GitHub API only).

- [ ] **Step 1: File follow-up Issue A — roll out logging to other commands**

```bash
gh issue create --title "Roll out structured logging to remaining gh-manage commands (apply/labels/protection/init/doctor)" --body "$(cat <<'EOF'
Follow-up to cli/v1.8.0 (PR #NN — drift_sync logging). The logging infrastructure (`gh_manage.logging_config`, `--log-level` root option, `GH_MANAGE_LOG_JSON` env var) is in place; this issue tracks applying the same pattern to the remaining commands.

## Scope

Each command gets:
- `log = logging.getLogger(__name__)` at module top
- INFO around the entry/exit points (subcommand invoked, completed)
- WARNING on guarded-but-unexpected branches (e.g., 404 fallbacks, skip-on-error)
- ERROR / `log.exception` on catch-all branches
- Caplog-based regression tests for each new log point

## Commands

- `gh_manage.commands.apply`
- `gh_manage.commands.labels`
- `gh_manage.commands.protection`
- `gh_manage.commands.init`
- `gh_manage.commands.doctor`
- `gh_manage.commands.issues`

## Out of scope

- Logging in `github_client.py` / API wrappers — that layer should stay silent (HTTP noise would dominate) unless specifically useful.
- New log levels or formats — reuse the cli/v1.8.0 infrastructure as-is.

## Priority

Low. cli/v1.8.0 already gives operators + agents what they need for the most fragile (drift) path. This is hygiene.
EOF
)"
```

- [ ] **Step 2: File follow-up Issue B — scan_id correlation**

```bash
gh issue create --title "Add scan_id correlation (UUID4) to drift_sync logs" --body "$(cat <<'EOF'
Follow-up to cli/v1.8.0. When `drift --all` runs in parallel, records from different scans interleave on stderr. A per-scan UUID4 threaded via `LoggerAdapter` or `ContextVar` would let JSON consumers filter with `jq 'select(.scan_id == \"...\")'`.

## Proposal

- Generate UUID4 at the top of `_scan_single_repo` (one per repo).
- Use `logging.LoggerAdapter` to inject `{"scan_id": "..."}` into every record's `extra` for the duration of the scan.
- JSON formatter already propagates `extra` fields, so no config change.
- Update caplog tests to assert `scan_id` is present on relevant records.

## Out of scope

- Correlation across other CLI commands (use Issue A's logging rollout once it lands).
- Request IDs threaded through `github_api.*` — adds surface with no current consumer.

## Priority

Medium when fleet debugging becomes noisy. Currently 22 repos is tractable without IDs.
EOF
)"
```

- [ ] **Step 3: File follow-up Issue C — `--log-file` flag**

```bash
gh issue create --title "Add --log-file destination flag to gh-manage CLI" --body "$(cat <<'EOF'
Follow-up to cli/v1.8.0. Currently logs go to stderr only. For long cron runs (daily `drift --all`), capturing to a file on disk would avoid losing records if the process is interrupted.

## Proposal

- Add `--log-file PATH` to the root click group, envvar `GH_MANAGE_LOG_FILE`.
- When set, `configure_logging` attaches a `FileHandler` (in addition to the stderr handler, or as a replacement — decide during spec).
- No rotation; users can handle that externally with logrotate / GitHub Actions artifacts.

## Out of scope

- Log rotation, size limits, retention policies — leave to external tools.
- Dual output (stderr + file simultaneously) — maybe; decide during spec.

## Priority

Low. Stderr + GitHub Actions artifact capture currently covers the cron use case. File this as a capability gap, not a blocker.
EOF
)"
```

- [ ] **Step 4: Record the issue numbers for the PR body**

Note down the 3 issue numbers emitted by the `gh issue create` commands. They'll be referenced in Task 11's PR body and release notes.

---

## Task 11: PR + 4-reviewer + merge + tag + release

**Files:** none (orchestration).

- [ ] **Step 1: Push**

```bash
git push -u origin feat/drift-sync-logging
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --title "feat: drift_sync structured logging (cli/v1.8.0)" --body "$(cat <<'EOF'
## Summary

- Introduces `gh_manage.logging_config` + root `--log-level` option with hybrid plain/JSON format (`GH_MANAGE_LOG_JSON=1` switches to JSON).
- 8 concrete log points across `drift_sync/registry.py`, `drift_sync/checks.py`, `drift_sync/issue_state.py`, `commands/drift.py`.
- Resolves [#62](https://github.com/yakkuro/gh-manage/issues/62) HIGH #3 (malformed-timestamp WARNING) and HIGH #5 (unexpected-exception traceback).
- Closes Theme A item 6 of [#47](https://github.com/yakkuro/gh-manage/issues/47).

## One intentional behavior change

`check_protection` currently swallows `GhNotFoundError` silently; it now emits a WARNING before the swallow. Returned findings + exit codes unchanged. Called out in spec §4 and §7 risks table.

## New dep

`python-json-logger>=2.0,<3.0` — single-module stdlib-compatible Formatter subclass.

## Test plan

- [x] `uv run pytest -q` — 587 passed (572 baseline + 15 new across 2 new files)
- [x] `uvx ruff@0.8.0 check src/ tests/` — clean
- [x] `uv run mypy src/` — clean
- [x] Manual: default level produces no log output on clean repo (WARNING floor)
- [x] Manual: `--log-level debug` shows check entry/exit DEBUGs
- [x] Manual: `GH_MANAGE_LOG_JSON=1` produces valid JSON lines
- [x] Manual: crafted malformed-timestamp comment triggers the new WARNING
- [x] Manual: forced `TypeError` in `_scan_single_repo` reproduces `log.exception` with traceback
- [x] `drift --all`: 22 repos scanned, 0 FAILED

Spec: [`docs/specs/2026-04-19-drift-sync-logging-design.md`](docs/specs/2026-04-19-drift-sync-logging-design.md)
Plan: [`docs/plans/2026-04-19-drift-sync-logging-plan.md`](docs/plans/2026-04-19-drift-sync-logging-plan.md)

Follow-ups (Issues filed alongside this PR):
- #{A}: Roll out logging to remaining commands
- #{B}: Add scan_id correlation
- #{C}: Add `--log-file` flag

Refs #47, closes part of #62 (HIGH #3, HIGH #5).

Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

Replace `#{A}`, `#{B}`, `#{C}` with the actual numbers from Task 10.

- [ ] **Step 3: Wait for CI**

```bash
PR_NUM=$(gh pr view --json number -q .number)
gh pr checks "$PR_NUM" --watch
```

- [ ] **Step 4: Dispatch 4-reviewer protocol in parallel**

Per `workflow-review.md`, in ONE message with 4 tool calls:

1. `bash /home/server160/repos/claude-dotfiles/scripts/codex-review-resilient.sh "..."` (background)
2. `Agent(subagent_type="superpowers:code-reviewer")` — pass plan + spec paths
3. `Agent(subagent_type="pr-review-toolkit:silent-failure-hunter")` — focus on catch-all + new log points not hiding new failures
4. `Agent(subagent_type="code-reviewer", model="sonnet")` — diff size is moderate (~600 net LOC), sonnet fits

- [ ] **Step 5: Triage**

- CRITICAL/HIGH: fix and push, re-review.
- MEDIUM: fix if cheap, document rationale otherwise.
- LOW/nit: optional.

- [ ] **Step 6: Merge + tag + release**

```bash
gh pr merge "$PR_NUM" --squash --delete-branch
git checkout main && git pull
git tag -a cli/v1.8.0 -m "cli/v1.8.0 — drift_sync structured logging"
git push origin cli/v1.8.0
gh release create cli/v1.8.0 --title "cli/v1.8.0 — drift_sync structured logging" --notes "$(cat <<'EOF'
See [PR #NN](https://github.com/yakkuro/gh-manage/pull/NN) for full details.

## Highlights

- **New**: `--log-level {debug,info,warning,error}` root option (envvar `GH_MANAGE_LOG_LEVEL`, default `warning`).
- **New**: `GH_MANAGE_LOG_JSON=1` switches log output to JSON lines (python-json-logger under the hood).
- **New**: 8 log points in `drift_sync/` + `commands/drift.py` for scan lifecycle, malformed-timestamp warnings, and unexpected-exception tracebacks.
- **Resolved**: [#62](https://github.com/yakkuro/gh-manage/issues/62) HIGH #3 (malformed timestamps no longer silently dropped) and HIGH #5 (parallel worker unexpected exceptions now leave full tracebacks in logs).
- **Closes** Theme A item 6 from [#47](https://github.com/yakkuro/gh-manage/issues/47).

## One intentional behavior change

`check_protection` now emits a WARNING before its pre-existing `GhNotFoundError` → empty-protection fallback. Findings tuples and exit codes are unchanged; only log output differs.

## Dependency change

Adds `python-json-logger>=2.0,<3.0`.

## Two-track versioning reminder

`cli/v1.8.0` is a **CLI-track** tag. Reusable workflows stay on `v1.1.0`.

## Follow-ups tracked

- #{A}: Roll out logging to remaining commands
- #{B}: Add scan_id correlation
- #{C}: Add `--log-file` flag
EOF
)"
```

Replace `NN`, `#{A}/B/C` with actual numbers.

- [ ] **Step 7: Comment on #47**

```bash
gh issue comment 47 --body "$(cat <<'EOF'
**Theme A item 6 shipped**: [cli/v1.8.0](https://github.com/yakkuro/gh-manage/releases/tag/cli/v1.8.0) ([PR #NN](https://github.com/yakkuro/gh-manage/pull/NN)).

Structured logging in place for `drift_sync/` + `commands/drift.py` with hybrid plain/JSON format. Two #62 HIGH items resolved inline (malformed-timestamp WARNING; unexpected-exception traceback via `log.exception`).

Follow-up rollouts tracked separately: #{A} (other commands), #{B} (scan_id correlation), #{C} (--log-file flag).

Theme A remaining items after this: item 5 (protection_sync split, parallel to item 4's drift_sync split).
EOF
)"
```

- [ ] **Step 8: Comment on #62**

```bash
gh issue comment 62 --body "$(cat <<'EOF'
**HIGH #3 (malformed timestamp logging) and HIGH #5 (worker exception traceback) resolved** in cli/v1.8.0 ([PR #NN](https://github.com/yakkuro/gh-manage/pull/NN)).

Remaining items in this issue: CRITICAL #1 (_CHECKS runtime assert), CRITICAL #2 (non-transactional issue sequence), HIGH #4 (_read_template_content error messages), MEDIUM #6 (fragile `next()`), MEDIUM #7 (formatter single-repo invariant), LOW #8/#9 (docstring + type polish).
EOF
)"
```

---

## Rollback notes

- Each of tasks 1-9 is a single commit. If a regression surfaces, revert from the most suspect commit and work backward; every intermediate commit is green individually.
- `python-json-logger` is the only new dep. `uv sync` after a dependency revert regenerates `uv.lock`.
- The intentional `check_protection` WARNING is easy to isolate: remove the `log.warning(...)` call and the `current = {}` assignment is untouched — no functional regression.
