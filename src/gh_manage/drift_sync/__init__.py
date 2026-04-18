"""Pure-function engine for drift detection.

Mirrors gh_manage.profile_sync / labels_sync / protection_sync. Phase 8
ships the drift scanner with a check registry pattern:

  @register_check
  def check_labels(ctx: ScanContext) -> tuple[Finding, ...]: ...

  @register_check
  def check_protection(ctx: ScanContext) -> tuple[Finding, ...]: ...

  @register_check
  def check_profile_files(ctx: ScanContext) -> tuple[Finding, ...]: ...

New checks added by future phases (workflow pinning, etc.) just write
a decorated function — the orchestrator in `run_all_checks` does not
change.

Each check:
  1. Receives a ScanContext with the resolved path, repo, default branch,
     loaded profile, labels config, and branch-protection config.
  2. Returns a tuple of Finding objects (empty if no drift detected).
  3. May perform IO (API calls, filesystem reads) — mocks happen at the
     subprocess / module-attribute boundary in tests.

Report formatters (format_*_report) are pure functions that take a
tuple of Finding objects and return a string. Destination (stdout vs
file) is decided by the CLI layer in commands/drift.py.

Section map:
  ========== Data Model ==========
  ========== Error Hierarchy ==========
  ========== Check Registry ==========
  ========== Adapters ==========
  ========== Checks ==========
  ========== Report Formatters ==========
"""

from __future__ import annotations

import hashlib
import json as _json
import re as _re
from datetime import datetime, timedelta
from importlib.resources import files as _package_files
from pathlib import Path
from typing import Any


# ========== Data Model (moved to findings.py in cli/v1.2.0) ==========

from gh_manage.findings import Finding, Severity  # noqa: F401

# ScanContext + drift errors moved to drift_sync.context in cli/v1.7.0.
from gh_manage.drift_sync.context import (  # noqa: F401
    DriftError,
    DriftOutputError,
    ScanContext,
)


# ========== Check Registry (moved to drift_sync.registry in cli/v1.7.0) ==========

from gh_manage.drift_sync.registry import (  # noqa: E402, F401
    _CHECKS,
    CheckFn,
    _filter_by_severity,
    register_check,
    run_all_checks,
)


# ========== Adapters ==========

from gh_manage.github_api import issues as issues_api  # noqa: E402
from gh_manage.github_api import labels as labels_api  # noqa: E402
from gh_manage.labels_sync import (  # noqa: E402
    LabelsDiff,
    compute_diff as _compute_labels_diff,
)


def _labels_diff_to_findings(diff: LabelsDiff, repo: str) -> tuple[Finding, ...]:
    """Convert a LabelsDiff into a tuple of Finding objects.

    Severity mapping:
    - creates (profile has, repo missing)     → high
    - deletes (repo has, profile missing)     → low (user may have added intentionally)
    - updates (color/description mismatch)    → medium
    - renames (label rename in profile)       → medium
    """
    findings: list[Finding] = []
    remediation = "gh manage labels sync . --apply"

    for create in diff.creates:
        findings.append(
            Finding(
                severity="high",
                check="labels",
                repo=repo,
                field_path=f"labels[{create.label.name}]",
                current_value=None,
                desired_value=create.label.name,
                message=f"Label {create.label.name!r} is missing from the repository",
                remediation=remediation,
            )
        )
    for delete in diff.deletes:
        findings.append(
            Finding(
                severity="low",
                check="labels",
                repo=repo,
                field_path=f"labels[{delete.name}]",
                current_value=delete.name,
                desired_value=None,
                message=(
                    f"Label {delete.name!r} exists on the repository but is "
                    f"not defined in labels.yml"
                ),
                remediation=None,
            )
        )
    for update in diff.updates:
        findings.append(
            Finding(
                severity="medium",
                check="labels",
                repo=repo,
                field_path=f"labels[{update.label.name}]",
                current_value="drifted",
                desired_value=f"color={update.label.color}",
                message=(
                    f"Label {update.label.name!r} has drifted (color or "
                    f"description mismatch)"
                ),
                remediation=remediation,
            )
        )
    for rename in diff.renames:
        findings.append(
            Finding(
                severity="medium",
                check="labels",
                repo=repo,
                field_path=f"labels[{rename.old_name}]",
                current_value=rename.old_name,
                desired_value=rename.new_label.name,
                message=(
                    f"Label {rename.old_name!r} should be renamed to "
                    f"{rename.new_label.name!r}"
                ),
                remediation=remediation,
            )
        )
    return tuple(findings)


from gh_manage.github_api import protection as protection_api  # noqa: E402
from gh_manage.github_client import GhNotFoundError  # noqa: E402
from gh_manage.protection_sync import (  # noqa: E402
    ProtectionDiff,
    compute_protection_diff,
)


def _protection_diff_to_findings(
    diff: ProtectionDiff, repo: str
) -> tuple[Finding, ...]:
    """Convert a ProtectionDiff into a tuple of Finding objects.

    Severity mapping:
    - downgrade (field in diff.downgrades)      → critical
    - non-downgrade change (e.g., upgrade side) → medium

    A change is a downgrade if its `field_path` appears in
    `diff.downgrades`. All other changes are medium severity.
    """
    downgrade_paths = {d.field_path for d in diff.downgrades}
    remediation = "gh manage protection sync . --profile <profile> --apply"

    findings: list[Finding] = []
    for change in diff.changes:
        is_downgrade = change.field_path in downgrade_paths
        severity: Severity = "critical" if is_downgrade else "medium"

        if is_downgrade:
            downgrade_entry = next(
                d for d in diff.downgrades if d.field_path == change.field_path
            )
            message = (
                f"Protection weakened on {change.field_path}: {downgrade_entry.reason}"
            )
        else:
            message = f"Protection drift on {change.field_path}"

        findings.append(
            Finding(
                severity=severity,
                check="protection",
                repo=repo,
                field_path=change.field_path,
                current_value=change.current_value,
                desired_value=change.desired_value,
                message=message,
                remediation=remediation,
            )
        )
    return tuple(findings)


# ========== Checks ==========


@register_check
def check_labels(ctx: ScanContext) -> tuple[Finding, ...]:
    """Drift check: repo labels vs ctx.labels_config.

    Calls labels_api.list_labels(ctx.repo) to fetch the current state,
    then reuses labels_sync.compute_diff() (with prune=True) and translates
    the resulting LabelsDiff into Finding objects.

    IO: yes (subprocess via labels_api.list_labels). Mocked at the
    module-attribute boundary (gh_manage.drift_sync.labels_api.list_labels)
    in scenario tests.

    `prune=True` is used here — drift scan should report extras so the user
    can see extras, and the adapter marks them low-severity with no
    remediation command.
    """
    current = labels_api.list_labels(ctx.repo)
    diff = _compute_labels_diff(current, ctx.labels_config, prune=True)
    return _labels_diff_to_findings(diff, ctx.repo)


@register_check
def check_protection(ctx: ScanContext) -> tuple[Finding, ...]:
    """Drift check: current branch protection vs profile's policy.

    Returns early with an empty tuple if:
    - ctx.profile.protection_policy is None (opt-out — profile does
      not manage protection)
    - ctx.bp_config is None (CLI builder did not load branch-protection.yml)

    Otherwise:
    1. Look up the policy in ctx.bp_config.policies by name.
    2. Fetch current protection via protection_api.get_branch_protection
       on ctx.default_branch. 404 → treat as empty dict.
    3. Compute diff via protection_sync.compute_protection_diff.
    4. Pass the diff through _protection_diff_to_findings.

    IO: yes (subprocess via protection_api). Mocked at
    gh_manage.drift_sync.protection_api.get_branch_protection in
    scenario tests.
    """
    if ctx.profile.protection_policy is None or ctx.bp_config is None:
        return ()

    policy = ctx.bp_config.policies[ctx.profile.protection_policy]
    try:
        current = protection_api.get_branch_protection(ctx.repo, ctx.default_branch)
    except GhNotFoundError:
        current = {}

    diff = compute_protection_diff(current, policy, ctx.profile, ctx.default_branch)
    return _protection_diff_to_findings(diff, ctx.repo)


def _read_template_content(source: str) -> str:
    """Read a template file from the bundled gh_manage.data.templates
    package data. `source` is relative path like "ci/python-ci.yml".

    Raises DriftError with actionable context if the template file is
    missing or unreadable (silent-failure-hunter HIGH #1 fix).
    """
    templates_root = Path(str(_package_files("gh_manage.data") / "templates"))
    template_path = templates_root / source
    try:
        return template_path.read_text(encoding="utf-8")
    except OSError as e:
        raise DriftError(
            f"Cannot read bundled template {source!r} at {template_path}: {e}. "
            f"This may indicate a packaging bug — the template should be "
            f"bundled in gh_manage.data.templates."
        ) from e


def _content_hash(text: str) -> str:
    """Compute SHA256 hex digest of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@register_check
def check_profile_files(ctx: ScanContext) -> tuple[Finding, ...]:
    """Drift check: local repo files vs profile's template files.

    For each entry in ctx.profile.files:
    - Read the template content from gh_manage.data.templates/<source>.
    - Check if ctx.path / entry.dest exists.
      - Missing + skip_if_exists=False → severity=medium, "missing file"
      - Missing + skip_if_exists=True  → no finding (user opted out)
    - Compare content hashes:
      - Match → no finding
      - Mismatch + skip_if_exists=False → severity=medium, "content drifted"
      - Mismatch + skip_if_exists=True  → severity=low, "content drifted" (informational)

    IO: yes (filesystem reads). Tests inject scenario state via tmp_path
    in the conftest `drift_scenario` fixture.
    """
    findings: list[Finding] = []
    remediation_apply = f"gh manage apply . --profile {ctx.profile.name} --apply"

    for entry in ctx.profile.files:
        local = ctx.path / entry.dest
        template_content = _read_template_content(entry.source)
        template_hash = _content_hash(template_content)

        if not local.exists():
            if entry.skip_if_exists:
                continue
            findings.append(
                Finding(
                    severity="medium",
                    check="profile_files",
                    repo=ctx.repo,
                    field_path=entry.dest,
                    current_value=None,
                    desired_value=f"<template {entry.source}>",
                    message=(
                        f"Profile file {entry.dest!r} is missing from the "
                        f"repository (template: {entry.source!r})"
                    ),
                    remediation=remediation_apply,
                )
            )
            continue

        try:
            local_content = local.read_text(encoding="utf-8")
        except OSError as e:
            raise DriftError(
                f"Cannot read {entry.dest!r} at {local}: {e}. Check file permissions."
            ) from e
        local_hash = _content_hash(local_content)
        if local_hash == template_hash:
            continue

        # Content mismatch
        severity: Severity = "low" if entry.skip_if_exists else "medium"
        findings.append(
            Finding(
                severity=severity,
                check="profile_files",
                repo=ctx.repo,
                field_path=entry.dest,
                current_value=f"hash={local_hash[:12]}",
                desired_value=f"hash={template_hash[:12]}",
                message=(
                    f"Profile file {entry.dest!r} has drifted from the "
                    f"template {entry.source!r}"
                    + (" (user-editable)" if entry.skip_if_exists else "")
                ),
                remediation=remediation_apply if not entry.skip_if_exists else None,
            )
        )
    return tuple(findings)


# ========== Report Formatters ==========


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


# Side-effect import: doctor.bridge.check_shape registers with drift's
# registry on module load. Spec §4.
from gh_manage.doctor import bridge as _doctor_bridge  # noqa: F401, E402
