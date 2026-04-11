"""Tests for gh_manage.models.branch_protection — PolicySpec + BranchProtectionConfig."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from gh_manage.models.branch_protection import (
    BranchProtectionConfig,
    PolicySpec,
    RequiredPullRequestReviews,
    RequiredStatusChecks,
)


# RequiredStatusChecks
def test_required_status_checks_minimal() -> None:
    s = RequiredStatusChecks(strict=True)
    assert s.strict is True
    assert s.contexts == []


def test_required_status_checks_with_contexts() -> None:
    s = RequiredStatusChecks(strict=False, contexts=["pr-gate / test"])
    assert s.strict is False
    assert s.contexts == ["pr-gate / test"]


def test_required_status_checks_rejects_extra() -> None:
    with pytest.raises(ValidationError):
        RequiredStatusChecks(strict=True, unknown_field="x")  # type: ignore[call-arg]


# RequiredPullRequestReviews
def test_required_pull_request_reviews_minimal() -> None:
    r = RequiredPullRequestReviews(required_approving_review_count=0)
    assert r.required_approving_review_count == 0
    assert r.dismiss_stale_reviews is False
    assert r.require_code_owner_reviews is False


def test_required_pull_request_reviews_rejects_negative_count() -> None:
    with pytest.raises(ValidationError):
        RequiredPullRequestReviews(required_approving_review_count=-1)


def test_required_pull_request_reviews_rejects_over_six() -> None:
    with pytest.raises(ValidationError):
        RequiredPullRequestReviews(required_approving_review_count=7)


# PolicySpec
def _minimal_policy_kwargs() -> dict:
    return dict(
        description="test",
        target_branches=["main"],
        required_status_checks=RequiredStatusChecks(strict=True),
        enforce_admins=False,
        required_pull_request_reviews=RequiredPullRequestReviews(
            required_approving_review_count=0
        ),
        required_conversation_resolution=True,
        required_linear_history=True,
        allow_force_pushes=False,
        allow_deletions=False,
    )


def test_policy_spec_minimal_valid() -> None:
    p = PolicySpec(**_minimal_policy_kwargs())
    assert p.description == "test"
    assert p.target_branches == ["main"]


def test_policy_spec_null_status_checks_is_valid() -> None:
    """docs-only-style policy with no status checks."""
    kwargs = _minimal_policy_kwargs()
    kwargs["required_status_checks"] = None
    p = PolicySpec(**kwargs)
    assert p.required_status_checks is None


def test_policy_spec_null_review_requirements_is_valid() -> None:
    kwargs = _minimal_policy_kwargs()
    kwargs["required_pull_request_reviews"] = None
    p = PolicySpec(**kwargs)
    assert p.required_pull_request_reviews is None


def test_policy_spec_rejects_empty_target_branches() -> None:
    kwargs = _minimal_policy_kwargs()
    kwargs["target_branches"] = []
    with pytest.raises(ValidationError, match="at least one branch"):
        PolicySpec(**kwargs)


def test_policy_spec_rejects_extra_field() -> None:
    kwargs = _minimal_policy_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        PolicySpec(**kwargs)


# BranchProtectionConfig
def test_branch_protection_config_minimal() -> None:
    policy = PolicySpec(**_minimal_policy_kwargs())
    config = BranchProtectionConfig(version=1, policies={"solo-default": policy})
    assert config.version == 1
    assert "solo-default" in config.policies


def test_branch_protection_config_multiple_policies() -> None:
    policy1 = PolicySpec(**_minimal_policy_kwargs())
    kwargs2 = _minimal_policy_kwargs()
    kwargs2["description"] = "second"
    policy2 = PolicySpec(**kwargs2)
    config = BranchProtectionConfig(version=1, policies={"a": policy1, "b": policy2})
    assert len(config.policies) == 2


def test_branch_protection_config_rejects_unknown_version() -> None:
    policy = PolicySpec(**_minimal_policy_kwargs())
    with pytest.raises(ValidationError):
        BranchProtectionConfig(version=2, policies={"x": policy})  # type: ignore[arg-type]
