"""Smoke tests for gh-manage CLI entry: --version, --help, and stub subcommands."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from gh_manage import __version__
from gh_manage.cli import main


def test_version_flag_outputs_semver() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
    assert "gh-manage" in result.output


def test_help_flag_lists_all_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for sub in ("init", "apply", "labels", "protection", "drift", "issues"):
        assert sub in result.output


def test_short_help_flag_works() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["-h"])
    assert result.exit_code == 0
    assert "Usage:" in result.output


@pytest.mark.parametrize(
    "subcommand",
    ["init", "apply", "labels", "protection", "drift", "issues"],
)
def test_stub_subcommand_exits_nonzero(subcommand: str) -> None:
    runner = CliRunner()
    result = runner.invoke(main, [subcommand])
    assert result.exit_code == 1
    assert "not yet implemented" in result.output


def test_unknown_subcommand_exits_with_click_usage_error() -> None:
    """Unknown subcommands should get click's standard usage error (exit code 2)."""
    runner = CliRunner()
    result = runner.invoke(main, ["totally-not-a-command"])
    assert result.exit_code == 2
    assert "No such command" in result.output or "Usage:" in result.output


@pytest.mark.parametrize(
    "subcommand",
    ["init", "apply", "labels", "protection", "drift", "issues"],
)
def test_stub_subcommand_help_shows_help_without_firing_stub(subcommand: str) -> None:
    """`gh manage <stub> --help` must display the subcommand's help text
    (exit 0) instead of firing the "not yet implemented" stub error (exit 1).
    click dispatches --help before invoking the command callback, so the
    stub's `sys.exit(1)` must NOT run."""
    runner = CliRunner()
    result = runner.invoke(main, [subcommand, "--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    # The stub callback must not have run — its error message starts with "error:".
    assert "error:" not in result.output
