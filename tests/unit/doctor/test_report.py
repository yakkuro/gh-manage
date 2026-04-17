"""Doctor report formatters (spec §2 output sample + §4 drift integration)."""

from __future__ import annotations

import json

from gh_manage.findings import Finding


def _findings() -> tuple[Finding, ...]:
    return (
        Finding(
            severity="critical",
            check="shape/job-shape-coherence",
            repo="yakkuro/example",
            field_path=".github/workflows/ci.yml:jobs.test",
            current_value="test / PR Gate",
            desired_value=["PR Gate / PR Gate"],
            message="context mismatch",
            remediation="rename the job",
        ),
    )


def test_format_stdout_contains_severity_counts_and_finding_sections():
    from gh_manage.doctor.report import format_stdout

    out = format_stdout(_findings(), repo="yakkuro/example")

    assert "yakkuro/example" in out
    assert "1 critical" in out
    assert "## critical" in out
    assert "shape/job-shape-coherence" in out
    assert "rename the job" in out


def test_format_stdout_empty_is_clean_summary():
    from gh_manage.doctor.report import format_stdout

    out = format_stdout((), repo="yakkuro/example")
    assert "0 critical" in out


def test_format_json_emits_valid_json_with_all_finding_fields():
    from gh_manage.doctor.report import format_json

    out = format_json(_findings(), repo="yakkuro/example")
    data = json.loads(out)
    assert data["repo"] == "yakkuro/example"
    assert len(data["findings"]) == 1
    f = data["findings"][0]
    assert f["severity"] == "critical"
    assert f["check"] == "shape/job-shape-coherence"
    assert f["current_value"] == "test / PR Gate"


def test_format_markdown_matches_drift_style_headers():
    from gh_manage.doctor.report import format_markdown

    out = format_markdown(_findings(), repo="yakkuro/example")
    assert "## critical" in out
    assert "### shape/job-shape-coherence" in out
