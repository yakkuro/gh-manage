"""Drift bridge: one drift-registered check that delegates to doctor
and converts DoctorCheckError to a shape/check-error finding.

Spec §4."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def _fake_scan_ctx():
    """Minimal ScanContext-shaped stub."""

    class _FakeProfile:
        name = "python-service"
        required_contexts = ()

    class _FakeCtx:
        repo = "yakkuro/example"
        path = Path("/tmp/nonexistent")
        default_branch = "main"
        profile = _FakeProfile()
        labels_config = None
        bp_config = None
        live_required_contexts = ()
        live_required_contexts_readable = True

    return _FakeCtx()


def test_drift_bridge_delegates_to_doctor_run_checks():
    from gh_manage.doctor.bridge import check_shape
    from gh_manage.findings import Finding

    fake_finding = Finding(
        severity="medium",
        check="shape/job-shape-coherence",
        repo="yakkuro/example",
        field_path="x",
        current_value=None,
        desired_value=None,
        message="m",
    )

    with patch(
        "gh_manage.doctor.bridge.doctor_run_checks", return_value=(fake_finding,)
    ):
        findings = check_shape(_fake_scan_ctx())

    assert len(findings) == 1
    assert findings[0].check == "shape/job-shape-coherence"


def test_drift_bridge_converts_doctor_check_error_to_finding():
    from gh_manage.doctor.bridge import check_shape
    from gh_manage.doctor.errors import DoctorCheckError

    with patch(
        "gh_manage.doctor.bridge.doctor_run_checks",
        side_effect=DoctorCheckError("ci.yml malformed"),
    ):
        findings = check_shape(_fake_scan_ctx())

    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert findings[0].check == "shape/check-error"
    assert "malformed" in findings[0].message
