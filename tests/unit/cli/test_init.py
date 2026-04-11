"""Tests for `gh manage init` click command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
import pytest
from pytest_mock import MockerFixture

from gh_manage.cli import main
from gh_manage.git_cli import (
    NoOriginRemoteError,
    NotAGitRepoError,
    UnsupportedOriginError,
)
from gh_manage.github_client import GhAuthError
from gh_manage.labels_sync import LabelsDiff


def _empty_labels_diff() -> LabelsDiff:
    return LabelsDiff(renames=(), creates=(), updates=(), deletes=())


def _patch_git(mocker: MockerFixture, owner_repo: str = "yakkuro/gh-manage") -> None:
    mocker.patch(
        "gh_manage.commands.init.git_cli.get_origin_owner_repo",
        return_value=owner_repo,
    )


def _patch_labels(mocker: MockerFixture) -> None:
    mocker.patch("gh_manage.github_api.labels.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.init.labels_sync.compute_diff",
        return_value=_empty_labels_diff(),
    )


# Happy path
def test_init_dry_run_default(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    mock_apply = mocker.patch("gh_manage.commands.init.profile_sync.apply_files_diff")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Dry-run" in result.output
    mock_apply.assert_not_called()


def test_init_apply_writes_files_and_calls_labels_apply(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    mock_files_apply = mocker.patch(
        "gh_manage.commands.init.profile_sync.apply_files_diff"
    )
    mock_labels_apply = mocker.patch("gh_manage.commands.init.labels_sync.apply_diff")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service", "--apply"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Done" in result.output or "Next steps" in result.output
    mock_files_apply.assert_called_once()
    mock_labels_apply.assert_called_once()


def test_init_apply_and_dry_run_conflict(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "init",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
            "--dry-run",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 2  # UsageError


# Precheck error paths
def test_init_not_a_git_repo(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch(
        "gh_manage.commands.init.git_cli.get_origin_owner_repo",
        side_effect=NotAGitRepoError("Not a git repository. Run `git init` first."),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "git init" in result.output


def test_init_no_origin_remote(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch(
        "gh_manage.commands.init.git_cli.get_origin_owner_repo",
        side_effect=NoOriginRemoteError(
            "No `origin` remote configured. Run `git remote add origin ...`."
        ),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "git remote add origin" in result.output


def test_init_gitlab_origin_url(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch(
        "gh_manage.commands.init.git_cli.get_origin_owner_repo",
        side_effect=UnsupportedOriginError(
            "Unsupported git remote URL: 'git@gitlab.com:foo/bar.git'. "
            "gh-manage only supports github.com origins."
        ),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "github.com" in result.output


def test_init_gh_auth_error_actionable_message(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """init always touches labels (Q1 = B), so gh auth must be set up
    even for dry-run. Auth failure produces actionable message."""
    _patch_git(mocker)
    mocker.patch(
        "gh_manage.github_api.labels.list_labels",
        side_effect=GhAuthError("Run `gh auth login` and try again."),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "gh auth login" in result.output


def test_init_unknown_profile(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "nonexistent-profile-xyz"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert (
        "nonexistent-profile-xyz" in result.output
        or "not found" in result.output.lower()
    )


# Profile-name security validation (Codex review #1)
@pytest.mark.parametrize(
    "bad_name",
    [
        "../../etc/passwd",
        "..",
        "../python-service",
        "subdir/python-service",
        "subdir\\python-service",
        ".hidden",
        "",
    ],
)
def test_init_profile_name_path_traversal_rejected(
    mocker: MockerFixture, tmp_path: Path, bad_name: str
) -> None:
    """A `--profile` value containing `/`, `..`, or starting with `.` must
    be rejected as an invalid identifier — NOT used to read arbitrary
    YAML files outside src/gh_manage/data/profiles/. Defense against
    Codex review finding #1 (Phase 6 PR)."""
    _patch_git(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", bad_name],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "Invalid profile name" in result.output or "not allowed" in result.output


# Phase 7: Branch protection in init
from gh_manage.protection_sync import (
    DowngradeFinding,
    ProtectionDiff,
    ProtectionFieldChange,
)


def _empty_protection_diff() -> ProtectionDiff:
    return ProtectionDiff(changes=(), downgrades=(), current_raw={}, desired_raw={})


def _nonempty_protection_diff(downgrades: tuple = ()) -> ProtectionDiff:
    return ProtectionDiff(
        changes=(ProtectionFieldChange("enforce_admins", False, True),),
        downgrades=downgrades,
        current_raw={},
        desired_raw={"enforce_admins": True, "restrictions": None},
    )


def _patch_protection(mocker: MockerFixture, diff: ProtectionDiff) -> None:
    mocker.patch(
        "gh_manage.commands.init.protection_api.get_branch_protection",
        return_value={},
    )
    mocker.patch(
        "gh_manage.commands.init.protection_sync.compute_protection_diff",
        return_value=diff,
    )


def test_init_applies_protection_when_profile_has_policy(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    _patch_protection(mocker, _nonempty_protection_diff())
    mocker.patch("gh_manage.commands.init.profile_sync.apply_files_diff")
    mock_protection_apply = mocker.patch(
        "gh_manage.commands.init.protection_sync.apply_protection_diff"
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service", "--apply"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    mock_protection_apply.assert_called_once()


def test_init_skips_protection_when_profile_has_none(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    mock_get_protection = mocker.patch(
        "gh_manage.commands.init.protection_api.get_branch_protection"
    )
    # Mock load_config so the profile has protection_policy=None
    from gh_manage.models.profiles import ProfileSpec
    from gh_manage.models.labels import LabelsConfig, CategorySpec, LabelSpec

    def _fake_load_config(path, model_cls):
        if model_cls is ProfileSpec:
            return ProfileSpec(
                version=1,
                name="python-service",
                files=[],
                protection_policy=None,
            )
        if model_cls is LabelsConfig:
            return LabelsConfig(
                version=1,
                categories={
                    "t": CategorySpec(
                        description="t",
                        labels=[LabelSpec(name="test", color="000000")],
                    )
                },
            )
        return mocker.DEFAULT

    mocker.patch("gh_manage.commands.init.load_config", side_effect=_fake_load_config)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    mock_get_protection.assert_not_called()


def test_init_protection_dry_run_prints_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    _patch_protection(mocker, _nonempty_protection_diff())

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Branch protection" in result.output or "enforce_admins" in result.output


def test_init_stops_on_protection_downgrade(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    _patch_protection(
        mocker,
        _nonempty_protection_diff(
            downgrades=(DowngradeFinding("enforce_admins", True, False, "weakened"),),
        ),
    )
    mocker.patch("gh_manage.commands.init.profile_sync.apply_files_diff")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service", "--apply"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "downgrade" in result.output.lower()
    assert "protection sync" in result.output  # actionable redirect
