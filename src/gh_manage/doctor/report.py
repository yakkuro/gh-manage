"""Doctor report formatters: stdout / json / markdown.

Output conventions match drift_sync.format_*_report so the drift
scanner can emit shape findings alongside existing labels / protection
/ profile_files findings without a format change.

Spec §2 (CLI output) + §4 (drift integration).
"""

from __future__ import annotations

import json
from dataclasses import asdict

from gh_manage.findings import Finding, Severity

_SEVERITY_ORDER: tuple[Severity, ...] = ("critical", "high", "medium", "low")


def _bucket(findings: tuple[Finding, ...]) -> dict[Severity, list[Finding]]:
    buckets: dict[Severity, list[Finding]] = {s: [] for s in _SEVERITY_ORDER}
    for f in findings:
        buckets[f.severity].append(f)
    return buckets


def _counts_line(findings: tuple[Finding, ...]) -> str:
    counts = {s: 0 for s in _SEVERITY_ORDER}
    for f in findings:
        counts[f.severity] += 1
    return ", ".join(f"{counts[s]} {s}" for s in _SEVERITY_ORDER)


def format_stdout(findings: tuple[Finding, ...], *, repo: str) -> str:
    """Human-readable output for the doctor CLI."""
    lines: list[str] = [f"{repo} — {_counts_line(findings)}"]
    buckets = _bucket(findings)
    for sev in _SEVERITY_ORDER:
        sev_findings = buckets[sev]
        if not sev_findings:
            continue
        lines.append("")
        lines.append(f"## {sev}")
        for f in sev_findings:
            lines.append("")
            lines.append(f"### {f.check}")
            lines.append(f.field_path)
            lines.append(f"Current:  {f.current_value}")
            lines.append(f"Desired:  {f.desired_value}")
            lines.append(f.message)
            if f.remediation:
                lines.append(f"→ {f.remediation}")
    return "\n".join(lines)


def format_json(findings: tuple[Finding, ...], *, repo: str) -> str:
    """Machine-readable output. Schema matches drift's JSON v1."""
    payload = {
        "schema_version": 1,
        "repo": repo,
        "findings": [asdict(f) for f in findings],
    }
    return json.dumps(payload, indent=2, default=str, sort_keys=True)


def format_markdown(findings: tuple[Finding, ...], *, repo: str) -> str:
    """Markdown for drift-scanner issue bodies."""
    if not findings:
        return f"# {repo}\n\nNo findings.\n"
    lines: list[str] = [f"# {repo}", "", _counts_line(findings), ""]
    buckets = _bucket(findings)
    for sev in _SEVERITY_ORDER:
        sev_findings = buckets[sev]
        if not sev_findings:
            continue
        lines.append(f"## {sev}")
        lines.append("")
        for f in sev_findings:
            lines.append(f"### {f.check}")
            lines.append("")
            lines.append(f"- **Field**: `{f.field_path}`")
            lines.append(f"- **Current**: `{f.current_value}`")
            lines.append(f"- **Desired**: `{f.desired_value}`")
            lines.append(f"- {f.message}")
            if f.remediation:
                lines.append(f"- **Fix**: {f.remediation}")
            lines.append("")
    return "\n".join(lines)
