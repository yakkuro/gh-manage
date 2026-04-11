"""Tests for `gh manage apply` click command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from pytest_mock import MockerFixture

from gh_manage.cli import main
from gh_manage.labels_sync import LabelsDiff


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


def test_apply_also_protection_errors_out_with_phase_7_message(
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
            "--also-protection",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "Phase 7" in result.output


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
