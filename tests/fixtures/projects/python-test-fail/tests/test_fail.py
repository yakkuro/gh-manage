"""Intentionally failing tests to verify gh-manage reusable detects test failures."""

from __future__ import annotations

from python_test_fail import add


def test_intentional_failure() -> None:
    result = add(1, 1)
    assert (
        result == 3
    ), "Intentional failure: 1 + 1 is not 3, verifying test-fail fixture fails"
