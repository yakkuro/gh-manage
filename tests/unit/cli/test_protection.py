"""Tests for `gh manage protection` click commands."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from pytest_mock import MockerFixture

from gh_manage.cli import main
from gh_manage.protection_sync import (
    DowngradeFinding,
    ProtectionDiff,
    ProtectionFieldChange,
)


def _empty_diff() -> ProtectionDiff:
    return ProtectionDiff(changes=(), downgrades=(), current_raw={}, desired_raw={})


def _simple_diff() -> ProtectionDiff:
    return ProtectionDiff(
        changes=(ProtectionFieldChange("enforce_admins", False, True),),
        downgrades=(),
        current_raw={"enforce_admins": {"enabled": False}},
        desired_raw={"enforce_admins": True, "restrictions": None},
    )


def _downgrade_diff() -> ProtectionDiff:
    return ProtectionDiff(
        changes=(ProtectionFieldChange("enforce_admins", True, False),),
        downgrades=(DowngradeFinding("enforce_admins", True, False, "admin weakened"),),
        current_raw={"enforce_admins": {"enabled": True}},
        desired_raw={"enforce_admins": False, "restrictions": None},
    )


def _patch_git(mocker: MockerFixture) -> None:
    mocker.patch(
        "gh_manage.commands.protection.git_cli.get_origin_owner_repo",
        return_value="yakkuro/gh-manage",
    )


def _patch_get_protection(mocker: MockerFixture, response: dict | None = None) -> None:
    mocker.patch(
        "gh_manage.commands.protection.protection_api.get_branch_protection",
        return_value=response or {},
    )


# protection sync — happy paths
def test_sync_dry_run_default(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker)
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_simple_diff(),
    )
    mock_apply = mocker.patch(
        "gh_manage.commands.protection.protection_sync.apply_protection_diff"
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["protection", "sync", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Dry-run" in result.output
    mock_apply.assert_not_called()


def test_sync_apply_calls_apply_protection_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker)
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_simple_diff(),
    )
    mock_apply = mocker.patch(
        "gh_manage.commands.protection.protection_sync.apply_protection_diff"
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "sync",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    mock_apply.assert_called_once()


def test_sync_empty_diff_reports_no_changes(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker)
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_empty_diff(),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["protection", "sync", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "No changes" in result.output


def test_sync_apply_and_dry_run_conflict(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "sync",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
            "--dry-run",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 2  # UsageError


# Downgrade guardrails
def test_sync_downgrade_without_flag_stops(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker, {"enforce_admins": {"enabled": True}})
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_downgrade_diff(),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "sync",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "downgrade" in result.output.lower()
    assert "--downgrade-allowed" in result.output


def test_sync_downgrade_with_flag_and_yes_proceeds(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker, {"enforce_admins": {"enabled": True}})
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_downgrade_diff(),
    )
    mock_apply = mocker.patch(
        "gh_manage.commands.protection.protection_sync.apply_protection_diff"
    )
    # Simulate non-TTY stdin
    mocker.patch(
        "gh_manage.commands.protection._is_tty_stdin",
        return_value=False,
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "sync",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
            "--downgrade-allowed",
            "--yes",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    mock_apply.assert_called_once()


def test_sync_downgrade_non_tty_without_yes_stops(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker, {"enforce_admins": {"enabled": True}})
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_downgrade_diff(),
    )
    mocker.patch(
        "gh_manage.commands.protection._is_tty_stdin",
        return_value=False,
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "sync",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
            "--downgrade-allowed",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert (
        "non-tty" in result.output.lower() or "non-interactive" in result.output.lower()
    )


# Profile validation errors
def test_sync_profile_without_protection_policy_stops(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    from gh_manage.models.profiles import ProfileSpec
    from gh_manage.models.branch_protection import BranchProtectionConfig

    # Mock resolve_profile_path to return a dummy path
    profile_path = tmp_path / "dummy.yml"
    mocker.patch(
        "gh_manage.commands.protection.resolve_profile_path",
        return_value=profile_path,
    )

    # Create real mocks for both the profile and branch-protection config
    profile_without_policy = ProfileSpec(
        version=1, name="test", files=[], protection_policy=None
    )
    bp_config = mocker.MagicMock(spec=BranchProtectionConfig)

    # Mock load_config to return appropriate objects based on the path
    def _fake_load_config(path, model_cls):
        if path == profile_path:
            return profile_without_policy
        else:
            return bp_config

    mocker.patch(
        "gh_manage.commands.protection.load_config",
        side_effect=_fake_load_config,
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["protection", "sync", str(tmp_path), "--profile", "test"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "protection_policy" in result.output


# diff subcommand
def test_diff_empty_exit_0(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker)
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_empty_diff(),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["protection", "diff", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "No changes" in result.output


def test_diff_downgrade_without_flag_exit_1(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker, {"enforce_admins": {"enabled": True}})
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_downgrade_diff(),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "diff",
            str(tmp_path),
            "--profile",
            "python-service",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1


def test_diff_downgrade_with_flag_exit_0(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker, {"enforce_admins": {"enabled": True}})
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_downgrade_diff(),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "diff",
            str(tmp_path),
            "--profile",
            "python-service",
            "--downgrade-allowed",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
