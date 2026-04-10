"""`gh manage init` — initialize a new repo with a gh-manage profile.

Scheduled for cli/v0.3.0 (Phase 6).
"""

from __future__ import annotations

import sys

import click


@click.command(
    help="Initialize a new repo with a gh-manage profile (not yet implemented)."
)
def init() -> None:
    click.echo(
        "error: `gh manage init` is not yet implemented — "
        "scheduled for cli/v0.3.0 (Phase 6).",
        err=True,
    )
    sys.exit(1)
