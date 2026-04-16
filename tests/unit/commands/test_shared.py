"""Tests for commands/_shared.py — shared CLI helpers."""

from __future__ import annotations

from pathlib import Path

import click
import pytest

from gh_manage.commands._shared import (
    VALID_PROFILE_NAME_RE,
    format_files_diff,
    handle_errors,
    resolve_backup_dir,
    resolve_branch_protection_path,
    resolve_default_labels_path,
    resolve_profile_path,
    resolve_repos_path,
    resolve_templates_root,
)
from gh_manage.config import ConfigFileNotFoundError
from gh_manage.github_client import GhError
from gh_manage.profile_sync import FileCreate, ProfileFilesDiff


class TestValidProfileNameRe:
    def test_accepts_simple_name(self) -> None:
        assert VALID_PROFILE_NAME_RE.match("python-service")

    def test_rejects_path_traversal(self) -> None:
        assert not VALID_PROFILE_NAME_RE.match("../etc/passwd")

    def test_rejects_leading_dot(self) -> None:
        assert not VALID_PROFILE_NAME_RE.match(".hidden")

    def test_rejects_empty(self) -> None:
        assert not VALID_PROFILE_NAME_RE.match("")


class TestResolveProfilePath:
    def test_valid_profile_resolves(self) -> None:
        path = resolve_profile_path("python-service")
        assert path.is_file()
        assert path.name == "python-service.yml"

    def test_invalid_name_raises(self) -> None:
        with pytest.raises(ConfigFileNotFoundError, match="Invalid profile name"):
            resolve_profile_path("../../etc/passwd")

    def test_nonexistent_profile_raises(self) -> None:
        with pytest.raises(ConfigFileNotFoundError, match="Profile not found"):
            resolve_profile_path("nonexistent-profile-xyz")


class TestResolvePathHelpers:
    def test_templates_root_is_directory(self) -> None:
        assert resolve_templates_root().is_dir()

    def test_labels_path_is_file(self) -> None:
        assert resolve_default_labels_path().is_file()

    def test_branch_protection_path_is_file(self) -> None:
        assert resolve_branch_protection_path().is_file()

    def test_repos_path_is_file(self) -> None:
        assert resolve_repos_path().is_file()

    def test_backup_dir_is_under_home(self) -> None:
        path = resolve_backup_dir()
        assert ".gh-manage" in str(path)
        assert "backups" in str(path)


class TestHandleErrors:
    def test_gh_error_becomes_click_exception(self) -> None:
        @handle_errors
        def failing() -> None:
            raise GhError("test gh error")

        with pytest.raises(click.ClickException, match="test gh error"):
            failing()

    def test_no_error_passes_through(self) -> None:
        @handle_errors
        def succeeding() -> str:
            return "ok"

        assert succeeding() == "ok"


class TestFormatFilesDiff:
    def test_empty_diff(self) -> None:
        diff = ProfileFilesDiff(creates=(), overwrites=(), skipped=(), noops=())
        result = format_files_diff(diff)
        assert "no file changes" in result

    def test_creates_shown(self) -> None:
        diff = ProfileFilesDiff(
            creates=(FileCreate(source=Path("/s"), dest=Path("/d/file.yml")),),
            overwrites=(),
            skipped=(),
            noops=(),
        )
        result = format_files_diff(diff)
        assert "+ create" in result
        assert "file.yml" in result
