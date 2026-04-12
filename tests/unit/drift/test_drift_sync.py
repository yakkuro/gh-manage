"""Tests for gh_manage.drift_sync — drift scanner engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gh_manage.config import load_config
from gh_manage.drift_sync import (
    DriftError,
    DriftOutputError,
    Finding,
    ScanContext,
    _CHECKS,
    _filter_by_severity,
    _labels_diff_to_findings,
    check_labels,
    register_check,
    run_all_checks,
)
from gh_manage.github_api.labels import Label, Label as LabelInfo
from gh_manage.labels_sync import (
    LabelCreate,
    LabelDelete,
    LabelsDiff,
    LabelUpdate,
)
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.labels import CategorySpec, LabelSpec, LabelsConfig
from gh_manage.models.profiles import ProfileSpec
from tests.unit.drift.conftest import (
    DriftScenario,
    ExpectedFinding,
    read_template_for,
)


def _make_labels_config() -> LabelsConfig:
    """Helper: create a valid minimal LabelsConfig for tests."""
    return LabelsConfig(
        version=1,
        categories={
            "priority": CategorySpec(
                description="Priority levels",
                labels=[LabelSpec(name="critical", color="ff0000")],
            )
        },
    )


# Data classes
def test_finding_is_frozen() -> None:
    f = Finding(
        severity="high",
        check="labels",
        repo="yakkuro/gh-manage",
        field_path="labels[priority/critical]",
        current_value=None,
        desired_value="priority/critical",
        message="Missing label",
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        f.severity = "low"  # type: ignore[misc]


def test_finding_has_remediation_default_none() -> None:
    f = Finding(
        severity="high",
        check="labels",
        repo="yakkuro/gh-manage",
        field_path="labels[x]",
        current_value=None,
        desired_value="x",
        message="m",
    )
    assert f.remediation is None


def test_finding_accepts_remediation_string() -> None:
    f = Finding(
        severity="high",
        check="labels",
        repo="yakkuro/gh-manage",
        field_path="labels[x]",
        current_value=None,
        desired_value="x",
        message="m",
        remediation="gh manage labels sync . --apply",
    )
    assert f.remediation == "gh manage labels sync . --apply"


def test_finding_equality_and_hashability() -> None:
    f1 = Finding("high", "labels", "yakkuro/gh-manage", "x", None, "y", "m")
    f2 = Finding("high", "labels", "yakkuro/gh-manage", "x", None, "y", "m")
    assert f1 == f2
    assert hash(f1) == hash(f2)


def test_scan_context_is_frozen(tmp_path: Path) -> None:
    profile = ProfileSpec(version=1, name="test", files=[])
    labels_config = _make_labels_config()
    ctx = ScanContext(
        path=tmp_path,
        repo="yakkuro/gh-manage",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=None,
    )
    with pytest.raises(Exception):
        ctx.repo = "other"  # type: ignore[misc]


# Error hierarchy
def test_all_errors_inherit_drift_error() -> None:
    assert issubclass(DriftOutputError, DriftError)


def test_drift_output_error_message_includes_context() -> None:
    err = DriftOutputError("Cannot write to /tmp/x: Permission denied")
    assert "Cannot write" in str(err)


# Registry
def test_register_check_appends_to_global_list() -> None:
    initial_count = len(_CHECKS)

    def my_check(ctx: ScanContext) -> tuple[Finding, ...]:
        return ()

    register_check(my_check)
    assert my_check in _CHECKS
    _CHECKS.remove(my_check)
    assert len(_CHECKS) == initial_count


def test_register_check_returns_function(tmp_path: Path) -> None:
    def my_check(ctx: ScanContext) -> tuple[Finding, ...]:
        return ()

    result = register_check(my_check)
    assert result is my_check
    _CHECKS.remove(my_check)


def test_run_all_checks_calls_every_registered_check(tmp_path: Path) -> None:
    called: list[str] = []

    def check_a(ctx: ScanContext) -> tuple[Finding, ...]:
        called.append("a")
        return ()

    def check_b(ctx: ScanContext) -> tuple[Finding, ...]:
        called.append("b")
        return (Finding("low", "test", ctx.repo, "x", None, "y", "m"),)

    register_check(check_a)
    register_check(check_b)

    try:
        profile = ProfileSpec(version=1, name="test", files=[])
        labels_config = _make_labels_config()
        ctx = ScanContext(
            path=tmp_path,
            repo="yakkuro/gh-manage",
            default_branch="main",
            profile=profile,
            labels_config=labels_config,
            bp_config=None,
        )
        findings = run_all_checks(ctx)
        assert "a" in called
        assert "b" in called
        assert any(f.check == "test" for f in findings)
    finally:
        _CHECKS.remove(check_a)
        _CHECKS.remove(check_b)


# Filter by severity


def _f(severity: str) -> Finding:
    return Finding(
        severity=severity,  # type: ignore[arg-type]
        check="test",
        repo="yakkuro/gh-manage",
        field_path="x",
        current_value=None,
        desired_value="y",
        message="m",
    )


def test_filter_by_severity_keeps_matching_and_higher() -> None:
    findings = (_f("critical"), _f("high"), _f("medium"), _f("low"))
    result = _filter_by_severity(findings, "high")
    assert len(result) == 2
    assert result[0].severity == "critical"
    assert result[1].severity == "high"


def test_filter_by_severity_empty_input() -> None:
    assert _filter_by_severity((), "low") == ()


def test_filter_by_severity_low_keeps_everything() -> None:
    findings = (_f("critical"), _f("high"), _f("medium"), _f("low"))
    result = _filter_by_severity(findings, "low")
    assert len(result) == 4


def test_filter_by_severity_critical_keeps_only_critical() -> None:
    findings = (_f("critical"), _f("high"), _f("medium"), _f("low"))
    result = _filter_by_severity(findings, "critical")
    assert len(result) == 1
    assert result[0].severity == "critical"


def test_filter_by_severity_preserves_order() -> None:
    findings = (_f("low"), _f("high"), _f("low"), _f("critical"))
    result = _filter_by_severity(findings, "high")
    assert [f.severity for f in result] == ["high", "critical"]


# Conftest smoke test
def test_drift_scenario_conftest_importable() -> None:
    """Sanity check: conftest module imports cleanly and exposes the
    DriftScenario model."""
    from tests.unit.drift import conftest

    assert hasattr(conftest, "DriftScenario")
    assert hasattr(conftest, "_load_scenarios")
    assert hasattr(conftest, "read_template_for")


# Task 5: check_labels adapter unit tests


def test_labels_diff_to_findings_creates_are_high_severity() -> None:  # noqa: E501
    diff = LabelsDiff(
        renames=(),
        creates=(LabelCreate(Label("priority/critical", "b60205", "crit")),),
        updates=(),
        deletes=(),
    )
    findings = _labels_diff_to_findings(diff, "yakkuro/gh-manage")
    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].check == "labels"
    assert findings[0].repo == "yakkuro/gh-manage"
    assert "priority/critical" in findings[0].field_path
    assert "missing" in findings[0].message.lower()
    assert findings[0].remediation is not None
    assert "labels sync" in findings[0].remediation


def test_labels_diff_to_findings_deletes_are_low_severity() -> None:
    diff = LabelsDiff(
        renames=(),
        creates=(),
        updates=(),
        deletes=(LabelDelete("custom/extra"),),
    )
    findings = _labels_diff_to_findings(diff, "yakkuro/gh-manage")
    assert len(findings) == 1
    assert findings[0].severity == "low"
    assert "custom/extra" in findings[0].field_path
    # No remediation for deletes (spec says: don't propose deletion)
    assert findings[0].remediation is None


def test_labels_diff_to_findings_updates_are_medium_severity() -> None:
    # An update represents a color or description change. In Phase 5's
    # LabelsDiff, LabelUpdate carries the full Label object — the test
    # cannot easily distinguish color vs description from the Label
    # object alone, so the adapter emits severity=medium for all
    # updates regardless. If the spec later requires color (medium) vs
    # description (low) distinction, the LabelsDiff model would need
    # to carry that information.
    diff = LabelsDiff(
        renames=(),
        creates=(),
        updates=(LabelUpdate(Label("type/bug", "d93f0b", "Something broken")),),
        deletes=(),
    )
    findings = _labels_diff_to_findings(diff, "yakkuro/gh-manage")
    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert "type/bug" in findings[0].field_path


def test_labels_diff_to_findings_empty_diff_emits_no_findings() -> None:
    diff = LabelsDiff(renames=(), creates=(), updates=(), deletes=())
    findings = _labels_diff_to_findings(diff, "yakkuro/gh-manage")
    assert findings == ()


# Task 5: test_scenario parametrized function


def _matches(actual: Finding, expected: ExpectedFinding) -> bool:
    if actual.severity != expected.severity:
        return False
    if actual.check != expected.check:
        return False
    if (
        expected.field_path_contains
        and expected.field_path_contains not in actual.field_path
    ):
        return False
    if expected.message_contains and expected.message_contains not in actual.message:
        return False
    return True


def _resolve_profile_path_for_test(name: str) -> Path:
    from importlib.resources import files

    return Path(str(files("gh_manage.data.profiles") / f"{name}.yml"))


def _resolve_labels_config_path() -> Path:
    from importlib.resources import files

    return Path(str(files("gh_manage.data") / "labels.yml"))


def _resolve_bp_config_path() -> Path:
    from importlib.resources import files

    return Path(str(files("gh_manage.data") / "branch-protection.yml"))


def test_scenario(
    drift_scenario: tuple[Path, DriftScenario],
    mocker: Any,
    tmp_path: Path,
) -> None:
    """Test scenario runner. Deferred imports allow Task 5 to run before
    Task 7/8 implement check_protection and check_profile_files."""
    # Deferred imports so Task 5 doesn't need check_protection /
    # check_profile_files to exist yet — they land in Tasks 7 and 8.

    try:
        from gh_manage.drift_sync import check_protection
    except ImportError:
        check_protection = None  # type: ignore[assignment]
    try:
        from gh_manage.drift_sync import check_profile_files
    except ImportError:
        check_profile_files = None  # type: ignore[assignment]

    _, scenario = drift_scenario

    check_fn = {
        "labels": check_labels,
        "protection": check_protection,
        "profile_files": check_profile_files,
    }[scenario.check]

    if check_fn is None:
        pytest.skip(
            f"Check {scenario.check!r} not yet implemented (scenario: {scenario.name})"
        )

    # Load the profile and bundled configs
    profile = load_config(_resolve_profile_path_for_test(scenario.profile), ProfileSpec)
    labels_config = load_config(_resolve_labels_config_path(), LabelsConfig)
    bp_config = load_config(_resolve_bp_config_path(), BranchProtectionConfig)

    # Build the tmp repo tree
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    if scenario.inputs.repo_files:
        for rel_path, content in scenario.inputs.repo_files.items():
            if content == "__USE_TEMPLATE__":
                content = read_template_for(scenario.profile, rel_path)
            target = repo_path / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    # Mock API boundaries based on check
    if scenario.inputs.current_labels is not None:
        mock_labels = [
            LabelInfo(
                name=lbl["name"],
                color=lbl["color"].lower(),
                description=lbl.get("description") or "",
            )
            for lbl in scenario.inputs.current_labels
        ]
        mocker.patch(
            "gh_manage.drift_sync.labels_api.list_labels",
            return_value=mock_labels,
        )
    if scenario.inputs.current_protection is not None:
        mocker.patch(
            "gh_manage.drift_sync.protection_api.get_branch_protection",
            return_value=scenario.inputs.current_protection,
        )

    ctx = ScanContext(
        path=repo_path,
        repo=scenario.repo,
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=bp_config,
    )

    findings = check_fn(ctx)

    # Order-independent comparison: every expected must be matched,
    # and no extras.
    assert len(findings) == len(scenario.expected_findings), (
        f"Expected {len(scenario.expected_findings)} findings, "
        f"got {len(findings)}: {[str(f) for f in findings]}"
    )
    for expected in scenario.expected_findings:
        matches = [f for f in findings if _matches(f, expected)]
        assert (
            matches
        ), f"No finding matches expected {expected}; got: {[str(f) for f in findings]}"


# Task 6: _protection_diff_to_findings adapter


def test_protection_diff_to_findings_downgrade_is_critical() -> None:
    from gh_manage.drift_sync import _protection_diff_to_findings
    from gh_manage.protection_sync import (
        DowngradeFinding,
        ProtectionDiff,
        ProtectionFieldChange,
    )

    diff = ProtectionDiff(
        changes=(ProtectionFieldChange("enforce_admins", True, False),),
        downgrades=(
            DowngradeFinding(
                field_path="enforce_admins",
                current_value=True,
                desired_value=False,
                reason="admin enforcement disabled",
            ),
        ),
        current_raw={},
        desired_raw={},
    )
    findings = _protection_diff_to_findings(diff, "yakkuro/gh-manage")
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].check == "protection"
    assert "enforce_admins" in findings[0].field_path
    assert findings[0].remediation is not None
    assert "protection sync" in findings[0].remediation


def test_protection_diff_to_findings_non_downgrade_is_medium() -> None:
    from gh_manage.drift_sync import _protection_diff_to_findings
    from gh_manage.protection_sync import ProtectionDiff, ProtectionFieldChange

    # A change that is NOT classified as a downgrade (e.g., upgrade)
    diff = ProtectionDiff(
        changes=(ProtectionFieldChange("allow_force_pushes", True, False),),
        downgrades=(),  # not a downgrade — current was weaker
        current_raw={},
        desired_raw={},
    )
    findings = _protection_diff_to_findings(diff, "yakkuro/gh-manage")
    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert "allow_force_pushes" in findings[0].field_path


def test_protection_diff_to_findings_empty_diff() -> None:
    from gh_manage.drift_sync import _protection_diff_to_findings
    from gh_manage.protection_sync import ProtectionDiff

    diff = ProtectionDiff(changes=(), downgrades=(), current_raw={}, desired_raw={})
    assert _protection_diff_to_findings(diff, "yakkuro/gh-manage") == ()


# Task 9: Golden test (self-dogfood)


def test_golden_production_data_zero_drift(mocker: Any, tmp_path: Path) -> None:
    """Self-dogfood golden test: when the production config is loaded
    and the mocked API returns the exact same state, run_all_checks
    returns zero findings.

    This is the "baseline" test — any Phase 8+ change that breaks the
    identity property (equal state → zero findings) fails here.
    """
    from importlib.resources import files

    from gh_manage.drift_sync import (
        check_labels,
        check_profile_files,
        check_protection,
    )
    from gh_manage.models.branch_protection import BranchProtectionConfig
    from gh_manage.models.labels import LabelsConfig
    from gh_manage.models.profiles import ProfileSpec
    from gh_manage.protection_sync import build_desired_protection

    # Load bundled configs
    profile = load_config(
        Path(str(files("gh_manage.data.profiles") / "python-service.yml")),
        ProfileSpec,
    )
    labels_config = load_config(
        Path(str(files("gh_manage.data") / "labels.yml")),
        LabelsConfig,
    )
    bp_config = load_config(
        Path(str(files("gh_manage.data") / "branch-protection.yml")),
        BranchProtectionConfig,
    )

    # Build a tmp repo with every profile.files entry materialized from
    # its template (so check_profile_files sees zero drift).
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    for entry in profile.files:
        template_root = Path(str(files("gh_manage.data") / "templates"))
        content = (template_root / entry.source).read_text(encoding="utf-8")
        local = repo_path / entry.dest
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(content, encoding="utf-8")

    # Mock labels API to return exactly the bundled labels.yml content.
    from gh_manage.labels_sync import _flatten_desired, _spec_to_label  # type: ignore[attr-defined]

    bundled_labels = [_spec_to_label(spec) for spec in _flatten_desired(labels_config)]
    mocker.patch(
        "gh_manage.drift_sync.labels_api.list_labels",
        return_value=bundled_labels,
    )

    # Mock protection API to return the exact shape that
    # build_desired_protection would PUT — that way compute_diff sees
    # no changes.
    policy = bp_config.policies[profile.protection_policy]  # type: ignore[index]
    desired_put_body = build_desired_protection(policy, profile)

    # GitHub's GET response wraps enforce_admins etc. in {enabled: bool}.
    # For the test, we can pass a synthetic current_raw that normalizes
    # to the same canonical shape as desired.
    mocker.patch(
        "gh_manage.drift_sync.protection_api.get_branch_protection",
        return_value={
            "enforce_admins": {"enabled": desired_put_body["enforce_admins"]},
            "required_status_checks": desired_put_body["required_status_checks"],
            "required_pull_request_reviews": desired_put_body[
                "required_pull_request_reviews"
            ],
            "required_conversation_resolution": {
                "enabled": desired_put_body["required_conversation_resolution"]
            },
            "required_linear_history": {
                "enabled": desired_put_body["required_linear_history"]
            },
            "allow_force_pushes": {"enabled": desired_put_body["allow_force_pushes"]},
            "allow_deletions": {"enabled": desired_put_body["allow_deletions"]},
        },
    )

    ctx = ScanContext(
        path=repo_path,
        repo="yakkuro/gh-manage",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=bp_config,
    )

    # Run each check individually to make failures easier to diagnose
    labels_findings = check_labels(ctx)
    assert labels_findings == (), f"check_labels drift: {labels_findings}"

    protection_findings = check_protection(ctx)
    assert protection_findings == (), f"check_protection drift: {protection_findings}"

    files_findings = check_profile_files(ctx)
    assert files_findings == (), f"check_profile_files drift: {files_findings}"
