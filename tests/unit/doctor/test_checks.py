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


def test_shape_reusable_adoption_fires_when_no_reusable_job():
    ci_yml = """
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make ci
"""
    from gh_manage.doctor.checks import check_reusable_adoption

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text=ci_yml,
        profile_name="python-service",
        required_contexts=(),
        source_hint="test",
    )
    findings = check_reusable_adoption(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert findings[0].check == "shape/reusable-adoption"


def test_shape_reusable_adoption_silent_when_reusable_present():
    ci_yml = """
jobs:
  pr-gate:
    name: "PR Gate"
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
"""
    from gh_manage.doctor.checks import check_reusable_adoption

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text=ci_yml,
        profile_name="python-service",
        required_contexts=(),
        source_hint="test",
    )
    assert check_reusable_adoption(ctx) == ()


def test_shape_reusable_adoption_silent_when_local_relative_reusable_present():
    """Self-dogfood case: gh-manage's own ci.yml uses the local reusable.

    A job whose `uses:` resolves to `./.github/workflows/reusable-pr-gate-<lang>.yml`
    (no `@<ref>` — local references can't carry one) must count as
    adoption so that gh-manage's own drift scan doesn't report a
    spurious MEDIUM. Refs #71.
    """
    ci_yml = """
jobs:
  pr-gate:
    name: "PR Gate"
    uses: ./.github/workflows/reusable-pr-gate-python.yml
"""
    from gh_manage.doctor.checks import check_reusable_adoption

    ctx = CheckContext(
        repo="yakkuro/gh-manage",
        ci_yml_text=ci_yml,
        profile_name="python-service",
        required_contexts=(),
        source_hint="test",
    )
    assert check_reusable_adoption(ctx) == ()


def test_shape_reusable_adoption_silent_for_local_typescript_variant():
    """Parity coverage: typescript variant of the self-dogfood path."""
    ci_yml = """
jobs:
  pr-gate:
    name: "PR Gate"
    uses: ./.github/workflows/reusable-pr-gate-typescript.yml
"""
    from gh_manage.doctor.checks import check_reusable_adoption

    ctx = CheckContext(
        repo="yakkuro/gh-manage",
        ci_yml_text=ci_yml,
        profile_name="ts-service",
        required_contexts=(),
        source_hint="test",
    )
    assert check_reusable_adoption(ctx) == ()


def test_shape_job_coherence_skips_when_required_contexts_unreadable():
    """If the protection fetch failed (auth/permission), the check must
    not fire CRITICAL — the live state is unknown, not empty. Emits
    a LOW diagnostic instead so the operator sees the skip.
    """
    ci_yml = """
jobs:
  pr-gate:
    name: "PR Gate"
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0
"""
    from gh_manage.doctor.checks import check_job_shape_coherence

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text=ci_yml,
        profile_name="python-service",
        required_contexts=(),
        required_contexts_readable=False,
        source_hint="test",
    )
    findings = check_job_shape_coherence(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "low"
    assert "Could not read live branch protection" in findings[0].message


def test_shape_required_contexts_match_skips_when_unreadable():
    """required-contexts-match must be silent when live state is unknown."""
    from gh_manage.doctor.checks import check_required_contexts_match

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="",
        profile_name="python-service",
        required_contexts=(),
        required_contexts_readable=False,
        profile_required_contexts=("PR Gate / PR Gate",),
        source_hint="test",
    )
    assert check_required_contexts_match(ctx) == ()


def test_shape_reusable_adoption_fires_on_bogus_local_path():
    """Defensive: a `./`-prefixed path that isn't actually a reusable
    workflow must NOT be treated as adoption (e.g., typo, wrong file).
    """
    ci_yml = """
jobs:
  pr-gate:
    name: "PR Gate"
    uses: ./.github/workflows/unrelated-workflow.yml
"""
    from gh_manage.doctor.checks import check_reusable_adoption

    ctx = CheckContext(
        repo="yakkuro/gh-manage",
        ci_yml_text=ci_yml,
        profile_name="python-service",
        required_contexts=(),
        source_hint="test",
    )
    findings = check_reusable_adoption(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "medium"


def test_shape_reusable_adoption_fires_when_ci_yml_missing():
    from gh_manage.doctor.checks import check_reusable_adoption

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="",
        profile_name="python-service",
        required_contexts=(),
        source_hint="test",
    )
    findings = check_reusable_adoption(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "medium"
    assert (
        "no .github/workflows/ci.yml found" in findings[0].message.lower()
        or "missing" in findings[0].message.lower()
    )


def test_shape_required_contexts_match_flags_missing_high():
    from gh_manage.doctor.checks import check_required_contexts_match

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="",
        profile_name="python-service",
        required_contexts=(),
        profile_required_contexts=("PR Gate / PR Gate",),
        source_hint="test",
    )
    findings = check_required_contexts_match(ctx)
    high = [f for f in findings if f.severity == "high"]
    assert len(high) == 1
    assert "not enforc" in high[0].message.lower()


def test_shape_required_contexts_match_flags_extra_medium():
    from gh_manage.doctor.checks import check_required_contexts_match

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="",
        profile_name="python-service",
        required_contexts=("PR Gate / PR Gate", "Custom / Other"),
        profile_required_contexts=("PR Gate / PR Gate",),
        source_hint="test",
    )
    findings = check_required_contexts_match(ctx)
    medium = [f for f in findings if f.severity == "medium"]
    assert len(medium) == 1
    assert "custom / other" in medium[0].message.lower()


def test_shape_required_contexts_match_silent_when_aligned():
    from gh_manage.doctor.checks import check_required_contexts_match

    ctx = CheckContext(
        repo="yakkuro/example",
        ci_yml_text="",
        profile_name="python-service",
        required_contexts=("PR Gate / PR Gate",),
        profile_required_contexts=("PR Gate / PR Gate",),
        source_hint="test",
    )
    assert check_required_contexts_match(ctx) == ()
