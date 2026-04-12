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
