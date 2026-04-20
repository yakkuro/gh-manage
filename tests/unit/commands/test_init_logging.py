"""Regression tests for commands/init.py log points.

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
def mock_init_deps(monkeypatch):
    fake_profile = MagicMock()
    fake_profile.name = "python-service"
    fake_profile.protection_policy = None

    def _load(path, cls):
        if cls.__name__ == "ProfileSpec":
            return fake_profile
        return MagicMock()

    monkeypatch.setattr("gh_manage.commands.init.load_config", _load)
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
    monkeypatch.setattr("gh_manage.github_api.labels.list_labels", lambda repo: ())
    monkeypatch.setattr(
        "gh_manage.labels_sync.compute_diff",
        lambda *a, **kw: MagicMock(
            is_empty=True,
            total_changes=0,
            creates=[],
            updates=[],
            renames=[],
        ),
    )
    monkeypatch.setattr(
        "gh_manage.profile_sync.compute_files_diff",
        lambda *a, **kw: MagicMock(
            creates=[],
            overwrites=[],
            skipped=[],
            noops=[],
            is_empty=True,
        ),
    )


def test_init_logs_invocation(mock_init_deps, tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--log-level", "info", "init", str(tmp_path), "--profile", "python-service"],
    )
    assert "init invoked" in result.output
    assert "owner/repo" in result.output


def test_init_logs_completion(mock_init_deps, tmp_path, monkeypatch):
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
    result = runner.invoke(
        main,
        [
            "--log-level",
            "info",
            "init",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
        ],
    )
    assert "init complete" in result.output


def test_init_logs_warning_on_ghnotfound(tmp_path, monkeypatch):
    fake_profile = MagicMock()
    fake_profile.name = "python-service"
    fake_profile.protection_policy = "standard"
    fake_bp = MagicMock(policies={"standard": MagicMock()})

    def _load(path, cls):
        if cls.__name__ == "ProfileSpec":
            return fake_profile
        if cls.__name__ == "BranchProtectionConfig":
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
    monkeypatch.setattr("gh_manage.github_api.labels.list_labels", lambda repo: ())
    monkeypatch.setattr(
        "gh_manage.labels_sync.compute_diff",
        lambda *a, **kw: MagicMock(
            is_empty=True,
            total_changes=0,
            creates=[],
            updates=[],
            renames=[],
        ),
    )
    monkeypatch.setattr(
        "gh_manage.profile_sync.compute_files_diff",
        lambda *a, **kw: MagicMock(
            creates=[],
            overwrites=[],
            skipped=[],
            noops=[],
            is_empty=True,
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
            is_empty=True,
            has_downgrades=False,
            changes=(),
        ),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
    )
    assert "branch protection not configured" in result.output
