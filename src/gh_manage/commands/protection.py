"""`gh manage protection` — branch protection sync + diff commands."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from gh_manage import git_cli, protection_sync
from gh_manage.commands._shared import (
    handle_errors,
    resolve_backup_dir,
    resolve_branch_protection_path,
    resolve_profile_path,
)
from gh_manage.config import ConfigValidationError, load_config
from gh_manage.github_api import protection as protection_api
from gh_manage.github_client import GhNotFoundError
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.profiles import ProfileSpec
from gh_manage.protection_sync import (
    ProtectionDiff,
    ProtectionDowngradeError,
    ProtectionPolicyNotFoundError,
)

log = logging.getLogger(__name__)


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
    profile_path = resolve_profile_path(profile_name)
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

    bp_config = load_config(resolve_branch_protection_path(), BranchProtectionConfig)
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
@handle_errors
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

    log.info(
        "protection sync invoked: repo=%s profile=%s apply=%s downgrade_allowed=%s",
        owner_repo,
        profile_name,
        apply_flag,
        downgrade_allowed,
    )

    profile, bp_config = _load_profile_and_policy(profile_name)
    policy = bp_config.policies[profile.protection_policy]  # type: ignore[index]

    try:
        current = protection_api.get_branch_protection(owner_repo, "main")
    except GhNotFoundError:
        log.warning(
            "branch protection not configured on %s@main; treating as empty",
            owner_repo,
        )
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

        log.warning(
            "applying protection downgrade on %s@main: %d field(s) weakened",
            owner_repo,
            len(diff.downgrades),
        )

    backup_dir = resolve_backup_dir()
    click.echo("")
    protection_sync.apply_protection_diff(
        diff,
        owner_repo,
        "main",
        downgrade_allowed=downgrade_allowed,
        backup_dir=backup_dir,
        progress=click.echo,
    )

    log.info(
        "protection apply complete: repo=%s fields=%d",
        owner_repo,
        len(diff.changes),
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
@handle_errors
def diff_cmd(path: Path, profile_name: str, downgrade_allowed: bool) -> None:
    """Show diff between current protection and profile + policy state.

    Exit codes (for git-pre-commit / CI drift checks):
      0 = no changes, or non-downgrade changes, or downgrade + --downgrade-allowed
      1 = downgrade detected and --downgrade-allowed not passed
    """
    target = path.resolve()
    owner_repo = git_cli.get_origin_owner_repo(target)

    log.info(
        "protection diff invoked: repo=%s profile=%s",
        owner_repo,
        profile_name,
    )

    profile, bp_config = _load_profile_and_policy(profile_name)
    policy = bp_config.policies[profile.protection_policy]  # type: ignore[index]

    try:
        current = protection_api.get_branch_protection(owner_repo, "main")
    except GhNotFoundError:
        log.warning(
            "branch protection not configured on %s@main; treating as empty",
            owner_repo,
        )
        current = {}

    diff = protection_sync.compute_protection_diff(current, policy, profile, "main")

    click.echo(_format_diff(diff))

    if diff.is_empty:
        click.echo("\nNo changes.")
        return

    if diff.has_downgrades and not downgrade_allowed:
        sys.exit(1)
