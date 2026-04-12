"""GitHub Classic Branch Protection API helpers.

Mirrors gh_manage.github_api.labels: resource-specific wrapper around
gh_manage.github_client's generic transport. Classic API only; Rulesets
API is future work.

Phase 7 is the first production consumer of run_gh_api(body=dict) —
the Phase 5 checkpoint refactor rewrote that path to send JSON via
`gh api --input -` (stdin) specifically to handle nested bodies like
branch protection PUT without the `-f key=value` type-coercion traps.
"""

from __future__ import annotations

from typing import Any

from gh_manage.github_client import run_gh_api


def get_branch_protection(repo: str, branch: str = "main") -> dict[str, Any]:
    """GET /repos/{repo}/branches/{branch}/protection.

    Returns the raw JSON response (nested dict matching GitHub's wire
    shape). The caller is responsible for normalization via
    `protection_sync.normalize_protection_response`.

    Raises GhNotFoundError if the branch has no protection configured —
    the caller should catch it and treat as "empty dict" for diff
    computation.
    """
    result = run_gh_api(f"repos/{repo}/branches/{branch}/protection")
    if result is None:
        return {}
    assert isinstance(result, dict), (
        f"Expected dict response, got {type(result).__name__}"
    )
    return result


def put_branch_protection(repo: str, branch: str, body: dict[str, Any]) -> None:
    """PUT /repos/{repo}/branches/{branch}/protection with the given body.

    Uses run_gh_api(body=...) which sends the JSON via `gh api --input -`
    (stdin). This avoids the `-f key=value` coercion traps — branch
    protection bodies contain nested objects (required_status_checks,
    required_pull_request_reviews) and booleans that string-coerce
    incorrectly.
    """
    run_gh_api(
        f"repos/{repo}/branches/{branch}/protection",
        method="PUT",
        body=body,
    )


def delete_branch_protection(repo: str, branch: str = "main") -> None:
    """DELETE /repos/{repo}/branches/{branch}/protection.

    Phase 7 does NOT call this in the normal flow — included for
    completeness and for Phase 7.5+ when a `gh manage protection unset`
    command may be added.
    """
    run_gh_api(
        f"repos/{repo}/branches/{branch}/protection",
        method="DELETE",
    )
