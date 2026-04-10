"""Shared repository reference parsing and normalization.

Used by any command that takes a `<repo>` argument. Accepts either a bare
repo name (prepended with `DEFAULT_OWNER`) or a fully-qualified `owner/repo`
string, and validates both segments against GitHub's repo naming rules.
"""

from __future__ import annotations

import re

DEFAULT_OWNER = "yakkuro"

# GitHub repo / owner name segment: letters, digits, `_`, `.`, `-`; must not
# start with `.` or `-`. Length limit up to 100 chars per GitHub docs, but we
# don't enforce that — rely on the API to reject excessively long names.
_SEGMENT_RE = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_REPO_REF_RE = re.compile(rf"^{_SEGMENT_RE}(?:/{_SEGMENT_RE})?$")


class InvalidRepoRefError(ValueError):
    """Raised when a repo argument doesn't look like a valid owner/repo."""


def parse_repo(name: str) -> str:
    """Normalize a repo argument to `owner/repo` form.

    Accepts either:
      - Bare repo name (`gh-manage`) → prepended with `DEFAULT_OWNER/`
      - Fully-qualified `owner/repo` → passed through unchanged

    Validates that both segments match GitHub's repo name rules. Raises
    InvalidRepoRefError with an actionable message for malformed input.
    """
    if not name or not _REPO_REF_RE.match(name):
        raise InvalidRepoRefError(
            f"Invalid repo reference: {name!r}. "
            f"Expected `owner/repo` or a bare repo name "
            f"(e.g., `gh-manage` → `{DEFAULT_OWNER}/gh-manage`)."
        )
    if "/" in name:
        return name
    return f"{DEFAULT_OWNER}/{name}"
