"""Bundled ci/* templates — canonical shape regression gate (spec §4).

These tests fail if any bundled ci.yml template drifts away from the
`jobs.pr-gate: { name: "PR Gate" }` shape that branch-protection
requires. The canonical shape produces the status context
"PR Gate / PR Gate" when run; branch protection is hard-coded to
require that exact context.

If a PR edits the templates and breaks the shape, CI fails. See
yakkuro/gh-manage#46 for the incident where three consumer repos
had to be admin-merged because of this invariant breaking.

NOTE: Add any new bundled ci/* template to the parametrize list
manually — this test is not auto-discovered.
"""

from __future__ import annotations

import re
from importlib.resources import files

import pytest
import yaml

_REUSABLE_USES_PYTHON = re.compile(
    r"^yakkuro/gh-manage/\.github/workflows/reusable-pr-gate-python\.yml@.+$"
)
_REUSABLE_USES_TS = re.compile(
    r"^yakkuro/gh-manage/\.github/workflows/reusable-pr-gate-typescript\.yml@.+$"
)


@pytest.mark.parametrize(
    "filename, uses_re",
    [
        ("python-ci.yml", _REUSABLE_USES_PYTHON),
        ("ts-ci.yml", _REUSABLE_USES_TS),
    ],
)
def test_bundled_ci_template_preserves_canonical_shape(
    filename: str, uses_re: re.Pattern[str]
) -> None:
    text = (files("gh_manage.data") / "templates" / "ci" / filename).read_text(
        encoding="utf-8"
    )

    parsed = yaml.safe_load(text)

    assert isinstance(parsed, dict), f"{filename}: top-level must be a mapping"
    assert "jobs" in parsed and "pr-gate" in parsed["jobs"], (
        f"{filename}: must declare `jobs.pr-gate` — see spec "
        f"docs/specs/2026-04-22-theme-b-guardrails-prevention-layer-design.md §4"
    )
    pr_gate = parsed["jobs"]["pr-gate"]
    assert pr_gate.get("name") == "PR Gate", (
        f"{filename}: `jobs.pr-gate.name` must be exactly 'PR Gate' to "
        f"produce status context 'PR Gate / PR Gate'. See "
        f"yakkuro/gh-manage#46."
    )
    uses_value = pr_gate.get("uses", "")
    assert uses_re.match(uses_value), (
        f"{filename}: `jobs.pr-gate.uses` must reference reusable-pr-gate; "
        f"got {uses_value!r}"
    )
