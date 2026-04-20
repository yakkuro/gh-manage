"""Tests for gh_manage.models.repos — RepoEntry + ReposConfig."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from gh_manage.models.repos import RepoEntry, ReposConfig
from gh_manage.config import load_config
from importlib.resources import files
from pathlib import Path


def test_repo_entry_valid() -> None:
    e = RepoEntry(name="yakkuro/gh-manage", profile="python-service")
    assert e.name == "yakkuro/gh-manage"
    assert e.profile == "python-service"
    assert e.enabled is True  # default


def test_repo_entry_enabled_false() -> None:
    e = RepoEntry(name="yakkuro/archived", profile="python-service", enabled=False)
    assert e.enabled is False


def test_repo_entry_rejects_no_slash() -> None:
    with pytest.raises(ValidationError, match="owner/repo"):
        RepoEntry(name="just-a-name", profile="python-service")


def test_repo_entry_rejects_multiple_slashes() -> None:
    with pytest.raises(ValidationError, match="owner/repo"):
        RepoEntry(name="a/b/c", profile="python-service")


def test_repo_entry_rejects_empty_parts() -> None:
    with pytest.raises(ValidationError, match="non-empty"):
        RepoEntry(name="/repo", profile="python-service")


def test_repo_entry_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        RepoEntry(name="a/b", profile="p", unknown="x")  # type: ignore[call-arg]


def test_repos_config_valid() -> None:
    config = ReposConfig(
        version=1,
        repos=[RepoEntry(name="yakkuro/gh-manage", profile="python-service")],
    )
    assert len(config.repos) == 1


def test_repos_config_rejects_version_2() -> None:
    with pytest.raises(ValidationError):
        ReposConfig(
            version=2,  # type: ignore[arg-type]
            repos=[],
        )


def test_bundled_repos_yml_loads() -> None:
    """Production repos.yml loads without validation errors."""
    repos_path = Path(str(files("gh_manage.data") / "repos.yml"))
    config = load_config(repos_path, ReposConfig)
    assert len(config.repos) >= 1
    assert config.repos[0].name == "yakkuro/gh-manage"


# #39: ReposConfig profile validator
def test_reposconfig_valid_profile_passes() -> None:
    config = ReposConfig(
        version=1,
        repos=[RepoEntry(name="yakkuro/foo", profile="python-service")],
    )
    assert len(config.repos) == 1


def test_reposconfig_invalid_profile_fails() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ReposConfig(
            version=1,
            repos=[RepoEntry(name="yakkuro/foo", profile="pytohn-service")],
        )
    msg = str(exc_info.value)
    assert "pytohn-service" in msg
    assert "Available profiles" in msg
    assert "python-service" in msg  # listed as available


def test_reposconfig_multiple_invalid_profiles_aggregated() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ReposConfig(
            version=1,
            repos=[
                RepoEntry(name="yakkuro/a", profile="pytohn-service"),
                RepoEntry(name="yakkuro/b", profile="go-service"),
                RepoEntry(name="yakkuro/c", profile="unknown-prof"),
            ],
        )
    msg = str(exc_info.value)
    assert "pytohn-service" in msg
    assert "go-service" in msg
    assert "unknown-prof" in msg
    assert msg.count("yakkuro/") == 3  # all three offender names listed


def test_reposconfig_mixed_valid_invalid_reports_only_invalid() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ReposConfig(
            version=1,
            repos=[
                RepoEntry(name="yakkuro/ok1", profile="python-service"),
                RepoEntry(name="yakkuro/bad", profile="typo-prof"),
                RepoEntry(name="yakkuro/ok2", profile="python-service"),
            ],
        )
    msg = str(exc_info.value)
    assert "typo-prof" in msg
    assert "yakkuro/bad" in msg
    assert "yakkuro/ok1" not in msg  # valid repos not listed as invalid
    assert "yakkuro/ok2" not in msg


def test_profiles_dir_accessible_via_importlib_resources() -> None:
    """Packaging regression guard: the bundled profiles dir must be
    enumerable via importlib.resources. If this fails in CI, the wheel
    is missing data/profiles/ and the validator would crash in prod.
    """
    from importlib.resources import files

    profiles_root = files("gh_manage.data.profiles")
    yml_files = [
        p
        for p in profiles_root.iterdir()
        if p.is_file() and p.name.endswith((".yml", ".yaml"))
    ]
    assert len(yml_files) >= 1, "No bundled profiles found"
    assert any(p.name == "python-service.yml" for p in yml_files)


# #29: ts-service profile integration
def test_reposconfig_accepts_ts_service_profile() -> None:
    """ts-service is a bundled profile after this PR — ReposConfig accepts it."""
    config = ReposConfig(
        version=1,
        repos=[RepoEntry(name="yakkuro/foo", profile="ts-service")],
    )
    assert config.repos[0].profile == "ts-service"


def test_bundled_profiles_includes_both_python_and_ts() -> None:
    """Regression guard: both profiles exist in the bundled data dir.
    If the wheel drops ts-service.yml, this test fails in CI instead
    of the validator silently rejecting 'ts-service' at runtime.
    """
    from importlib.resources import files

    profiles_root = files("gh_manage.data.profiles")
    names = {
        p.name.rsplit(".", 1)[0]
        for p in profiles_root.iterdir()
        if p.is_file() and p.name.endswith((".yml", ".yaml"))
    }
    assert "python-service" in names
    assert "ts-service" in names


def test_bundled_ts_ci_template_loadable() -> None:
    """Regression guard: ts-ci.yml is bundled AND parseable AND references
    a REAL workflow tag (v1.1.0 — the current reusable-workflow tag per
    docs/versioning.md two-track model), not the CLI tag (cli/v1.X.Y)
    or a non-existent tag like v1.6.0.

    Catches the class of bug Codex review flagged on PR #60: consumers
    pointed at a non-existent tag would fail at workflow resolution time.
    """
    from importlib.resources import files
    import yaml

    templates_root = files("gh_manage.data.templates.ci")
    ts_ci_resource = next(
        (p for p in templates_root.iterdir() if p.name == "ts-ci.yml"),
        None,
    )
    assert ts_ci_resource is not None, "ts-ci.yml not bundled"
    assert ts_ci_resource.is_file()

    payload = yaml.safe_load(ts_ci_resource.read_text(encoding="utf-8"))
    pr_gate = payload["jobs"]["pr-gate"]
    assert pr_gate["name"] == "PR Gate"

    uses_ref = pr_gate["uses"]
    assert uses_ref.startswith(
        "yakkuro/gh-manage/.github/workflows/reusable-pr-gate-typescript.yml@"
    )
    tag = uses_ref.rsplit("@", 1)[1]
    # Workflow tag (vX.Y.Z), not CLI tag (cli/vX.Y.Z). Two-track versioning
    # per docs/versioning.md — consumers resolve vX.Y.Z, not cli/vX.Y.Z.
    assert not tag.startswith("cli/"), (
        f"ts-ci.yml pins {tag!r} which looks like a CLI tag. "
        "Consumers resolve workflow-track tags (vX.Y.Z). Use v1.1.0 or newer."
    )
    assert pr_gate["with"]["gh-manage-ref"] == tag, (
        "gh-manage-ref must match the @<tag> in `uses:`."
    )


def test_repo_entry_self_referencing_defaults_false() -> None:
    e = RepoEntry(name="yakkuro/foo", profile="python-service")
    assert e.self_referencing is False


def test_repo_entry_self_referencing_true() -> None:
    e = RepoEntry(
        name="yakkuro/gh-manage",
        profile="python-service",
        self_referencing=True,
    )
    assert e.self_referencing is True


def test_repo_entry_self_referencing_rejects_non_bool() -> None:
    # Pydantic coerces "true"/"false" strings — make sure that still works
    # for YAML compat, but reject obviously-wrong types.
    with pytest.raises(ValidationError):
        RepoEntry(
            name="yakkuro/foo",
            profile="python-service",
            self_referencing=["yes"],  # type: ignore[arg-type]
        )


def test_bundled_repos_yml_marks_gh_manage_self_referencing() -> None:
    """Regression guard: gh-manage entry must stay marked self_referencing
    so the drift scanner skips its self-hosted ci.yml."""
    repos_path = Path(str(files("gh_manage.data") / "repos.yml"))
    config = load_config(repos_path, ReposConfig)
    by_name = {e.name: e for e in config.repos}
    assert by_name["yakkuro/gh-manage"].self_referencing is True
    # All other repos should remain self_referencing=False (no other
    # self-hosted reusable publishers as of this PR).
    for name, entry in by_name.items():
        if name != "yakkuro/gh-manage":
            assert entry.self_referencing is False, (
                f"Unexpected self_referencing=True on {name}; "
                "only gh-manage should opt in."
            )
