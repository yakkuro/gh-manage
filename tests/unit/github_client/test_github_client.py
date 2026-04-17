"""Tests for gh_manage.github_client — transport + error hierarchy only.

Resource-specific label tests (list_labels, create_label, update_label,
delete_label) moved to tests/unit/github_api/test_labels.py during the
Phase 5 checkpoint refactor. This file tests only the generic transport
layer: run_gh, run_gh_api, and the GhError classification.
"""

from __future__ import annotations

from subprocess import CompletedProcess

import pytest
from pytest_mock import MockerFixture

from gh_manage.github_client import (
    GhAPIError,
    GhAuthError,
    GhError,
    GhNotFoundError,
    GhNotInstalledError,
    GhPermissionError,
    GhRateLimitError,
    run_gh,
    run_gh_api,
)


def _mock_gh_success(mocker: MockerFixture, stdout: str):
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=""),
    )


def _mock_gh_failure(mocker: MockerFixture, stderr: str, returncode: int = 1):
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr=stderr
        ),
    )


# Error classification — parametrized over all 6 stderr patterns
@pytest.mark.parametrize(
    ("stderr", "expected_exc"),
    [
        ("HTTP 404: Not Found\n", GhNotFoundError),
        ("You are not logged in to any GitHub hosts.\n", GhAuthError),
        ("Bad credentials\n", GhAuthError),
        ("HTTP 403: Forbidden\n", GhPermissionError),
        ("API rate limit exceeded\n", GhRateLimitError),
        ("Some unknown error\n", GhAPIError),
    ],
)
def test_run_gh_api_classifies_stderr_into_typed_exception(
    mocker: MockerFixture, stderr: str, expected_exc: type[Exception]
) -> None:
    _mock_gh_failure(mocker, stderr)
    with pytest.raises(expected_exc):
        run_gh_api("repos/foo/bar/labels")


# Not-installed case
def test_run_gh_api_filenotfound_raises_gh_not_installed(
    mocker: MockerFixture,
) -> None:
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("gh"))
    with pytest.raises(GhNotInstalledError, match="cli.github.com"):
        run_gh_api("repos/foo/bar/labels")


# Actionable messages
def test_gh_not_found_error_message_contains_gh_auth_status(
    mocker: MockerFixture,
) -> None:
    _mock_gh_failure(mocker, "HTTP 404: Not Found\n")
    with pytest.raises(GhNotFoundError, match="gh auth status"):
        run_gh_api("repos/foo/bar/labels")


def test_gh_auth_error_mentions_gh_auth_login(mocker: MockerFixture) -> None:
    _mock_gh_failure(mocker, "You are not logged in.\n")
    with pytest.raises(GhAuthError, match="gh auth login"):
        run_gh_api("repos/foo/bar/labels")


# Regression: silent-failure-hunter review findings (Phase 5)
def test_run_gh_api_malformed_json_raises_gh_api_error(
    mocker: MockerFixture,
) -> None:
    """json.loads on malformed stdout must be wrapped into GhAPIError so
    the user sees an actionable message instead of a raw JSONDecodeError
    traceback. Can happen in practice with truncated responses or GitHub
    API format changes."""
    _mock_gh_success(mocker, "{this is not valid json")
    with pytest.raises(GhAPIError, match="invalid JSON"):
        run_gh_api("repos/foo/bar/labels")


def test_run_gh_non_zero_exit_propagates_classified_error(
    mocker: MockerFixture,
) -> None:
    """run_gh (the low-level function) must always raise a GhError subclass
    on non-zero exit — never return silently. Tests exercise run_gh_api
    which wraps run_gh; this test directly verifies run_gh itself so a
    future refactor can't silently regress the non-zero path."""
    _mock_gh_failure(mocker, "HTTP 404: Not Found\n")
    with pytest.raises(GhError):
        run_gh(["api", "repos/foo/bar/labels"])


# Body/stdin semantics — regression for Codex PR #10 refactor #11.
# run_gh_api(body=...) must serialize the dict to JSON, append
# `--input -` to argv, and pipe the JSON into subprocess stdin.
def test_run_gh_api_with_body_sends_json_via_stdin(
    mocker: MockerFixture,
) -> None:
    import json

    mock_run = _mock_gh_success(mocker, '{"id": 1}')
    run_gh_api(
        "repos/foo/bar/labels",
        method="POST",
        body={"name": "bug", "color": "d73a4a", "nested": {"k": "v"}},
    )
    args = mock_run.call_args.args[0]
    assert "--input" in args
    assert "-" in args
    assert "-X" in args
    assert "POST" in args
    stdin_input = mock_run.call_args.kwargs["input"]
    assert json.loads(stdin_input) == {
        "name": "bug",
        "color": "d73a4a",
        "nested": {"k": "v"},
    }


def test_run_gh_api_without_body_sends_no_stdin(
    mocker: MockerFixture,
) -> None:
    """GET calls (body=None) must NOT append `--input -` nor pass stdin."""
    mock_run = _mock_gh_success(mocker, "[]")
    run_gh_api("repos/foo/bar/labels")
    args = mock_run.call_args.args[0]
    assert "--input" not in args
    assert mock_run.call_args.kwargs.get("input") is None


# Issue #11 — POST/PATCH empty stdout silent None
def test_run_gh_api_post_empty_stdout_raises(mocker: MockerFixture) -> None:
    """POST returning exit 0 with empty stdout must raise GhAPIError, not return None.

    GitHub's labels API documents that POST returns the created resource on
    success. An empty stdout indicates the gh subprocess succeeded but
    returned nothing — silent failure that the caller would never notice.
    """
    _mock_gh_success(mocker, "")
    with pytest.raises(GhAPIError, match="empty response for POST"):
        run_gh_api(
            "repos/yakkuro/gh-manage/labels",
            method="POST",
            body={"name": "x", "color": "ff0000"},
        )


def test_run_gh_api_patch_empty_stdout_raises(mocker: MockerFixture) -> None:
    """PATCH returning exit 0 with empty stdout must raise GhAPIError, not return None.

    Same rationale as POST — GitHub's API documents that PATCH returns the
    updated resource on success.
    """
    _mock_gh_success(mocker, "")
    with pytest.raises(GhAPIError, match="empty response for PATCH"):
        run_gh_api(
            "repos/yakkuro/gh-manage/labels/x",
            method="PATCH",
            body={"name": "y"},
        )


# Task 1: status_code attribute on base GhError
def test_gh_error_base_accepts_status_code_kwarg() -> None:
    from gh_manage.github_client import GhError

    e = GhError("boom", status_code=503)
    assert str(e) == "boom"
    assert e.status_code == 503


def test_gh_error_status_code_defaults_to_none() -> None:
    from gh_manage.github_client import GhError

    e = GhError("boom")
    assert e.status_code is None


def test_gh_error_subclasses_accept_status_code() -> None:
    from gh_manage.github_client import GhAuthError, GhNotFoundError

    assert GhAuthError("x", status_code=401).status_code == 401
    assert GhNotFoundError("x", status_code=404).status_code == 404
