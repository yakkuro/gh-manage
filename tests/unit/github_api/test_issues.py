"""Tests for gh_manage.github_api.issues — GitHub Issues API wrapper."""

from __future__ import annotations

import json
from subprocess import CompletedProcess

import pytest
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
# get_issue_comments
def test_get_issue_comments_returns_list(mocker: MockerFixture) -> None:
    comments = [{"id": 1, "body": "hello"}, {"id": 2, "body": "world"}]
    _mock_gh_success(mocker, json.dumps(comments))
    result = get_issue_comments("yakkuro/gh-manage", 42, per_page=5)
    assert len(result) == 2
    assert result[0]["body"] == "hello"


# #40: ensure_drift_label — GET-first, no silent 422 swallow
def test_ensure_drift_label_exists_no_post(mocker: MockerFixture) -> None:
    """GET returns the label — function returns without calling POST."""
    mock_run = _mock_gh_success(
        mocker, json.dumps({"name": "gh-manage:drift", "color": "d4c5f9"})
    )
    ensure_drift_label("yakkuro/foo")
    assert mock_run.call_count == 1
    args = mock_run.call_args.args[0]
    # The single call should be GET to /labels/{name}, not POST to /labels
    assert "-X" not in args  # run_gh_api without -X means GET (default)
    endpoint_arg = [a for a in args if a.startswith("repos/")][0]
    assert endpoint_arg.endswith("/labels/gh-manage:drift")


def test_ensure_drift_label_missing_then_created(mocker: MockerFixture) -> None:
    """GET 404 → POST to create. Two subprocess calls; verify POST body."""
    calls: list[CompletedProcess] = [
        CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="gh: Not Found (HTTP 404)\n",
        ),
        CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"id": 1, "name": "gh-manage:drift"}),
            stderr="",
        ),
    ]
    captured_calls: list[tuple[list[str], str | None]] = []

    def _next_call(*args: object, **kwargs: object) -> CompletedProcess:
        argv = args[0] if args else kwargs.get("args") or []
        stdin = kwargs.get("input")
        captured_calls.append((list(argv), stdin))  # type: ignore[arg-type]
        return calls[len(captured_calls) - 1]

    mocker.patch("subprocess.run", side_effect=_next_call)
    mocker.patch("time.sleep", return_value=None)
    ensure_drift_label("yakkuro/foo")
    assert len(captured_calls) == 2

    # Second call must be POST to /repos/.../labels with the correct body.
    post_argv, post_stdin = captured_calls[1]
    assert "-X" in post_argv and "POST" in post_argv
    post_endpoint = [a for a in post_argv if a.startswith("repos/")][0]
    assert post_endpoint == "repos/yakkuro/foo/labels"
    assert post_stdin is not None
    body = json.loads(post_stdin)
    assert body["name"] == "gh-manage:drift"
    assert body["color"] == "d4c5f9"
    assert "Automated drift report" in body["description"]


def test_ensure_drift_label_get_auth_error_propagates(mocker: MockerFixture) -> None:
    """GET returns 401 → propagates GhAuthError (no silent swallow)."""
    from gh_manage.github_client import GhAuthError

    _mock_gh_failure(mocker, "gh: Bad credentials (HTTP 401)\n")
    mocker.patch("time.sleep", return_value=None)
    with pytest.raises(GhAuthError):
        ensure_drift_label("yakkuro/foo")


def test_ensure_drift_label_post_permission_error_propagates(
    mocker: MockerFixture,
) -> None:
    """GET 404 → POST 403 (non-rate-limit) → propagates GhPermissionError."""
    from subprocess import CompletedProcess

    from gh_manage.github_client import GhPermissionError

    calls: list[CompletedProcess] = [
        CompletedProcess(
            args=[], returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)\n"
        ),
        CompletedProcess(
            args=[], returncode=1, stdout="", stderr="gh: Forbidden (HTTP 403)\n"
        ),
    ]
    call_idx = {"n": 0}

    def _next_call(*args: object, **kwargs: object) -> CompletedProcess:
        resp = calls[call_idx["n"]]
        call_idx["n"] += 1
        return resp

    mocker.patch("subprocess.run", side_effect=_next_call)
    mocker.patch("time.sleep", return_value=None)
    with pytest.raises(GhPermissionError):
        ensure_drift_label("yakkuro/foo")


def test_ensure_drift_label_post_422_retries_get(mocker: MockerFixture) -> None:
    """Race: GET 404 → POST 422 → retry GET succeeds → return."""
    calls: list[CompletedProcess] = [
        CompletedProcess(
            args=[], returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)\n"
        ),
        CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="gh: Unprocessable Entity (HTTP 422)\n",
        ),
        CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"name": "gh-manage:drift"}),
            stderr="",
        ),
    ]
    call_idx = {"n": 0}

    def _next_call(*args: object, **kwargs: object) -> CompletedProcess:
        resp = calls[call_idx["n"]]
        call_idx["n"] += 1
        return resp

    mocker.patch("subprocess.run", side_effect=_next_call)
    mocker.patch("time.sleep", return_value=None)
    ensure_drift_label("yakkuro/foo")
    assert call_idx["n"] == 3


def test_ensure_drift_label_post_422_retry_still_fails_raises(
    mocker: MockerFixture,
) -> None:
    """Race: GET 404 → POST 422 → retry GET still 404 → raise."""
    from gh_manage.github_client import GhError

    calls: list[CompletedProcess] = [
        CompletedProcess(
            args=[], returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)\n"
        ),
        CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="gh: Unprocessable Entity (HTTP 422)\n",
        ),
        CompletedProcess(
            args=[], returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)\n"
        ),
    ]
    call_idx = {"n": 0}

    def _next_call(*args: object, **kwargs: object) -> CompletedProcess:
        resp = calls[call_idx["n"]]
        call_idx["n"] += 1
        return resp

    mocker.patch("subprocess.run", side_effect=_next_call)
    mocker.patch("time.sleep", return_value=None)
    with pytest.raises(GhError):
        ensure_drift_label("yakkuro/foo")


def test_ensure_drift_label_post_422_retry_permission_error_propagates_real_error(
    mocker: MockerFixture,
) -> None:
    """Race retry GET hits 403 (not 404) — real permission issue must
    propagate unchanged; do NOT mask it as the original 422. Regression
    guard for review feedback: the old `except GhError` caught too
    broadly and hid real errors behind the 422.
    """
    from gh_manage.github_client import GhPermissionError

    calls: list[CompletedProcess] = [
        CompletedProcess(
            args=[], returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)\n"
        ),
        CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="gh: Unprocessable Entity (HTTP 422)\n",
        ),
        CompletedProcess(
            args=[], returncode=1, stdout="", stderr="gh: Forbidden (HTTP 403)\n"
        ),
    ]
    call_idx = {"n": 0}

    def _next_call(*args: object, **kwargs: object) -> CompletedProcess:
        resp = calls[call_idx["n"]]
        call_idx["n"] += 1
        return resp

    mocker.patch("subprocess.run", side_effect=_next_call)
    mocker.patch("time.sleep", return_value=None)
    with pytest.raises(GhPermissionError):
        ensure_drift_label("yakkuro/foo")


def test_ensure_drift_label_post_422_retry_rate_limit_propagates_real_error(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Race retry GET hits rate limit (429) — propagate unchanged.

    Without the GhNotFoundError-only catch, the caller would see a
    misleading 422 and never know to back off on rate limit.

    Uses GH_MANAGE_RATE_LIMIT_WAIT_MAX=0 so retry_gh does not
    silently retry the rate-limit internally; we want the 429 to
    reach ensure_drift_label's outer handler where the propagation
    decision lives.
    """
    from gh_manage.github_client import GhRateLimitError

    monkeypatch.setenv("GH_MANAGE_RATE_LIMIT_WAIT_MAX", "0")

    calls: list[CompletedProcess] = [
        CompletedProcess(
            args=[], returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)\n"
        ),
        CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="gh: Unprocessable Entity (HTTP 422)\n",
        ),
        CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="gh: Too Many Requests (HTTP 429)\n",
        ),
    ]
    call_idx = {"n": 0}

    def _next_call(*args: object, **kwargs: object) -> CompletedProcess:
        resp = calls[call_idx["n"]]
        call_idx["n"] += 1
        return resp

    mocker.patch("subprocess.run", side_effect=_next_call)
    mocker.patch("gh_manage.github_retry._fetch_rate_limit_reset", return_value=None)
    mocker.patch("time.sleep", return_value=None)
    with pytest.raises(GhRateLimitError):
        ensure_drift_label("yakkuro/foo")
