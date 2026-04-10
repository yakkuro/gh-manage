"""Tests for gh_manage.repo_ref.parse_repo.

NOTE: parse_repo intentionally does NOT validate GitHub's owner/repo
naming rules. Codex's review of the Phase 5 checkpoint refactor flagged
a regex-based validator as a behavior regression: it rejected valid
names like `.github` (a well-known GitHub repo) while accepting invalid
owner forms like `user_name` (usernames cannot contain underscores) and
`foo--bar` (no consecutive hyphens). We now delegate naming validation
to the `gh` CLI, which has authoritative rules and actionable errors.
These tests only cover the normalization contract:
  - `/` present → pass through unchanged
  - `/` absent → prepend DEFAULT_OWNER
"""

from __future__ import annotations

import pytest

from gh_manage.repo_ref import DEFAULT_OWNER, parse_repo


# Happy path — bare name prepends DEFAULT_OWNER
@pytest.mark.parametrize(
    "bare",
    ["gh-manage", "port-registry", "llm-kb", "abc123", "a", ".github"],
)
def test_bare_name_prepends_default_owner(bare: str) -> None:
    assert parse_repo(bare) == f"{DEFAULT_OWNER}/{bare}"


# Happy path — anything with `/` passes through unchanged
@pytest.mark.parametrize(
    "qualified",
    [
        "yakkuro/gh-manage",
        "other-org/other-repo",
        "foo/bar",
        "A/B",
        "github/.github",  # well-known special repo starting with dot
    ],
)
def test_owner_slash_repo_passes_through(qualified: str) -> None:
    assert parse_repo(qualified) == qualified


def test_slash_only_is_passed_through_to_gh() -> None:
    """Edge case: a raw `/` has no bare form to normalize, so it passes
    through unchanged. `gh` will reject it with a classified GhError."""
    assert parse_repo("/") == "/"
