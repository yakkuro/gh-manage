"""Drift issue lifecycle.

Resolves a drift scan into a GitHub Issue action: create new, update
existing, or close on repeated zero findings (24h double-check rule).
Top of the drift_sync DAG.
"""

from __future__ import annotations

import re as _re
from datetime import datetime, timedelta
from typing import Any

from gh_manage.drift_sync.formatters import format_issue_body, format_issue_comment
from gh_manage.findings import Finding
from gh_manage.github_api import issues as issues_api

_ZERO_FINDINGS_RE = _re.compile(r"<!-- scan:zero-findings:(\S+) -->")


def parse_zero_findings_timestamps(
    comments: list[dict[str, Any]],
) -> list[datetime]:
    """Parse <!-- scan:zero-findings:<ISO8601> --> from comment bodies.

    Returns a list of datetime objects (newest first, matching the
    comment order from get_issue_comments which returns newest first).
    Malformed timestamps are silently skipped.
    """
    timestamps: list[datetime] = []
    for comment in comments:
        body = comment.get("body", "")
        match = _ZERO_FINDINGS_RE.search(body)
        if match:
            try:
                ts = datetime.fromisoformat(match.group(1))
                timestamps.append(ts)
            except ValueError:
                # Malformed timestamp — skip
                continue
    return timestamps


def should_close_issue(comments: list[dict[str, Any]]) -> bool:
    """Check if the 24h double-check rule is satisfied.

    Rule: the most recent 2 scan comments with zero-findings metadata
    must have timestamps ≥ 24h apart. If fewer than 2 zero-findings
    comments exist, or if the gap is < 24h, return False.

    Comments are expected newest-first (from get_issue_comments).
    """
    timestamps = parse_zero_findings_timestamps(comments)
    if len(timestamps) < 2:
        return False
    # timestamps[0] is newest, timestamps[1] is second newest
    gap = timestamps[0] - timestamps[1]
    return gap >= timedelta(hours=24)


_DRIFT_ISSUE_TITLE_TEMPLATE = "[gh-manage drift] {repo}"
_DRIFT_LABEL = "gh-manage:drift"


def resolve_drift_issue(
    findings: tuple[Finding, ...],
    repo: str,
    scan_time: str,
) -> str:
    """Issue state machine: search → create/update/close.

    Returns a human-readable status string for CLI output.
    """
    issues_api.ensure_drift_label(repo)
    existing = issues_api.search_drift_issue(repo)
    has_findings = len(findings) > 0

    if existing is None:
        # No open Issue
        if not has_findings:
            return f"No drift detected for {repo}. No Issue created."
        # Create new Issue
        body = format_issue_body(findings, repo, scan_time)
        comment = format_issue_comment(findings, scan_time)
        title = _DRIFT_ISSUE_TITLE_TEMPLATE.format(repo=repo)
        issue = issues_api.create_issue(repo, title, body, [_DRIFT_LABEL])
        issues_api.add_issue_comment(repo, issue["number"], comment)
        return f"Created issue #{issue['number']} on {repo} ({len(findings)} findings)"

    issue_number = existing["number"]

    # Update existing Issue
    body = format_issue_body(findings, repo, scan_time)
    comment = format_issue_comment(findings, scan_time)
    issues_api.update_issue_body(repo, issue_number, body)
    issues_api.add_issue_comment(repo, issue_number, comment)

    if not has_findings:
        # Check 24h close rule
        comments = issues_api.get_issue_comments(repo, issue_number, per_page=5)
        if should_close_issue(comments):
            issues_api.close_issue(repo, issue_number)
            issues_api.add_issue_comment(
                repo,
                issue_number,
                f"## Auto-closed — {scan_time}\n\n"
                f"Zero drift detected on 2 consecutive scans ≥24h apart. "
                f"If drift recurs, a new Issue will be created.",
            )
            return f"Closed issue #{issue_number} on {repo} (zero drift, 24h rule satisfied)"

    return f"Updated issue #{issue_number} on {repo} ({len(findings)} findings)"
