"""Tests for cli.py --log-file validation and option wiring."""

from __future__ import annotations

import os
import stat

import click
import pytest
from click.testing import CliRunner

from gh_manage.cli import _validate_log_file, main


def test_validate_log_file_rejects_missing_parent(tmp_path):
    missing = tmp_path / "nonexistent-dir" / "x.log"
    with pytest.raises(click.UsageError) as exc:
        _validate_log_file(missing)
    assert "parent directory does not exist" in str(exc.value)


def test_validate_log_file_rejects_unwritable(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root bypasses permission bits")
    tmp_path.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        target = tmp_path / "x.log"
        with pytest.raises(click.UsageError) as exc:
            _validate_log_file(target)
        assert "Cannot write" in str(exc.value)
    finally:
        tmp_path.chmod(stat.S_IRWXU)


def test_validate_log_file_accepts_new_path(tmp_path):
    target = tmp_path / "new.log"
    assert not target.exists()
    _validate_log_file(target)
    assert target.exists()


def test_validate_log_file_accepts_existing_path(tmp_path):
    target = tmp_path / "existing.log"
    target.write_text("pre-existing content\n", encoding="utf-8")
    _validate_log_file(target)
    assert target.read_text(encoding="utf-8") == "pre-existing content\n"


# ---- CLI integration tests (Task 5) ----


def test_cli_log_file_env_var_honored(tmp_path, monkeypatch):
    log_path = tmp_path / "x.log"
    monkeypatch.setenv("GH_MANAGE_LOG_FILE", str(log_path))
    runner = CliRunner()
    # Invoke a subcommand (no required args → subcommand fails) to trigger the
    # root callback. The root callback runs before subcommand dispatch, which
    # is enough to touch the log file via _validate_log_file.
    runner.invoke(main, ["labels"], env={"GH_MANAGE_LOG_FILE": str(log_path)})
    assert log_path.exists()


def test_cli_log_file_rejects_bad_path(tmp_path):
    bad = tmp_path / "nonexistent-parent" / "x.log"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--log-file", str(bad), "labels", "show", "owner/repo"],
    )
    assert result.exit_code != 0
    combined = result.output + (str(result.exception) if result.exception else "")
    assert "parent directory does not exist" in combined


def test_cli_log_file_env_var_rejects_bad_path(tmp_path, monkeypatch):
    bad = tmp_path / "nonexistent-parent" / "x.log"
    monkeypatch.setenv("GH_MANAGE_LOG_FILE", str(bad))
    runner = CliRunner()
    result = runner.invoke(main, ["labels", "show", "owner/repo"])
    assert result.exit_code != 0
    combined = result.output + (str(result.exception) if result.exception else "")
    assert "parent directory does not exist" in combined
