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
    required_contexts_readable
        True when `required_contexts` reflects the actual live
        protection state. False when the protection API call failed
        (e.g., auth/permission error — CI default GITHUB_TOKEN cannot
        read branch protection). Shape checks that compare produced
        vs required contexts must skip when False, to avoid surfacing
        spurious CRITICAL/HIGH findings for "mismatch with unknown
        state". Default True (most callers have authenticated access).
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
    required_contexts_readable: bool = True
