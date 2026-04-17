"""Doctor α checks (spec §3)."""

from __future__ import annotations

from gh_manage.doctor.context import CheckContext


def _ctx(ci_yml_text: str, required: tuple[str, ...]) -> CheckContext:
    return CheckContext(
        repo="yakkuro/example",
        ci_yml_text=ci_yml_text,
        profile_name="python-service",
        required_contexts=required,
        source_hint="test",
    )


def test_shape_job_shape_coherence_fires_when_context_does_not_match():
    ci_yml = """
name: CI
on: [pull_request]
jobs:
  test:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
    with:
      python-version: "3.12"
"""
    from gh_manage.doctor.checks import check_job_shape_coherence

    findings = check_job_shape_coherence(_ctx(ci_yml, required=("PR Gate / PR Gate",)))

    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "critical"
    assert f.check == "shape/job-shape-coherence"
    assert "test / PR Gate" in str(f.current_value)
    assert "PR Gate / PR Gate" in str(f.desired_value)


def test_shape_job_shape_coherence_passes_when_name_is_pr_gate():
    ci_yml = """
jobs:
  pr-gate:
    name: "PR Gate"
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
"""
    from gh_manage.doctor.checks import check_job_shape_coherence

    findings = check_job_shape_coherence(_ctx(ci_yml, required=("PR Gate / PR Gate",)))
    assert findings == ()


def test_shape_job_shape_coherence_ignores_non_reusable_jobs():
    ci_yml = """
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""
    from gh_manage.doctor.checks import check_job_shape_coherence

    findings = check_job_shape_coherence(_ctx(ci_yml, required=("PR Gate / PR Gate",)))
    assert findings == ()


def test_shape_job_shape_coherence_missing_name_with_correct_id_still_fails():
    ci_yml = """
jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
"""
    from gh_manage.doctor.checks import check_job_shape_coherence

    findings = check_job_shape_coherence(_ctx(ci_yml, required=("PR Gate / PR Gate",)))
    assert len(findings) == 1
    f = findings[0]
    assert f.current_value == "pr-gate / PR Gate"


def test_shape_job_shape_coherence_empty_ci_yml_produces_no_findings():
    from gh_manage.doctor.checks import check_job_shape_coherence

    findings = check_job_shape_coherence(_ctx("", required=("PR Gate / PR Gate",)))
    assert findings == ()
