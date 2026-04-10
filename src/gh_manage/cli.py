"""Top-level click group for gh-manage."""

from __future__ import annotations

import click

from gh_manage import __version__
from gh_manage.commands import (
    apply as apply_cmd,
    drift as drift_cmd,
    init as init_cmd,
    issues as issues_cmd,
    labels as labels_cmd,
    protection as protection_cmd,
)


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    help=(
        "gh-manage — GitHub-based CI/CD, Issue management, and operations "
        "for yakkuro/* repositories."
    ),
)
@click.version_option(version=__version__, prog_name="gh-manage")
def main() -> None:
    """Root command group. Subcommands are registered below."""


main.add_command(init_cmd.init)
main.add_command(apply_cmd.apply)
main.add_command(labels_cmd.labels)
main.add_command(protection_cmd.protection)
main.add_command(drift_cmd.drift)
main.add_command(issues_cmd.issues)


if __name__ == "__main__":
    main()
