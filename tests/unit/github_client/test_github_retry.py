"""Tests for gh_manage.github_retry — retry engine + rate-limit probe."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from subprocess import CompletedProcess

from pytest_mock import MockerFixture


def _mock_subprocess_ok(mocker: MockerFixture, stdout: str):
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=""),
    )


def _mock_subprocess_fail(mocker: MockerFixture, stderr: str, returncode: int = 1):
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr=stderr
        ),
    )


def test_fetch_rate_limit_reset_returns_datetime_on_success(
    mocker: MockerFixture,
) -> None:
    from gh_manage.github_retry import _fetch_rate_limit_reset

    reset_ts = 1_744_886_400  # 2026-04-17T10:00:00Z (example)
    body = json.dumps(
        {"resources": {"core": {"reset": reset_ts, "remaining": 0, "limit": 5000}}}
    )
    _mock_subprocess_ok(mocker, body)

    result = _fetch_rate_limit_reset()
    assert isinstance(result, datetime)
    assert result == datetime.fromtimestamp(reset_ts, tz=timezone.utc)


def test_fetch_rate_limit_reset_returns_none_on_probe_failure(
    mocker: MockerFixture,
) -> None:
    from gh_manage.github_retry import _fetch_rate_limit_reset

    _mock_subprocess_fail(mocker, "some probe error")
    result = _fetch_rate_limit_reset()
    assert result is None


def test_fetch_rate_limit_reset_returns_none_on_malformed_json(
    mocker: MockerFixture,
) -> None:
    from gh_manage.github_retry import _fetch_rate_limit_reset

    _mock_subprocess_ok(mocker, "{not valid json")
    assert _fetch_rate_limit_reset() is None


def test_fetch_rate_limit_reset_returns_none_on_subprocess_timeout(
    mocker: MockerFixture,
) -> None:
    from gh_manage.github_retry import _fetch_rate_limit_reset

    mocker.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 5))
    assert _fetch_rate_limit_reset() is None
