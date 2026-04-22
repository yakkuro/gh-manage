"""Regression tests for commands/apply.py log points.

Scope: log emission only. Command behavior is covered by existing tests.

Note: `gh_manage` logger has `propagate=False` (set by configure_logging),
so pytest's caplog — which attaches at root — cannot see records. These
tests check `result.output` instead, which CliRunner captures from stderr
(where configure_logging's StreamHandler writes).
"""

from __future__ import annotations

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
        creates=[],
        overwrites=[],
        skipped=[],
        noops=[],
        is_empty=True,
    )
    monkeypatch.setattr(
        "gh_manage.profile_sync.compute_files_diff",
        lambda *a, **kw: fake_diff,
    )


def test_apply_logs_invocation_at_info(mock_apply_deps, tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--log-level",
            "info",
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
        ],
    )
    assert "apply invoked" in result.output
    assert "owner/repo" in result.output


def test_apply_logs_completion_at_info(mock_apply_deps, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "gh_manage.profile_sync.apply_files_diff",
        lambda *a, **kw: [],
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
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
        ],
    )
    assert "apply complete" in result.output


def test_apply_logs_warning_on_ghnotfound_protection_fallback(tmp_path, monkeypatch):
    from gh_manage.github_client import GhNotFoundError

    monkeypatch.setattr(
        "gh_manage.git_cli.get_origin_owner_repo", lambda p: "owner/repo"
    )
    fake_profile = MagicMock()
    fake_profile.name = "python-service"
    fake_profile.protection_policy = "standard"
    fake_bp = MagicMock(policies={"standard": MagicMock()})

    def _load(path, cls):
        # Dispatch on the config class, not path string — paths don't
        # contain "profile" so substring matching is unreliable.
        if cls.__name__ == "ProfileSpec":
            return fake_profile
        if cls.__name__ == "BranchProtectionConfig":
            return fake_bp
        return MagicMock()  # LabelsConfig fallback

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
            changes=(),
            has_downgrades=False,
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--also-protection",
        ],
    )
    assert "branch protection not configured" in result.output
    assert "owner/repo" in result.output


def test_apply_logs_warning_on_doctor_check_error(
    mock_apply_deps, tmp_path, monkeypatch
):
    from gh_manage.doctor.errors import DoctorCheckError

    monkeypatch.setattr(
        "gh_manage.profile_sync.apply_files_diff",
        lambda *a, **kw: [],
    )

    def _raise_doctor_check(*a, **kw):
        raise DoctorCheckError("bad ci.yml")

    # Pre-apply doctor should pass (return empty); post-apply should raise.
    # Since both call doctor.run_on_path, we patch at the helper level:
    # pre-apply uses _shared.doctor, post-apply uses _doctor alias.
    call_count = [0]

    def _doctor_run_on_path(*a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            # Pre-apply call: return empty
            return ()
        else:
            # Post-apply call: raise
            raise DoctorCheckError("bad ci.yml")

    monkeypatch.setattr("gh_manage.doctor.run_on_path", _doctor_run_on_path)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
        ],
    )
    assert "post-apply doctor check failed" in result.output
    assert "bad ci.yml" in result.output
