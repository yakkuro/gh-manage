"""Tests for gh_manage.github_api.issues — GitHub Issues API wrapper."""

from __future__ import annotations

import json
from subprocess import CompletedProcess

from pytest_mock import MockerFixture

from gh_manage.github_api.issues import (
    add_issue_comment,
    close_issue,
    create_issue,
    ensure_drift_label,
    get_issue_comments,
    search_drift_issue,
    update_issue_body,
)


def _mock_gh_success(mocker: MockerFixture, stdout: str) -> object:
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=""),
    )


def _mock_gh_failure(mocker: MockerFixture, stderr: str, returncode: int = 1) -> object:
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr=stderr
        ),
    )


# search_drift_issue
def test_search_drift_issue_found(mocker: MockerFixture) -> None:
    response = [{"number": 42, "title": "[gh-manage drift] yakkuro/gh-manage"}]
    _mock_gh_success(mocker, json.dumps(response))
    result = search_drift_issue("yakkuro/gh-manage")
    assert result is not None
    assert result["number"] == 42


def test_search_drift_issue_not_found(mocker: MockerFixture) -> None:
    _mock_gh_success(mocker, json.dumps([]))
    result = search_drift_issue("yakkuro/gh-manage")
    assert result is None


def test_search_drift_issue_uses_label_filter(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "[]")
    search_drift_issue("yakkuro/gh-manage")
    args = mock_run.call_args.args[0]
    args_str = " ".join(args)
    assert "repos/yakkuro/gh-manage/issues" in args_str
    assert "gh-manage:drift" in args_str


# create_issue
def test_create_issue_returns_issue_dict(mocker: MockerFixture) -> None:
    response = {
        "number": 42,
        "html_url": "https://github.com/yakkuro/gh-manage/issues/42",
    }
    _mock_gh_success(mocker, json.dumps(response))
    result = create_issue("yakkuro/gh-manage", "title", "body", ["gh-manage:drift"])
    assert result["number"] == 42


def test_create_issue_sends_body_via_stdin(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, '{"number": 1}')
    create_issue("yakkuro/gh-manage", "Test", "Body", ["gh-manage:drift"])
    args = mock_run.call_args.args[0]
    assert "-X" in args and "POST" in args
    assert "--input" in args and "-" in args
    stdin_input = mock_run.call_args.kwargs["input"]
    parsed = json.loads(stdin_input)
    assert parsed["title"] == "Test"
    assert parsed["body"] == "Body"
    assert parsed["labels"] == ["gh-manage:drift"]


# update_issue_body
def test_update_issue_body_uses_patch(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "{}")
    update_issue_body("yakkuro/gh-manage", 42, "new body")
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/issues/42" in args
    assert "-X" in args and "PATCH" in args
    stdin_input = mock_run.call_args.kwargs["input"]
    assert json.loads(stdin_input)["body"] == "new body"


# add_issue_comment
def test_add_issue_comment_posts_to_comments_endpoint(
    mocker: MockerFixture,
) -> None:
    mock_run = _mock_gh_success(mocker, "{}")
    add_issue_comment("yakkuro/gh-manage", 42, "scan comment")
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/issues/42/comments" in args
    assert "-X" in args and "POST" in args


# close_issue
def test_close_issue_patches_state_closed(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "{}")
    close_issue("yakkuro/gh-manage", 42)
    stdin_input = mock_run.call_args.kwargs["input"]
    assert json.loads(stdin_input)["state"] == "closed"


# ensure_drift_label
def test_ensure_drift_label_creates_label(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "{}")
    ensure_drift_label("yakkuro/gh-manage")
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/labels" in args
    assert "-X" in args and "POST" in args


def test_ensure_drift_label_ignores_422_already_exists(
    mocker: MockerFixture,
) -> None:
    """422 = label already exists. Should not raise."""
    _mock_gh_failure(mocker, "HTTP 422: Validation Failed\nalready_exists\n")
    # Should NOT raise
    ensure_drift_label("yakkuro/gh-manage")


# get_issue_comments
def test_get_issue_comments_returns_list(mocker: MockerFixture) -> None:
    comments = [{"id": 1, "body": "hello"}, {"id": 2, "body": "world"}]
    _mock_gh_success(mocker, json.dumps(comments))
    result = get_issue_comments("yakkuro/gh-manage", 42, per_page=5)
    assert len(result) == 2
    assert result[0]["body"] == "hello"
