"""Tests for `gh manage apply` click command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from pytest_mock import MockerFixture

from gh_manage.cli import main
from gh_manage.labels_sync import LabelsDiff
from gh_manage.protection_sync import (
    DowngradeFinding,
    ProtectionDiff,
    ProtectionFieldChange,
)


def _empty_labels_diff() -> LabelsDiff:
    return LabelsDiff(renames=(), creates=(), updates=(), deletes=())


def _patch_git(mocker: MockerFixture, owner_repo: str = "yakkuro/gh-manage") -> None:
    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value=owner_repo,
    )


# Default behavior — files only, no labels
def test_apply_dry_run_default_does_not_call_labels_api(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    mock_list = mocker.patch("gh_manage.github_api.labels.list_labels")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["apply", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Dry-run" in result.output
    mock_list.assert_not_called()


def test_apply_with_also_labels_calls_labels_api(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    mocker.patch("gh_manage.github_api.labels.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.apply.labels_sync.compute_diff",
        return_value=_empty_labels_diff(),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--also-labels",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output


def test_apply_with_also_labels_and_apply_calls_labels_apply(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    mocker.patch("gh_manage.github_api.labels.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.apply.labels_sync.compute_diff",
        return_value=_empty_labels_diff(),
    )
    mocker.patch("gh_manage.commands.apply.profile_sync.apply_files_diff")
    mock_labels_apply = mocker.patch("gh_manage.commands.apply.labels_sync.apply_diff")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--also-labels",
            "--apply",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    mock_labels_apply.assert_called_once()


def test_apply_apply_and_dry_run_conflict(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
            "--dry-run",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 2  # UsageError


def test_apply_does_not_print_next_steps(mocker: MockerFixture, tmp_path: Path) -> None:
    """apply is for existing managed repos, not bootstrap. The 'Next steps'
    message belongs to init only."""
    _patch_git(mocker)
    mocker.patch("gh_manage.commands.apply.profile_sync.apply_files_diff")

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
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Next steps" not in result.output
    assert "bootstrap" not in result.output


def _nonempty_protection_diff(downgrades: tuple = ()) -> ProtectionDiff:
    return ProtectionDiff(
        changes=(ProtectionFieldChange("enforce_admins", False, True),),
        downgrades=downgrades,
        current_raw={},
        desired_raw={"enforce_admins": True, "restrictions": None},
    )


def _patch_protection_for_apply(mocker: MockerFixture, diff: ProtectionDiff) -> None:
    mocker.patch(
        "gh_manage.commands.apply.protection_api.get_branch_protection",
        return_value={},
    )
    mocker.patch(
        "gh_manage.commands.apply.protection_sync.compute_protection_diff",
        return_value=diff,
    )


def test_apply_also_protection_dry_run_displays_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_protection_for_apply(mocker, _nonempty_protection_diff())

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
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Branch protection" in result.output or "enforce_admins" in result.output


def test_apply_also_protection_apply_calls_apply_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_protection_for_apply(mocker, _nonempty_protection_diff())
    mocker.patch("gh_manage.commands.apply.profile_sync.apply_files_diff")
    mock_protection_apply = mocker.patch(
        "gh_manage.commands.apply.protection_sync.apply_protection_diff"
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
            "--apply",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    mock_protection_apply.assert_called_once()


def test_apply_also_protection_downgrade_redirects_to_protection_sync(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_protection_for_apply(
        mocker,
        _nonempty_protection_diff(
            downgrades=(DowngradeFinding("enforce_admins", True, False, "weakened"),),
        ),
    )
    mock_files_apply = mocker.patch(
        "gh_manage.commands.apply.profile_sync.apply_files_diff"
    )
    mock_labels_apply = mocker.patch("gh_manage.commands.apply.labels_sync.apply_diff")
    mock_protection_apply = mocker.patch(
        "gh_manage.commands.apply.protection_sync.apply_protection_diff"
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
            "--apply",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "downgrade" in result.output.lower()
    assert "protection sync" in result.output
    # Downgrade must abort BEFORE any side effect. Otherwise the repo
    # ends up in a partial-apply state with files already written but
    # protection untouched.
    mock_files_apply.assert_not_called()
    mock_labels_apply.assert_not_called()
    mock_protection_apply.assert_not_called()
