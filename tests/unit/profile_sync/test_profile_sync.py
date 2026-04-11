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
    apply_files_diff,
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


# apply_files_diff tests


def test_apply_files_diff_writes_creates(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "new\n")

    profile = _make_profile(FileEntry(source="ci.yml", dest=".github/workflows/ci.yml"))
    diff = compute_files_diff(profile, target, templates)
    apply_files_diff(diff, target, templates)

    written = target / ".github/workflows/ci.yml"
    assert written.exists()
    assert written.read_text() == "new\n"


def test_apply_files_diff_creates_parent_directories(tmp_path: Path) -> None:
    """Phase 6 AC: parent directories must be created automatically.
    Consumer repos may be missing .github/workflows/."""
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "x\n")

    profile = _make_profile(FileEntry(source="ci.yml", dest=".github/workflows/ci.yml"))
    diff = compute_files_diff(profile, target, templates)

    assert not (target / ".github").exists()
    apply_files_diff(diff, target, templates)
    assert (target / ".github" / "workflows" / "ci.yml").is_file()


def test_apply_files_diff_overwrite_blocked_without_force(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "new\n")
    _write_target(target, "ci.yml", "old\n")

    profile = _make_profile(FileEntry(source="ci.yml", dest="ci.yml"))
    diff = compute_files_diff(profile, target, templates)
    with pytest.raises(ProfileConflictError):
        apply_files_diff(diff, target, templates, force=False)

    # File untouched
    assert (target / "ci.yml").read_text() == "old\n"


def test_apply_files_diff_overwrite_allowed_with_force(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "new\n")
    _write_target(target, "ci.yml", "old\n")

    profile = _make_profile(FileEntry(source="ci.yml", dest="ci.yml"))
    diff = compute_files_diff(profile, target, templates)
    apply_files_diff(diff, target, templates, force=True)
    assert (target / "ci.yml").read_text() == "new\n"


def test_apply_files_diff_skip_if_exists_not_overwritten_with_force(
    tmp_path: Path,
) -> None:
    """LOAD-BEARING: skip_if_exists is absolute. Even --force does not
    touch a SkipExists entry."""
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "claude.md", "starter\n")
    _write_target(target, "CLAUDE.md", "user content\n")

    profile = _make_profile(
        FileEntry(source="claude.md", dest="CLAUDE.md", skip_if_exists=True)
    )
    diff = compute_files_diff(profile, target, templates)
    apply_files_diff(diff, target, templates, force=True)
    assert (target / "CLAUDE.md").read_text() == "user content\n"


def test_apply_files_diff_progress_callback_invoked_per_write(
    tmp_path: Path,
) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "a.yml", "a\n")
    _write_template(templates, "b.yml", "b\n")
    _write_target(target, "c.yml", "c-old\n")  # will overwrite
    _write_template(templates, "c.yml", "c-new\n")

    profile = _make_profile(
        FileEntry(source="a.yml", dest="a.yml"),
        FileEntry(source="b.yml", dest="b.yml"),
        FileEntry(source="c.yml", dest="c.yml"),
    )
    diff = compute_files_diff(profile, target, templates)

    progress_calls: list[str] = []
    apply_files_diff(
        diff, target, templates, force=True, progress=progress_calls.append
    )

    assert len(progress_calls) == 3


def test_apply_files_diff_skipped_and_noops_do_not_invoke_progress(
    tmp_path: Path,
) -> None:
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "a.yml", "x\n")
    _write_target(target, "a.yml", "x\n")  # noop
    _write_template(templates, "b.yml", "starter\n")
    _write_target(target, "b.yml", "user\n")  # skipped

    profile = _make_profile(
        FileEntry(source="a.yml", dest="a.yml"),
        FileEntry(source="b.yml", dest="b.yml", skip_if_exists=True),
    )
    diff = compute_files_diff(profile, target, templates)

    progress_calls: list[str] = []
    apply_files_diff(diff, target, templates, progress=progress_calls.append)
    assert progress_calls == []


def test_apply_files_diff_conflict_check_is_atomic(tmp_path: Path) -> None:
    """LOAD-BEARING: if force=False and ANY overwrite exists, NO file is
    written — not even the Creates."""
    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "create.yml", "new\n")
    _write_template(templates, "overwrite.yml", "new\n")
    _write_target(target, "overwrite.yml", "old\n")

    profile = _make_profile(
        FileEntry(source="create.yml", dest="create.yml"),
        FileEntry(source="overwrite.yml", dest="overwrite.yml"),
    )
    diff = compute_files_diff(profile, target, templates)
    with pytest.raises(ProfileConflictError):
        apply_files_diff(diff, target, templates, force=False)

    # The Create entry must NOT have been written
    assert not (target / "create.yml").exists()
    # The Overwrite target must be untouched
    assert (target / "overwrite.yml").read_text() == "old\n"


# OSError wrapping (silent-failure-hunter findings + Codex MEDIUM #2)
def test_compute_files_diff_dest_is_directory_raises_io_error(
    tmp_path: Path,
) -> None:
    """If the dest path exists but is a DIRECTORY (not a regular file),
    we must raise ProfileIOError with an actionable message — not let
    IsADirectoryError propagate as a raw traceback. Codex review #2."""
    from gh_manage.profile_sync import ProfileIOError

    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "x\n")
    # Create a directory at the dest path (not a file)
    (target / "ci.yml").mkdir()

    profile = _make_profile(FileEntry(source="ci.yml", dest="ci.yml"))
    with pytest.raises(ProfileIOError, match="not a regular file"):
        compute_files_diff(profile, target, templates)


def test_compute_files_diff_unreadable_source_wraps_oserror(
    tmp_path: Path,
) -> None:
    """If the source template can't be read (e.g., permission denied),
    raise ProfileIOError with context — not a raw OSError traceback.
    silent-failure-hunter CRITICAL #2."""
    from gh_manage.profile_sync import ProfileIOError

    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "x\n")
    # Make the file unreadable (chmod 000)
    (templates / "ci.yml").chmod(0o000)

    profile = _make_profile(FileEntry(source="ci.yml", dest="ci.yml"))
    try:
        with pytest.raises(ProfileIOError, match="Cannot read template"):
            compute_files_diff(profile, target, templates)
    finally:
        (templates / "ci.yml").chmod(0o644)  # restore for cleanup


def test_apply_files_diff_unwritable_target_wraps_oserror(
    tmp_path: Path,
) -> None:
    """If apply_files_diff can't write to dest (e.g., parent is read-only),
    raise ProfileIOError with context. silent-failure-hunter CRITICAL #1
    + HIGH #3."""
    from gh_manage.profile_sync import ProfileIOError

    templates = tmp_path / "templates"
    target = tmp_path / "target"
    target.mkdir()
    _write_template(templates, "ci.yml", "x\n")
    # Make target read-only so write_bytes fails
    target.chmod(0o555)

    profile = _make_profile(FileEntry(source="ci.yml", dest="ci.yml"))
    diff = compute_files_diff(profile, target, templates)
    try:
        with pytest.raises(ProfileIOError):
            apply_files_diff(diff, target, templates)
    finally:
        target.chmod(0o755)  # restore for cleanup
