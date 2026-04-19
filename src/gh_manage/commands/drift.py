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

import logging
from pathlib import Path

import click

from gh_manage import drift_sync, git_cli
from gh_manage.commands._shared import (
    handle_errors,
    resolve_branch_protection_path,
    resolve_default_labels_path,
    resolve_profile_path,
    resolve_repos_path,
)
from gh_manage.config import (
    ConfigError,
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

log = logging.getLogger(__name__)


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
    log.info("scanning %s (profile=%s)", owner_repo, profile_name)
    # Get default branch
    default_branch = repo_info.get_default_branch(owner_repo)

    # Load profile and configs
    profile = load_config(resolve_profile_path(profile_name), ProfileSpec)
    labels_config = load_config(resolve_default_labels_path(), LabelsConfig)

    bp_config: BranchProtectionConfig | None = None
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
    log.info("scan complete for %s: %d findings", owner_repo, len(all_findings))
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
    concurrency: int = 4,
) -> None:
    """Scan all enabled repos from repos.yml in parallel.

    Threading discipline (spec §2): workers are pure functions that
    return (name, status_label, payload_or_exc). Only the main thread
    emits to stdout/stderr — no print locks needed, line-atomic output
    is guaranteed.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from gh_manage.models.repos import RepoEntry, ReposConfig

    repos_path = resolve_repos_path()
    config = load_config(repos_path, ReposConfig)

    # Partition repos: enabled vs disabled
    enabled_entries = [e for e in config.repos if e.enabled]
    disabled_entries = [e for e in config.repos if not e.enabled]

    per_repo_results: dict[
        str, str
    ] = {}  # name -> "OK" | "SKIPPED (...)" | "FAILED (...)"

    for e in disabled_entries:
        per_repo_results[e.name] = f"  {e.name}: SKIPPED (disabled)"

    def _worker(entry: RepoEntry) -> tuple[str, str, str | Exception]:
        """Scan one repo. Returns (name, status, payload_or_exc).

        The broad `except Exception` fallback is intentional for parallel
        isolation (spec §2): one repo's failure — even from an unexpected
        exception type like OSError on tempdir creation — must NOT abort
        the whole --all run. Domain exceptions are caught first for
        specific error messages; anything else is caught and materialized
        as FAILED so `future.result()` never raises.
        """
        try:
            result_str = _scan_single_repo(
                entry.name,
                entry.profile,
                severity,
                report_mode,
                output,
                skip_profile_check=True,
            )
            return (entry.name, "OK", result_str)
        except (
            GhError,
            ConfigError,
            GitError,
            ProfileError,
            ProtectionError,
            DriftError,
        ) as e:
            return (entry.name, "FAILED", e)
        except Exception as e:  # noqa: BLE001 — parallel isolation, spec §2
            log.exception(
                "unexpected error scanning %s (%s: %s)",
                entry.name,
                type(e).__name__,
                e,
            )
            return (entry.name, "FAILED", e)

    if enabled_entries and concurrency > 1:
        click.echo(
            f"[drift --all] {len(enabled_entries)} repos, concurrency={concurrency}",
            err=True,
        )

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        future_to_entry = {pool.submit(_worker, e): e for e in enabled_entries}
        completed = 0
        for future in as_completed(future_to_entry):
            name, status, payload = future.result()
            completed += 1
            if status == "OK":
                if report_mode in ("stdout", "json", "markdown-file"):
                    click.echo(payload)
                per_repo_results[name] = f"  {name}: OK"
            else:  # FAILED
                per_repo_results[name] = f"  {name}: FAILED ({payload})"
            if concurrency > 1:
                click.echo(
                    f"[drift --all] {completed}/{len(enabled_entries)} scanned",
                    err=True,
                )

    scanned = len(enabled_entries)
    skipped = len(disabled_entries)
    failed = sum(1 for v in per_repo_results.values() if "FAILED" in v)
    click.echo(
        f"\n--- Scan Summary ---\nScanned: {scanned}, Skipped: {skipped}, Failed: {failed}",
        err=True,
    )
    # Print per-repo results in repos.yml order (deterministic)
    for entry in config.repos:
        click.echo(per_repo_results[entry.name], err=True)


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
    "--concurrency",
    type=click.IntRange(1, 16),
    default=4,
    show_default=True,
    help="Parallel worker count for --all mode. Values outside [1,16] are rejected. "
    "Only meaningful with --all; ignored otherwise. "
    "--concurrency 8+ may interact with GitHub secondary rate-limit.",
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
@handle_errors
def drift(
    path: Path | None,
    profile_name: str | None,
    scan_all: bool,
    concurrency: int,
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
        _scan_all_repos(severity, report_mode, output, concurrency=concurrency)
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
