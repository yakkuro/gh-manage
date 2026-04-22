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


def test_run_checks_isolates_ci_yml_parse_error():
    """If one check raises CiYmlParseError, it becomes a synthetic
    LOW diagnostic and other checks' findings are preserved."""
    from gh_manage.doctor import registry
    from gh_manage.doctor.errors import CiYmlParseError

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/bad", resolves_with=("sync_files",))
        def _bad(ctx: CheckContext) -> tuple[Finding, ...]:
            raise CiYmlParseError("synthetic parse failure")

        @registry.register_check("shape/good", resolves_with=())
        def _good(ctx: CheckContext) -> tuple[Finding, ...]:
            return (
                Finding(
                    severity="high",
                    check="shape/good",
                    repo=ctx.repo,
                    field_path="x",
                    current_value=None,
                    desired_value=None,
                    message="good fired",
                ),
            )

        findings = registry.run_checks(_ctx())
        assert len(findings) == 2
        synthetic = [f for f in findings if f.check.startswith("shape/check-error:")]
        good = [f for f in findings if f.check == "shape/good"]
        assert len(synthetic) == 1
        assert synthetic[0].severity == "low"
        assert synthetic[0].check == "shape/check-error:shape/bad"
        assert "synthetic parse failure" in synthetic[0].message
        assert len(good) == 1
        assert good[0].severity == "high"
    finally:
        registry._CHECKS[:] = before


def test_run_checks_isolates_doctor_check_error():
    from gh_manage.doctor import registry
    from gh_manage.doctor.errors import DoctorCheckError

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/broken", resolves_with=("sync_protection",))
        def _broken(ctx: CheckContext) -> tuple[Finding, ...]:
            raise DoctorCheckError("unexpected failure")

        findings = registry.run_checks(_ctx())
        assert len(findings) == 1
        assert findings[0].check == "shape/check-error:shape/broken"
        assert findings[0].severity == "low"
    finally:
        registry._CHECKS[:] = before


def test_run_checks_propagates_non_check_exceptions():
    """Only CiYmlParseError / DoctorCheckError are caught. Other
    exception classes (including arbitrary Python errors) propagate."""
    import pytest

    from gh_manage.doctor import registry

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/kaboom")
        def _kaboom(ctx: CheckContext) -> tuple[Finding, ...]:
            raise ValueError("unmodeled failure")

        with pytest.raises(ValueError):
            registry.run_checks(_ctx())
    finally:
        registry._CHECKS[:] = before


def test_synthetic_finding_carries_original_resolves_with():
    """The synthetic check-error finding's resolves_with lookup must
    return the original check's declared domains."""
    from gh_manage.doctor import registry
    from gh_manage.doctor.errors import CiYmlParseError

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/foo", resolves_with=("sync_files",))
        def _foo(ctx: CheckContext) -> tuple[Finding, ...]:
            raise CiYmlParseError("boom")

        findings = registry.run_checks(_ctx())
        synthetic_name = findings[0].check
        assert synthetic_name == "shape/check-error:shape/foo"
        assert registry.get_check_resolves_with(synthetic_name) == ("sync_files",)
    finally:
        registry._CHECKS[:] = before
