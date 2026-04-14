"""Tests for gh_manage.github_api.labels — Label dataclass + label CRUD.

Moved from tests/unit/github_client/test_github_client.py during the
Phase 5 checkpoint refactor. Codex flagged that the transport layer and
resource-specific helpers should live in separate modules, so label
tests follow the label helpers into github_api.labels.
"""

from __future__ import annotations

import json
from subprocess import CompletedProcess

import pytest
from pytest_mock import MockerFixture

from gh_manage.github_api.labels import (
    Label,
    create_label,
    delete_label,
    list_labels,
    update_label,
)
from gh_manage.github_client import GhAPIError


def _mock_gh_success(mocker: MockerFixture, stdout: str):
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=""),
    )


# Happy path — list_labels.
# NOTE: list_labels uses `gh api --paginate --jq '.[]'` which emits one
# JSON object per line (NDJSON). Tests mock stdout with newline-separated
# JSON objects, not a single JSON array.
def test_list_labels_parses_ndjson_response(mocker: MockerFixture) -> None:
    ndjson = (
        json.dumps({"name": "bug", "color": "d73a4a", "description": "Buggy"})
        + "\n"
        + json.dumps({"name": "feat", "color": "a2eeef", "description": None})
        + "\n"
    )
    _mock_gh_success(mocker, ndjson)
    result = list_labels("yakkuro/gh-manage")
    assert result == [
        Label(name="bug", color="d73a4a", description="Buggy"),
        Label(name="feat", color="a2eeef", description=""),
    ]


def test_list_labels_uses_paginate_and_jq_flags(mocker: MockerFixture) -> None:
    """list_labels must use `--paginate --jq '.[]'` to produce NDJSON.

    Plain `--paginate` emits multiple JSON documents concatenated which
    json.loads cannot parse for repos with >100 labels. `--jq '.[]'`
    makes gh emit one JSON object per line — safe to parse line-by-line.
    """
    mock_run = _mock_gh_success(mocker, "")
    list_labels("yakkuro/gh-manage")
    args = mock_run.call_args.args[0]
    assert "--paginate" in args
    assert "--jq" in args
    jq_idx = args.index("--jq")
    assert args[jq_idx + 1] == ".[]"


def test_list_labels_handles_empty_response(mocker: MockerFixture) -> None:
    """Empty stdout → empty list."""
    _mock_gh_success(mocker, "")
    result = list_labels("yakkuro/gh-manage")
    assert result == []


def test_list_labels_handles_multi_page_response(mocker: MockerFixture) -> None:
    """A multi-page response via --paginate --jq '.[]' outputs one JSON
    object per line. Repos with >100 labels (or any multi-page result)
    must parse correctly."""
    ndjson_lines = [
        json.dumps({"name": f"label{i}", "color": "000000", "description": ""})
        for i in range(250)  # simulates 3 pages × ~100 labels
    ]
    _mock_gh_success(mocker, "\n".join(ndjson_lines) + "\n")
    result = list_labels("yakkuro/big-repo")
    assert len(result) == 250
    assert result[0].name == "label0"
    assert result[249].name == "label249"


def test_list_labels_raises_gh_api_error_on_malformed_ndjson_line(
    mocker: MockerFixture,
) -> None:
    """If gh api produces a malformed line (API format change, truncated
    response), list_labels must raise GhAPIError, not propagate
    json.JSONDecodeError as a raw traceback."""
    ndjson = (
        json.dumps({"name": "bug", "color": "d73a4a", "description": ""})
        + "\n"
        + "{this is not valid json\n"
    )
    _mock_gh_success(mocker, ndjson)
    with pytest.raises(GhAPIError, match="Failed to parse label entry"):
        list_labels("yakkuro/gh-manage")


# Normalization
def test_list_labels_normalizes_color_to_lowercase(
    mocker: MockerFixture,
) -> None:
    _mock_gh_success(
        mocker,
        json.dumps({"name": "bug", "color": "D73A4A", "description": "x"}) + "\n",
    )
    result = list_labels("yakkuro/gh-manage")
    assert result[0].color == "d73a4a"


def test_list_labels_converts_null_description_to_empty_string(
    mocker: MockerFixture,
) -> None:
    _mock_gh_success(
        mocker,
        json.dumps({"name": "bug", "color": "d73a4a", "description": None}) + "\n",
    )
    result = list_labels("yakkuro/gh-manage")
    assert result[0].description == ""


# Happy path — create_label.
# NOTE: after the Phase 5 checkpoint refactor, create/update now send a
# JSON body via `gh api --input -` (stdin), not `-f key=value` fields.
# The body is captured as `call_args.kwargs["input"]` — a JSON string.
def test_create_label_sends_correct_body(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "")
    create_label(
        "yakkuro/gh-manage",
        Label(name="chore", color="e1e7eb", description="housekeeping"),
    )
    args = mock_run.call_args.args[0]
    assert "api" in args
    assert "repos/yakkuro/gh-manage/labels" in args
    assert "-X" in args
    assert "POST" in args
    assert "--input" in args
    assert "-" in args
    body = json.loads(mock_run.call_args.kwargs["input"])
    assert body == {
        "name": "chore",
        "color": "e1e7eb",
        "description": "housekeeping",
    }


# Happy path — update_label with rename
def test_update_label_with_rename_includes_new_name(
    mocker: MockerFixture,
) -> None:
    mock_run = _mock_gh_success(mocker, "")
    update_label(
        "yakkuro/gh-manage",
        current_name="bug",
        new_label=Label(name="fix", color="d73a4a", description="Bug fix"),
    )
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/labels/bug" in args
    assert "-X" in args
    assert "PATCH" in args
    assert "--input" in args
    body = json.loads(mock_run.call_args.kwargs["input"])
    assert body == {
        "new_name": "fix",
        "color": "d73a4a",
        "description": "Bug fix",
    }


# Happy path — update_label without rename
def test_update_label_without_rename_omits_new_name(
    mocker: MockerFixture,
) -> None:
    mock_run = _mock_gh_success(mocker, "")
    update_label(
        "yakkuro/gh-manage",
        current_name="fix",
        new_label=Label(name="fix", color="d73a4a", description="Updated desc"),
    )
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/labels/fix" in args
    assert "-X" in args
    assert "PATCH" in args
    body = json.loads(mock_run.call_args.kwargs["input"])
    assert "new_name" not in body
    assert body == {
        "color": "d73a4a",
        "description": "Updated desc",
    }


# Happy path — delete_label.
# DELETE has no body, so stdin_input is None (no `input=` in call_args).
def test_delete_label_calls_correct_endpoint(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "")
    delete_label("yakkuro/gh-manage", "bug")
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/labels/bug" in args
    assert "-X" in args
    assert "DELETE" in args
    assert "--input" not in args
    assert mock_run.call_args.kwargs.get("input") is None


# Issue #10 — pydantic-based NDJSON validation
def test_list_labels_missing_name_raises(mocker: MockerFixture) -> None:
    """Valid JSON with missing 'name' field should raise GhAPIError, not KeyError."""
    _mock_gh_success(mocker, '{"color": "ff0000", "description": "x"}\n')
    with pytest.raises(GhAPIError, match="malformed label item"):
        list_labels("yakkuro/gh-manage")


def test_list_labels_wrong_typed_color_raises(mocker: MockerFixture) -> None:
    """Valid JSON with wrong-typed 'color' (int instead of str) should raise GhAPIError."""
    _mock_gh_success(mocker, '{"name": "bug", "color": 12345, "description": "x"}\n')
    with pytest.raises(GhAPIError, match="malformed label item"):
        list_labels("yakkuro/gh-manage")


def test_list_labels_null_description_normalizes_to_empty(
    mocker: MockerFixture,
) -> None:
    """description=null (existing behavior) must still normalize to empty string."""
    _mock_gh_success(
        mocker, '{"name": "bug", "color": "ff0000", "description": null}\n'
    )
    result = list_labels("yakkuro/gh-manage")
    assert len(result) == 1
    assert result[0].name == "bug"
    assert result[0].color == "ff0000"
    assert result[0].description == ""


def test_list_labels_falsy_non_none_description_raises(mocker: MockerFixture) -> None:
    """description=0 (a non-None falsy value) must raise GhAPIError under hardening,
    not silently coerce to empty string. Old behavior used `item.get("description") or ""`
    which collapsed 0/false/empty/None all into ''. New behavior uses pydantic so wrong
    types raise. In practice GitHub never returns 0 for description, but the hardening
    catches API contract violations and broken test fixtures."""
    _mock_gh_success(mocker, '{"name": "bug", "color": "ff0000", "description": 0}\n')
    with pytest.raises(GhAPIError, match="malformed label item"):
        list_labels("yakkuro/gh-manage")
