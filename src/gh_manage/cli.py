"""Entry point for the gh-manage CLI.

Phase 0 provides only a --version stub. Full command wiring lands in Phase 4.
"""

from __future__ import annotations

import click

from gh_manage import __version__


@click.group(help="gh-manage — GitHub-based CI/CD, Issue management, and operations.")
@click.version_option(version=__version__, prog_name="gh-manage")
def main() -> None:
    """Root command group. Subcommands are added in later phases."""


if __name__ == "__main__":
    main()
