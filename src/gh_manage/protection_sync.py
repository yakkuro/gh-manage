"""Pure-function engine for branch protection sync.

Mirrors gh_manage.profile_sync and gh_manage.labels_sync. Layered into
5 public functions called in order:

  1. normalize_protection_response(raw_api_response) -> canonical_current
  2. build_desired_protection(policy, profile) -> desired_body
  3. detect_downgrade(current, desired) -> tuple of DowngradeFinding
  4. compute_protection_diff(current, policy, profile, target_branch)
     -> ProtectionDiff (walks all 3 above)
  5. apply_protection_diff(diff, repo, target_branch, *, ...) -> None

Layer 1-3 are primitives; layer 4 composes them; layer 5 is the only
one that touches GitHub or filesystem (backup + PUT). Tasks 5-8
implement each layer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gh_manage.models.branch_protection import PolicySpec
from gh_manage.models.profiles import ProfileSpec


# Diff entry types
@dataclass(frozen=True)
class ProtectionFieldChange:
    """One field-level change detected between current and desired protection."""

    field_path: str
    current_value: Any
    desired_value: Any


@dataclass(frozen=True)
class DowngradeFinding:
    """A field change classified as weakening protection."""

    field_path: str
    current_value: Any
    desired_value: Any
    reason: str


@dataclass(frozen=True)
class ProtectionDiff:
    """Output of compute_protection_diff.

    changes: every field that differs (both upgrades and downgrades)
    downgrades: the subset that are weakening (downgrades ⊆ changes)
    current_raw: raw GitHub API response (for backup)
    desired_raw: PUT body (for apply)
    """

    changes: tuple[ProtectionFieldChange, ...]
    downgrades: tuple[DowngradeFinding, ...]
    current_raw: dict[str, Any]
    desired_raw: dict[str, Any]

    @property
    def is_empty(self) -> bool:
        return not self.changes

    @property
    def has_downgrades(self) -> bool:
        return bool(self.downgrades)


# Error hierarchy
class ProtectionError(Exception):
    """Base for protection_sync errors. Caught by commands/_handle_errors."""


class ProtectionPolicyNotFoundError(ProtectionError):
    """profile.protection_policy references a policy name not in
    branch-protection.yml. Message includes the list of available
    policies from the loaded config."""


class ProtectionDowngradeError(ProtectionError):
    """apply_protection_diff was called with diff.has_downgrades AND
    downgrade_allowed=False."""

    def __init__(self, downgrades: tuple[DowngradeFinding, ...]):
        self.downgrades = downgrades
        lines = "\n  ".join(
            f"{d.field_path}: {d.current_value} → {d.desired_value} ({d.reason})"
            for d in downgrades
        )
        super().__init__(
            f"{len(downgrades)} protection field(s) would be weakened:\n  {lines}\n"
            f"Re-run with --downgrade-allowed to override explicitly, or update "
            f"the profile/policy to preserve the current strength."
        )


class ProtectionBackupError(ProtectionError):
    """Failed to write the pre-apply backup. apply_protection_diff aborts
    BEFORE the PUT call — we refuse to modify protection without a
    restorable backup path."""


class ProtectionApplyError(ProtectionError):
    """The PUT to GitHub failed. Wraps the underlying GhError."""


# Stub engine functions — implementations land in Tasks 5-8
def normalize_protection_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize GitHub API response to canonical comparison shape.
    Implementation in Task 5."""
    raise NotImplementedError("Task 5")


def build_desired_protection(
    policy: PolicySpec, profile: ProfileSpec
) -> dict[str, Any]:
    """Combine a policy with a profile to produce the effective PUT body.
    Implementation in Task 7."""
    raise NotImplementedError("Task 7")


def detect_downgrade(
    current: dict[str, Any], desired: dict[str, Any]
) -> tuple[DowngradeFinding, ...]:
    """Check the 13 downgrade rules.
    Implementation in Task 6."""
    raise NotImplementedError("Task 6")


def compute_protection_diff(
    current: dict[str, Any],
    policy: PolicySpec,
    profile: ProfileSpec,
    target_branch: str = "main",
) -> ProtectionDiff:
    """Compute the diff between current protection and desired state.
    Implementation in Task 7."""
    raise NotImplementedError("Task 7")


def apply_protection_diff(
    diff: ProtectionDiff,
    repo: str,
    target_branch: str = "main",
    *,
    downgrade_allowed: bool = False,
    backup_dir: Path,
    progress: Callable[[str], None] = lambda _: None,
) -> None:
    """Apply the protection diff with safety guards.
    Implementation in Task 8."""
    raise NotImplementedError("Task 8")
