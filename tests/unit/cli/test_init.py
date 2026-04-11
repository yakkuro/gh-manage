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
