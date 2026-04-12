"""Smoke tests for gh-manage CLI entry: --version, --help, and stub subcommands.

Tests use `prog_name="gh-manage"` when invoking the root group to match the
real runtime contract (set by `src/gh_manage/__main__.py`). Without this,
click would derive prog_name from `sys.argv[0]` at test time (`pytest`), and
the assertions on `Usage: gh-manage ...` would fail.

One test (`test_main_module_invokes_with_correct_prog_name`) invokes the
module via subprocess to exercise the real `__main__.py` code path. Without
this, a regression that removes `prog_name="gh-manage"` from `__main__.py`
would go undetected — the CliRunner tests inject prog_name independently.
"""

from __future__ import annotations

import subprocess
import sys

import pytest
from click.testing import CliRunner

from gh_manage import __version__
from gh_manage.cli import main

# Exact stub error messages keyed by subcommand. Kept in lockstep with
# src/gh_manage/commands/*.py. If this map drifts from the real stubs, the
# test fails — which is the point.
# Note: init (Phase 6), apply (Phase 6), protection (Phase 7), and drift
# (Phase 8) are now implemented, so they are removed from this map. The test
# below only runs for remaining stubs.
STUB_ERROR_MESSAGES: dict[str, str] = {
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
    ["issues"],
)
def test_stub_subcommand_exits_with_exact_phase_message(subcommand: str) -> None:
    """Each stub must print the EXACT error message from STUB_ERROR_MESSAGES.
    This guards against phase-to-command drift across cli.py, the stub files,
    CHANGELOG-cli.md, and docs/usage/cli.md. Uses exact equality (rstrip'd)
    so any additional output (e.g., a stub accidentally printing before its
    error) would be caught.

    Note: init (Phase 6) and apply (Phase 6) are now implemented and no longer
    stubs, so they are excluded from this test.
    """
    runner = CliRunner()
    result = runner.invoke(main, [subcommand], prog_name="gh-manage")
    assert result.exit_code == 1
    assert result.output.rstrip() == STUB_ERROR_MESSAGES[subcommand]


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
    ["drift", "issues"],
)
def test_stub_subcommand_help_shows_help_without_firing_stub(subcommand: str) -> None:
    """`gh manage <stub> --help` must display the subcommand's help text
    (exit 0) instead of firing the "not yet implemented" stub error (exit 1).
    click dispatches --help before invoking the command callback, so the
    stub's `sys.exit(1)` must NOT run.

    Also verifies that prog_name propagates into subcommand usage lines.

    Note: init (Phase 6) and apply (Phase 6) are now implemented and no longer
    stubs, so they are excluded from this test.
    """
    runner = CliRunner()
    result = runner.invoke(main, [subcommand, "--help"], prog_name="gh-manage")
    assert result.exit_code == 0
    assert result.output.startswith(f"Usage: gh-manage {subcommand} [OPTIONS]")
    # The stub callback must not have run — its error message starts with "error:".
    assert "error:" not in result.output


def test_main_module_invokes_with_correct_prog_name() -> None:
    """Regression test for Codex re-review LOW finding: verify __main__.py's
    prog_name propagates by invoking the module via a real subprocess. The
    CliRunner tests above inject prog_name="gh-manage" in runner.invoke(...),
    which bypasses __main__.py entirely — so if someone removes
    prog_name="gh-manage" from __main__.py, the other tests would still pass
    but the real CLI would show `Usage: python -m gh_manage ...` instead of
    `Usage: gh-manage ...`. This subprocess call exercises the real code path.
    """
    result = subprocess.run(
        [sys.executable, "-m", "gh_manage", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.startswith("Usage: gh-manage [OPTIONS] COMMAND [ARGS]...")
    # Make sure the leaked implementation detail is NOT in the output.
    assert "python -m gh_manage" not in result.stdout
