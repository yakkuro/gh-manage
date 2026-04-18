"""Diff → Finding adapters.

Pure functions that convert labels_sync / protection_sync diff objects
into Finding tuples. Stateless, no I/O. Layer 3 in the DAG.
"""

from __future__ import annotations

from gh_manage.findings import Finding, Severity
from gh_manage.labels_sync import LabelsDiff
from gh_manage.protection_sync import ProtectionDiff


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
