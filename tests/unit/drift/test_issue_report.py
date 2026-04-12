"""Tests for drift Issue body/comment formatting + metadata parsing."""

from __future__ import annotations


from gh_manage.drift_sync import (
    Finding,
    format_issue_body,
    format_issue_comment,
    parse_zero_findings_timestamps,
    should_close_issue,
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


def _make_comment(body: str) -> dict:
    return {"body": body}


# parse_zero_findings_timestamps
def test_parse_zero_findings_extracts_timestamps() -> None:
    comments = [
        _make_comment(
            "## Scan\n<!-- scan:zero-findings:2026-04-12T09:00:00+00:00 -->\n<!-- scan:finding-count:0 -->"
        ),
        _make_comment("## Scan\n<!-- scan:finding-count:3 -->"),
        _make_comment(
            "## Scan\n<!-- scan:zero-findings:2026-04-05T09:00:00+00:00 -->\n<!-- scan:finding-count:0 -->"
        ),
    ]
    timestamps = parse_zero_findings_timestamps(comments)
    assert len(timestamps) == 2
    assert timestamps[0].year == 2026
    assert timestamps[0].month == 4
    assert timestamps[0].day == 12


def test_parse_zero_findings_empty_comments() -> None:
    assert parse_zero_findings_timestamps([]) == []


def test_parse_zero_findings_no_metadata() -> None:
    comments = [_make_comment("human comment without metadata")]
    assert parse_zero_findings_timestamps(comments) == []


def test_parse_zero_findings_malformed_timestamp_skipped() -> None:
    comments = [_make_comment("<!-- scan:zero-findings:not-a-date -->")]
    # Malformed timestamps are silently skipped (warning in production)
    assert parse_zero_findings_timestamps(comments) == []


# should_close_issue
def test_should_close_issue_two_consecutive_zero_24h_apart() -> None:
    comments = [
        _make_comment(
            "<!-- scan:zero-findings:2026-04-12T09:00:00+00:00 -->\n<!-- scan:finding-count:0 -->"
        ),
        _make_comment(
            "<!-- scan:zero-findings:2026-04-05T09:00:00+00:00 -->\n<!-- scan:finding-count:0 -->"
        ),
    ]
    assert should_close_issue(comments) is True


def test_should_close_issue_only_one_zero_scan() -> None:
    comments = [
        _make_comment(
            "<!-- scan:zero-findings:2026-04-12T09:00:00+00:00 -->\n<!-- scan:finding-count:0 -->"
        ),
    ]
    assert should_close_issue(comments) is False


def test_should_close_issue_two_zero_within_24h() -> None:
    comments = [
        _make_comment(
            "<!-- scan:zero-findings:2026-04-12T09:00:00+00:00 -->\n<!-- scan:finding-count:0 -->"
        ),
        _make_comment(
            "<!-- scan:zero-findings:2026-04-12T08:00:00+00:00 -->\n<!-- scan:finding-count:0 -->"
        ),
    ]
    assert should_close_issue(comments) is False


def test_should_close_issue_latest_has_findings() -> None:
    comments = [
        _make_comment("<!-- scan:finding-count:3 -->"),
        _make_comment(
            "<!-- scan:zero-findings:2026-04-05T09:00:00+00:00 -->\n<!-- scan:finding-count:0 -->"
        ),
    ]
    assert should_close_issue(comments) is False


def test_should_close_issue_empty_comments() -> None:
    assert should_close_issue([]) is False
