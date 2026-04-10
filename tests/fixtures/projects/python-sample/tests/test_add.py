"""Unit tests for python_sample.add."""

from __future__ import annotations

from python_sample import add


def test_add_positive() -> None:
    assert add(1, 2) == 3


def test_add_negative() -> None:
    assert add(-1, -1) == -2


def test_add_zero() -> None:
    assert add(0, 0) == 0
