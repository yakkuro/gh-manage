"""Golden file test for Phase 7: build_desired_protection + compute_protection_diff
roundtrip against production data (solo-default policy + python-service profile).
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from gh_manage.config import load_config
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.profiles import ProfileSpec
from gh_manage.protection_sync import (
    build_desired_protection,
    compute_protection_diff,
)


def test_production_data_loads() -> None:
    """branch-protection.yml and python-service.yml load without validation errors."""
    bp_path = Path(str(files("gh_manage.data") / "branch-protection.yml"))
    bp_config = load_config(bp_path, BranchProtectionConfig)
    assert "solo-default" in bp_config.policies

    profile_path = Path(str(files("gh_manage.data.profiles") / "python-service.yml"))
    profile = load_config(profile_path, ProfileSpec)
    assert profile.protection_policy == "solo-default"
    assert profile.required_contexts == []


def test_build_desired_on_production_solo_default_matches_expected() -> None:
    """build_desired_protection(solo-default, python-service) produces the
    canonical PUT body shape with contexts [] (empty list override)."""
    bp_path = Path(str(files("gh_manage.data") / "branch-protection.yml"))
    bp_config = load_config(bp_path, BranchProtectionConfig)
    profile_path = Path(str(files("gh_manage.data.profiles") / "python-service.yml"))
    profile = load_config(profile_path, ProfileSpec)

    body = build_desired_protection(bp_config.policies["solo-default"], profile)

    assert body == {
        "required_status_checks": {
            "strict": True,
            "contexts": [],  # profile.required_contexts override
        },
        "enforce_admins": False,
        "required_pull_request_reviews": {
            "required_approving_review_count": 0,
            "dismiss_stale_reviews": False,
            "require_code_owner_reviews": False,
        },
        "required_conversation_resolution": True,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "restrictions": None,
    }


def test_compute_diff_empty_current_vs_solo_default_profile() -> None:
    """A fresh repo with no protection → solo-default produces all changes,
    no downgrades."""
    bp_path = Path(str(files("gh_manage.data") / "branch-protection.yml"))
    bp_config = load_config(bp_path, BranchProtectionConfig)
    profile_path = Path(str(files("gh_manage.data.profiles") / "python-service.yml"))
    profile = load_config(profile_path, ProfileSpec)

    diff = compute_protection_diff(
        current={},
        policy=bp_config.policies["solo-default"],
        profile=profile,
        target_branch="main",
    )

    assert not diff.is_empty
    assert not diff.has_downgrades
    # Empty current normalizes to: enforce_admins=False, conversation=False,
    # linear_history=False, force_pushes=True, deletions=True.
    # Desired has: enforce_admins=False (no change), conversation=True (change),
    # linear_history=True (change), force_pushes=False (change), deletions=False (change).
    # Plus required_status_checks (None → {...}) and required_pull_request_reviews (None → {...}).
    field_paths = {c.field_path for c in diff.changes}
    assert "required_conversation_resolution" in field_paths
    assert "required_linear_history" in field_paths
    # force_pushes/deletions: empty-canonical has both=True, desired has both=False
    # → these are changes (upgrades), NOT downgrades
    assert "allow_force_pushes" in field_paths
    assert "allow_deletions" in field_paths
    # required_status_checks and required_pull_request_reviews are added
    assert "required_status_checks" in field_paths
    assert "required_pull_request_reviews" in field_paths
    # enforce_admins should NOT be a change (both False)
    assert "enforce_admins" not in field_paths
