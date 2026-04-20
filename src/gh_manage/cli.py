"""Top-level click group for gh-manage."""

from __future__ import annotations

from pathlib import Path

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


def _validate_log_file(path: Path) -> None:
    """Raise UsageError if the log file cannot be written to.

    Runs at CLI startup, before any subcommand. Rejects missing parent
    directory and write-permission failures with actionable messages.
    Creating the file (0-byte touch via append-open) is intentional —
    users who pass --log-file have opted into file creation.
    """
    parent = path.parent.resolve()
    if not parent.is_dir():
        raise click.UsageError(
            f"--log-file parent directory does not exist: {parent}. "
            f"Create it or choose a different path."
        )
    try:
        with path.open("a", encoding="utf-8"):
            pass
    except OSError as e:
        raise click.UsageError(
            f"Cannot write to --log-file {path}: {e}. Check permissions and disk space."
        ) from e


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
@click.option(
    "--log-file",
    type=click.Path(dir_okay=False, path_type=Path),
    envvar="GH_MANAGE_LOG_FILE",
    default=None,
    help=(
        "Write logs to this file in addition to stderr. Also honours "
        "GH_MANAGE_LOG_FILE. Parent directory must exist and be writable; "
        "otherwise the command exits with a usage error."
    ),
)
def main(log_level: str, log_file: Path | None) -> None:
    """Root command group. Subcommands are registered below."""
    level: LogLevel = log_level.lower()  # type: ignore[assignment]
    if log_file is not None:
        _validate_log_file(log_file)
    configure_logging(level=level, log_file=log_file)


main.add_command(init_cmd.init)
main.add_command(apply_cmd.apply)
main.add_command(doctor_cmd.doctor_cmd)
main.add_command(labels_cmd.labels)
main.add_command(protection_cmd.protection)
main.add_command(drift_cmd.drift)
main.add_command(issues_cmd.issues)


if __name__ == "__main__":
    main()
