"""Finding/Severity moved out of drift_sync.py (spec §1 extraction)."""

from __future__ import annotations

import pytest


def test_finding_importable_from_findings_module():
    from gh_manage.findings import Finding

    f = Finding(
        severity="high",
        check="shape/test",
        repo="owner/repo",
        field_path="jobs.x",
        current_value="a",
        desired_value="b",
        message="test",
    )
    assert f.severity == "high"
    assert f.remediation is None
    with pytest.raises((AttributeError, Exception)):
        f.severity = "low"  # type: ignore[misc]


def test_finding_still_importable_from_drift_sync_for_bc():
    from gh_manage.drift_sync import Finding as DriftFinding
    from gh_manage.findings import Finding as SharedFinding

    assert DriftFinding is SharedFinding


def test_severity_literal_values():
    from gh_manage.findings import Severity  # noqa: F401
