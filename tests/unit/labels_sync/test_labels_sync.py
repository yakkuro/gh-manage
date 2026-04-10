"""Tests for gh_manage.labels_sync — pure-function diff computation and apply."""

from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from gh_manage.github_client import GhAPIError, Label
from gh_manage.labels_sync import (
    LabelCreate,
    LabelDelete,
    LabelRename,
    LabelsDiff,
    LabelUpdate,
    apply_diff,
    compute_diff,
)
from gh_manage.models.labels import CategorySpec, LabelSpec, LabelsConfig


def _make_config(specs: list[LabelSpec]) -> LabelsConfig:
    """Build a LabelsConfig with one category containing the given specs."""
    return LabelsConfig(
        version=1,
        categories={
            "test": CategorySpec(description="test", labels=specs),
        },
    )


# compute_diff — happy paths
def test_empty_repo_with_new_labels_produces_creates_only() -> None:
    current: list[Label] = []
    desired = _make_config(
        [
            LabelSpec(name="bug", color="ff0000", description="broken"),
            LabelSpec(name="feat", color="00ff00", description="new"),
        ]
    )
    diff = compute_diff(current, desired)
    assert len(diff.creates) == 2
    assert len(diff.renames) == 0
    assert len(diff.updates) == 0
    assert len(diff.deletes) == 0


def test_matching_labels_produce_empty_diff() -> None:
    current = [Label(name="bug", color="d73a4a", description="broken")]
    desired = _make_config(
        [LabelSpec(name="bug", color="d73a4a", description="broken")]
    )
    diff = compute_diff(current, desired)
    assert diff.is_empty


def test_color_mismatch_produces_update() -> None:
    current = [Label(name="bug", color="d73a4a", description="broken")]
    desired = _make_config(
        [LabelSpec(name="bug", color="ff0000", description="broken")]
    )
    diff = compute_diff(current, desired)
    assert len(diff.updates) == 1
    assert diff.updates[0].label.color == "ff0000"


def test_description_mismatch_produces_update() -> None:
    current = [Label(name="bug", color="d73a4a", description="old")]
    desired = _make_config([LabelSpec(name="bug", color="d73a4a", description="new")])
    diff = compute_diff(current, desired)
    assert len(diff.updates) == 1


def test_uppercase_desired_color_matches_lowercase_current() -> None:
    """compute_diff must normalize spec.color via .lower() before comparing."""
    current = [Label(name="bug", color="d73a4a", description="x")]
    desired = _make_config([LabelSpec(name="bug", color="D73A4A", description="x")])
    diff = compute_diff(current, desired)
    assert diff.is_empty


def test_none_description_in_spec_matches_empty_description_in_current() -> None:
    """LabelSpec.description=None must equal Label.description=''."""
    current = [Label(name="bug", color="d73a4a", description="")]
    desired = _make_config([LabelSpec(name="bug", color="d73a4a", description=None)])
    diff = compute_diff(current, desired)
    assert diff.is_empty


# compute_diff — rename logic
def test_old_name_match_produces_rename_not_create() -> None:
    current = [Label(name="bug", color="d73a4a", description="broken")]
    desired = _make_config(
        [LabelSpec(name="fix", old_name="bug", color="d73a4a", description="Bug fix")]
    )
    diff = compute_diff(current, desired)
    assert len(diff.renames) == 1
    assert diff.renames[0].old_name == "bug"
    assert diff.renames[0].new_label.name == "fix"
    assert len(diff.creates) == 0


def test_rename_with_color_change_is_single_rename_not_update() -> None:
    """A rename that also changes color is ONE rename operation, not a
    separate rename + update. The PATCH request includes new_name, color,
    and description in one call."""
    current = [Label(name="bug", color="d73a4a", description="x")]
    desired = _make_config(
        [LabelSpec(name="fix", old_name="bug", color="ff0000", description="x")]
    )
    diff = compute_diff(current, desired)
    assert len(diff.renames) == 1
    assert diff.renames[0].new_label.color == "ff0000"
    assert len(diff.updates) == 0


def test_name_match_preferred_over_old_name_match() -> None:
    """If a spec's name already matches a current label, that takes
    precedence over the spec's old_name field. The old_name-referenced
    label stays unmatched (no rename)."""
    current = [
        Label(name="fix", color="d73a4a", description="fix"),
        Label(name="bug", color="ffffff", description="bug"),
    ]
    desired = _make_config(
        [LabelSpec(name="fix", old_name="bug", color="d73a4a", description="fix")]
    )
    diff = compute_diff(current, desired)
    assert len(diff.renames) == 0
    # "fix" matches; "bug" is unmatched but prune=False so no delete
    assert diff.is_empty


# compute_diff — prune logic
def test_prune_false_ignores_extra_labels() -> None:
    current = [
        Label(name="bug", color="d73a4a", description="x"),
        Label(name="old-label", color="ffffff", description="y"),
    ]
    desired = _make_config([LabelSpec(name="bug", color="d73a4a", description="x")])
    diff = compute_diff(current, desired, prune=False)
    assert len(diff.deletes) == 0


def test_prune_true_emits_deletes_for_extras() -> None:
    current = [
        Label(name="bug", color="d73a4a", description="x"),
        Label(name="old-label", color="ffffff", description="y"),
    ]
    desired = _make_config([LabelSpec(name="bug", color="d73a4a", description="x")])
    diff = compute_diff(current, desired, prune=True)
    assert len(diff.deletes) == 1
    assert diff.deletes[0].name == "old-label"


def test_prune_does_not_delete_label_consumed_by_rename() -> None:
    """Even with prune=True, a label that was consumed by a rename
    should NOT be emitted as a delete."""
    current = [Label(name="bug", color="d73a4a", description="x")]
    desired = _make_config(
        [LabelSpec(name="fix", old_name="bug", color="d73a4a", description="x")]
    )
    diff = compute_diff(current, desired, prune=True)
    assert len(diff.deletes) == 0
    assert len(diff.renames) == 1


# compute_diff — edge cases
def test_prune_false_with_unrelated_desired_no_deletes() -> None:
    """With prune=False, labels in current but not in desired (by name or
    old_name) are ignored — no delete emitted."""
    current = [Label(name="bug", color="d73a4a", description="x")]
    desired = _make_config([LabelSpec(name="other", color="ffffff", description="y")])
    diff = compute_diff(current, desired, prune=False)
    assert len(diff.deletes) == 0
    assert len(diff.creates) == 1


def test_prune_true_with_unrelated_desired_deletes_all_current() -> None:
    current = [
        Label(name="bug", color="d73a4a", description="x"),
        Label(name="feat", color="00ff00", description="y"),
    ]
    desired = _make_config([LabelSpec(name="other", color="ffffff", description="z")])
    diff = compute_diff(current, desired, prune=True)
    assert len(diff.deletes) == 2
    delete_names = {d.name for d in diff.deletes}
    assert delete_names == {"bug", "feat"}


# apply_diff — execution order
def test_apply_diff_calls_renames_before_creates(mocker: MockerFixture) -> None:
    call_order: list[str] = []

    mocker.patch(
        "gh_manage.github_client.update_label",
        side_effect=lambda *a, **k: call_order.append("update"),
    )
    mocker.patch(
        "gh_manage.github_client.create_label",
        side_effect=lambda *a, **k: call_order.append("create"),
    )
    mocker.patch("gh_manage.github_client.delete_label")

    diff = LabelsDiff(
        renames=(LabelRename(old_name="bug", new_label=Label("fix", "d73a4a", "x")),),
        creates=(LabelCreate(label=Label("chore", "e1e7eb", "y")),),
        updates=(),
        deletes=(),
    )
    apply_diff(diff, "yakkuro/gh-manage")
    assert call_order == ["update", "create"]


def test_apply_diff_calls_deletes_last(mocker: MockerFixture) -> None:
    call_order: list[str] = []
    mocker.patch(
        "gh_manage.github_client.create_label",
        side_effect=lambda *a, **k: call_order.append("create"),
    )
    mocker.patch(
        "gh_manage.github_client.update_label",
        side_effect=lambda *a, **k: call_order.append("update"),
    )
    mocker.patch(
        "gh_manage.github_client.delete_label",
        side_effect=lambda *a, **k: call_order.append("delete"),
    )

    diff = LabelsDiff(
        renames=(),
        creates=(LabelCreate(label=Label("chore", "e1e7eb", "x")),),
        updates=(LabelUpdate(label=Label("bug", "ff0000", "x")),),
        deletes=(LabelDelete(name="old"),),
    )
    apply_diff(diff, "yakkuro/gh-manage")
    assert call_order[-1] == "delete"


def test_apply_diff_fails_fast_on_first_error(mocker: MockerFixture) -> None:
    """When the rename step raises, subsequent create/update/delete must
    NOT be called."""

    def fail_update(*args, **kwargs):
        raise GhAPIError("simulated failure")

    mock_create = mocker.patch("gh_manage.github_client.create_label")
    mocker.patch("gh_manage.github_client.update_label", side_effect=fail_update)
    mocker.patch("gh_manage.github_client.delete_label")

    diff = LabelsDiff(
        renames=(LabelRename(old_name="bug", new_label=Label("fix", "d73a4a", "x")),),
        creates=(LabelCreate(label=Label("chore", "e1e7eb", "y")),),
        updates=(),
        deletes=(),
    )
    with pytest.raises(GhAPIError):
        apply_diff(diff, "yakkuro/gh-manage")
    mock_create.assert_not_called()


def test_apply_diff_progress_callback_invoked_in_order(
    mocker: MockerFixture,
) -> None:
    mocker.patch("gh_manage.github_client.update_label")
    mocker.patch("gh_manage.github_client.create_label")
    mocker.patch("gh_manage.github_client.delete_label")

    progress_calls: list[str] = []
    diff = LabelsDiff(
        renames=(LabelRename(old_name="bug", new_label=Label("fix", "d73a4a", "x")),),
        creates=(LabelCreate(label=Label("chore", "e1e7eb", "y")),),
        updates=(),
        deletes=(),
    )
    apply_diff(diff, "yakkuro/gh-manage", progress=progress_calls.append)
    assert len(progress_calls) == 2
    assert "bug" in progress_calls[0]
    assert "fix" in progress_calls[0]
    assert "chore" in progress_calls[1]


# LabelsDiff — properties
def test_labels_diff_is_empty_and_total_changes() -> None:
    empty = LabelsDiff(renames=(), creates=(), updates=(), deletes=())
    assert empty.is_empty
    assert empty.total_changes == 0

    nonempty = LabelsDiff(
        renames=(LabelRename(old_name="a", new_label=Label("b", "000000", "")),),
        creates=(LabelCreate(label=Label("c", "111111", "")),),
        updates=(),
        deletes=(),
    )
    assert not nonempty.is_empty
    assert nonempty.total_changes == 2
