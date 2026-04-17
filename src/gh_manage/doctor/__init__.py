"""gh-manage doctor — consumer-repo shape guardrail.

Public API (stable across cli/v1.2.x):

    run_checks(ctx) -> tuple[Finding, ...]          (Task 3)
    run_named_checks(ctx, names) -> tuple[Finding, ...]  (Task 3)
    run_on_path(path, profile_name=None) -> tuple[Finding, ...]  (Task 9)
    run_on_remote(repo, profile_name=None) -> tuple[Finding, ...]  (Task 9)

Spec: docs/specs/2026-04-17-doctor-guardrail-design.md
"""

from __future__ import annotations

import base64
from pathlib import Path

# Importing checks registers them via @register_check side-effects
# (registry + checks populate in Tasks 3-6).
from gh_manage.doctor import checks  # noqa: F401

from gh_manage.doctor.context import CheckContext
from gh_manage.doctor.errors import (
    CiYmlParseError,
    DoctorCheckError,
    DoctorError,
)
from gh_manage.doctor.registry import run_checks, run_named_checks

from gh_manage import git_cli
from gh_manage.config import load_config
from gh_manage.findings import Finding
from gh_manage.github_api import protection as protection_api
from gh_manage.github_client import GhError, GhNotFoundError, run_gh_api
from gh_manage.models.profiles import ProfileSpec
from gh_manage.models.repos import ReposConfig

import yaml

__all__ = [
    "CheckContext",
    "DoctorError",
    "DoctorCheckError",
    "CiYmlParseError",
    "run_checks",
    "run_named_checks",
    "run_on_path",
    "run_on_remote",
]


def _load_profile(profile_name: str) -> ProfileSpec:
    from gh_manage.commands._shared import resolve_profile_path

    return load_config(resolve_profile_path(profile_name), ProfileSpec)


def _read_local_ci_yml(path: Path) -> str:
    ci = path / ".github" / "workflows" / "ci.yml"
    try:
        return ci.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _fetch_remote_ci_yml(repo: str) -> str:
    """Return ci.yml contents for owner/repo, or '' if the file is absent."""
    try:
        raw = run_gh_api(["repos", repo, "contents", ".github/workflows/ci.yml"])
    except GhNotFoundError:
        return ""
    payload = yaml.safe_load(raw)
    if not isinstance(payload, dict) or "content" not in payload:
        return ""
    return base64.b64decode(payload["content"]).decode("utf-8")


def _resolve_profile_required_contexts(profile: ProfileSpec) -> tuple[str, ...]:
    return tuple(getattr(profile, "required_contexts", ()) or ())


def _resolve_live_required_contexts(repo: str, default_branch: str) -> tuple[str, ...]:
    try:
        payload = protection_api.get_branch_protection(repo, default_branch)
    except GhError:
        return ()
    if not isinstance(payload, dict):
        return ()
    rsc = payload.get("required_status_checks") or {}
    contexts = rsc.get("contexts") or []
    return tuple(contexts)


def _infer_profile_for_repo(repo: str) -> str:
    """Look up repo in bundled repos.yml. Raise DoctorError if absent."""
    from gh_manage.commands._shared import resolve_repos_path

    config = load_config(resolve_repos_path(), ReposConfig)
    # RepoEntry uses 'name' field for the owner/repo format
    for entry in config.repos:
        if entry.name == repo:
            return entry.profile
    raise DoctorError(
        f"Cannot infer profile: {repo!r} is not in bundled repos.yml. "
        f"Pass --profile explicitly."
    )


def run_on_path(path: Path, profile_name: str | None = None) -> tuple[Finding, ...]:
    """Run every registered doctor check against a local repo path."""
    path = path.resolve()
    repo = git_cli.get_origin_owner_repo(path)
    profile_name = profile_name or _infer_profile_for_repo(repo)
    profile = _load_profile(profile_name)
    ci_yml_text = _read_local_ci_yml(path)
    live_ctx = _resolve_live_required_contexts(repo, "main")
    ctx = CheckContext(
        repo=repo,
        ci_yml_text=ci_yml_text,
        profile_name=profile_name,
        required_contexts=live_ctx,
        profile_required_contexts=_resolve_profile_required_contexts(profile),
        source_hint=str(path),
    )
    return run_checks(ctx)


def run_on_remote(repo: str, profile_name: str | None = None) -> tuple[Finding, ...]:
    """Run every registered doctor check against a remote owner/repo."""
    profile_name = profile_name or _infer_profile_for_repo(repo)
    profile = _load_profile(profile_name)
    ci_yml_text = _fetch_remote_ci_yml(repo)
    live_ctx = _resolve_live_required_contexts(repo, "main")
    ctx = CheckContext(
        repo=repo,
        ci_yml_text=ci_yml_text,
        profile_name=profile_name,
        required_contexts=live_ctx,
        profile_required_contexts=_resolve_profile_required_contexts(profile),
        source_hint=f"remote:{repo}",
    )
    return run_checks(ctx)
