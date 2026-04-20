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
from gh_manage.github_client import (
    GhAuthError,
    GhError,
    GhNotFoundError,
    GhPermissionError,
    run_gh_api,
)
from gh_manage.models.profiles import ProfileSpec
from gh_manage.models.repos import ReposConfig

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
    """Return ci.yml contents for owner/repo, or '' if the file is absent.

    The GitHub contents API returns a JSON object with `content`
    base64-encoded for a file path. run_gh_api already parses the
    response as JSON.

    Error handling:
    - `GhNotFoundError` (HTTP 404) → return "": the ci.yml genuinely
      doesn't exist. This is the only case that maps to "absent".
    - Response shaped unexpectedly (not a dict, or dict without
      `content`) → raise DoctorError. GitHub's contents API returns a
      list for directory paths; a list here means we somehow queried a
      directory instead of a file and silently treating it as "absent"
      would make doctor return green for a case doctor should surface.
    - base64/UTF-8 decode failures → raise DoctorError with repo context.
    - Any other GhError (403, 401, 5xx, rate limit) → propagates
      unchanged; the caller sees a real auth/operational error.
    """
    import binascii

    try:
        payload = run_gh_api(f"repos/{repo}/contents/.github/workflows/ci.yml")
    except GhNotFoundError:
        return ""

    if not isinstance(payload, dict) or "content" not in payload:
        raise DoctorError(
            f"GitHub contents API for {repo}/.github/workflows/ci.yml "
            f"returned an unexpected shape ({type(payload).__name__}); "
            f"expected a file object with a 'content' field. "
            f"If the path is actually a directory in this repo, the "
            f"consumer's ci.yml layout has drifted from the expected "
            f"single-file shape and needs manual investigation."
        )

    try:
        return base64.b64decode(payload["content"]).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise DoctorError(
            f"Failed to decode ci.yml content from {repo}: {exc}"
        ) from exc


def _resolve_profile_required_contexts(profile: ProfileSpec) -> tuple[str, ...]:
    return tuple(getattr(profile, "required_contexts", ()) or ())


def _resolve_live_required_contexts(
    repo: str, default_branch: str
) -> tuple[str, ...] | None:
    """Return the live required_status_checks.contexts list, or None if
    we could not read it (auth / permission failure).

    Distinguishes three cases so checks can react appropriately:
      - dict payload with a contexts list → `tuple(contexts)` (may be empty)
      - GhNotFoundError (404) → `()`  (protection exists but no contexts)
      - GhAuthError / GhPermissionError → `None` (state unknown)
      - any other GhError → `None` (defensive — treat as unknown rather
        than fabricate an empty list, which would surface as spurious
        HIGH/CRITICAL findings under shape/* checks)

    Callers must treat None as "skip live-vs-profile comparisons".
    """
    try:
        payload = protection_api.get_branch_protection(repo, default_branch)
    except GhNotFoundError:
        return ()
    except (GhAuthError, GhPermissionError):
        return None
    except GhError:
        return None
    if not isinstance(payload, dict):
        return None
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
    readable = live_ctx is not None
    ctx = CheckContext(
        repo=repo,
        ci_yml_text=ci_yml_text,
        profile_name=profile_name,
        required_contexts=live_ctx or (),
        required_contexts_readable=readable,
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
    readable = live_ctx is not None
    ctx = CheckContext(
        repo=repo,
        ci_yml_text=ci_yml_text,
        profile_name=profile_name,
        required_contexts=live_ctx or (),
        required_contexts_readable=readable,
        profile_required_contexts=_resolve_profile_required_contexts(profile),
        source_hint=f"remote:{repo}",
    )
    return run_checks(ctx)
