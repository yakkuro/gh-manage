"""Tests for gh_manage.commands.drift — CLI-level behavior.

Engine tests live in tests/unit/drift/. This file covers CLI flag
validation and the parallel _scan_all_repos orchestration (Task 12+).
"""

from __future__ import annotations

import time
from pathlib import Path

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


# Task 12: parallel _scan_all_repos


def test_scan_all_repos_parallel_returns_all_three_results(mocker) -> None:
    """3 mock repos, concurrency=3, all succeed → all 3 in stdout."""
    from gh_manage.models.repos import ReposConfig, RepoEntry

    fake_config = ReposConfig(
        version=1,
        repos=[
            RepoEntry(name="yakkuro/a", profile="python-service", enabled=True),
            RepoEntry(name="yakkuro/b", profile="python-service", enabled=True),
            RepoEntry(name="yakkuro/c", profile="python-service", enabled=True),
        ],
    )

    mocker.patch("gh_manage.commands.drift.load_config", return_value=fake_config)
    mocker.patch(
        "gh_manage.commands.drift.resolve_repos_path",
        return_value=Path("/fake/repos.yml"),
    )

    def fake_scan(owner_repo, *args, **kwargs):
        return f"scan-of-{owner_repo}"

    mocker.patch("gh_manage.commands.drift._scan_single_repo", side_effect=fake_scan)

    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "3"])

    assert result.exit_code == 0, result.output
    assert "scan-of-yakkuro/a" in result.output
    assert "scan-of-yakkuro/b" in result.output
    assert "scan-of-yakkuro/c" in result.output


def test_scan_all_repos_one_failure_does_not_abort_others(mocker) -> None:
    from gh_manage.github_client import GhAPIError
    from gh_manage.models.repos import ReposConfig, RepoEntry

    fake_config = ReposConfig(
        version=1,
        repos=[
            RepoEntry(name="yakkuro/ok", profile="python-service", enabled=True),
            RepoEntry(name="yakkuro/bad", profile="python-service", enabled=True),
        ],
    )
    mocker.patch("gh_manage.commands.drift.load_config", return_value=fake_config)
    mocker.patch(
        "gh_manage.commands.drift.resolve_repos_path",
        return_value=Path("/fake/repos.yml"),
    )

    def fake_scan(owner_repo, *args, **kwargs):
        if owner_repo == "yakkuro/bad":
            raise GhAPIError("synthetic failure", status_code=500)
        return "ok-output"

    mocker.patch("gh_manage.commands.drift._scan_single_repo", side_effect=fake_scan)

    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "2"])

    assert result.exit_code == 0
    assert "ok-output" in result.output
    # Summary (stderr in the real app; CliRunner with mix_stderr=True merges them)
    assert "FAILED" in result.output
    assert "yakkuro/bad" in result.output


def test_scan_all_repos_unexpected_exception_does_not_abort_scan(mocker) -> None:
    """Non-domain exceptions (e.g. OSError from tempdir) must NOT escape
    future.result() and crash --all. Spec §2 parallel isolation requires
    any exception to be materialized as FAILED.
    """
    from gh_manage.models.repos import RepoEntry, ReposConfig

    fake_config = ReposConfig(
        version=1,
        repos=[
            RepoEntry(name="yakkuro/ok", profile="python-service", enabled=True),
            RepoEntry(name="yakkuro/crash", profile="python-service", enabled=True),
        ],
    )
    mocker.patch("gh_manage.commands.drift.load_config", return_value=fake_config)
    mocker.patch(
        "gh_manage.commands.drift.resolve_repos_path",
        return_value=Path("/fake/repos.yml"),
    )

    def fake_scan(owner_repo, *args, **kwargs):
        if owner_repo == "yakkuro/crash":
            raise OSError("tempdir unavailable")
        return "ok-output"

    mocker.patch("gh_manage.commands.drift._scan_single_repo", side_effect=fake_scan)

    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "2"])

    # Exit 0: the scan completes; the unexpected OSError is materialized as FAILED
    assert result.exit_code == 0, result.output
    assert "ok-output" in result.output
    assert "FAILED" in result.output
    assert "yakkuro/crash" in result.output
    assert "yakkuro/ok" in result.output


def test_scan_all_repos_summary_in_repos_yml_order(mocker) -> None:
    """Per-repo results may stream in completion order, but the final
    summary must list repos in repos.yml order for deterministic diffs.
    """
    from gh_manage.models.repos import ReposConfig, RepoEntry

    fake_config = ReposConfig(
        version=1,
        repos=[
            RepoEntry(name="yakkuro/first", profile="python-service", enabled=True),
            RepoEntry(name="yakkuro/second", profile="python-service", enabled=True),
            RepoEntry(name="yakkuro/third", profile="python-service", enabled=True),
        ],
    )
    mocker.patch("gh_manage.commands.drift.load_config", return_value=fake_config)
    mocker.patch(
        "gh_manage.commands.drift.resolve_repos_path",
        return_value=Path("/fake/repos.yml"),
    )
    mocker.patch("gh_manage.commands.drift._scan_single_repo", return_value="done")

    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "3"])
    assert result.exit_code == 0

    # Summary lines appear after '--- Scan Summary ---'
    summary = result.output.split("--- Scan Summary ---", 1)[1]
    first_idx = summary.index("yakkuro/first")
    second_idx = summary.index("yakkuro/second")
    third_idx = summary.index("yakkuro/third")
    assert first_idx < second_idx < third_idx


def test_scan_all_repos_parallel_wall_clock_faster_than_sequential(
    mocker,
) -> None:
    """4 mock repos @ 1s each; concurrency=4 must finish < 1.8s (overhead
    budget). concurrency=1 must be > 3.5s (sequential). Guards against
    GIL-bound regressions where workers don't actually run in parallel.
    """
    from gh_manage.models.repos import ReposConfig, RepoEntry

    fake_config = ReposConfig(
        version=1,
        repos=[
            RepoEntry(name=f"yakkuro/r{i}", profile="python-service", enabled=True)
            for i in range(4)
        ],
    )
    mocker.patch("gh_manage.commands.drift.load_config", return_value=fake_config)
    mocker.patch(
        "gh_manage.commands.drift.resolve_repos_path",
        return_value=Path("/fake/repos.yml"),
    )

    def slow_scan(owner_repo, *args, **kwargs):
        time.sleep(1.0)
        return "done"

    mocker.patch("gh_manage.commands.drift._scan_single_repo", side_effect=slow_scan)

    runner = CliRunner()
    t0 = time.monotonic()
    result = runner.invoke(drift, ["--all", "--concurrency", "4"])
    parallel_elapsed = time.monotonic() - t0
    assert result.exit_code == 0
    assert parallel_elapsed < 1.8, f"parallel took {parallel_elapsed:.2f}s"

    t0 = time.monotonic()
    result = runner.invoke(drift, ["--all", "--concurrency", "1"])
    sequential_elapsed = time.monotonic() - t0
    assert result.exit_code == 0
    assert sequential_elapsed > 3.5, f"sequential took {sequential_elapsed:.2f}s"


def test_scan_all_repos_disabled_entries_skipped(mocker) -> None:
    from gh_manage.models.repos import ReposConfig, RepoEntry

    fake_config = ReposConfig(
        version=1,
        repos=[
            RepoEntry(name="yakkuro/on", profile="python-service", enabled=True),
            RepoEntry(name="yakkuro/off", profile="python-service", enabled=False),
        ],
    )
    mocker.patch("gh_manage.commands.drift.load_config", return_value=fake_config)
    mocker.patch(
        "gh_manage.commands.drift.resolve_repos_path",
        return_value=Path("/fake/repos.yml"),
    )

    scan_mock = mocker.patch(
        "gh_manage.commands.drift._scan_single_repo", return_value="done"
    )

    runner = CliRunner()
    result = runner.invoke(drift, ["--all", "--concurrency", "2"])
    assert result.exit_code == 0
    assert "SKIPPED" in result.output
    assert "yakkuro/off" in result.output
    assert scan_mock.call_count == 1  # only the enabled one
