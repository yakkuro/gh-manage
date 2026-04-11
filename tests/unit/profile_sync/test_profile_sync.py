"""Tests for gh_manage.profile_sync — pure-function profile engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from gh_manage.models.profiles import FileEntry, ProfileSpec
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
    compute_files_diff,
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


# compute_files_diff tests


def _make_profile(*entries: FileEntry) -> ProfileSpec:
    return ProfileSpec(version=1, name="test", files=list(entries))


def _write_template(templates_root: Path, rel_path: str, content: str) -> None:
    p = templates_root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _write_target(target_root: Path, rel_path: str, content: str) -> None:
    p = target_root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# Happy paths
def test_compute_files_diff_empty_target_produces_creates(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "ci content\n")
    _write_template(templates, "claude.md", "claude content\n")

    profile = _make_profile(
        FileEntry(source="ci.yml", dest=".github/ci.yml"),
        FileEntry(source="claude.md", dest="CLAUDE.md"),
    )

    diff = compute_files_diff(profile, target, templates)
    assert len(diff.creates) == 2
    assert len(diff.overwrites) == 0
    assert len(diff.skipped) == 0
    assert len(diff.noops) == 0
    assert {c.dest.name for c in diff.creates} == {"ci.yml", "CLAUDE.md"}


def test_compute_files_diff_identical_content_is_noop(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "same content\n")
    _write_target(target, "ci.yml", "same content\n")

    profile = _make_profile(FileEntry(source="ci.yml", dest="ci.yml"))
    diff = compute_files_diff(profile, target, templates)
    assert len(diff.noops) == 1
    assert len(diff.creates) == 0
    assert diff.is_empty


def test_compute_files_diff_different_content_no_skip_is_overwrite(
    tmp_path: Path,
) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "new content\n")
    _write_target(target, "ci.yml", "old content\n")

    profile = _make_profile(FileEntry(source="ci.yml", dest="ci.yml"))
    diff = compute_files_diff(profile, target, templates)
    assert len(diff.overwrites) == 1
    assert len(diff.creates) == 0
    assert not diff.is_empty
    assert diff.has_overwrites


def test_compute_files_diff_different_content_with_skip_is_skipped(
    tmp_path: Path,
) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "claude.md", "starter\n")
    _write_target(target, "CLAUDE.md", "user customization\n")

    profile = _make_profile(
        FileEntry(source="claude.md", dest="CLAUDE.md", skip_if_exists=True)
    )
    diff = compute_files_diff(profile, target, templates)
    assert len(diff.skipped) == 1
    assert len(diff.overwrites) == 0
    assert diff.is_empty


def test_compute_files_diff_identical_with_skip_is_noop_not_skipped(
    tmp_path: Path,
) -> None:
    """Same-content files don't need writing AND don't need 'skip' label —
    they're just noops. The skip_if_exists flag only matters when content
    differs."""
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "claude.md", "same\n")
    _write_target(target, "CLAUDE.md", "same\n")

    profile = _make_profile(
        FileEntry(source="claude.md", dest="CLAUDE.md", skip_if_exists=True)
    )
    diff = compute_files_diff(profile, target, templates)
    assert len(diff.noops) == 1
    assert len(diff.skipped) == 0


# Errors
def test_compute_files_diff_missing_source_raises_template_not_found(
    tmp_path: Path,
) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    target = tmp_path / "target"
    target.mkdir()

    profile = _make_profile(FileEntry(source="missing.yml", dest="x.yml"))
    with pytest.raises(ProfileTemplateNotFoundError, match="missing.yml"):
        compute_files_diff(profile, target, templates)


def test_compute_files_diff_dest_symlink_escape_raises_path_escape(
    tmp_path: Path,
) -> None:
    """If a parent component of dest is a symlink pointing outside target_root,
    the resolved path escapes. Must be detected at compute time."""
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    outside = tmp_path / "outside"
    target.mkdir()
    outside.mkdir()
    _write_template(templates, "ci.yml", "x\n")

    # Make .github inside target a symlink to outside
    (target / ".github").symlink_to(outside)

    profile = _make_profile(FileEntry(source="ci.yml", dest=".github/workflows/ci.yml"))
    with pytest.raises(ProfilePathEscapeError):
        compute_files_diff(profile, target, templates)


def test_compute_files_diff_source_symlink_escape_raises_path_escape(
    tmp_path: Path,
) -> None:
    """Same defense for source: if a templates entry would escape via symlink."""
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    outside = tmp_path / "outside"
    templates.mkdir()
    target.mkdir()
    outside.mkdir()
    (outside / "evil.yml").write_text("evil\n")

    # Make ci/ inside templates a symlink to outside
    (templates / "ci").symlink_to(outside)

    profile = _make_profile(FileEntry(source="ci/evil.yml", dest="x.yml"))
    with pytest.raises(ProfilePathEscapeError):
        compute_files_diff(profile, target, templates)


def test_file_create_is_frozen() -> None:
    """Diff entries must be immutable so callers can't mutate them
    between compute and apply phases."""
    fc = FileCreate(source=Path("/s"), dest=Path("/d"))
    with pytest.raises(Exception):  # FrozenInstanceError
        fc.source = Path("/other")  # type: ignore[misc]
