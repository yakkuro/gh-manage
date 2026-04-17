"""Bundled ci-template shape test (spec §5.A).

If a bundled template is edited to produce a shape doctor considers
critical, CI fails before the template ships.
"""

from __future__ import annotations

from importlib.resources import files


def test_python_ci_template_passes_job_shape_coherence():
    from gh_manage.doctor.checks import check_job_shape_coherence
    from gh_manage.doctor.context import CheckContext

    tmpl_text = (
        files("gh_manage.data") / "templates" / "ci" / "python-ci.yml"
    ).read_text(encoding="utf-8")

    ctx = CheckContext(
        repo="yakkuro/example-consumer",
        ci_yml_text=tmpl_text,
        profile_name="python-service",
        required_contexts=("PR Gate / PR Gate",),
        source_hint="bundled:python-ci.yml",
    )
    assert check_job_shape_coherence(ctx) == ()


def test_python_ci_template_passes_reusable_adoption():
    from gh_manage.doctor.checks import check_reusable_adoption
    from gh_manage.doctor.context import CheckContext

    tmpl_text = (
        files("gh_manage.data") / "templates" / "ci" / "python-ci.yml"
    ).read_text(encoding="utf-8")

    ctx = CheckContext(
        repo="yakkuro/example-consumer",
        ci_yml_text=tmpl_text,
        profile_name="python-service",
        required_contexts=("PR Gate / PR Gate",),
        source_hint="bundled:python-ci.yml",
    )
    assert check_reusable_adoption(ctx) == ()
