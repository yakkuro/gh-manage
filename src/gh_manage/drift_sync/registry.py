"""Check registry + severity filter.

Layer 2 of the drift_sync package. Depends on context (for ScanContext)
and on gh_manage.findings (for Finding/Severity). Does NOT depend on
adapters, checks, formatters, or issue_state.

The module-level _CHECKS list is the single source of truth for which
drift checks run. @register_check mutates _CHECKS at import time; every
submodule that defines a @register_check-decorated function must be
imported by __init__.py for the check to be registered.
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import chain

from gh_manage.drift_sync.context import ScanContext
from gh_manage.findings import Finding, Severity

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
