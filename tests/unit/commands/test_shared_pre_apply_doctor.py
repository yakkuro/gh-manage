"""Tests for commands._shared.run_pre_apply_doctor (spec §3.1)."""

from __future__ import annotations

from pathlib import Path

import click
import pytest
from pytest_mock import MockerFixture

from gh_manage.doctor.semantic_filter import ApplyScope
from gh_manage.findings import Finding


def _finding(
    check: str = "shape/required-contexts-match",
    severity: str = "high",
) -> Finding:
    return Finding(
        severity=severity,
        check=check,
        repo="yakkuro/example",
        field_path="x",
        current_value=None,
        desired_value=None,
        message="msg",
    )


def test_pass_when_no_findings(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch("gh_manage.commands._shared.doctor.run_on_path", return_value=())
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=True)
    run_pre_apply_doctor(
        tmp_path, profile_name="python-service", scope=scope, allow_blocking=False
    )


def test_pass_when_only_filtered_findings(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """shape/required-contexts-match is filtered when sync_protection=True."""
    from gh_manage.doctor import checks  # noqa: F401 — force registration

    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(_finding(severity="high"),),
    )
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=True)
    run_pre_apply_doctor(
        tmp_path, profile_name="python-service", scope=scope, allow_blocking=False
    )


def test_pass_when_only_low_or_medium_findings(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Low/medium are not in the blocking set even if unfiltered."""
    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(_finding(check="shape/fabricated", severity="medium"),),
    )
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=False, sync_labels=False, sync_protection=False)
    run_pre_apply_doctor(
        tmp_path, profile_name="python-service", scope=scope, allow_blocking=False
    )


def test_blocks_on_unfiltered_high(mocker: MockerFixture, tmp_path: Path) -> None:
    from gh_manage.doctor import checks  # noqa: F401

    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(
            _finding(check="shape/required-contexts-match", severity="high"),
        ),
    )
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=False)
    with pytest.raises(click.ClickException) as exc_info:
        run_pre_apply_doctor(
            tmp_path, profile_name="python-service", scope=scope, allow_blocking=False
        )
    assert "Pre-apply doctor" in str(exc_info.value.message)
    assert "--allow-blocking" in str(exc_info.value.message)


def test_blocks_on_unfiltered_critical(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(_finding(check="shape/fabricated", severity="critical"),),
    )
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=False, sync_labels=False, sync_protection=False)
    with pytest.raises(click.ClickException):
        run_pre_apply_doctor(
            tmp_path, profile_name="python-service", scope=scope, allow_blocking=False
        )


def test_allow_blocking_bypasses_block(
    mocker: MockerFixture, tmp_path: Path, capsys
) -> None:
    from gh_manage.doctor import checks  # noqa: F401

    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(
            _finding(check="shape/required-contexts-match", severity="high"),
        ),
    )
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=False)
    run_pre_apply_doctor(
        tmp_path, profile_name="python-service", scope=scope, allow_blocking=True
    )
    captured = capsys.readouterr()
    assert "--allow-blocking" in captured.err
    assert "blocking finding" in captured.err


def test_setup_error_propagates(mocker: MockerFixture, tmp_path: Path) -> None:
    """DoctorError from run_on_path (profile missing, repos.yml corrupt,
    etc.) propagates to the caller without being swallowed."""
    from gh_manage.doctor.errors import DoctorError

    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        side_effect=DoctorError("profile not found"),
    )
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=True)
    with pytest.raises(DoctorError):
        run_pre_apply_doctor(
            tmp_path, profile_name="bogus", scope=scope, allow_blocking=False
        )
