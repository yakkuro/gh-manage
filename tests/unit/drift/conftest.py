"""Shared fixtures for drift scenario tests.

Scenario fixtures live under tests/fixtures/drift-scenarios/<check>/<name>.yml.
Each YAML defines the inputs (mocked API response or on-disk file tree)
and the expected findings.

The `drift_scenario` fixture is pytest-parametrized over all discovered
YAML files and yields (path, DriftScenario) tuples. Tests can then run
the appropriate check function against the inputs and compare findings.

Sentinel `__USE_TEMPLATE__` in inputs.repo_files means "use the profile's
template content as-is" — loaders resolve it via importlib.resources.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

import pytest
import yaml
from pydantic import BaseModel, ConfigDict


class ExpectedFinding(BaseModel):
    """Match spec for an expected Finding. severity and check are
    compared exact-match; field_path_contains and message_contains are
    compared as substring."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["critical", "high", "medium", "low"]
    check: str
    field_path_contains: str | None = None
    message_contains: str | None = None


class ScenarioInputs(BaseModel):
    """Possible inputs for a drift scenario. A given scenario uses
    whichever subset is relevant to its check (labels scenarios only
    provide current_labels, etc.)."""

    model_config = ConfigDict(extra="forbid")

    current_labels: list[dict[str, str]] | None = None
    current_protection: dict[str, Any] | None = None
    repo_files: dict[str, str] | None = None


class DriftScenario(BaseModel):
    """One drift detection scenario, loaded from a YAML fixture."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    check: Literal["labels", "protection", "profile_files"]
    repo: str
    profile: str
    inputs: ScenarioInputs
    expected_findings: list[ExpectedFinding]


_SCENARIO_ROOT = Path(__file__).parent.parent.parent / "fixtures" / "drift-scenarios"


def _load_scenarios() -> list[tuple[Path, DriftScenario]]:
    """Glob all scenario YAML files under tests/fixtures/drift-scenarios/
    and parse them into DriftScenario instances."""
    scenarios: list[tuple[Path, DriftScenario]] = []
    for yml_path in sorted(_SCENARIO_ROOT.rglob("*.yml")):
        data = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
        scenarios.append((yml_path, DriftScenario(**data)))
    return scenarios


def _load_scenario_params() -> list[tuple[Path, DriftScenario]]:
    """Called at module import time by the fixture parametrization.

    Returns an empty list if no YAML files exist yet (early-task
    execution). pytest will still collect the fixture but skip any
    test that uses it since parameter list is empty.
    """
    try:
        return _load_scenarios()
    except FileNotFoundError:
        return []


@pytest.fixture(
    params=_load_scenario_params(),
    ids=lambda p: p[0].stem if p else "no-scenarios",
)
def drift_scenario(request: pytest.FixtureRequest) -> tuple[Path, DriftScenario]:
    return request.param


def read_template_for(profile_name: str, rel_path: str) -> str:
    """Resolve the sentinel `__USE_TEMPLATE__` by reading the template
    file that the profile would copy to `rel_path`.

    Walks ProfileSpec.files entries to find an entry whose `dest` matches
    `rel_path`, then reads the corresponding `source` from the bundled
    templates/ directory via importlib.resources.
    """
    from gh_manage.config import load_config
    from gh_manage.models.profiles import ProfileSpec

    profile_path = Path(str(files("gh_manage.data.profiles") / f"{profile_name}.yml"))
    profile = load_config(profile_path, ProfileSpec)

    for entry in profile.files:
        if entry.dest == rel_path:
            templates_root = Path(str(files("gh_manage.data") / "templates"))
            template_path = templates_root / entry.source
            return template_path.read_text(encoding="utf-8")

    raise ValueError(
        f"Profile {profile_name!r} has no files entry for dest={rel_path!r}. "
        f"Either add an entry to the profile or use a concrete content "
        f"string in the scenario YAML instead of the __USE_TEMPLATE__ sentinel."
    )
