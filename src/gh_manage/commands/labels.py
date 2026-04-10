"""`gh manage labels` — label synchronization.

Scheduled for cli/v0.2.0 (Phase 5).
"""

from __future__ import annotations

import sys

import click


@click.command(
    help="Synchronize GitHub repo labels against config/labels.yml (not yet implemented)."
)
def labels() -> None:
    click.echo(
        "error: `gh manage labels` is not yet implemented — "
        "scheduled for cli/v0.2.0 (Phase 5).",
        err=True,
    )
    sys.exit(1)
