"""Doctor registry decorator + run helpers (spec §1)."""

from __future__ import annotations

from gh_manage.doctor.context import CheckContext
from gh_manage.findings import Finding


def _ctx() -> CheckContext:
    return CheckContext(
        repo="yakkuro/example",
        ci_yml_text="",
        profile_name="python-service",
        required_contexts=(),
        source_hint="test",
    )


def test_register_check_adds_to_registry_and_run_checks_executes_all():
    from gh_manage.doctor import registry

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/a")
        def _a(ctx: CheckContext) -> tuple[Finding, ...]:
            return (
                Finding(
                    severity="low",
                    check="shape/a",
                    repo=ctx.repo,
                    field_path="x",
                    current_value=None,
                    desired_value=None,
                    message="a",
                ),
            )

        @registry.register_check("shape/b")
        def _b(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        findings = registry.run_checks(_ctx())
        assert len(findings) == 1
        assert findings[0].check == "shape/a"
    finally:
        registry._CHECKS[:] = before


def test_run_named_checks_filters_by_name():
    from gh_manage.doctor import registry

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/a")
        def _a(ctx: CheckContext) -> tuple[Finding, ...]:
            return (Finding("low", "shape/a", ctx.repo, "x", None, None, "a"),)

        @registry.register_check("shape/b")
        def _b(ctx: CheckContext) -> tuple[Finding, ...]:
            return (Finding("low", "shape/b", ctx.repo, "y", None, None, "b"),)

        findings = registry.run_named_checks(_ctx(), ("shape/b",))
        assert len(findings) == 1
        assert findings[0].check == "shape/b"
    finally:
        registry._CHECKS[:] = before


def test_run_named_checks_raises_on_unknown_name():
    import pytest

    from gh_manage.doctor import registry
    from gh_manage.doctor.errors import DoctorError

    with pytest.raises(DoctorError):
        registry.run_named_checks(_ctx(), ("shape/does-not-exist",))


def test_register_check_stores_resolves_with_tuple():
    from gh_manage.doctor import registry

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check(
            "shape/test-with-resolves", resolves_with=("sync_files",)
        )
        def _c(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        assert getattr(_c, "__doctor_resolves_with__", None) == ("sync_files",)
    finally:
        registry._CHECKS[:] = before


def test_register_check_resolves_with_defaults_to_empty():
    from gh_manage.doctor import registry

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/test-no-resolves")
        def _c(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        assert getattr(_c, "__doctor_resolves_with__", None) == ()
    finally:
        registry._CHECKS[:] = before


def test_get_check_resolves_with_returns_registered_tuple():
    from gh_manage.doctor import registry

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/known", resolves_with=("sync_files",))
        def _c(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        assert registry.get_check_resolves_with("shape/known") == ("sync_files",)
    finally:
        registry._CHECKS[:] = before


def test_get_check_resolves_with_synthetic_prefix_strip():
    """shape/check-error:<original> maps to original's resolves_with."""
    from gh_manage.doctor import registry

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check(
            "shape/original",
            resolves_with=("sync_protection",),
        )
        def _c(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        assert registry.get_check_resolves_with("shape/check-error:shape/original") == (
            "sync_protection",
        )
    finally:
        registry._CHECKS[:] = before


def test_get_check_resolves_with_unknown_returns_empty():
    from gh_manage.doctor import registry

    assert registry.get_check_resolves_with("shape/does-not-exist") == ()


def test_get_check_resolves_with_unknown_synthetic_returns_empty():
    from gh_manage.doctor import registry

    assert registry.get_check_resolves_with("shape/check-error:shape/nonexistent") == ()
