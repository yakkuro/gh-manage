"""`gh manage drift` — config drift scanner.

Scheduled for cli/v0.5.0 (Phase 8).
"""

from __future__ import annotations

import sys

import click


@click.command(help="Scan repos for config drift (not yet implemented).")
def drift() -> None:
    click.echo(
        "error: `gh manage drift` is not yet implemented — "
        "scheduled for cli/v0.5.0 (Phase 8).",
        err=True,
    )
    sys.exit(1)
