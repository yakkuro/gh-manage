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
