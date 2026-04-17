"""Snapshot regression: doctor must identify each of today's three
admin-merged consumers (#46) as shape/job-shape-coherence critical.

Prevents silent regressions where doctor returns green for a case it
was specifically designed to catch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "broken_consumers"


@pytest.mark.parametrize(
    "fixture_dir",
    ["tg_commander", "repo_init", "deep_research"],
)
def test_fixture_produces_expected_job_shape_finding(fixture_dir: str) -> None:
    from gh_manage.doctor.checks import check_job_shape_coherence
    from gh_manage.doctor.context import CheckContext

    ci_text = (_FIXTURES / fixture_dir / "ci.yml").read_text(encoding="utf-8")
    protection = json.loads(
        (_FIXTURES / fixture_dir / "protection.json").read_text(encoding="utf-8")
    )
    expected = json.loads(
        (_FIXTURES / fixture_dir / "expected_findings.json").read_text(encoding="utf-8")
    )
    required = tuple(protection["required_status_checks"]["contexts"])

    ctx = CheckContext(
        repo=f"yakkuro/{fixture_dir}",
        ci_yml_text=ci_text,
        profile_name="python-service",
        required_contexts=required,
        source_hint=f"fixture:{fixture_dir}",
    )
    findings = check_job_shape_coherence(ctx)
    criticals = [f for f in findings if f.severity == "critical"]

    assert len(criticals) == 1, (
        f"Expected exactly one shape/job-shape-coherence critical for "
        f"{fixture_dir}, got {len(criticals)}: {findings}"
    )
    assert criticals[0].current_value == expected["expected_current"]
