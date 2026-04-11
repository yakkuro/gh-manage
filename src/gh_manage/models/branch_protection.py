"""Pydantic schema for config/branch-protection.yml.

A BranchProtectionConfig holds a dict of named policies. Each policy
describes the fields that gh-manage will PUT to GitHub's Classic Branch
Protection API for a given set of target branches.

Phase 7 MVP ships one policy (`solo-default`). Phase 7.5+ may add
`collaborative` and `docs-only`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RequiredStatusChecks(BaseModel):
    """required_status_checks field of a branch protection policy."""

    model_config = ConfigDict(extra="forbid")

    strict: bool
    contexts: list[str] = Field(default_factory=list)


class RequiredPullRequestReviews(BaseModel):
    """required_pull_request_reviews field of a branch protection policy."""

    model_config = ConfigDict(extra="forbid")

    required_approving_review_count: int = Field(ge=0, le=6)
    dismiss_stale_reviews: bool = False
    require_code_owner_reviews: bool = False


class PolicySpec(BaseModel):
    """One named policy in branch-protection.yml."""

    model_config = ConfigDict(extra="forbid")

    description: str
    target_branches: list[str]
    required_status_checks: RequiredStatusChecks | None
    enforce_admins: bool
    required_pull_request_reviews: RequiredPullRequestReviews | None
    required_conversation_resolution: bool
    required_linear_history: bool
    allow_force_pushes: bool
    allow_deletions: bool

    @field_validator("target_branches")
    @classmethod
    def _target_branches_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("target_branches must contain at least one branch")
        return v


class BranchProtectionConfig(BaseModel):
    """Top-level schema for config/branch-protection.yml."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    policies: dict[str, PolicySpec]
