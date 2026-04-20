"""Regression tests for commands/doctor.py log points.

Tests assert on result.output (CliRunner stderr capture) since
gh_manage logger has propagate=False.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from gh_manage.cli import main


@pytest.fixture
def mock_doctor_deps(monkeypatch):
    monkeypatch.setattr("gh_manage.doctor.run_on_path", lambda *a, **kw: ())
    monkeypatch.setattr("gh_manage.doctor.run_on_remote", lambda *a, **kw: ())
    monkeypatch.setattr(
        "gh_manage.git_cli.get_origin_owner_repo",
        lambda p: "owner/repo",
    )


def test_doctor_logs_invocation(mock_doctor_deps, tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--log-level", "info", "doctor", str(tmp_path), "--exit-zero"],
    )
    assert "doctor invoked" in result.output


def test_doctor_logs_completion(mock_doctor_deps, tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--log-level", "info", "doctor", str(tmp_path), "--exit-zero"],
    )
    assert "doctor complete" in result.output


def test_doctor_logs_warning_on_label_derivation_error(tmp_path, monkeypatch):
    monkeypatch.setattr("gh_manage.doctor.run_on_path", lambda *a, **kw: ())

    def _raise(p):
        raise RuntimeError("no git origin")

    monkeypatch.setattr("gh_manage.git_cli.get_origin_owner_repo", _raise)
    runner = CliRunner()
    result = runner.invoke(main, ["doctor", str(tmp_path), "--exit-zero"])
    assert "could not derive owner/repo" in result.output
