"""Local git CLI subprocess transport + error hierarchy.

Mirrors gh_manage.github_client: a typed wrapper around the `git` CLI
with classified errors. All git subprocess calls in gh-manage go through
this module so error handling stays consistent across phases.

Phase 6 ships parse_origin_url + get_origin_owner_repo. Phase 7+ may
add is_clean_tree, current_branch, etc. — same module, same error
classification pattern.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlparse

# Step 1 (SCP-form normalization): captures `git@host:path` (no scheme).
# urllib.parse cannot parse no-scheme URLs, so we normalize SCP-form to
# ssh:// before delegating to urlparse. The greedy `(.+)` second capture
# is intentional — malformed inputs like `git@host:443:extra` flow through
# to the path-split validation at Step 5 and are rejected there.
_SCP_FORM = re.compile(r"^git@([\w.\-]+):(.+)$")

# Step 6 (owner/repo character validation): preserves the old regex's
# strict character set — alphanumeric, dot, dash, underscore. GitHub allows
# these in repository names; anything else (spaces, colons, etc.) is rejected.
_PART_RE = re.compile(r"^[\w.\-]+$")

# Allowed schemes: https for HTTPS, ssh for explicit SSH, plus the SCP-form
# (no scheme) which we normalize to ssh:// at Step 1. The `git://` read-only
# protocol is intentionally NOT allowed — it is unused by gh-manage and
# untested. Add only when a real consumer requests it.
_ALLOWED_SCHEMES = ("https", "ssh")

# Allowed hosts: github.com (default) and ssh.github.com (the alternate
# SSH-over-port-443 hostname for users behind restrictive firewalls).
_ALLOWED_HOSTS = ("github.com", "ssh.github.com")


def parse_origin_url(url: str) -> str:
    """Parse a git remote URL into 'owner/repo' form. Pure.

    Supports GitHub only (github.com or ssh.github.com):

      git@github.com:owner/repo[.git]                      → owner/repo
      https://github.com/owner/repo[.git]                  → owner/repo
      ssh://git@github.com/owner/repo[.git]                → owner/repo
      ssh://git@ssh.github.com:443/owner/repo[.git]        → owner/repo

    Raises ValueError on any other form (gitlab, bitbucket, self-hosted,
    malformed) with an actionable message naming the offending URL and
    explaining gh-manage's GitHub-only constraint.

    Implementation is a hybrid: SCP-form (no scheme) is normalized to
    ssh:// via a regex first, then everything is parsed by urllib.parse.
    See spec docs/specs/2026-04-14-v1.0.x-cleanup-design.md for the
    rationale and edge cases.
    """
    # Step 1: SCP-form normalization (urllib.parse cannot handle no-scheme URLs)
    if (scp_match := _SCP_FORM.match(url)) is not None:
        host, path = scp_match.groups()
        url_to_parse = f"ssh://git@{host}/{path}"
    else:
        url_to_parse = url

    # Step 2: parse via urllib
    parsed = urlparse(url_to_parse)

    # Step 3: validate scheme
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Unsupported git remote URL: {url!r}. "
            f"Scheme {parsed.scheme!r} is not supported. "
            f"gh-manage only supports github.com origins via https, ssh, or git@."
        )

    # Step 4: validate host
    host = parsed.hostname or ""
    if host not in _ALLOWED_HOSTS:
        raise ValueError(
            f"Unsupported git remote URL: {url!r}. "
            f"gh-manage only supports GitHub (github.com) origins. "
            f"Non-GitHub remotes (gitlab.com, bitbucket.org, self-hosted) "
            f"are not supported."
        )

    # Step 5: extract and clean path
    path = parsed.path.lstrip("/").removesuffix("/").removesuffix(".git")
    parts = path.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(
            f"Unsupported git remote URL: {url!r}. "
            f"Cannot extract owner/repo from path {parsed.path!r}."
        )
    owner, repo = parts

    # Step 6: validate owner/repo characters
    if not _PART_RE.match(owner) or not _PART_RE.match(repo):
        raise ValueError(
            f"Unsupported git remote URL: {url!r}. "
            f"owner/repo characters must match [\\w.\\-]+."
        )

    return f"{owner}/{repo}"


class GitError(Exception):
    """Base for git CLI subprocess failures. Never raised directly."""


class GitNotInstalledError(GitError):
    """`git` CLI missing on PATH."""


class NotAGitRepoError(GitError):
    """target is not inside a git work tree."""


class NoOriginRemoteError(GitError):
    """git is set up but `origin` remote is not configured."""


class UnsupportedOriginError(GitError):
    """`origin` is set but URL is not a github.com remote (gitlab, bitbucket,
    self-hosted, etc.). Wraps ValueError from parse_origin_url so callers
    only need to catch GitError subclasses."""


_GIT_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C", "LC_MESSAGES": "C"}


def _raise_classified_git_error(*, stderr: str, returncode: int) -> NoReturn:
    """Classify git stderr into a typed GitError subclass."""
    stderr_lower = stderr.lower()
    if "not a git repository" in stderr_lower:
        raise NotAGitRepoError(
            f"Not a git repository. Run `git init` first to create one. "
            f"(git exit {returncode}: {stderr.strip()[:200]})"
        )
    if "no such remote" in stderr_lower:
        raise NoOriginRemoteError(
            "No `origin` remote configured. Run "
            "`git remote add origin git@github.com:OWNER/REPO.git` "
            "and try again."
        )
    raise GitError(
        f"git command failed (exit {returncode}): {stderr.strip()[:300]}. "
        f"Re-run with `GIT_TRACE=1` to see what git was doing."
    )


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run `git -C <cwd> <args>` with locale forced to C.

    All public functions in this module go through _run_git so error
    classification stays consistent and stderr matching stays locale-stable.

    Raises GitNotInstalledError if `git` is not on PATH. Returns the
    CompletedProcess unchanged otherwise — callers inspect returncode
    and call _raise_classified_git_error on non-zero.
    """
    try:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            check=False,
            env=_GIT_ENV,
        )
    except FileNotFoundError as e:
        raise GitNotInstalledError(
            "The `git` CLI is required but was not found on PATH. "
            "Install git from https://git-scm.com/ and try again."
        ) from e


def get_origin_owner_repo(target: Path) -> str:
    """Run `git remote get-url origin` in target and parse → 'owner/repo'.

    Raises:
      GitNotInstalledError    — git not on PATH
      NotAGitRepoError        — target is not inside a git work tree
      NoOriginRemoteError     — git is OK but `origin` is not set
      UnsupportedOriginError  — origin URL is not a github.com URL
      GitError                — other git failures (catch-all)
    """
    result = _run_git(["remote", "get-url", "origin"], cwd=target)
    if result.returncode != 0:
        _raise_classified_git_error(stderr=result.stderr, returncode=result.returncode)
    url = result.stdout.strip()
    if not url:
        raise NoOriginRemoteError(
            "The `origin` remote exists but has an empty URL. "
            "Run `git remote set-url origin git@github.com:OWNER/REPO.git` "
            "and try again."
        )
    try:
        return parse_origin_url(url)
    except ValueError as e:
        raise UnsupportedOriginError(str(e)) from e
