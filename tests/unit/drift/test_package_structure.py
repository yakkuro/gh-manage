"""Regression guards for the drift_sync package split (cli/v1.7.0).

Protects the backward-compat contract from silent regressions:
1. reexports_complete — every public symbol still importable
2. mock_path_identity — module-attribute bindings resolve correctly
3. mock_patch_reaches_checks — functional mock flow still works
4. checks_registration — @register_check fired for all 3 drift checks
5. submodules_do_not_import_from_package_root — DAG discipline
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from pytest_mock import MockerFixture


def test_drift_sync_reexports_are_complete() -> None:
    from gh_manage import drift_sync

    # Backward-compat module attributes (test mocks depend on these)
    assert hasattr(drift_sync, "labels_api")
    assert hasattr(drift_sync, "protection_api")
    assert hasattr(drift_sync, "issues_api")

    # Public symbols
    for name in (
        "ScanContext",
        "DriftError",
        "DriftOutputError",
        "Finding",
        "Severity",
        "CheckFn",
        "register_check",
        "run_all_checks",
        "check_labels",
        "check_protection",
        "check_profile_files",
        "format_stdout_report",
        "format_json_report",
        "format_markdown_report",
        "format_issue_body",
        "format_issue_comment",
        "parse_zero_findings_timestamps",
        "should_close_issue",
        "resolve_drift_issue",
    ):
        assert hasattr(drift_sync, name), f"drift_sync missing re-export: {name}"

    # Private symbol used by commands/drift.py via attribute access
    assert hasattr(drift_sync, "_filter_by_severity")


def test_mock_path_identity() -> None:
    """Sanity check: drift_sync's module bindings resolve to the actual
    github_api submodules. Necessary-but-not-sufficient for the test-mock
    contract. See test_mock_patch_reaches_checks for the functional
    verification.
    """
    from gh_manage import drift_sync
    from gh_manage.github_api import issues as issues_api
    from gh_manage.github_api import labels as labels_api
    from gh_manage.github_api import protection as protection_api

    assert drift_sync.labels_api is labels_api
    assert drift_sync.protection_api is protection_api
    assert drift_sync.issues_api is issues_api


def test_mock_patch_reaches_checks(mocker: MockerFixture) -> None:
    """Functional mock guard (spec-critique HIGH 1): patching
    gh_manage.drift_sync.labels_api.list_labels must affect what
    check_labels sees when run through run_all_checks. If the split
    ever re-binds labels_api in a way that breaks this flow, the
    identity check above would still pass but the real mock contract
    would be broken — this test catches that.
    """
    from gh_manage import drift_sync
    from gh_manage.drift_sync import ScanContext
    from gh_manage.models.labels import CategorySpec, LabelSpec, LabelsConfig
    from gh_manage.models.profiles import ProfileSpec

    # Patch BOTH the list_labels and protection calls that could be
    # reached during run_all_checks.
    mock_list = mocker.patch(
        "gh_manage.drift_sync.labels_api.list_labels",
        return_value=[],  # empty current labels → creates for every profile label
    )
    mocker.patch(
        "gh_manage.drift_sync.protection_api.get_branch_protection",
        return_value={},
    )

    # Build a minimal but valid ScanContext. profile.files=[] avoids
    # file I/O in check_profile_files; protection_policy=None makes
    # check_protection a no-op.
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
    ctx = ScanContext(
        path=Path("/tmp"),
        repo="yakkuro/sentinel-repo",
        default_branch="main",
        profile=profile,
        labels_config=labels_config,
        bp_config=None,
    )

    drift_sync.run_all_checks(ctx)
    assert mock_list.called, (
        "patching gh_manage.drift_sync.labels_api.list_labels did not reach "
        "check_labels. Module-attribute re-exports may be broken."
    )


def test_checks_registration() -> None:
    """Regression guard (spec-critique HIGH 4): the 3 drift checks
    must be registered in the _CHECKS registry after package import.
    If extract Commit 5 introduces a subtle bug (e.g., checks.py not
    imported by __init__.py, so @register_check never runs), this test
    catches it — empty _CHECKS would silently return 0 findings on
    every drift scan.
    """
    from gh_manage.drift_sync.checks import (
        check_labels,
        check_profile_files,
        check_protection,
    )
    from gh_manage.drift_sync.registry import _CHECKS

    check_fns = set(_CHECKS)
    assert check_labels in check_fns
    assert check_protection in check_fns
    assert check_profile_files in check_fns


def test_submodules_do_not_import_from_package_root() -> None:
    """Import discipline lint-as-test (spec-critique HIGH 3): submodules
    under drift_sync/ must only import from specific sibling submodules
    or from external modules, never from `gh_manage.drift_sync` (the
    package __init__.py). Importing from the package root creates a
    load-order cycle because __init__.py itself imports from every
    submodule.
    """
    package_root = files("gh_manage.drift_sync")
    submodules = [
        p
        for p in package_root.iterdir()
        if p.is_file() and p.name.endswith(".py") and p.name != "__init__.py"
    ]
    assert len(submodules) == 6, (
        f"Expected 6 submodules (context, registry, adapters, checks, "
        f"formatters, issue_state), found {len(submodules)}: "
        f"{sorted(p.name for p in submodules)}"
    )

    offenders: list[str] = []
    for sub in submodules:
        text = sub.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("from gh_manage.drift_sync import") or (
                stripped.startswith("from gh_manage.drift_sync ")
                and not stripped.startswith("from gh_manage.drift_sync.")
            ):
                offenders.append(f"{sub.name}:{line_no}: {stripped}")
            if stripped == "import gh_manage.drift_sync":
                offenders.append(f"{sub.name}:{line_no}: {stripped}")
    assert not offenders, (
        "drift_sync submodules must not import from the package root "
        "(circular-import risk). Offenders:\n" + "\n".join(offenders)
    )
