"""Tests for gh_manage.github_api.protection — Classic Branch Protection API wrapper.

Mirrors tests/unit/github_api/test_labels.py — subprocess.run is mocked
to return controlled CompletedProcess instances.
"""

from __future__ import annotations

import json
from subprocess import CompletedProcess

import pytest
from pytest_mock import MockerFixture

from gh_manage.github_api.protection import (
    delete_branch_protection,
    get_branch_protection,
    put_branch_protection,
)
from gh_manage.github_client import GhAPIError, GhNotFoundError


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


# get_branch_protection
def test_get_branch_protection_happy_path(mocker: MockerFixture) -> None:
    response = {
        "enforce_admins": {"enabled": False},
        "required_status_checks": {"strict": True, "contexts": []},
    }
    _mock_gh_success(mocker, json.dumps(response))
    result = get_branch_protection("yakkuro/gh-manage", "main")
    assert result == response


def test_get_branch_protection_default_branch_is_main(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "{}")
    get_branch_protection("yakkuro/gh-manage")
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/branches/main/protection" in args


def test_get_branch_protection_404_propagates_as_gh_not_found(
    mocker: MockerFixture,
) -> None:
    _mock_gh_failure(mocker, "HTTP 404: Not Found\nBranch not protected\n")
    with pytest.raises(GhNotFoundError):
        get_branch_protection("yakkuro/gh-manage", "main")


def test_get_branch_protection_malformed_json_raises_gh_api_error(
    mocker: MockerFixture,
) -> None:
    _mock_gh_success(mocker, "{not valid json")
    with pytest.raises(GhAPIError):
        get_branch_protection("yakkuro/gh-manage", "main")


# put_branch_protection
def test_put_branch_protection_sends_body_via_stdin(mocker: MockerFixture) -> None:
    """LOAD-BEARING: the Phase 5 checkpoint refactor rewrote run_gh_api to
    send bodies via `gh api --input -` (stdin). Phase 7 is the first
    production caller of that path. This test guards the regression."""
    mock_run = _mock_gh_success(mocker, "{}")
    body = {
        "required_status_checks": {"strict": True, "contexts": ["pr-gate / test"]},
        "enforce_admins": False,
        "required_pull_request_reviews": None,
        "restrictions": None,
    }
    put_branch_protection("yakkuro/gh-manage", "main", body)

    args = mock_run.call_args.args[0]
    # Must use PUT method
    assert "-X" in args
    assert "PUT" in args
    # Must use --input - (stdin body) from Phase 5 checkpoint refactor
    assert "--input" in args
    assert "-" in args
    # Body sent via stdin, not -f key=value
    stdin_input = mock_run.call_args.kwargs["input"]
    assert json.loads(stdin_input) == body


def test_put_branch_protection_endpoint(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "{}")
    put_branch_protection("yakkuro/gh-manage", "main", {})
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/branches/main/protection" in args


# delete_branch_protection
def test_delete_branch_protection_calls_delete(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "")
    delete_branch_protection("yakkuro/gh-manage", "main")
    args = mock_run.call_args.args[0]
    assert "-X" in args
    assert "DELETE" in args
    assert "repos/yakkuro/gh-manage/branches/main/protection" in args
