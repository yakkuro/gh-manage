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


# ========== Data Model (moved to findings.py in cli/v1.2.0) ==========

from gh_manage.findings import Finding, Severity  # noqa: F401

# ScanContext + drift errors moved to drift_sync.context in cli/v1.7.0.
from gh_manage.drift_sync.context import (  # noqa: F401
    DriftError,
    DriftOutputError,
    ScanContext,
)


# ========== Check Registry (moved to drift_sync.registry in cli/v1.7.0) ==========

from gh_manage.drift_sync.registry import (  # noqa: E402, F401
    _CHECKS,
    CheckFn,
    _filter_by_severity,
    register_check,
    run_all_checks,
)


# ========== Adapters (moved to drift_sync.adapters in cli/v1.7.0) ==========

# Module-attribute bindings — test mocks depend on these.
# `gh_manage.drift_sync.labels_api.list_labels` and the matching binding
# inside checks.py resolve to the SAME module object, so patching either
# path flows through every caller inside the package.
from gh_manage.github_api import issues as issues_api  # noqa: E402, F401
from gh_manage.github_api import labels as labels_api  # noqa: E402, F401
from gh_manage.github_api import protection as protection_api  # noqa: E402, F401

from gh_manage.drift_sync.adapters import (  # noqa: E402, F401
    _labels_diff_to_findings,
    _protection_diff_to_findings,
)


# ========== Checks (moved to drift_sync.checks in cli/v1.7.0) ==========

# Importing checks triggers @register_check side-effects — _CHECKS is
# populated with check_labels, check_protection, check_profile_files.
# DO NOT remove this import or _CHECKS will be empty at runtime.
from gh_manage.drift_sync.checks import (  # noqa: E402, F401
    _content_hash,
    _read_template_content,
    check_labels,
    check_profile_files,
    check_protection,
)


# ========== Report Formatters (moved to drift_sync.formatters in cli/v1.7.0) ==========

from gh_manage.drift_sync.formatters import (  # noqa: E402, F401
    _SEVERITY_ORDER,
    _count_by_severity,
    _group_by_severity,
    format_issue_body,
    format_issue_comment,
    format_json_report,
    format_markdown_report,
    format_stdout_report,
)


# ========== Issue State (moved to drift_sync.issue_state in cli/v1.7.0) ==========

from gh_manage.drift_sync.issue_state import (  # noqa: E402, F401
    parse_zero_findings_timestamps,
    resolve_drift_issue,
    should_close_issue,
)


# Side-effect import: doctor.bridge.check_shape registers with drift's
# registry on module load. Spec §4.
from gh_manage.doctor import bridge as _doctor_bridge  # noqa: F401, E402
