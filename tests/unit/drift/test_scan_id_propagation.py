"""Tests for scan_id ContextVar propagation via _scan_single_repo."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from gh_manage.drift_sync.context import scan_id_var


@pytest.fixture
def mock_scan_deps(monkeypatch):
    """Patch heavy dependencies of _scan_single_repo."""
    from gh_manage.commands import drift as drift_cmd

    mock_profile = MagicMock(protection_policy=None)
    mock_labels_config = MagicMock()

    monkeypatch.setattr(drift_cmd.repo_info, "get_default_branch", lambda repo: "main")
    monkeypatch.setattr(
        drift_cmd,
        "load_config",
        lambda path, cls: (
            mock_profile if "profile" in str(path) else mock_labels_config
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
    return drift_cmd


def _make_capturing_stub(captured: dict, key: str):
    def _stub(ctx):
        captured[key] = scan_id_var.get()
        return ()

    return _stub


def test_scan_id_set_at_single_repo_entry(mock_scan_deps, monkeypatch):
    drift_cmd = mock_scan_deps
    captured: dict = {}
    monkeypatch.setattr(
        drift_cmd.drift_sync, "run_all_checks", _make_capturing_stub(captured, "a")
    )
    drift_cmd._scan_single_repo(
        "owner/repo",
        "python-service",
        "low",
        "stdout",
        None,
        skip_profile_check=True,
    )
    sid = captured["a"]
    uuid.UUID(sid, version=4)


def test_scan_id_reset_after_single_repo_exit(mock_scan_deps, monkeypatch):
    drift_cmd = mock_scan_deps
    monkeypatch.setattr(drift_cmd.drift_sync, "run_all_checks", lambda ctx: ())
    drift_cmd._scan_single_repo(
        "owner/repo",
        "python-service",
        "low",
        "stdout",
        None,
        skip_profile_check=True,
    )
    assert scan_id_var.get() == ""


def test_scan_id_reset_even_on_exception(mock_scan_deps, monkeypatch):
    drift_cmd = mock_scan_deps

    def _raise(ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(drift_cmd.drift_sync, "run_all_checks", _raise)
    with pytest.raises(RuntimeError, match="boom"):
        drift_cmd._scan_single_repo(
            "owner/repo",
            "python-service",
            "low",
            "stdout",
            None,
            skip_profile_check=True,
        )
    assert scan_id_var.get() == ""


def test_scan_id_differs_across_sequential_scans_in_same_thread(
    mock_scan_deps, monkeypatch
):
    drift_cmd = mock_scan_deps
    captured: dict = {}
    monkeypatch.setattr(
        drift_cmd.drift_sync, "run_all_checks", _make_capturing_stub(captured, "seq")
    )
    drift_cmd._scan_single_repo(
        "owner/repo-1",
        "python-service",
        "low",
        "stdout",
        None,
        skip_profile_check=True,
    )
    first = captured["seq"]
    drift_cmd._scan_single_repo(
        "owner/repo-2",
        "python-service",
        "low",
        "stdout",
        None,
        skip_profile_check=True,
    )
    second = captured["seq"]
    assert first != second
    uuid.UUID(first, version=4)
    uuid.UUID(second, version=4)


def test_scan_id_isolated_per_worker_thread(mock_scan_deps, monkeypatch):
    drift_cmd = mock_scan_deps
    captured: dict = {}
    lock = threading.Lock()
    counter = {"n": 0}

    def _stub(ctx):
        with lock:
            counter["n"] += 1
            key = f"worker_{counter['n']}"
        captured[key] = scan_id_var.get()
        return ()

    monkeypatch.setattr(drift_cmd.drift_sync, "run_all_checks", _stub)

    def _call():
        drift_cmd._scan_single_repo(
            "owner/repo",
            "python-service",
            "low",
            "stdout",
            None,
            skip_profile_check=True,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_call) for _ in range(2)]
        for f in futures:
            f.result()

    vals = list(captured.values())
    assert len(vals) == 2
    assert vals[0] != vals[1]
    for v in vals:
        uuid.UUID(v, version=4)
    assert scan_id_var.get() == ""
