"""gh-manage doctor — consumer-repo shape guardrail.

Public API (stable across cli/v1.2.x):

    run_checks(ctx) -> tuple[Finding, ...]          (Task 3)
    run_named_checks(ctx, names) -> tuple[Finding, ...]  (Task 3)
    run_on_path(path, profile_name=None) -> tuple[Finding, ...]  (Task 9)
    run_on_remote(repo, profile_name=None) -> tuple[Finding, ...]  (Task 9)

Spec: docs/specs/2026-04-17-doctor-guardrail-design.md
"""

from __future__ import annotations

# Importing checks registers them via @register_check side-effects
# (registry + checks populate in Tasks 3-6).
from gh_manage.doctor import checks  # noqa: F401

from gh_manage.doctor.context import CheckContext
from gh_manage.doctor.errors import (
    CiYmlParseError,
    DoctorCheckError,
    DoctorError,
)

__all__ = [
    "CheckContext",
    "DoctorError",
    "DoctorCheckError",
    "CiYmlParseError",
]
