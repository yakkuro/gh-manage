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
from pathlib import Path
from typing import IO, Literal

from pythonjsonlogger.jsonlogger import JsonFormatter as _BaseJsonFormatter

from gh_manage.drift_sync.context import scan_id_var


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


def _env_says_json() -> bool:
    raw = os.environ.get("GH_MANAGE_LOG_JSON", "").strip().lower()
    return raw in _TRUTHY


def configure_logging(
    level: LogLevel = "warning",
    json: bool | None = None,
    stream: IO[str] | None = None,
    log_file: Path | None = None,
) -> None:
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
    if json is None:
        json = _env_says_json()

    if stream is None:
        stream = sys.stderr

    formatter: logging.Formatter
    if json:
        formatter = _ScanIdJsonFormatter(_JSON_FORMAT, datefmt=_JSON_DATEFMT)
    else:
        formatter = logging.Formatter(_PLAIN_FORMAT, datefmt=_PLAIN_DATEFMT)

    handlers: list[logging.Handler] = [logging.StreamHandler(stream=stream)]
    if log_file is not None:
        handlers.append(logging.FileHandler(str(log_file), mode="a", encoding="utf-8"))
    for h in handlers:
        h.setFormatter(formatter)

    gh_logger = logging.getLogger("gh_manage")
    gh_logger.handlers[:] = handlers
    gh_logger.setLevel(_LOG_LEVELS[level])
    gh_logger.propagate = False
