"""Codex review HIGH #2: bridge catches DoctorError (broader than just
DoctorCheckError) and OSError so malformed ci.yml / permission denied
in ONE repo doesn't abort a multi-repo drift --all scan. Spec §4."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def _fake_scan_ctx():
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

    return _FakeCtx()


def test_bridge_catches_ci_yml_parse_error_as_medium_finding():
    # CiYmlParseError is DoctorError but NOT DoctorCheckError. Bridge
    # must still catch it so one broken ci.yml doesn't abort --all.
    from gh_manage.doctor.bridge import check_shape
    from gh_manage.doctor.errors import CiYmlParseError

    with patch(
        "gh_manage.doctor.bridge.doctor_run_checks",
        side_effect=CiYmlParseError("malformed YAML"),
    ):
        findings = check_shape(_fake_scan_ctx())

    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert findings[0].check == "shape/check-error"
    assert "malformed YAML" in findings[0].message


def test_bridge_catches_os_error_as_medium_finding():
    # PermissionError / IsADirectoryError from ci.yml read path should
    # also not abort the scan.
    from gh_manage.doctor.bridge import check_shape

    with patch(
        "gh_manage.doctor.bridge.doctor_run_checks",
        side_effect=PermissionError("permission denied"),
    ):
        findings = check_shape(_fake_scan_ctx())

    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert findings[0].check == "shape/check-error"
    assert "PermissionError" in findings[0].message


def test_bridge_does_not_catch_unexpected_non_doctor_non_os_errors():
    # Per spec §4: "genuine bugs" (e.g., TypeError, ValueError from
    # our own code, not a doctor error) should propagate for a clear
    # traceback. This assertion is deliberate regression protection.
    import pytest

    from gh_manage.doctor.bridge import check_shape

    with patch(
        "gh_manage.doctor.bridge.doctor_run_checks",
        side_effect=TypeError("doctor bug"),
    ):
        with pytest.raises(TypeError):
            check_shape(_fake_scan_ctx())
