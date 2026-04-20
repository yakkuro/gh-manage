"""Tests for cli.py --log-file validation and option wiring."""

from __future__ import annotations

import os
import stat

import click
import pytest

from gh_manage.cli import _validate_log_file


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
