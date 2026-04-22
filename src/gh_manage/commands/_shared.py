"""Shared CLI helpers for gh-manage commands.

Extracted from commands/init.py, apply.py, drift.py, protection.py to
eliminate security-critical code duplication (Issue #38). The path
traversal defense in resolve_profile_path is load-bearing — having it
in one place ensures a security fix is applied once, not in 4 files.

This module is internal to the commands package (leading underscore).
"""

from __future__ import annotations

import functools
import logging
import re
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage import doctor
from gh_manage.config import ConfigError, ConfigFileNotFoundError
from gh_manage.doctor.errors import DoctorError
from gh_manage.doctor.report import format_stdout as _doctor_format_stdout
from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings
from gh_manage.findings import Finding, Severity
from gh_manage.drift_sync import DriftError
from gh_manage.git_cli import GitError
from gh_manage.github_client import GhError
from gh_manage.profile_sync import ProfileError, ProfileFilesDiff
from gh_manage.protection_sync import ProtectionError

log = logging.getLogger(__name__)

_F = TypeVar("_F", bound=Callable[..., Any])

VALID_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_DOMAIN_ERRORS = (
    GhError,
    ConfigError,
    GitError,
    ProfileError,
    ProtectionError,
    DriftError,
    DoctorError,
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


def _resolve_self_referencing(owner_repo: str) -> bool:
    """Look up `owner_repo` in bundled repos.yml; return its self_referencing
    flag if found, False otherwise.

    Used by the single-repo drift CLI path (where there's no RepoEntry in
    scope) to flow the flag into ScanContext. The --all path bypasses
    this helper because _scan_worker has the RepoEntry directly.

    Failures (missing repos.yml, parse error) are logged and return False
    rather than propagating — the drift scan should not abort because of
    this lookup. An unregistered repo is also a False (no entry, ad-hoc
    scan).
    """
    from gh_manage.config import ConfigError, load_config
    from gh_manage.models.repos import ReposConfig

    try:
        config = load_config(resolve_repos_path(), ReposConfig)
    except (ConfigError, OSError) as e:
        log.warning(
            "could not load repos.yml for self_referencing lookup of %s: %s; "
            "treating as self_referencing=False",
            owner_repo,
            e,
        )
        return False

    for entry in config.repos:
        if entry.name == owner_repo:
            return entry.self_referencing
    return False


def run_pre_apply_doctor(
    target: Path,
    profile_name: str,
    scope: ApplyScope,
    allow_blocking: bool,
) -> None:
    """Block the caller if pre-apply doctor finds unresolved blocking findings.

    Raises `click.ClickException` on block. Returns None on pass. Emits
    a loud stderr warning when `allow_blocking=True` bypasses a block.

    Exception handling:
    - Per-check exceptions (CiYmlParseError, DoctorCheckError) are
      caught INSIDE `doctor.registry.run_checks` and converted to
      synthetic LOW findings (see spec §3.1.1). No handling needed
      here.
    - Setup errors (DoctorError subclasses raised from run_on_path
      itself — profile missing, repos.yml corrupt, git_cli failure,
      GitHub API error before any check runs) propagate.
    """
    blocking_severities: tuple[Severity, ...] = ("critical", "high")

    findings = doctor.run_on_path(target, profile_name=profile_name)
    filtered = filter_pre_apply_findings(findings, scope)
    blocking = tuple(f for f in filtered if f.severity in blocking_severities)

    log.info(
        "pre-apply doctor: findings=%d filtered=%d blocking=%d allow_blocking=%s",
        len(findings),
        len(findings) - len(filtered),
        len(blocking),
        allow_blocking,
    )

    if not blocking:
        return

    if allow_blocking:
        click.echo(
            f"WARNING: --allow-blocking: proceeding despite "
            f"{len(blocking)} blocking finding(s).",
            err=True,
        )
        return

    raise click.ClickException(_format_blocking_message(blocking, target, profile_name))


def _format_blocking_message(
    blocking: tuple[Finding, ...],
    target: Path,
    profile_name: str,
) -> str:
    """Compose the user-facing pre-apply block message.

    The `doctor` subcommand in the suggested recovery command MUST
    carry `--profile` explicitly. `doctor` falls back to inferring the
    profile from `repos.yml` when the flag is omitted, which fails on
    fresh / unregistered repos and picks the wrong profile when the
    caller intentionally passed a different one.
    """
    repo_label = str(target)
    prefix = (
        "Pre-apply doctor found blocking-severity finding(s) that this "
        "invocation will not resolve:\n"
    )
    body = _doctor_format_stdout(blocking, repo=repo_label)
    suffix = (
        "\n"
        "To proceed anyway (not recommended), re-run with --allow-blocking.\n"
        "To see all findings (including non-blocking), run:\n"
        f"    gh-manage doctor {target} --profile {profile_name}"
    )
    return prefix + "\n" + body + "\n" + suffix
