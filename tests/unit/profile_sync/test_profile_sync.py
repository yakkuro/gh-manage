"""Tests for gh_manage.profile_sync — pure-function profile engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from gh_manage.profile_sync import (
    FileCreate,
    FileNoop,
    FileOverwrite,
    FileSkipExists,
    ProfileConflictError,
    ProfileError,
    ProfileFilesDiff,
    ProfilePathEscapeError,
    ProfileTemplateNotFoundError,
)


# Diff data classes
def test_profile_files_diff_is_empty_when_no_creates_or_overwrites() -> None:
    diff = ProfileFilesDiff(creates=(), overwrites=(), skipped=(), noops=())
    assert diff.is_empty


def test_profile_files_diff_is_empty_ignores_skipped_and_noops() -> None:
    """Skipped and Noops are reported but don't count as 'changes'."""
    diff = ProfileFilesDiff(
        creates=(),
        overwrites=(),
        skipped=(FileSkipExists(dest=Path("/x")),),
        noops=(FileNoop(dest=Path("/y")),),
    )
    assert diff.is_empty


def test_profile_files_diff_not_empty_with_creates() -> None:
    diff = ProfileFilesDiff(
        creates=(FileCreate(source=Path("/s"), dest=Path("/d")),),
        overwrites=(),
        skipped=(),
        noops=(),
    )
    assert not diff.is_empty


def test_profile_files_diff_not_empty_with_overwrites() -> None:
    diff = ProfileFilesDiff(
        creates=(),
        overwrites=(FileOverwrite(source=Path("/s"), dest=Path("/d")),),
        skipped=(),
        noops=(),
    )
    assert not diff.is_empty


def test_profile_files_diff_has_overwrites_property() -> None:
    diff = ProfileFilesDiff(
        creates=(),
        overwrites=(FileOverwrite(source=Path("/s"), dest=Path("/d")),),
        skipped=(),
        noops=(),
    )
    assert diff.has_overwrites


def test_profile_files_diff_has_overwrites_false_when_empty() -> None:
    diff = ProfileFilesDiff(creates=(), overwrites=(), skipped=(), noops=())
    assert not diff.has_overwrites


# Error hierarchy
def test_profile_conflict_error_message_lists_conflicts() -> None:
    overwrite = FileOverwrite(source=Path("/s"), dest=Path("/dest/file.yml"))
    err = ProfileConflictError((overwrite,))
    assert "1 file" in str(err)
    assert "/dest/file.yml" in str(err)
    assert "--force" in str(err)


def test_profile_conflict_error_with_multiple() -> None:
    o1 = FileOverwrite(source=Path("/s1"), dest=Path("/d1"))
    o2 = FileOverwrite(source=Path("/s2"), dest=Path("/d2"))
    err = ProfileConflictError((o1, o2))
    assert "2 file" in str(err)


def test_profile_template_not_found_error_is_profile_error() -> None:
    err = ProfileTemplateNotFoundError("missing")
    assert isinstance(err, ProfileError)


def test_profile_path_escape_error_is_profile_error() -> None:
    err = ProfilePathEscapeError("escape")
    assert isinstance(err, ProfileError)


def test_profile_conflict_error_is_profile_error() -> None:
    err = ProfileConflictError(())
    assert isinstance(err, ProfileError)


def test_file_create_is_frozen() -> None:
    """Diff entries must be immutable so callers can't mutate them
    between compute and apply phases."""
    fc = FileCreate(source=Path("/s"), dest=Path("/d"))
    with pytest.raises(Exception):  # FrozenInstanceError
        fc.source = Path("/other")  # type: ignore[misc]
