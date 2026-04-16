"""Shared CLI helpers for gh-manage commands.

Extracted from commands/init.py, apply.py, drift.py, protection.py to
eliminate security-critical code duplication (Issue #38). The path
traversal defense in resolve_profile_path is load-bearing — having it
in one place ensures a security fix is applied once, not in 4 files.

This module is internal to the commands package (leading underscore).
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage.config import ConfigError, ConfigFileNotFoundError
from gh_manage.drift_sync import DriftError
from gh_manage.git_cli import GitError
from gh_manage.github_client import GhError
from gh_manage.profile_sync import ProfileError, ProfileFilesDiff
from gh_manage.protection_sync import ProtectionError

_F = TypeVar("_F", bound=Callable[..., Any])

VALID_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_DOMAIN_ERRORS = (
    GhError,
    ConfigError,
    GitError,
    ProfileError,
    ProtectionError,
    DriftError,
)


def handle_errors(func: _F) -> _F:
    """Decorator: catch domain errors and re-raise as click.ClickException.

    Uses the union of all domain exception types so every command module
    can share one decorator without maintaining per-command exception lists.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except _DOMAIN_ERRORS as e:
            raise click.ClickException(str(e)) from e

    return wrapper  # type: ignore[return-value]


def resolve_profile_path(name: str) -> Path:
    """Resolve a profile name to a bundled YAML path.

    LOAD-BEARING path traversal defense: regex rejects slashes / .. /
    leading dots, then Path.resolve() + is_relative_to() provides
    defense-in-depth against symlink escapes.

    Raises ConfigFileNotFoundError on invalid name or missing profile.
    """
    if not name or not VALID_PROFILE_NAME_RE.match(name):
        raise ConfigFileNotFoundError(
            f"Invalid profile name: {name!r}. Profile names must be a single "
            f"identifier (alphanumeric plus `._-`, not starting with `.`). "
            f"Path separators and `..` are not allowed."
        )

    profiles_root = Path(str(files("gh_manage.data.profiles"))).resolve()
    candidate = (profiles_root / f"{name}.yml").resolve()

    if not candidate.is_relative_to(profiles_root):
        raise ConfigFileNotFoundError(
            f"Profile path resolved outside the bundled profiles directory: "
            f"{name!r} → {candidate}. This should not happen with a valid "
            f"profile name; if it does, it indicates a packaging bug."
        )

    if not candidate.is_file():
        raise ConfigFileNotFoundError(
            f"Profile not found: {name!r}. "
            f"Looked in {profiles_root}. "
            f"Available profiles can be listed with `gh manage profiles list` "
            f"(not yet implemented)."
        )
    return candidate


def resolve_templates_root() -> Path:
    """Resolve the bundled templates directory."""
    return Path(str(files("gh_manage.data") / "templates"))


def resolve_default_labels_path() -> Path:
    """Resolve the bundled labels.yml path."""
    return Path(str(files("gh_manage.data") / "labels.yml"))


def resolve_branch_protection_path() -> Path:
    """Resolve the bundled branch-protection.yml path."""
    return Path(str(files("gh_manage.data") / "branch-protection.yml"))


def resolve_repos_path() -> Path:
    """Resolve the bundled repos.yml path."""
    return Path(str(files("gh_manage.data") / "repos.yml"))


def resolve_backup_dir() -> Path:
    """Resolve the backup directory for protection snapshots."""
    return Path.home() / ".gh-manage" / "backups"


def format_files_diff(diff: ProfileFilesDiff) -> str:
    """Format a ProfileFilesDiff for human-readable CLI output."""
    lines: list[str] = ["Files:"]
    if diff.is_empty and not diff.skipped and not diff.noops:
        lines.append("  (no file changes)")
    for c in diff.creates:
        lines.append(f"  + create    {c.dest}")
    for o in diff.overwrites:
        lines.append(f"  ! overwrite {o.dest}  (use --force)")
    for s in diff.skipped:
        lines.append(f"  ≈ skip      {s.dest}  (skip_if_exists)")
    for n in diff.noops:
        lines.append(f"  = noop      {n.dest}")
    return "\n".join(lines)
