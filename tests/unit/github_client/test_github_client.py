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
