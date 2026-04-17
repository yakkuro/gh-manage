"""Regression: ensure drift_sync.ScanContext supplies every field that
doctor.CheckContext requires (spec §4 convergent finding)."""

from __future__ import annotations

from dataclasses import fields


def test_scan_context_covers_check_context_required_fields():
    from gh_manage.drift_sync import ScanContext

    scan_fields = {f.name for f in fields(ScanContext)}

    # Each entry asserts a ScanContext attribute exists on which the
    # bridge's CheckContext adapter can rely. If ScanContext changes,
    # this fails loud.
    expected_fields = {
        "repo",  # CheckContext.repo
        "profile",  # source for CheckContext.profile_name
        "live_required_contexts",  # CheckContext.required_contexts
    }
    missing = expected_fields - scan_fields
    assert not missing, (
        f"Doctor bridge expects ScanContext fields {missing}; absent. "
        f"If ScanContext was renamed, update doctor/bridge.py::"
        f"_build_check_context too."
    )
