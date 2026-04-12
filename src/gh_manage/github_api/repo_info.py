"""GitHub repo metadata helpers.

Thin wrapper around `gh api repos/{repo}` returning the fields gh-manage
needs (default branch, etc.). Phase 8 adds `get_default_branch` for the
drift scanner so that `check_protection` can resolve the target branch
dynamically instead of hardcoding "main".

Uses `gh api ... --jq <field>` to extract a single field from the
response. `gh` handles the jq expression server-side-ish and returns
the bare field value (not a JSON document), so we parse it as a string
with `str.strip()`.
"""

from __future__ import annotations

from gh_manage.github_client import GhAPIError, run_gh


def get_default_branch(repo: str) -> str:
    """Resolve the default branch of `repo` via `gh api repos/{repo}
    --jq .default_branch`.

    `repo` must be in `owner/repo` form. Returns the branch name as a
    trimmed string. Raises `GhNotFoundError` for 404 (repo does not
    exist or is inaccessible) and `GhAPIError` if the response is empty
    or whitespace-only.
    """
    stdout = run_gh(["api", f"repos/{repo}", "--jq", ".default_branch"])
    branch = stdout.strip()
    if not branch:
        raise GhAPIError(
            f"Empty default_branch response for {repo!r}. "
            f"This may indicate the repo has no default branch set, or the "
            f"API returned unexpected output. "
            f"Re-run with `GH_DEBUG=api` to inspect the raw response."
        )
    return branch
