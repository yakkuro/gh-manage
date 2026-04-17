"""SFH follow-up: _fetch_remote_ci_yml wraps non-404 decode errors in
DoctorError instead of letting binascii.Error / UnicodeDecodeError
leak raw (SFH CRITICAL #1).

Note: run_gh_api already parses JSON, so the response is always a
dict (or raises on API-level failure). The only decode that can fail
here is base64 → UTF-8 on the content field.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_fetch_remote_ci_yml_wraps_base64_error_in_doctor_error():
    from gh_manage.doctor import _fetch_remote_ci_yml
    from gh_manage.doctor.errors import DoctorError

    # GitHub returns {"content": "...", "encoding": "base64"}. If
    # content can't be base64-decoded, DoctorError wraps the failure.
    with patch(
        "gh_manage.doctor.run_gh_api",
        return_value={"content": "!!!not-valid-base64!!!", "encoding": "base64"},
    ):
        with pytest.raises(DoctorError) as excinfo:
            _fetch_remote_ci_yml("yakkuro/example")
    assert "yakkuro/example" in str(excinfo.value)


def test_fetch_remote_ci_yml_returns_empty_on_404():
    from gh_manage.doctor import _fetch_remote_ci_yml
    from gh_manage.github_client import GhNotFoundError

    with patch(
        "gh_manage.doctor.run_gh_api",
        side_effect=GhNotFoundError("not found"),
    ):
        assert _fetch_remote_ci_yml("yakkuro/example") == ""


def test_fetch_remote_ci_yml_returns_empty_on_unexpected_shape():
    from gh_manage.doctor import _fetch_remote_ci_yml

    # GitHub API could theoretically return a list (for dir listings).
    # Treat as "file absent" rather than crashing.
    with patch("gh_manage.doctor.run_gh_api", return_value=[]):
        assert _fetch_remote_ci_yml("yakkuro/example") == ""
