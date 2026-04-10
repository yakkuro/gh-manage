"""Negative fixture — intentionally contains unused imports (ruff F401)."""

import os  # noqa: F401 - intentional, will be removed below to produce F401
import sys  # intentional unused import to fail ruff check

# The fixture deliberately leaves sys unused to trigger F401.
# os has a noqa to isolate the failure to exactly one unused import.


def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b
