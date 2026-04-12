"""Tests for drift Issue body/comment formatting + metadata parsing."""

from __future__ import annotations

from gh_manage.drift_sync import (
    Finding,
    format_issue_body,
    format_issue_comment,
)


def _f(severity: str = "high", check: str = "labels", field_path: str = "x") -> Finding:
    return Finding(
        severity=severity,  # type: ignore[arg-type]
        check=check,
        repo="yakkuro/gh-manage",
        field_path=field_path,
        current_value=None,
        desired_value="y",
        message="test message",
    )


# format_issue_body
def test_format_issue_body_contains_hidden_metadata() -> None:
    body = format_issue_body((_f(),), "yakkuro/gh-manage", "2026-04-12T09:00:00Z")
    assert "<!-- gh-manage:drift:yakkuro/gh-manage -->" in body


def test_format_issue_body_contains_scan_timestamp() -> None:
    body = format_issue_body((_f(),), "yakkuro/gh-manage", "2026-04-12T09:00:00Z")
    assert "2026-04-12T09:00:00Z" in body


def test_format_issue_body_contains_markdown_report() -> None:
    body = format_issue_body((_f(),), "yakkuro/gh-manage", "2026-04-12T09:00:00Z")
    assert "# Drift report" in body
    assert "test message" in body


def test_format_issue_body_contains_auto_update_note() -> None:
    body = format_issue_body((_f(),), "yakkuro/gh-manage", "2026-04-12T09:00:00Z")
    assert "auto-updated" in body.lower()


def test_format_issue_body_zero_findings() -> None:
    body = format_issue_body((), "yakkuro/gh-manage", "2026-04-12T09:00:00Z")
    assert "0 findings" in body


# format_issue_comment
def test_format_issue_comment_contains_finding_count_metadata() -> None:
    comment = format_issue_comment((_f(), _f()), "2026-04-12T09:00:00Z")
    assert "<!-- scan:finding-count:2 -->" in comment


def test_format_issue_comment_zero_findings_has_zero_metadata() -> None:
    comment = format_issue_comment((), "2026-04-12T09:00:00Z")
    assert "<!-- scan:zero-findings:2026-04-12T09:00:00Z -->" in comment
    assert "<!-- scan:finding-count:0 -->" in comment


def test_format_issue_comment_nonzero_has_no_zero_findings_tag() -> None:
    comment = format_issue_comment((_f(),), "2026-04-12T09:00:00Z")
    assert "scan:zero-findings" not in comment
    assert "<!-- scan:finding-count:1 -->" in comment


def test_format_issue_comment_contains_scan_timestamp() -> None:
    comment = format_issue_comment((_f(),), "2026-04-12T09:00:00Z")
    assert "2026-04-12T09:00:00Z" in comment
