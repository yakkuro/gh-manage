"""`gh manage init` — bootstrap a fresh repo with a gh-manage profile."""

from __future__ import annotations

from pathlib import Path

import click

from gh_manage import doctor as doctor_pkg
from gh_manage import git_cli, labels_sync, profile_sync, protection_sync
from gh_manage.commands._shared import (
    format_files_diff,
    handle_errors,
    resolve_backup_dir,
    resolve_branch_protection_path,
    resolve_default_labels_path,
    resolve_profile_path,
    resolve_templates_root,
)
from gh_manage.config import load_config
from gh_manage.doctor import report as doctor_report
from gh_manage.github_api import labels as labels_api
from gh_manage.github_api import protection as protection_api
from gh_manage.github_client import GhNotFoundError
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.labels import LabelsConfig
from gh_manage.models.profiles import ProfileSpec


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
@handle_errors
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
    profile_path = resolve_profile_path(profile_name)
    profile = load_config(profile_path, ProfileSpec)
    if profile.name != profile_name:
        from gh_manage.config import ConfigValidationError

        raise ConfigValidationError(
            f"Profile filename {profile_name!r} does not match its `name` "
            f"field {profile.name!r}. Rename the file or fix the YAML."
        )

    templates_root = resolve_templates_root()
    files_diff = profile_sync.compute_files_diff(profile, target, templates_root)

    # Labels: ALWAYS computed for init (Q1 design decision)
    labels_path = resolve_default_labels_path()
    labels_config = load_config(labels_path, LabelsConfig)
    current_labels = labels_api.list_labels(owner_repo)
    labels_diff = labels_sync.compute_diff(current_labels, labels_config)

    # Protection: computed only when profile has a policy (Phase 7)
    protection_diff = None
    if profile.protection_policy is not None:
        bp_config = load_config(
            resolve_branch_protection_path(), BranchProtectionConfig
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
    click.echo(format_files_diff(files_diff))
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

    if protection_diff is not None:
        click.echo("")
        click.echo(
            f"Branch protection (main): {len(protection_diff.changes)} change(s)"
        )
        for change in protection_diff.changes:
            click.echo(
                f"  {change.field_path}: {change.current_value} → {change.desired_value}"
            )

    if not apply_flag:
        n_protection = len(protection_diff.changes) if protection_diff else 0
        click.echo(
            f"\nDry-run: {len(files_diff.creates) + len(files_diff.overwrites)} "
            f"file changes, {labels_diff.total_changes} label changes, "
            f"{n_protection} protection changes. "
            f"Re-run with --apply to execute."
        )
        return

    # Pre-apply validation: fail fast on protection downgrade BEFORE any
    # side-effect (files, labels, protection). Otherwise an aborting
    # downgrade would leave the repo in a partial-apply state with files
    # and labels already written.
    if (
        protection_diff is not None
        and not protection_diff.is_empty
        and protection_diff.has_downgrades
    ):
        raise click.ClickException(
            f"Protection downgrade detected during init. "
            f"init does not force-downgrade protection. "
            f"Run `gh manage protection sync {owner_repo} --profile "
            f"{profile_name} --downgrade-allowed --apply --yes` "
            f"explicitly to override, then re-run init."
        )

    # Apply
    click.echo("")
    created_paths: list[Path] = profile_sync.apply_files_diff(
        files_diff, target, templates_root, force=force, progress=click.echo
    )
    labels_sync.apply_diff(labels_diff, owner_repo, progress=click.echo)

    if protection_diff is not None and not protection_diff.is_empty:
        backup_dir = resolve_backup_dir()
        protection_sync.apply_protection_diff(
            protection_diff,
            owner_repo,
            "main",
            downgrade_allowed=False,
            backup_dir=backup_dir,
            progress=click.echo,
        )

    # Post-apply doctor gate (spec §5.B).
    # Critical findings trigger rollback: remove files init created
    # (best-effort unlink), surface the doctor findings.
    findings = doctor_pkg.run_on_path(target, profile_name=profile_name)
    critical = tuple(f for f in findings if f.severity == "critical")
    if critical:
        click.echo("", err=True)
        click.echo("init post-check found critical findings:", err=True)
        click.echo(
            doctor_report.format_stdout(critical, repo=owner_repo),
            err=True,
        )
        for p in reversed(created_paths):
            try:
                if p.is_file():
                    p.unlink()
            except OSError as roll_err:
                click.echo(
                    f"WARNING: rollback failed for {p}: {roll_err}",
                    err=True,
                )
        raise click.ClickException(
            "init aborted due to critical doctor findings; rolled back "
            "files. See docs/specs/2026-04-17-doctor-guardrail-design.md §5."
        )

    click.echo("\nDone. Next steps:")
    click.echo("  git status                # review what gh-manage placed")
    click.echo("  git add <gh-manage paths> # stage only the new files")
    click.echo("  git commit -m 'chore: bootstrap with gh-manage init'")
