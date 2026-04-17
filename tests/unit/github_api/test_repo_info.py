"""Tests for gh_manage.github_api.repo_info — repo metadata helpers."""

from __future__ import annotations

from subprocess import CompletedProcess

import pytest
from pytest_mock import MockerFixture

from gh_manage.github_api.repo_info import get_default_branch
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


def test_get_default_branch_returns_main(mocker: MockerFixture) -> None:
    _mock_gh_success(mocker, "main\n")
    assert get_default_branch("yakkuro/gh-manage") == "main"


def test_get_default_branch_returns_develop(mocker: MockerFixture) -> None:
    _mock_gh_success(mocker, "develop\n")
    assert get_default_branch("some/repo") == "develop"


def test_get_default_branch_strips_whitespace(mocker: MockerFixture) -> None:
    _mock_gh_success(mocker, "  master  \n\n")
    assert get_default_branch("some/repo") == "master"


def test_get_default_branch_uses_jq_flag(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "main\n")
    get_default_branch("yakkuro/gh-manage")
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage" in args
    assert "--jq" in args
    assert ".default_branch" in args


def test_get_default_branch_404_propagates(mocker: MockerFixture) -> None:
    _mock_gh_failure(mocker, "gh: Not Found (HTTP 404)\nRepository does not exist\n")
    with pytest.raises(GhNotFoundError):
        get_default_branch("nonexistent/repo")


def test_get_default_branch_empty_response_raises_api_error(
    mocker: MockerFixture,
) -> None:
    _mock_gh_success(mocker, "")
    with pytest.raises(GhAPIError, match="(?i)empty"):
        get_default_branch("some/repo")
