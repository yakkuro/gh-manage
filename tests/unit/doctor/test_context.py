"""CheckContext data shape and constructors (spec §1, §2)."""

from __future__ import annotations


def test_errors_importable():
    from gh_manage.doctor.errors import CiYmlParseError, DoctorCheckError, DoctorError

    assert issubclass(DoctorCheckError, DoctorError)
    assert issubclass(CiYmlParseError, DoctorError)


def test_check_context_fields():
    from gh_manage.doctor.context import CheckContext

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="jobs: {}",
        profile_name="python-service",
        required_contexts=("PR Gate / PR Gate",),
        source_hint="test",
    )
    assert ctx.repo == "yakkuro/example"
    assert ctx.required_contexts == ("PR Gate / PR Gate",)


def test_check_context_is_frozen():
    from gh_manage.doctor.context import CheckContext

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="",
        profile_name="python-service",
        required_contexts=(),
        source_hint="test",
    )
    try:
        ctx.repo = "other/repo"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("CheckContext should be frozen (immutable)")
