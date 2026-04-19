"""Top-level click group for gh-manage."""

from __future__ import annotations

import click

from gh_manage import __version__
from gh_manage.commands import (
    apply as apply_cmd,
    doctor as doctor_cmd,
    drift as drift_cmd,
    init as init_cmd,
    issues as issues_cmd,
    labels as labels_cmd,
    protection as protection_cmd,
)
from gh_manage.logging_config import LogLevel, configure_logging


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    help=(
        "gh-manage — GitHub-based CI/CD, Issue management, and operations "
        "for yakkuro/* repositories."
    ),
)
@click.version_option(version=__version__, prog_name="gh-manage")
@click.option(
    "--log-level",
    type=click.Choice(["debug", "info", "warning", "error"], case_sensitive=False),
    envvar="GH_MANAGE_LOG_LEVEL",
    default="warning",
    show_default=True,
    help=(
        "Logging verbosity for gh_manage modules. Also honours "
        "GH_MANAGE_LOG_LEVEL. For JSON output, set GH_MANAGE_LOG_JSON=1."
    ),
)
def main(log_level: str) -> None:
    """Root command group. Subcommands are registered below."""
    level: LogLevel = log_level.lower()  # type: ignore[assignment]
    configure_logging(level=level)


main.add_command(init_cmd.init)
main.add_command(apply_cmd.apply)
main.add_command(doctor_cmd.doctor_cmd)
main.add_command(labels_cmd.labels)
main.add_command(protection_cmd.protection)
main.add_command(drift_cmd.drift)
main.add_command(issues_cmd.issues)


if __name__ == "__main__":
    main()
