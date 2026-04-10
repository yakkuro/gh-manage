"""Tests for python_lint_fail. These pass — lint-fail only fails at ruff check."""

from __future__ import annotations

from python_lint_fail import add


def test_add_works() -> None:
    assert add(2, 3) == 5
