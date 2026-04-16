"""Verify bundled python-ci.yml template matches reusable workflow requirements."""

from __future__ import annotations

from importlib.resources import files

import yaml


def test_python_ci_template_has_gh_manage_ref() -> None:
    """LOAD-BEARING: reusable workflow requires gh-manage-ref input.
    Without this, any consumer using gh manage init/apply gets broken CI."""
    content = (files("gh_manage.data.templates") / "ci" / "python-ci.yml").read_text()
    parsed = yaml.safe_load(content)
    job = parsed["jobs"]["pr-gate"]
    assert (
        "gh-manage-ref" in job["with"]
    ), "python-ci.yml template missing required 'gh-manage-ref' input"


def test_python_ci_template_pins_v1() -> None:
    """Template must pin to a release tag, not @main."""
    content = (files("gh_manage.data.templates") / "ci" / "python-ci.yml").read_text()
    parsed = yaml.safe_load(content)
    uses = parsed["jobs"]["pr-gate"]["uses"]
    assert "@v1.0.0" in uses, f"Template uses '{uses}', expected @v1.0.0 pin"
    assert "@main" not in uses, f"Template still uses @main: {uses}"


def test_python_ci_template_has_python_version() -> None:
    """Template must specify python-version (required input)."""
    content = (files("gh_manage.data.templates") / "ci" / "python-ci.yml").read_text()
    parsed = yaml.safe_load(content)
    job = parsed["jobs"]["pr-gate"]
    assert "python-version" in job["with"]
