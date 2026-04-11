"""Tests for normalize_protection_response — canonical shape transformation."""

from __future__ import annotations

from gh_manage.protection_sync import normalize_protection_response


# Empty dict → all weakest defaults
def test_normalize_empty_dict() -> None:
    result = normalize_protection_response({})
    assert result == {
        "required_status_checks": None,
        "required_pull_request_reviews": None,
        "enforce_admins": False,
        "required_conversation_resolution": False,
        "required_linear_history": False,
        "allow_force_pushes": True,  # weakest
        "allow_deletions": True,  # weakest
    }


# enforce_admins wrapper unwrap
def test_normalize_enforce_admins_wrapper_enabled() -> None:
    raw = {"enforce_admins": {"enabled": True, "url": "https://api.github.com/..."}}
    result = normalize_protection_response(raw)
    assert result["enforce_admins"] is True


def test_normalize_enforce_admins_wrapper_disabled() -> None:
    raw = {"enforce_admins": {"enabled": False, "url": "https://api.github.com/..."}}
    result = normalize_protection_response(raw)
    assert result["enforce_admins"] is False


# allow_force_pushes / allow_deletions wrappers
def test_normalize_allow_force_pushes_wrapper() -> None:
    raw = {"allow_force_pushes": {"enabled": True}}
    result = normalize_protection_response(raw)
    assert result["allow_force_pushes"] is True


def test_normalize_allow_deletions_wrapper() -> None:
    raw = {"allow_deletions": {"enabled": False}}
    result = normalize_protection_response(raw)
    assert result["allow_deletions"] is False


def test_normalize_missing_allow_force_pushes_defaults_weakest() -> None:
    """Missing key means GitHub didn't include it — default to weakest
    state (force push allowed)."""
    raw = {"enforce_admins": {"enabled": True}}
    result = normalize_protection_response(raw)
    assert result["allow_force_pushes"] is True
    assert result["allow_deletions"] is True


# required_status_checks — drop extras
def test_normalize_required_status_checks_extracts_strict_and_contexts() -> None:
    raw = {
        "required_status_checks": {
            "strict": True,
            "contexts": ["pr-gate / test"],
            "checks": [{"context": "pr-gate / test", "app_id": -1}],  # extras dropped
        }
    }
    result = normalize_protection_response(raw)
    assert result["required_status_checks"] == {
        "strict": True,
        "contexts": ["pr-gate / test"],
    }


def test_normalize_required_status_checks_missing_becomes_none() -> None:
    raw = {"enforce_admins": {"enabled": False}}
    result = normalize_protection_response(raw)
    assert result["required_status_checks"] is None


# required_pull_request_reviews — drop extras
def test_normalize_review_requirements_extracts_3_fields() -> None:
    raw = {
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
            "required_review_thread_resolution": True,  # dropped
            "dismissal_restrictions": {},  # dropped
        }
    }
    result = normalize_protection_response(raw)
    assert result["required_pull_request_reviews"] == {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": False,
    }


def test_normalize_review_requirements_missing_becomes_none() -> None:
    raw = {"enforce_admins": {"enabled": False}}
    result = normalize_protection_response(raw)
    assert result["required_pull_request_reviews"] is None


# conversation resolution + linear history top-level booleans
def test_normalize_required_conversation_resolution_true() -> None:
    raw = {"required_conversation_resolution": {"enabled": True}}
    result = normalize_protection_response(raw)
    assert result["required_conversation_resolution"] is True


def test_normalize_required_linear_history_wrapper() -> None:
    raw = {"required_linear_history": {"enabled": True}}
    result = normalize_protection_response(raw)
    assert result["required_linear_history"] is True
