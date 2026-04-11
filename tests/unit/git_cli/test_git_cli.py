"""Tests for gh_manage.git_cli — local git CLI subprocess transport.

Mirrors tests/unit/github_client/test_github_client.py — subprocess.run
is mocked to return controlled CompletedProcess instances.
"""

from __future__ import annotations

import pytest

from gh_manage.git_cli import parse_origin_url


# parse_origin_url — happy paths
@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("git@github.com:yakkuro/gh-manage.git", "yakkuro/gh-manage"),
        ("git@github.com:yakkuro/gh-manage", "yakkuro/gh-manage"),
        ("https://github.com/yakkuro/gh-manage.git", "yakkuro/gh-manage"),
        ("https://github.com/yakkuro/gh-manage", "yakkuro/gh-manage"),
        ("https://github.com/some-org/multi.dot.repo", "some-org/multi.dot.repo"),
    ],
)
def test_parse_origin_url_happy_paths(url: str, expected: str) -> None:
    assert parse_origin_url(url) == expected


# parse_origin_url — unsupported origins
def test_parse_origin_url_rejects_gitlab() -> None:
    with pytest.raises(ValueError, match="github.com"):
        parse_origin_url("git@gitlab.com:yakkuro/foo.git")


def test_parse_origin_url_rejects_bitbucket() -> None:
    with pytest.raises(ValueError, match="github.com"):
        parse_origin_url("https://bitbucket.org/yakkuro/foo.git")


def test_parse_origin_url_rejects_self_hosted_https() -> None:
    with pytest.raises(ValueError, match="github.com"):
        parse_origin_url("https://git.internal.example.com/owner/repo.git")


def test_parse_origin_url_rejects_malformed() -> None:
    with pytest.raises(ValueError):
        parse_origin_url("not-a-url-at-all")


def test_parse_origin_url_error_message_includes_offending_url() -> None:
    with pytest.raises(ValueError, match="gitlab.com"):
        parse_origin_url("git@gitlab.com:foo/bar.git")
