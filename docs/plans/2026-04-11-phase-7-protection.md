# Phase 7 — `gh manage protection sync` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `gh manage protection sync` and `gh manage protection diff` for declarative branch protection management with transactional downgrade detection + pre-apply backup, and wire Phase 6 `init` / `apply --also-protection` to the real implementation.

**Architecture:** 3-layer pattern mirroring Phase 5/6 — `commands/{protection,init,apply}.py` (click) → `protection_sync.py` (pure-function engine: normalize + build_desired + compute_diff + detect_downgrade + apply_diff) → `models/branch_protection.py` (pydantic) + `github_api/protection.py` (Classic Branch Protection API wrapper — the first production consumer of Phase 5's `run_gh_api(body=dict)` stdin path).

**Tech Stack:** Python 3.12 + click 8 + pydantic v2 + PyYAML + pytest 8 + pytest-mock + hatchling. Reuses Phase 5/6 plumbing (`git_cli`, `labels_sync`, `profile_sync`, `github_client.run_gh_api`, `config.load_config`, `_handle_errors` decorator).

**Spec:** [`docs/specs/2026-04-11-phase-7-protection-design.md`](../specs/2026-04-11-phase-7-protection-design.md) — read it before starting any task.

---

## File Structure

### New source files

| Path | Responsibility | Created in task |
|---|---|---|
| `src/gh_manage/models/branch_protection.py` | Pydantic schema: `RequiredStatusChecks`, `RequiredPullRequestReviews`, `PolicySpec`, `BranchProtectionConfig` | Task 1 |
| `src/gh_manage/github_api/protection.py` | `get_branch_protection`, `put_branch_protection`, `delete_branch_protection` (Classic API wrapper) | Task 3 |
| `src/gh_manage/protection_sync.py` | Engine: dataclasses, error hierarchy, normalize, build_desired, compute_diff, detect_downgrade, apply_diff | Tasks 4-8 |
| `src/gh_manage/data/branch-protection.yml` | `solo-default` policy (MVP: 1 policy) | Task 9 |

### Modified source files

| Path | Change | Task |
|---|---|---|
| `src/gh_manage/models/profiles.py` | Add `protection_policy: str \| None` and `required_contexts: list[str]` fields | Task 2 |
| `src/gh_manage/data/profiles/python-service.yml` | Add `protection_policy: solo-default` and `required_contexts: []` | Task 9 |
| `src/gh_manage/commands/protection.py` | Replace stub with full implementation (sync + diff subcommands) | Task 10 |
| `src/gh_manage/commands/init.py` | Add protection auto-apply path (Q5 = X) | Task 11 |
| `src/gh_manage/commands/apply.py` | Wire `--also-protection` to real impl (replace stub error) | Task 12 |

### New test files

| Path | Purpose | Task |
|---|---|---|
| `tests/unit/models/test_branch_protection.py` | pydantic schema validation | Task 1 |
| `tests/unit/github_api/test_protection.py` | subprocess mock tests for get/put/delete_branch_protection | Task 3 |
| `tests/unit/protection_sync/__init__.py` | package marker | Task 4 |
| `tests/unit/protection_sync/test_protection_sync.py` | Data classes + apply_diff flow | Tasks 4, 7, 8 |
| `tests/unit/protection_sync/test_normalize.py` | normalize_protection_response edge cases | Task 5 |
| `tests/unit/protection_sync/test_downgrade.py` | 13 downgrade rules parametrized | Task 6 |
| `tests/unit/protection_sync/test_golden.py` | build_desired + apply roundtrip on fixture | Task 9 |
| `tests/unit/cli/test_protection.py` | `gh manage protection sync/diff` click tests | Task 10 |

### Modified test files

| Path | Change | Task |
|---|---|---|
| `tests/unit/models/test_profiles.py` | +3 cases for new ProfileSpec fields | Task 2 |
| `tests/unit/cli/test_init.py` | +4 cases for protection integration | Task 11 |
| `tests/unit/cli/test_apply.py` | Replace 1 stub test with 3 real `--also-protection` tests | Task 12 |

### New test fixtures

| Path | Content | Task |
|---|---|---|
| `tests/fixtures/protection/solo-default-policy.yml` | Minimal `branch-protection.yml` with solo-default | Task 4 |
| `tests/fixtures/protection/current-empty.json` | Empty dict `{}` (404 / no protection) | Task 7 |
| `tests/fixtures/protection/current-solo.json` | GitHub API response matching solo-default + empty contexts | Task 7 |

---

## Pre-flight checklist

```bash
cd /home/server160/repos/gh-manage
git status              # clean
git checkout main
git pull --ff-only
uv run pytest           # 189 pass baseline
uv run ruff check src/ tests/   # clean
uv run mypy src/        # pre-existing yaml stub note only
```

If any fails, **stop and report**. Then create the working branch:

```bash
git checkout -b feat/phase-7-protection
```

All Phase 7 tasks commit to this branch. The final PR opens `feat/phase-7-protection` → `main`.

---

## Task 1: `models/branch_protection.py` pydantic schema

**Goal:** Create the pydantic models for `branch-protection.yml`. No engine logic — just the type definitions + validators + tests.

**Files:**
- Create: `src/gh_manage/models/branch_protection.py`
- Create: `tests/unit/models/test_branch_protection.py`

- [ ] **Step 1.1: Write the failing tests**

Create `tests/unit/models/test_branch_protection.py`:

```python
"""Tests for gh_manage.models.branch_protection — PolicySpec + BranchProtectionConfig."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from gh_manage.models.branch_protection import (
    BranchProtectionConfig,
    PolicySpec,
    RequiredPullRequestReviews,
    RequiredStatusChecks,
)


# RequiredStatusChecks
def test_required_status_checks_minimal() -> None:
    s = RequiredStatusChecks(strict=True)
    assert s.strict is True
    assert s.contexts == []


def test_required_status_checks_with_contexts() -> None:
    s = RequiredStatusChecks(strict=False, contexts=["pr-gate / test"])
    assert s.strict is False
    assert s.contexts == ["pr-gate / test"]


def test_required_status_checks_rejects_extra() -> None:
    with pytest.raises(ValidationError):
        RequiredStatusChecks(strict=True, unknown_field="x")  # type: ignore[call-arg]


# RequiredPullRequestReviews
def test_required_pull_request_reviews_minimal() -> None:
    r = RequiredPullRequestReviews(required_approving_review_count=0)
    assert r.required_approving_review_count == 0
    assert r.dismiss_stale_reviews is False
    assert r.require_code_owner_reviews is False


def test_required_pull_request_reviews_rejects_negative_count() -> None:
    with pytest.raises(ValidationError):
        RequiredPullRequestReviews(required_approving_review_count=-1)


def test_required_pull_request_reviews_rejects_over_six() -> None:
    with pytest.raises(ValidationError):
        RequiredPullRequestReviews(required_approving_review_count=7)


# PolicySpec
def _minimal_policy_kwargs() -> dict:
    return dict(
        description="test",
        target_branches=["main"],
        required_status_checks=RequiredStatusChecks(strict=True),
        enforce_admins=False,
        required_pull_request_reviews=RequiredPullRequestReviews(
            required_approving_review_count=0
        ),
        required_conversation_resolution=True,
        required_linear_history=True,
        allow_force_pushes=False,
        allow_deletions=False,
    )


def test_policy_spec_minimal_valid() -> None:
    p = PolicySpec(**_minimal_policy_kwargs())
    assert p.description == "test"
    assert p.target_branches == ["main"]


def test_policy_spec_null_status_checks_is_valid() -> None:
    """docs-only-style policy with no status checks."""
    kwargs = _minimal_policy_kwargs()
    kwargs["required_status_checks"] = None
    p = PolicySpec(**kwargs)
    assert p.required_status_checks is None


def test_policy_spec_null_review_requirements_is_valid() -> None:
    kwargs = _minimal_policy_kwargs()
    kwargs["required_pull_request_reviews"] = None
    p = PolicySpec(**kwargs)
    assert p.required_pull_request_reviews is None


def test_policy_spec_rejects_empty_target_branches() -> None:
    kwargs = _minimal_policy_kwargs()
    kwargs["target_branches"] = []
    with pytest.raises(ValidationError, match="at least one branch"):
        PolicySpec(**kwargs)


def test_policy_spec_rejects_extra_field() -> None:
    kwargs = _minimal_policy_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        PolicySpec(**kwargs)


# BranchProtectionConfig
def test_branch_protection_config_minimal() -> None:
    policy = PolicySpec(**_minimal_policy_kwargs())
    config = BranchProtectionConfig(version=1, policies={"solo-default": policy})
    assert config.version == 1
    assert "solo-default" in config.policies


def test_branch_protection_config_multiple_policies() -> None:
    policy1 = PolicySpec(**_minimal_policy_kwargs())
    kwargs2 = _minimal_policy_kwargs()
    kwargs2["description"] = "second"
    policy2 = PolicySpec(**kwargs2)
    config = BranchProtectionConfig(
        version=1, policies={"a": policy1, "b": policy2}
    )
    assert len(config.policies) == 2


def test_branch_protection_config_rejects_unknown_version() -> None:
    policy = PolicySpec(**_minimal_policy_kwargs())
    with pytest.raises(ValidationError):
        BranchProtectionConfig(version=2, policies={"x": policy})  # type: ignore[arg-type]
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/models/test_branch_protection.py -v
```

Expected: collection error (`gh_manage.models.branch_protection` doesn't exist).

- [ ] **Step 1.3: Implement `models/branch_protection.py`**

Create `src/gh_manage/models/branch_protection.py`:

```python
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
```

- [ ] **Step 1.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/models/test_branch_protection.py -v
```

Expected: 13 passed.

- [ ] **Step 1.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green (189 + 13 = 202 tests).

- [ ] **Step 1.6: Commit**

```bash
git add src/gh_manage/models/branch_protection.py tests/unit/models/test_branch_protection.py
git commit -m "$(cat <<'EOF'
feat(phase-7): add BranchProtectionConfig pydantic schema

Three nested models for config/branch-protection.yml:
- RequiredStatusChecks (strict + contexts)
- RequiredPullRequestReviews (review count + flags, bounded 0-6)
- PolicySpec (full policy definition with nullable status checks and
  review requirements — supports docs-only-style policies)
- BranchProtectionConfig (top-level with version=Literal[1] and
  policies dict)

extra="forbid" on all models — unknown fields raise ValidationError,
which will help catch GitHub API additions we haven't yet modeled.

_target_branches_nonempty validator: empty list is meaningless (no
branches to protect) and is rejected at load time.

13 unit tests cover:
- Minimal valid instances for each class
- Validators (extra=forbid, bounded review count, empty target_branches)
- Null fields (required_status_checks=None, required_pull_request_reviews=None)
- BranchProtectionConfig with one or multiple policies
- Unknown version rejected

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Extend `models/profiles.py` with protection fields

**Goal:** Add `protection_policy: str | None` and `required_contexts: list[str]` to `ProfileSpec` so profiles can reference a policy + override its status checks.

**Files:**
- Modify: `src/gh_manage/models/profiles.py`
- Modify: `tests/unit/models/test_profiles.py`

- [ ] **Step 2.1: Append failing tests**

Append to `tests/unit/models/test_profiles.py`:

```python
# Phase 7 extension: protection_policy + required_contexts
def test_profile_spec_protection_policy_defaults_to_none() -> None:
    p = ProfileSpec(version=1, name="test", files=[])
    assert p.protection_policy is None


def test_profile_spec_protection_policy_set() -> None:
    p = ProfileSpec(
        version=1,
        name="test",
        files=[],
        protection_policy="solo-default",
    )
    assert p.protection_policy == "solo-default"


def test_profile_spec_required_contexts_defaults_to_empty_list() -> None:
    p = ProfileSpec(version=1, name="test", files=[])
    assert p.required_contexts == []


def test_profile_spec_required_contexts_set() -> None:
    p = ProfileSpec(
        version=1,
        name="test",
        files=[],
        required_contexts=["pr-gate / test", "ci-review / gitleaks"],
    )
    assert p.required_contexts == ["pr-gate / test", "ci-review / gitleaks"]
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/models/test_profiles.py -v
```

Expected: 4 new tests fail with `unexpected keyword argument 'protection_policy'` etc.

- [ ] **Step 2.3: Extend `ProfileSpec`**

In `src/gh_manage/models/profiles.py`, replace the `ProfileSpec` class with:

```python
class ProfileSpec(BaseModel):
    """A gh-manage profile."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    name: str
    description: str | None = None
    files: list[FileEntry]
    # Phase 7 additions:
    protection_policy: str | None = None
    required_contexts: list[str] = Field(default_factory=list)

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
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/models/test_profiles.py -v
```

Expected: 23 passed (19 existing + 4 new).

- [ ] **Step 2.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green (202 + 4 = 206 tests).

- [ ] **Step 2.6: Commit**

```bash
git add src/gh_manage/models/profiles.py tests/unit/models/test_profiles.py
git commit -m "$(cat <<'EOF'
feat(phase-7): extend ProfileSpec with protection_policy + required_contexts

Two new optional fields on ProfileSpec:
- protection_policy: str | None — name of a policy in branch-protection.yml.
  None means "this profile does not manage protection" (the init/apply
  protection path is skipped when None).
- required_contexts: list[str] — CI check names that completely replace
  the policy's contexts list (per the master spec's "Profile ↔ Branch
  Protection contract"). Default empty list.

Both fields are backward-compatible: existing profiles without them
still validate. extra="forbid" is preserved, so any other new field
would still raise.

4 new tests (202 → 206 total).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `github_api/protection.py` — GitHub API wrapper

**Goal:** Create the resource wrapper for GitHub's Classic Branch Protection API. Three functions: `get`, `put`, `delete`. Only `get` and `put` are used in Phase 7; `delete` is included for completeness.

**Files:**
- Create: `src/gh_manage/github_api/protection.py`
- Create: `tests/unit/github_api/test_protection.py`

- [ ] **Step 3.1: Write the failing tests**

Create `tests/unit/github_api/test_protection.py`:

```python
"""Tests for gh_manage.github_api.protection — Classic Branch Protection API wrapper.

Mirrors tests/unit/github_api/test_labels.py — subprocess.run is mocked
to return controlled CompletedProcess instances.
"""

from __future__ import annotations

import json
from subprocess import CompletedProcess

import pytest
from pytest_mock import MockerFixture

from gh_manage.github_api.protection import (
    delete_branch_protection,
    get_branch_protection,
    put_branch_protection,
)
from gh_manage.github_client import GhAPIError, GhNotFoundError


def _mock_gh_success(mocker: MockerFixture, stdout: str) -> object:
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=0, stdout=stdout, stderr=""
        ),
    )


def _mock_gh_failure(mocker: MockerFixture, stderr: str, returncode: int = 1) -> object:
    return mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr=stderr
        ),
    )


# get_branch_protection
def test_get_branch_protection_happy_path(mocker: MockerFixture) -> None:
    response = {
        "enforce_admins": {"enabled": False},
        "required_status_checks": {"strict": True, "contexts": []},
    }
    _mock_gh_success(mocker, json.dumps(response))
    result = get_branch_protection("yakkuro/gh-manage", "main")
    assert result == response


def test_get_branch_protection_default_branch_is_main(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "{}")
    get_branch_protection("yakkuro/gh-manage")
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/branches/main/protection" in args


def test_get_branch_protection_404_propagates_as_gh_not_found(
    mocker: MockerFixture,
) -> None:
    _mock_gh_failure(
        mocker, "HTTP 404: Not Found\nBranch not protected\n"
    )
    with pytest.raises(GhNotFoundError):
        get_branch_protection("yakkuro/gh-manage", "main")


def test_get_branch_protection_malformed_json_raises_gh_api_error(
    mocker: MockerFixture,
) -> None:
    _mock_gh_success(mocker, "{not valid json")
    with pytest.raises(GhAPIError):
        get_branch_protection("yakkuro/gh-manage", "main")


# put_branch_protection
def test_put_branch_protection_sends_body_via_stdin(mocker: MockerFixture) -> None:
    """LOAD-BEARING: the Phase 5 checkpoint refactor rewrote run_gh_api to
    send bodies via `gh api --input -` (stdin). Phase 7 is the first
    production caller of that path. This test guards the regression."""
    mock_run = _mock_gh_success(mocker, "{}")
    body = {
        "required_status_checks": {"strict": True, "contexts": ["pr-gate / test"]},
        "enforce_admins": False,
        "required_pull_request_reviews": None,
        "restrictions": None,
    }
    put_branch_protection("yakkuro/gh-manage", "main", body)

    args = mock_run.call_args.args[0]
    # Must use PUT method
    assert "-X" in args
    assert "PUT" in args
    # Must use --input - (stdin body) from Phase 5 checkpoint refactor
    assert "--input" in args
    assert "-" in args
    # Body sent via stdin, not -f key=value
    stdin_input = mock_run.call_args.kwargs["input"]
    assert json.loads(stdin_input) == body


def test_put_branch_protection_endpoint(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "{}")
    put_branch_protection("yakkuro/gh-manage", "main", {})
    args = mock_run.call_args.args[0]
    assert "repos/yakkuro/gh-manage/branches/main/protection" in args


# delete_branch_protection
def test_delete_branch_protection_calls_delete(mocker: MockerFixture) -> None:
    mock_run = _mock_gh_success(mocker, "")
    delete_branch_protection("yakkuro/gh-manage", "main")
    args = mock_run.call_args.args[0]
    assert "-X" in args
    assert "DELETE" in args
    assert "repos/yakkuro/gh-manage/branches/main/protection" in args
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/github_api/test_protection.py -v
```

Expected: collection error (module doesn't exist).

- [ ] **Step 3.3: Implement `github_api/protection.py`**

Create `src/gh_manage/github_api/protection.py`:

```python
"""GitHub Classic Branch Protection API helpers.

Mirrors gh_manage.github_api.labels: resource-specific wrapper around
gh_manage.github_client's generic transport. Classic API only; Rulesets
API is future work.

Phase 7 is the first production consumer of run_gh_api(body=dict) —
the Phase 5 checkpoint refactor rewrote that path to send JSON via
`gh api --input -` (stdin) specifically to handle nested bodies like
branch protection PUT without the `-f key=value` type-coercion traps.
"""

from __future__ import annotations

from typing import Any

from gh_manage.github_client import run_gh_api


def get_branch_protection(repo: str, branch: str = "main") -> dict[str, Any]:
    """GET /repos/{repo}/branches/{branch}/protection.

    Returns the raw JSON response (nested dict matching GitHub's wire
    shape). The caller is responsible for normalization via
    `protection_sync.normalize_protection_response`.

    Raises GhNotFoundError if the branch has no protection configured —
    the caller should catch it and treat as "empty dict" for diff
    computation.
    """
    result = run_gh_api(f"repos/{repo}/branches/{branch}/protection")
    if result is None:
        return {}
    assert isinstance(result, dict), (
        f"Expected dict response, got {type(result).__name__}"
    )
    return result


def put_branch_protection(
    repo: str, branch: str, body: dict[str, Any]
) -> None:
    """PUT /repos/{repo}/branches/{branch}/protection with the given body.

    Uses run_gh_api(body=...) which sends the JSON via `gh api --input -`
    (stdin). This avoids the `-f key=value` coercion traps — branch
    protection bodies contain nested objects (required_status_checks,
    required_pull_request_reviews) and booleans that string-coerce
    incorrectly.
    """
    run_gh_api(
        f"repos/{repo}/branches/{branch}/protection",
        method="PUT",
        body=body,
    )


def delete_branch_protection(repo: str, branch: str = "main") -> None:
    """DELETE /repos/{repo}/branches/{branch}/protection.

    Phase 7 does NOT call this in the normal flow — included for
    completeness and for Phase 7.5+ when a `gh manage protection unset`
    command may be added.
    """
    run_gh_api(
        f"repos/{repo}/branches/{branch}/protection",
        method="DELETE",
    )
```

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/github_api/test_protection.py -v
```

Expected: 7 passed.

- [ ] **Step 3.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green (206 + 7 = 213 tests).

- [ ] **Step 3.6: Commit**

```bash
git add src/gh_manage/github_api/protection.py tests/unit/github_api/test_protection.py
git commit -m "$(cat <<'EOF'
feat(phase-7): add github_api/protection.py Classic Branch Protection wrapper

Resource-specific wrapper mirroring gh_manage.github_api.labels. Three
functions:
- get_branch_protection — returns raw JSON dict for compute_diff to
  normalize via protection_sync.normalize_protection_response
- put_branch_protection — sends body via run_gh_api(body=dict) → gh
  api --input - (stdin), the Phase 5 checkpoint refactor path. This
  is the first production consumer of that path, so the regression
  test asserts --input - appears in argv and the body is passed
  via subprocess stdin (NOT via -f key=value which would corrupt
  nested objects and booleans).
- delete_branch_protection — included for Phase 7.5+ completeness

404 from get propagates as GhNotFoundError (caller catches to treat
as "empty" / "no protection").

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `protection_sync.py` data classes + error hierarchy + stubs

**Goal:** Create the engine module's contract types. No logic yet — just dataclasses, exception classes, stub functions. Mirrors Phase 6 Task 5.

**Files:**
- Create: `src/gh_manage/protection_sync.py`
- Create: `tests/unit/protection_sync/__init__.py`
- Create: `tests/unit/protection_sync/test_protection_sync.py`
- Create: `tests/fixtures/protection/solo-default-policy.yml`

- [ ] **Step 4.1: Create directories + fixture**

```bash
mkdir -p tests/unit/protection_sync tests/fixtures/protection
```

Create `tests/unit/protection_sync/__init__.py` (empty):

```python
```

Create `tests/fixtures/protection/solo-default-policy.yml`:

```yaml
version: 1
policies:
  solo-default:
    description: "Solo-dev default (no review requirement)"
    target_branches: ["main"]
    required_status_checks:
      strict: true
      contexts: []
    enforce_admins: false
    required_pull_request_reviews:
      required_approving_review_count: 0
      dismiss_stale_reviews: false
      require_code_owner_reviews: false
    required_conversation_resolution: true
    required_linear_history: true
    allow_force_pushes: false
    allow_deletions: false
```

- [ ] **Step 4.2: Write the failing tests**

Create `tests/unit/protection_sync/test_protection_sync.py`:

```python
"""Tests for gh_manage.protection_sync — pure-function engine."""

from __future__ import annotations

import pytest

from gh_manage.protection_sync import (
    DowngradeFinding,
    ProtectionApplyError,
    ProtectionBackupError,
    ProtectionDiff,
    ProtectionDowngradeError,
    ProtectionError,
    ProtectionFieldChange,
    ProtectionPolicyNotFoundError,
)


# Data classes
def test_protection_field_change_is_frozen() -> None:
    c = ProtectionFieldChange(
        field_path="enforce_admins",
        current_value=False,
        desired_value=True,
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        c.field_path = "other"  # type: ignore[misc]


def test_downgrade_finding_holds_all_fields() -> None:
    d = DowngradeFinding(
        field_path="enforce_admins",
        current_value=True,
        desired_value=False,
        reason="admin enforcement disabled",
    )
    assert d.field_path == "enforce_admins"
    assert d.reason == "admin enforcement disabled"


def test_protection_diff_is_empty_when_no_changes() -> None:
    diff = ProtectionDiff(
        changes=(),
        downgrades=(),
        current_raw={},
        desired_raw={},
    )
    assert diff.is_empty
    assert not diff.has_downgrades


def test_protection_diff_is_not_empty_when_has_changes() -> None:
    change = ProtectionFieldChange("x", False, True)
    diff = ProtectionDiff(
        changes=(change,),
        downgrades=(),
        current_raw={},
        desired_raw={},
    )
    assert not diff.is_empty


def test_protection_diff_has_downgrades_when_set() -> None:
    d = DowngradeFinding("x", True, False, "weakened")
    diff = ProtectionDiff(
        changes=(ProtectionFieldChange("x", True, False),),
        downgrades=(d,),
        current_raw={},
        desired_raw={},
    )
    assert diff.has_downgrades
    assert not diff.is_empty


# Error hierarchy
def test_all_errors_inherit_protection_error() -> None:
    assert issubclass(ProtectionPolicyNotFoundError, ProtectionError)
    assert issubclass(ProtectionDowngradeError, ProtectionError)
    assert issubclass(ProtectionBackupError, ProtectionError)
    assert issubclass(ProtectionApplyError, ProtectionError)


def test_protection_downgrade_error_message_lists_findings() -> None:
    d1 = DowngradeFinding("enforce_admins", True, False, "admin weakened")
    d2 = DowngradeFinding("allow_force_pushes", False, True, "force push allowed")
    err = ProtectionDowngradeError((d1, d2))
    msg = str(err)
    assert "2 protection field" in msg
    assert "enforce_admins" in msg
    assert "allow_force_pushes" in msg
    assert "--downgrade-allowed" in msg


def test_protection_downgrade_error_single_finding() -> None:
    d = DowngradeFinding("x", True, False, "weakened")
    err = ProtectionDowngradeError((d,))
    assert "1 protection field" in str(err)
```

- [ ] **Step 4.3: Run tests to verify they fail**

```bash
uv run pytest tests/unit/protection_sync/test_protection_sync.py -v
```

Expected: collection error (`gh_manage.protection_sync` doesn't exist).

- [ ] **Step 4.4: Create `protection_sync.py` with data classes + errors + stubs**

Create `src/gh_manage/protection_sync.py`:

```python
"""Pure-function engine for branch protection sync.

Mirrors gh_manage.profile_sync and gh_manage.labels_sync. Layered into
5 public functions called in order:

  1. normalize_protection_response(raw_api_response) -> canonical_current
  2. build_desired_protection(policy, profile) -> desired_body
  3. detect_downgrade(current, desired) -> tuple of DowngradeFinding
  4. compute_protection_diff(current, policy, profile, target_branch)
     -> ProtectionDiff (walks all 3 above)
  5. apply_protection_diff(diff, repo, target_branch, *, ...) -> None

Layer 1-3 are primitives; layer 4 composes them; layer 5 is the only
one that touches GitHub or filesystem (backup + PUT). Tasks 5-8
implement each layer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gh_manage.models.branch_protection import PolicySpec
from gh_manage.models.profiles import ProfileSpec


# Diff entry types
@dataclass(frozen=True)
class ProtectionFieldChange:
    """One field-level change detected between current and desired protection."""

    field_path: str
    current_value: Any
    desired_value: Any


@dataclass(frozen=True)
class DowngradeFinding:
    """A field change classified as weakening protection."""

    field_path: str
    current_value: Any
    desired_value: Any
    reason: str


@dataclass(frozen=True)
class ProtectionDiff:
    """Output of compute_protection_diff.

    changes: every field that differs (both upgrades and downgrades)
    downgrades: the subset that are weakening (downgrades ⊆ changes)
    current_raw: raw GitHub API response (for backup)
    desired_raw: PUT body (for apply)
    """

    changes: tuple[ProtectionFieldChange, ...]
    downgrades: tuple[DowngradeFinding, ...]
    current_raw: dict[str, Any]
    desired_raw: dict[str, Any]

    @property
    def is_empty(self) -> bool:
        return not self.changes

    @property
    def has_downgrades(self) -> bool:
        return bool(self.downgrades)


# Error hierarchy
class ProtectionError(Exception):
    """Base for protection_sync errors. Caught by commands/_handle_errors."""


class ProtectionPolicyNotFoundError(ProtectionError):
    """profile.protection_policy references a policy name not in
    branch-protection.yml. Message includes the list of available
    policies from the loaded config."""


class ProtectionDowngradeError(ProtectionError):
    """apply_protection_diff was called with diff.has_downgrades AND
    downgrade_allowed=False."""

    def __init__(self, downgrades: tuple[DowngradeFinding, ...]):
        self.downgrades = downgrades
        lines = "\n  ".join(
            f"{d.field_path}: {d.current_value} → {d.desired_value} ({d.reason})"
            for d in downgrades
        )
        super().__init__(
            f"{len(downgrades)} protection field(s) would be weakened:\n  {lines}\n"
            f"Re-run with --downgrade-allowed to override explicitly, or update "
            f"the profile/policy to preserve the current strength."
        )


class ProtectionBackupError(ProtectionError):
    """Failed to write the pre-apply backup. apply_protection_diff aborts
    BEFORE the PUT call — we refuse to modify protection without a
    restorable backup path."""


class ProtectionApplyError(ProtectionError):
    """The PUT to GitHub failed. Wraps the underlying GhError."""


# Stub engine functions — implementations land in Tasks 5-8
def normalize_protection_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize GitHub API response to canonical comparison shape.
    Implementation in Task 5."""
    raise NotImplementedError("Task 5")


def build_desired_protection(
    policy: PolicySpec, profile: ProfileSpec
) -> dict[str, Any]:
    """Combine a policy with a profile to produce the effective PUT body.
    Implementation in Task 7."""
    raise NotImplementedError("Task 7")


def detect_downgrade(
    current: dict[str, Any], desired: dict[str, Any]
) -> tuple[DowngradeFinding, ...]:
    """Check the 13 downgrade rules.
    Implementation in Task 6."""
    raise NotImplementedError("Task 6")


def compute_protection_diff(
    current: dict[str, Any],
    policy: PolicySpec,
    profile: ProfileSpec,
    target_branch: str = "main",
) -> ProtectionDiff:
    """Compute the diff between current protection and desired state.
    Implementation in Task 7."""
    raise NotImplementedError("Task 7")


def apply_protection_diff(
    diff: ProtectionDiff,
    repo: str,
    target_branch: str = "main",
    *,
    downgrade_allowed: bool = False,
    backup_dir: Path,
    progress: Callable[[str], None] = lambda _: None,
) -> None:
    """Apply the protection diff with safety guards.
    Implementation in Task 8."""
    raise NotImplementedError("Task 8")
```

- [ ] **Step 4.5: Run tests to verify they pass**

```bash
uv run pytest tests/unit/protection_sync/test_protection_sync.py -v
```

Expected: 9 passed.

- [ ] **Step 4.6: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green (213 + 9 = 222 tests).

- [ ] **Step 4.7: Commit**

```bash
git add src/gh_manage/protection_sync.py tests/unit/protection_sync/ tests/fixtures/protection/
git commit -m "$(cat <<'EOF'
feat(phase-7): add protection_sync data classes + error hierarchy + stubs

Contract types for the branch protection engine:
- ProtectionFieldChange (frozen dataclass): one field diff (current/desired)
- DowngradeFinding (frozen dataclass): a change classified as weakening
- ProtectionDiff (frozen dataclass): tuple of changes + downgrades +
  raw dicts, with is_empty + has_downgrades properties
- ProtectionError hierarchy (5 classes): ProtectionError base,
  ProtectionPolicyNotFoundError, ProtectionDowngradeError (with actionable
  message listing all findings), ProtectionBackupError, ProtectionApplyError

Stub functions raising NotImplementedError with task references:
- normalize_protection_response (Task 5)
- build_desired_protection (Task 7)
- detect_downgrade (Task 6)
- compute_protection_diff (Task 7)
- apply_protection_diff (Task 8)

Also adds tests/fixtures/protection/solo-default-policy.yml for the
downstream golden tests.

9 contract tests prove the data classes and error hierarchy are
correct before any engine logic is implemented.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `normalize_protection_response` — GitHub API quirks flattening

**Goal:** Implement the canonical-shape normalizer per spec-critique CRITICAL #2. GitHub's API returns wrapper objects (`enforce_admins: {enabled: bool, url: str}`) and sometimes omits falsy keys; downgrade detection needs a flat, consistent input.

**Files:**
- Modify: `src/gh_manage/protection_sync.py`
- Create: `tests/unit/protection_sync/test_normalize.py`

- [ ] **Step 5.1: Write the failing tests**

Create `tests/unit/protection_sync/test_normalize.py`:

```python
"""Tests for normalize_protection_response — canonical shape transformation."""

from __future__ import annotations

from gh_manage.protection_sync import normalize_protection_response


# Empty dict → all weakest defaults
def test_normalize_empty_dict() -> None:
    result = normalize_protection_response({})
    assert result == {
        "required_status_checks": None,
        "required_pull_request_reviews": None,
        "enforce_admins": False,
        "required_conversation_resolution": False,
        "required_linear_history": False,
        "allow_force_pushes": True,      # weakest
        "allow_deletions": True,         # weakest
    }


# enforce_admins wrapper unwrap
def test_normalize_enforce_admins_wrapper_enabled() -> None:
    raw = {"enforce_admins": {"enabled": True, "url": "https://api.github.com/..."}}
    result = normalize_protection_response(raw)
    assert result["enforce_admins"] is True


def test_normalize_enforce_admins_wrapper_disabled() -> None:
    raw = {"enforce_admins": {"enabled": False, "url": "https://api.github.com/..."}}
    result = normalize_protection_response(raw)
    assert result["enforce_admins"] is False


# allow_force_pushes / allow_deletions wrappers
def test_normalize_allow_force_pushes_wrapper() -> None:
    raw = {"allow_force_pushes": {"enabled": True}}
    result = normalize_protection_response(raw)
    assert result["allow_force_pushes"] is True


def test_normalize_allow_deletions_wrapper() -> None:
    raw = {"allow_deletions": {"enabled": False}}
    result = normalize_protection_response(raw)
    assert result["allow_deletions"] is False


def test_normalize_missing_allow_force_pushes_defaults_weakest() -> None:
    """Missing key means GitHub didn't include it — default to weakest
    state (force push allowed)."""
    raw = {"enforce_admins": {"enabled": True}}
    result = normalize_protection_response(raw)
    assert result["allow_force_pushes"] is True
    assert result["allow_deletions"] is True


# required_status_checks — drop extras
def test_normalize_required_status_checks_extracts_strict_and_contexts() -> None:
    raw = {
        "required_status_checks": {
            "strict": True,
            "contexts": ["pr-gate / test"],
            "checks": [{"context": "pr-gate / test", "app_id": -1}],  # extras dropped
        }
    }
    result = normalize_protection_response(raw)
    assert result["required_status_checks"] == {
        "strict": True,
        "contexts": ["pr-gate / test"],
    }


def test_normalize_required_status_checks_missing_becomes_none() -> None:
    raw = {"enforce_admins": {"enabled": False}}
    result = normalize_protection_response(raw)
    assert result["required_status_checks"] is None


# required_pull_request_reviews — drop extras
def test_normalize_review_requirements_extracts_3_fields() -> None:
    raw = {
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
            "required_review_thread_resolution": True,  # dropped
            "dismissal_restrictions": {},  # dropped
        }
    }
    result = normalize_protection_response(raw)
    assert result["required_pull_request_reviews"] == {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": False,
    }


def test_normalize_review_requirements_missing_becomes_none() -> None:
    raw = {"enforce_admins": {"enabled": False}}
    result = normalize_protection_response(raw)
    assert result["required_pull_request_reviews"] is None


# conversation resolution + linear history top-level booleans
def test_normalize_required_conversation_resolution_true() -> None:
    raw = {"required_conversation_resolution": {"enabled": True}}
    result = normalize_protection_response(raw)
    assert result["required_conversation_resolution"] is True


def test_normalize_required_linear_history_wrapper() -> None:
    raw = {"required_linear_history": {"enabled": True}}
    result = normalize_protection_response(raw)
    assert result["required_linear_history"] is True
```

- [ ] **Step 5.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/protection_sync/test_normalize.py -v
```

Expected: all fail with `NotImplementedError("Task 5")`.

- [ ] **Step 5.3: Implement `normalize_protection_response`**

Replace the stub in `src/gh_manage/protection_sync.py`:

```python
def normalize_protection_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a GitHub branch-protection API response into a canonical
    comparison shape. See Phase 7 design spec Section 'Engine' for the
    full rule set.

    Rules:
    1. Empty dict / missing top-level key → weakest default for each field
    2. `enforce_admins` → unwrap {enabled: bool}, default False
    3. `allow_force_pushes` / `allow_deletions` → unwrap {enabled: bool},
       default True (weakest — GitHub's unmanaged default)
    4. `required_status_checks` → extract `strict` + `contexts`, drop
       other fields; missing → None
    5. `required_pull_request_reviews` → extract the 3 fields we care
       about (count, dismiss_stale, code_owner); missing → None
    6. `required_conversation_resolution` / `required_linear_history` →
       unwrap {enabled: bool}, default False
    """

    def _unwrap_enabled(key: str, default: bool) -> bool:
        wrapper = raw.get(key)
        if wrapper is None:
            return default
        if isinstance(wrapper, dict):
            return bool(wrapper.get("enabled", default))
        if isinstance(wrapper, bool):
            return wrapper
        return default

    # required_status_checks
    rsc_raw = raw.get("required_status_checks")
    rsc: dict[str, Any] | None
    if rsc_raw is None:
        rsc = None
    else:
        rsc = {
            "strict": bool(rsc_raw.get("strict", False)),
            "contexts": list(rsc_raw.get("contexts", [])),
        }

    # required_pull_request_reviews
    rpr_raw = raw.get("required_pull_request_reviews")
    rpr: dict[str, Any] | None
    if rpr_raw is None:
        rpr = None
    else:
        rpr = {
            "required_approving_review_count": int(
                rpr_raw.get("required_approving_review_count", 0)
            ),
            "dismiss_stale_reviews": bool(rpr_raw.get("dismiss_stale_reviews", False)),
            "require_code_owner_reviews": bool(
                rpr_raw.get("require_code_owner_reviews", False)
            ),
        }

    return {
        "required_status_checks": rsc,
        "required_pull_request_reviews": rpr,
        "enforce_admins": _unwrap_enabled("enforce_admins", default=False),
        "required_conversation_resolution": _unwrap_enabled(
            "required_conversation_resolution", default=False
        ),
        "required_linear_history": _unwrap_enabled(
            "required_linear_history", default=False
        ),
        "allow_force_pushes": _unwrap_enabled("allow_force_pushes", default=True),
        "allow_deletions": _unwrap_enabled("allow_deletions", default=True),
    }
```

- [ ] **Step 5.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/protection_sync/test_normalize.py -v
```

Expected: 13 passed.

- [ ] **Step 5.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green (222 + 13 = 235 tests).

- [ ] **Step 5.6: Commit**

```bash
git add src/gh_manage/protection_sync.py tests/unit/protection_sync/test_normalize.py
git commit -m "$(cat <<'EOF'
feat(phase-7): implement normalize_protection_response

Canonical-shape flattening of GitHub's Classic Branch Protection API
response. Handles the API's quirks:
- Missing keys → weakest default (add-protection = upgrade, remove = downgrade)
- enforce_admins wrapper: {enabled: bool} → bool
- allow_force_pushes / allow_deletions wrappers: same shape, default True
  (weakest — GitHub's unmanaged default allows force push/delete)
- required_conversation_resolution / required_linear_history: {enabled: bool}
- required_status_checks: drop `checks` array (overlaps with `contexts`)
- required_pull_request_reviews: drop extras (thread resolution,
  dismissal_restrictions) — Phase 7 only tracks count + 2 bool flags

Pure function. 13 tests cover all the normalization rules.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `detect_downgrade` — 13 rules

**Goal:** Implement all 13 downgrade rules with parametrized tests for both downgrade and upgrade directions.

**Files:**
- Modify: `src/gh_manage/protection_sync.py`
- Create: `tests/unit/protection_sync/test_downgrade.py`

- [ ] **Step 6.1: Write the failing tests**

Create `tests/unit/protection_sync/test_downgrade.py`:

```python
"""Tests for detect_downgrade — all 13 downgrade rules.

Each rule has parametrize entries for both directions:
- "downgrade" case: current stronger, desired weaker → must detect
- "upgrade" case: current weaker, desired stronger → must NOT detect
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from gh_manage.protection_sync import detect_downgrade, normalize_protection_response


def _empty_canonical() -> dict[str, Any]:
    return normalize_protection_response({})


def _strong_canonical() -> dict[str, Any]:
    """A fully-armed canonical state that every rule can step down from."""
    return {
        "required_status_checks": {
            "strict": True,
            "contexts": ["pr-gate / test", "ci-review / gitleaks"],
        },
        "required_pull_request_reviews": {
            "required_approving_review_count": 2,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
        },
        "enforce_admins": True,
        "required_conversation_resolution": True,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


# Rule 1: required_approving_review_count decrease
def test_rule_1_review_count_decrease_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_pull_request_reviews"]["required_approving_review_count"] = 1
    findings = detect_downgrade(current, desired)
    assert len(findings) == 1
    assert "required_approving_review_count" in findings[0].field_path


def test_rule_1_review_count_increase_is_not_downgrade() -> None:
    current = _strong_canonical()
    current["required_pull_request_reviews"]["required_approving_review_count"] = 1
    desired = _strong_canonical()  # count=2
    assert detect_downgrade(current, desired) == ()


# Rule 2: dismiss_stale_reviews true → false
def test_rule_2_dismiss_stale_reviews_off_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_pull_request_reviews"]["dismiss_stale_reviews"] = False
    findings = detect_downgrade(current, desired)
    assert any("dismiss_stale_reviews" in f.field_path for f in findings)


def test_rule_2_dismiss_stale_reviews_on_is_not_downgrade() -> None:
    current = _strong_canonical()
    current["required_pull_request_reviews"]["dismiss_stale_reviews"] = False
    desired = _strong_canonical()
    assert detect_downgrade(current, desired) == ()


# Rule 3: require_code_owner_reviews true → false
def test_rule_3_code_owner_off_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_pull_request_reviews"]["require_code_owner_reviews"] = False
    findings = detect_downgrade(current, desired)
    assert any("require_code_owner_reviews" in f.field_path for f in findings)


# Rule 4: required_pull_request_reviews exist → null
def test_rule_4_reviews_wrapper_to_null_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_pull_request_reviews"] = None
    findings = detect_downgrade(current, desired)
    assert any(f.field_path == "required_pull_request_reviews" for f in findings)


def test_rule_4_null_to_wrapper_is_not_downgrade() -> None:
    current = _empty_canonical()  # reviews=None
    desired = _strong_canonical()
    findings = detect_downgrade(current, desired)
    # No downgrades — going from null to wrapper is an upgrade
    assert findings == ()


# Rule 5: enforce_admins true → false
def test_rule_5_enforce_admins_off_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["enforce_admins"] = False
    findings = detect_downgrade(current, desired)
    assert any("enforce_admins" in f.field_path for f in findings)


def test_rule_5_enforce_admins_on_is_not_downgrade() -> None:
    current = _empty_canonical()
    desired = _strong_canonical()
    # Empty → strong is pure upgrade
    assert detect_downgrade(current, desired) == ()


# Rule 6: required_status_checks.strict true → false
def test_rule_6_strict_off_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_status_checks"]["strict"] = False
    findings = detect_downgrade(current, desired)
    assert any("strict" in f.field_path for f in findings)


# Rule 7: contexts list shrinks (set difference)
def test_rule_7_context_removed_is_downgrade() -> None:
    current = _strong_canonical()  # ["pr-gate / test", "ci-review / gitleaks"]
    desired = deepcopy(current)
    desired["required_status_checks"]["contexts"] = ["pr-gate / test"]
    findings = detect_downgrade(current, desired)
    assert any("contexts" in f.field_path for f in findings)


def test_rule_7_context_added_is_not_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_status_checks"]["contexts"] = [
        "pr-gate / test",
        "ci-review / gitleaks",
        "extra / check",
    ]
    assert detect_downgrade(current, desired) == ()


def test_rule_7_same_contexts_is_not_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    assert detect_downgrade(current, desired) == ()


# Rule 8: required_status_checks exist → null
def test_rule_8_status_checks_to_null_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_status_checks"] = None
    findings = detect_downgrade(current, desired)
    assert any(f.field_path == "required_status_checks" for f in findings)


# Rule 9: required_conversation_resolution true → false
def test_rule_9_conversation_resolution_off_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_conversation_resolution"] = False
    findings = detect_downgrade(current, desired)
    assert any("required_conversation_resolution" in f.field_path for f in findings)


# Rule 10: required_linear_history true → false
def test_rule_10_linear_history_off_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["required_linear_history"] = False
    findings = detect_downgrade(current, desired)
    assert any("required_linear_history" in f.field_path for f in findings)


# Rule 11: allow_force_pushes false → true
def test_rule_11_force_pushes_allowed_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["allow_force_pushes"] = True
    findings = detect_downgrade(current, desired)
    assert any("allow_force_pushes" in f.field_path for f in findings)


def test_rule_11_force_pushes_disallowed_is_not_downgrade() -> None:
    current = _empty_canonical()  # allow_force_pushes=True
    desired = _strong_canonical()  # allow_force_pushes=False
    assert detect_downgrade(current, desired) == ()


# Rule 12: allow_deletions false → true
def test_rule_12_deletions_allowed_is_downgrade() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["allow_deletions"] = True
    findings = detect_downgrade(current, desired)
    assert any("allow_deletions" in f.field_path for f in findings)


# Sanity: empty → empty
def test_empty_to_empty_is_no_downgrade() -> None:
    assert detect_downgrade(_empty_canonical(), _empty_canonical()) == ()


# Sanity: matching strong states
def test_strong_to_strong_is_no_downgrade() -> None:
    assert detect_downgrade(_strong_canonical(), _strong_canonical()) == ()


# Multiple downgrades reported together
def test_multiple_downgrades_all_reported() -> None:
    current = _strong_canonical()
    desired = deepcopy(current)
    desired["enforce_admins"] = False
    desired["allow_force_pushes"] = True
    desired["allow_deletions"] = True
    findings = detect_downgrade(current, desired)
    paths = [f.field_path for f in findings]
    assert "enforce_admins" in paths
    assert "allow_force_pushes" in paths
    assert "allow_deletions" in paths
```

- [ ] **Step 6.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/protection_sync/test_downgrade.py -v
```

Expected: all fail with `NotImplementedError("Task 6")`.

- [ ] **Step 6.3: Implement `detect_downgrade`**

Replace the stub in `src/gh_manage/protection_sync.py`:

```python
def detect_downgrade(
    current: dict[str, Any], desired: dict[str, Any]
) -> tuple[DowngradeFinding, ...]:
    """Check the 13 downgrade rules. Both inputs MUST be canonical shape
    (output of normalize_protection_response). Raw GitHub API responses
    must not be passed directly.

    Returns empty tuple if desired is equal or stronger than current for
    every rule. Otherwise returns a DowngradeFinding per detected downgrade.
    """
    findings: list[DowngradeFinding] = []

    # Rule 4: required_pull_request_reviews exist → null (wrapper drop)
    curr_rpr = current.get("required_pull_request_reviews")
    desi_rpr = desired.get("required_pull_request_reviews")
    if curr_rpr is not None and desi_rpr is None:
        findings.append(
            DowngradeFinding(
                field_path="required_pull_request_reviews",
                current_value=curr_rpr,
                desired_value=None,
                reason="pull request review requirements removed entirely",
            )
        )
    # Rules 1, 2, 3 only apply when BOTH current and desired have the wrapper
    if curr_rpr is not None and desi_rpr is not None:
        # Rule 1: required_approving_review_count decrease
        cc = curr_rpr.get("required_approving_review_count", 0)
        dc = desi_rpr.get("required_approving_review_count", 0)
        if dc < cc:
            findings.append(
                DowngradeFinding(
                    field_path="required_pull_request_reviews.required_approving_review_count",
                    current_value=cc,
                    desired_value=dc,
                    reason=f"approving review count decreased {cc} → {dc}",
                )
            )
        # Rule 2: dismiss_stale_reviews true → false
        if curr_rpr.get("dismiss_stale_reviews") is True and desi_rpr.get(
            "dismiss_stale_reviews"
        ) is False:
            findings.append(
                DowngradeFinding(
                    field_path="required_pull_request_reviews.dismiss_stale_reviews",
                    current_value=True,
                    desired_value=False,
                    reason="stale review dismissal disabled",
                )
            )
        # Rule 3: require_code_owner_reviews true → false
        if curr_rpr.get("require_code_owner_reviews") is True and desi_rpr.get(
            "require_code_owner_reviews"
        ) is False:
            findings.append(
                DowngradeFinding(
                    field_path="required_pull_request_reviews.require_code_owner_reviews",
                    current_value=True,
                    desired_value=False,
                    reason="code owner review requirement disabled",
                )
            )

    # Rule 5: enforce_admins true → false
    if current.get("enforce_admins") is True and desired.get("enforce_admins") is False:
        findings.append(
            DowngradeFinding(
                field_path="enforce_admins",
                current_value=True,
                desired_value=False,
                reason="admin enforcement disabled",
            )
        )

    # Rule 8: required_status_checks exist → null
    curr_rsc = current.get("required_status_checks")
    desi_rsc = desired.get("required_status_checks")
    if curr_rsc is not None and desi_rsc is None:
        findings.append(
            DowngradeFinding(
                field_path="required_status_checks",
                current_value=curr_rsc,
                desired_value=None,
                reason="status check requirements removed entirely",
            )
        )
    # Rules 6, 7 only apply when BOTH current and desired have the wrapper
    if curr_rsc is not None and desi_rsc is not None:
        # Rule 6: strict true → false
        if curr_rsc.get("strict") is True and desi_rsc.get("strict") is False:
            findings.append(
                DowngradeFinding(
                    field_path="required_status_checks.strict",
                    current_value=True,
                    desired_value=False,
                    reason="strict update requirement disabled",
                )
            )
        # Rule 7: contexts set difference
        curr_contexts = set(curr_rsc.get("contexts", []))
        desi_contexts = set(desi_rsc.get("contexts", []))
        removed = curr_contexts - desi_contexts
        if removed:
            findings.append(
                DowngradeFinding(
                    field_path="required_status_checks.contexts",
                    current_value=sorted(curr_contexts),
                    desired_value=sorted(desi_contexts),
                    reason=f"required status checks removed: {sorted(removed)}",
                )
            )

    # Rule 9: required_conversation_resolution true → false
    if (
        current.get("required_conversation_resolution") is True
        and desired.get("required_conversation_resolution") is False
    ):
        findings.append(
            DowngradeFinding(
                field_path="required_conversation_resolution",
                current_value=True,
                desired_value=False,
                reason="conversation resolution requirement disabled",
            )
        )

    # Rule 10: required_linear_history true → false
    if (
        current.get("required_linear_history") is True
        and desired.get("required_linear_history") is False
    ):
        findings.append(
            DowngradeFinding(
                field_path="required_linear_history",
                current_value=True,
                desired_value=False,
                reason="linear history requirement disabled",
            )
        )

    # Rule 11: allow_force_pushes false → true
    if (
        current.get("allow_force_pushes") is False
        and desired.get("allow_force_pushes") is True
    ):
        findings.append(
            DowngradeFinding(
                field_path="allow_force_pushes",
                current_value=False,
                desired_value=True,
                reason="force push now allowed",
            )
        )

    # Rule 12: allow_deletions false → true
    if (
        current.get("allow_deletions") is False
        and desired.get("allow_deletions") is True
    ):
        findings.append(
            DowngradeFinding(
                field_path="allow_deletions",
                current_value=False,
                desired_value=True,
                reason="branch deletion now allowed",
            )
        )

    # Rule 13: target_branches is handled at a higher layer (the caller
    # applies the policy per-branch). Phase 7 MVP only handles "main", so
    # this rule is dormant but documented here for future phases.

    return tuple(findings)
```

- [ ] **Step 6.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/protection_sync/test_downgrade.py -v
```

Expected: 24 passed.

- [ ] **Step 6.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green (235 + 24 = 259 tests).

- [ ] **Step 6.6: Commit**

```bash
git add src/gh_manage/protection_sync.py tests/unit/protection_sync/test_downgrade.py
git commit -m "$(cat <<'EOF'
feat(phase-7): implement detect_downgrade with 12 active rules

12 of the 13 downgrade rules are active in Phase 7 (rule 13 on
target_branches is documented but dormant — the caller applies the
policy per-branch and Phase 7 MVP only handles 'main').

Rules 1-3 (review count decrease / dismiss_stale / code_owner off)
only fire when both current and desired have required_pull_request_reviews.
Rule 4 fires on wrapper removal.

Rules 6-7 (strict off / contexts shrunk) only fire when both current
and desired have required_status_checks.
Rule 8 fires on wrapper removal.
Rule 7 uses set difference — removing any context from the required
list is a downgrade, adding one is not.

Rules 5, 9, 10, 11, 12 are plain boolean transitions at the top level.

24 parametrized tests cover both downgrade and upgrade directions for
every rule, plus multi-rule interaction (multiple downgrades
reported together) and sanity cases (empty→empty, strong→strong).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `build_desired_protection` + `compute_protection_diff`

**Goal:** Combine policy + profile into the PUT body, then walk the field tree to produce a `ProtectionDiff`. Uses `normalize_protection_response` (Task 5) and `detect_downgrade` (Task 6).

**Files:**
- Modify: `src/gh_manage/protection_sync.py`
- Modify: `tests/unit/protection_sync/test_protection_sync.py`

- [ ] **Step 7.1: Append failing tests**

Append to `tests/unit/protection_sync/test_protection_sync.py`:

```python
from gh_manage.models.branch_protection import (
    BranchProtectionConfig,
    PolicySpec,
    RequiredPullRequestReviews,
    RequiredStatusChecks,
)
from gh_manage.models.profiles import FileEntry, ProfileSpec
from gh_manage.protection_sync import (
    build_desired_protection,
    compute_protection_diff,
)


def _make_policy(**overrides: Any) -> PolicySpec:
    defaults: dict[str, Any] = dict(
        description="test",
        target_branches=["main"],
        required_status_checks=RequiredStatusChecks(strict=True, contexts=[]),
        enforce_admins=False,
        required_pull_request_reviews=RequiredPullRequestReviews(
            required_approving_review_count=0
        ),
        required_conversation_resolution=True,
        required_linear_history=True,
        allow_force_pushes=False,
        allow_deletions=False,
    )
    defaults.update(overrides)
    return PolicySpec(**defaults)


def _make_profile(
    protection_policy: str | None = "solo-default",
    required_contexts: list[str] | None = None,
) -> ProfileSpec:
    return ProfileSpec(
        version=1,
        name="test",
        files=[],
        protection_policy=protection_policy,
        required_contexts=required_contexts or [],
    )


# build_desired_protection
def test_build_desired_uses_policy_fields() -> None:
    policy = _make_policy()
    profile = _make_profile(required_contexts=[])
    body = build_desired_protection(policy, profile)
    assert body["enforce_admins"] is False
    assert body["required_status_checks"]["strict"] is True
    assert body["required_linear_history"] is True


def test_build_desired_contexts_from_profile_override() -> None:
    """LOAD-BEARING: policy.contexts [] is overwritten by profile.required_contexts."""
    policy = _make_policy()
    profile = _make_profile(required_contexts=["pr-gate / test"])
    body = build_desired_protection(policy, profile)
    assert body["required_status_checks"]["contexts"] == ["pr-gate / test"]


def test_build_desired_empty_profile_contexts_means_empty_contexts() -> None:
    policy = _make_policy()
    profile = _make_profile(required_contexts=[])
    body = build_desired_protection(policy, profile)
    assert body["required_status_checks"]["contexts"] == []


def test_build_desired_policy_with_null_status_checks() -> None:
    """A policy with required_status_checks=None → body has null."""
    policy = _make_policy(required_status_checks=None)
    profile = _make_profile()
    body = build_desired_protection(policy, profile)
    assert body["required_status_checks"] is None


# compute_protection_diff
def test_compute_diff_empty_current_all_changes() -> None:
    policy = _make_policy()
    profile = _make_profile()
    diff = compute_protection_diff({}, policy, profile, "main")
    assert not diff.is_empty
    assert len(diff.changes) > 0
    assert not diff.has_downgrades


def test_compute_diff_matching_current_empty() -> None:
    policy = _make_policy()
    profile = _make_profile()
    # Build the current state to match what build_desired would produce
    desired = build_desired_protection(policy, profile)
    # Fake a GitHub API response shape matching the desired state
    current_raw = {
        "enforce_admins": {"enabled": desired["enforce_admins"]},
        "required_status_checks": {
            "strict": desired["required_status_checks"]["strict"],
            "contexts": desired["required_status_checks"]["contexts"],
        },
        "required_pull_request_reviews": desired["required_pull_request_reviews"],
        "required_conversation_resolution": {"enabled": True},
        "required_linear_history": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }
    diff = compute_protection_diff(current_raw, policy, profile, "main")
    assert diff.is_empty


def test_compute_diff_detects_downgrade() -> None:
    policy = _make_policy(enforce_admins=False)  # desired weaker
    profile = _make_profile()
    current_raw = {
        "enforce_admins": {"enabled": True},  # current stronger
    }
    diff = compute_protection_diff(current_raw, policy, profile, "main")
    assert diff.has_downgrades
    assert any("enforce_admins" in d.field_path for d in diff.downgrades)


def test_compute_diff_raw_dicts_preserved() -> None:
    policy = _make_policy()
    profile = _make_profile()
    current_raw = {"enforce_admins": {"enabled": True}}
    diff = compute_protection_diff(current_raw, policy, profile, "main")
    assert diff.current_raw == current_raw
    assert diff.desired_raw  # non-empty
```

- [ ] **Step 7.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/protection_sync/test_protection_sync.py -v
```

Expected: 8 new tests fail with `NotImplementedError("Task 7")`.

- [ ] **Step 7.3: Implement `build_desired_protection` and `compute_protection_diff`**

Replace the stubs in `src/gh_manage/protection_sync.py`:

```python
def build_desired_protection(
    policy: PolicySpec, profile: ProfileSpec
) -> dict[str, Any]:
    """Combine a policy with a profile to produce the effective PUT body.

    Implements the Phase 7 spec's Profile ↔ Branch Protection contract:
        effective.required_status_checks.contexts = profile.required_contexts
    (complete replacement — the policy's contexts: [] is always overwritten).

    All other fields come from the policy as-is. Returns a dict shaped
    for the GitHub PUT /branches/{branch}/protection API body.
    """
    if policy.required_status_checks is None:
        rsc: dict[str, Any] | None = None
    else:
        rsc = {
            "strict": policy.required_status_checks.strict,
            "contexts": list(profile.required_contexts),  # profile override
        }

    if policy.required_pull_request_reviews is None:
        rpr: dict[str, Any] | None = None
    else:
        rpr = {
            "required_approving_review_count": policy.required_pull_request_reviews.required_approving_review_count,
            "dismiss_stale_reviews": policy.required_pull_request_reviews.dismiss_stale_reviews,
            "require_code_owner_reviews": policy.required_pull_request_reviews.require_code_owner_reviews,
        }

    return {
        "required_status_checks": rsc,
        "enforce_admins": policy.enforce_admins,
        "required_pull_request_reviews": rpr,
        "required_conversation_resolution": policy.required_conversation_resolution,
        "required_linear_history": policy.required_linear_history,
        "allow_force_pushes": policy.allow_force_pushes,
        "allow_deletions": policy.allow_deletions,
        # restrictions is required by the API and means "no user/team restrictions"
        "restrictions": None,
    }


def compute_protection_diff(
    current: dict[str, Any],
    policy: PolicySpec,
    profile: ProfileSpec,
    target_branch: str = "main",
) -> ProtectionDiff:
    """Compute the diff between current protection and the desired state.

    Algorithm:
      1. normalized = normalize_protection_response(current)
      2. desired = build_desired_protection(policy, profile)
      3. Walk the field tree comparing normalized vs desired.
      4. Run detect_downgrade(normalized, desired) and emit DowngradeFinding
         for each weakening.
      5. Return ProtectionDiff containing changes + downgrades + raw dicts.

    Pure: no IO, no subprocess, no git, no GitHub API.
    """
    normalized = normalize_protection_response(current)
    desired = build_desired_protection(policy, profile)

    changes: list[ProtectionFieldChange] = []

    # Compare each field that both canonical shapes have
    for field in (
        "enforce_admins",
        "required_conversation_resolution",
        "required_linear_history",
        "allow_force_pushes",
        "allow_deletions",
    ):
        if normalized.get(field) != desired.get(field):
            changes.append(
                ProtectionFieldChange(
                    field_path=field,
                    current_value=normalized.get(field),
                    desired_value=desired.get(field),
                )
            )

    # required_status_checks (wrapper comparison)
    curr_rsc = normalized.get("required_status_checks")
    desi_rsc = desired.get("required_status_checks")
    if curr_rsc is None and desi_rsc is None:
        pass
    elif curr_rsc != desi_rsc:
        # Break down the nested diff for clearer output
        if (curr_rsc is None) != (desi_rsc is None):
            changes.append(
                ProtectionFieldChange(
                    field_path="required_status_checks",
                    current_value=curr_rsc,
                    desired_value=desi_rsc,
                )
            )
        else:
            assert curr_rsc is not None and desi_rsc is not None
            if curr_rsc.get("strict") != desi_rsc.get("strict"):
                changes.append(
                    ProtectionFieldChange(
                        field_path="required_status_checks.strict",
                        current_value=curr_rsc.get("strict"),
                        desired_value=desi_rsc.get("strict"),
                    )
                )
            if curr_rsc.get("contexts") != desi_rsc.get("contexts"):
                changes.append(
                    ProtectionFieldChange(
                        field_path="required_status_checks.contexts",
                        current_value=curr_rsc.get("contexts"),
                        desired_value=desi_rsc.get("contexts"),
                    )
                )

    # required_pull_request_reviews (wrapper comparison)
    curr_rpr = normalized.get("required_pull_request_reviews")
    desi_rpr = desired.get("required_pull_request_reviews")
    if curr_rpr is None and desi_rpr is None:
        pass
    elif curr_rpr != desi_rpr:
        if (curr_rpr is None) != (desi_rpr is None):
            changes.append(
                ProtectionFieldChange(
                    field_path="required_pull_request_reviews",
                    current_value=curr_rpr,
                    desired_value=desi_rpr,
                )
            )
        else:
            assert curr_rpr is not None and desi_rpr is not None
            for sub in (
                "required_approving_review_count",
                "dismiss_stale_reviews",
                "require_code_owner_reviews",
            ):
                if curr_rpr.get(sub) != desi_rpr.get(sub):
                    changes.append(
                        ProtectionFieldChange(
                            field_path=f"required_pull_request_reviews.{sub}",
                            current_value=curr_rpr.get(sub),
                            desired_value=desi_rpr.get(sub),
                        )
                    )

    downgrades = detect_downgrade(normalized, desired)

    return ProtectionDiff(
        changes=tuple(changes),
        downgrades=downgrades,
        current_raw=current,
        desired_raw=desired,
    )
```

- [ ] **Step 7.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/protection_sync/test_protection_sync.py -v
```

Expected: 17 passed (9 from Task 4 + 8 new).

- [ ] **Step 7.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green (259 + 8 = 267 tests).

- [ ] **Step 7.6: Commit**

```bash
git add src/gh_manage/protection_sync.py tests/unit/protection_sync/test_protection_sync.py
git commit -m "$(cat <<'EOF'
feat(phase-7): implement build_desired_protection + compute_protection_diff

build_desired_protection: composes a PUT body from a PolicySpec + a
ProfileSpec. Implements the master spec's Profile ↔ Branch Protection
contract where profile.required_contexts completely replaces the
policy's contexts: [] (contexts ALWAYS come from profile, never
from policy).

compute_protection_diff: orchestrates the full diff path.
  1. normalize_protection_response(current) → canonical shape
  2. build_desired_protection(policy, profile) → PUT body
  3. Walk 5 flat fields + required_status_checks wrapper + review
     wrapper, emitting one ProtectionFieldChange per divergence
  4. detect_downgrade(normalized, desired) → DowngradeFinding tuple
  5. Return ProtectionDiff with both current_raw and desired_raw
     preserved for the apply phase (backup needs current_raw, PUT
     needs desired_raw)

Nested wrappers are broken down when both sides have them (e.g.,
required_status_checks.contexts vs required_status_checks.strict get
separate ProtectionFieldChange entries). When one side is null and
the other is not, a wrapper-level change is emitted.

Pure function. Composes existing Tasks 5 + 6 primitives. 8 new tests.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `apply_protection_diff` — transactional apply with backup + PUT

**Goal:** The heart of Phase 7 — the write path. Conflict check → backup dir pre-flight → backup write with microsecond-unique filename → PUT → error propagation with backup retention.

**Files:**
- Modify: `src/gh_manage/protection_sync.py`
- Modify: `tests/unit/protection_sync/test_protection_sync.py`

- [ ] **Step 8.1: Append failing tests**

Append to `tests/unit/protection_sync/test_protection_sync.py`:

```python
import re

from pathlib import Path

from pytest_mock import MockerFixture


def _nonempty_diff(downgrades: tuple = ()) -> ProtectionDiff:
    """Build a ProtectionDiff with at least one change for apply_diff tests."""
    return ProtectionDiff(
        changes=(
            ProtectionFieldChange("enforce_admins", False, True),
        ),
        downgrades=downgrades,
        current_raw={"enforce_admins": {"enabled": False}},
        desired_raw={"enforce_admins": True, "restrictions": None},
    )


# Downgrade check — transactional
def test_apply_diff_downgrade_not_allowed_raises_before_io(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    from gh_manage.protection_sync import apply_protection_diff

    mock_put = mocker.patch(
        "gh_manage.github_api.protection.put_branch_protection"
    )
    diff = _nonempty_diff(
        downgrades=(DowngradeFinding("x", True, False, "weakened"),),
    )
    backup_dir = tmp_path / "backups"

    with pytest.raises(ProtectionDowngradeError):
        apply_protection_diff(
            diff,
            "yakkuro/gh-manage",
            "main",
            downgrade_allowed=False,
            backup_dir=backup_dir,
        )

    # No backup dir created, no PUT
    assert not backup_dir.exists()
    mock_put.assert_not_called()


def test_apply_diff_downgrade_allowed_proceeds(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    from gh_manage.protection_sync import apply_protection_diff

    mock_put = mocker.patch(
        "gh_manage.github_api.protection.put_branch_protection"
    )
    diff = _nonempty_diff(
        downgrades=(DowngradeFinding("x", True, False, "weakened"),),
    )
    backup_dir = tmp_path / "backups"

    apply_protection_diff(
        diff,
        "yakkuro/gh-manage",
        "main",
        downgrade_allowed=True,
        backup_dir=backup_dir,
    )

    # Backup created, PUT called
    assert backup_dir.exists()
    assert len(list(backup_dir.iterdir())) == 1
    mock_put.assert_called_once()


# Backup dir pre-flight
def test_apply_diff_backup_dir_is_file_raises_backup_error(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    from gh_manage.protection_sync import apply_protection_diff

    mock_put = mocker.patch(
        "gh_manage.github_api.protection.put_branch_protection"
    )
    # Create a regular file at the backup_dir path
    backup_file = tmp_path / "backups"
    backup_file.write_text("not a dir")

    diff = _nonempty_diff()
    with pytest.raises(ProtectionBackupError, match="not a directory"):
        apply_protection_diff(
            diff,
            "yakkuro/gh-manage",
            "main",
            backup_dir=backup_file,
        )
    mock_put.assert_not_called()


def test_apply_diff_backup_dir_created_automatically(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    from gh_manage.protection_sync import apply_protection_diff

    mocker.patch("gh_manage.github_api.protection.put_branch_protection")
    backup_dir = tmp_path / "nested" / "backups"
    assert not backup_dir.exists()

    diff = _nonempty_diff()
    apply_protection_diff(
        diff, "yakkuro/gh-manage", "main", backup_dir=backup_dir
    )

    assert backup_dir.is_dir()


# Backup filename uniqueness (spec-critique CRITICAL #1)
def test_apply_diff_backup_filename_includes_microseconds(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    from gh_manage.protection_sync import apply_protection_diff

    mocker.patch("gh_manage.github_api.protection.put_branch_protection")
    backup_dir = tmp_path / "backups"

    diff = _nonempty_diff()
    apply_protection_diff(
        diff, "yakkuro/gh-manage", "main", backup_dir=backup_dir
    )

    files = list(backup_dir.iterdir())
    assert len(files) == 1
    # Pattern: yakkuro-gh-manage-YYYYMMDDTHHMMSS-microseconds.yml
    assert re.match(
        r"^yakkuro-gh-manage-\d{8}T\d{6}-\d{6}\.yml$", files[0].name
    )


def test_apply_diff_two_calls_same_second_produce_distinct_backups(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Regression guard for spec-critique CRITICAL #1: backup filename
    must be unique across rapid retries within the same second."""
    from gh_manage.protection_sync import apply_protection_diff

    mocker.patch("gh_manage.github_api.protection.put_branch_protection")
    backup_dir = tmp_path / "backups"

    diff = _nonempty_diff()
    apply_protection_diff(
        diff, "yakkuro/gh-manage", "main", backup_dir=backup_dir
    )
    apply_protection_diff(
        diff, "yakkuro/gh-manage", "main", backup_dir=backup_dir
    )

    files = sorted(backup_dir.iterdir())
    # Both backups must exist; the second must NOT overwrite the first
    assert len(files) == 2
    assert files[0].name != files[1].name


# Backup content
def test_apply_diff_backup_contains_yaml_dump_of_current_raw(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    import yaml

    from gh_manage.protection_sync import apply_protection_diff

    mocker.patch("gh_manage.github_api.protection.put_branch_protection")
    backup_dir = tmp_path / "backups"

    current_raw = {
        "enforce_admins": {"enabled": True},
        "required_status_checks": {"strict": True, "contexts": ["x"]},
    }
    diff = ProtectionDiff(
        changes=(ProtectionFieldChange("enforce_admins", True, False),),
        downgrades=(),
        current_raw=current_raw,
        desired_raw={},
    )
    apply_protection_diff(
        diff, "yakkuro/gh-manage", "main", backup_dir=backup_dir
    )

    files = list(backup_dir.iterdir())
    assert len(files) == 1
    loaded = yaml.safe_load(files[0].read_text())
    assert loaded == current_raw


# Progress callback
def test_apply_diff_progress_callback_invoked_in_order(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    from gh_manage.protection_sync import apply_protection_diff

    mocker.patch("gh_manage.github_api.protection.put_branch_protection")
    backup_dir = tmp_path / "backups"

    progress_calls: list[str] = []
    diff = _nonempty_diff()
    apply_protection_diff(
        diff,
        "yakkuro/gh-manage",
        "main",
        backup_dir=backup_dir,
        progress=progress_calls.append,
    )

    assert len(progress_calls) == 2
    assert "backup" in progress_calls[0]
    assert "apply" in progress_calls[1]
```

- [ ] **Step 8.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/protection_sync/test_protection_sync.py -v -k apply_diff
```

Expected: new tests fail with `NotImplementedError("Task 8")`.

- [ ] **Step 8.3: Implement `apply_protection_diff`**

Replace the stub in `src/gh_manage/protection_sync.py` and add the required imports at the top:

First, update the imports section near the top of `src/gh_manage/protection_sync.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from gh_manage.github_api import protection as protection_api
from gh_manage.models.branch_protection import PolicySpec
from gh_manage.models.profiles import ProfileSpec
```

Then replace the `apply_protection_diff` stub with:

```python
def apply_protection_diff(
    diff: ProtectionDiff,
    repo: str,
    target_branch: str = "main",
    *,
    downgrade_allowed: bool = False,
    backup_dir: Path,
    progress: Callable[[str], None] = lambda _: None,
) -> None:
    """Apply the protection diff with transactional safety guards.

    Order of operations (LOAD-BEARING):
      1. If diff.has_downgrades AND not downgrade_allowed → raise
         ProtectionDowngradeError BEFORE any IO.
      2. Pre-flight check backup_dir: if exists but not a directory,
         raise ProtectionBackupError. Otherwise mkdir(parents, exist_ok).
      3. Compute microsecond-unique backup filename, write YAML dump
         of diff.current_raw. Failure → ProtectionBackupError, no PUT.
      4. PUT the desired body via github_api.protection.put_branch_protection.
      5. If PUT fails, propagate the GhError — backup remains on disk
         for manual restore via `gh api ... --input <backup-file>`.

    progress() is called twice: once before backup, once before PUT.
    """
    # Step 1: downgrade check (transactional, no IO)
    if diff.has_downgrades and not downgrade_allowed:
        raise ProtectionDowngradeError(diff.downgrades)

    # Step 2: backup dir pre-flight
    if backup_dir.exists() and not backup_dir.is_dir():
        raise ProtectionBackupError(
            f"Backup directory path exists but is not a directory: {backup_dir}. "
            f"Remove or rename the file at this path, then re-run."
        )
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ProtectionBackupError(
            f"Cannot create backup directory {backup_dir}: {e}. "
            f"Check filesystem permissions."
        ) from e

    # Step 3: backup write with microsecond-unique filename
    owner_slug, _, repo_slug = repo.partition("/")
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S-%f")  # %f = microseconds
    backup_filename = f"{owner_slug}-{repo_slug}-{timestamp}.yml"
    backup_path = backup_dir / backup_filename

    progress(f"backup → {backup_path}")
    try:
        backup_path.write_text(
            yaml.safe_dump(
                diff.current_raw,
                default_flow_style=False,
                sort_keys=True,
                allow_unicode=True,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError as e:
        raise ProtectionBackupError(
            f"Cannot write backup to {backup_path}: {e}. "
            f"Check disk space and write permissions on {backup_dir}."
        ) from e

    # Step 4: PUT — any failure propagates with backup preserved
    progress(f"apply → {repo}:{target_branch}")
    protection_api.put_branch_protection(repo, target_branch, diff.desired_raw)
```

- [ ] **Step 8.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/protection_sync/test_protection_sync.py -v
```

Expected: 25 passed (17 existing + 8 new for apply_diff).

- [ ] **Step 8.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green (267 + 8 = 275 tests).

- [ ] **Step 8.6: Commit**

```bash
git add src/gh_manage/protection_sync.py tests/unit/protection_sync/test_protection_sync.py
git commit -m "$(cat <<'EOF'
feat(phase-7): implement apply_protection_diff with transactional safety

The heart of Phase 7's write path. Four strictly-ordered steps:

1. Downgrade check: if diff.has_downgrades and not downgrade_allowed,
   raise ProtectionDowngradeError BEFORE any IO. Test asserts the
   backup directory is NOT created and put_branch_protection is NOT
   called when the guard fires.

2. Backup dir pre-flight (spec-critique HIGH #6): if backup_dir is an
   existing regular file instead of a directory, raise
   ProtectionBackupError with actionable message. Otherwise mkdir
   parents+exist_ok, catching OSError → ProtectionBackupError.

3. Backup write with microsecond-unique filename (spec-critique CRITICAL
   #1): datetime.now().strftime('%Y%m%dT%H%M%S-%f') → 6-digit
   microsecond suffix. Regression test proves two calls in the same
   second produce distinct files (NOT overwritten). YAML format per
   spec: safe_dump(sort_keys=True, allow_unicode=True, default_flow_style=False,
   indent=2). Backup write OSError → ProtectionBackupError, no PUT.

4. PUT via github_api.protection.put_branch_protection. Any GhError
   propagates, leaving the backup on disk for manual restore via
   `gh api ... --input <backup-file>`.

progress() fires twice: before backup (with path), before PUT (with
repo:branch). Tests assert order + content.

8 new tests (275 total) cover every branch of the state machine:
- downgrade blocked vs allowed
- backup_dir is file vs is nested nonexistent path
- backup filename format (regex assertion)
- two-calls-same-second uniqueness (regression guard)
- backup YAML content == yaml.safe_load(current_raw)
- progress callback order

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Production data + golden test

**Goal:** Ship the production `data/branch-protection.yml` (1 policy: solo-default) and update `python-service.yml` with `protection_policy` + `required_contexts`. Add a golden file test that runs `build_desired_protection` on real fixture data.

**Files:**
- Create: `src/gh_manage/data/branch-protection.yml`
- Modify: `src/gh_manage/data/profiles/python-service.yml`
- Create: `tests/unit/protection_sync/test_golden.py`

- [ ] **Step 9.1: Create `data/branch-protection.yml`**

```yaml
version: 1
policies:
  solo-default:
    description: "Solo-dev default (no review requirement)"
    target_branches: ["main"]
    required_status_checks:
      strict: true
      contexts: []
    enforce_admins: false
    required_pull_request_reviews:
      required_approving_review_count: 0
      dismiss_stale_reviews: false
      require_code_owner_reviews: false
    required_conversation_resolution: true
    required_linear_history: true
    allow_force_pushes: false
    allow_deletions: false
```

- [ ] **Step 9.2: Update `data/profiles/python-service.yml`**

```yaml
version: 1
name: python-service
description: "Python service repo (uv + ruff + mypy + pytest)"
files:
  - source: ci/python-ci.yml
    dest: .github/workflows/ci.yml
  - source: claude-md/default.md
    dest: CLAUDE.md
    skip_if_exists: true
protection_policy: solo-default
required_contexts: []
```

- [ ] **Step 9.3: Write the golden test**

Create `tests/unit/protection_sync/test_golden.py`:

```python
"""Golden file test for Phase 7: build_desired_protection + compute_protection_diff
roundtrip against production data (solo-default policy + python-service profile).
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from gh_manage.config import load_config
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.profiles import ProfileSpec
from gh_manage.protection_sync import (
    build_desired_protection,
    compute_protection_diff,
)


def test_production_data_loads() -> None:
    """branch-protection.yml and python-service.yml load without validation errors."""
    bp_path = Path(str(files("gh_manage.data") / "branch-protection.yml"))
    bp_config = load_config(bp_path, BranchProtectionConfig)
    assert "solo-default" in bp_config.policies

    profile_path = Path(
        str(files("gh_manage.data.profiles") / "python-service.yml")
    )
    profile = load_config(profile_path, ProfileSpec)
    assert profile.protection_policy == "solo-default"
    assert profile.required_contexts == []


def test_build_desired_on_production_solo_default_matches_expected() -> None:
    """build_desired_protection(solo-default, python-service) produces the
    canonical PUT body shape with contexts [] (empty list override)."""
    bp_path = Path(str(files("gh_manage.data") / "branch-protection.yml"))
    bp_config = load_config(bp_path, BranchProtectionConfig)
    profile_path = Path(
        str(files("gh_manage.data.profiles") / "python-service.yml")
    )
    profile = load_config(profile_path, ProfileSpec)

    body = build_desired_protection(bp_config.policies["solo-default"], profile)

    assert body == {
        "required_status_checks": {
            "strict": True,
            "contexts": [],  # profile.required_contexts override
        },
        "enforce_admins": False,
        "required_pull_request_reviews": {
            "required_approving_review_count": 0,
            "dismiss_stale_reviews": False,
            "require_code_owner_reviews": False,
        },
        "required_conversation_resolution": True,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "restrictions": None,
    }


def test_compute_diff_empty_current_vs_solo_default_profile() -> None:
    """A fresh repo with no protection → solo-default produces all changes,
    no downgrades."""
    bp_path = Path(str(files("gh_manage.data") / "branch-protection.yml"))
    bp_config = load_config(bp_path, BranchProtectionConfig)
    profile_path = Path(
        str(files("gh_manage.data.profiles") / "python-service.yml")
    )
    profile = load_config(profile_path, ProfileSpec)

    diff = compute_protection_diff(
        current={},
        policy=bp_config.policies["solo-default"],
        profile=profile,
        target_branch="main",
    )

    assert not diff.is_empty
    assert not diff.has_downgrades
    # All 5 flat fields + required_status_checks + required_pull_request_reviews
    field_paths = {c.field_path for c in diff.changes}
    assert "enforce_admins" in field_paths
    assert "required_conversation_resolution" in field_paths
    assert "required_linear_history" in field_paths
    # force_pushes/deletions: empty-canonical has both=True, desired has both=False
    # → these are changes (upgrades), NOT downgrades
    assert "allow_force_pushes" in field_paths
    assert "allow_deletions" in field_paths
```

- [ ] **Step 9.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/protection_sync/test_golden.py -v
```

Expected: 3 passed.

- [ ] **Step 9.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green (275 + 3 = 278 tests).

- [ ] **Step 9.6: Commit**

```bash
git add src/gh_manage/data/branch-protection.yml src/gh_manage/data/profiles/python-service.yml tests/unit/protection_sync/test_golden.py
git commit -m "$(cat <<'EOF'
feat(phase-7): ship solo-default policy + wire python-service profile

New production data files:
- src/gh_manage/data/branch-protection.yml — one policy (solo-default),
  matches the example in the master design spec. All fields explicit
  (strict=true, contexts=[], enforce_admins=false, review count=0,
  conversation resolution + linear history true, no force push or
  delete).

Modified:
- src/gh_manage/data/profiles/python-service.yml — adds
  protection_policy: solo-default and required_contexts: [].
  required_contexts is empty because the templates/ci/python-ci.yml
  workflow/job name is not yet stable; Phase 7.5+ will fill in actual
  check names once the CI templates settle.

3 golden tests verify:
1. Both production YAML files load without pydantic validation errors
2. build_desired_protection(solo-default, python-service) produces the
   exact expected PUT body (regression guard for the contract)
3. compute_protection_diff against empty current → all changes, no
   downgrades (the fresh-repo-bootstrap case)

278 tests total.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: `commands/protection.py` — sync + diff subcommands

**Goal:** Replace the Phase 7 stub in `commands/protection.py` with the full click implementation (sync + diff), including downgrade-allowed + TTY interactive confirm + backup dir resolution.

**Files:**
- Modify: `src/gh_manage/commands/protection.py`
- Create: `tests/unit/cli/test_protection.py`

- [ ] **Step 10.1: Write the failing tests**

Create `tests/unit/cli/test_protection.py`:

```python
"""Tests for `gh manage protection` click commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from pytest_mock import MockerFixture

from gh_manage.cli import main
from gh_manage.protection_sync import (
    DowngradeFinding,
    ProtectionDiff,
    ProtectionFieldChange,
)


def _empty_diff() -> ProtectionDiff:
    return ProtectionDiff(
        changes=(), downgrades=(), current_raw={}, desired_raw={}
    )


def _simple_diff() -> ProtectionDiff:
    return ProtectionDiff(
        changes=(ProtectionFieldChange("enforce_admins", False, True),),
        downgrades=(),
        current_raw={"enforce_admins": {"enabled": False}},
        desired_raw={"enforce_admins": True, "restrictions": None},
    )


def _downgrade_diff() -> ProtectionDiff:
    return ProtectionDiff(
        changes=(ProtectionFieldChange("enforce_admins", True, False),),
        downgrades=(
            DowngradeFinding("enforce_admins", True, False, "admin weakened"),
        ),
        current_raw={"enforce_admins": {"enabled": True}},
        desired_raw={"enforce_admins": False, "restrictions": None},
    )


def _patch_git(mocker: MockerFixture) -> None:
    mocker.patch(
        "gh_manage.commands.protection.git_cli.get_origin_owner_repo",
        return_value="yakkuro/gh-manage",
    )


def _patch_get_protection(
    mocker: MockerFixture, response: dict | None = None
) -> None:
    mocker.patch(
        "gh_manage.commands.protection.protection_api.get_branch_protection",
        return_value=response or {},
    )


# protection sync — happy paths
def test_sync_dry_run_default(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker)
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_simple_diff(),
    )
    mock_apply = mocker.patch(
        "gh_manage.commands.protection.protection_sync.apply_protection_diff"
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["protection", "sync", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Dry-run" in result.output
    mock_apply.assert_not_called()


def test_sync_apply_calls_apply_protection_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker)
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_simple_diff(),
    )
    mock_apply = mocker.patch(
        "gh_manage.commands.protection.protection_sync.apply_protection_diff"
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "sync",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    mock_apply.assert_called_once()


def test_sync_empty_diff_reports_no_changes(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker)
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_empty_diff(),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["protection", "sync", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "No changes" in result.output


def test_sync_apply_and_dry_run_conflict(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "sync",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
            "--dry-run",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 2  # UsageError


# Downgrade guardrails
def test_sync_downgrade_without_flag_stops(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker, {"enforce_admins": {"enabled": True}})
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_downgrade_diff(),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "sync",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "downgrade" in result.output.lower()
    assert "--downgrade-allowed" in result.output


def test_sync_downgrade_with_flag_and_yes_proceeds(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker, {"enforce_admins": {"enabled": True}})
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_downgrade_diff(),
    )
    mock_apply = mocker.patch(
        "gh_manage.commands.protection.protection_sync.apply_protection_diff"
    )
    # Simulate non-TTY stdin
    mocker.patch(
        "gh_manage.commands.protection._is_tty_stdin",
        return_value=False,
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "sync",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
            "--downgrade-allowed",
            "--yes",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    mock_apply.assert_called_once()


def test_sync_downgrade_non_tty_without_yes_stops(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker, {"enforce_admins": {"enabled": True}})
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_downgrade_diff(),
    )
    mocker.patch(
        "gh_manage.commands.protection._is_tty_stdin",
        return_value=False,
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "sync",
            str(tmp_path),
            "--profile",
            "python-service",
            "--apply",
            "--downgrade-allowed",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "non-tty" in result.output.lower() or "non-interactive" in result.output.lower()


# Profile validation errors
def test_sync_profile_without_protection_policy_stops(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    # Mock load_config to return a profile WITHOUT protection_policy
    from gh_manage.models.profiles import ProfileSpec

    def _fake_load_config(path, model_cls):
        if "profiles" in str(path):
            return ProfileSpec(version=1, name="test", files=[])  # no protection_policy
        return mocker.DEFAULT

    mocker.patch(
        "gh_manage.commands.protection.load_config",
        side_effect=_fake_load_config,
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["protection", "sync", str(tmp_path), "--profile", "test"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "protection_policy" in result.output


# diff subcommand
def test_diff_empty_exit_0(mocker: MockerFixture, tmp_path: Path) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker)
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_empty_diff(),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["protection", "diff", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
    assert "No changes" in result.output


def test_diff_downgrade_without_flag_exit_1(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker, {"enforce_admins": {"enabled": True}})
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_downgrade_diff(),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "diff",
            str(tmp_path),
            "--profile",
            "python-service",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1


def test_diff_downgrade_with_flag_exit_0(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_get_protection(mocker, {"enforce_admins": {"enabled": True}})
    mocker.patch(
        "gh_manage.commands.protection.protection_sync.compute_protection_diff",
        return_value=_downgrade_diff(),
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "protection",
            "diff",
            str(tmp_path),
            "--profile",
            "python-service",
            "--downgrade-allowed",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0
```

- [ ] **Step 10.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/cli/test_protection.py -v
```

Expected: multiple tests fail — the current stub just errors out immediately.

- [ ] **Step 10.3: Rewrite `commands/protection.py`**

Replace the entire content of `src/gh_manage/commands/protection.py`:

```python
"""`gh manage protection` — branch protection sync + diff commands."""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeVar

import click

from gh_manage import git_cli, protection_sync
from gh_manage.config import ConfigError, ConfigValidationError, load_config
from gh_manage.git_cli import GitError
from gh_manage.github_api import protection as protection_api
from gh_manage.github_client import GhError, GhNotFoundError
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.models.profiles import ProfileSpec
from gh_manage.protection_sync import (
    ProtectionDiff,
    ProtectionDowngradeError,
    ProtectionError,
    ProtectionPolicyNotFoundError,
)

_F = TypeVar("_F", bound=Callable[..., Any])


def _handle_errors(func: _F) -> _F:
    """Decorator: catch all domain errors and re-raise as ClickException."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (
            GhError,
            ConfigError,
            GitError,
            ProtectionError,
        ) as e:
            raise click.ClickException(str(e)) from e

    return wrapper  # type: ignore[return-value]


def _resolve_profile_path(name: str) -> Path:
    """Resolve a profile name to a package-data Path."""
    import re

    _VALID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    if not name or not _VALID.match(name):
        from gh_manage.config import ConfigFileNotFoundError

        raise ConfigFileNotFoundError(
            f"Invalid profile name: {name!r}. Profile names must be a single "
            f"identifier (alphanumeric plus `._-`, not starting with `.`)."
        )

    profiles_root = Path(str(files("gh_manage.data.profiles"))).resolve()
    candidate = (profiles_root / f"{name}.yml").resolve()
    if not candidate.is_relative_to(profiles_root):
        from gh_manage.config import ConfigFileNotFoundError

        raise ConfigFileNotFoundError(
            f"Profile path resolved outside bundled profiles directory: {name!r}"
        )
    if not candidate.is_file():
        from gh_manage.config import ConfigFileNotFoundError

        raise ConfigFileNotFoundError(
            f"Profile not found: {name!r}. Looked in {profiles_root}."
        )
    return candidate


def _resolve_branch_protection_path() -> Path:
    return Path(str(files("gh_manage.data") / "branch-protection.yml"))


def _resolve_backup_dir() -> Path:
    return Path.home() / ".gh-manage" / "backups"


def _is_tty_stdin() -> bool:
    """Check if stdin is a TTY. Extracted for test mocking."""
    return click.get_text_stream("stdin").isatty()


def _format_diff(diff: ProtectionDiff) -> str:
    lines: list[str] = ["Branch protection (main):"]
    if diff.is_empty:
        lines.append("  (no changes)")
        return "\n".join(lines)

    for change in diff.changes:
        classification = "(DOWNGRADE)" if any(
            d.field_path == change.field_path for d in diff.downgrades
        ) else "(upgrade)"
        lines.append(
            f"  {change.field_path}: {change.current_value} → "
            f"{change.desired_value}  {classification}"
        )

    if diff.has_downgrades:
        lines.append("")
        lines.append(f"Downgrades: {len(diff.downgrades)}")
        for d in diff.downgrades:
            lines.append(f"  {d.field_path}: {d.reason}")

    return "\n".join(lines)


def _load_profile_and_policy(
    profile_name: str,
) -> tuple[ProfileSpec, BranchProtectionConfig]:
    """Common precheck for protection subcommands.

    Loads the profile, validates protection_policy is set, loads the
    branch-protection config, validates the policy exists in it.
    Raises ConfigValidationError or ProtectionPolicyNotFoundError on
    mismatch.
    """
    profile_path = _resolve_profile_path(profile_name)
    profile = load_config(profile_path, ProfileSpec)
    if profile.name != profile_name:
        raise ConfigValidationError(
            f"Profile filename {profile_name!r} does not match its `name` "
            f"field {profile.name!r}."
        )
    if profile.protection_policy is None:
        raise ConfigValidationError(
            f"Profile {profile_name!r} has no protection_policy field. "
            f"Add `protection_policy: <name>` to the profile YAML and try again."
        )

    bp_config = load_config(
        _resolve_branch_protection_path(), BranchProtectionConfig
    )
    if profile.protection_policy not in bp_config.policies:
        raise ProtectionPolicyNotFoundError(
            f"Policy {profile.protection_policy!r} not found in "
            f"branch-protection.yml. Available policies: "
            f"{sorted(bp_config.policies.keys())}. Either fix the profile's "
            f"`protection_policy` field or add a new policy to "
            f"src/gh_manage/data/branch-protection.yml."
        )

    return profile, bp_config


@click.group("protection", help="Synchronize branch protection from profiles + policies.")
def protection() -> None:
    """Entry group for protection subcommands."""


@protection.command("sync")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
)
@click.option(
    "--profile",
    "profile_name",
    required=True,
    help="Profile name (resolves to bundled profiles/<name>.yml).",
)
@click.option("--dry-run", is_flag=True)
@click.option("--apply", "apply_flag", is_flag=True)
@click.option(
    "--downgrade-allowed",
    is_flag=True,
    help="Allow applying weaker protection (requires --yes in non-TTY).",
)
@click.option(
    "--yes",
    "yes_flag",
    is_flag=True,
    help="Skip interactive confirmation (required for non-TTY downgrade).",
)
@_handle_errors
def sync(
    path: Path,
    profile_name: str,
    dry_run: bool,
    apply_flag: bool,
    downgrade_allowed: bool,
    yes_flag: bool,
) -> None:
    """Apply profile + policy to a repo's branch protection.

    Default is dry-run; pass --apply to execute. Downgrades require
    --downgrade-allowed + --yes (or TTY interactive confirm).
    """
    if apply_flag and dry_run:
        raise click.UsageError("--apply and --dry-run are mutually exclusive.")

    target = path.resolve()
    owner_repo = git_cli.get_origin_owner_repo(target)

    profile, bp_config = _load_profile_and_policy(profile_name)
    policy = bp_config.policies[profile.protection_policy]  # type: ignore[index]

    try:
        current = protection_api.get_branch_protection(owner_repo, "main")
    except GhNotFoundError:
        current = {}  # no protection yet → treat as empty

    diff = protection_sync.compute_protection_diff(
        current, policy, profile, "main"
    )

    click.echo(_format_diff(diff))

    if diff.is_empty:
        click.echo("\nNo changes.")
        return

    if not apply_flag:
        # Dry-run: exit 1 if downgrade present without flag (for pre-commit hooks)
        suffix = f", {len(diff.downgrades)} downgrade(s)" if diff.has_downgrades else ""
        click.echo(
            f"\nDry-run: {len(diff.changes)} field change(s){suffix}. "
            f"Re-run with --apply to execute."
        )
        if diff.has_downgrades and not downgrade_allowed:
            sys.exit(1)
        return

    # --apply path
    if diff.has_downgrades and not downgrade_allowed:
        raise ProtectionDowngradeError(diff.downgrades)

    if diff.has_downgrades and downgrade_allowed:
        # Safety prompt / --yes gate
        if _is_tty_stdin():
            if not click.confirm(
                f"\nThis will weaken {len(diff.downgrades)} protection field(s). Continue?",
                default=False,
            ):
                click.echo("Aborted.")
                return
        elif not yes_flag:
            raise click.ClickException(
                "Non-TTY environment detected. Pass --yes to confirm the "
                "downgrade in CI/non-interactive contexts."
            )

    backup_dir = _resolve_backup_dir()
    click.echo("")
    protection_sync.apply_protection_diff(
        diff,
        owner_repo,
        "main",
        downgrade_allowed=downgrade_allowed,
        backup_dir=backup_dir,
        progress=click.echo,
    )
    click.echo(f"\nDone. Protection updated for {owner_repo}:main.")


@protection.command("diff")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
)
@click.option(
    "--profile",
    "profile_name",
    required=True,
    help="Profile name (resolves to bundled profiles/<name>.yml).",
)
@click.option(
    "--downgrade-allowed",
    is_flag=True,
    help="Suppress the exit-1 signal when downgrade is detected (for CI drift checks).",
)
@_handle_errors
def diff_cmd(path: Path, profile_name: str, downgrade_allowed: bool) -> None:
    """Show diff between current protection and profile + policy state.

    Exit codes (for git-pre-commit / CI drift checks):
      0 = no changes, or non-downgrade changes, or downgrade + --downgrade-allowed
      1 = downgrade detected and --downgrade-allowed not passed
    """
    target = path.resolve()
    owner_repo = git_cli.get_origin_owner_repo(target)

    profile, bp_config = _load_profile_and_policy(profile_name)
    policy = bp_config.policies[profile.protection_policy]  # type: ignore[index]

    try:
        current = protection_api.get_branch_protection(owner_repo, "main")
    except GhNotFoundError:
        current = {}

    diff = protection_sync.compute_protection_diff(
        current, policy, profile, "main"
    )

    click.echo(_format_diff(diff))

    if diff.is_empty:
        click.echo("\nNo changes.")
        return

    if diff.has_downgrades and not downgrade_allowed:
        sys.exit(1)
```

Also update `src/gh_manage/cli.py` to register the new `protection` group (it's currently imported as a stub `@click.command`). Find the import / registration block and change:

```python
from gh_manage.commands.protection import protection
...
main.add_command(protection)
```

(The existing import already points at `protection` — Phase 7 changes the export from a `@click.command` to a `@click.group`, and click handles both transparently, so the `cli.py` line should not need changes. If the existing file has `from gh_manage.commands.protection import protection as protection_cmd` with a rename, adjust accordingly.)

- [ ] **Step 10.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/cli/test_protection.py -v
```

Expected: 12 passed.

- [ ] **Step 10.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green (278 + 12 = 290 tests).

- [ ] **Step 10.6: Commit**

```bash
git add src/gh_manage/commands/protection.py tests/unit/cli/test_protection.py
git commit -m "$(cat <<'EOF'
feat(phase-7): implement gh manage protection sync + diff commands

Replaces the Phase 4 stub with two subcommands:

protection sync [<path>] --profile <name>
                        [--dry-run] [--apply]
                        [--downgrade-allowed] [--yes]

  Flow: git_cli.get_origin_owner_repo → load profile + policy →
  github_api.protection.get_branch_protection → compute_protection_diff
  → display → dry-run exit or apply.

  Apply path runs the downgrade guardrail:
  - has_downgrades AND not --downgrade-allowed → ProtectionDowngradeError
  - has_downgrades AND --downgrade-allowed AND TTY → click.confirm
    interactive prompt (default No)
  - has_downgrades AND --downgrade-allowed AND non-TTY → require --yes
    or raise "Non-TTY environment detected" ClickException

  Non-downgrade apply path: mkdir backup_dir, call apply_protection_diff
  which writes backup + PUTs body.

protection diff [<path>] --profile <name> [--downgrade-allowed]

  Read-only. Exit codes are designed for git-pre-commit / CI drift
  checks:
  - 0: no changes, or non-downgrade changes only, or downgrade +
       --downgrade-allowed (CI opt-in)
  - 1: downgrade detected without --downgrade-allowed

Shared helpers:
- _load_profile_and_policy: common precheck (filename/name invariant,
  protection_policy presence, policy exists in branch-protection.yml).
  ProtectionPolicyNotFoundError message includes the sorted list of
  available policies.
- _resolve_backup_dir: Path.home() / .gh-manage / backups
- _is_tty_stdin: click.get_text_stream("stdin").isatty(), extracted
  for test mocking
- _format_diff: renders ProtectionDiff with upgrade/DOWNGRADE
  classification per field

Errors caught by _handle_errors decorator:
(GhError, ConfigError, GitError, ProtectionError) — same tuple pattern
as Phase 6 init/apply, plus ProtectionError.

12 CLI tests cover happy paths, mutex, downgrade guardrails (with
TTY mocking), profile validation errors, diff exit codes.

290 tests total.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: `commands/init.py` — protection auto-apply integration

**Goal:** Phase 6 init currently applies files + labels. Phase 7 extends it to also apply protection when `profile.protection_policy` is set. No new CLI flags on init (per Q5 = X: init is full bootstrap, protection is automatic).

**Files:**
- Modify: `src/gh_manage/commands/init.py`
- Modify: `tests/unit/cli/test_init.py`

- [ ] **Step 11.1: Append failing tests**

Append to `tests/unit/cli/test_init.py`:

```python
from gh_manage.protection_sync import (
    DowngradeFinding,
    ProtectionDiff,
    ProtectionFieldChange,
)


def _empty_protection_diff() -> ProtectionDiff:
    return ProtectionDiff(
        changes=(), downgrades=(), current_raw={}, desired_raw={}
    )


def _nonempty_protection_diff(downgrades: tuple = ()) -> ProtectionDiff:
    return ProtectionDiff(
        changes=(ProtectionFieldChange("enforce_admins", False, True),),
        downgrades=downgrades,
        current_raw={},
        desired_raw={"enforce_admins": True, "restrictions": None},
    )


def _patch_protection(mocker: MockerFixture, diff: ProtectionDiff) -> None:
    mocker.patch(
        "gh_manage.commands.init.protection_api.get_branch_protection",
        return_value={},
    )
    mocker.patch(
        "gh_manage.commands.init.protection_sync.compute_protection_diff",
        return_value=diff,
    )


def test_init_applies_protection_when_profile_has_policy(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    _patch_protection(mocker, _nonempty_protection_diff())
    mocker.patch("gh_manage.commands.init.profile_sync.apply_files_diff")
    mock_protection_apply = mocker.patch(
        "gh_manage.commands.init.protection_sync.apply_protection_diff"
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service", "--apply"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    mock_protection_apply.assert_called_once()


def test_init_skips_protection_when_profile_has_none(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    mock_get_protection = mocker.patch(
        "gh_manage.commands.init.protection_api.get_branch_protection"
    )
    # Mock load_config so the profile has protection_policy=None
    from gh_manage.models.profiles import ProfileSpec
    from gh_manage.models.labels import LabelsConfig, CategorySpec

    def _fake_load_config(path, model_cls):
        if model_cls is ProfileSpec:
            return ProfileSpec(
                version=1,
                name="python-service",
                files=[],
                protection_policy=None,
            )
        if model_cls is LabelsConfig:
            return LabelsConfig(version=1, categories={"t": CategorySpec(description="t", labels=[])})
        return mocker.DEFAULT

    mocker.patch(
        "gh_manage.commands.init.load_config", side_effect=_fake_load_config
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    mock_get_protection.assert_not_called()


def test_init_protection_dry_run_prints_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    _patch_protection(mocker, _nonempty_protection_diff())

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Branch protection" in result.output or "enforce_admins" in result.output


def test_init_stops_on_protection_downgrade(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_labels(mocker)
    _patch_protection(
        mocker,
        _nonempty_protection_diff(
            downgrades=(
                DowngradeFinding("enforce_admins", True, False, "weakened"),
            ),
        ),
    )
    mocker.patch("gh_manage.commands.init.profile_sync.apply_files_diff")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service", "--apply"],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "downgrade" in result.output.lower()
    assert "protection sync" in result.output  # actionable redirect
```

- [ ] **Step 11.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/cli/test_init.py -v
```

Expected: 4 new tests fail (init doesn't know about protection yet).

- [ ] **Step 11.3: Modify `src/gh_manage/commands/init.py`**

Add the protection imports to the top of the file (after existing imports):

```python
from gh_manage import protection_sync
from gh_manage.github_api import protection as protection_api
from gh_manage.github_client import GhNotFoundError
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.protection_sync import ProtectionError
```

Update `_handle_errors` to include `ProtectionError` in the catch tuple:

```python
def _handle_errors(func: _F) -> _F:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (GhError, ConfigError, GitError, ProfileError, ProtectionError) as e:
            raise click.ClickException(str(e)) from e

    return wrapper  # type: ignore[return-value]
```

Add a helper after the existing `_resolve_*` functions:

```python
def _resolve_branch_protection_path() -> Path:
    return Path(str(files("gh_manage.data") / "branch-protection.yml"))


def _resolve_backup_dir() -> Path:
    return Path.home() / ".gh-manage" / "backups"
```

In the `init` function body, after the existing labels computation, add the protection computation. The modified flow section (after `labels_diff = labels_sync.compute_diff(...)` line) becomes:

```python
    # Labels: ALWAYS computed for init (Q1 design decision)
    labels_path = _resolve_default_labels_path()
    labels_config = load_config(labels_path, LabelsConfig)
    current_labels = labels_api.list_labels(owner_repo)
    labels_diff = labels_sync.compute_diff(current_labels, labels_config)

    # Protection: computed only when profile has a policy (Phase 7)
    protection_diff = None
    if profile.protection_policy is not None:
        bp_config = load_config(
            _resolve_branch_protection_path(), BranchProtectionConfig
        )
        if profile.protection_policy not in bp_config.policies:
            from gh_manage.protection_sync import ProtectionPolicyNotFoundError

            raise ProtectionPolicyNotFoundError(
                f"Policy {profile.protection_policy!r} not found in "
                f"branch-protection.yml. Available policies: "
                f"{sorted(bp_config.policies.keys())}."
            )
        policy = bp_config.policies[profile.protection_policy]
        try:
            current_protection = protection_api.get_branch_protection(
                owner_repo, "main"
            )
        except GhNotFoundError:
            current_protection = {}
        protection_diff = protection_sync.compute_protection_diff(
            current_protection, policy, profile, "main"
        )
```

Add the protection display after the existing label display:

```python
    # Print combined diff
    click.echo(_format_files_diff(files_diff))
    click.echo("")
    click.echo(f"Labels: {labels_diff.total_changes} change(s)")
    if not labels_diff.is_empty:
        for create in labels_diff.creates:
            click.echo(
                f"  + {create.label.name}  color={create.label.color}  "
                f"desc={create.label.description!r}"
            )
        for rename in labels_diff.renames:
            click.echo(f"  ~ {rename.old_name} → {rename.new_label.name}")
        for update in labels_diff.updates:
            click.echo(f"  ~ {update.label.name}  (color/desc update)")

    if protection_diff is not None:
        click.echo("")
        click.echo(f"Branch protection (main): {len(protection_diff.changes)} change(s)")
        for change in protection_diff.changes:
            click.echo(
                f"  {change.field_path}: {change.current_value} → {change.desired_value}"
            )
```

Update the dry-run message to include protection count:

```python
    if not apply_flag:
        n_protection = len(protection_diff.changes) if protection_diff else 0
        click.echo(
            f"\nDry-run: {len(files_diff.creates) + len(files_diff.overwrites)} "
            f"file changes, {labels_diff.total_changes} label changes, "
            f"{n_protection} protection changes. Re-run with --apply to execute."
        )
        return
```

Update the apply path to include protection apply (with downgrade guard):

```python
    # Apply
    click.echo("")
    profile_sync.apply_files_diff(
        files_diff, target, templates_root, force=force, progress=click.echo
    )
    labels_sync.apply_diff(labels_diff, owner_repo, progress=click.echo)

    if protection_diff is not None and not protection_diff.is_empty:
        if protection_diff.has_downgrades:
            from gh_manage.protection_sync import ProtectionDowngradeError

            raise click.ClickException(
                f"Protection downgrade detected during init. "
                f"init does not force-downgrade protection. "
                f"Run `gh manage protection sync {owner_repo} --profile "
                f"{profile_name} --downgrade-allowed --apply --yes` "
                f"explicitly to override, then re-run init."
            )
        backup_dir = _resolve_backup_dir()
        protection_sync.apply_protection_diff(
            protection_diff,
            owner_repo,
            "main",
            downgrade_allowed=False,
            backup_dir=backup_dir,
            progress=click.echo,
        )

    click.echo("\nDone. Next steps:")
    click.echo("  git status                # review what gh-manage placed")
    click.echo("  git add <gh-manage paths> # stage only the new files")
    click.echo("  git commit -m 'chore: bootstrap with gh-manage init'")
```

- [ ] **Step 11.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/cli/test_init.py -v
```

Expected: 19 passed (15 existing + 4 new).

- [ ] **Step 11.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green (290 + 4 = 294 tests).

- [ ] **Step 11.6: Commit**

```bash
git add src/gh_manage/commands/init.py tests/unit/cli/test_init.py
git commit -m "$(cat <<'EOF'
feat(phase-7): init auto-applies protection per master spec contract

Phase 6 init applied files + labels. Phase 7 extends it to also apply
protection when the profile has protection_policy set. Matches the
master design spec's init = full bootstrap (files ✅ + labels ✅ +
protection ✅).

New flow (additions are conditional on profile.protection_policy):
1. Load branch-protection.yml via package data
2. Validate profile.protection_policy exists in the config (available
   policies listed on error — regression guard from spec-critique HIGH #5)
3. get_branch_protection (404 → empty dict, treat as "no protection yet")
4. compute_protection_diff
5. Print protection diff alongside files + labels diff
6. Apply path:
   - If diff.has_downgrades → ClickException with actionable redirect
     to `gh manage protection sync <repo> --profile <name>
     --downgrade-allowed --apply --yes` (init is conservative; per
     Q5 = X it never force-downgrades)
   - Otherwise → apply_protection_diff with downgrade_allowed=False

init keeps NO --also-protection or --downgrade-allowed flag —
protection is automatic (Q5 = X from brainstorming). New repos
typically have no existing protection so the downgrade path rarely
fires; when it does, the user is explicitly redirected to the
protection command.

_handle_errors catch tuple extended to include ProtectionError.

4 new tests cover: auto-apply, skip when profile.protection_policy
is None, dry-run displays the protection diff, downgrade stops with
actionable redirect.

294 tests total.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: `commands/apply.py` — wire `--also-protection` to real impl

**Goal:** Replace the Phase 6 stub error (`raise ClickException("--also-protection is not yet implemented (scheduled for Phase 7)...")`) with the real integration. Apply is conservative — same downgrade redirect as init.

**Files:**
- Modify: `src/gh_manage/commands/apply.py`
- Modify: `tests/unit/cli/test_apply.py`

- [ ] **Step 12.1: Remove the existing stub test + add new tests**

Remove the existing `test_apply_also_protection_errors_out_with_phase_7_message` from `tests/unit/cli/test_apply.py`.

Then append:

```python
from gh_manage.protection_sync import (
    DowngradeFinding,
    ProtectionDiff,
    ProtectionFieldChange,
)


def _nonempty_protection_diff(downgrades: tuple = ()) -> ProtectionDiff:
    return ProtectionDiff(
        changes=(ProtectionFieldChange("enforce_admins", False, True),),
        downgrades=downgrades,
        current_raw={},
        desired_raw={"enforce_admins": True, "restrictions": None},
    )


def _patch_protection_for_apply(
    mocker: MockerFixture, diff: ProtectionDiff
) -> None:
    mocker.patch(
        "gh_manage.commands.apply.protection_api.get_branch_protection",
        return_value={},
    )
    mocker.patch(
        "gh_manage.commands.apply.protection_sync.compute_protection_diff",
        return_value=diff,
    )


def test_apply_also_protection_dry_run_displays_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_protection_for_apply(mocker, _nonempty_protection_diff())

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--also-protection",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    assert "Branch protection" in result.output or "enforce_admins" in result.output


def test_apply_also_protection_apply_calls_apply_diff(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_protection_for_apply(mocker, _nonempty_protection_diff())
    mocker.patch("gh_manage.commands.apply.profile_sync.apply_files_diff")
    mock_protection_apply = mocker.patch(
        "gh_manage.commands.apply.protection_sync.apply_protection_diff"
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--also-protection",
            "--apply",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 0, result.output
    mock_protection_apply.assert_called_once()


def test_apply_also_protection_downgrade_redirects_to_protection_sync(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    _patch_git(mocker)
    _patch_protection_for_apply(
        mocker,
        _nonempty_protection_diff(
            downgrades=(
                DowngradeFinding("enforce_admins", True, False, "weakened"),
            ),
        ),
    )
    mocker.patch("gh_manage.commands.apply.profile_sync.apply_files_diff")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--also-protection",
            "--apply",
        ],
        prog_name="gh-manage",
    )
    assert result.exit_code == 1
    assert "downgrade" in result.output.lower()
    assert "protection sync" in result.output
```

- [ ] **Step 12.2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/cli/test_apply.py -v
```

Expected: 3 new tests fail (the stub test was removed, the new tests need real impl).

- [ ] **Step 12.3: Modify `src/gh_manage/commands/apply.py`**

Add the protection imports at the top:

```python
from gh_manage import protection_sync
from gh_manage.github_api import protection as protection_api
from gh_manage.github_client import GhNotFoundError
from gh_manage.models.branch_protection import BranchProtectionConfig
from gh_manage.protection_sync import ProtectionError
```

Update `_handle_errors` catch tuple:

```python
except (GhError, ConfigError, GitError, ProfileError, ProtectionError) as e:
```

Add the same helper functions at the top of the file:

```python
def _resolve_branch_protection_path() -> Path:
    return Path(str(files("gh_manage.data") / "branch-protection.yml"))


def _resolve_backup_dir() -> Path:
    return Path.home() / ".gh-manage" / "backups"
```

Replace the `--also-protection` stub error block with real integration:

```python
    if also_protection:
        if profile.protection_policy is None:
            raise click.ClickException(
                f"Profile {profile_name!r} has no `protection_policy` field — "
                f"`--also-protection` has nothing to apply. Use a profile that "
                f"sets `protection_policy` or drop the `--also-protection` flag."
            )
        bp_config = load_config(
            _resolve_branch_protection_path(), BranchProtectionConfig
        )
        if profile.protection_policy not in bp_config.policies:
            from gh_manage.protection_sync import ProtectionPolicyNotFoundError

            raise ProtectionPolicyNotFoundError(
                f"Policy {profile.protection_policy!r} not found in "
                f"branch-protection.yml. Available policies: "
                f"{sorted(bp_config.policies.keys())}."
            )
        policy = bp_config.policies[profile.protection_policy]
        try:
            current_protection = protection_api.get_branch_protection(
                owner_repo, "main"
            )
        except GhNotFoundError:
            current_protection = {}
        protection_diff = protection_sync.compute_protection_diff(
            current_protection, policy, profile, "main"
        )
    else:
        protection_diff = None
```

Add protection diff display to the existing print block (after labels):

```python
    # Print combined diff
    click.echo(_format_files_diff(files_diff))
    if labels_diff is not None:
        click.echo("")
        click.echo(f"Labels: {labels_diff.total_changes} change(s)")
    if protection_diff is not None:
        click.echo("")
        click.echo(f"Branch protection (main): {len(protection_diff.changes)} change(s)")
        for change in protection_diff.changes:
            click.echo(
                f"  {change.field_path}: {change.current_value} → {change.desired_value}"
            )
```

Update the dry-run exit message:

```python
    n_file_changes = len(files_diff.creates) + len(files_diff.overwrites)
    n_label_changes = labels_diff.total_changes if labels_diff is not None else 0
    n_protection_changes = (
        len(protection_diff.changes) if protection_diff is not None else 0
    )

    if not apply_flag:
        click.echo(
            f"\nDry-run: {n_file_changes} file changes, "
            f"{n_label_changes} label changes, "
            f"{n_protection_changes} protection changes. "
            f"Re-run with --apply to execute."
        )
        return
```

Update the apply path:

```python
    # Apply
    click.echo("")
    profile_sync.apply_files_diff(
        files_diff, target, templates_root, force=force, progress=click.echo
    )
    if labels_diff is not None:
        labels_sync.apply_diff(labels_diff, owner_repo, progress=click.echo)

    if protection_diff is not None and not protection_diff.is_empty:
        if protection_diff.has_downgrades:
            raise click.ClickException(
                f"Protection downgrade detected during `apply --also-protection`. "
                f"`apply` does not force-downgrade protection. Run "
                f"`gh manage protection sync {owner_repo} --profile "
                f"{profile_name} --downgrade-allowed --apply --yes` "
                f"explicitly to override, then re-run `apply`."
            )
        backup_dir = _resolve_backup_dir()
        protection_sync.apply_protection_diff(
            protection_diff,
            owner_repo,
            "main",
            downgrade_allowed=False,
            backup_dir=backup_dir,
            progress=click.echo,
        )

    click.echo(
        f"\nApplied {n_file_changes} file changes"
        + (f" + {n_label_changes} label changes" if also_labels else "")
        + (f" + {n_protection_changes} protection changes" if also_protection else "")
        + "."
    )
```

Remove the old `--also-protection` stub error (the line `raise click.ClickException("--also-protection is not yet implemented...")`) from the click body.

- [ ] **Step 12.4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/cli/test_apply.py -v
```

Expected: 8 passed (6 existing minus 1 removed stub test + 3 new).

- [ ] **Step 12.5: Run full gate**

```bash
uv run pytest && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/
```

Expected: all green (294 + 2 = 296 tests; 294 was after Task 11's +4, but we removed 1 stub test and added 3 new ones → net +2).

- [ ] **Step 12.6: Commit**

```bash
git add src/gh_manage/commands/apply.py tests/unit/cli/test_apply.py
git commit -m "$(cat <<'EOF'
feat(phase-7): wire apply --also-protection to real implementation

Phase 6 left --also-protection as a stub that raised "not yet
implemented (scheduled for Phase 7)". Phase 7 replaces that error
path with the real integration:

1. Profile must have protection_policy set (else actionable error)
2. Load branch-protection.yml, validate policy exists (available
   policies listed on error)
3. get_branch_protection (404 → empty dict)
4. compute_protection_diff
5. Display the diff alongside files (and optional labels)
6. Apply path:
   - has_downgrades → ClickException with actionable redirect to
     `gh manage protection sync --downgrade-allowed` (apply is
     conservative, same pattern as init from Task 11)
   - Otherwise → apply_protection_diff(downgrade_allowed=False)

--also-protection remains OPT-IN (unlike init where it's automatic).
This preserves Phase 6's design: apply is the files-only "safe
partial-update" path, and each --also-* flag explicitly opts into a
broader action.

_handle_errors catch tuple extended with ProtectionError.

Tests: removed the Phase 6 stub test
test_apply_also_protection_errors_out_with_phase_7_message and added
3 new tests:
- Dry-run displays protection diff
- --apply calls apply_protection_diff
- Downgrade redirects to protection sync --downgrade-allowed

Net +2 tests (296 total).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Final gate + dogfood smoke test

**Goal:** Final gate pass + end-to-end dogfood smoke test of `gh manage protection diff gh-manage --profile python-service` in gh-manage's own repo. Verify nothing crashes and the output is sensible. Push the branch.

**Files:** none modified (verification only).

- [ ] **Step 13.1: Full test suite**

```bash
uv run pytest 2>&1 | tail -15
```

Expected: ~296 tests pass (189 Phase 6 baseline + ~107 Phase 7 additions).

- [ ] **Step 13.2: Lint + format + mypy**

```bash
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/ 2>&1 | tail -5
```

Expected: all clean except the pre-existing yaml stub note.

- [ ] **Step 13.3: Dogfood — `gh manage protection diff gh-manage --profile python-service`**

```bash
cd /home/server160/repos/gh-manage
uv run gh-manage protection diff gh-manage --profile python-service 2>&1
echo "real-exit=$?"
```

Expected behaviors:
- The command loads `python-service.yml` profile from package data
- Resolves the `solo-default` policy from `data/branch-protection.yml`
- Fetches current protection for `yakkuro/gh-manage` via `gh api`
- Runs `compute_protection_diff`
- Prints the diff
- Exits 0 (if no changes, or non-downgrade changes only) or 1 (if downgrade detected without `--downgrade-allowed`)

**If the command crashes** with a Python traceback, STOP and investigate.
**If it exits 0 or 1 cleanly with human-readable output**, the smoke test passes.

- [ ] **Step 13.4: Dogfood — `gh manage protection sync gh-manage --profile python-service --dry-run`**

```bash
uv run gh-manage protection sync gh-manage --profile python-service --dry-run 2>&1
echo "real-exit=$?"
```

Expected: same diff output as 13.3, plus the "Dry-run: N field changes..." trailer. Exit 0.

- [ ] **Step 13.5: Dogfood — init still works (regression)**

```bash
cd /tmp && /home/server160/repos/gh-manage/.venv/bin/gh-manage init --profile python-service /tmp 2>&1
echo "real-exit=$?"
```

Expected: same error as Phase 6's post-merge test — `NotAGitRepoError` (because /tmp isn't a git repo). The presence of protection in the profile should not cause early crash; the command should reach the precheck.

Return to the repo:

```bash
cd /home/server160/repos/gh-manage
```

- [ ] **Step 13.6: Push the branch**

```bash
git push -u origin feat/phase-7-protection 2>&1 | tail -5
```

- [ ] **Step 13.7: Summary for PR body**

```bash
git log --oneline main..HEAD
git diff main..HEAD --stat | tail -5
```

Expected: 12 commits (one per Task 1-12), roughly +4000/-300 lines across ~25 files.

---

## Self-Review Notes

### Spec coverage

| Spec section | Implementation task |
|---|---|
| Profile resolution via --profile flag | Task 10 (`_resolve_profile_path`), Task 11/12 (init/apply integration) |
| `config/branch-protection.yml` with solo-default | Task 9 |
| `ProfileSpec` extension | Task 2 |
| `models/branch_protection.py` pydantic schema | Task 1 |
| `github_api/protection.py` Classic API wrapper | Task 3 (including stdin body regression guard) |
| `protection_sync.py` data classes + errors | Task 4 |
| `normalize_protection_response` | Task 5 |
| `detect_downgrade` 13 rules | Task 6 (12 active + rule 13 dormant) |
| `build_desired_protection` + `compute_protection_diff` | Task 7 |
| `apply_protection_diff` with backup + PUT + TTY prompt | Task 8 (backup unique filename, backup dir pre-flight) |
| Golden test (roundtrip on production data) | Task 9 |
| `commands/protection.py` sync + diff + `_is_tty_stdin` | Task 10 |
| `init` auto-applies protection (Q5 = X) | Task 11 |
| `apply --also-protection` wiring (Q5 = A conservative) | Task 12 |
| Dogfood smoke test | Task 13 |
| 13 downgrade rules parametrized tests | Task 6 |
| `normalize` edge cases (5 cases from spec-critique) | Task 5 |
| Backup filename uniqueness regression guard | Task 8 |
| TTY detection tests | Task 10 |
| `ProtectionPolicyNotFoundError` includes available policies | Task 10 (`_load_profile_and_policy`) |
| All 24 ACs from the spec | Mapped across Tasks 1-13 |

All spec items have corresponding tasks.

### Placeholder scan

No "TBD", "TODO", "FIXME", or "implement later" in the plan itself (except the self-review paragraph above referring to spec items).

### Type consistency

- `ProtectionDiff`, `ProtectionFieldChange`, `DowngradeFinding` — referenced consistently in Tasks 4, 7, 8, 10, 11, 12
- `ProtectionError` hierarchy — catch tuple in Tasks 10, 11, 12 all include `ProtectionError`
- `compute_protection_diff(current, policy, profile, target_branch="main")` — signature matches across Tasks 4, 7, 10, 11, 12
- `apply_protection_diff(diff, repo, target_branch, *, downgrade_allowed, backup_dir, progress)` — signature matches across Tasks 4, 8, 10, 11, 12
- `build_desired_protection(policy, profile)` — signature matches across Tasks 4, 7, 9
- `detect_downgrade(current, desired)` — signature matches across Tasks 4, 6, 7
- `normalize_protection_response(raw)` — signature matches across Tasks 4, 5, 7

### Test count progression

| After task | Count | Delta |
|---|---|---|
| Phase 6 baseline | 189 | — |
| Task 1 (models/branch_protection) | 202 | +13 |
| Task 2 (profiles extension) | 206 | +4 |
| Task 3 (github_api/protection) | 213 | +7 |
| Task 4 (protection_sync stubs) | 222 | +9 |
| Task 5 (normalize) | 235 | +13 |
| Task 6 (downgrade 13 rules) | 259 | +24 |
| Task 7 (build_desired + compute_diff) | 267 | +8 |
| Task 8 (apply_protection_diff) | 275 | +8 |
| Task 9 (golden + production data) | 278 | +3 |
| Task 10 (commands/protection) | 290 | +12 |
| Task 11 (init integration) | 294 | +4 |
| Task 12 (apply --also-protection) | 296 | +2 (net: +3 new, -1 stub) |
| Task 13 (dogfood smoke) | 296 | — |

Total: 189 → 296 (+107).

### Out of scope confirmed

- `collaborative` / `docs-only` policies — only `solo-default` ships
- `gh manage protection show` subcommand — deferred, `diff` covers it
- `config/repos.yml` — still Phase 8
- Backup rotation / cleanup — Phase 7.5+
- `extra_labels` in profile YAML — Phase 7.5+
- Rulesets API — Phase 7.5+
- Multi-branch support beyond `main` — test fixtures cover 1 branch only, engine supports multiple (policy.target_branches)
- Phase 5/6 pre-existing issues #10, #11, #13 — unchanged, separate PRs
