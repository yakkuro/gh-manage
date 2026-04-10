"""Smoke tests for gh-manage CLI entry: --version, --help, and stub subcommands.

Tests use `prog_name="gh-manage"` when invoking the root group to match the
real runtime contract (set by `src/gh_manage/__main__.py`). Without this,
click would derive prog_name from `sys.argv[0]` at test time (`pytest`), and
the assertions on `Usage: gh-manage ...` would fail.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from gh_manage import __version__
from gh_manage.cli import main

# Exact stub error messages keyed by subcommand. Kept in lockstep with
# src/gh_manage/commands/*.py. If this map drifts from the real stubs, the
# test fails — which is the point.
STUB_ERROR_MESSAGES: dict[str, str] = {
    "init": (
        "error: `gh manage init` is not yet implemented — "
        "scheduled for cli/v0.3.0 (Phase 6)."
    ),
    "apply": (
        "error: `gh manage apply` is not yet implemented — "
        "scheduled for cli/v0.3.0 (Phase 6)."
    ),
    "labels": (
        "error: `gh manage labels` is not yet implemented — "
        "scheduled for cli/v0.2.0 (Phase 5)."
    ),
    "protection": (
        "error: `gh manage protection` is not yet implemented — "
        "scheduled for cli/v0.4.0 (Phase 7)."
    ),
    "drift": (
        "error: `gh manage drift` is not yet implemented — "
        "scheduled for cli/v0.5.0 (Phase 8)."
    ),
    "issues": (
        "error: `gh manage issues` is not yet implemented — "
        "scheduled for cli/v0.5.0 (Phase 8)."
    ),
}


def test_version_flag_outputs_exact_semver() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"], prog_name="gh-manage")
    assert result.exit_code == 0
    assert result.output.strip() == f"gh-manage, version {__version__}"


def test_help_flag_shows_exact_prog_name_and_lists_all_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"], prog_name="gh-manage")
    assert result.exit_code == 0
    # Exact prog_name in the Usage line — catches prog_name drift.
    assert result.output.startswith("Usage: gh-manage [OPTIONS] COMMAND [ARGS]...")
    for sub in ("init", "apply", "labels", "protection", "drift", "issues"):
        assert sub in result.output


def test_short_help_flag_shows_exact_prog_name() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["-h"], prog_name="gh-manage")
    assert result.exit_code == 0
    assert result.output.startswith("Usage: gh-manage [OPTIONS] COMMAND [ARGS]...")


@pytest.mark.parametrize(
    "subcommand",
    ["init", "apply", "labels", "protection", "drift", "issues"],
)
def test_stub_subcommand_exits_with_exact_phase_message(subcommand: str) -> None:
    """Each stub must print the EXACT error message from STUB_ERROR_MESSAGES.
    This guards against phase-to-command drift across cli.py, the stub files,
    CHANGELOG-cli.md, and docs/usage/cli.md."""
    runner = CliRunner()
    result = runner.invoke(main, [subcommand], prog_name="gh-manage")
    assert result.exit_code == 1
    assert STUB_ERROR_MESSAGES[subcommand] in result.output


def test_unknown_subcommand_exits_with_click_usage_error() -> None:
    """Unknown subcommands should get click's standard usage error (exit code 2)."""
    runner = CliRunner()
    result = runner.invoke(main, ["totally-not-a-command"], prog_name="gh-manage")
    assert result.exit_code == 2
    assert "No such command 'totally-not-a-command'" in result.output
    # Usage line uses the gh-manage prog_name, not sys.argv[0].
    assert "Usage: gh-manage" in result.output


@pytest.mark.parametrize(
    "subcommand",
    ["init", "apply", "labels", "protection", "drift", "issues"],
)
def test_stub_subcommand_help_shows_help_without_firing_stub(subcommand: str) -> None:
    """`gh manage <stub> --help` must display the subcommand's help text
    (exit 0) instead of firing the "not yet implemented" stub error (exit 1).
    click dispatches --help before invoking the command callback, so the
    stub's `sys.exit(1)` must NOT run.

    Also verifies that prog_name propagates into subcommand usage lines."""
    runner = CliRunner()
    result = runner.invoke(main, [subcommand, "--help"], prog_name="gh-manage")
    assert result.exit_code == 0
    assert result.output.startswith(f"Usage: gh-manage {subcommand} [OPTIONS]")
    # The stub callback must not have run — its error message starts with "error:".
    assert "error:" not in result.output
