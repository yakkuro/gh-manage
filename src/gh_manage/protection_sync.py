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
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from gh_manage.github_api import protection as protection_api
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
    """Normalize a GitHub branch-protection API response into a canonical
    comparison shape. See Phase 7 design spec Section 'Engine' for the
    full rule set.

    Rules:
    1. Empty dict / missing top-level key → weakest default for each field
    2. `enforce_admins` → unwrap {enabled: bool}, default False
    3. `allow_force_pushes` / `allow_deletions` → unwrap {enabled: bool},
       default True (weakest — GitHub's unmanaged default allows force push/delete)
    4. `required_status_checks` → extract `strict` + `contexts`, drop
       other fields; missing → None
    5. `required_pull_request_reviews` → extract the 3 fields we care
       about (count, dismiss_stale, code_owner); missing → None
    6. `required_conversation_resolution` / `required_linear_history` →
       unwrap {enabled: bool}, default False
    """

    def _unwrap_enabled(key: str, default: bool) -> bool:
        wrapper = raw.get(key)
        if wrapper is None:
            return default
        if isinstance(wrapper, dict):
            return bool(wrapper.get("enabled", default))
        if isinstance(wrapper, bool):
            return wrapper
        return default

    # required_status_checks
    rsc_raw = raw.get("required_status_checks")
    rsc: dict[str, Any] | None
    if rsc_raw is None:
        rsc = None
    else:
        rsc = {
            "strict": bool(rsc_raw.get("strict", False)),
            "contexts": list(rsc_raw.get("contexts", [])),
        }

    # required_pull_request_reviews
    rpr_raw = raw.get("required_pull_request_reviews")
    rpr: dict[str, Any] | None
    if rpr_raw is None:
        rpr = None
    else:
        rpr = {
            "required_approving_review_count": int(
                rpr_raw.get("required_approving_review_count", 0)
            ),
            "dismiss_stale_reviews": bool(rpr_raw.get("dismiss_stale_reviews", False)),
            "require_code_owner_reviews": bool(
                rpr_raw.get("require_code_owner_reviews", False)
            ),
        }

    return {
        "required_status_checks": rsc,
        "required_pull_request_reviews": rpr,
        "enforce_admins": _unwrap_enabled("enforce_admins", default=False),
        "required_conversation_resolution": _unwrap_enabled(
            "required_conversation_resolution", default=False
        ),
        "required_linear_history": _unwrap_enabled(
            "required_linear_history", default=False
        ),
        "allow_force_pushes": _unwrap_enabled("allow_force_pushes", default=True),
        "allow_deletions": _unwrap_enabled("allow_deletions", default=True),
    }


def build_desired_protection(
    policy: PolicySpec, profile: ProfileSpec
) -> dict[str, Any]:
    """Combine a policy with a profile to produce the effective PUT body.

    Implements the Phase 7 spec's Profile ↔ Branch Protection contract:
        effective.required_status_checks.contexts = profile.required_contexts
    (complete replacement — the policy's contexts: [] is always overwritten).

    All other fields come from the policy as-is. Returns a dict shaped
    for the GitHub PUT /branches/{branch}/protection API body.
    """
    if policy.required_status_checks is None:
        rsc: dict[str, Any] | None = None
    else:
        rsc = {
            "strict": policy.required_status_checks.strict,
            "contexts": list(profile.required_contexts),  # profile override
        }

    if policy.required_pull_request_reviews is None:
        rpr: dict[str, Any] | None = None
    else:
        rpr = {
            "required_approving_review_count": policy.required_pull_request_reviews.required_approving_review_count,
            "dismiss_stale_reviews": policy.required_pull_request_reviews.dismiss_stale_reviews,
            "require_code_owner_reviews": policy.required_pull_request_reviews.require_code_owner_reviews,
        }

    return {
        "required_status_checks": rsc,
        "enforce_admins": policy.enforce_admins,
        "required_pull_request_reviews": rpr,
        "required_conversation_resolution": policy.required_conversation_resolution,
        "required_linear_history": policy.required_linear_history,
        "allow_force_pushes": policy.allow_force_pushes,
        "allow_deletions": policy.allow_deletions,
        # restrictions is required by the API and means "no user/team restrictions"
        "restrictions": None,
    }


def detect_downgrade(
    current: dict[str, Any], desired: dict[str, Any]
) -> tuple[DowngradeFinding, ...]:
    """Check the 13 downgrade rules. Both inputs MUST be canonical shape
    (output of normalize_protection_response). Raw GitHub API responses
    must not be passed directly.

    Returns empty tuple if desired is equal or stronger than current for
    every rule. Otherwise returns a DowngradeFinding per detected downgrade.
    """
    findings: list[DowngradeFinding] = []

    # Rule 4: required_pull_request_reviews exist → null (wrapper drop)
    curr_rpr = current.get("required_pull_request_reviews")
    desi_rpr = desired.get("required_pull_request_reviews")
    if curr_rpr is not None and desi_rpr is None:
        findings.append(
            DowngradeFinding(
                field_path="required_pull_request_reviews",
                current_value=curr_rpr,
                desired_value=None,
                reason="pull request review requirements removed entirely",
            )
        )
    # Rules 1, 2, 3 only apply when BOTH current and desired have the wrapper
    if curr_rpr is not None and desi_rpr is not None:
        # Rule 1: required_approving_review_count decrease
        cc = curr_rpr.get("required_approving_review_count", 0)
        dc = desi_rpr.get("required_approving_review_count", 0)
        if dc < cc:
            findings.append(
                DowngradeFinding(
                    field_path="required_pull_request_reviews.required_approving_review_count",
                    current_value=cc,
                    desired_value=dc,
                    reason=f"approving review count decreased {cc} → {dc}",
                )
            )
        # Rule 2: dismiss_stale_reviews true → false
        if (
            curr_rpr.get("dismiss_stale_reviews") is True
            and desi_rpr.get("dismiss_stale_reviews") is False
        ):
            findings.append(
                DowngradeFinding(
                    field_path="required_pull_request_reviews.dismiss_stale_reviews",
                    current_value=True,
                    desired_value=False,
                    reason="stale review dismissal disabled",
                )
            )
        # Rule 3: require_code_owner_reviews true → false
        if (
            curr_rpr.get("require_code_owner_reviews") is True
            and desi_rpr.get("require_code_owner_reviews") is False
        ):
            findings.append(
                DowngradeFinding(
                    field_path="required_pull_request_reviews.require_code_owner_reviews",
                    current_value=True,
                    desired_value=False,
                    reason="code owner review requirement disabled",
                )
            )

    # Rule 5: enforce_admins true → false
    if current.get("enforce_admins") is True and desired.get("enforce_admins") is False:
        findings.append(
            DowngradeFinding(
                field_path="enforce_admins",
                current_value=True,
                desired_value=False,
                reason="admin enforcement disabled",
            )
        )

    # Rule 8: required_status_checks exist → null
    curr_rsc = current.get("required_status_checks")
    desi_rsc = desired.get("required_status_checks")
    if curr_rsc is not None and desi_rsc is None:
        findings.append(
            DowngradeFinding(
                field_path="required_status_checks",
                current_value=curr_rsc,
                desired_value=None,
                reason="status check requirements removed entirely",
            )
        )
    # Rules 6, 7 only apply when BOTH current and desired have the wrapper
    if curr_rsc is not None and desi_rsc is not None:
        # Rule 6: strict true → false
        if curr_rsc.get("strict") is True and desi_rsc.get("strict") is False:
            findings.append(
                DowngradeFinding(
                    field_path="required_status_checks.strict",
                    current_value=True,
                    desired_value=False,
                    reason="strict update requirement disabled",
                )
            )
        # Rule 7: contexts set difference
        curr_contexts = set(curr_rsc.get("contexts", []))
        desi_contexts = set(desi_rsc.get("contexts", []))
        removed = curr_contexts - desi_contexts
        if removed:
            findings.append(
                DowngradeFinding(
                    field_path="required_status_checks.contexts",
                    current_value=sorted(curr_contexts),
                    desired_value=sorted(desi_contexts),
                    reason=f"required status checks removed: {sorted(removed)}",
                )
            )

    # Rule 9: required_conversation_resolution true → false
    if (
        current.get("required_conversation_resolution") is True
        and desired.get("required_conversation_resolution") is False
    ):
        findings.append(
            DowngradeFinding(
                field_path="required_conversation_resolution",
                current_value=True,
                desired_value=False,
                reason="conversation resolution requirement disabled",
            )
        )

    # Rule 10: required_linear_history true → false
    if (
        current.get("required_linear_history") is True
        and desired.get("required_linear_history") is False
    ):
        findings.append(
            DowngradeFinding(
                field_path="required_linear_history",
                current_value=True,
                desired_value=False,
                reason="linear history requirement disabled",
            )
        )

    # Rule 11: allow_force_pushes false → true
    if (
        current.get("allow_force_pushes") is False
        and desired.get("allow_force_pushes") is True
    ):
        findings.append(
            DowngradeFinding(
                field_path="allow_force_pushes",
                current_value=False,
                desired_value=True,
                reason="force push now allowed",
            )
        )

    # Rule 12: allow_deletions false → true
    if (
        current.get("allow_deletions") is False
        and desired.get("allow_deletions") is True
    ):
        findings.append(
            DowngradeFinding(
                field_path="allow_deletions",
                current_value=False,
                desired_value=True,
                reason="branch deletion now allowed",
            )
        )

    # Rule 13: target_branches is handled at a higher layer (the caller
    # applies the policy per-branch). Phase 7 MVP only handles "main", so
    # this rule is dormant but documented here for future phases.

    return tuple(findings)


def compute_protection_diff(
    current: dict[str, Any],
    policy: PolicySpec,
    profile: ProfileSpec,
    target_branch: str = "main",
) -> ProtectionDiff:
    """Compute the diff between current protection and desired state.

    Algorithm:
      1. normalized = normalize_protection_response(current)
      2. desired = build_desired_protection(policy, profile)
      3. Walk the field tree comparing normalized vs desired.
      4. Run detect_downgrade(normalized, desired) and emit DowngradeFinding
         for each weakening.
      5. Return ProtectionDiff containing changes + downgrades + raw dicts.

    Pure: no IO, no subprocess, no git, no GitHub API.
    """
    normalized = normalize_protection_response(current)
    desired = build_desired_protection(policy, profile)

    changes: list[ProtectionFieldChange] = []

    # Compare each field that both canonical shapes have
    for field in (
        "enforce_admins",
        "required_conversation_resolution",
        "required_linear_history",
        "allow_force_pushes",
        "allow_deletions",
    ):
        if normalized.get(field) != desired.get(field):
            changes.append(
                ProtectionFieldChange(
                    field_path=field,
                    current_value=normalized.get(field),
                    desired_value=desired.get(field),
                )
            )

    # required_status_checks (wrapper comparison)
    curr_rsc = normalized.get("required_status_checks")
    desi_rsc = desired.get("required_status_checks")
    if curr_rsc is None and desi_rsc is None:
        pass
    elif curr_rsc != desi_rsc:
        # Break down the nested diff for clearer output
        if (curr_rsc is None) != (desi_rsc is None):
            changes.append(
                ProtectionFieldChange(
                    field_path="required_status_checks",
                    current_value=curr_rsc,
                    desired_value=desi_rsc,
                )
            )
        else:
            assert curr_rsc is not None and desi_rsc is not None
            if curr_rsc.get("strict") != desi_rsc.get("strict"):
                changes.append(
                    ProtectionFieldChange(
                        field_path="required_status_checks.strict",
                        current_value=curr_rsc.get("strict"),
                        desired_value=desi_rsc.get("strict"),
                    )
                )
            # Compare contexts as a set: GitHub returns them in an
            # arbitrary order and order carries no semantic meaning.
            # Without this, a reorder would surface as a drift and cause
            # sync --apply to PUT unnecessarily.
            curr_contexts = set(curr_rsc.get("contexts") or [])
            desi_contexts = set(desi_rsc.get("contexts") or [])
            if curr_contexts != desi_contexts:
                changes.append(
                    ProtectionFieldChange(
                        field_path="required_status_checks.contexts",
                        current_value=curr_rsc.get("contexts"),
                        desired_value=desi_rsc.get("contexts"),
                    )
                )

    # required_pull_request_reviews (wrapper comparison)
    curr_rpr = normalized.get("required_pull_request_reviews")
    desi_rpr = desired.get("required_pull_request_reviews")
    if curr_rpr is None and desi_rpr is None:
        pass
    elif curr_rpr != desi_rpr:
        if (curr_rpr is None) != (desi_rpr is None):
            changes.append(
                ProtectionFieldChange(
                    field_path="required_pull_request_reviews",
                    current_value=curr_rpr,
                    desired_value=desi_rpr,
                )
            )
        else:
            assert curr_rpr is not None and desi_rpr is not None
            for sub in (
                "required_approving_review_count",
                "dismiss_stale_reviews",
                "require_code_owner_reviews",
            ):
                if curr_rpr.get(sub) != desi_rpr.get(sub):
                    changes.append(
                        ProtectionFieldChange(
                            field_path=f"required_pull_request_reviews.{sub}",
                            current_value=curr_rpr.get(sub),
                            desired_value=desi_rpr.get(sub),
                        )
                    )

    downgrades = detect_downgrade(normalized, desired)

    return ProtectionDiff(
        changes=tuple(changes),
        downgrades=downgrades,
        current_raw=current,
        desired_raw=desired,
    )


def _build_restore_body(current_raw: dict[str, Any]) -> dict[str, Any]:
    """Build a PUT-compatible body from a GET /branches/{branch}/protection
    response. Used by apply_protection_diff to ensure the backup file can
    actually be restored via `gh api -X PUT ... --input <backup-file>`.

    GitHub's GET wraps booleans as {enabled: bool, url: ...} objects and
    omits the `restrictions` key when no user/team restrictions are set,
    but the PUT endpoint requires flat booleans and a `restrictions: null`
    (or object). Calling normalize_protection_response first gives us the
    canonical flat shape; adding `restrictions: None` makes it PUT-ready.

    Limitation: fields we don't track in the canonical schema (e.g.,
    required_signatures, block_creations, lock_branch) are NOT preserved
    in the backup. Phase 7 MVP only covers the 7 fields listed in the
    design spec.
    """
    normalized = normalize_protection_response(current_raw)
    return {**normalized, "restrictions": None}


def apply_protection_diff(
    diff: ProtectionDiff,
    repo: str,
    target_branch: str = "main",
    *,
    downgrade_allowed: bool = False,
    backup_dir: Path,
    progress: Callable[[str], None] = lambda _: None,
) -> None:
    """Apply the protection diff with transactional safety guards.

    Order of operations (LOAD-BEARING):
      1. If diff.has_downgrades AND not downgrade_allowed → raise
         ProtectionDowngradeError BEFORE any IO.
      2. Pre-flight check backup_dir: if exists but not a directory,
         raise ProtectionBackupError. Otherwise mkdir(parents, exist_ok).
      3. Compute microsecond-unique backup filename, write YAML dump
         of _build_restore_body(diff.current_raw) — a PUT-compatible
         body so manual restore via `gh api -X PUT ... --input <backup>`
         actually works. Failure → ProtectionBackupError, no PUT.
      4. PUT the desired body via github_api.protection.put_branch_protection.
      5. If PUT fails, propagate the GhError — backup remains on disk
         for manual restore.

    progress() is called twice: once before backup, once before PUT.
    """
    # Step 1: downgrade check (transactional, no IO)
    if diff.has_downgrades and not downgrade_allowed:
        raise ProtectionDowngradeError(diff.downgrades)

    # Step 2: backup dir pre-flight
    if backup_dir.exists() and not backup_dir.is_dir():
        raise ProtectionBackupError(
            f"Backup directory path exists but is not a directory: {backup_dir}. "
            f"Remove or rename the file at this path, then re-run."
        )
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ProtectionBackupError(
            f"Cannot create backup directory {backup_dir}: {e}. "
            f"Check filesystem permissions."
        ) from e

    # Step 3: backup write with microsecond-unique filename
    owner_slug, _, repo_slug = repo.partition("/")
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S-%f")  # %f = microseconds
    backup_filename = f"{owner_slug}-{repo_slug}-{timestamp}.yml"
    backup_path = backup_dir / backup_filename

    progress(f"backup → {backup_path}")
    try:
        restore_body = _build_restore_body(diff.current_raw)
        backup_path.write_text(
            yaml.safe_dump(
                restore_body,
                default_flow_style=False,
                sort_keys=True,
                allow_unicode=True,
                indent=2,
            ),
            encoding="utf-8",
        )
    except (OSError, yaml.YAMLError) as e:
        raise ProtectionBackupError(
            f"Cannot write backup to {backup_path}: {e}. "
            f"Check disk space and write permissions on {backup_dir}, "
            f"or ensure the protection data is serializable."
        ) from e

    # Step 4: PUT — any failure propagates with backup preserved
    progress(f"apply → {repo}:{target_branch}")
    protection_api.put_branch_protection(repo, target_branch, diff.desired_raw)
