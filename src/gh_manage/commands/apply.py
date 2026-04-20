"""`gh manage apply` — apply a gh-manage profile to an existing repo."""

from __future__ import annotations

import logging
from pathlib import Path

import click

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
from gh_manage.github_api import labels as labels_api
from gh_manage.github_api import protection as protection_api
from gh_manage.github_client import GhNotFoundError
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.labels import LabelsConfig
from gh_manage.models.profiles import ProfileSpec

log = logging.getLogger(__name__)


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
@handle_errors
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

    log.info(
        "apply invoked: repo=%s profile=%s apply=%s also_labels=%s also_protection=%s",
        owner_repo,
        profile_name,
        apply_flag,
        also_labels,
        also_protection,
    )

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

    labels_diff = None
    if also_labels:
        labels_path = resolve_default_labels_path()
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
            log.warning(
                "branch protection not configured on %s@main; treating as empty",
                owner_repo,
            )
            current_protection = {}
        protection_diff = protection_sync.compute_protection_diff(
            current_protection, policy, profile, "main"
        )

    # Print combined diff
    click.echo(format_files_diff(files_diff))
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
            f"Protection downgrade detected during `apply --also-protection`. "
            f"`apply` does not force-downgrade protection. Run "
            f"`gh manage protection sync {owner_repo} --profile "
            f"{profile_name} --downgrade-allowed --apply --yes` "
            f"explicitly to override, then re-run `apply`."
        )

    # Apply
    click.echo("")
    profile_sync.apply_files_diff(
        files_diff, target, templates_root, force=force, progress=click.echo
    )
    if labels_diff is not None:
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

    click.echo(
        f"\nApplied {n_file_changes} file changes"
        + (f" + {n_label_changes} label changes" if also_labels else "")
        + "."
    )

    log.info(
        "apply complete: repo=%s file_changes=%d label_changes=%d protection_changes=%d",
        owner_repo,
        n_file_changes,
        n_label_changes,
        n_protection_changes,
    )

    # Post-apply doctor warnings (spec §5 enforcement scope).
    # apply NEVER blocks on doctor FINDINGS; critical/high go to stderr
    # for visibility. But apply DOES propagate doctor *setup* errors
    # (missing profile, bad repos.yml, unreachable protection API) —
    # those are user-actionable and should surface via handle_errors,
    # not be silently swallowed as a warning.
    from gh_manage import doctor as _doctor
    from gh_manage.doctor import report as _doctor_report
    from gh_manage.doctor.errors import DoctorCheckError

    try:
        findings = _doctor.run_on_path(target, profile_name=profile_name)
    except DoctorCheckError as exc:
        # Per-check failure (malformed ci.yml etc.) is a warning only.
        log.warning("post-apply doctor check failed: %s", exc)
        click.echo(f"WARNING: post-apply doctor check failed: {exc}", err=True)
        findings = ()
    # DoctorError / GhError / GitError / ConfigError propagate to
    # handle_errors and surface as ClickException — intentional.

    blocking = tuple(f for f in findings if f.severity in ("critical", "high"))
    if blocking:
        click.echo("", err=True)
        click.echo(
            "WARNING: post-apply doctor surfaced blocking-severity findings:",
            err=True,
        )
        click.echo(
            _doctor_report.format_stdout(blocking, repo=owner_repo),
            err=True,
        )
        click.echo(
            "Not failing apply — run `gh-manage doctor` to review.",
            err=True,
        )
