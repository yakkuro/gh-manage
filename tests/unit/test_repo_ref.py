"""Tests for gh_manage.repo_ref.parse_repo."""

from __future__ import annotations

import pytest

from gh_manage.repo_ref import DEFAULT_OWNER, InvalidRepoRefError, parse_repo


# Happy path — bare name
@pytest.mark.parametrize(
    "bare",
    ["gh-manage", "port-registry", "llm-kb", "abc123", "a"],
)
def test_bare_name_prepends_default_owner(bare: str) -> None:
    assert parse_repo(bare) == f"{DEFAULT_OWNER}/{bare}"


# Happy path — fully qualified
@pytest.mark.parametrize(
    "qualified",
    [
        "yakkuro/gh-manage",
        "other-org/other-repo",
        "foo/bar",
        "A/B",
        "user_name/repo.name",
    ],
)
def test_owner_slash_repo_passes_through(qualified: str) -> None:
    assert parse_repo(qualified) == qualified


# Validation rejects invalid input
@pytest.mark.parametrize(
    "invalid",
    [
        "",  # empty
        "/foo",  # leading slash
        "foo/",  # trailing slash
        "foo/bar/baz",  # too many segments
        ".hidden",  # starts with dot
        "-dash",  # starts with dash
        "foo/.hidden",  # second segment starts with dot
        "foo/-dash",  # second segment starts with dash
        "foo bar",  # contains space
        "foo@bar",  # contains @
        "a b/c",  # space in first segment
    ],
)
def test_invalid_repo_ref_raises_invalid_repo_ref_error(invalid: str) -> None:
    with pytest.raises(InvalidRepoRefError, match="Invalid repo reference"):
        parse_repo(invalid)


def test_invalid_repo_ref_is_a_value_error_subclass() -> None:
    """Callers that catch ValueError should also catch InvalidRepoRefError."""
    with pytest.raises(ValueError):
        parse_repo("bad spaces")


def test_error_message_includes_the_bad_input() -> None:
    """Actionable error — the user needs to see what they typed."""
    with pytest.raises(InvalidRepoRefError, match=r"totally bad"):
        parse_repo("totally bad")


def test_error_message_mentions_owner_repo_format() -> None:
    """Actionable error — tell the user what's expected."""
    with pytest.raises(InvalidRepoRefError, match="owner/repo"):
        parse_repo("bad@ref")
