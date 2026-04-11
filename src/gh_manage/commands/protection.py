"""`gh manage protection` — branch protection sync + diff commands."""

from __future__ import annotations

import functools
import re
import sys
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage import git_cli, protection_sync
from gh_manage.config import ConfigError, ConfigValidationError, load_config
from gh_manage.git_cli import GitError
from gh_manage.github_api import protection as protection_api
from gh_manage.github_client import GhError, GhNotFoundError
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.profiles import ProfileSpec
from gh_manage.protection_sync import (
    ProtectionDiff,
    ProtectionDowngradeError,
    ProtectionError,
    ProtectionPolicyNotFoundError,
)

_F = TypeVar("_F", bound=Callable[..., Any])

_VALID_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _handle_errors(func: _F) -> _F:
    """Decorator: catch all domain errors and re-raise as ClickException."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (
            GhError,
            ConfigError,
            GitError,
            ProtectionError,
        ) as e:
            raise click.ClickException(str(e)) from e

    return wrapper  # type: ignore[return-value]


def _resolve_profile_path(name: str) -> Path:
    """Resolve a profile name to a package-data Path.

    Profile names are bundle identifiers, NOT user paths. They MUST be a
    single segment matching `[A-Za-z0-9][A-Za-z0-9._-]*` — anything else
    (slashes, `..`, leading dot, empty) is rejected to prevent reading
    arbitrary YAML files outside the bundled profiles directory.

    After resolution the candidate path is re-checked against the profiles
    root with `Path.resolve() + is_relative_to()` as a defense-in-depth
    layer.

    Raises ConfigError if the name is invalid or the profile YAML doesn't
    exist.
    """
    from gh_manage.config import ConfigFileNotFoundError

    if not name or not _VALID_PROFILE_NAME_RE.match(name):
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


def _resolve_branch_protection_path() -> Path:
    return Path(str(files("gh_manage.data") / "branch-protection.yml"))


def _resolve_backup_dir() -> Path:
    return Path.home() / ".gh-manage" / "backups"


def _is_tty_stdin() -> bool:
    """Check if stdin is a TTY. Extracted for test mocking."""
    return click.get_text_stream("stdin").isatty()


def _format_diff(diff: ProtectionDiff) -> str:
    lines: list[str] = ["Branch protection (main):"]
    if diff.is_empty:
        lines.append("  (no changes)")
        return "\n".join(lines)

    for change in diff.changes:
        classification = (
            "(DOWNGRADE)"
            if any(d.field_path == change.field_path for d in diff.downgrades)
            else "(upgrade)"
        )
        lines.append(
            f"  {change.field_path}: {change.current_value} → "
            f"{change.desired_value}  {classification}"
        )

    if diff.has_downgrades:
        lines.append("")
        lines.append(f"Downgrades: {len(diff.downgrades)}")
        for d in diff.downgrades:
            lines.append(f"  {d.field_path}: {d.reason}")

    return "\n".join(lines)


def _load_profile_and_policy(
    profile_name: str,
) -> tuple[ProfileSpec, BranchProtectionConfig]:
    """Common precheck for protection subcommands.

    Loads the profile, validates protection_policy is set, loads the
    branch-protection config, validates the policy exists in it.
    Raises ConfigValidationError or ProtectionPolicyNotFoundError on
    mismatch.
    """
    profile_path = _resolve_profile_path(profile_name)
    profile = load_config(profile_path, ProfileSpec)
    if profile.name != profile_name:
        raise ConfigValidationError(
            f"Profile filename {profile_name!r} does not match its `name` "
            f"field {profile.name!r}."
        )
    if profile.protection_policy is None:
        raise ConfigValidationError(
            f"Profile {profile_name!r} has no protection_policy field. "
            f"Add `protection_policy: <name>` to the profile YAML and try again."
        )

    bp_config = load_config(_resolve_branch_protection_path(), BranchProtectionConfig)
    if profile.protection_policy not in bp_config.policies:
        raise ProtectionPolicyNotFoundError(
            f"Policy {profile.protection_policy!r} not found in "
            f"branch-protection.yml. Available policies: "
            f"{sorted(bp_config.policies.keys())}. Either fix the profile's "
            f"`protection_policy` field or add a new policy to "
            f"src/gh_manage/data/branch-protection.yml."
        )

    return profile, bp_config


@click.group(
    "protection", help="Synchronize branch protection from profiles + policies."
)
def protection() -> None:
    """Entry group for protection subcommands."""


@protection.command("sync")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
)
@click.option(
    "--profile",
    "profile_name",
    required=True,
    help="Profile name (resolves to bundled profiles/<name>.yml).",
)
@click.option("--dry-run", is_flag=True)
@click.option("--apply", "apply_flag", is_flag=True)
@click.option(
    "--downgrade-allowed",
    is_flag=True,
    help="Allow applying weaker protection (requires --yes in non-TTY).",
)
@click.option(
    "--yes",
    "yes_flag",
    is_flag=True,
    help="Skip interactive confirmation (required for non-TTY downgrade).",
)
@_handle_errors
def sync(
    path: Path,
    profile_name: str,
    dry_run: bool,
    apply_flag: bool,
    downgrade_allowed: bool,
    yes_flag: bool,
) -> None:
    """Apply profile + policy to a repo's branch protection.

    Default is dry-run; pass --apply to execute. Downgrades require
    --downgrade-allowed + --yes (or TTY interactive confirm).
    """
    if apply_flag and dry_run:
        raise click.UsageError("--apply and --dry-run are mutually exclusive.")

    target = path.resolve()
    owner_repo = git_cli.get_origin_owner_repo(target)

    profile, bp_config = _load_profile_and_policy(profile_name)
    policy = bp_config.policies[profile.protection_policy]  # type: ignore[index]

    try:
        current = protection_api.get_branch_protection(owner_repo, "main")
    except GhNotFoundError:
        current = {}  # no protection yet → treat as empty

    diff = protection_sync.compute_protection_diff(current, policy, profile, "main")

    click.echo(_format_diff(diff))

    if diff.is_empty:
        click.echo("\nNo changes.")
        return

    if not apply_flag:
        # Dry-run: exit 1 if downgrade present without flag (for pre-commit hooks)
        suffix = f", {len(diff.downgrades)} downgrade(s)" if diff.has_downgrades else ""
        click.echo(
            f"\nDry-run: {len(diff.changes)} field change(s){suffix}. "
            f"Re-run with --apply to execute."
        )
        if diff.has_downgrades and not downgrade_allowed:
            sys.exit(1)
        return

    # --apply path
    if diff.has_downgrades and not downgrade_allowed:
        raise ProtectionDowngradeError(diff.downgrades)

    if diff.has_downgrades and downgrade_allowed:
        # Safety prompt / --yes gate
        if _is_tty_stdin():
            if not click.confirm(
                f"\nThis will weaken {len(diff.downgrades)} protection field(s). Continue?",
                default=False,
            ):
                click.echo("Aborted.")
                return
        elif not yes_flag:
            raise click.ClickException(
                "Non-TTY environment detected. Pass --yes to confirm the "
                "downgrade in CI/non-interactive contexts."
            )

    backup_dir = _resolve_backup_dir()
    click.echo("")
    protection_sync.apply_protection_diff(
        diff,
        owner_repo,
        "main",
        downgrade_allowed=downgrade_allowed,
        backup_dir=backup_dir,
        progress=click.echo,
    )
    click.echo(f"\nDone. Protection updated for {owner_repo}:main.")


@protection.command("diff")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
)
@click.option(
    "--profile",
    "profile_name",
    required=True,
    help="Profile name (resolves to bundled profiles/<name>.yml).",
)
@click.option(
    "--downgrade-allowed",
    is_flag=True,
    help="Suppress the exit-1 signal when downgrade is detected (for CI drift checks).",
)
@_handle_errors
def diff_cmd(path: Path, profile_name: str, downgrade_allowed: bool) -> None:
    """Show diff between current protection and profile + policy state.

    Exit codes (for git-pre-commit / CI drift checks):
      0 = no changes, or non-downgrade changes, or downgrade + --downgrade-allowed
      1 = downgrade detected and --downgrade-allowed not passed
    """
    target = path.resolve()
    owner_repo = git_cli.get_origin_owner_repo(target)

    profile, bp_config = _load_profile_and_policy(profile_name)
    policy = bp_config.policies[profile.protection_policy]  # type: ignore[index]

    try:
        current = protection_api.get_branch_protection(owner_repo, "main")
    except GhNotFoundError:
        current = {}

    diff = protection_sync.compute_protection_diff(current, policy, profile, "main")

    click.echo(_format_diff(diff))

    if diff.is_empty:
        click.echo("\nNo changes.")
        return

    if diff.has_downgrades and not downgrade_allowed:
        sys.exit(1)
