"""Pydantic schema for config/labels.yml (version 1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LabelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    color: str = Field(pattern=r"^[0-9a-fA-F]{6}$")
    description: str | None = None


class CategorySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    labels: list[LabelSpec] = Field(min_length=1)


class LabelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    categories: dict[str, CategorySpec] = Field(min_length=1)
