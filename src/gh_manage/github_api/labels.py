"""GitHub labels API helpers.

Resource-specific helpers for the GitHub labels endpoints. All HTTP
transport is delegated to gh_manage.github_client (which wraps the `gh`
CLI subprocess). This module owns the typed Label dataclass and the
labels-specific CRUD semantics (rename via new_name body field, pagination
via `--jq '.[]'` NDJSON output).

Moved from github_client.py in the Phase 5 checkpoint refactor — Codex
flagged that mixing transport and resource helpers in the same file
blocks Phase 7 protection sync from adding its own resource layer cleanly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from gh_manage.github_client import GhAPIError, run_gh, run_gh_api


@dataclass(frozen=True)
class Label:
    """A GitHub label in normalized form.

    - color: always lowercase 6-char hex. github_api.labels.list_labels
      normalizes from the GitHub API which returns lowercase, but we
      lowercase defensively for cross-API consistency.
    - description: always str, never None. GitHub returns null for unset
      descriptions; we normalize to "" so equality comparisons are safe.
    """

    name: str
    color: str
    description: str


def list_labels(repo: str) -> list[Label]:
    """GET /repos/{repo}/labels — auto-paginated via `gh api --paginate --jq '.[]'`.

    `repo` must be in `owner/repo` form.
    Returns a list of Label instances with color lowercased and
    description normalized to "" if the API returned null.

    Pagination note: `gh api --paginate` alone emits multiple JSON
    documents concatenated (one per page), which `json.loads()` cannot
    parse for repos with >100 labels. Adding `--jq '.[]'` makes gh emit
    one JSON object per line (NDJSON), which we parse line-by-line.
    This handles repos of any size without falling into the multi-document
    trap. Regression test: test_list_labels_handles_multi_page_response.
    """
    stdout = run_gh(["api", f"repos/{repo}/labels", "--paginate", "--jq", ".[]"])
    labels: list[Label] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as e:
            raise GhAPIError(
                f"Failed to parse label entry from `gh api` output: {e}. "
                f"Re-run with `GH_DEBUG=api` to inspect the raw response."
            ) from e
        labels.append(
            Label(
                name=item["name"],
                color=item["color"].lower(),
                description=item.get("description") or "",
            )
        )
    return labels


def create_label(repo: str, label: Label) -> None:
    """POST /repos/{repo}/labels with {name, color, description}."""
    run_gh_api(
        f"repos/{repo}/labels",
        method="POST",
        body={
            "name": label.name,
            "color": label.color,
            "description": label.description,
        },
    )


def update_label(repo: str, current_name: str, new_label: Label) -> None:
    """PATCH /repos/{repo}/labels/{current_name}.

    If new_label.name != current_name the body includes new_name (rename).
    Otherwise only color/description are updated.
    """
    body: dict[str, str] = {
        "color": new_label.color,
        "description": new_label.description,
    }
    if new_label.name != current_name:
        body["new_name"] = new_label.name

    run_gh_api(
        f"repos/{repo}/labels/{current_name}",
        method="PATCH",
        body=body,
    )


def delete_label(repo: str, name: str) -> None:
    """DELETE /repos/{repo}/labels/{name}."""
    run_gh_api(
        f"repos/{repo}/labels/{name}",
        method="DELETE",
    )
