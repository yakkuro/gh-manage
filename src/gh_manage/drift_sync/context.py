"""Scan context + drift-specific errors.

Lowest layer of the drift_sync package. Depends on nothing else inside
drift_sync/ — only on stdlib + sibling models. All other drift_sync
submodules are allowed to import from here.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.labels import LabelsConfig
from gh_manage.models.profiles import ProfileSpec


@dataclass(frozen=True)
class ScanContext:
    """Input bundle for a drift scan. All checks read from ctx — they do
    not touch global state or pass extra arguments to each other.

    - path: local repo root (for file-based checks).
    - repo: "owner/repo" for API-based checks.
    - default_branch: resolved via `get_default_branch(repo)` at CLI
      startup. check_protection uses this instead of hardcoded "main".
    - profile: the loaded ProfileSpec.
    - labels_config: the loaded bundled labels.yml.
    - bp_config: the loaded bundled branch-protection.yml, or None if
      profile.protection_policy is None (opt-out).
    - live_required_contexts: tuple of status-check contexts required by
      the repo's branch-protection policy, resolved from the remote repo.
      Defaults to empty to avoid breaking existing call sites.
    - live_required_contexts_readable: True when the tuple above reflects
      a successful protection fetch. False when the fetch hit an
      auth/permission error; shape/* checks must then skip the
      produced-vs-required comparison to avoid spurious findings.
    """

    path: Path
    repo: str
    default_branch: str
    profile: ProfileSpec
    labels_config: LabelsConfig
    bp_config: BranchProtectionConfig | None
    live_required_contexts: tuple[str, ...] = ()
    live_required_contexts_readable: bool = True


class DriftError(Exception):
    """Base for drift_sync errors. Caught by commands/_handle_errors."""


class DriftOutputError(DriftError):
    """Failed to write the drift report to --output <path>. Wraps the
    underlying OSError with an actionable message."""


# Per-scan correlation id. Set at the entry of _scan_single_repo
# (commands/drift.py) and reset on exit. Default empty string means
# "not inside a scan" — the JSON formatter skips the field in that case.
# See docs/specs/2026-04-20-structured-logging-followups-design.md §2.
scan_id_var: ContextVar[str] = ContextVar("scan_id", default="")
