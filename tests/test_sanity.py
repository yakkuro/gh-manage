"""Sanity tests that verify the Phase 0 scaffolding is wired correctly."""

from __future__ import annotations

import gh_manage


def test_package_version_is_defined() -> None:
    assert hasattr(gh_manage, "__version__")
    assert isinstance(gh_manage.__version__, str)
    assert gh_manage.__version__ == "1.7.0"


def test_cli_module_is_importable() -> None:
    from gh_manage import cli

    assert hasattr(cli, "main")
    assert callable(cli.main)
