"""Tests for _resolve_self_referencing — repos.yml lookup helper.

The helper is used by the single-repo drift CLI path to find the
self_referencing flag for the local repo (whose owner/repo is derived
from `git remote get-url origin`). The --all path bypasses the lookup
because it already has the RepoEntry in scope.
"""

from __future__ import annotations

from typing import Any

from gh_manage.commands._shared import _resolve_self_referencing


def test_resolve_self_referencing_returns_true_for_gh_manage() -> None:
    """gh-manage is marked self_referencing: true in bundled repos.yml."""
    assert _resolve_self_referencing("yakkuro/gh-manage") is True


def test_resolve_self_referencing_returns_false_for_other_bundled_repos() -> None:
    """All other bundled entries default to False."""
    assert _resolve_self_referencing("yakkuro/slack-agents") is False
    assert _resolve_self_referencing("yakkuro/llm-kb") is False


def test_resolve_self_referencing_returns_false_for_unregistered_repo() -> None:
    """Repos not in repos.yml safely default to False (ad-hoc scans
    of unregistered repos are allowed)."""
    assert _resolve_self_referencing("yakkuro/totally-unregistered") is False


def test_resolve_self_referencing_returns_false_when_repos_yml_missing(
    mocker: Any,
) -> None:
    """If repos.yml cannot be loaded, the helper logs a warning and
    returns False — drift checks must not abort because of this lookup."""
    from gh_manage.config import ConfigError

    mocker.patch(
        "gh_manage.config.load_config",
        side_effect=ConfigError("simulated missing repos.yml"),
    )
    assert _resolve_self_referencing("yakkuro/gh-manage") is False
