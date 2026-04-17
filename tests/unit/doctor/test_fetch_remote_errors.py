"""SFH follow-up: _fetch_remote_ci_yml wraps non-404 decode errors in
DoctorError instead of letting yaml.YAMLError / binascii.Error /
UnicodeDecodeError leak raw (SFH CRITICAL #1)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_fetch_remote_ci_yml_wraps_yaml_error_in_doctor_error():
    from gh_manage.doctor import _fetch_remote_ci_yml
    from gh_manage.doctor.errors import DoctorError

    with patch(
        "gh_manage.doctor.run_gh_api",
        return_value="not: valid: yaml: [",
    ):
        with pytest.raises(DoctorError) as excinfo:
            _fetch_remote_ci_yml("yakkuro/example")
    assert "yakkuro/example" in str(excinfo.value)


def test_fetch_remote_ci_yml_wraps_base64_error_in_doctor_error():
    from gh_manage.doctor import _fetch_remote_ci_yml
    from gh_manage.doctor.errors import DoctorError

    # GitHub content API returns {"content": "...", "encoding": "base64"}
    # If content is not valid base64, decode fails.
    with patch(
        "gh_manage.doctor.run_gh_api",
        return_value='content: "!!!not-base64!!!"\n',
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
