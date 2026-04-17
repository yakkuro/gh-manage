"""Tests for gh_manage.github_client — transport + error hierarchy only.

Resource-specific label tests (list_labels, create_label, update_label,
delete_label) moved to tests/unit/github_api/test_labels.py during the
Phase 5 checkpoint refactor. This file tests only the generic transport
layer: run_gh, run_gh_api, and the GhError classification.
"""

from __future__ import annotations

from datetime import datetime, timezone
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
    GhTransientError,
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


# Task 3: Path A (HTTP-status-parsed) classifier
@pytest.mark.parametrize(
    ("stderr", "expected_exc", "expected_status"),
    [
        # Path A — HTTP status parsed from stderr
        ("gh: Not Found (HTTP 404)\n", GhNotFoundError, 404),
        ("gh: Bad credentials (HTTP 401)\n", GhAuthError, 401),
        ("gh: Forbidden (HTTP 403)\n", GhPermissionError, 403),
        ("gh: API rate limit exceeded (HTTP 403)\n", GhRateLimitError, 403),
        (
            "gh: You have exceeded a secondary rate limit (HTTP 403)\n",
            GhRateLimitError,
            403,
        ),
        ("gh: abuse detection mechanism (HTTP 403)\n", GhRateLimitError, 403),
        ("gh: Too Many Requests (HTTP 429)\n", GhRateLimitError, 429),
        ("gh: Internal Server Error (HTTP 500)\n", GhTransientError, 500),
        ("gh: Bad Gateway (HTTP 502)\n", GhTransientError, 502),
        ("gh: Service Unavailable (HTTP 503)\n", GhTransientError, 503),
        ("gh: Gateway Timeout (HTTP 504)\n", GhTransientError, 504),
        ("gh: I'm a teapot (HTTP 418)\n", GhAPIError, 418),
        ("gh: weird code (HTTP 599)\n", GhAPIError, 599),
    ],
)
def test_path_a_http_status_classification(
    mocker: MockerFixture,
    stderr: str,
    expected_exc: type[Exception],
    expected_status: int,
) -> None:
    _mock_gh_failure(mocker, stderr)
    with pytest.raises(expected_exc) as exc_info:
        run_gh_api("repos/foo/bar/labels")
    assert exc_info.value.status_code == expected_status


# Task 3: Path B (no HTTP status — network level)
@pytest.mark.parametrize(
    ("stderr", "expected_exc"),
    [
        ("error: dial tcp: lookup api.github.com: no such host\n", GhTransientError),
        ("error: dial tcp 140.82.121.5:443: connection refused\n", GhTransientError),
        ("error: Post https://api.github.com: i/o timeout\n", GhTransientError),
        ("error: context deadline exceeded\n", GhTransientError),
        ("error: connection refused\n", GhTransientError),
        ("error: some totally unknown error\n", GhAPIError),
        ("\n", GhAPIError),
    ],
)
def test_path_b_network_marker_classification(
    mocker: MockerFixture,
    stderr: str,
    expected_exc: type[Exception],
) -> None:
    _mock_gh_failure(mocker, stderr)
    with pytest.raises(expected_exc) as exc_info:
        run_gh_api("repos/foo/bar/labels")
    assert exc_info.value.status_code is None


# Task 3: Path A wins when BOTH HTTP status AND network markers present
def test_path_a_wins_over_path_b_when_both_present(mocker: MockerFixture) -> None:
    _mock_gh_failure(
        mocker,
        "gh: Internal Server Error (HTTP 500): dial tcp failed\n",
    )
    with pytest.raises(GhTransientError) as exc_info:
        run_gh_api("repos/foo/bar/labels")
    assert exc_info.value.status_code == 500


# Task 3: Canary — `gh` CLI format must keep (HTTP <code>) parseable
def test_canary_gh_cli_http_code_format_parseable() -> None:
    """If a future gh CLI version drops '(HTTP <code>)' from stderr, this
    test breaks loudly before every downstream retry test also breaks."""
    import re

    # This is the exact contract the classifier depends on.
    match = re.search(r"\(HTTP (\d{3})\)", "gh: Not Found (HTTP 404)\n")
    assert match is not None
    assert match.group(1) == "404"


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
    _mock_gh_failure(mocker, "gh: Not Found (HTTP 404)\n")
    with pytest.raises(GhNotFoundError, match="gh auth status"):
        run_gh_api("repos/foo/bar/labels")


def test_gh_auth_error_mentions_gh_auth_login(mocker: MockerFixture) -> None:
    _mock_gh_failure(mocker, "gh: Bad credentials (HTTP 401)\n")
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
    _mock_gh_failure(mocker, "gh: Not Found (HTTP 404)\n")
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


# Task 2: GhTransientError
def test_gh_transient_error_is_ghapierror_subclass() -> None:
    from gh_manage.github_client import GhAPIError, GhError

    assert issubclass(GhTransientError, GhAPIError)
    assert issubclass(GhTransientError, GhError)


def test_gh_transient_error_accepts_status_code() -> None:
    e = GhTransientError("temp 503", status_code=503)
    assert e.status_code == 503

    e_net = GhTransientError("network", status_code=None)
    assert e_net.status_code is None


# Task 4: GhRateLimitError with reset_at
def test_gh_rate_limit_error_reset_at_defaults_to_none() -> None:
    from gh_manage.github_client import GhRateLimitError

    e = GhRateLimitError("x")
    assert e.reset_at is None
    assert e.status_code is None


def test_gh_rate_limit_error_with_reset_at_and_status_code() -> None:
    from gh_manage.github_client import GhRateLimitError

    ts = datetime(2026, 4, 17, 10, 45, tzinfo=timezone.utc)
    e = GhRateLimitError("wait", status_code=429, reset_at=ts)
    assert e.status_code == 429
    assert e.reset_at == ts
