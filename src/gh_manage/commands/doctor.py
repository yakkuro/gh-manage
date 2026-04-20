"""`gh-manage doctor` — consumer-shape guardrail CLI (spec §2)."""

from __future__ import annotations

import logging
from pathlib import Path

import click

from gh_manage import doctor as doctor_pkg
from gh_manage.commands._shared import handle_errors
from gh_manage.doctor import report as doctor_report
from gh_manage.findings import Finding, Severity

log = logging.getLogger(__name__)

_REPORT_MODES = ("stdout", "json", "markdown-file")
_BLOCKING_SEVERITIES: tuple[Severity, ...] = ("critical", "high")
_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _looks_like_owner_repo(target: str) -> bool:
    if "/" not in target:
        return False
    if target.startswith((".", "/")):
        return False
    if Path(target).exists():
        return False
    return True


def _filter_severity(
    findings: tuple[Finding, ...], min_severity: Severity | None
) -> tuple[Finding, ...]:
    if min_severity is None:
        return findings
    threshold = _SEVERITY_RANK[min_severity]
    return tuple(f for f in findings if _SEVERITY_RANK[f.severity] >= threshold)


def _derive_repo_label(path: Path, *, fallback: str) -> str:
    from gh_manage import git_cli

    try:
        return git_cli.get_origin_owner_repo(path)
    except Exception as e:
        log.warning("could not derive owner/repo from path %s: %s", path, e)
        return fallback


@click.command(
    "doctor",
    help="Check a repo's ci.yml / branch protection shape against a profile.",
)
@click.argument("target", type=str)
@click.option("--profile", "profile_name", default=None)
@click.option("--check", "check_names", multiple=True)
@click.option(
    "--severity",
    type=click.Choice(["critical", "high", "medium", "low"]),
    default=None,
)
@click.option(
    "--report-mode",
    type=click.Choice(_REPORT_MODES),
    default="stdout",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
)
@click.option("--exit-zero", is_flag=True)
@handle_errors
def doctor_cmd(
    target: str,
    profile_name: str | None,
    check_names: tuple[str, ...],
    severity: Severity | None,
    report_mode: str,
    output: Path | None,
    exit_zero: bool,
) -> None:
    log.info(
        "doctor invoked: target=%s profile=%s report_mode=%s",
        target,
        profile_name,
        report_mode,
    )

    if _looks_like_owner_repo(target):
        findings = doctor_pkg.run_on_remote(target, profile_name)
        repo = target
    else:
        path = Path(target).resolve()
        findings = doctor_pkg.run_on_path(path, profile_name)
        repo = _derive_repo_label(path, fallback=str(path))

    if check_names:
        findings = tuple(f for f in findings if f.check in set(check_names))

    findings = _filter_severity(findings, severity)

    if report_mode == "stdout":
        click.echo(doctor_report.format_stdout(findings, repo=repo))
    elif report_mode == "json":
        click.echo(doctor_report.format_json(findings, repo=repo))
    elif report_mode == "markdown-file":
        if output is None:
            raise click.UsageError(
                "--output is required with --report-mode markdown-file"
            )
        output.write_text(
            doctor_report.format_markdown(findings, repo=repo),
            encoding="utf-8",
        )

    blocking_count = sum(1 for f in findings if f.severity in _BLOCKING_SEVERITIES)
    log.info(
        "doctor complete: target=%s findings=%d blocking=%d",
        target,
        len(findings),
        blocking_count,
    )

    if exit_zero:
        return

    if any(f.severity in _BLOCKING_SEVERITIES for f in findings):
        raise SystemExit(1)
