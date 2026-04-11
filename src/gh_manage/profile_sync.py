"""Pure-function profile engine: compute diff + apply.

Mirrors gh_manage.labels_sync's pattern. compute_files_diff produces a
ProfileFilesDiff describing what would happen; apply_files_diff
executes that diff with transactional conflict semantics.

This module knows about the local filesystem but not about subprocess,
git, or the GitHub API. Tests pass tmp_path-based fixtures.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gh_manage.models.profiles import ProfileSpec


# Diff entry types
@dataclass(frozen=True)
class FileCreate:
    """dest does not exist; will be written."""

    source: Path
    dest: Path


@dataclass(frozen=True)
class FileOverwrite:
    """dest exists with different content and skip_if_exists is False.
    Will be written iff apply_files_diff(force=True)."""

    source: Path
    dest: Path


@dataclass(frozen=True)
class FileSkipExists:
    """skip_if_exists=True and dest exists. Never written, even with --force."""

    dest: Path


@dataclass(frozen=True)
class FileNoop:
    """dest exists with byte-identical content. No write needed."""

    dest: Path


@dataclass(frozen=True)
class ProfileFilesDiff:
    """The output of compute_files_diff: four buckets of file operations.

    Note: only `creates` and `overwrites` represent actionable changes;
    `skipped` and `noops` are reported for transparency but don't trigger
    writes.
    """

    creates: tuple[FileCreate, ...]
    overwrites: tuple[FileOverwrite, ...]
    skipped: tuple[FileSkipExists, ...]
    noops: tuple[FileNoop, ...]

    @property
    def is_empty(self) -> bool:
        """No actionable changes. Skipped/Noops do not count."""
        return not (self.creates or self.overwrites)

    @property
    def has_overwrites(self) -> bool:
        return bool(self.overwrites)


# Error hierarchy
class ProfileError(Exception):
    """Base for profile_sync errors. Caught by commands/_handle_errors."""


class ProfileTemplateNotFoundError(ProfileError):
    """A profile.files entry references a source path that doesn't exist
    under templates_root."""


class ProfilePathEscapeError(ProfileError):
    """A profile.files entry's resolved source or dest path escapes its
    root directory (via symlink, absolute path, or surviving `..`).
    Raised by compute_files_diff before any IO."""


class ProfileConflictError(ProfileError):
    """Raised when apply_files_diff is called with overwrites and force=False.

    Contains the conflict list and an actionable message instructing
    the user to re-run with --force or remove the files manually.
    """

    def __init__(self, conflicts: tuple[FileOverwrite, ...]):
        self.conflicts = conflicts
        names = "\n  ".join(str(c.dest) for c in conflicts)
        super().__init__(
            f"{len(conflicts)} file(s) would be overwritten:\n  {names}\n"
            f"Re-run with --force to overwrite, or remove the files manually."
        )


def compute_files_diff(
    profile: ProfileSpec,
    target_root: Path,
    templates_root: Path,
) -> ProfileFilesDiff:
    """Compute the file placement diff for a profile.

    Implementation lands in Task 6.
    """
    raise NotImplementedError("Task 6")


def apply_files_diff(
    diff: ProfileFilesDiff,
    target_root: Path,
    templates_root: Path,
    *,
    force: bool = False,
    progress: Callable[[str], None] = lambda _: None,
) -> None:
    """Apply the diff with transactional conflict semantics.

    Implementation lands in Task 7.
    """
    raise NotImplementedError("Task 7")
