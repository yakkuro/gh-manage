"""`gh manage init` — bootstrap a fresh repo with a gh-manage profile."""

from __future__ import annotations

import functools
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage import git_cli, labels_sync, profile_sync
from gh_manage.config import ConfigError, load_config
from gh_manage.git_cli import GitError
from gh_manage.github_api import labels as labels_api
from gh_manage.github_client import GhError
from gh_manage.models.labels import LabelsConfig
from gh_manage.models.profiles import ProfileSpec
from gh_manage.profile_sync import ProfileError, ProfileFilesDiff

_F = TypeVar("_F", bound=Callable[..., Any])


def _handle_errors(func: _F) -> _F:
    """Decorator: catch GhError / ConfigError / GitError / ProfileError
    and re-raise as click.ClickException (exit 1 with `Error: <msg>`)."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (GhError, ConfigError, GitError, ProfileError) as e:
            raise click.ClickException(str(e)) from e

    return wrapper  # type: ignore[return-value]


def _resolve_profile_path(name: str) -> Path:
    """Resolve a profile name to a package-data Path.

    Raises ConfigError if the profile YAML doesn't exist.
    """
    candidate = Path(str(files("gh_manage.data.profiles") / f"{name}.yml"))
    if not candidate.is_file():
        from gh_manage.config import ConfigFileNotFoundError

        raise ConfigFileNotFoundError(
            f"Profile not found: {name!r}. "
            f"Looked in {candidate.parent}. "
            f"Available profiles can be listed with `gh manage profiles list` "
            f"(not yet implemented)."
        )
    return candidate


def _resolve_templates_root() -> Path:
    return Path(str(files("gh_manage.data") / "templates"))


def _resolve_default_labels_path() -> Path:
    return Path(str(files("gh_manage.data") / "labels.yml"))


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
    "init",
    help=(
        "Bootstrap a fresh repo with a gh-manage profile. Places profile "
        "files and syncs labels. Default is dry-run; pass --apply to execute."
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
@click.option(
    "--dry-run",
    is_flag=True,
    help="Explicit dry-run; conflicts with --apply.",
)
@click.option(
    "--apply",
    "apply_flag",
    is_flag=True,
    help="Actually execute changes (default is dry-run).",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing non-skip files.",
)
@_handle_errors
def init(
    path: Path,
    profile_name: str,
    dry_run: bool,
    apply_flag: bool,
    force: bool,
) -> None:
    if apply_flag and dry_run:
        raise click.UsageError("--apply and --dry-run are mutually exclusive.")

    target = path.resolve()

    # Precheck: derive owner/repo from origin remote
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

    # Labels: ALWAYS computed for init (Q1 design decision)
    labels_path = _resolve_default_labels_path()
    labels_config = load_config(labels_path, LabelsConfig)
    current_labels = labels_api.list_labels(owner_repo)
    labels_diff = labels_sync.compute_diff(current_labels, labels_config)

    # Print combined diff
    click.echo(_format_files_diff(files_diff))
    click.echo("")
    click.echo(f"Labels: {labels_diff.total_changes} change(s)")
    if not labels_diff.is_empty:
        for create in labels_diff.creates:
            click.echo(
                f"  + {create.label.name}  color={create.label.color}  "
                f"desc={create.label.description!r}"
            )
        for rename in labels_diff.renames:
            click.echo(f"  ~ {rename.old_name} → {rename.new_label.name}")
        for update in labels_diff.updates:
            click.echo(f"  ~ {update.label.name}  (color/desc update)")

    if not apply_flag:
        click.echo(
            f"\nDry-run: {len(files_diff.creates) + len(files_diff.overwrites)} "
            f"file changes, {labels_diff.total_changes} label changes. "
            f"Re-run with --apply to execute."
        )
        return

    # Apply
    click.echo("")
    profile_sync.apply_files_diff(
        files_diff, target, templates_root, force=force, progress=click.echo
    )
    labels_sync.apply_diff(labels_diff, owner_repo, progress=click.echo)
    click.echo("\nDone. Next steps:")
    click.echo("  git status                # review what gh-manage placed")
    click.echo("  git add <gh-manage paths> # stage only the new files")
    click.echo("  git commit -m 'chore: bootstrap with gh-manage init'")
