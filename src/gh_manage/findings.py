"""Shared finding/severity types.

Extracted from drift_sync.py so both drift_sync (check_labels /
check_protection / check_profile_files) and doctor (shape checks) can
import the same type without a circular dependency.

This is the first concrete step of the drift_sync.py split tracked as
Theme A (#47). drift_sync.py continues to re-export Finding and
Severity for one release (cli/v1.2.x) to keep existing imports working.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


Severity = Literal["critical", "high", "medium", "low"]


@dataclass(frozen=True)
class Finding:
    """One drift finding. Frozen, comparable, hashable.

    Phase 8 uses per-item granularity: 10 missing labels produce 10
    findings. Group rendering (if ever needed) happens at the report
    layer; the Finding itself is atomic.
    """

    severity: Severity
    check: str  # "labels" | "protection" | "profile_files"
    repo: str  # "owner/repo"
    field_path: str  # e.g. "labels[priority/critical]", "enforce_admins", "CLAUDE.md"
    current_value: Any  # current value on the repo (None if missing)
    desired_value: Any  # desired value per profile/policy (None if extraneous)
    message: str  # human-readable 1-line explanation
    remediation: str | None = None  # optional fix command
