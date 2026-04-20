"""Regression tests for commands/labels.py log points + decorator consolidation.

Tests assert on result.output (CliRunner captures stderr) rather than
caplog, since gh_manage logger has propagate=False.
"""

from __future__ import annotations

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
    monkeypatch.setattr("gh_manage.github_api.labels.list_labels", lambda repo: ())
    monkeypatch.setattr(
        "gh_manage.commands.labels.load_config",
        lambda path, cls: MagicMock(labels=[]),
    )
    monkeypatch.setattr(
        "gh_manage.labels_sync.compute_diff",
        lambda *a, **kw: MagicMock(
            is_empty=True,
            total_changes=0,
            creates=[],
            updates=[],
            renames=[],
            deletes=[],
        ),
    )


def test_labels_sync_logs_invocation(mock_labels_deps):
    runner = CliRunner()
    result = runner.invoke(
        main, ["--log-level", "info", "labels", "sync", "owner/repo"]
    )
    assert "labels sync invoked" in result.output
    assert "owner/repo" in result.output


def test_labels_show_logs_invocation(mock_labels_deps):
    runner = CliRunner()
    result = runner.invoke(
        main, ["--log-level", "info", "labels", "show", "owner/repo"]
    )
    assert "labels show invoked" in result.output
    assert "owner/repo" in result.output


def test_labels_diff_logs_invocation(mock_labels_deps):
    runner = CliRunner()
    result = runner.invoke(
        main, ["--log-level", "info", "labels", "diff", "owner/repo"]
    )
    assert "labels diff invoked" in result.output
    assert "owner/repo" in result.output


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
