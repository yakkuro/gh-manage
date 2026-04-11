"""gh manage labels — sync, diff, show GitHub repo labels."""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage import labels_sync
from gh_manage.config import ConfigError, load_config
from gh_manage.github_api import labels as labels_api
from gh_manage.github_client import GhError
from gh_manage.labels_sync import LabelsDiff
from gh_manage.models.labels import LabelsConfig
from gh_manage.repo_ref import parse_repo

DEFAULT_CONFIG_PATH = Path(str(files("gh_manage.data") / "labels.yml"))

_F = TypeVar("_F", bound=Callable[..., Any])


def _format_diff(diff: LabelsDiff) -> str:
    """Render LabelsDiff as plain text (Q7 A)."""
    lines: list[str] = []
    for rename in diff.renames:
        lines.append(f"~ {rename.old_name} → {rename.new_label.name}")
        lines.append(
            f"    color={rename.new_label.color}  desc={rename.new_label.description!r}"
        )
    for create in diff.creates:
        lines.append(
            f"+ {create.label.name}  color={create.label.color}  "
            f"desc={create.label.description!r}"
        )
    for update in diff.updates:
        lines.append(
            f"≈ {update.label.name}  color={update.label.color}  "
            f"desc={update.label.description!r}"
        )
    for delete in diff.deletes:
        lines.append(f"- {delete.name}")
    return "\n".join(lines)


def _handle_errors(func: _F) -> _F:
    """Decorator: catch GhError/ConfigError and re-raise as click.ClickException.

    click.ClickException prints `Error: <msg>` to stderr and exits 1.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (GhError, ConfigError) as e:
            raise click.ClickException(str(e)) from e

    return wrapper  # type: ignore[return-value]


@click.group(help="Synchronize GitHub repo labels against the bundled labels.yml.")
def labels() -> None:
    """Entry group for labels subcommands."""


@labels.command(
    help=(
        "Apply the bundled labels.yml to a repo. Default is dry-run; "
        "pass --apply to execute."
    ),
)
@click.argument("repo")
@click.option(
    "--apply",
    "apply_flag",
    is_flag=True,
    help="Actually execute changes (default is dry-run).",
)
@click.option(
    "--prune",
    is_flag=True,
    help="Delete labels not in config (requires --apply).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Explicit dry-run; conflicts with --apply.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_CONFIG_PATH,
    help="Path to labels.yml.",
)
@_handle_errors
def sync(
    repo: str,
    apply_flag: bool,
    prune: bool,
    dry_run: bool,
    config_path: Path,
) -> None:
    if apply_flag and dry_run:
        raise click.UsageError("--apply and --dry-run are mutually exclusive.")

    qualified = parse_repo(repo)
    config = load_config(config_path, LabelsConfig)
    current = labels_api.list_labels(qualified)

    diff = labels_sync.compute_diff(current, config, prune=prune)

    if diff.is_empty:
        click.echo("No changes.")
        return

    click.echo(_format_diff(diff))

    if not apply_flag:
        click.echo(
            f"\nDry-run: {diff.total_changes} changes. Re-run with --apply to execute."
        )
        return

    click.echo("")
    labels_sync.apply_diff(diff, qualified, progress=click.echo)
    click.echo(f"\nApplied {diff.total_changes} changes.")


@labels.command(
    "diff",
    help=(
        "Show diff between the bundled labels.yml and a repo. "
        "Exit 0 if no diff, 1 if diff present (git diff --quiet style)."
    ),
)
@click.argument("repo")
@click.option(
    "--prune",
    is_flag=True,
    help="Include would-be deletes in the diff.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_CONFIG_PATH,
)
@_handle_errors
def diff_cmd(repo: str, prune: bool, config_path: Path) -> None:
    qualified = parse_repo(repo)
    config = load_config(config_path, LabelsConfig)
    current = labels_api.list_labels(qualified)

    diff = labels_sync.compute_diff(current, config, prune=prune)

    if diff.is_empty:
        click.echo("No diff.")
        sys.exit(0)

    click.echo(_format_diff(diff))
    sys.exit(1)


@labels.command(
    "show",
    help="List current labels on a repo (read-only).",
)
@click.argument("repo")
@_handle_errors
def show(repo: str) -> None:
    """Show does NOT load config/labels.yml — it lists the repo's current
    state. No --config flag, no config validation. The only failure modes
    are GhError subclasses from the list_labels call."""
    qualified = parse_repo(repo)
    current = labels_api.list_labels(qualified)
    for label in sorted(current, key=lambda lb: lb.name):
        click.echo(f"{label.name}  color={label.color}  desc={label.description!r}")
