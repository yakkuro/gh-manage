"""Regression guards for the log points added in cli/v1.8.0.

Each test uses pytest's caplog fixture (which captures records
regardless of stream or handler, so tests don't need configure_logging).
These tests pin each log point's logger name, level, and key content,
so future refactors that silently drop a log emission will fail.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def _propagate_gh_manage_logger():
    """caplog captures records via the root logger. configure_logging
    disables propagation on `gh_manage` to avoid duplicate output in
    production. Re-enable propagation inside tests so caplog sees our
    records.
    """
    gh_logger = logging.getLogger("gh_manage")
    prev = gh_logger.propagate
    gh_logger.propagate = True
    yield
    gh_logger.propagate = prev


def _make_scan_context(tmp_path: Path):
    from gh_manage.drift_sync import ScanContext
    from gh_manage.models.labels import CategorySpec, LabelSpec, LabelsConfig
    from gh_manage.models.profiles import ProfileSpec

    labels_config = LabelsConfig(
        version=1,
        categories={
            "sentinel": CategorySpec(
                description="test category",
                labels=[LabelSpec(name="sentinel", color="ffffff")],
            ),
        },
    )
    profile = ProfileSpec(
        version=1,
        name="python-service",
        description="test",
        files=[],
        protection_policy=None,
    )
    return ScanContext(
        path=tmp_path,
        repo="yakkuro/sentinel-repo",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=None,
    )


def test_check_protection_warns_on_not_found(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """check_protection: GhNotFoundError fallback now emits WARNING
    (spec §4 behavior change; new log line, unchanged findings)."""
    from gh_manage.drift_sync import ScanContext
    from gh_manage.drift_sync.checks import check_protection
    from gh_manage.github_client import GhNotFoundError
    from gh_manage.models.branch_protection import (
        BranchProtectionConfig,
        PolicySpec,
        RequiredStatusChecks,
    )
    from gh_manage.models.labels import CategorySpec, LabelSpec, LabelsConfig
    from gh_manage.models.profiles import ProfileSpec

    # Profile WITH a protection policy, so the code reaches the API call.
    policy = PolicySpec(
        description="solo default",
        target_branches=["main"],
        required_status_checks=RequiredStatusChecks(
            strict=True, contexts=["PR Gate / PR Gate"]
        ),
        enforce_admins=False,
        required_pull_request_reviews=None,
        required_conversation_resolution=False,
        required_linear_history=False,
        allow_force_pushes=False,
        allow_deletions=False,
    )
    bp_config = BranchProtectionConfig(version=1, policies={"solo-default": policy})
    profile = ProfileSpec(
        version=1,
        name="python-service",
        description="test",
        files=[],
        protection_policy="solo-default",
    )
    labels_config = LabelsConfig(
        version=1,
        categories={
            "sentinel": CategorySpec(
                description="test",
                labels=[LabelSpec(name="sentinel", color="ffffff")],
            ),
        },
    )
    ctx = ScanContext(
        path=tmp_path,
        repo="yakkuro/sentinel-repo",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=bp_config,
    )

    mocker.patch(
        "gh_manage.drift_sync.checks.protection_api.get_branch_protection",
        side_effect=GhNotFoundError("not found"),
    )

    with caplog.at_level(logging.WARNING, logger="gh_manage.drift_sync.checks"):
        check_protection(ctx)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "branch protection not configured" in r.getMessage() for r in warnings
    ), f"expected WARNING about branch protection, got: {[r.getMessage() for r in warnings]}"


def test_parse_zero_findings_warns_on_malformed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#62 HIGH #3 regression guard: malformed timestamps no longer
    silently swallowed."""
    from gh_manage.drift_sync.issue_state import parse_zero_findings_timestamps

    comments = [
        {"body": "<!-- scan:zero-findings:2026-04-19T09:00:00 -->"},
        {"body": "<!-- scan:zero-findings:NOT_A_DATE -->"},
    ]
    with caplog.at_level(logging.WARNING, logger="gh_manage.drift_sync.issue_state"):
        result = parse_zero_findings_timestamps(comments)

    # Only the valid timestamp survives.
    assert len(result) == 1

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "expected a WARNING for the malformed timestamp"
    assert "malformed" in warnings[0].getMessage().lower()
    assert "NOT_A_DATE" in warnings[0].getMessage()


def test_resolve_drift_issue_logs_created_event(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from gh_manage.drift_sync.issue_state import resolve_drift_issue
    from gh_manage.findings import Finding

    mocker.patch("gh_manage.drift_sync.issues_api.ensure_drift_label")
    mocker.patch(
        "gh_manage.drift_sync.issues_api.search_drift_issue", return_value=None
    )
    mocker.patch(
        "gh_manage.drift_sync.issues_api.create_issue", return_value={"number": 42}
    )
    mocker.patch("gh_manage.drift_sync.issues_api.add_issue_comment")

    findings = (
        Finding(
            severity="high",
            check="labels",
            repo="yakkuro/sentinel",
            field_path="labels[x]",
            current_value=None,
            desired_value="x",
            message="missing",
            remediation=None,
        ),
    )
    with caplog.at_level(logging.INFO, logger="gh_manage.drift_sync.issue_state"):
        resolve_drift_issue(findings, "yakkuro/sentinel", "2026-04-19T10:00:00")

    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("created drift issue #42" in m for m in msgs)


def test_resolve_drift_issue_logs_updated_event(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from gh_manage.drift_sync.issue_state import resolve_drift_issue
    from gh_manage.findings import Finding

    mocker.patch("gh_manage.drift_sync.issues_api.ensure_drift_label")
    mocker.patch(
        "gh_manage.drift_sync.issues_api.search_drift_issue",
        return_value={"number": 99},
    )
    mocker.patch("gh_manage.drift_sync.issues_api.update_issue_body")
    mocker.patch("gh_manage.drift_sync.issues_api.add_issue_comment")

    findings = (
        Finding(
            severity="medium",
            check="labels",
            repo="yakkuro/sentinel",
            field_path="labels[y]",
            current_value=None,
            desired_value="y",
            message="drifted",
            remediation=None,
        ),
    )
    with caplog.at_level(logging.INFO, logger="gh_manage.drift_sync.issue_state"):
        resolve_drift_issue(findings, "yakkuro/sentinel", "2026-04-19T10:00:00")

    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("updated drift issue #99" in m for m in msgs)


def test_resolve_drift_issue_logs_closed_event(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from gh_manage.drift_sync.issue_state import resolve_drift_issue

    mocker.patch("gh_manage.drift_sync.issues_api.ensure_drift_label")
    mocker.patch(
        "gh_manage.drift_sync.issues_api.search_drift_issue",
        return_value={"number": 7},
    )
    mocker.patch("gh_manage.drift_sync.issues_api.update_issue_body")
    mocker.patch("gh_manage.drift_sync.issues_api.add_issue_comment")
    mocker.patch(
        "gh_manage.drift_sync.issues_api.get_issue_comments",
        return_value=[
            {"body": "<!-- scan:zero-findings:2026-04-19T10:00:00 -->"},
            {"body": "<!-- scan:zero-findings:2026-04-18T09:59:00 -->"},
        ],
    )
    mocker.patch("gh_manage.drift_sync.issues_api.close_issue")

    with caplog.at_level(logging.INFO, logger="gh_manage.drift_sync.issue_state"):
        resolve_drift_issue((), "yakkuro/sentinel", "2026-04-19T10:00:00")

    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("closed drift issue #7" in m for m in msgs)


def test_worker_logs_exception_with_traceback(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#62 HIGH #5 regression guard: unexpected exceptions in the
    parallel worker now leave a traceback in the logs.

    Tests the actual module-level `_scan_worker` (not a test replica),
    so removal or regression of the production log.exception call will
    fail this test (addresses Codex review MEDIUM #1).
    """
    import gh_manage.commands.drift as drift_cmd
    from gh_manage.models.repos import RepoEntry

    mocker.patch.object(
        drift_cmd,
        "_scan_single_repo",
        side_effect=TypeError("sentinel"),
    )

    entry = RepoEntry(name="yakkuro/sentinel-repo", profile="python-service")

    with caplog.at_level(logging.ERROR, logger="gh_manage.commands.drift"):
        name, status, payload = drift_cmd._scan_worker(entry, "low", "stdout", None)

    assert name == "yakkuro/sentinel-repo"
    assert status == "FAILED"
    assert isinstance(payload, TypeError)

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors, "expected an ERROR record for the unexpected exception"
    last = errors[-1]
    assert last.name == "gh_manage.commands.drift"
    assert last.exc_info is not None
    assert last.exc_info[0] is TypeError


def test_debug_events_hidden_at_warning_level(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """Default configure_logging() level (WARNING) suppresses DEBUG
    emissions at the logger itself, before any handler sees them. If
    configure_logging's default is broken to DEBUG, this test fails.

    Drives the actual production configuration (addresses Codex review
    MEDIUM #2: the previous version used caplog.at_level to force
    WARNING, making the test tautological).
    """
    import io

    from gh_manage.drift_sync import run_all_checks
    from gh_manage.logging_config import configure_logging

    mocker.patch("gh_manage.drift_sync.checks.labels_api.list_labels", return_value=[])
    mocker.patch(
        "gh_manage.drift_sync.checks.protection_api.get_branch_protection",
        return_value={},
    )

    ctx = _make_scan_context(tmp_path)

    # Call configure_logging WITHOUT a level arg so the defaulting path
    # is exercised; writes to a StringIO so we can inspect emitted text.
    buf = io.StringIO()
    configure_logging(stream=buf)  # default level="warning"

    run_all_checks(ctx)

    emitted = buf.getvalue()
    assert "DEBUG" not in emitted, (
        "DEBUG line reached the configured handler — configure_logging's "
        f"default level is not filtering them. Output:\n{emitted}"
    )
