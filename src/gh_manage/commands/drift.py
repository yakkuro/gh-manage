"""`gh manage drift` — drift scanner CLI.

Phase 8 ships the MVP: single-repo scan comparing labels, branch
protection, and profile files against the profile + policies. Reports
findings in stdout, json, or markdown-file mode. Always exit 0 on
successful scan (drift is reported, not an error).

Architecture:
  commands/drift.py (this file) — CLI input + glue
    → drift_sync.run_all_checks (engine)
    → drift_sync.format_*_report (formatters)
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage import drift_sync, git_cli
from gh_manage.config import (
    ConfigError,
    ConfigFileNotFoundError,
    load_config,
)
from gh_manage.drift_sync import (
    DriftError,
    DriftOutputError,
    ScanContext,
)
from gh_manage.git_cli import GitError
from gh_manage.github_api import repo_info
from gh_manage.github_client import GhError
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.labels import LabelsConfig
from gh_manage.models.profiles import ProfileSpec
from gh_manage.profile_sync import ProfileError
from gh_manage.protection_sync import ProtectionError

_F = TypeVar("_F", bound=Callable[..., Any])


def _handle_errors(func: _F) -> _F:
    """Decorator: catch GhError / ConfigError / GitError / ProfileError /
    ProtectionError / DriftError and re-raise as click.ClickException
    (exit 1 with `Error: <msg>`)."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (
            GhError,
            ConfigError,
            GitError,
            ProfileError,
            ProtectionError,
            DriftError,
        ) as e:
            raise click.ClickException(str(e)) from e

    return wrapper  # type: ignore[return-value]


_VALID_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _resolve_profile_path(name: str) -> Path:
    """Resolve a profile name to a bundled YAML path with path-traversal
    defense. Mirrors commands/init.py's helper."""
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
            f"{name!r} → {candidate}."
        )
    if not candidate.is_file():
        raise ConfigFileNotFoundError(
            f"Profile not found: {name!r}. Looked in {profiles_root}."
        )
    return candidate


def _resolve_default_labels_path() -> Path:
    return Path(str(files("gh_manage.data") / "labels.yml"))


def _resolve_branch_protection_path() -> Path:
    return Path(str(files("gh_manage.data") / "branch-protection.yml"))


def _resolve_repos_path() -> Path:
    """Resolve the bundled repos.yml path."""
    return Path(str(files("gh_manage.data") / "repos.yml"))


def _scan_single_repo(
    owner_repo: str,
    profile_name: str,
    severity: str,
    report_mode: str,
    output: Path | None,
    skip_profile_check: bool = False,
) -> str:
    """Scan a single repo and return the result/status string.

    Args:
        owner_repo: Repository in "owner/repo" format.
        profile_name: Profile name to use.
        severity: Minimum severity to report.
        report_mode: Output mode (stdout, json, markdown-file, issue).
        output: Output file path (for markdown-file mode).
        skip_profile_check: If True, don't check profile files locally
            (used in --all mode with no local clone).

    Returns:
        Status/result string for the repo.
    """
    # Get default branch
    default_branch = repo_info.get_default_branch(owner_repo)

    # Load profile and configs
    profile = load_config(_resolve_profile_path(profile_name), ProfileSpec)
    labels_config = load_config(_resolve_default_labels_path(), LabelsConfig)

    bp_config: BranchProtectionConfig | None = None
    if profile.protection_policy is not None:
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

    # In --all mode, use a dummy empty path (skip_profile_check=True)
    # In normal mode, use the actual path
    if skip_profile_check:
        import tempfile

        scan_path = (
            Path(tempfile.gettempdir())
            / f"gh-manage-scan-{owner_repo.replace('/', '-')}"
        )
        scan_path.mkdir(exist_ok=True)
    else:
        scan_path = Path.cwd().resolve()

    ctx = ScanContext(
        path=scan_path,
        repo=owner_repo,
        default_branch=default_branch,
        profile=profile,
        labels_config=labels_config,
        bp_config=bp_config,
    )

    all_findings = drift_sync.run_all_checks(ctx)
    filtered = drift_sync._filter_by_severity(all_findings, severity)  # type: ignore[arg-type]

    match report_mode:
        case "stdout":
            rendered = drift_sync.format_stdout_report(filtered)
            return rendered
        case "json":
            rendered = drift_sync.format_json_report(filtered)
            return rendered
        case "markdown-file":
            rendered = drift_sync.format_markdown_report(filtered)
            if output is not None:
                try:
                    output.write_text(rendered, encoding="utf-8")
                except OSError as e:
                    raise DriftOutputError(
                        f"Cannot write drift report to {output}: {e}. "
                        f"Check disk space, write permissions, and that the parent "
                        f"directory exists."
                    ) from e
            return f"Report written to {output}"
        case "issue":
            from datetime import datetime, timezone

            status = drift_sync.resolve_drift_issue(
                filtered,
                owner_repo,
                datetime.now(timezone.utc).isoformat(),
            )
            return status
        case _:
            raise ValueError(f"Unknown report mode: {report_mode!r}")


def _scan_all_repos(
    severity: str,
    report_mode: str,
    output: Path | None,
) -> None:
    """Scan all enabled repos from repos.yml.

    Prints a structured summary to stderr with scan counts and results.
    """
    from gh_manage.models.repos import ReposConfig

    repos_path = _resolve_repos_path()
    config = load_config(repos_path, ReposConfig)

    results = []
    skipped = 0
    failed = 0

    for entry in config.repos:
        if not entry.enabled:
            results.append(f"  {entry.name}: SKIPPED (disabled)")
            skipped += 1
            continue

        try:
            result_str = _scan_single_repo(
                entry.name,
                entry.profile,
                severity,
                report_mode,
                output,
                skip_profile_check=True,
            )
            # For stdout/json/markdown mode, print the result
            if report_mode in ("stdout", "json", "markdown-file"):
                click.echo(result_str)
            results.append(f"  {entry.name}: OK")
        except (
            GhError,
            ConfigError,
            GitError,
            ProfileError,
            ProtectionError,
            DriftError,
        ) as e:
            results.append(f"  {entry.name}: FAILED ({e})")
            failed += 1

    # Print summary to stderr
    scanned = len(config.repos) - skipped
    click.echo(
        f"\n--- Scan Summary ---\nScanned: {scanned}, Skipped: {skipped}, Failed: {failed}",
        err=True,
    )
    for result in results:
        click.echo(result, err=True)


@click.command(
    "drift",
    help=(
        "Scan a repo for config drift vs profile + policies. "
        "Always exits 0 on successful scan regardless of findings."
    ),
)
@click.argument(
    "path",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    required=False,
)
@click.option(
    "--profile",
    "profile_name",
    default=None,
    help="Profile name (resolves to bundled profiles/<name>.yml).",
)
@click.option(
    "--all",
    "scan_all",
    is_flag=True,
    help="Scan all enabled repos from repos.yml instead of a single path.",
)
@click.option(
    "--severity",
    type=click.Choice(["critical", "high", "medium", "low"]),
    default="low",
    help="Minimum severity to report (default: low = show everything).",
)
@click.option(
    "--report-mode",
    type=click.Choice(["stdout", "json", "markdown-file", "issue"]),
    default="stdout",
    help="Report format. Destination is --output (defaults to stdout).",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the report to this file instead of stdout.",
)
@_handle_errors
def drift(
    path: Path | None,
    profile_name: str | None,
    scan_all: bool,
    severity: str,
    report_mode: str,
    output: Path | None,
) -> None:
    """Scan for drift against the named profile."""
    # Validation: --all XOR (path + profile)
    if scan_all:
        if path is not None or profile_name is not None:
            raise click.UsageError(
                "--all and path/--profile are mutually exclusive. "
                "Use either '--all' (scans all repos) or 'path --profile' (single repo)."
            )
        _scan_all_repos(severity, report_mode, output)
        return

    # Single-repo mode
    if path is None or profile_name is None:
        raise click.UsageError(
            "--profile is required when not using --all. "
            "Provide both 'path' and '--profile', or use '--all' to scan all repos."
        )

    # Check that path exists
    target = path.resolve()
    if not target.exists():
        raise click.UsageError(f"Path does not exist: {target}")

    owner_repo = git_cli.get_origin_owner_repo(target)
    result = _scan_single_repo(
        owner_repo,
        profile_name,
        severity,
        report_mode,
        output,
        skip_profile_check=False,
    )

    # For issue mode, result is already printed by resolve_drift_issue
    # For other modes, we need to print or write the result
    if report_mode == "issue":
        click.echo(result)
    elif report_mode == "markdown-file":
        click.echo(result)
    else:
        click.echo(result)
