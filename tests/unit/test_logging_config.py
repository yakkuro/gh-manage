"""Tests for gh_manage.logging_config.

All tests clean up the `gh_manage` logger's handler state after each run
so tests don't interfere with each other or with pytest's own logger.
"""

from __future__ import annotations

import io
import logging

import pytest


@pytest.fixture(autouse=True)
def _reset_gh_manage_logger():
    """Save/restore the gh_manage logger state around each test."""
    gh_logger = logging.getLogger("gh_manage")
    saved_handlers = list(gh_logger.handlers)
    saved_level = gh_logger.level
    saved_propagate = gh_logger.propagate
    yield
    gh_logger.handlers[:] = saved_handlers
    gh_logger.setLevel(saved_level)
    gh_logger.propagate = saved_propagate


def test_configure_logging_default_level_is_warning() -> None:
    from gh_manage.logging_config import configure_logging

    configure_logging()
    assert logging.getLogger("gh_manage").level == logging.WARNING


def test_configure_logging_sets_explicit_level() -> None:
    from gh_manage.logging_config import configure_logging

    configure_logging(level="info")
    assert logging.getLogger("gh_manage").level == logging.INFO


def test_configure_logging_plain_formatter_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    """Env says yes; explicit arg says no. Explicit wins."""
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
    assert (
        root_handlers_before == root_handlers_after
    ), "configure_logging must not touch the root logger — only the `gh_manage` tree."


def test_configure_logging_sets_propagate_false() -> None:
    """configure_logging must set gh_manage.propagate = False to prevent
    duplicate output when a caller also configures a root handler.

    This is a separate assertion from the root-handler test above because
    a logger can have no root handler yet still propagate records up
    through the logging tree — testing both is necessary to fully lock
    down the isolation contract (addresses Codex review LOW).
    """
    from gh_manage.logging_config import configure_logging

    configure_logging()
    assert logging.getLogger("gh_manage").propagate is False
