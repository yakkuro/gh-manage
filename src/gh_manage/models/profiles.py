"""Pydantic schema for profile YAML files (config/profiles/<name>.yml).

A profile defines a set of files to copy into a target repo when
`gh manage init` or `gh manage apply` runs. Phase 6 schema is minimal
(version, name, description, files); Phase 7+ will add extra_labels,
protection_policy, required_contexts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FileEntry(BaseModel):
    """A single file copy operation in a profile."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., description="Path under templates/, relative")
    dest: str = Field(..., description="Path under target repo root, relative")
    skip_if_exists: bool = False

    @field_validator("source", "dest")
    @classmethod
    def _no_obvious_traversal(cls, v: str) -> str:
        """Cheap structural rejection. Real escape prevention happens at
        apply time via Path.resolve() + is_relative_to() — see profile_sync.
        """
        if not v:
            raise ValueError("Path must not be empty")
        if v.startswith("/"):
            raise ValueError(f"Path must not be absolute: {v!r}")
        if ".." in v.split("/"):
            raise ValueError(f"Path must not contain '..' segments: {v!r}")
        return v


class ProfileSpec(BaseModel):
    """A gh-manage profile."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    name: str
    description: str | None = None
    files: list[FileEntry]

    @model_validator(mode="after")
    def _check_unique_dest(self) -> ProfileSpec:
        """Two entries writing to the same dest is a silent shadowing bug
        at apply time — only the last write would survive."""
        seen: set[str] = set()
        for entry in self.files:
            if entry.dest in seen:
                raise ValueError(
                    f"Duplicate dest path in profile {self.name!r}: {entry.dest!r}"
                )
            seen.add(entry.dest)
        return self
