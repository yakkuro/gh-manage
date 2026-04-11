"""Tests for gh_manage.protection_sync — pure-function engine."""

from __future__ import annotations

from typing import Any

import pytest

from gh_manage.models.branch_protection import (
    PolicySpec,
    RequiredPullRequestReviews,
    RequiredStatusChecks,
)
from gh_manage.models.profiles import ProfileSpec
from gh_manage.protection_sync import (
    DowngradeFinding,
    ProtectionApplyError,
    ProtectionBackupError,
    ProtectionDiff,
    ProtectionDowngradeError,
    ProtectionError,
    ProtectionFieldChange,
    ProtectionPolicyNotFoundError,
    build_desired_protection,
    compute_protection_diff,
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


# Helpers for build_desired_protection and compute_protection_diff tests
def _make_policy(**overrides: Any) -> PolicySpec:
    defaults: dict[str, Any] = dict(
        description="test",
        target_branches=["main"],
        required_status_checks=RequiredStatusChecks(strict=True, contexts=[]),
        enforce_admins=False,
        required_pull_request_reviews=RequiredPullRequestReviews(
            required_approving_review_count=0
        ),
        required_conversation_resolution=True,
        required_linear_history=True,
        allow_force_pushes=False,
        allow_deletions=False,
    )
    defaults.update(overrides)
    return PolicySpec(**defaults)


def _make_profile(
    protection_policy: str | None = "solo-default",
    required_contexts: list[str] | None = None,
) -> ProfileSpec:
    return ProfileSpec(
        version=1,
        name="test",
        files=[],
        protection_policy=protection_policy,
        required_contexts=required_contexts or [],
    )


# build_desired_protection
def test_build_desired_uses_policy_fields() -> None:
    policy = _make_policy()
    profile = _make_profile(required_contexts=[])
    body = build_desired_protection(policy, profile)
    assert body["enforce_admins"] is False
    assert body["required_status_checks"]["strict"] is True
    assert body["required_linear_history"] is True


def test_build_desired_contexts_from_profile_override() -> None:
    """LOAD-BEARING: policy.contexts [] is overwritten by profile.required_contexts."""
    policy = _make_policy()
    profile = _make_profile(required_contexts=["pr-gate / test"])
    body = build_desired_protection(policy, profile)
    assert body["required_status_checks"]["contexts"] == ["pr-gate / test"]


def test_build_desired_empty_profile_contexts_means_empty_contexts() -> None:
    policy = _make_policy()
    profile = _make_profile(required_contexts=[])
    body = build_desired_protection(policy, profile)
    assert body["required_status_checks"]["contexts"] == []


def test_build_desired_policy_with_null_status_checks() -> None:
    """A policy with required_status_checks=None → body has null."""
    policy = _make_policy(required_status_checks=None)
    profile = _make_profile()
    body = build_desired_protection(policy, profile)
    assert body["required_status_checks"] is None


# compute_protection_diff
def test_compute_diff_empty_current_all_changes() -> None:
    policy = _make_policy()
    profile = _make_profile()
    diff = compute_protection_diff({}, policy, profile, "main")
    assert not diff.is_empty
    assert len(diff.changes) > 0
    assert not diff.has_downgrades


def test_compute_diff_matching_current_empty() -> None:
    policy = _make_policy()
    profile = _make_profile()
    # Build the current state to match what build_desired would produce
    desired = build_desired_protection(policy, profile)
    # Fake a GitHub API response shape matching the desired state
    current_raw = {
        "enforce_admins": {"enabled": desired["enforce_admins"]},
        "required_status_checks": {
            "strict": desired["required_status_checks"]["strict"],
            "contexts": desired["required_status_checks"]["contexts"],
        },
        "required_pull_request_reviews": desired["required_pull_request_reviews"],
        "required_conversation_resolution": {"enabled": True},
        "required_linear_history": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }
    diff = compute_protection_diff(current_raw, policy, profile, "main")
    assert diff.is_empty


def test_compute_diff_detects_downgrade() -> None:
    policy = _make_policy(enforce_admins=False)  # desired weaker
    profile = _make_profile()
    current_raw = {
        "enforce_admins": {"enabled": True},  # current stronger
    }
    diff = compute_protection_diff(current_raw, policy, profile, "main")
    assert diff.has_downgrades
    assert any("enforce_admins" in d.field_path for d in diff.downgrades)


def test_compute_diff_raw_dicts_preserved() -> None:
    policy = _make_policy()
    profile = _make_profile()
    current_raw = {"enforce_admins": {"enabled": True}}
    diff = compute_protection_diff(current_raw, policy, profile, "main")
    assert diff.current_raw == current_raw
    assert diff.desired_raw  # non-empty
