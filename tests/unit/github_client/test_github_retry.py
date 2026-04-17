"""Tests for gh_manage.github_retry — retry engine + rate-limit probe."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from subprocess import CompletedProcess

import pytest
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


# Task 6: retry_gh transient path
def test_retry_gh_succeeds_after_transient_failures(
    mocker: MockerFixture,
) -> None:
    """3 transient failures, then success → retry_gh returns the value."""
    from gh_manage.github_client import GhTransientError
    from gh_manage.github_retry import retry_gh

    mocker.patch("time.sleep", return_value=None)  # skip real sleeps
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 4:
            raise GhTransientError("temp", status_code=503)
        return "ok"

    result = retry_gh(flaky, endpoint="api repos/foo", max_attempts=3)
    assert result == "ok"
    assert calls["n"] == 4  # 1 initial + 3 retries


def test_retry_gh_gives_up_after_max_attempts(mocker: MockerFixture) -> None:
    from gh_manage.github_client import GhTransientError
    from gh_manage.github_retry import retry_gh

    mocker.patch("time.sleep", return_value=None)
    calls = {"n": 0}

    def always_fail() -> str:
        calls["n"] += 1
        raise GhTransientError("temp", status_code=503)

    import pytest

    with pytest.raises(GhTransientError):
        retry_gh(always_fail, endpoint="api repos/foo", max_attempts=3)
    assert calls["n"] == 4  # 1 initial + 3 retries


def test_retry_gh_does_not_retry_non_retriable(mocker: MockerFixture) -> None:
    """401/403-perm/404 must pass through on the first attempt."""
    from gh_manage.github_client import GhAuthError, GhNotFoundError, GhPermissionError
    from gh_manage.github_retry import retry_gh

    import pytest

    sleep_mock = mocker.patch("time.sleep", return_value=None)

    for exc_cls in (GhAuthError, GhNotFoundError, GhPermissionError):
        calls = {"n": 0}

        def fn(cls=exc_cls) -> str:
            calls["n"] += 1
            raise cls("perm")

        with pytest.raises(exc_cls):
            retry_gh(fn, endpoint="api repos/foo", max_attempts=3)
        assert calls["n"] == 1

    assert sleep_mock.call_count == 0  # zero retries → zero sleeps


def test_retry_gh_exponential_backoff_with_jitter(mocker: MockerFixture) -> None:
    """Sleep durations should be in [1, 1.5), [2, 3), [4, 6) for attempts 1-3."""
    from gh_manage.github_client import GhTransientError
    from gh_manage.github_retry import retry_gh

    sleeps: list[float] = []

    def record_sleep(t: float) -> None:
        sleeps.append(t)

    mocker.patch("time.sleep", side_effect=record_sleep)
    calls = {"n": 0}

    def always_fail() -> str:
        calls["n"] += 1
        raise GhTransientError("temp", status_code=503)

    import pytest

    with pytest.raises(GhTransientError):
        retry_gh(always_fail, endpoint="api repos/foo", max_attempts=3)

    assert len(sleeps) == 3
    assert 1.0 <= sleeps[0] < 1.5
    assert 2.0 <= sleeps[1] < 3.0
    assert 4.0 <= sleeps[2] < 6.0


def test_retry_gh_env_var_overrides_max_attempts(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gh_manage.github_client import GhTransientError
    from gh_manage.github_retry import retry_gh

    import pytest

    monkeypatch.setenv("GH_MANAGE_MAX_RETRIES", "1")
    mocker.patch("time.sleep", return_value=None)
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise GhTransientError("temp", status_code=503)

    with pytest.raises(GhTransientError):
        retry_gh(fn, endpoint="api repos/foo")
    assert calls["n"] == 2  # 1 initial + 1 retry
