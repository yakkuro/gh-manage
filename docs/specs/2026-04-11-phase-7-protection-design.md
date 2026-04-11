# Phase 7 — `gh manage protection` Design Spec

**Date:** 2026-04-11
**Size:** Medium (3+ source files, 2 pydantic schemas, 2-3 subcommands, new GitHub API resource wrapper, Phase 6 integration)
**Sizing rationale:** New CLI subcommands + new pure-function engine + new pydantic schema + new github_api resource module + Phase 6 integration (init auto-applies + apply `--also-protection` wiring). Multiple files but a single coherent subsystem with one obvious decomposition. Not Large because it's a single feature (branch protection sync) with no cross-domain coupling — it reuses Phase 5/6 plumbing.
**Target:** `gh-manage` (yakkuro/gh-manage)
**Goal:** Implement `gh manage protection sync` and `gh manage protection diff` so branch protection can be declaratively applied from a profile + policy, with transactional downgrade detection + pre-apply backup. Phase 6's `gh manage init` auto-applies protection; Phase 6's `gh manage apply --also-protection` is wired to the real implementation.

## Acceptance Criteria

- [ ] `gh manage protection sync <repo> --profile python-service --apply --yes` applies the `solo-default` policy to a repo (against an empty / no-protection starting state)
- [ ] Applying a weaker policy (e.g., `allow_force_pushes: false → true`) stops with `ProtectionDowngradeError` in the default case (exit 1, actionable message)
- [ ] `--downgrade-allowed --apply --yes` allows the downgrade through
- [ ] `--downgrade-allowed --apply` on non-TTY stdin without `--yes` stops with error (CI safety against accidental downgrade)
- [ ] Pre-apply current protection state is backed up to `~/.gh-manage/backups/<owner>-<repo>-<timestamp>.yml`
- [ ] Backup write failure raises `ProtectionBackupError` and PUT is NOT called (refuse to modify without a restore path)
- [ ] `gh manage protection diff <repo> --profile python-service` prints the diff; exit 1 when a downgrade is detected without `--downgrade-allowed`, exit 0 otherwise
- [ ] `gh manage init --profile python-service --apply` in a properly-configured consumer repo applies files + labels + protection (all three)
- [ ] `gh manage apply --profile python-service --also-protection --apply` applies files + protection (labels only with `--also-labels`)
- [ ] `apply --also-protection` on downgrade detection stops with `ProtectionDowngradeError` guiding the user to `gh manage protection sync <repo> --profile <name> --downgrade-allowed` for explicit override
- [ ] Profile with `protection_policy: None` → `protection sync` stops with actionable `ConfigValidationError`
- [ ] All 13 downgrade rules have parametrized tests (upgrade direction also covered) + tests for `normalize_protection_response` edge cases (empty dict, missing keys, GitHub API wrapper unwrapping)
- [ ] Backup filename uses microsecond precision (`{owner}-{repo}-{YYYYMMDDTHHMMSS}-{microsecond}.yml`) — regression test asserts that two calls in the same second produce distinct filenames
- [ ] Backup dir pre-flight check: if `~/.gh-manage` exists as a regular file (not directory), raise `ProtectionBackupError` with actionable message
- [ ] TTY detection: non-TTY + `--downgrade-allowed` without `--yes` → exit 1 with "Non-TTY environment detected" message; non-TTY + `--downgrade-allowed` + `--yes` → proceeds
- [ ] `ProtectionPolicyNotFoundError` message includes the list of available policies from the loaded `branch-protection.yml`
- [ ] `branch-protection.yml` schema validation tests cover: unknown field, out-of-range review count, empty target_branches, null for optional fields
- [ ] `put_branch_protection` sends the body via `run_gh_api(body=dict)` (Phase 5 checkpoint-refactor stdin path — regression guard)
- [ ] `uv run pytest` — all pass (Phase 6 baseline 189 + Phase 7 additions)
- [ ] `uv run ruff check src/ tests/` — clean
- [ ] `uv run ruff format --check src/ tests/` — clean
- [ ] `uv run mypy src/` — only the pre-existing yaml stub note
- [ ] Dogfood smoke test: `gh manage protection diff gh-manage --profile python-service` runs in gh-manage's own repo without crashing (drift OK; crash not OK)

## Scope

Implementing in this phase:
- `gh manage protection sync <repo> --profile <name> [--apply] [--dry-run] [--downgrade-allowed] [--yes]`
- `gh manage protection diff <repo> --profile <name> [--downgrade-allowed]`
- `config/branch-protection.yml` → `src/gh_manage/data/branch-protection.yml` shipping ONE policy (`solo-default`)
- `ProfileSpec` extension: `protection_policy: str | None` and `required_contexts: list[str]`
- `python-service.yml` update: `protection_policy: solo-default`, `required_contexts: []`
- `gh manage init` auto-applies protection alongside files + labels (matching the master spec contract table)
- `gh manage apply --also-protection` replaces the "Phase 7 not yet implemented" stub with the real implementation
- 13-rule downgrade detection
- Pre-apply YAML backup to `~/.gh-manage/backups/`

Intentionally out of scope (Phase 7.5+):
- `gh manage protection show <repo>` subcommand (diff covers it in practice)
- `collaborative` / `docs-only` policies (deferred until a consumer needs them)
- Backup rotation / retention / cleanup command
- `gh manage protection restore <backup-file>` (manual `gh api --input` works)
- Rulesets API (modern GitHub branch protection) — Classic only per master spec decision
- Multi-branch support beyond `target_branches: [main]` — mechanism in place but tests cover single branch
- `config/repos.yml` — still deferred to Phase 8 per Phase 6 Q1 decision
- `extra_labels` in profile YAML — still deferred to Phase 7.5+
- `init --skip-protection` flag — use a profile with `protection_policy: None` instead
- Backup encryption — protection config is not sensitive
- Phase 5/6 pre-existing issues #10, #11, #13 — unchanged, handled in separate PRs

## Architecture

Phase 5/6 の 3 層構造を踏襲します。

| Layer | 責務 | Phase 7 で追加 / 既存 |
|---|---|---|
| `commands/` | click 引数 + 出力整形 + IO orchestration | `protection.py` 書き直し、`init.py`/`apply.py` 統合修正 |
| `protection_sync.py`(pure) | diff 計算 + downgrade 検出 + apply 実行 | NEW |
| `models/branch_protection.py` | pydantic schema | NEW |
| `github_api/protection.py` | GitHub API resource wrapper(Classic branch protection)| NEW(Phase 5 `github_api/labels.py` と対称)|
| 既存 utility 再利用 | `git_cli.get_origin_owner_repo`, `github_client.run_gh_api(body=...)`, `config.load_config`, `_handle_errors` decorator | 既存 |

### 依存方向

```
commands/{protection,init,apply}.py
   │
   ├─→ protection_sync.py ──→ models/branch_protection.py
   │       │
   │       └─→ github_api/protection.py ──→ github_client.run_gh_api (body via stdin)
   │
   ├─→ git_cli.get_origin_owner_repo (precheck)
   │
   └─→ [既存] profile_sync, labels_sync, github_api/labels, importlib.resources
```

3 モジュール分割の理由:
- `protection_sync.py` は純粋関数(subprocess / network なし、全部 pydantic model 入出力)
- `github_api/protection.py` が唯一 `run_gh_api(body=dict)` を使う(Phase 5 checkpoint refactor で stdin 経由に書き直した path の初めての production consumer)
- `models/branch_protection.py` は GitHub API response shape を pydantic で表現

### File layout

```
src/gh_manage/
├── commands/
│   ├── protection.py                # 書き直し(現状は Phase 7 stub)
│   ├── init.py                      # 修正: protection 自動適用パスを追加
│   └── apply.py                     # 修正: --also-protection を本実装に差し替え
├── models/
│   ├── branch_protection.py         # NEW: BranchProtectionConfig, PolicySpec, RequiredStatusChecks, RequiredPullRequestReviews
│   └── profiles.py                  # 修正: protection_policy + required_contexts フィールド追加
├── github_api/
│   └── protection.py                # NEW: get_branch_protection, put_branch_protection, delete_branch_protection
├── protection_sync.py               # NEW: 純粋関数 engine
└── data/
    ├── branch-protection.yml        # NEW: solo-default policy 1 件
    └── profiles/python-service.yml  # 修正: protection_policy + required_contexts 追加

tests/unit/
├── github_api/test_protection.py    # NEW
├── models/test_branch_protection.py # NEW
├── models/test_profiles.py          # 修正: 新フィールドのテスト 3 件追加
├── protection_sync/
│   ├── __init__.py                  # NEW
│   ├── test_protection_sync.py      # NEW: compute_protection_diff + apply_protection_diff
│   ├── test_downgrade.py            # NEW: 13 downgrade ルール
│   └── test_golden.py               # NEW: build_desired_protection roundtrip
├── cli/
│   ├── test_protection.py           # NEW
│   ├── test_init.py                 # 修正: protection 統合テスト追加
│   └── test_apply.py                # 修正: --also-protection 本実装のテストに差し替え
└── fixtures/protection/
    ├── solo-default.yml             # NEW
    ├── current-empty.json           # NEW
    └── current-solo.json            # NEW
```

## Config schema & contents

### `src/gh_manage/data/branch-protection.yml` (Phase 7 MVP: 1 policy)

```yaml
version: 1
policies:
  solo-default:
    description: "Solo-dev default (no review requirement)"
    target_branches: ["main"]
    required_status_checks:
      strict: true
      contexts: []                  # profile.required_contexts で上書き
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

### `models/branch_protection.py` (pydantic schema)

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RequiredStatusChecks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strict: bool
    contexts: list[str] = Field(default_factory=list)


class RequiredPullRequestReviews(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_approving_review_count: int = Field(ge=0, le=6)
    dismiss_stale_reviews: bool = False
    require_code_owner_reviews: bool = False


class PolicySpec(BaseModel):
    """One policy entry in branch-protection.yml."""
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

設計判断:
- `PolicySpec.required_status_checks` と `required_pull_request_reviews` は `| None`(docs-only 風 policy で null を使う可能性があるため)。Phase 7 MVP の `solo-default` は両方 non-null
- `extra="forbid"` で未知フィールドは validation error → 将来 GitHub API が新 field を追加した時に気付ける
- `target_branches` の空リストは `_target_branches_nonempty` validator で拒否
- pydantic の数値制約 `ge=0, le=6` で `required_approving_review_count` の妥当性チェック(GitHub の上限は 6)
- Schema versioning は Phase 5/6 と同じ `version: Literal[1]` + `config.load_config` 経由

### `ProfileSpec` 拡張(`models/profiles.py`)

```python
class ProfileSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    name: str
    description: str | None = None
    files: list[FileEntry]
    # Phase 7 で追加:
    protection_policy: str | None = None
    required_contexts: list[str] = Field(default_factory=list)
```

- `protection_policy` は optional: 指定なし = protection 対象外
- `required_contexts` は空リストがデフォルト
- `extra_labels` は引き続き除外(Phase 6 のスコープ判断維持)

### `src/gh_manage/data/profiles/python-service.yml` 更新

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

`required_contexts: []` は意図的に空。`templates/ci/python-ci.yml` の workflow/job 名が固定されたら Phase 7.5 以降で実際の値を追加する。

## Engine

### `github_api/protection.py` — GitHub API wrapper

```python
"""GitHub branch-protection API helpers.

Phase 5/6 の github_api/labels.py と対称的な resource wrapper。run_gh_api を
経由して Classic Branch Protection API を呼ぶ。Rulesets API は将来検討。
"""

def get_branch_protection(repo: str, branch: str = "main") -> dict[str, Any]:
    """GET /repos/{repo}/branches/{branch}/protection.

    Returns the raw JSON response (a nested dict matching GitHub's schema).
    Raises GhNotFoundError if the branch has no protection configured
    (the caller should treat this as "empty/unprotected" state).
    """


def put_branch_protection(
    repo: str, branch: str, body: dict[str, Any]
) -> None:
    """PUT /repos/{repo}/branches/{branch}/protection with the given body.

    Uses run_gh_api(body=...) — the Phase 5 checkpoint refactor rewrote
    run_gh_api to accept JSON via stdin (`gh api --input -`) specifically
    for nested bodies like this. Phase 7 is the first production caller
    of that path.
    """


def delete_branch_protection(repo: str, branch: str = "main") -> None:
    """DELETE /repos/{repo}/branches/{branch}/protection.
    Phase 7 does NOT call this — included for completeness / Phase 7.5+."""
```

### `protection_sync.py` — data classes

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gh_manage.models.branch_protection import PolicySpec
from gh_manage.models.profiles import ProfileSpec


@dataclass(frozen=True)
class ProtectionFieldChange:
    """One field-level change detected between current and desired protection."""
    field_path: str               # e.g., "required_status_checks.contexts"
    current_value: Any            # from GitHub API
    desired_value: Any            # from policy + profile


@dataclass(frozen=True)
class DowngradeFinding:
    """A field change classified as weakening protection."""
    field_path: str
    current_value: Any
    desired_value: Any
    reason: str                   # human-readable


@dataclass(frozen=True)
class ProtectionDiff:
    changes: tuple[ProtectionFieldChange, ...]
    downgrades: tuple[DowngradeFinding, ...]
    current_raw: dict[str, Any]   # GitHub API response (empty dict = no protection)
    desired_raw: dict[str, Any]   # PUT body

    @property
    def is_empty(self) -> bool:
        return not self.changes

    @property
    def has_downgrades(self) -> bool:
        return bool(self.downgrades)
```

### Error hierarchy

```python
class ProtectionError(Exception):
    """Base for protection_sync errors. Caught by commands/_handle_errors."""


class ProtectionPolicyNotFoundError(ProtectionError):
    """profile.protection_policy references a policy name not in
    branch-protection.yml. Raised at compute time.

    Error message MUST include the list of available policies from the
    loaded branch-protection.yml so the user can choose or fix a typo
    without having to open the YAML file. Example:

        f"Policy {requested!r} not found in branch-protection.yml. "
        f"Available policies: {sorted(config.policies.keys())}. "
        f"Either fix the profile's `protection_policy` field or add "
        f"a new policy to src/gh_manage/data/branch-protection.yml."
    """


class ProtectionDowngradeError(ProtectionError):
    """apply_protection_diff was called with diff.has_downgrades AND
    downgrade_allowed=False. Message lists each DowngradeFinding with
    reason and points to --downgrade-allowed override."""

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
    BEFORE the PUT call if the backup can't be written — we refuse to
    modify a protection config we can't restore."""


class ProtectionApplyError(ProtectionError):
    """The PUT to GitHub failed. Wraps the underlying GhError."""
```

### Core engine functions

```python
def build_desired_protection(
    policy: PolicySpec,
    profile: ProfileSpec,
) -> dict[str, Any]:
    """Combine a policy with a profile to produce the effective PUT body.

    Implements the 'contracts' section of the master spec:
        effective.required_status_checks.contexts = profile.required_contexts
    (complete replacement — the policy's `contexts: []` is always overwritten.)

    All other fields come from the policy as-is. Returns a dict shaped
    for the GitHub PUT /branches/{branch}/protection API body.
    """


def normalize_protection_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a GitHub branch-protection API response (or an empty
    dict representing "no protection") into a canonical comparison shape.

    Canonical shape (matches our model, not GitHub's wire shape):
      {
        "required_status_checks":
          None | {"strict": bool, "contexts": list[str]},
        "required_pull_request_reviews":
          None | {
            "required_approving_review_count": int,
            "dismiss_stale_reviews": bool,
            "require_code_owner_reviews": bool,
          },
        "enforce_admins": bool,
        "required_conversation_resolution": bool,
        "required_linear_history": bool,
        "allow_force_pushes": bool,
        "allow_deletions": bool,
      }

    Normalization rules (LOAD-BEARING for downgrade detection correctness):

    1. Empty dict (from 404 → "no protection yet"): all fields default to
       their WEAKEST value:
         required_status_checks = None
         required_pull_request_reviews = None
         enforce_admins = False
         required_conversation_resolution = False
         required_linear_history = False
         allow_force_pushes = True
         allow_deletions = True
    2. Missing top-level key: treated as absent → uses the weakest default.
       GitHub's API sometimes omits falsy keys; treating missing as weakest
       ensures "add protection" is classified as UPGRADE and "remove
       protection" is correctly flagged as DOWNGRADE.
    3. `enforce_admins` wrapper: GitHub returns {"enforce_admins":
       {"enabled": bool, "url": str}}. Extract `.enabled` → bool. Missing
       → False.
    4. `allow_force_pushes` / `allow_deletions` wrappers: same shape as
       enforce_admins ({"enabled": bool}). Extract `.enabled`. Missing →
       True (the weakest state — GitHub's default for unmanaged branches
       is to allow force-push and deletion).
    5. `required_status_checks`: extract `strict` + `contexts` from the
       wrapper object. Drop other fields (e.g., the overlapping `checks`
       array). Missing top-level key → None.
    6. `required_pull_request_reviews`: extract the 3 fields we care
       about (required_approving_review_count, dismiss_stale_reviews,
       require_code_owner_reviews). Drop the rest. Missing → None.

    This is a plain-Python dict transformation — no pydantic validation,
    because we want to accept malformed / partial API responses
    gracefully rather than crash on unexpected shapes.
    """


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
      3. Walk the field tree comparing normalized vs desired:
         - required_status_checks.{strict, contexts}
         - required_pull_request_reviews.{required_approving_review_count,
           dismiss_stale_reviews, require_code_owner_reviews}
         - enforce_admins, required_conversation_resolution,
           required_linear_history, allow_force_pushes, allow_deletions
      4. For each field change, emit ProtectionFieldChange.
      5. Run detect_downgrade(normalized, desired) and emit
         DowngradeFinding for each weakening.
      6. Return ProtectionDiff containing both lists + raw dicts.

    Pure: no IO, no subprocess, no git, no GitHub API.
    """


def detect_downgrade(
    current: dict[str, Any], desired: dict[str, Any]
) -> tuple[DowngradeFinding, ...]:
    """Check the 13 downgrade rules. Returns empty tuple if desired is
    equal or stronger than current. Both arguments MUST be
    normalize_protection_response()-ed shape; raw GitHub API responses
    must not be passed directly."""
```

### 13 downgrade rules (合意済み、normalized shape 前提)

各ルールは `(current, desired) → is_downgrade: bool` の純関数比較。入力は
必ず `normalize_protection_response()` された canonical shape であること。

| # | field_path | 比較条件(True = downgrade) |
|---|---|---|
| 1 | `required_pull_request_reviews.required_approving_review_count` | `desired < current`(例: 2 → 1、1 → 0 は downgrade、0 → 1 は upgrade) |
| 2 | `required_pull_request_reviews.dismiss_stale_reviews` | `current is True and desired is False` |
| 3 | `required_pull_request_reviews.require_code_owner_reviews` | `current is True and desired is False` |
| 4 | `required_pull_request_reviews`(wrapper) | `current is not None and desired is None`(review 要件を完全撤去)|
| 5 | `enforce_admins` | `current is True and desired is False` |
| 6 | `required_status_checks.strict` | `current is True and desired is False` |
| 7 | `required_status_checks.contexts` | `set(current) - set(desired)` が non-empty(任意の context が消える)|
| 8 | `required_status_checks`(wrapper) | `current is not None and desired is None`(status check を完全撤去)|
| 9 | `required_conversation_resolution` | `current is True and desired is False` |
| 10 | `required_linear_history` | `current is True and desired is False` |
| 11 | `allow_force_pushes` | `current is False and desired is True`(force push 許可)|
| 12 | `allow_deletions` | `current is False and desired is True`(branch 削除許可)|
| 13 | `target_branches` | `set(current) - set(desired)` が non-empty(保護ブランチの削除、Phase 7 MVP では発火しない)|

**重要**: ルール 1 は `<` 比較(strictly less than)。`desired == current` は
変化なしで downgrade ではない。ルール 7 と 13 は set difference(左辺 -
右辺が non-empty な場合に downgrade)。ルール 4 と 8 は null 遷移
専用で、どちらも null → null や object → object(内部変化は他のルールで
検出)は対象外。

`detect_downgrade` は 13 ルールを順に評価して DowngradeFinding を
collect、非空なら tuple にして返す。ルール間は独立(1 つの変更が
複数ルールに該当する場合、該当するすべてが個別の DowngradeFinding
として記録される — 例: `required_pull_request_reviews` が存在 → null
に遷移した場合、ルール 4 が発火するが、ルール 1/2/3 は発火しない
(wrapper object がないため評価対象外))。

### `apply_protection_diff` — transactional apply

```python
def apply_protection_diff(
    diff: ProtectionDiff,
    repo: str,                        # "owner/repo"
    target_branch: str = "main",
    *,
    downgrade_allowed: bool = False,
    backup_dir: Path,                 # ~/.gh-manage/backups resolved by CLI
    progress: Callable[[str], None] = lambda _: None,
) -> None:
    """Apply the protection diff with safety guards.

    Order of operations (LOAD-BEARING):
      1. If diff.has_downgrades AND not downgrade_allowed:
         raise ProtectionDowngradeError BEFORE any IO.
      2. Pre-flight check on backup_dir: if it exists and is NOT a directory
         (e.g., a regular file at ~/.gh-manage), raise ProtectionBackupError
         with actionable message. If it does not exist, create it with
         `mkdir(parents=True, exist_ok=True)`.
      3. Compute unique backup filename (collision-safe — see below) and
         write YAML dump of diff.current_raw. If backup write fails
         (permission, disk full, path too long), raise ProtectionBackupError.
         NEVER modify protection without a restorable backup.
      4. PUT the desired body to GitHub API via
         github_api.protection.put_branch_protection.
      5. If PUT fails, propagate the GhError (wrap into
         ProtectionApplyError if needed). The backup remains on disk
         for manual restore via `gh api ... --input <backup-file>`.

    Transactional guarantees:
      - Conflict check → backup dir check → backup write → PUT is the full order.
      - If steps 1, 2, or 3 fail, nothing is modified on GitHub.
      - Step 4 failure leaves the backup on disk (intentional, for manual restore).

    `progress` is called before backup + before PUT:
      progress(f"backup → {backup_path}")
      progress(f"apply → {repo}:{target_branch}")
    """
```

**Backup filename — collision-safe uniqueness (spec-critique CRITICAL #1):**

Filename format: `{owner}-{repo}-{YYYYMMDDTHHMMSS}-{microsecond}.yml`

Example: `yakkuro-gh-manage-20260411T120512-043921.yml`

The 6-digit microsecond suffix ensures that two `apply_protection_diff` calls
in the same second (legitimate retry scenario) produce distinct filenames.
A second-resolution timestamp alone is NOT sufficient — Python's
`datetime.now().strftime("%Y%m%dT%H%M%S")` would collide and the second
backup would overwrite the first, destroying the original restore path.

Implementation: `datetime.now().strftime("%Y%m%dT%H%M%S-%f")` (Python's `%f`
directive yields 6-digit microseconds). In the extremely unlikely event of
a sub-microsecond collision, `write_bytes()` will overwrite, but this is
acceptable because: (a) microsecond precision is more than sufficient for
any realistic CLI retry pattern, (b) the alternative (sequence-number
scan of backup_dir) introduces its own race conditions without meaningful
safety improvement for a single-user CLI.

**Backup YAML format:**

```python
yaml.safe_dump(
    diff.current_raw,
    default_flow_style=False,   # block style for readability
    sort_keys=True,             # stable key order for diff'ability
    allow_unicode=True,         # preserve UTF-8 in descriptions etc.
    indent=2,
)
```

`sort_keys=True` intentionally differs from "preserve GitHub API order" —
backups are consumed by diff tools and human inspection, both of which
benefit from stable key order. When restoring via `gh api --input <file>`,
GitHub accepts keys in any order, so the sort does not affect restore
correctness.

## CLI commands & flow

### `gh manage protection sync <repo> --profile <name>`

```
gh manage protection sync [<path>] --profile <name>
                          [--dry-run] [--apply] [--downgrade-allowed] [--yes]
```

**Flags:**
- `path`: positional, default `.` (used only for `git_cli.get_origin_owner_repo` precheck)
- `--profile <name>`: required
- `--dry-run` / `--apply`: mutually exclusive
- `--downgrade-allowed`: bypass the downgrade safety check (default off)
- `--yes`: skip the interactive confirmation prompt on `--apply` + `--downgrade-allowed`

**Flow:**

```
1. target = Path(path or ".")
2. Precheck: owner_repo = git_cli.get_origin_owner_repo(target)
3. profile = load_config(<package data>/profiles/<name>.yml, ProfileSpec)
   — filename ↔ profile.name invariant check
4. If profile.protection_policy is None:
   raise ConfigValidationError (actionable: "add protection_policy to profile")
5. branch_protection_config = load_config(
       <package data>/branch-protection.yml, BranchProtectionConfig)
6. policy = branch_protection_config.policies.get(profile.protection_policy)
   — if None: raise ProtectionPolicyNotFoundError
7. current = github_api.protection.get_branch_protection(owner_repo, "main")
   — on GhNotFoundError: treat as empty dict (no protection yet)
8. diff = protection_sync.compute_protection_diff(current, policy, profile, "main")
9. Print diff
10. If diff.is_empty: "No changes." + exit 0
11. If not --apply: "Dry-run: N changes [, M downgrades]. Re-run with --apply."
    + exit 0 if no downgrades, exit 1 if downgrades AND not --downgrade-allowed
    (so `protection diff` can be used in pre-commit hooks as a drift check)
12. If --apply + diff.has_downgrades + not --downgrade-allowed:
    raise ProtectionDowngradeError (exit 1, actionable msg)
13. If --apply + diff.has_downgrades + --downgrade-allowed + not --yes:
    Interactive confirmation prompt (TTY only).
    Non-TTY → require --yes or exit 1 with "CI environment detected; pass --yes".
14. If --apply:
    backup_dir = Path.home() / ".gh-manage" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    protection_sync.apply_protection_diff(
        diff, owner_repo, "main",
        downgrade_allowed=downgrade_allowed,
        backup_dir=backup_dir,
        progress=click.echo,
    )
    "Done. Protection updated for {owner_repo}:main."
```

**`--yes` semantics(spec-critique HIGH #4 対応、TTY detection 明示):**

- `--apply` + `--downgrade-allowed` の組み合わせ = 意図的な弱体化
- **TTY 判定方法**: `click.get_text_stream("stdin").isatty()` を使う(Python 標準の `sys.stdin.isatty()` と等価だが click 経由で testing 可能)
- TTY = True なら `click.confirm("This will weaken N protection field(s). Continue?", default=False)` で二重確認
- TTY = False(CI 環境、Docker、cron、パイプ入力等) AND `--yes` 未指定 → `click.ClickException("Non-TTY environment detected. Pass --yes to confirm the downgrade in CI/non-interactive contexts.")` で exit 1
- TTY = False AND `--yes` 指定あり → 確認スキップ、apply 続行
- `--apply` だけ(downgrade なし)は prompt なし(普通の safe case)
- `--dry-run` は prompt なし(副作用なし)

**TTY detection エッジケース:**
- GitHub Actions: `runs-on: ubuntu-latest` は stdin が TTY ではない → `--yes` 要求
- Docker interactive(`docker run -it`): stdin が TTY → interactive confirm
- Docker non-interactive(`docker run`, ENTRYPOINT shell)TTY なし → `--yes` 要求
- cron: stdin が /dev/null or 閉じる → TTY なし → `--yes` 要求
- `gh-manage ... < /dev/null`: pipe input → TTY なし → `--yes` 要求

すべて `--yes` フラグで明示 opt-in させる方針。デフォルトで安全側に倒す。

### `gh manage protection diff <repo> --profile <name>`

```
gh manage protection diff [<path>] --profile <name> [--downgrade-allowed]
```

sync の `--dry-run` とほぼ同じフロー。違い:
- `--apply` フラグなし(常に read-only)
- exit code は downgrade 有無 + `--downgrade-allowed` 組み合わせで決まる:
  - 変更なし → 0
  - 非 downgrade の変更あり → 0
  - downgrade + flag なし → 1
  - downgrade + `--downgrade-allowed` → 0

### Diff display format

```
Branch protection (main):
  enforce_admins:                    false → true        (upgrade)
  required_pull_request_reviews.required_approving_review_count:
                                     0 → 1               (upgrade)
  required_status_checks.contexts:
    + pr-gate / test                                     (upgrade)
    - legacy-check / foo                                 (DOWNGRADE)

Downgrades: 1
  required_status_checks.contexts: removed ['legacy-check / foo']
                                   (shrinking required checks)

Dry-run: 3 field changes, 1 downgrade. Re-run with --apply + --downgrade-allowed to execute.
```

Symbols:
- `→` field-level change
- `+` / `-` list-element add / remove (contexts, target_branches)
- `(upgrade)` / `(DOWNGRADE)` classification
- trailing "Downgrades: N" section repeats each `DowngradeFinding.reason`

### `init.py` integration (Q5 = X: 自動 protection 適用)

現在の flow(Phase 6):
```
1. precheck (git_cli)
2. load profile
3. files_diff = profile_sync.compute_files_diff(...)
4. labels_diff = labels_sync.compute_diff(...)
5. print diff
6. if --apply: apply files + apply labels + "Next steps"
```

Phase 7 で追加:
```
4b. if profile.protection_policy is not None:
    policy = <load from branch-protection.yml>
    current = github_api.protection.get_branch_protection(owner_repo, "main")
    protection_diff = protection_sync.compute_protection_diff(
        current, policy, profile, "main",
    )
    else:
        protection_diff = None

5. print files + labels + protection (if not None)

6a. if --apply + protection_diff is not None:
    if protection_diff.has_downgrades:
       raise ProtectionDowngradeError  # init never force-downgrades
    backup_dir = Path.home() / ".gh-manage" / "backups"
    protection_sync.apply_protection_diff(
        protection_diff, owner_repo, "main",
        downgrade_allowed=False,
        backup_dir=backup_dir,
        progress=click.echo,
    )
```

`init` は `--downgrade-allowed` フラグを持たない。downgrade 検出時は actionable error で stop、ユーザーは `protection sync --downgrade-allowed` を明示実行する。

新規 repo には通常 protection がないので `protection_diff.current_raw = {}` となり、全フィールドが empty → stronger の upgrade 扱い、downgrade は発火しない。

### `apply.py` の `--also-protection` wiring

現在(Phase 6)の stub:
```python
if also_protection:
    raise click.ClickException("Phase 7 で実装予定...")
```

Phase 7 差し替え:
```python
if also_protection:
    if profile.protection_policy is None:
        raise click.ClickException(
            "Profile has no protection_policy — `--also-protection` has "
            "nothing to apply. Use a profile with protection_policy set."
        )
    # compute + display (init と同じパス)
    ...
    if apply_flag:
        if protection_diff.has_downgrades:
            raise ProtectionDowngradeError
        protection_sync.apply_protection_diff(
            protection_diff, owner_repo, "main",
            downgrade_allowed=False,
            backup_dir=backup_dir,
            progress=click.echo,
        )
```

`apply --also-protection` は downgrade 時に自動続行せず、ユーザーを `gh manage protection sync <repo> --profile <name> --downgrade-allowed --apply --yes` に誘導する。

### Preconditions 追加

Phase 6 の Preconditions 表に 3 行追加:

| Precondition | Detected by | Failure error |
|---|---|---|
| `gh` CLI authenticated(protection path any time)| `github_api.protection.get_branch_protection` | `GhAuthError` |
| Profile has `protection_policy` set(protection path any time)| CLI 層の `profile.protection_policy is not None` check | `ConfigValidationError` |
| `branch-protection.yml` contains the referenced policy | `branch_protection_config.policies.get(name)` | `ProtectionPolicyNotFoundError` |

## Test strategy

### Test layout

```
tests/unit/
├── github_api/test_protection.py    # NEW (~8 cases)
├── models/
│   ├── test_branch_protection.py    # NEW (~10 cases)
│   └── test_profiles.py             # +3 cases
├── protection_sync/
│   ├── __init__.py                  # NEW
│   ├── test_protection_sync.py      # NEW (~12 cases)
│   ├── test_downgrade.py            # NEW (~26 cases: 13 rules × 2 directions)
│   └── test_golden.py               # NEW (~2 cases)
├── cli/
│   ├── test_protection.py           # NEW (~10 cases)
│   ├── test_init.py                 # +4 cases
│   └── test_apply.py                # +3 cases (replace 1 stub test)
└── fixtures/protection/
    ├── solo-default.yml             # NEW
    ├── current-empty.json           # NEW
    └── current-solo.json            # NEW
```

### Test scenarios (抜粋)

**`test_branch_protection.py`** (~10 cases):
- Valid v1 policy loads
- `version: 2` → `SchemaVersionError`
- `target_branches: []` → `ValidationError`
- `required_approving_review_count: -1` → `ValidationError`
- `required_approving_review_count: 7` → `ValidationError`
- `required_status_checks: null` is valid
- `required_pull_request_reviews: null` is valid
- Unknown field → `ValidationError`
- Multiple policies in one file
- Missing version → `SchemaVersionError`

**`test_profiles.py`** (+3 cases):
- `protection_policy: str` default None
- `required_contexts: list[str]` default []
- Existing 16 + 3 new = 19

**`test_protection.py` (github_api)** (~8 cases):
- `get_branch_protection` happy path
- 404 → `GhNotFoundError` propagate
- `put_branch_protection` body が `run_gh_api(body=dict)` 経由(Phase 5 checkpoint path の regression guard)
- `put_branch_protection` argv に `--input -` が入る
- Malformed JSON response → `GhAPIError`

**`test_downgrade.py`** (13 rules × 2 directions + normalization edge cases):
- Review count 2 → 1 = downgrade
- Review count 0 → 1 = NOT downgrade
- `enforce_admins: true → false` = downgrade
- `enforce_admins: false → true` = NOT downgrade
- ... (残り 11 ルールも同様)
- Current が空 dict(normalized: all weakest defaults)→ どんな "add protection" desired も NOT downgrade
- Current と desired が完全一致 → NOT downgrade、`diff.is_empty`
- **`normalize_protection_response` edge cases (新規 spec-critique 対応):**
  - Empty dict `{}` → canonical shape with all weakest defaults
  - `{"enforce_admins": {"enabled": True, "url": "..."}}` → `{"enforce_admins": True, ...}`(wrapper 展開)
  - Missing `allow_force_pushes` → `True`(GitHub のデフォルト weakest)
  - Missing `allow_deletions` → `True`
  - `{"required_status_checks": {"strict": True, "contexts": [], "checks": [{...}]}}` → 余計な `checks` を drop、`strict` + `contexts` のみ残る
  - `{"required_pull_request_reviews": {"required_approving_review_count": 1, "extra_field": "ignore"}}` → 既知 3 フィールドのみ残る、extra_field は drop

**`test_protection_sync.py`** (~16 cases):
- `compute_protection_diff(empty, policy, profile)` → 全 field が change、downgrade なし
- `compute_protection_diff(matching, policy, profile)` → `is_empty`
- `build_desired_protection` が `contexts = profile.required_contexts` を反映
- `profile.protection_policy` が branch-protection.yml にない → `ProtectionPolicyNotFoundError`(available policies list が message に含まれる regression guard)
- `apply_protection_diff` with downgrade + not allowed → `ProtectionDowngradeError`、backup 未作成、PUT 未呼出
- `apply_protection_diff` with downgrade + allowed → backup 作成 + PUT 呼出
- `apply_protection_diff` no downgrade → backup + PUT
- `apply_protection_diff` backup dir pre-flight: 存在しない → 自動作成
- `apply_protection_diff` backup dir pre-flight: `~/.gh-manage` が file → `ProtectionBackupError`、PUT 未呼出
- Backup 書き込み失敗(permission denied 相当) → `ProtectionBackupError`、PUT 未呼出
- PUT failure → backup は残る、エラー伝播
- `progress` が backup → PUT の順で呼ばれる
- **Backup filename uniqueness: `apply_protection_diff` を `datetime.now` mock で同一秒に 2 回呼んでも、microsecond suffix で 2 ファイルとも残る(上書きされない)regression guard**
- Backup ファイル名形式: `{owner}-{repo}-{YYYYMMDDTHHMMSS}-{microsecond}.yml` の regex assertion
- Backup 内容が `current_raw` の `yaml.safe_dump(sort_keys=True, allow_unicode=True, indent=2)` 結果と一致

**`test_golden.py`** (2 cases):
- Fixture profile + solo-default policy → `build_desired_protection` 結果 == expected YAML
- Roundtrip: `compute → apply (mocked) → re-fetch` で `is_empty`

**`test_protection.py` (cli)** (~10 cases):
- `sync --profile ... --dry-run` happy path
- `--apply` で apply 呼出、backup + PUT
- `--apply --dry-run` mutex → exit 2
- `--profile` 省略 → click error
- Profile に `protection_policy: None` → `ConfigValidationError`
- 存在しない profile 名 → `ConfigFileNotFoundError`
- 存在しない policy 名 → `ProtectionPolicyNotFoundError`
- Downgrade + no flag → `ProtectionDowngradeError`、exit 1
- Downgrade + `--downgrade-allowed` + `--yes` → apply 実行
- Downgrade + `--downgrade-allowed` + non-TTY stdin + 非 `--yes` → error("Non-TTY environment detected" message)、exit 1
- Downgrade + `--downgrade-allowed` + non-TTY stdin + `--yes` → apply 実行(TTY detection を `click.get_text_stream("stdin").isatty()` の mock で制御)
- `diff` 差分あり → exit 0 または 1(downgrade 有無)
- `diff` empty → "No changes."、exit 0
- `ProtectionPolicyNotFoundError` message に "Available policies: ..." が含まれる(regression guard for spec-critique HIGH #5)

**`test_init.py`** (+4 cases):
- `protection_policy` 設定あり → `protection_diff` 計算 + 表示
- `protection_policy: None` → protection path スキップ
- `--apply` で protection も書き込まれる
- `--apply` で downgrade 検出 → `ProtectionDowngradeError`

**`test_apply.py`** (+3 cases, -1 stub):
- 既存の `test_apply_also_protection_errors_out_with_phase_7_message` を削除
- `--also-protection --dry-run` で protection_diff 表示
- `--also-protection --apply` で `apply_protection_diff` 呼出
- `--also-protection --apply` で downgrade → `ProtectionDowngradeError`

### Phase 5/6 との非干渉性

既存 189 件のテストは Phase 7 で touch しない。`models/test_profiles.py` は `protection_policy` と `required_contexts` 追加に伴い 3 件テスト追加するだけで、既存テストは不変(新フィールドは optional なので既存の minimal profile も valid なまま)。

## エラーハンドリング戦略

`commands/{protection,init,apply}.py` の `_handle_errors` decorator で catch する例外型:

```python
except (
    GhError,                       # gh API failures
    ConfigError,                   # config load failures
    GitError,                      # git CLI failures
    ProfileError,                  # profile_sync failures
    ProtectionError,               # protection_sync failures (NEW in Phase 7)
) as e:
    raise click.ClickException(str(e)) from e
```

`OSError` も引き続き catch は **しない** — Phase 6 のパターンを継承(Phase 6 で `ProfileIOError` を導入して `OSError` を明示的にラップしたのと同じ哲学で、protection の backup 書き込み失敗も `ProtectionBackupError` でラップする)。

## YAGNI / 設計判断メモ

### Profile 解決は `--profile` 必須フラグ(Q1 = A)

Phase 6 init/apply と対称。`config/repos.yml` は Phase 8 に先送り。毎回タイプが必要だが shell history + alias で軽減可能。

### Phase 7 スコープは MVP(Q2 = A)

- `solo-default` 1 policy のみ
- `sync` + `diff` の 2 subcommand(`show` は Phase 7.5+)
- `--also-protection` wiring + `init` 自動 protection 統合

`collaborative` / `docs-only` policies は Phase 7 では実装しない。テスト fixture が solo-default 1 件で十分 downgrade 13 ルールをカバーできるため。

### 13 ルール downgrade 検出(Q3 = A)

spec M-3 の 4 ルールだけでは `allow_deletions` や `required_linear_history` などの変化を検出できず、事故防止として弱い。実装コストは各ルール 1 つの比較関数で小さい。

### Backup は `~/.gh-manage/backups/` + 永続 + no cleanup(Q4 = A)

- Home-based: CWD 非依存、consumer repo の git 状態を汚染しない
- 永続: cleanup/rotation は Phase 7.5+
- YAML dump: GitHub API response をそのまま保存、`gh api ... --input` で復元可能

### init の自動 protection 適用(Q5 = X)

master spec の contract table(init = files ✅ + labels ✅ + protection ✅)に従う。新規 repo には通常 protection がないので downgrade は発火しない。downgrade 検出時は conservative に stop、ユーザーは `protection sync --downgrade-allowed` を明示実行。

### `apply --also-protection` は保守的(Q5 = A)

統合パスは常に安全デフォルト(`downgrade_allowed=False`)。意図的な弱体化は専用 `protection sync --downgrade-allowed` に誘導。

### Classic Branch Protection(Rulesets ではない)

master spec の決定通り。Rulesets API は将来検討(Phase 7.5+ または Phase 9 の v1.0 後)。Classic は安定して 10 年以上稼働している API で、Phase 7 の要件(fields, downgrade 検出, backup)をすべて満たす。

## Phase 5/6 との対称性チェック

| Phase 5 (labels) | Phase 6 (profile/files) | Phase 7 (protection) |
|---|---|---|
| `commands/labels.py` | `commands/init.py` + `commands/apply.py` | `commands/protection.py` + init/apply 修正 |
| `labels_sync.py` | `profile_sync.py` | `protection_sync.py` |
| `models/labels.py` | `models/profiles.py`(+ Phase 7 で拡張)| `models/branch_protection.py` |
| `github_api/labels.py` | (reuse) | `github_api/protection.py` |
| `github_client.py` | (reuse) | (reuse, `run_gh_api(body=...)` が Phase 7 で初めて production 利用) |
| `LabelsDiff`(creates/renames/updates/deletes tuples) | `ProfileFilesDiff`(creates/overwrites/skipped/noops) | `ProtectionDiff`(changes/downgrades + raw dicts) |
| `compute_diff` + `apply_diff`(fail-fast) | `compute_files_diff` + `apply_files_diff`(transactional conflict) | `compute_protection_diff` + `apply_protection_diff`(downgrade check + backup + PUT) |
| `--apply` / `--dry-run` mutex | 同じ | 同じ |
| `_handle_errors` decorator | 同じ | 同じ(+ `ProtectionError` を catch tuple に追加)|
| `progress` callback | 同じ | 同じ |
| (なし) | Q5 = X で init 自動 labels 適用 | Q5 = X で init 自動 protection 適用(同じ哲学)|
| (なし) | `--also-labels` opt-in for apply | `--also-protection` opt-in for apply |

このパターン踏襲により、Phase 6 レビュアと将来フェーズ実装者が「Phase 5/6 と同じ構造」と理解しやすい。

## Open questions(plan で詰めるもの)

- `click` の confirmation prompt 実装(`click.confirm` vs 自前 `input()` + TTY check)
- `_run_git` / `_run_gh` の backup I/O 部分の error handling 詳細(disk full vs permission denied vs path too long vs 他 OSError 派生)
- Backup YAML の key 順序(`yaml.safe_dump(sort_keys=False)` で GitHub API の order を保つか、sort して diff しやすくするか)
- `target_branch` のハードコード `"main"` → Phase 7 MVP では OK、Phase 7.5+ で policy の `target_branches` を iterate する時のループ構造
- `python-service.yml` の `required_contexts` を空 `[]` のまま docker にするか、`["pr-gate / test"]` のような暫定値を入れるか(dogfood 時の GitHub API 実動作を見て判断)
- `github_api/protection.py` の response normalization(空の `contexts: []` vs null の扱い、GitHub API の quirks)

これらは brainstorming の境界ではなく、writing-plans / 実装時の細部判断。
