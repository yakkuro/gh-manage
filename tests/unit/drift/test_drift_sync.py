"""Tests for gh_manage.drift_sync — drift scanner engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from gh_manage.drift_sync import (
    DriftError,
    DriftOutputError,
    Finding,
    ScanContext,
    _CHECKS,
    register_check,
    run_all_checks,
)
from gh_manage.models.labels import CategorySpec, LabelSpec, LabelsConfig
from gh_manage.models.profiles import ProfileSpec


def _make_labels_config() -> LabelsConfig:
    """Helper: create a valid minimal LabelsConfig for tests."""
    return LabelsConfig(
        version=1,
        categories={
            "priority": CategorySpec(
                description="Priority levels",
                labels=[LabelSpec(name="critical", color="ff0000")],
            )
        },
    )


# Data classes
def test_finding_is_frozen() -> None:
    f = Finding(
        severity="high",
        check="labels",
        repo="yakkuro/gh-manage",
        field_path="labels[priority/critical]",
        current_value=None,
        desired_value="priority/critical",
        message="Missing label",
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        f.severity = "low"  # type: ignore[misc]


def test_finding_has_remediation_default_none() -> None:
    f = Finding(
        severity="high",
        check="labels",
        repo="yakkuro/gh-manage",
        field_path="labels[x]",
        current_value=None,
        desired_value="x",
        message="m",
    )
    assert f.remediation is None


def test_finding_accepts_remediation_string() -> None:
    f = Finding(
        severity="high",
        check="labels",
        repo="yakkuro/gh-manage",
        field_path="labels[x]",
        current_value=None,
        desired_value="x",
        message="m",
        remediation="gh manage labels sync . --apply",
    )
    assert f.remediation == "gh manage labels sync . --apply"


def test_finding_equality_and_hashability() -> None:
    f1 = Finding("high", "labels", "yakkuro/gh-manage", "x", None, "y", "m")
    f2 = Finding("high", "labels", "yakkuro/gh-manage", "x", None, "y", "m")
    assert f1 == f2
    assert hash(f1) == hash(f2)


def test_scan_context_is_frozen(tmp_path: Path) -> None:
    profile = ProfileSpec(version=1, name="test", files=[])
    labels_config = _make_labels_config()
    ctx = ScanContext(
        path=tmp_path,
        repo="yakkuro/gh-manage",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=None,
    )
    with pytest.raises(Exception):
        ctx.repo = "other"  # type: ignore[misc]


# Error hierarchy
def test_all_errors_inherit_drift_error() -> None:
    assert issubclass(DriftOutputError, DriftError)


def test_drift_output_error_message_includes_context() -> None:
    err = DriftOutputError("Cannot write to /tmp/x: Permission denied")
    assert "Cannot write" in str(err)


# Registry
def test_register_check_appends_to_global_list() -> None:
    initial_count = len(_CHECKS)

    def my_check(ctx: ScanContext) -> tuple[Finding, ...]:
        return ()

    register_check(my_check)
    assert my_check in _CHECKS
    _CHECKS.remove(my_check)
    assert len(_CHECKS) == initial_count


def test_register_check_returns_function(tmp_path: Path) -> None:
    def my_check(ctx: ScanContext) -> tuple[Finding, ...]:
        return ()

    result = register_check(my_check)
    assert result is my_check
    _CHECKS.remove(my_check)


def test_run_all_checks_calls_every_registered_check(tmp_path: Path) -> None:
    called: list[str] = []

    def check_a(ctx: ScanContext) -> tuple[Finding, ...]:
        called.append("a")
        return ()

    def check_b(ctx: ScanContext) -> tuple[Finding, ...]:
        called.append("b")
        return (Finding("low", "test", ctx.repo, "x", None, "y", "m"),)

    register_check(check_a)
    register_check(check_b)

    try:
        profile = ProfileSpec(version=1, name="test", files=[])
        labels_config = _make_labels_config()
        ctx = ScanContext(
            path=tmp_path,
            repo="yakkuro/gh-manage",
            default_branch="main",
            profile=profile,
            labels_config=labels_config,
            bp_config=None,
        )
        findings = run_all_checks(ctx)
        assert "a" in called
        assert "b" in called
        assert any(f.check == "test" for f in findings)
    finally:
        _CHECKS.remove(check_a)
        _CHECKS.remove(check_b)
