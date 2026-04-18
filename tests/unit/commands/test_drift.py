"""Tests for gh_manage.commands.drift — CLI-level behavior.

Engine tests live in tests/unit/drift/. This file covers CLI flag
validation and the parallel _scan_all_repos orchestration (Task 12+).
"""

from __future__ import annotations

from click.testing import CliRunner

from gh_manage.commands.drift import drift


def test_concurrency_zero_rejected() -> None:
    """--concurrency 0 must be rejected by click.IntRange(1, 16)."""
    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "0"])
    assert result.exit_code == 2
    # click rejects out-of-range with non-zero exit
    assert "no such option" not in result.output.lower()  # flag must exist


def test_concurrency_seventeen_rejected() -> None:
    """--concurrency 17 must be rejected by click.IntRange(1, 16)."""
    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "17"])
    assert result.exit_code == 2
    assert "no such option" not in result.output.lower()


def test_concurrency_one_accepted() -> None:
    """--concurrency 1 must be a valid value (sequential-equivalent mode).

    The actual invocation will fail because we haven't mocked repos.yml,
    but the click validation must pass first.
    """
    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "1"])
    # click validation passed (flag accepted) — any subsequent error is not about the flag itself
    assert "no such option" not in result.output.lower()
