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

    - level: log level for the `gh_manage` logger tree. Third-party
      packages' loggers are untouched.
    - json: tri-state. Precedence: explicit `json=True/False` wins
      over env var. If `json is None` (default), read
      `GH_MANAGE_LOG_JSON` env var; truthy values ("1", "true", "yes",
      case-insensitive) → JSON, everything else → plain.
    - stream: destination for log output. Defaults to sys.stderr.
      Production callers (cli.py) should omit this argument. Unit
      tests pass a StringIO to capture output without touching real
      stderr.

    Side effect: clears existing handlers on the `gh_manage` logger and
    replaces them with a single StreamHandler bound to `stream`.
    Callers should invoke this exactly once, at CLI entry.

    Immutability: the plain and JSON formatter strings (including
    datefmt) are fixed by this module — not runtime-configurable.
    Changing them requires editing logging_config.py, so caplog-based
    tests can rely on the record shape.
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
    # Don't propagate to root — otherwise a user who configures a root
    # handler for third-party logs would see our records duplicated.
    gh_logger.propagate = False
