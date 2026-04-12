"""Tests for `gh manage drift` click command."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from pytest_mock import MockerFixture

from gh_manage.cli import main
from gh_manage.drift_sync import Finding


def _patch_git_and_repo(
    mocker: MockerFixture, owner_repo: str = "yakkuro/gh-manage"
) -> None:
    mocker.patch(
        "gh_manage.commands.drift.git_cli.get_origin_owner_repo",
        return_value=owner_repo,
    )
    mocker.patch(
        "gh_manage.commands.drift.repo_info.get_default_branch",
        return_value="main",
    )


def _patch_run_all_checks(mocker: MockerFixture, findings: tuple[Finding, ...]) -> None:
    mocker.patch(
        "gh_manage.commands.drift.drift_sync.run_all_checks",
        return_value=findings,
    )


def _sample_finding(severity: str = "high") -> Finding:
    return Finding(
        severity=severity,  # type: ignore[arg-type]
        check="labels",
        repo="yakkuro/gh-manage",
        field_path="labels[priority/critical]",
        current_value=None,
        desired_value="priority/critical",
        message="Label priority/critical is missing",
        remediation="gh manage labels sync . --apply",
    )


# Happy paths
def test_drift_stdout_no_findings(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(mocker, ())
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["drift", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "No drift" in result.output


def test_drift_stdout_with_findings_shows_report(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(mocker, (_sample_finding(),))
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["drift", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "HIGH" in result.output
    assert "priority/critical" in result.output


def test_drift_json_mode_emits_parseable_document(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(mocker, (_sample_finding(),))
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "python-service",
            "--report-mode",
            "json",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["version"] == 1
    assert parsed["findings"][0]["field_path"] == "labels[priority/critical]"


def test_drift_markdown_file_mode_writes_to_output(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(mocker, (_sample_finding(),))
    output_path = tmp_path / "drift.md"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "python-service",
            "--report-mode",
            "markdown-file",
            "--output",
            str(output_path),
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "# Drift report" in content
    assert "priority/critical" in content


def test_drift_severity_filter_drops_below_threshold(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(
        mocker,
        (
            _sample_finding("low"),
            _sample_finding("critical"),
        ),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "python-service",
            "--severity",
            "high",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    # low entry dropped, critical kept
    assert "CRITICAL" in result.output
    assert "1 findings" in result.output or "1 findings total" in result.output


# Error paths
def test_drift_unknown_profile_exits_1(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git_and_repo(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "nonexistent-profile-xyz",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "profile" in result.output.lower()


def test_drift_profile_name_path_traversal_rejected(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["drift", str(tmp_path), "--profile", "../../etc/passwd"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "invalid" in result.output.lower() or "not allowed" in result.output.lower()


def test_drift_invalid_severity_exits_2(mocker: MockerFixture, tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "python-service",
            "--severity",
            "urgent",  # not a valid level
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 2


def test_drift_output_path_write_failure_raises(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(mocker, (_sample_finding(),))
    # Output to a path under a nonexistent parent
    bad_output = tmp_path / "nonexistent-dir" / "drift.md"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "python-service",
            "--report-mode",
            "markdown-file",
            "--output",
            str(bad_output),
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "Cannot write" in result.output or "cannot write" in result.output.lower()


# Task 6: --report-mode issue


def test_drift_issue_mode_creates_issue(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(mocker, (_sample_finding(),))
    mock_resolve = mocker.patch(
        "gh_manage.commands.drift.drift_sync.resolve_drift_issue",
        return_value="Created issue #42 on yakkuro/gh-manage (1 findings)",
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "python-service",
            "--report-mode",
            "issue",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Created issue #42" in result.output
    mock_resolve.assert_called_once()


def test_drift_issue_mode_zero_findings(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git_and_repo(mocker)
    _patch_run_all_checks(mocker, ())
    mock_resolve = mocker.patch(
        "gh_manage.commands.drift.drift_sync.resolve_drift_issue",
        return_value="No drift detected for yakkuro/gh-manage. No Issue created.",
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "drift",
            str(tmp_path),
            "--profile",
            "python-service",
            "--report-mode",
            "issue",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "No drift" in result.output
    mock_resolve.assert_called_once()
