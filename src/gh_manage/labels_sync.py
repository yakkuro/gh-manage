"""Pure-function label diff computation and application.

All functions here are click/subprocess independent. Tests can exercise
compute_diff with in-memory data and apply_diff with monkey-patched
github_client module functions.

Dependency direction: this module imports github_client for the Label
dataclass and the 4 CRUD helpers. It does NOT import click or subprocess.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from gh_manage import github_client
from gh_manage.github_client import Label
from gh_manage.models.labels import LabelsConfig, LabelSpec


@dataclass(frozen=True)
class LabelRename:
    """A label rename operation. Uses PATCH with new_name body field."""

    old_name: str
    new_label: Label


@dataclass(frozen=True)
class LabelCreate:
    """A label creation. Uses POST."""

    label: Label


@dataclass(frozen=True)
class LabelUpdate:
    """A same-name label update (color/description only). Uses PATCH without new_name."""

    label: Label


@dataclass(frozen=True)
class LabelDelete:
    """A label deletion. Uses DELETE. Only emitted when prune=True."""

    name: str


@dataclass(frozen=True)
class LabelsDiff:
    """Computed diff between current repo labels and desired config.

    Operations are grouped by type into frozen tuples. Empty tuples for
    any empty bucket. apply_diff executes them in fail-fast order:
    renames → creates → updates → deletes.
    """

    renames: tuple[LabelRename, ...]
    creates: tuple[LabelCreate, ...]
    updates: tuple[LabelUpdate, ...]
    deletes: tuple[LabelDelete, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.renames or self.creates or self.updates or self.deletes)

    @property
    def total_changes(self) -> int:
        return (
            len(self.renames)
            + len(self.creates)
            + len(self.updates)
            + len(self.deletes)
        )


def _spec_to_label(spec: LabelSpec) -> Label:
    """Convert a LabelSpec (from yml) into a Label (github_client type).

    Normalizes:
      - color.lower() — LabelSpec regex accepts any case; we lowercase here
        so compute_diff comparisons are case-insensitive.
      - description None → "" — LabelSpec.description is str | None,
        Label.description is str. Normalize None to "" so equality works.
    """
    return Label(
        name=spec.name,
        color=spec.color.lower(),
        description=spec.description or "",
    )


def _flatten_desired(desired: LabelsConfig) -> list[LabelSpec]:
    """Flatten LabelsConfig.categories into a flat list of LabelSpec."""
    specs: list[LabelSpec] = []
    for category in desired.categories.values():
        specs.extend(category.labels)
    return specs


def compute_diff(
    current: list[Label],
    desired: LabelsConfig,
    *,
    prune: bool = False,
) -> LabelsDiff:
    """Compute the diff between current repo labels and desired config.

    Algorithm:
      1. Build a name→Label map of current labels.
      2. For each LabelSpec in flattened desired.categories:
         a. If spec.name is in current: compare color/desc → LabelUpdate or skip.
         b. Elif spec.old_name is set and in current: LabelRename.
         c. Else: LabelCreate.
         Mark any matched current name as consumed in either case.
      3. For each current label NOT consumed in step 2:
         - prune=True → LabelDelete.
         - prune=False → ignore.

    Normalization (applied before any equality check):
      - Color: spec.color.lower() vs current.color (already lowercase from
        github_client.list_labels normalization).
      - Description: (spec.description or "") vs current.description
        (already "" if GitHub returned null).
    """
    current_by_name = {label.name: label for label in current}
    consumed: set[str] = set()

    renames: list[LabelRename] = []
    creates: list[LabelCreate] = []
    updates: list[LabelUpdate] = []

    for spec in _flatten_desired(desired):
        desired_label = _spec_to_label(spec)

        # Case a: name match (preferred over old_name)
        if spec.name in current_by_name:
            existing = current_by_name[spec.name]
            if (
                existing.color != desired_label.color
                or existing.description != desired_label.description
            ):
                updates.append(LabelUpdate(label=desired_label))
            consumed.add(spec.name)
            continue

        # Case b: rename via old_name
        if spec.old_name and spec.old_name in current_by_name:
            renames.append(LabelRename(old_name=spec.old_name, new_label=desired_label))
            consumed.add(spec.old_name)
            continue

        # Case c: no match at all → create
        creates.append(LabelCreate(label=desired_label))

    deletes: list[LabelDelete] = []
    if prune:
        for label in current:
            if label.name not in consumed:
                deletes.append(LabelDelete(name=label.name))

    return LabelsDiff(
        renames=tuple(renames),
        creates=tuple(creates),
        updates=tuple(updates),
        deletes=tuple(deletes),
    )


def apply_diff(
    diff: LabelsDiff,
    repo: str,
    *,
    progress: Callable[[str], None] = lambda _: None,
) -> None:
    """Apply diff operations in fail-fast order.

    Execution order:
      1. Renames — first, so subsequent creates don't collide with old names.
      2. Creates — new labels.
      3. Updates — same-name color/desc changes.
      4. Deletes — last, so a failed delete doesn't orphan dependent state.

    Fail-fast semantics: on the first GhError from github_client, the
    exception propagates to the caller. No rollback; operations are
    idempotent, so re-running after fixing the cause picks up remaining work.

    `progress` is called with a one-line description BEFORE each operation.
    CLI layer passes click.echo; tests pass a no-op lambda or a list.append.
    """
    for rename in diff.renames:
        progress(f"~ {rename.old_name} → {rename.new_label.name}")
        github_client.update_label(repo, rename.old_name, rename.new_label)
    for create in diff.creates:
        progress(f"+ {create.label.name}")
        github_client.create_label(repo, create.label)
    for update in diff.updates:
        progress(f"≈ {update.label.name}")
        github_client.update_label(repo, update.label.name, update.label)
    for delete in diff.deletes:
        progress(f"- {delete.name}")
        github_client.delete_label(repo, delete.name)
