"""Tests for commands/labels.py click subcommands."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from pytest_mock import MockerFixture

from gh_manage.cli import main
from gh_manage.commands.labels import _parse_repo
from gh_manage.github_client import GhAuthError, GhNotFoundError, Label
from gh_manage.labels_sync import (
    LabelCreate,
    LabelsDiff,
)


def _empty_diff() -> LabelsDiff:
    return LabelsDiff(renames=(), creates=(), updates=(), deletes=())


def _nonempty_diff() -> LabelsDiff:
    return LabelsDiff(
        renames=(),
        creates=(LabelCreate(label=Label("chore", "e1e7eb", "x")),),
        updates=(),
        deletes=(),
    )


def _write_minimal_config(path: Path) -> None:
    """Write a minimal valid labels.yml fixture."""
    path.write_text(
        "version: 1\n"
        "categories:\n"
        "  test:\n"
        '    description: "t"\n'
        "    labels:\n"
        '      - {name: "chore", color: "e1e7eb", description: "x"}\n',
        encoding="utf-8",
    )


# _parse_repo — parametrized (Q6 C)
@pytest.mark.parametrize(
    ("input_repo", "expected"),
    [
        ("gh-manage", "yakkuro/gh-manage"),
        ("yakkuro/gh-manage", "yakkuro/gh-manage"),
        ("other-org/other-repo", "other-org/other-repo"),
    ],
)
def test_parse_repo_normalization(input_repo: str, expected: str) -> None:
    assert _parse_repo(input_repo) == expected


# sync command
def test_sync_dry_run_by_default_prints_plan(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_nonempty_diff(),
    )
    mock_apply = mocker.patch("gh_manage.commands.labels.labels_sync.apply_diff")

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["labels", "sync", "gh-manage", "--config", str(config_file)],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "Dry-run" in result.output
    mock_apply.assert_not_called()


def test_sync_with_apply_calls_apply_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_nonempty_diff(),
    )
    mock_apply = mocker.patch("gh_manage.commands.labels.labels_sync.apply_diff")

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "labels",
            "sync",
            "gh-manage",
            "--apply",
            "--config",
            str(config_file),
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "Applied" in result.output
    mock_apply.assert_called_once()


def test_sync_with_apply_passes_prune_to_compute_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mock_compute = mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_empty_diff(),
    )
    mocker.patch("gh_manage.commands.labels.labels_sync.apply_diff")

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    runner.invoke(
        main,
        [
            "labels",
            "sync",
            "gh-manage",
            "--apply",
            "--prune",
            "--config",
            str(config_file),
        ],
        prog_name="gh-manage",
    )
    assert mock_compute.call_args.kwargs["prune"] is True


def test_sync_apply_and_dry_run_conflict_raises_usage_error(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "labels",
            "sync",
            "gh-manage",
            "--apply",
            "--dry-run",
            "--config",
            str(config_file),
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 2  # click UsageError


def test_sync_bare_repo_prepends_yakkuro(mocker: MockerFixture, tmp_path: Path) -> None:
    mock_list = mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_empty_diff(),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    runner.invoke(
        main,
        ["labels", "sync", "gh-manage", "--config", str(config_file)],
        prog_name="gh-manage",
    )
    mock_list.assert_called_once_with("yakkuro/gh-manage")


def test_sync_owner_slash_repo_passes_through(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mock_list = mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_empty_diff(),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    runner.invoke(
        main,
        [
            "labels",
            "sync",
            "other-org/other-repo",
            "--config",
            str(config_file),
        ],
        prog_name="gh-manage",
    )
    mock_list.assert_called_once_with("other-org/other-repo")


def test_sync_empty_diff_prints_no_changes(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_empty_diff(),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["labels", "sync", "gh-manage", "--config", str(config_file)],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "No changes" in result.output


def test_sync_gh_auth_error_displays_actionable_message(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch(
        "gh_manage.github_client.list_labels",
        side_effect=GhAuthError("Run `gh auth login` and try again."),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["labels", "sync", "gh-manage", "--config", str(config_file)],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "gh auth login" in result.output


def test_sync_config_not_found_returns_click_path_error() -> None:
    """click.Path(exists=True) rejects nonexistent paths at arg parse time,
    returning exit 2 (usage error) not 1 (ConfigError)."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "labels",
            "sync",
            "gh-manage",
            "--config",
            "/nonexistent/labels.yml",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 2


# diff command
def test_diff_exit_zero_when_no_diff(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_empty_diff(),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["labels", "diff", "gh-manage", "--config", str(config_file)],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "No diff" in result.output


def test_diff_exit_one_when_diff_present(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_nonempty_diff(),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["labels", "diff", "gh-manage", "--config", str(config_file)],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "chore" in result.output


def test_diff_prune_flag_passed_to_compute_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("gh_manage.github_client.list_labels", return_value=[])
    mock_compute = mocker.patch(
        "gh_manage.commands.labels.labels_sync.compute_diff",
        return_value=_empty_diff(),
    )

    config_file = tmp_path / "labels.yml"
    _write_minimal_config(config_file)

    runner = CliRunner()
    runner.invoke(
        main,
        [
            "labels",
            "diff",
            "gh-manage",
            "--prune",
            "--config",
            str(config_file),
        ],
        prog_name="gh-manage",
    )
    assert mock_compute.call_args.kwargs["prune"] is True


# show command
def test_show_lists_current_labels_sorted(mocker: MockerFixture) -> None:
    mocker.patch(
        "gh_manage.github_client.list_labels",
        return_value=[
            Label(name="zebra", color="000000", description="z"),
            Label(name="alpha", color="ffffff", description="a"),
        ],
    )
    runner = CliRunner()
    result = runner.invoke(main, ["labels", "show", "gh-manage"], prog_name="gh-manage")
    assert result.exit_code == 0
    # alpha appears before zebra
    alpha_idx = result.output.index("alpha")
    zebra_idx = result.output.index("zebra")
    assert alpha_idx < zebra_idx


def test_show_does_not_load_config(mocker: MockerFixture) -> None:
    """show should succeed without any config/labels.yml present."""
    mocker.patch(
        "gh_manage.github_client.list_labels",
        return_value=[Label(name="bug", color="d73a4a", description="x")],
    )
    mock_load = mocker.patch("gh_manage.commands.labels.load_config")
    runner = CliRunner()
    result = runner.invoke(main, ["labels", "show", "gh-manage"], prog_name="gh-manage")
    assert result.exit_code == 0
    mock_load.assert_not_called()


def test_show_gh_not_found_displays_actionable_message(
    mocker: MockerFixture,
) -> None:
    mocker.patch(
        "gh_manage.github_client.list_labels",
        side_effect=GhNotFoundError(
            "GitHub API returned 404 for repos/foo/bar/labels. "
            "Check the resource name and your auth status with `gh auth status`."
        ),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["labels", "show", "nonexistent"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "gh auth status" in result.output
