"""Shared repository reference parsing and normalization.

Used by any command that takes a `<repo>` argument. Accepts either a bare
repo name (prepended with `DEFAULT_OWNER`) or a fully-qualified `owner/repo`
string, and returns the normalized form.

Naming validation is intentionally delegated to the `gh` CLI. GitHub's
actual owner/repo naming rules are nuanced — e.g. `.github` is a valid
repo but usernames cannot contain underscores or consecutive hyphens —
and getting a regex wrong here would silently reject valid repos or
accept invalid ones. The `gh` CLI already returns actionable 404/422
errors for truly malformed names, which are classified by
`github_client._raise_classified_error` into the GhError hierarchy.
"""

from __future__ import annotations

DEFAULT_OWNER = "yakkuro"


def parse_repo(name: str) -> str:
    """Normalize a repo argument to `owner/repo` form.

    Accepts either:
      - Bare repo name (`gh-manage`) → prepended with `DEFAULT_OWNER/`.
      - Anything containing a `/` → passed through unchanged.

    This mirrors the pre-refactor behavior of the inline `_parse_repo`
    helper that used to live in `commands/labels.py`. Validation of the
    actual owner/repo name happens at the `gh` CLI layer; we don't try
    to pre-validate here.
    """
    if "/" in name:
        return name
    return f"{DEFAULT_OWNER}/{name}"
