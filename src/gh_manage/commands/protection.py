"""`gh manage protection` — branch protection synchronization.

Scheduled for cli/v0.4.0 (Phase 7).
"""

from __future__ import annotations

import sys

import click


@click.command(help="Synchronize branch protection (not yet implemented).")
def protection() -> None:
    click.echo(
        "error: `gh manage protection` is not yet implemented — "
        "scheduled for cli/v0.4.0 (Phase 7).",
        err=True,
    )
    sys.exit(1)
