"""Tests for gh_manage.git_cli — local git CLI subprocess transport.

Mirrors tests/unit/github_client/test_github_client.py — subprocess.run
is mocked to return controlled CompletedProcess instances.
"""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

import pytest
from pytest_mock import MockerFixture

from gh_manage.git_cli import (
    GitError,
    GitNotInstalledError,
    NoOriginRemoteError,
    NotAGitRepoError,
    UnsupportedOriginError,
    get_origin_owner_repo,
    parse_origin_url,
)


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


def _mock_git_success(mocker: MockerFixture, stdout: str) -> object:
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=""),
    )


def _mock_git_failure(
    mocker: MockerFixture, stderr: str, returncode: int = 1
) -> object:
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr=stderr
        ),
    )


# get_origin_owner_repo — happy path
def test_get_origin_owner_repo_success(mocker: MockerFixture) -> None:
    _mock_git_success(mocker, "git@github.com:yakkuro/gh-manage.git\n")
    assert get_origin_owner_repo(Path("/tmp/fake")) == "yakkuro/gh-manage"


def test_get_origin_owner_repo_https_success(mocker: MockerFixture) -> None:
    _mock_git_success(mocker, "https://github.com/yakkuro/gh-manage\n")
    assert get_origin_owner_repo(Path("/tmp/fake")) == "yakkuro/gh-manage"


# get_origin_owner_repo — error classification
def test_get_origin_owner_repo_not_a_git_repo(mocker: MockerFixture) -> None:
    _mock_git_failure(
        mocker, "fatal: not a git repository (or any parent up to mount point /)\n"
    )
    with pytest.raises(NotAGitRepoError, match="git init"):
        get_origin_owner_repo(Path("/tmp/fake"))


def test_get_origin_owner_repo_no_origin_remote(mocker: MockerFixture) -> None:
    _mock_git_failure(mocker, "error: No such remote 'origin'\n", returncode=2)
    with pytest.raises(NoOriginRemoteError, match="git remote add origin"):
        get_origin_owner_repo(Path("/tmp/fake"))


def test_get_origin_owner_repo_git_not_installed(mocker: MockerFixture) -> None:
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("git"))
    with pytest.raises(GitNotInstalledError, match="git-scm.com"):
        get_origin_owner_repo(Path("/tmp/fake"))


def test_get_origin_owner_repo_other_failure_is_generic_git_error(
    mocker: MockerFixture,
) -> None:
    _mock_git_failure(mocker, "fatal: some other error\n")
    with pytest.raises(GitError):
        get_origin_owner_repo(Path("/tmp/fake"))


# get_origin_owner_repo — UnsupportedOriginError wraps ValueError
def test_get_origin_owner_repo_gitlab_url_raises_unsupported_origin(
    mocker: MockerFixture,
) -> None:
    """parse_origin_url raises ValueError on non-github URLs;
    get_origin_owner_repo MUST wrap this into UnsupportedOriginError(GitError)
    so callers only need to catch GitError."""
    _mock_git_success(mocker, "git@gitlab.com:yakkuro/foo.git\n")
    with pytest.raises(UnsupportedOriginError, match="github.com"):
        get_origin_owner_repo(Path("/tmp/fake"))


def test_unsupported_origin_error_is_a_git_error_subclass() -> None:
    """Catch GitError must also catch UnsupportedOriginError."""
    err = UnsupportedOriginError("test")
    assert isinstance(err, GitError)


def test_get_origin_owner_repo_empty_url_raises_no_origin_remote(
    mocker: MockerFixture,
) -> None:
    """If `git remote get-url origin` exits 0 with empty stdout (origin
    is set but its URL is empty/whitespace), raise NoOriginRemoteError
    with an actionable message — NOT pass the empty string to
    parse_origin_url where it would become a confusing
    'Unsupported git remote URL: \\'\\'' error.
    silent-failure-hunter HIGH #4."""
    _mock_git_success(mocker, "   \n")
    with pytest.raises(NoOriginRemoteError, match="empty URL"):
        get_origin_owner_repo(Path("/tmp/fake"))


# Locale enforcement — LOAD-BEARING
def test_get_origin_owner_repo_uses_lc_all_c(mocker: MockerFixture) -> None:
    """Subprocess invocation must include LC_ALL=C in env so stderr
    string matching is locale-stable. Regression guard for the locale
    contract documented in the design spec."""
    mock_run = _mock_git_success(mocker, "git@github.com:yakkuro/gh-manage.git\n")
    get_origin_owner_repo(Path("/tmp/fake"))
    env = mock_run.call_args.kwargs["env"]
    assert env["LC_ALL"] == "C"
    assert env["LANG"] == "C"
    assert env["LC_MESSAGES"] == "C"


def test_get_origin_owner_repo_uses_target_as_cwd(mocker: MockerFixture) -> None:
    """Subprocess must run with `git -C <target>` so it doesn't pick up
    the test runner's CWD by accident."""
    mock_run = _mock_git_success(mocker, "git@github.com:yakkuro/gh-manage.git\n")
    get_origin_owner_repo(Path("/tmp/some-target"))
    args = mock_run.call_args.args[0]
    assert args[0] == "git"
    assert "-C" in args
    c_idx = args.index("-C")
    assert args[c_idx + 1] == "/tmp/some-target"
