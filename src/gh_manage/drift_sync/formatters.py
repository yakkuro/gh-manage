"""Report formatters.

Pure rendering: Finding tuples → strings (stdout, JSON, Markdown,
issue body, issue comment). No I/O, no network. Layer 5 in the DAG.
"""

from __future__ import annotations

import json as _json
from typing import Any

from gh_manage.findings import Finding, Severity

_SEVERITY_ORDER: tuple[Severity, ...] = ("critical", "high", "medium", "low")


def _group_by_severity(
    findings: tuple[Finding, ...],
) -> dict[Severity, list[Finding]]:
    grouped: dict[Severity, list[Finding]] = {s: [] for s in _SEVERITY_ORDER}
    for f in findings:
        grouped[f.severity].append(f)
    return grouped


def _count_by_severity(findings: tuple[Finding, ...]) -> dict[Severity, int]:
    counts: dict[Severity, int] = {s: 0 for s in _SEVERITY_ORDER}
    for f in findings:
        counts[f.severity] += 1
    return counts


def format_stdout_report(findings: tuple[Finding, ...]) -> str:
    """Render findings as a human-readable stdout report.

    Layout:
      Drift report for <repo>

        [CRITICAL] <check>/<field_path>
          <message>
          Fix: <remediation>

        [HIGH] ...

      Summary: N critical, N high, N medium, N low — N findings total.

    When findings is empty, emits "No drift detected." and a summary line.
    """
    if not findings:
        return "No drift detected. 0 findings."

    grouped = _group_by_severity(findings)
    counts = _count_by_severity(findings)
    total = len(findings)
    repo = findings[0].repo  # all findings share the same repo in a single scan

    lines: list[str] = [f"Drift report for {repo}", ""]
    for severity in _SEVERITY_ORDER:
        items = grouped[severity]
        if not items:
            continue
        for item in items:
            lines.append(f"  [{severity.upper()}] {item.check}/{item.field_path}")
            lines.append(f"    {item.message}")
            if item.remediation:
                lines.append(f"    Fix: {item.remediation}")
            lines.append("")
    lines.append(
        f"Summary: {counts['critical']} critical, {counts['high']} high, "
        f"{counts['medium']} medium, {counts['low']} low — {total} findings total."
    )
    return "\n".join(lines)


def format_json_report(findings: tuple[Finding, ...]) -> str:
    """Render findings as a stable JSON document.

    Shape:
      {
        "version": 1,
        "repo": "owner/repo",
        "findings": [{...}, ...],
        "summary": {"critical": N, "high": N, "medium": N, "low": N, "total": N}
      }

    `version` is a schema version for consumers; bump if the shape
    changes incompatibly. `repo` is the first finding's repo (all
    findings in a single scan share the same repo). `findings` is a
    list of per-finding dicts with every Finding field except
    `current_value` / `desired_value` serialized via json.dumps
    defaults (complex types fall back to repr).
    """
    repo = findings[0].repo if findings else ""
    counts = _count_by_severity(findings)

    def _finding_to_dict(f: Finding) -> dict[str, Any]:
        return {
            "severity": f.severity,
            "check": f.check,
            "repo": f.repo,
            "field_path": f.field_path,
            "current_value": f.current_value,
            "desired_value": f.desired_value,
            "message": f.message,
            "remediation": f.remediation,
        }

    doc = {
        "version": 1,
        "repo": repo,
        "findings": [_finding_to_dict(f) for f in findings],
        "summary": {
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
            "low": counts["low"],
            "total": len(findings),
        },
    }
    return _json.dumps(doc, indent=2, default=str)


def format_markdown_report(findings: tuple[Finding, ...]) -> str:
    """Render findings as GitHub-flavored markdown suitable for an
    Issue body or a standalone report file.

    Layout:
      # Drift report — `<repo>`

      **Summary**: N critical, N high, N medium, N low — N findings total.

      ## Critical

      ### `check/field_path`

      <message>

      - **Current**: `<current_value>`
      - **Desired**: `<desired_value>`
      - **Fix**: `<remediation>`

      ## High
      ...
    """
    if not findings:
        return "# Drift report\n\n0 findings. No drift detected.\n"

    repo = findings[0].repo
    counts = _count_by_severity(findings)
    total = len(findings)
    grouped = _group_by_severity(findings)

    lines: list[str] = [
        f"# Drift report — `{repo}`",
        "",
        (
            f"**Summary**: {counts['critical']} critical, {counts['high']} high, "
            f"{counts['medium']} medium, {counts['low']} low — {total} findings total."
        ),
        "",
    ]

    section_titles = {
        "critical": "Critical",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    }
    for severity in _SEVERITY_ORDER:
        items = grouped[severity]
        if not items:
            continue
        lines.append(f"## {section_titles[severity]}")
        lines.append("")
        for item in items:
            lines.append(f"### `{item.check}/{item.field_path}`")
            lines.append("")
            lines.append(item.message)
            lines.append("")
            lines.append(f"- **Current**: `{item.current_value}`")
            lines.append(f"- **Desired**: `{item.desired_value}`")
            if item.remediation:
                lines.append(f"- **Fix**: `{item.remediation}`")
            lines.append("")

    return "\n".join(lines)


def format_issue_body(findings: tuple[Finding, ...], repo: str, scan_time: str) -> str:
    """Format the GitHub Issue body for a drift report.

    Layout:
      <!-- gh-manage:drift:<repo> -->        (dormant search metadata)
      <format_markdown_report output>        (the report itself)
      **Last scan**: <scan_time>
      > Note: This issue body is auto-updated by gh-manage drift scanner.
      > Add comments below for manual notes.
    """
    markdown = format_markdown_report(findings)

    lines = [
        f"<!-- gh-manage:drift:{repo} -->",
        "",
        markdown,
        "",
        f"**Last scan**: {scan_time}",
        "",
        "> Note: This issue body is auto-updated by gh-manage drift scanner. "
        "Add comments below for manual notes.",
    ]
    return "\n".join(lines)


def format_issue_comment(findings: tuple[Finding, ...], scan_time: str) -> str:
    """Format a scan run comment with hidden metadata.

    Hidden metadata:
    - <!-- scan:finding-count:N --> — always present
    - <!-- scan:zero-findings:<ISO8601> --> — only when N=0

    The 24h auto-close logic parses these from comments to determine
    whether to close the Issue.
    """
    count = len(findings)
    counts = _count_by_severity(findings)

    lines = [
        f"## Scan run — {scan_time}",
        "",
    ]

    if count == 0:
        lines.append(f"<!-- scan:zero-findings:{scan_time} -->")
    lines.append(f"<!-- scan:finding-count:{count} -->")
    lines.append("")

    if count == 0:
        lines.append("**0 findings** — no drift detected.")
    else:
        summary_parts = []
        for sev in _SEVERITY_ORDER:
            c = counts[sev]
            if c > 0:
                summary_parts.append(f"{c} {sev}")
        lines.append(f"**{count} findings** ({', '.join(summary_parts)})")

    return "\n".join(lines)
