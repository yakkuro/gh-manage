"""Tests for gh_manage.drift_sync report formatters."""

from __future__ import annotations

import json

from gh_manage.drift_sync import (
    Finding,
    format_json_report,
    format_markdown_report,
    format_stdout_report,
)


def _f(
    severity: str,
    check: str,
    field_path: str,
    message: str,
    remediation: str | None = None,
) -> Finding:
    return Finding(
        severity=severity,  # type: ignore[arg-type]
        check=check,
        repo="yakkuro/gh-manage",
        field_path=field_path,
        current_value=None,
        desired_value="x",
        message=message,
        remediation=remediation,
    )


# ========== Task 10: format_stdout_report tests ==========


def test_format_stdout_report_empty_shows_no_drift() -> None:
    report = format_stdout_report(())
    assert "No drift" in report or "0 findings" in report


def test_format_stdout_report_single_finding_shows_severity_tag() -> None:
    findings = (_f("critical", "protection", "enforce_admins", "admin weakened"),)
    report = format_stdout_report(findings)
    assert "CRITICAL" in report
    assert "enforce_admins" in report
    assert "admin weakened" in report


def test_format_stdout_report_multi_severity_order() -> None:
    findings = (
        _f("low", "labels", "x", "a"),
        _f("critical", "protection", "y", "b"),
        _f("medium", "labels", "z", "c"),
        _f("high", "profile_files", "CLAUDE.md", "d"),
    )
    report = format_stdout_report(findings)
    # Sections should appear in severity order: critical, high, medium, low
    critical_pos = report.find("CRITICAL")
    high_pos = report.find("HIGH")
    medium_pos = report.find("MEDIUM")
    low_pos = report.find("LOW")
    assert critical_pos < high_pos < medium_pos < low_pos


def test_format_stdout_report_includes_remediation() -> None:
    findings = (
        _f(
            "high",
            "labels",
            "x",
            "missing",
            remediation="gh manage labels sync . --apply",
        ),
    )
    report = format_stdout_report(findings)
    assert "gh manage labels sync" in report


def test_format_stdout_report_summary_line() -> None:
    findings = (
        _f("critical", "protection", "a", "x"),
        _f("critical", "protection", "b", "y"),
        _f("high", "labels", "c", "z"),
    )
    report = format_stdout_report(findings)
    assert "2 critical" in report or "2 CRITICAL" in report
    assert "1 high" in report or "1 HIGH" in report
    assert "3 findings" in report or "Total: 3" in report or "3 total" in report


# ========== Task 11: format_json_report tests ==========


def test_format_json_report_empty_valid_shape() -> None:
    rendered = format_json_report(())
    parsed = json.loads(rendered)
    assert parsed["version"] == 1
    assert parsed["findings"] == []
    assert parsed["summary"]["total"] == 0


def test_format_json_report_single_finding_round_trip() -> None:
    findings = (_f("high", "labels", "x", "missing"),)
    rendered = format_json_report(findings)
    parsed = json.loads(rendered)
    assert parsed["version"] == 1
    assert len(parsed["findings"]) == 1
    entry = parsed["findings"][0]
    assert entry["severity"] == "high"
    assert entry["check"] == "labels"
    assert entry["repo"] == "yakkuro/gh-manage"
    assert entry["field_path"] == "x"
    assert entry["message"] == "missing"
    assert parsed["summary"]["high"] == 1
    assert parsed["summary"]["total"] == 1


def test_format_json_report_multi_finding_summary_counts() -> None:
    findings = (
        _f("critical", "protection", "a", "x"),
        _f("critical", "protection", "b", "y"),
        _f("medium", "labels", "c", "z"),
    )
    parsed = json.loads(format_json_report(findings))
    assert parsed["summary"]["critical"] == 2
    assert parsed["summary"]["medium"] == 1
    assert parsed["summary"]["high"] == 0
    assert parsed["summary"]["total"] == 3


# ========== Task 11: format_markdown_report tests ==========


def test_format_markdown_report_empty_no_findings_heading() -> None:
    report = format_markdown_report(())
    assert "# Drift report" in report
    assert "0 findings" in report


def test_format_markdown_report_single_finding_structure() -> None:
    findings = (_f("critical", "protection", "enforce_admins", "admin weakened"),)
    report = format_markdown_report(findings)
    assert "## Critical" in report
    assert "enforce_admins" in report
    assert "admin weakened" in report


def test_format_markdown_report_per_severity_sections() -> None:
    findings = (
        _f("critical", "protection", "a", "x"),
        _f("high", "labels", "b", "y"),
        _f("medium", "labels", "c", "z"),
    )
    report = format_markdown_report(findings)
    critical_pos = report.find("## Critical")
    high_pos = report.find("## High")
    medium_pos = report.find("## Medium")
    assert critical_pos != -1
    assert high_pos != -1
    assert medium_pos != -1
    assert critical_pos < high_pos < medium_pos
