"""CheckContext — the input bundle each doctor check receives."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckContext:
    """Inputs to a single-repo doctor run.

    repo
        "owner/repo" for reporting.
    ci_yml_text
        Raw contents of the target repo's .github/workflows/ci.yml, or
        empty string if the file is absent.
    profile_name
        The gh-manage profile name the repo is being validated against.
    required_contexts
        Tuple of status-check contexts required by the target repo's
        branch-protection policy on the default branch.
    profile_required_contexts
        Tuple of status-check contexts declared required by the
        bundled profile. Compared against `required_contexts` (the
        live protection view) in shape/required-contexts-match.
    source_hint
        Short string describing where ci_yml_text came from (local path
        or remote fetch). Used only in error messages.
    """

    repo: str
    ci_yml_text: str
    profile_name: str
    required_contexts: tuple[str, ...]
    profile_required_contexts: tuple[str, ...] = ()
    source_hint: str = "unknown"
