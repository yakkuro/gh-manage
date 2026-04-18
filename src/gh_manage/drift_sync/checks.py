"""Drift checks — labels, branch protection, profile files.

Each @register_check function is appended to registry._CHECKS at import
time. This module MUST be imported by __init__.py so the registrations
fire before run_all_checks is called.

Module-attribute pattern (load-bearing for test mocks): labels_api /
protection_api are bound here with `as` aliases. Because Python module
objects are singletons, `gh_manage.drift_sync.labels_api` (bound via
__init__.py's re-export) and `gh_manage.drift_sync.checks.labels_api`
(bound here) refer to the SAME module object. Patching either path
with unittest.mock.patch affects every caller. See spec §4 Option P1.
"""

from __future__ import annotations

import hashlib
from importlib.resources import files as _package_files
from pathlib import Path

from gh_manage.drift_sync.adapters import (
    _labels_diff_to_findings,
    _protection_diff_to_findings,
)
from gh_manage.drift_sync.context import DriftError, ScanContext
from gh_manage.drift_sync.registry import register_check
from gh_manage.findings import Finding, Severity
from gh_manage.github_api import labels as labels_api
from gh_manage.github_api import protection as protection_api
from gh_manage.github_client import GhNotFoundError
from gh_manage.labels_sync import compute_diff as _compute_labels_diff
from gh_manage.protection_sync import compute_protection_diff


@register_check
def check_labels(ctx: ScanContext) -> tuple[Finding, ...]:
    """Drift check: repo labels vs ctx.labels_config.

    Calls labels_api.list_labels(ctx.repo) to fetch the current state,
    then reuses labels_sync.compute_diff() (with prune=True) and translates
    the resulting LabelsDiff into Finding objects.

    IO: yes (subprocess via labels_api.list_labels). Mocked at the
    module-attribute boundary (gh_manage.drift_sync.labels_api.list_labels)
    in scenario tests.

    `prune=True` is used here — drift scan should report extras so the user
    can see extras, and the adapter marks them low-severity with no
    remediation command.
    """
    current = labels_api.list_labels(ctx.repo)
    diff = _compute_labels_diff(current, ctx.labels_config, prune=True)
    return _labels_diff_to_findings(diff, ctx.repo)


@register_check
def check_protection(ctx: ScanContext) -> tuple[Finding, ...]:
    """Drift check: current branch protection vs profile's policy.

    Returns early with an empty tuple if:
    - ctx.profile.protection_policy is None (opt-out — profile does
      not manage protection)
    - ctx.bp_config is None (CLI builder did not load branch-protection.yml)

    Otherwise:
    1. Look up the policy in ctx.bp_config.policies by name.
    2. Fetch current protection via protection_api.get_branch_protection
       on ctx.default_branch. 404 → treat as empty dict.
    3. Compute diff via protection_sync.compute_protection_diff.
    4. Pass the diff through _protection_diff_to_findings.

    IO: yes (subprocess via protection_api). Mocked at
    gh_manage.drift_sync.protection_api.get_branch_protection in
    scenario tests.
    """
    if ctx.profile.protection_policy is None or ctx.bp_config is None:
        return ()

    policy = ctx.bp_config.policies[ctx.profile.protection_policy]
    try:
        current = protection_api.get_branch_protection(ctx.repo, ctx.default_branch)
    except GhNotFoundError:
        current = {}

    diff = compute_protection_diff(current, policy, ctx.profile, ctx.default_branch)
    return _protection_diff_to_findings(diff, ctx.repo)


def _read_template_content(source: str) -> str:
    """Read a template file from the bundled gh_manage.data.templates
    package data. `source` is relative path like "ci/python-ci.yml".

    Raises DriftError with actionable context if the template file is
    missing or unreadable (silent-failure-hunter HIGH #1 fix).
    """
    templates_root = Path(str(_package_files("gh_manage.data") / "templates"))
    template_path = templates_root / source
    try:
        return template_path.read_text(encoding="utf-8")
    except OSError as e:
        raise DriftError(
            f"Cannot read bundled template {source!r} at {template_path}: {e}. "
            f"This may indicate a packaging bug — the template should be "
            f"bundled in gh_manage.data.templates."
        ) from e


def _content_hash(text: str) -> str:
    """Compute SHA256 hex digest of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@register_check
def check_profile_files(ctx: ScanContext) -> tuple[Finding, ...]:
    """Drift check: local repo files vs profile's template files.

    For each entry in ctx.profile.files:
    - Read the template content from gh_manage.data.templates/<source>.
    - Check if ctx.path / entry.dest exists.
      - Missing + skip_if_exists=False → severity=medium, "missing file"
      - Missing + skip_if_exists=True  → no finding (user opted out)
    - Compare content hashes:
      - Match → no finding
      - Mismatch + skip_if_exists=False → severity=medium, "content drifted"
      - Mismatch + skip_if_exists=True  → severity=low, "content drifted" (informational)

    IO: yes (filesystem reads). Tests inject scenario state via tmp_path
    in the conftest `drift_scenario` fixture.
    """
    findings: list[Finding] = []
    remediation_apply = f"gh manage apply . --profile {ctx.profile.name} --apply"

    for entry in ctx.profile.files:
        local = ctx.path / entry.dest
        template_content = _read_template_content(entry.source)
        template_hash = _content_hash(template_content)

        if not local.exists():
            if entry.skip_if_exists:
                continue
            findings.append(
                Finding(
                    severity="medium",
                    check="profile_files",
                    repo=ctx.repo,
                    field_path=entry.dest,
                    current_value=None,
                    desired_value=f"<template {entry.source}>",
                    message=(
                        f"Profile file {entry.dest!r} is missing from the "
                        f"repository (template: {entry.source!r})"
                    ),
                    remediation=remediation_apply,
                )
            )
            continue

        try:
            local_content = local.read_text(encoding="utf-8")
        except OSError as e:
            raise DriftError(
                f"Cannot read {entry.dest!r} at {local}: {e}. Check file permissions."
            ) from e
        local_hash = _content_hash(local_content)
        if local_hash == template_hash:
            continue

        # Content mismatch
        severity: Severity = "low" if entry.skip_if_exists else "medium"
        findings.append(
            Finding(
                severity=severity,
                check="profile_files",
                repo=ctx.repo,
                field_path=entry.dest,
                current_value=f"hash={local_hash[:12]}",
                desired_value=f"hash={template_hash[:12]}",
                message=(
                    f"Profile file {entry.dest!r} has drifted from the "
                    f"template {entry.source!r}"
                    + (" (user-editable)" if entry.skip_if_exists else "")
                ),
                remediation=remediation_apply if not entry.skip_if_exists else None,
            )
        )
    return tuple(findings)
