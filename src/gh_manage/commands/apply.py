"""`gh manage apply` — apply a gh-manage profile to existing repos.

Scheduled for cli/v0.3.0 (Phase 6).
"""

from __future__ import annotations

import sys

import click


@click.command(help="Apply gh-manage profiles to existing repos (not yet implemented).")
def apply() -> None:
    click.echo(
        "error: `gh manage apply` is not yet implemented — "
        "scheduled for cli/v0.3.0 (Phase 6).",
        err=True,
    )
    sys.exit(1)
