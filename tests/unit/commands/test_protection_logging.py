"""Regression tests for commands/protection.py log points.

Tests assert on result.output (CliRunner stderr capture) since
gh_manage logger has propagate=False.
"""

from __future__ import annotations

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
        # Dispatch on cls, not path substring.
        if cls.__name__ == "ProfileSpec":
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
            is_empty=True,
            changes=(),
            has_downgrades=False,
            downgrades=[],
        ),
    )
    monkeypatch.setattr(
        "gh_manage.github_api.protection.get_branch_protection",
        lambda *a, **kw: {},
    )


def test_protection_sync_logs_invocation(mock_protection_deps, tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--log-level",
            "info",
            "protection",
            "sync",
            str(tmp_path),
            "--profile",
            "python-service",
        ],
    )
    assert "protection sync invoked" in result.output
    assert "owner/repo" in result.output


def test_protection_diff_logs_invocation(mock_protection_deps, tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--log-level",
            "info",
            "protection",
            "diff",
            str(tmp_path),
            "--profile",
            "python-service",
        ],
    )
    assert "protection diff invoked" in result.output
    assert "owner/repo" in result.output


def test_protection_logs_warning_on_ghnotfound(
    mock_protection_deps, tmp_path, monkeypatch
):
    def _raise(*a, **kw):
        raise GhNotFoundError("404")

    monkeypatch.setattr("gh_manage.github_api.protection.get_branch_protection", _raise)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "sync",
            str(tmp_path),
            "--profile",
            "python-service",
        ],
    )
    assert "branch protection not configured" in result.output
    assert "owner/repo" in result.output
