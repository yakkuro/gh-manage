"""Local git CLI subprocess transport + error hierarchy.

Mirrors gh_manage.github_client: a typed wrapper around the `git` CLI
with classified errors. All git subprocess calls in gh-manage go through
this module so error handling stays consistent across phases.

Phase 6 ships parse_origin_url + get_origin_owner_repo. Phase 7+ may
add is_clean_tree, current_branch, etc. — same module, same error
classification pattern.
"""

from __future__ import annotations

import re

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
