"""Tests for gh_manage.github_client with subprocess.run mocked."""

from __future__ import annotations

import json
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
    Label,
    create_label,
    delete_label,
    list_labels,
    run_gh,
    run_gh_api,
    update_label,
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


# Happy path — list_labels
def test_list_labels_parses_json_response(mocker: MockerFixture) -> None:
    _mock_gh_success(
        mocker,
        json.dumps(
            [
                {"name": "bug", "color": "d73a4a", "description": "Buggy"},
                {"name": "feat", "color": "a2eeef", "description": None},
            ]
        ),
    )
    result = list_labels("yakkuro/gh-manage")
    assert result == [
        Label(name="bug", color="d73a4a", description="Buggy"),
        Label(name="feat", color="a2eeef", description=""),
    ]


def test_list_labels_auto_paginates(mocker: MockerFixture) -> None:
    """list_labels must pass --paginate to gh api."""
    mock_run = _mock_gh_success(mocker, "[]")
    list_labels("yakkuro/gh-manage")
    args = mock_run.call_args.args[0]
    assert "--paginate" in args


def test_list_labels_handles_empty_response(mocker: MockerFixture) -> None:
    _mock_gh_success(mocker, "[]")
    result = list_labels("yakkuro/gh-manage")
    assert result == []


# Normalization
def test_list_labels_normalizes_color_to_lowercase(mocker: MockerFixture) -> None:
    _mock_gh_success(
        mocker,
        json.dumps([{"name": "bug", "color": "D73A4A", "description": "x"}]),
    )
    result = list_labels("yakkuro/gh-manage")
    assert result[0].color == "d73a4a"


def test_list_labels_converts_null_description_to_empty_string(
    mocker: MockerFixture,
) -> None:
    _mock_gh_success(
        mocker,
        json.dumps([{"name": "bug", "color": "d73a4a", "description": None}]),
    )
    result = list_labels("yakkuro/gh-manage")
    assert result[0].description == ""


# Happy path — create_label
def test_create_label_sends_correct_body(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "")
    create_label(
        "yakkuro/gh-manage",
        Label(name="chore", color="e1e7eb", description="housekeeping"),
    )
    args = mock_run.call_args.args[0]
    assert "api" in args
    assert "repos/yakkuro/gh-manage/labels" in args
    assert "-X" in args
    assert "POST" in args
    assert "name=chore" in args
    assert "color=e1e7eb" in args
    assert "description=housekeeping" in args


# Happy path — update_label with rename
def test_update_label_with_rename_includes_new_name(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "")
    update_label(
        "yakkuro/gh-manage",
        current_name="bug",
        new_label=Label(name="fix", color="d73a4a", description="Bug fix"),
    )
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/labels/bug" in args
    assert "-X" in args
    assert "PATCH" in args
    assert "new_name=fix" in args
    assert "color=d73a4a" in args
    assert "description=Bug fix" in args


# Happy path — update_label without rename
def test_update_label_without_rename_omits_new_name(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "")
    update_label(
        "yakkuro/gh-manage",
        current_name="fix",
        new_label=Label(name="fix", color="d73a4a", description="Updated desc"),
    )
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/labels/fix" in args
    assert "-X" in args
    assert "PATCH" in args
    assert not any("new_name=" in a for a in args)
    assert "color=d73a4a" in args
    assert "description=Updated desc" in args


# Happy path — delete_label
def test_delete_label_calls_correct_endpoint(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "")
    delete_label("yakkuro/gh-manage", "bug")
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/labels/bug" in args
    assert "-X" in args
    assert "DELETE" in args


# Error classification — parametrized
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


# Regression: silent-failure-hunter review findings
def test_run_gh_api_malformed_json_raises_gh_api_error(
    mocker: MockerFixture,
) -> None:
    """Regression test for silent-failure-hunter MEDIUM finding:
    json.loads on malformed stdout must be wrapped into GhAPIError so the
    user sees an actionable message instead of a raw JSONDecodeError
    traceback. This can happen in practice with truncated responses or
    GitHub API format changes."""
    _mock_gh_success(mocker, "{this is not valid json")
    with pytest.raises(GhAPIError, match="invalid JSON"):
        run_gh_api("repos/foo/bar/labels")


def test_run_gh_non_zero_exit_propagates_classified_error(
    mocker: MockerFixture,
) -> None:
    """Regression test for silent-failure-hunter HIGH finding:
    run_gh (the lower-level function) must always raise a GhError subclass
    on non-zero exit — never return silently. Tests exercise run_gh_api
    which wraps run_gh; this test directly verifies run_gh itself so a
    future refactor can't silently regress the non-zero path."""
    _mock_gh_failure(mocker, "HTTP 404: Not Found\n")
    with pytest.raises(GhError):
        run_gh(["api", "repos/foo/bar/labels"])
