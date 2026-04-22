"""Tests for doctor.semantic_filter (spec §2)."""

from __future__ import annotations

import pytest

from gh_manage.findings import Finding


def _f(check: str, severity: str = "high") -> Finding:
    return Finding(
        severity=severity,
        check=check,
        repo="yakkuro/example",
        field_path="x",
        current_value=None,
        desired_value=None,
        message="msg",
    )


def test_apply_scope_is_frozen_dataclass():
    from gh_manage.doctor.semantic_filter import ApplyScope

    s = ApplyScope(sync_files=True, sync_labels=False, sync_protection=False)
    with pytest.raises(Exception):
        s.sync_files = False  # type: ignore[misc]


def test_filter_drops_finding_when_scope_covers_resolves_with():
    """sync_files=True filters out shape/job-shape-coherence
    (resolves_with=('sync_files',))."""
    from gh_manage.doctor import checks  # noqa: F401 — force registration
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=True, sync_labels=False, sync_protection=False)
    findings = (_f("shape/job-shape-coherence", "critical"),)
    filtered = filter_pre_apply_findings(findings, scope)
    assert filtered == ()


def test_filter_keeps_finding_when_scope_does_not_cover():
    """sync_protection=False keeps shape/required-contexts-match findings."""
    from gh_manage.doctor import checks  # noqa: F401
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=False)
    finding = _f("shape/required-contexts-match", "high")
    filtered = filter_pre_apply_findings((finding,), scope)
    assert len(filtered) == 1
    assert filtered[0].check == "shape/required-contexts-match"


def test_filter_unknown_check_never_dropped():
    """A check not in the registry is conservatively kept (invariant 1)."""
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=True)
    finding = _f("shape/fabricated-in-test", "high")
    filtered = filter_pre_apply_findings((finding,), scope)
    assert len(filtered) == 1


def test_filter_synthetic_error_name_resolves_via_prefix_strip():
    """shape/check-error:<registered> inherits the registered check's
    resolves_with and is filtered accordingly."""
    from gh_manage.doctor import checks  # noqa: F401
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=True, sync_labels=False, sync_protection=False)
    finding = _f("shape/check-error:shape/job-shape-coherence", "low")
    filtered = filter_pre_apply_findings((finding,), scope)
    assert filtered == ()


def test_filter_requires_all_domains_in_resolves_with():
    """AND semantics: a check with resolves_with=(A, B) is filtered
    only when BOTH A and B are in scope."""
    from gh_manage.doctor import registry
    from gh_manage.doctor.context import CheckContext
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check(
            "shape/needs-both",
            resolves_with=("sync_files", "sync_protection"),
        )
        def _c(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        finding = _f("shape/needs-both", "high")

        # Only sync_files → keeps
        s1 = ApplyScope(sync_files=True, sync_labels=False, sync_protection=False)
        assert filter_pre_apply_findings((finding,), s1) == (finding,)

        # Both → drops
        s2 = ApplyScope(sync_files=True, sync_labels=False, sync_protection=True)
        assert filter_pre_apply_findings((finding,), s2) == ()
    finally:
        registry._CHECKS[:] = before


def test_filter_empty_scope_keeps_everything():
    from gh_manage.doctor import checks  # noqa: F401
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=False, sync_labels=False, sync_protection=False)
    findings = (
        _f("shape/job-shape-coherence", "critical"),
        _f("shape/required-contexts-match", "high"),
        _f("shape/reusable-adoption", "medium"),
    )
    filtered = filter_pre_apply_findings(findings, scope)
    assert len(filtered) == 3


def test_filter_preserves_finding_order():
    from gh_manage.doctor import checks  # noqa: F401
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=False, sync_labels=False, sync_protection=False)
    findings = (
        _f("shape/job-shape-coherence", "critical"),
        _f("shape/required-contexts-match", "high"),
    )
    filtered = filter_pre_apply_findings(findings, scope)
    assert filtered[0].check == "shape/job-shape-coherence"
    assert filtered[1].check == "shape/required-contexts-match"


def test_filter_ignores_severity_only_checks_check_name():
    """A low-severity finding with matching resolves_with is still
    filtered (invariant 3). This is a no-op at the block gate but
    matters for any consumer that enumerates filtered findings."""
    from gh_manage.doctor import checks  # noqa: F401
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=True, sync_labels=False, sync_protection=False)
    finding = _f("shape/job-shape-coherence", "low")
    filtered = filter_pre_apply_findings((finding,), scope)
    assert filtered == ()
