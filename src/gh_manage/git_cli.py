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

# Match: git@github.com:owner/repo[.git] OR https://github.com/owner/repo[.git]
# Allow trailing slash, .git suffix, owner/repo segments matching GitHub's
# loose rules (alnum + dot + dash + underscore). Validation of the parts
# is delegated to GitHub itself; we only check the host.
_SSH_RE = re.compile(r"^git@github\.com:([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$")
_HTTPS_RE = re.compile(r"^https://github\.com/([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$")


def parse_origin_url(url: str) -> str:
    """Parse a git remote URL into 'owner/repo' form. Pure.

    Supports GitHub only (github.com):
      git@github.com:owner/repo.git    → owner/repo
      git@github.com:owner/repo        → owner/repo
      https://github.com/owner/repo.git → owner/repo
      https://github.com/owner/repo    → owner/repo

    Raises ValueError on any other URL form (gitlab, bitbucket, self-hosted,
    malformed) with an actionable message naming the offending URL and
    explaining gh-manage's GitHub-only constraint.
    """
    match = _SSH_RE.match(url) or _HTTPS_RE.match(url)
    if match is None:
        raise ValueError(
            f"Unsupported git remote URL: {url!r}. "
            f"gh-manage only supports GitHub (github.com) origins. "
            f"Non-GitHub remotes (gitlab.com, bitbucket.org, self-hosted) "
            f"are not supported in Phase 6."
        )
    owner, repo = match.groups()
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
    try:
        return parse_origin_url(url)
    except ValueError as e:
        raise UnsupportedOriginError(str(e)) from e
