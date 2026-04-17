"""CLI integration for `gh-manage doctor` (spec §2)."""

from __future__ import annotations

import json
from unittest.mock import patch

from click.testing import CliRunner

from gh_manage.cli import main


def test_doctor_cli_registered_on_main_group():
    result = CliRunner().invoke(main, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "doctor" in result.output.lower()


def test_doctor_cli_exit_1_on_critical_finding():
    from gh_manage.findings import Finding

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
    with patch("gh_manage.doctor.run_on_remote", return_value=fake):
        result = CliRunner().invoke(
            main, ["doctor", "yakkuro/example", "--profile", "python-service"]
        )
    assert result.exit_code == 1
    assert "critical" in result.output.lower()


def test_doctor_cli_exit_0_on_no_findings():
    with patch("gh_manage.doctor.run_on_remote", return_value=()):
        result = CliRunner().invoke(
            main, ["doctor", "yakkuro/example", "--profile", "python-service"]
        )
    assert result.exit_code == 0


def test_doctor_cli_exit_zero_flag_overrides_critical():
    from gh_manage.findings import Finding

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
    with patch("gh_manage.doctor.run_on_remote", return_value=fake):
        result = CliRunner().invoke(
            main,
            [
                "doctor",
                "yakkuro/example",
                "--profile",
                "python-service",
                "--exit-zero",
            ],
        )
    assert result.exit_code == 0


def test_doctor_cli_json_report_mode_emits_valid_payload():
    with patch("gh_manage.doctor.run_on_remote", return_value=()):
        result = CliRunner().invoke(
            main,
            [
                "doctor",
                "yakkuro/example",
                "--profile",
                "python-service",
                "--report-mode",
                "json",
            ],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["repo"] == "yakkuro/example"
    assert data["findings"] == []
