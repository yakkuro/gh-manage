"""Pydantic schema for config/repos.yml.

A ReposConfig holds a list of repos to scan with `gh manage drift --all`.
Each entry specifies the repo name (owner/repo format) and the profile
to use for scanning.

Phase 8.5 ships with 1 entry (gh-manage itself). Consumer repos are
added as they are onboarded.
"""

from __future__ import annotations

from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


_PROFILE_EXTENSIONS = (".yml", ".yaml")


class RepoEntry(BaseModel):
    """One repo in repos.yml."""

    model_config = ConfigDict(extra="forbid")

    name: str  # "owner/repo" full form
    profile: str  # bundled profile name
    enabled: bool = True
    self_referencing: bool = False
    """True when this repo publishes the templates it would otherwise be
    drift-checked against (e.g., yakkuro/gh-manage). Causes
    `check_profile_files` to skip per-entry comparisons whose template
    content references `<repo>/.github/workflows/` — the self-hosted form
    that uses `./` paths cannot hash-match the pinned-tag form. See
    docs/specs/2026-04-20-self-referencing-repos-design.md."""

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

    @model_validator(mode="after")
    def _validate_profile_names(self) -> ReposConfig:
        """Reject entries whose `profile` does not match a bundled profile.

        Looks up profiles via importlib.resources so the check works
        against installed wheels (not just source trees). All invalid
        entries are collected and reported in a single error message —
        a user with 3 typos should see them all in one run, not get
        whack-a-mole rejections.
        """
        profiles_root = files("gh_manage.data.profiles")
        available = {
            p.name.rsplit(".", 1)[0]
            for p in profiles_root.iterdir()
            if p.is_file() and p.name.endswith(_PROFILE_EXTENSIONS)
        }
        invalid = [
            (e.name, e.profile) for e in self.repos if e.profile not in available
        ]
        if invalid:
            msg_lines = ["Unknown profile references in repos.yml:"]
            for repo_name, profile in invalid:
                msg_lines.append(f"  - {repo_name}: profile={profile!r}")
            msg_lines.append(f"Available profiles: {sorted(available)}")
            raise ValueError("\n".join(msg_lines))
        return self
