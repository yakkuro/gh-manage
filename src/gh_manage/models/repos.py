"""Pydantic schema for config/repos.yml.

A ReposConfig holds a list of repos to scan with `gh manage drift --all`.
Each entry specifies the repo name (owner/repo format) and the profile
to use for scanning.

Phase 8.5 ships with 1 entry (gh-manage itself). Consumer repos are
added as they are onboarded.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class RepoEntry(BaseModel):
    """One repo in repos.yml."""

    model_config = ConfigDict(extra="forbid")

    name: str  # "owner/repo" full form
    profile: str  # bundled profile name
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _validate_owner_repo_format(cls, v: str) -> str:
        if "/" not in v or v.count("/") != 1:
            raise ValueError(f"Repo name must be in 'owner/repo' format, got: {v!r}")
        owner, repo = v.split("/")
        if not owner or not repo:
            raise ValueError(
                f"Repo name must have non-empty owner and repo parts, got: {v!r}"
            )
        return v


class ReposConfig(BaseModel):
    """Top-level schema for config/repos.yml."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    repos: list[RepoEntry]
