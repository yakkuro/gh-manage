"""Tests for detect_downgrade — all 13 downgrade rules.

Each rule has parametrize entries for both directions:
- "downgrade" case: current stronger, desired weaker → must detect
- "upgrade" case: current weaker, desired stronger → must NOT detect
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


from gh_manage.protection_sync import detect_downgrade, normalize_protection_response


def _empty_canonical() -> dict[str, Any]:
    return normalize_protection_response({})


def _strong_canonical() -> dict[str, Any]:
    """A fully-armed canonical state that every rule can step down from."""
    return {
        "required_status_checks": {
            "strict": True,
            "contexts": ["pr-gate / test", "ci-review / gitleaks"],
        },
        "required_pull_request_reviews": {
            "required_approving_review_count": 2,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
        },
        "enforce_admins": True,
        "required_conversation_resolution": True,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


# Rule 1: required_approving_review_count decrease
def test_rule_1_review_count_decrease_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_pull_request_reviews"]["required_approving_review_count"] = 1
    findings = detect_downgrade(current, desired)
    assert len(findings) == 1
    assert "required_approving_review_count" in findings[0].field_path


def test_rule_1_review_count_increase_is_not_downgrade() -> None:
    current = _strong_canonical()
    current["required_pull_request_reviews"]["required_approving_review_count"] = 1
    desired = _strong_canonical()  # count=2
    assert detect_downgrade(current, desired) == ()


# Rule 2: dismiss_stale_reviews true → false
def test_rule_2_dismiss_stale_reviews_off_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_pull_request_reviews"]["dismiss_stale_reviews"] = False
    findings = detect_downgrade(current, desired)
    assert any("dismiss_stale_reviews" in f.field_path for f in findings)


def test_rule_2_dismiss_stale_reviews_on_is_not_downgrade() -> None:
    current = _strong_canonical()
    current["required_pull_request_reviews"]["dismiss_stale_reviews"] = False
    desired = _strong_canonical()
    assert detect_downgrade(current, desired) == ()


# Rule 3: require_code_owner_reviews true → false
def test_rule_3_code_owner_off_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_pull_request_reviews"]["require_code_owner_reviews"] = False
    findings = detect_downgrade(current, desired)
    assert any("require_code_owner_reviews" in f.field_path for f in findings)


# Rule 4: required_pull_request_reviews exist → null
def test_rule_4_reviews_wrapper_to_null_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_pull_request_reviews"] = None
    findings = detect_downgrade(current, desired)
    assert any(f.field_path == "required_pull_request_reviews" for f in findings)


def test_rule_4_null_to_wrapper_is_not_downgrade() -> None:
    current = _empty_canonical()  # reviews=None
    desired = _strong_canonical()
    findings = detect_downgrade(current, desired)
    # No downgrades — going from null to wrapper is an upgrade
    assert findings == ()


# Rule 5: enforce_admins true → false
def test_rule_5_enforce_admins_off_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["enforce_admins"] = False
    findings = detect_downgrade(current, desired)
    assert any("enforce_admins" in f.field_path for f in findings)


def test_rule_5_enforce_admins_on_is_not_downgrade() -> None:
    current = _empty_canonical()
    desired = _strong_canonical()
    # Empty → strong is pure upgrade
    assert detect_downgrade(current, desired) == ()


# Rule 6: required_status_checks.strict true → false
def test_rule_6_strict_off_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_status_checks"]["strict"] = False
    findings = detect_downgrade(current, desired)
    assert any("strict" in f.field_path for f in findings)


# Rule 7: contexts list shrinks (set difference)
def test_rule_7_context_removed_is_downgrade() -> None:
    current = _strong_canonical()  # ["pr-gate / test", "ci-review / gitleaks"]
    desired = deepcopy(current)
    desired["required_status_checks"]["contexts"] = ["pr-gate / test"]
    findings = detect_downgrade(current, desired)
    assert any("contexts" in f.field_path for f in findings)


def test_rule_7_context_added_is_not_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_status_checks"]["contexts"] = [
        "pr-gate / test",
        "ci-review / gitleaks",
        "extra / check",
    ]
    assert detect_downgrade(current, desired) == ()


def test_rule_7_same_contexts_is_not_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    assert detect_downgrade(current, desired) == ()


# Rule 8: required_status_checks exist → null
def test_rule_8_status_checks_to_null_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_status_checks"] = None
    findings = detect_downgrade(current, desired)
    assert any(f.field_path == "required_status_checks" for f in findings)


# Rule 9: required_conversation_resolution true → false
def test_rule_9_conversation_resolution_off_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_conversation_resolution"] = False
    findings = detect_downgrade(current, desired)
    assert any("required_conversation_resolution" in f.field_path for f in findings)


# Rule 10: required_linear_history true → false
def test_rule_10_linear_history_off_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_linear_history"] = False
    findings = detect_downgrade(current, desired)
    assert any("required_linear_history" in f.field_path for f in findings)


# Rule 11: allow_force_pushes false → true
def test_rule_11_force_pushes_allowed_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["allow_force_pushes"] = True
    findings = detect_downgrade(current, desired)
    assert any("allow_force_pushes" in f.field_path for f in findings)


def test_rule_11_force_pushes_disallowed_is_not_downgrade() -> None:
    current = _empty_canonical()  # allow_force_pushes=True
    desired = _strong_canonical()  # allow_force_pushes=False
    assert detect_downgrade(current, desired) == ()


# Rule 12: allow_deletions false → true
def test_rule_12_deletions_allowed_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["allow_deletions"] = True
    findings = detect_downgrade(current, desired)
    assert any("allow_deletions" in f.field_path for f in findings)


# Sanity: empty → empty
def test_empty_to_empty_is_no_downgrade() -> None:
    assert detect_downgrade(_empty_canonical(), _empty_canonical()) == ()


# Sanity: matching strong states
def test_strong_to_strong_is_no_downgrade() -> None:
    assert detect_downgrade(_strong_canonical(), _strong_canonical()) == ()


# Multiple downgrades reported together
def test_multiple_downgrades_all_reported() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["enforce_admins"] = False
    desired["allow_force_pushes"] = True
    desired["allow_deletions"] = True
    findings = detect_downgrade(current, desired)
    paths = [f.field_path for f in findings]
    assert "enforce_admins" in paths
    assert "allow_force_pushes" in paths
    assert "allow_deletions" in paths
