"""Regression test for populating live_required_contexts in ScanContext.

Before this fix, `_scan_single_repo` built a ScanContext without
populating `live_required_contexts`, so the doctor-bridged check
`shape/required-contexts-match` always saw an empty tuple and reported
every profile-declared required context as "missing" on every repo.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gh_manage.drift_sync.context import ScanContext
from gh_manage.github_client import GhNotFoundError


@pytest.fixture
def mock_deps_with_protection(monkeypatch):
    """Set up heavy-dependency mocks for _scan_single_repo with a profile
    that declares a protection_policy (so the live-contexts fetch path fires)."""
    from gh_manage.commands import drift as drift_cmd

    fake_profile = MagicMock()
    fake_profile.protection_policy = "standard"
    fake_profile.name = "python-service"
    fake_labels_config = MagicMock()
    fake_policy = MagicMock()
    fake_bp_config = MagicMock(policies={"standard": fake_policy})

    def _load(path, cls):
        if cls.__name__ == "ProfileSpec":
            return fake_profile
        if cls.__name__ == "BranchProtectionConfig":
            return fake_bp_config
        return fake_labels_config

    monkeypatch.setattr(drift_cmd.repo_info, "get_default_branch", lambda repo: "main")
    monkeypatch.setattr(drift_cmd, "load_config", _load)
    monkeypatch.setattr(
        drift_cmd, "resolve_profile_path", lambda name: "/tmp/fake-profile.yml"
    )
    monkeypatch.setattr(
        drift_cmd, "resolve_default_labels_path", lambda: "/tmp/fake-labels.yml"
    )
    monkeypatch.setattr(
        drift_cmd, "resolve_branch_protection_path", lambda: "/tmp/fake-bp.yml"
    )
    monkeypatch.setattr(
        drift_cmd.drift_sync, "format_stdout_report", lambda findings: "report"
    )
    monkeypatch.setattr(
        drift_cmd.drift_sync, "_filter_by_severity", lambda findings, sev: findings
    )
    return drift_cmd


def _capture_ctx_stub(captured: dict, key: str):
    """run_all_checks stub that snapshots the ScanContext it was called with."""

    def _stub(ctx: ScanContext):
        captured[key] = ctx
        return ()

    return _stub


def test_live_required_contexts_populated_when_protection_exists(
    mock_deps_with_protection, monkeypatch
):
    drift_cmd = mock_deps_with_protection

    monkeypatch.setattr(
        drift_cmd.protection_api,
        "get_branch_protection",
        lambda repo, branch: {
            "required_status_checks": {
                "contexts": ["PR Gate / PR Gate", "lint"],
                "strict": True,
            }
        },
    )

    captured: dict[str, ScanContext] = {}
    monkeypatch.setattr(
        drift_cmd.drift_sync, "run_all_checks", _capture_ctx_stub(captured, "ctx")
    )
    drift_cmd._scan_single_repo(
        "owner/repo", "python-service", "low", "stdout", None, skip_profile_check=True
    )
    ctx = captured["ctx"]
    assert ctx.live_required_contexts == ("PR Gate / PR Gate", "lint")


def test_live_required_contexts_empty_when_protection_404(
    mock_deps_with_protection, monkeypatch
):
    drift_cmd = mock_deps_with_protection

    def _raise_404(*a, **kw):
        raise GhNotFoundError("404 no protection configured")

    monkeypatch.setattr(drift_cmd.protection_api, "get_branch_protection", _raise_404)

    captured: dict[str, ScanContext] = {}
    monkeypatch.setattr(
        drift_cmd.drift_sync, "run_all_checks", _capture_ctx_stub(captured, "ctx")
    )
    drift_cmd._scan_single_repo(
        "owner/repo", "python-service", "low", "stdout", None, skip_profile_check=True
    )
    ctx = captured["ctx"]
    assert ctx.live_required_contexts == ()


def test_live_required_contexts_empty_when_profile_has_no_policy(monkeypatch):
    """If profile.protection_policy is None, we don't fetch protection at all
    — live_required_contexts stays at its default empty tuple."""
    from gh_manage.commands import drift as drift_cmd

    fake_profile = MagicMock(protection_policy=None)
    fake_profile.name = "python-service"
    fake_labels_config = MagicMock()

    monkeypatch.setattr(drift_cmd.repo_info, "get_default_branch", lambda repo: "main")
    monkeypatch.setattr(
        drift_cmd,
        "load_config",
        lambda path, cls: (
            fake_profile if "profile" in str(path) else fake_labels_config
        ),
    )
    monkeypatch.setattr(
        drift_cmd, "resolve_profile_path", lambda name: "/tmp/fake-profile.yml"
    )
    monkeypatch.setattr(
        drift_cmd, "resolve_default_labels_path", lambda: "/tmp/fake-labels.yml"
    )
    monkeypatch.setattr(
        drift_cmd.drift_sync, "format_stdout_report", lambda findings: "report"
    )
    monkeypatch.setattr(
        drift_cmd.drift_sync, "_filter_by_severity", lambda findings, sev: findings
    )

    # Sentinel: if protection_api.get_branch_protection IS called, fail the test.
    def _should_not_be_called(*a, **kw):
        raise AssertionError(
            "protection_api.get_branch_protection called when profile has no protection_policy"
        )

    monkeypatch.setattr(
        drift_cmd.protection_api, "get_branch_protection", _should_not_be_called
    )

    captured: dict[str, ScanContext] = {}
    monkeypatch.setattr(
        drift_cmd.drift_sync, "run_all_checks", _capture_ctx_stub(captured, "ctx")
    )
    drift_cmd._scan_single_repo(
        "owner/repo", "python-service", "low", "stdout", None, skip_profile_check=True
    )
    ctx = captured["ctx"]
    assert ctx.live_required_contexts == ()
