"""`gh manage apply` — apply a gh-manage profile to an existing repo."""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage import git_cli, labels_sync, profile_sync, protection_sync
from gh_manage.config import ConfigError, load_config
from gh_manage.git_cli import GitError
from gh_manage.github_api import labels as labels_api
from gh_manage.github_api import protection as protection_api
from gh_manage.github_client import GhError, GhNotFoundError
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.labels import LabelsConfig
from gh_manage.models.profiles import ProfileSpec
from gh_manage.profile_sync import ProfileError, ProfileFilesDiff
from gh_manage.protection_sync import ProtectionError

_F = TypeVar("_F", bound=Callable[..., Any])


def _handle_errors(func: _F) -> _F:
    """Decorator: catch GhError / ConfigError / GitError / ProfileError / ProtectionError
    and re-raise as click.ClickException (exit 1 with `Error: <msg>`)."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (GhError, ConfigError, GitError, ProfileError, ProtectionError) as e:
            raise click.ClickException(str(e)) from e

    return wrapper  # type: ignore[return-value]


_VALID_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


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


def _resolve_templates_root() -> Path:
    return Path(str(files("gh_manage.data") / "templates"))


def _resolve_default_labels_path() -> Path:
    return Path(str(files("gh_manage.data") / "labels.yml"))


def _resolve_branch_protection_path() -> Path:
    return Path(str(files("gh_manage.data") / "branch-protection.yml"))


def _resolve_backup_dir() -> Path:
    return Path.home() / ".gh-manage" / "backups"


def _format_files_diff(diff: ProfileFilesDiff) -> str:
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


@click.command(
    "apply",
    help=(
        "Apply a gh-manage profile to an existing repo. By default updates "
        "files only — use --also-labels to also sync labels. Default is "
        "dry-run; pass --apply to execute."
    ),
)
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
@click.option("--force", is_flag=True, help="Overwrite existing non-skip files.")
@click.option(
    "--also-labels",
    is_flag=True,
    help="Also sync labels (off by default for safety).",
)
@click.option(
    "--also-protection",
    is_flag=True,
    help="Also apply branch protection (Phase 7 — not yet implemented).",
)
@_handle_errors
def apply(
    path: Path,
    profile_name: str,
    dry_run: bool,
    apply_flag: bool,
    force: bool,
    also_labels: bool,
    also_protection: bool,
) -> None:
    if apply_flag and dry_run:
        raise click.UsageError("--apply and --dry-run are mutually exclusive.")

    target = path.resolve()

    # Precheck: derive owner/repo from origin
    owner_repo = git_cli.get_origin_owner_repo(target)

    # Load profile from package data
    profile_path = _resolve_profile_path(profile_name)
    profile = load_config(profile_path, ProfileSpec)
    if profile.name != profile_name:
        from gh_manage.config import ConfigValidationError

        raise ConfigValidationError(
            f"Profile filename {profile_name!r} does not match its `name` "
            f"field {profile.name!r}. Rename the file or fix the YAML."
        )

    templates_root = _resolve_templates_root()
    files_diff = profile_sync.compute_files_diff(profile, target, templates_root)

    labels_diff = None
    if also_labels:
        labels_path = _resolve_default_labels_path()
        labels_config = load_config(labels_path, LabelsConfig)
        current_labels = labels_api.list_labels(owner_repo)
        labels_diff = labels_sync.compute_diff(current_labels, labels_config)

    protection_diff = None
    if also_protection:
        if profile.protection_policy is None:
            raise click.ClickException(
                f"Profile {profile_name!r} has no `protection_policy` field — "
                f"`--also-protection` has nothing to apply. Use a profile that "
                f"sets `protection_policy` or drop the `--also-protection` flag."
            )
        bp_config = load_config(
            _resolve_branch_protection_path(), BranchProtectionConfig
        )
        if profile.protection_policy not in bp_config.policies:
            from gh_manage.protection_sync import ProtectionPolicyNotFoundError

            raise ProtectionPolicyNotFoundError(
                f"Policy {profile.protection_policy!r} not found in "
                f"branch-protection.yml. Available policies: "
                f"{sorted(bp_config.policies.keys())}."
            )
        policy = bp_config.policies[profile.protection_policy]
        try:
            current_protection = protection_api.get_branch_protection(
                owner_repo, "main"
            )
        except GhNotFoundError:
            current_protection = {}
        protection_diff = protection_sync.compute_protection_diff(
            current_protection, policy, profile, "main"
        )

    # Print combined diff
    click.echo(_format_files_diff(files_diff))
    if labels_diff is not None:
        click.echo("")
        click.echo(f"Labels: {labels_diff.total_changes} change(s)")

    if protection_diff is not None:
        click.echo("")
        click.echo(
            f"Branch protection (main): {len(protection_diff.changes)} change(s)"
        )
        for change in protection_diff.changes:
            click.echo(
                f"  {change.field_path}: {change.current_value} → {change.desired_value}"
            )

    n_file_changes = len(files_diff.creates) + len(files_diff.overwrites)
    n_label_changes = labels_diff.total_changes if labels_diff is not None else 0
    n_protection_changes = (
        len(protection_diff.changes) if protection_diff is not None else 0
    )

    if not apply_flag:
        click.echo(
            f"\nDry-run: {n_file_changes} file changes, "
            f"{n_label_changes} label changes, "
            f"{n_protection_changes} protection changes. Re-run with --apply to execute."
        )
        return

    # Apply
    click.echo("")
    profile_sync.apply_files_diff(
        files_diff, target, templates_root, force=force, progress=click.echo
    )
    if labels_diff is not None:
        labels_sync.apply_diff(labels_diff, owner_repo, progress=click.echo)

    if protection_diff is not None and not protection_diff.is_empty:
        if protection_diff.has_downgrades:
            raise click.ClickException(
                f"Protection downgrade detected during `apply --also-protection`. "
                f"`apply` does not force-downgrade protection. Run "
                f"`gh manage protection sync {owner_repo} --profile "
                f"{profile_name} --downgrade-allowed --apply --yes` "
                f"explicitly to override, then re-run `apply`."
            )
        backup_dir = _resolve_backup_dir()
        protection_sync.apply_protection_diff(
            protection_diff,
            owner_repo,
            "main",
            downgrade_allowed=False,
            backup_dir=backup_dir,
            progress=click.echo,
        )

    click.echo(
        f"\nApplied {n_file_changes} file changes"
        + (f" + {n_label_changes} label changes" if also_labels else "")
        + "."
    )
