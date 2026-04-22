"""Tests for `gh manage apply` command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
from pytest_mock import MockerFixture

from gh_manage.cli import main
from gh_manage.findings import Finding


def test_apply_prints_doctor_warnings_to_stderr(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """apply must not block on critical doctor findings — emit warnings
    to stderr only. Spec §5 enforcement scope."""
    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )

    fake = (
        Finding(
            severity="critical",
            check="shape/job-shape-coherence",
            repo="yakkuro/example",
            field_path="x",
            current_value="a",
            desired_value="b",
            message="m",
        ),
    )

    runner = CliRunner()

    with (
        patch(
            "gh_manage.commands.apply.profile_sync.apply_files_diff", return_value=[]
        ),
        patch("gh_manage.commands.apply.labels_sync.apply_diff"),
        patch("gh_manage.commands.apply.labels_api.list_labels", return_value=[]),
        patch("gh_manage.doctor.run_on_path", return_value=fake),
    ):
        result = runner.invoke(
            main,
            ["apply", str(tmp_path), "--profile", "python-service", "--apply"],
        )

    # apply must exit 0 despite critical findings
    assert result.exit_code == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    # warning goes to stderr
    assert "critical" in (result.stderr or "").lower()


def test_apply_dry_run_with_allow_blocking_raises_usage_error(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """--dry-run + --allow-blocking is a user mistake; fail fast."""
    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--dry-run",
            "--allow-blocking",
        ],
    )
    assert result.exit_code == 2  # Click UsageError exits 2
    assert "--allow-blocking requires --apply" in (result.output or "")


def test_apply_allow_blocking_without_apply_raises_usage_error(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """--allow-blocking without --apply is also invalid (default is dry-run)."""
    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["apply", str(tmp_path), "--profile", "python-service", "--allow-blocking"],
    )
    assert result.exit_code == 2
    assert "--allow-blocking requires --apply" in (result.output or "")


def test_apply_blocks_on_unfiltered_high_finding(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """--apply without --also-protection: HIGH shape/required-contexts-match
    is NOT filtered (sync_protection=False) and blocks."""
    from gh_manage.doctor import checks  # noqa: F401

    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    mocker.patch("gh_manage.commands.apply.labels_api.list_labels", return_value=[])
    # Pre-apply doctor is invoked via commands._shared
    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(
            Finding(
                severity="high",
                check="shape/required-contexts-match",
                repo="yakkuro/example",
                field_path="x",
                current_value=None,
                desired_value=None,
                message="m",
            ),
        ),
    )

    runner = CliRunner()
    with (
        patch(
            "gh_manage.commands.apply.profile_sync.apply_files_diff", return_value=[]
        ),
        patch("gh_manage.commands.apply.labels_sync.apply_diff"),
    ):
        result = runner.invoke(
            main,
            ["apply", str(tmp_path), "--profile", "python-service", "--apply"],
        )

    # Pre-apply block raises ClickException → exit 1
    assert result.exit_code == 1
    assert "Pre-apply doctor" in (result.output or "")


def test_apply_also_protection_first_time_succeeds(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """--also-protection filters shape/required-contexts-match — first-time
    adoption (empty protection) proceeds."""
    from gh_manage.doctor import checks  # noqa: F401

    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    mocker.patch("gh_manage.commands.apply.labels_api.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands.apply.protection_api.get_branch_protection",
        return_value={},
    )
    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(
            Finding(
                severity="high",
                check="shape/required-contexts-match",
                repo="yakkuro/example",
                field_path="x",
                current_value=None,
                desired_value=None,
                message="m",
            ),
        ),
    )

    runner = CliRunner()
    with (
        patch(
            "gh_manage.commands.apply.profile_sync.apply_files_diff", return_value=[]
        ),
        patch(
            "gh_manage.commands.apply.protection_sync.apply_protection_diff",
        ),
    ):
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
        )

    # High finding is filtered — apply proceeds, exit 0
    assert result.exit_code == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"


def test_apply_allow_blocking_bypasses_pre_apply_block(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    from gh_manage.doctor import checks  # noqa: F401

    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    mocker.patch("gh_manage.commands.apply.labels_api.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(
            Finding(
                severity="high",
                check="shape/required-contexts-match",
                repo="yakkuro/example",
                field_path="x",
                current_value=None,
                desired_value=None,
                message="m",
            ),
        ),
    )
    runner = CliRunner()
    with (
        patch(
            "gh_manage.commands.apply.profile_sync.apply_files_diff", return_value=[]
        ),
        patch("gh_manage.commands.apply.labels_sync.apply_diff"),
    ):
        result = runner.invoke(
            main,
            [
                "apply",
                str(tmp_path),
                "--profile",
                "python-service",
                "--apply",
                "--allow-blocking",
            ],
        )

    assert result.exit_code == 0
    assert "--allow-blocking" in (result.output or "")


def test_apply_dry_run_skips_pre_apply_doctor(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    run_on_path_mock = mocker.patch("gh_manage.commands._shared.doctor.run_on_path")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["apply", str(tmp_path), "--profile", "python-service", "--dry-run"],
    )
    assert result.exit_code == 0
    run_on_path_mock.assert_not_called()
