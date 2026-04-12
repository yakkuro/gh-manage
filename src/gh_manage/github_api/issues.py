"""GitHub Issues API helpers for the drift scanner.

Thin wrapper around gh_manage.github_client for Issue-specific operations.
Mirrors the pattern of github_api/labels.py — each function is a single
API call with typed arguments and minimal logic.

Phase 8.5 uses these for the drift Issue state machine:
create/update/close Issues and manage the `gh-manage:drift` label.
"""

from __future__ import annotations

from typing import Any

from gh_manage.github_client import GhError, run_gh_api


_DRIFT_LABEL = "gh-manage:drift"
_DRIFT_LABEL_COLOR = "d4c5f9"
_DRIFT_LABEL_DESCRIPTION = "Automated drift report from gh-manage scanner"


def search_drift_issue(repo: str) -> dict[str, Any] | None:
    """Search for an open drift Issue on the repo.

    Uses the Issues endpoint with label filter (NOT the search API,
    which has index delay). Returns the first matching Issue dict,
    or None if no open drift Issue exists.
    """
    result = run_gh_api(
        f"repos/{repo}/issues?labels={_DRIFT_LABEL}&state=open&per_page=1"
    )
    if result is None:
        return None
    if isinstance(result, list) and len(result) > 0:
        return result[0]
    return None


def create_issue(repo: str, title: str, body: str, labels: list[str]) -> dict[str, Any]:
    """POST /repos/{repo}/issues. Returns the created Issue dict."""
    result = run_gh_api(
        f"repos/{repo}/issues",
        method="POST",
        body={"title": title, "body": body, "labels": labels},
    )
    assert isinstance(result, dict), (
        f"Expected dict from issue creation, got {type(result).__name__}"
    )
    return result


def update_issue_body(repo: str, issue_number: int, body: str) -> None:
    """PATCH /repos/{repo}/issues/{number} — update body only."""
    run_gh_api(
        f"repos/{repo}/issues/{issue_number}",
        method="PATCH",
        body={"body": body},
    )


def add_issue_comment(repo: str, issue_number: int, body: str) -> None:
    """POST /repos/{repo}/issues/{number}/comments."""
    run_gh_api(
        f"repos/{repo}/issues/{issue_number}/comments",
        method="POST",
        body={"body": body},
    )


def close_issue(repo: str, issue_number: int) -> None:
    """PATCH /repos/{repo}/issues/{number} — set state=closed."""
    run_gh_api(
        f"repos/{repo}/issues/{issue_number}",
        method="PATCH",
        body={"state": "closed"},
    )


def ensure_drift_label(repo: str) -> None:
    """Ensure the `gh-manage:drift` label exists on the repo.

    Attempts to create it. If the label already exists (HTTP 422),
    the error is silently ignored. Any other error propagates.
    """
    try:
        run_gh_api(
            f"repos/{repo}/labels",
            method="POST",
            body={
                "name": _DRIFT_LABEL,
                "color": _DRIFT_LABEL_COLOR,
                "description": _DRIFT_LABEL_DESCRIPTION,
            },
        )
    except GhError as e:
        # 422 = label already exists — expected and harmless
        if "422" in str(e) or "already_exists" in str(e):
            return
        raise


def get_issue_comments(
    repo: str, issue_number: int, per_page: int = 5
) -> list[dict[str, Any]]:
    """GET /repos/{repo}/issues/{number}/comments — latest N comments.

    Returns newest first (sort=created, direction=desc).
    """
    result = run_gh_api(
        f"repos/{repo}/issues/{issue_number}/comments"
        f"?per_page={per_page}&sort=created&direction=desc"
    )
    if result is None:
        return []
    assert isinstance(result, list), (
        f"Expected list from comments endpoint, got {type(result).__name__}"
    )
    return result
