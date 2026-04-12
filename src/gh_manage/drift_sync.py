"""Pure-function engine for drift detection.

Mirrors gh_manage.profile_sync / labels_sync / protection_sync. Phase 8
ships the drift scanner with a check registry pattern:

  @register_check
  def check_labels(ctx: ScanContext) -> tuple[Finding, ...]: ...

  @register_check
  def check_protection(ctx: ScanContext) -> tuple[Finding, ...]: ...

  @register_check
  def check_profile_files(ctx: ScanContext) -> tuple[Finding, ...]: ...

New checks added by future phases (workflow pinning, etc.) just write
a decorated function — the orchestrator in `run_all_checks` does not
change.

Each check:
  1. Receives a ScanContext with the resolved path, repo, default branch,
     loaded profile, labels config, and branch-protection config.
  2. Returns a tuple of Finding objects (empty if no drift detected).
  3. May perform IO (API calls, filesystem reads) — mocks happen at the
     subprocess / module-attribute boundary in tests.

Report formatters (format_*_report) are pure functions that take a
tuple of Finding objects and return a string. Destination (stdout vs
file) is decided by the CLI layer in commands/drift.py.

Section map:
  ========== Data Model ==========
  ========== Error Hierarchy ==========
  ========== Check Registry ==========
  ========== Adapters ==========
  ========== Checks ==========
  ========== Report Formatters ==========
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import Any, Literal

from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.labels import LabelsConfig
from gh_manage.models.profiles import ProfileSpec


# ========== Data Model ==========


Severity = Literal["critical", "high", "medium", "low"]


@dataclass(frozen=True)
class Finding:
    """One drift finding. Frozen, comparable, hashable.

    Phase 8 uses per-item granularity: 10 missing labels produce 10
    findings. Group rendering (if ever needed) happens at the report
    layer; the Finding itself is atomic.
    """

    severity: Severity
    check: str  # "labels" | "protection" | "profile_files"
    repo: str  # "owner/repo"
    field_path: str  # e.g. "labels[priority/critical]", "enforce_admins", "CLAUDE.md"
    current_value: Any  # current value on the repo (None if missing)
    desired_value: Any  # desired value per profile/policy (None if extraneous)
    message: str  # human-readable 1-line explanation
    remediation: str | None = None  # optional fix command


@dataclass(frozen=True)
class ScanContext:
    """Input bundle for a drift scan. All checks read from ctx — they do
    not touch global state or pass extra arguments to each other.

    - path: local repo root (for file-based checks).
    - repo: "owner/repo" for API-based checks.
    - default_branch: resolved via `get_default_branch(repo)` at CLI
      startup. check_protection uses this instead of hardcoded "main".
    - profile: the loaded ProfileSpec.
    - labels_config: the loaded bundled labels.yml.
    - bp_config: the loaded bundled branch-protection.yml, or None if
      profile.protection_policy is None (opt-out).
    """

    path: Path
    repo: str
    default_branch: str
    profile: ProfileSpec
    labels_config: LabelsConfig
    bp_config: BranchProtectionConfig | None


# ========== Error Hierarchy ==========


class DriftError(Exception):
    """Base for drift_sync errors. Caught by commands/_handle_errors."""


class DriftOutputError(DriftError):
    """Failed to write the drift report to --output <path>. Wraps the
    underlying OSError with an actionable message."""


# ========== Check Registry ==========


CheckFn = Callable[["ScanContext"], tuple[Finding, ...]]
_CHECKS: list[CheckFn] = []


def register_check(fn: CheckFn) -> CheckFn:
    """Decorator: register a check function in the global registry.

    Intended usage:

        @register_check
        def check_labels(ctx: ScanContext) -> tuple[Finding, ...]:
            ...

    Order of registration determines order of execution in
    run_all_checks. Phase 8 registers check_labels, check_protection,
    check_profile_files in that order.
    """
    _CHECKS.append(fn)
    return fn


def run_all_checks(ctx: ScanContext) -> tuple[Finding, ...]:
    """Run every registered check in order and concatenate findings.

    Fail-fast: if a check raises, the exception propagates and no
    further checks run. MVP does not have a --continue-on-error flag;
    that is filed as a Phase 8.5+ Issue.
    """
    return tuple(chain.from_iterable(check(ctx) for check in _CHECKS))


_SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def _filter_by_severity(
    findings: tuple[Finding, ...], min_severity: Severity
) -> tuple[Finding, ...]:
    """Filter findings to those with severity >= min_severity.

    Hierarchy (highest to lowest): critical > high > medium > low.
    Input order is preserved for stable reporting.
    """
    threshold = _SEVERITY_RANK[min_severity]
    return tuple(f for f in findings if _SEVERITY_RANK[f.severity] >= threshold)


# ========== Adapters ==========
# Implementation lands in Tasks 5, 6


# ========== Checks ==========
# Implementation lands in Tasks 5, 7, 8


# ========== Report Formatters ==========
# Implementation lands in Tasks 10, 11
