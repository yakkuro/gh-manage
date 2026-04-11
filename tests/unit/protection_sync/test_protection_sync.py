"""Tests for gh_manage.protection_sync — pure-function engine."""

from __future__ import annotations

import pytest

from gh_manage.protection_sync import (
    DowngradeFinding,
    ProtectionApplyError,
    ProtectionBackupError,
    ProtectionDiff,
    ProtectionDowngradeError,
    ProtectionError,
    ProtectionFieldChange,
    ProtectionPolicyNotFoundError,
)


# Data classes
def test_protection_field_change_is_frozen() -> None:
    c = ProtectionFieldChange(
        field_path="enforce_admins",
        current_value=False,
        desired_value=True,
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        c.field_path = "other"  # type: ignore[misc]


def test_downgrade_finding_holds_all_fields() -> None:
    d = DowngradeFinding(
        field_path="enforce_admins",
        current_value=True,
        desired_value=False,
        reason="admin enforcement disabled",
    )
    assert d.field_path == "enforce_admins"
    assert d.reason == "admin enforcement disabled"


def test_protection_diff_is_empty_when_no_changes() -> None:
    diff = ProtectionDiff(
        changes=(),
        downgrades=(),
        current_raw={},
        desired_raw={},
    )
    assert diff.is_empty
    assert not diff.has_downgrades


def test_protection_diff_is_not_empty_when_has_changes() -> None:
    change = ProtectionFieldChange("x", False, True)
    diff = ProtectionDiff(
        changes=(change,),
        downgrades=(),
        current_raw={},
        desired_raw={},
    )
    assert not diff.is_empty


def test_protection_diff_has_downgrades_when_set() -> None:
    d = DowngradeFinding("x", True, False, "weakened")
    diff = ProtectionDiff(
        changes=(ProtectionFieldChange("x", True, False),),
        downgrades=(d,),
        current_raw={},
        desired_raw={},
    )
    assert diff.has_downgrades
    assert not diff.is_empty


# Error hierarchy
def test_all_errors_inherit_protection_error() -> None:
    assert issubclass(ProtectionPolicyNotFoundError, ProtectionError)
    assert issubclass(ProtectionDowngradeError, ProtectionError)
    assert issubclass(ProtectionBackupError, ProtectionError)
    assert issubclass(ProtectionApplyError, ProtectionError)


def test_protection_downgrade_error_message_lists_findings() -> None:
    d1 = DowngradeFinding("enforce_admins", True, False, "admin weakened")
    d2 = DowngradeFinding("allow_force_pushes", False, True, "force push allowed")
    err = ProtectionDowngradeError((d1, d2))
    msg = str(err)
    assert "2 protection field" in msg
    assert "enforce_admins" in msg
    assert "allow_force_pushes" in msg
    assert "--downgrade-allowed" in msg


def test_protection_downgrade_error_single_finding() -> None:
    d = DowngradeFinding("x", True, False, "weakened")
    err = ProtectionDowngradeError((d,))
    assert "1 protection field" in str(err)
