"""`gh manage issues` — cross-repo issue listing.

Scheduled for cli/v0.5.0 (Phase 8).
"""

from __future__ import annotations

import sys

import click


@click.command(help="Cross-repo issue listing (not yet implemented).")
def issues() -> None:
    click.echo(
        "error: `gh manage issues` is not yet implemented — "
        "scheduled for cli/v0.5.0 (Phase 8).",
        err=True,
    )
    sys.exit(1)
