# Phase 5 Checkpoint — Post-Merge Refactor

> Informed by Codex's architectural review (fresh-eyes refactor pass) of `main` @ `f921f06` after Phase 5 merged. See session transcript for the full 12-question review.

## Goal

Address the 3 `REFACTOR NOW` + 1 `REMOVE` findings from Codex's checkpoint review, before Phase 6 (init/apply) starts. No user-facing behavior change — pure internal refactor with existing 91 tests as safety net. No version bump, no release.

## Codex's findings (summarized)

### Most dangerous (refactor now)

- **`github_client.py` shape**: generic transport + `Label` + label CRUD all in one file. Phase 7's branch protection will add more resource helpers to the same file → responsibility mixing gets locked in. **Split** transport into `github_client.py` and move `Label` + label CRUD to `github_api/labels.py`.
- **`run_gh_api(fields: dict[str, str], paginate: bool)`**: false genericity. `fields` is labels-shaped (flat string values only) and can't express nested JSON payloads that Phase 7's branch protection needs. `paginate` is dead code — `list_labels` uses `run_gh` directly with `--jq '.[]'`. **Rewrite** `run_gh_api` to accept `body: dict[str, Any] | None` (encoded as JSON via `gh api --input -`) and **remove** the `paginate` argument.
- **`_parse_repo` in `commands/labels.py`**: will be duplicated by Phase 6 (apply), Phase 7 (protection), Phase 8 (drift). **Extract** to shared utility `src/gh_manage/repo_ref.py` with regex validation.

### Kept as-is (the good parts)

- `load_config` — honest genericity, Phase 6-8 will reuse
- `labels_sync` 3-layer Tier 2 — pure function core, future-proof
- `GhError` 6 subclasses — remediation-per-class is the right axis
- `LabelsDiff` / `apply_diff` pattern — no premature unification
- `LabelSpec.old_name` — labels-only affordance
- Error stderr classification — least-bad given `gh` CLI constraint
- 2-layer mock test strategy (Q4 B)

### Key quote

> 今回いちばん future-proof なのは `labels_sync` で、いちばん危ないのは supposedly generic な `github_client`。`load_config` は honest genericity ですが、`run_gh_api(fields, paginate)` は false genericity です。

## Refactor plan — 3 commits

### Commit 1: Extract `repo_ref` shared utility

**Files:**
- Create: `src/gh_manage/repo_ref.py`
- Create: `tests/unit/test_repo_ref.py`
- Modify: `src/gh_manage/commands/labels.py` (use `parse_repo` from `repo_ref`, remove `_parse_repo`)
- Modify: `tests/unit/cli/test_labels.py` (update import + test_parse_repo_normalization)

**New module** `src/gh_manage/repo_ref.py`:

```python
"""Shared repository reference parsing and normalization."""

from __future__ import annotations

import re


DEFAULT_OWNER = "yakkuro"

# GitHub repo name segment: alphanumeric + `_`, `.`, `-`, cannot start with
# `.` or `-`. Owner and repo both use the same rule.
_SEGMENT_RE = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_REPO_REF_RE = re.compile(rf"^{_SEGMENT_RE}(?:/{_SEGMENT_RE})?$")


class InvalidRepoRefError(ValueError):
    """Raised when a repo argument doesn't look like a valid owner/repo."""


def parse_repo(name: str) -> str:
    """Normalize a repo argument to `owner/repo` form.

    Accepts either:
      - Bare repo name (`gh-manage`) → prepended with `yakkuro/`
      - Fully-qualified `owner/repo` → passed through unchanged

    Validates that both segments match GitHub's repo name rules. Raises
    InvalidRepoRefError for malformed input.
    """
    if not name or not _REPO_REF_RE.match(name):
        raise InvalidRepoRefError(
            f"Invalid repo reference: {name!r}. "
            f"Expected `owner/repo` or bare name (e.g., `gh-manage` → `{DEFAULT_OWNER}/gh-manage`)."
        )
    if "/" in name:
        return name
    return f"{DEFAULT_OWNER}/{name}"
```

### Commit 2: Split `github_client.py` → `github_api/labels.py`

**Files:**
- Create: `src/gh_manage/github_api/__init__.py` (empty)
- Create: `src/gh_manage/github_api/labels.py` (moved `Label` + CRUD)
- Create: `tests/unit/github_api/__init__.py` (empty)
- Create: `tests/unit/github_api/test_labels.py` (moved label-specific tests)
- Modify: `src/gh_manage/github_client.py` (remove `Label`, label CRUD — transport only)
- Modify: `src/gh_manage/labels_sync.py` (update imports to `github_api.labels`)
- Modify: `src/gh_manage/commands/labels.py` (update imports to `github_api.labels`)
- Modify: `tests/unit/github_client/test_github_client.py` (remove label-specific tests)
- Modify: `tests/unit/labels_sync/test_labels_sync.py` (update monkey-patch paths)
- Modify: `tests/unit/cli/test_labels.py` (update monkey-patch paths)

`github_client.py` after commit 2 contains only:
- `GhError` + 6 subclasses
- `_raise_classified_error`
- `run_gh`
- `run_gh_api` (signature unchanged in this commit; signature rework happens in commit 3)

`github_api/labels.py` contains:
- `Label` frozen dataclass (moved)
- `list_labels` (moved, unchanged)
- `create_label` (moved)
- `update_label` (moved)
- `delete_label` (moved)

### Commit 3: Rewrite `run_gh_api` transport signature

**Files:**
- Modify: `src/gh_manage/github_client.py` — `run_gh_api` signature change
- Modify: `src/gh_manage/github_api/labels.py` — `create_label` / `update_label` use new `body` arg
- Modify: `tests/unit/github_client/test_github_client.py` — update transport tests
- Modify: `tests/unit/github_api/test_labels.py` — update CRUD tests for new argv shape

**New signature**:

```python
def run_gh_api(
    endpoint: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> Any:
    """Run `gh api <endpoint>` and return parsed JSON.

    If body is provided, it's encoded as JSON and piped to `gh api` via
    `--input -` (stdin). This handles nested payloads (arrays, dicts,
    null values) that the previous `fields: dict[str, str]` couldn't.
    """
```

**Argv construction**:
- GET: `gh api <endpoint>`
- POST/PATCH without body: `gh api <endpoint> -X POST`
- POST/PATCH with body: `gh api <endpoint> -X POST --input -` + JSON on stdin
- DELETE: `gh api <endpoint> -X DELETE`

**Subprocess change**: pass `input=json.dumps(body)` to `subprocess.run` when body is not None. Requires `text=True` on the subprocess call (already set).

**Removed**:
- `fields` parameter
- `paginate` parameter (was dead code — `list_labels` uses `run_gh` directly)

## Acceptance criteria

- [ ] All 91 tests continue to pass (possibly with minor updates to mock assertions). If tests need updates for new argv shape, the count stays the same or grows.
- [ ] `ruff check .` clean
- [ ] `ruff format --check .` clean
- [ ] `uv run --with "mypy==1.12.0" mypy src` clean
- [ ] `./gh-manage labels show gh-manage` still works
- [ ] `./gh-manage labels diff gh-manage` still shows `No diff.` exit 0
- [ ] No version bump (this is an internal refactor)
- [ ] No CHANGELOG entry (no user-facing change)
- [ ] 4-reviewer cross-agent review before merge
- [ ] Merge + delete branch (no tag, no release)

## Verification commands

```bash
# Gate
uv run ruff check .
uv run ruff format --check .
uv run --with "mypy==1.12.0" mypy src
uv run pytest -v

# Live CLI
./gh-manage labels show gh-manage
./gh-manage labels diff gh-manage
./gh-manage labels sync gh-manage    # dry-run
```

## References

- Codex review transcript: session log (2026-04-11)
- Phase 5 spec: `docs/specs/2026-04-11-phase-5-labels-sync-design.md`
- Phase 5 plan: `docs/plans/2026-04-11-phase-5-labels-sync.md`
- Main design: `docs/specs/2026-04-10-gh-manage-design.md`
