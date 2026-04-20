"""Drift detection engine — package root.

This package was extracted from a single 784-line module in cli/v1.7.0.
External callers import from `gh_manage.drift_sync` (this file); test
mocks reach into `gh_manage.drift_sync.{labels,protection,issues}_api`
and those paths resolve through the bindings below.

Submodule layout:
  context.py     — ScanContext + drift errors (no internal deps)
  registry.py    — _CHECKS + register_check + run_all_checks
  adapters.py    — diff → Finding pure functions
  checks.py      — 3 @register_check drift checks (IMPORTED here so
                   registrations fire)
  formatters.py  — stdout/JSON/Markdown/issue renderers
  issue_state.py — drift issue lifecycle

Dependency DAG:
  context ← registry ← adapters ← checks ← formatters ← issue_state

Submodules MUST NOT import from `gh_manage.drift_sync` (the package
root) — see tests/unit/drift/test_package_structure.py for the
lint-as-test that enforces this.

Adding a new drift check: write a new module under drift_sync/, define
a @register_check-decorated function, and import it from __init__.py
(below the existing `from gh_manage.drift_sync.checks import` line).
Editing one file is enough — the registry takes care of the rest.
"""

from __future__ import annotations

# ---- Findings (extracted in cli/v1.2.0, lives in gh_manage.findings) ----
from gh_manage.findings import Finding, Severity  # noqa: F401

# ---- Context + errors (drift_sync.context) ----
from gh_manage.drift_sync.context import (  # noqa: F401
    DriftError,
    DriftOutputError,
    ScanContext,
    scan_id_var,
)

# ---- Registry (drift_sync.registry) ----
from gh_manage.drift_sync.registry import (  # noqa: F401
    _CHECKS,
    CheckFn,
    _filter_by_severity,
    register_check,
    run_all_checks,
)

# ---- Module-attribute bindings (load-bearing for test mocker.patch paths) ----
# `gh_manage.drift_sync.labels_api.list_labels` and the matching binding
# inside checks.py resolve to the SAME module object, so patching either
# path flows through every caller inside the package.
from gh_manage.github_api import issues as issues_api  # noqa: F401
from gh_manage.github_api import labels as labels_api  # noqa: F401
from gh_manage.github_api import protection as protection_api  # noqa: F401

# ---- Adapters (drift_sync.adapters) ----
from gh_manage.drift_sync.adapters import (  # noqa: F401
    _labels_diff_to_findings,
    _protection_diff_to_findings,
)

# ---- Checks (drift_sync.checks) ----
# Importing this module triggers @register_check side-effects — _CHECKS is
# populated with check_labels, check_protection, check_profile_files.
# DO NOT remove this import or _CHECKS will be empty at runtime.
from gh_manage.drift_sync.checks import (  # noqa: F401
    check_labels,
    check_profile_files,
    check_protection,
)

# ---- Formatters (drift_sync.formatters) ----
from gh_manage.drift_sync.formatters import (  # noqa: F401
    _SEVERITY_ORDER,
    _count_by_severity,
    _group_by_severity,
    format_issue_body,
    format_issue_comment,
    format_json_report,
    format_markdown_report,
    format_stdout_report,
)

# ---- Issue state machine (drift_sync.issue_state) ----
from gh_manage.drift_sync.issue_state import (  # noqa: F401
    parse_zero_findings_timestamps,
    resolve_drift_issue,
    should_close_issue,
)

# ---- Cross-package check registration (doctor → drift) ----
# Side-effect import: doctor.bridge.check_shape registers with drift's
# _CHECKS registry on module load.
from gh_manage.doctor import bridge as _doctor_bridge  # noqa: F401

__all__ = [
    # Findings (re-exported from gh_manage.findings)
    "Finding",
    "Severity",
    # Context + errors
    "ScanContext",
    "DriftError",
    "DriftOutputError",
    "scan_id_var",
    # Registry
    "CheckFn",
    "register_check",
    "run_all_checks",
    # Module-attribute bindings (preserve pre-split `from ... import *` surface;
    # test mocks reach these via gh_manage.drift_sync.labels_api.list_labels etc.)
    "labels_api",
    "protection_api",
    "issues_api",
    # Checks
    "check_labels",
    "check_protection",
    "check_profile_files",
    # Formatters
    "format_stdout_report",
    "format_json_report",
    "format_markdown_report",
    "format_issue_body",
    "format_issue_comment",
    # Issue state machine
    "parse_zero_findings_timestamps",
    "should_close_issue",
    "resolve_drift_issue",
]
