"""Tests for gh_manage.logging_config.

All tests clean up the `gh_manage` logger's handler state after each run
so tests don't interfere with each other or with pytest's own logger.
"""

from __future__ import annotations

import io
import json
import logging

import pytest

from gh_manage.drift_sync.context import scan_id_var
from gh_manage.logging_config import configure_logging


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

    configure_logging()
    assert logging.getLogger("gh_manage").level == logging.WARNING


def test_configure_logging_sets_explicit_level() -> None:

    configure_logging(level="info")
    assert logging.getLogger("gh_manage").level == logging.INFO


def test_configure_logging_plain_formatter_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GH_MANAGE_LOG_JSON", raising=False)

    configure_logging()
    handler = logging.getLogger("gh_manage").handlers[0]
    # Plain-text formatter is the stdlib class, not JsonFormatter.
    assert type(handler.formatter).__name__ == "Formatter"


def test_configure_logging_json_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_MANAGE_LOG_JSON", "1")
    from pythonjsonlogger.jsonlogger import JsonFormatter

    configure_logging()
    handler = logging.getLogger("gh_manage").handlers[0]
    assert isinstance(handler.formatter, JsonFormatter)


def test_configure_logging_json_explicit_arg_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env says yes; explicit arg says no. Explicit wins."""
    monkeypatch.setenv("GH_MANAGE_LOG_JSON", "1")

    configure_logging(json=False)
    handler = logging.getLogger("gh_manage").handlers[0]
    assert type(handler.formatter).__name__ == "Formatter"


def test_configure_logging_idempotent() -> None:

    configure_logging(level="info")
    configure_logging(level="debug")
    gh_logger = logging.getLogger("gh_manage")
    assert len(gh_logger.handlers) == 1
    assert gh_logger.level == logging.DEBUG


def test_configure_logging_writes_to_stream_argument() -> None:
    """Stream override is how unit tests isolate from real stderr."""

    buf = io.StringIO()
    configure_logging(level="info", stream=buf)
    logging.getLogger("gh_manage.test").info("sentinel-msg-xyz")
    assert "sentinel-msg-xyz" in buf.getvalue()


def test_configure_logging_does_not_add_handler_to_root_logger() -> None:

    root_handlers_before = list(logging.getLogger().handlers)
    configure_logging()
    root_handlers_after = list(logging.getLogger().handlers)
    assert root_handlers_before == root_handlers_after, (
        "configure_logging must not touch the root logger — only the `gh_manage` tree."
    )


def test_configure_logging_sets_propagate_false() -> None:
    """configure_logging must set gh_manage.propagate = False to prevent
    duplicate output when a caller also configures a root handler.

    This is a separate assertion from the root-handler test above because
    a logger can have no root handler yet still propagate records up
    through the logging tree — testing both is necessary to fully lock
    down the isolation contract (addresses Codex review LOW).
    """

    configure_logging()
    assert logging.getLogger("gh_manage").propagate is False


# ---- scan_id injection tests (cli/v1.9.0) ----


def _parse_first_json(stream: io.StringIO) -> dict:
    text = stream.getvalue().strip()
    assert text, "expected at least one log line"
    return json.loads(text.splitlines()[0])


def test_json_formatter_includes_scan_id_when_set():
    stream = io.StringIO()
    configure_logging(level="info", json=True, stream=stream)
    token = scan_id_var.set("test-uuid-123")
    try:
        logging.getLogger("gh_manage.test").info("hello")
    finally:
        scan_id_var.reset(token)
    assert _parse_first_json(stream)["scan_id"] == "test-uuid-123"


def test_json_formatter_omits_scan_id_when_unset():
    stream = io.StringIO()
    configure_logging(level="info", json=True, stream=stream)
    logging.getLogger("gh_manage.test").info("hello")
    assert "scan_id" not in _parse_first_json(stream)


def test_plain_formatter_omits_scan_id():
    stream = io.StringIO()
    configure_logging(level="info", json=False, stream=stream)
    token = scan_id_var.set("would-be-visible-if-not-omitted")
    try:
        logging.getLogger("gh_manage.test").info("hello")
    finally:
        scan_id_var.reset(token)
    assert "would-be-visible" not in stream.getvalue()


# ---- log_file + dual handler tests (cli/v1.9.0) ----


def test_configure_logging_with_log_file_adds_file_handler(tmp_path):
    log_path = tmp_path / "x.log"
    configure_logging(level="info", log_file=log_path)
    handlers = logging.getLogger("gh_manage").handlers
    assert len(handlers) == 2
    types = {type(h).__name__ for h in handlers}
    assert types == {"StreamHandler", "FileHandler"}


def test_log_file_mode_is_append(tmp_path):
    log_path = tmp_path / "x.log"
    log_path.write_text("pre-existing\n", encoding="utf-8")
    configure_logging(level="info", log_file=log_path)
    logging.getLogger("gh_manage.test").info("new-entry")
    for h in logging.getLogger("gh_manage").handlers:
        h.flush()
    content = log_path.read_text(encoding="utf-8")
    assert content.startswith("pre-existing\n")
    assert "new-entry" in content


def test_log_file_encoding_is_utf8(tmp_path):
    log_path = tmp_path / "x.log"
    configure_logging(level="info", log_file=log_path)
    logging.getLogger("gh_manage.test").info("日本語テスト")
    for h in logging.getLogger("gh_manage").handlers:
        h.flush()
    content = log_path.read_bytes().decode("utf-8")
    assert "日本語テスト" in content


def test_log_file_and_stderr_get_same_record(tmp_path):
    log_path = tmp_path / "x.log"
    stream = io.StringIO()
    configure_logging(level="info", log_file=log_path, stream=stream)
    logging.getLogger("gh_manage.test").info("dual-msg")
    for h in logging.getLogger("gh_manage").handlers:
        h.flush()
    assert "dual-msg" in stream.getvalue()
    assert "dual-msg" in log_path.read_text(encoding="utf-8")


def test_file_handler_inherits_scan_id_formatter(tmp_path):
    log_path = tmp_path / "x.log"
    configure_logging(level="info", json=True, log_file=log_path)
    token = scan_id_var.set("file-scan-id")
    try:
        logging.getLogger("gh_manage.test").info("msg")
    finally:
        scan_id_var.reset(token)
    for h in logging.getLogger("gh_manage").handlers:
        h.flush()
    first_line = log_path.read_text(encoding="utf-8").splitlines()[0]
    assert json.loads(first_line)["scan_id"] == "file-scan-id"
