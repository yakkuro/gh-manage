"""Codex review CRITICAL #1: apply_files_diff MUST NOT return paths it
overwrote. init's doctor rollback unlinks every returned path, and
unlinking an overwritten path would destroy the user's pre-existing
content.

Spec §5.B defers tempdir-backed restoration to a future release —
until then, only CREATED paths are rollback-safe."""

from __future__ import annotations

from pathlib import Path

from gh_manage.models.profiles import FileEntry
from gh_manage.profile_sync import ProfileFilesDiff, apply_files_diff


def test_apply_files_diff_returns_only_created_paths(tmp_path: Path):
    target = tmp_path / "repo"
    target.mkdir()
    templates_root = tmp_path / "templates"
    templates_root.mkdir()

    src_new = templates_root / "new_file.txt"
    src_new.write_text("new-content")
    src_over = templates_root / "over_file.txt"
    src_over.write_text("updated-content")

    # Pre-existing file that will be overwritten.
    existing = target / "over_file.txt"
    existing.write_text("ORIGINAL-USER-CONTENT")

    file_new = FileEntry(source="new_file.txt", dest="new_file.txt")
    file_over = FileEntry(source="over_file.txt", dest="over_file.txt")

    creates = [
        type(
            "Create",
            (),
            {
                "source": src_new,
                "dest": target / "new_file.txt",
                "entry": file_new,
            },
        )()
    ]
    overwrites = [
        type(
            "Overwrite",
            (),
            {
                "source": src_over,
                "dest": existing,
                "entry": file_over,
            },
        )()
    ]
    diff = ProfileFilesDiff(
        creates=creates,
        overwrites=overwrites,
        skipped=[],
        noops=[],
    )

    created_paths = apply_files_diff(diff, target, templates_root, force=True)

    # Only the truly-new path appears in the return.
    assert target / "new_file.txt" in created_paths
    assert existing not in created_paths, (
        "Overwritten paths must not be in the return list — init's "
        "rollback would unlink the user's pre-existing content. "
        "Codex review CRITICAL #1."
    )
    # Content verified actually written
    assert (target / "new_file.txt").read_text() == "new-content"
    assert existing.read_text() == "updated-content"
