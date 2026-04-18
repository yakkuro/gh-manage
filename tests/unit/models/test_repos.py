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
                RepoEntry(name="yakkuro/b", profile="ts-service"),
                RepoEntry(name="yakkuro/c", profile="unknown-prof"),
            ],
        )
    msg = str(exc_info.value)
    assert "pytohn-service" in msg
    assert "ts-service" in msg
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
