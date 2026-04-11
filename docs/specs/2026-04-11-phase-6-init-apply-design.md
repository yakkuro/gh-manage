# Phase 6 — `gh manage init` / `gh manage apply` Design Spec

**Date:** 2026-04-11
**Size:** Medium (3+ source files, 2+ pydantic schemas, 2 commands, new template directory)
**Sizing rationale:** New CLI commands + new pure-function engine + new pydantic schema + new git CLI subprocess wrapper + new template directory. Multiple files but a single coherent feature with one obvious decomposition. Not Large because it's a single subsystem (profile-based file scaffolding) with no cross-domain coupling.
**Target:** `gh-manage` (yakkuro/gh-manage)
**Goal:** Implement `gh manage init` and `gh manage apply` commands so that a fresh repo can be bootstrapped with a profile-defined set of files plus labels sync, and an existing managed repo can re-apply files (and optionally labels) safely.

## Acceptance Criteria

- [ ] `gh manage init --profile python-service` を空ディレクトリ(`git init` + `git remote add origin` 済み)で実行 → 2 つのファイルが配置される(`.github/workflows/ci.yml`, `CLAUDE.md`)
- [ ] `--dry-run`(デフォルト)で副作用なしに files diff + labels diff を表示
- [ ] `--apply` で実際にファイル配置 + labels sync を実行
- [ ] `--force` なしで `skip_if_exists: false` の既存ファイル差分があれば停止し、actionable な競合エラーを表示
- [ ] `skip_if_exists: true` のファイルは `--force` 時も上書きされない(absolute 保護)
- [ ] `gh manage apply --profile python-service`(default)は files のみ更新し、labels には触らない
- [ ] `gh manage apply --profile python-service --also-labels --apply` で files + labels 両方更新
- [ ] `gh manage apply --also-protection` は actionable error で停止("Phase 7 で実装予定")
- [ ] git repo でない / origin remote がない場合は actionable error で停止
- [ ] `uv run pytest` 全 pass(Phase 5 までの 102 件 + Phase 6 で追加されるテスト)
- [ ] `uv run mypy src/` clean(既存 yaml stub note 以外)
- [ ] `uv run ruff check src/ tests/` clean
- [ ] `uv run ruff format --check src/ tests/` clean
- [ ] dogfood smoke test: gh-manage 自身の repo で `gh manage apply --profile python-service --dry-run` がクラッシュせず実行できる

## Scope (master spec の Phase 6 から)

実装するもの:
- `gh manage init [<path>] --profile <name> [--dry-run] [--apply] [--force]`
- `gh manage apply [<path>] --profile <name> [--dry-run] [--apply] [--force] [--also-labels] [--also-protection]`
  - `--also-protection` は flag として定義するが、実行時に "not yet implemented (Phase 7)" エラーで停止

意図的に Phase 6 でやらないこと(out of scope、master spec から外す):
- `config/repos.yml` schema + parsing(Phase 7+ で実装)
- profile YAML の `extra_labels` field(Phase 6.5+)
- profile YAML の `protection_policy` / `required_contexts` field(Phase 7)
- `gh manage protection` command(Phase 7)
- TypeScript profile(`config/profiles/typescript-service.yml`)(Phase 6.5+)
- Backup of overwritten files(`.gh-manage-backup/`)— git history に依存
- Init 失敗時の rollback — `git status` での recovery に依存
- Template の変数置換 — pure file copy のみ
- `gh manage init --interactive`(対話モード)— 全フラグ明示前提
- Issue / PR template のテンプレ整備(Phase 6.5+)
- Issue #10 / #11(silent-failure-hunter の既存問題)— 別 PR

## Architecture

Phase 5 と同じ 3 層構造を踏襲する。

| Layer | 責務 | Phase 6 で追加 / 既存 |
|---|---|---|
| `commands/` | click 引数 + 出力整形 + IO orchestration | `init.py`, `apply.py`(両方スタブを書き直し) |
| `profile_sync.py` | pure-function engine: diff 計算 + apply 実行 | NEW |
| `models/profiles.py` | pydantic schema | NEW |
| `git_cli.py` | local git CLI subprocess transport + 型付きエラー階層 | NEW |
| 既存 utility 再利用 | `repo_ref.parse_repo`, `labels_sync.compute_diff/apply_diff`, `github_api.labels.list_labels`, `config.load_config` | 既存(Phase 5 の成果) |

依存方向(Phase 5 と同じレイヤリング):

```
commands/{init,apply}.py
   │
   ├─→ profile_sync.py ──→ models/profiles.py
   │       │
   │       └─→ (filesystem operations only)
   │
   ├─→ git_cli.py ──→ (subprocess to git CLI)
   │
   └─→ labels_sync.py ──→ github_api.labels ──→ github_client.py
```

`profile_sync.py` は subprocess も git も知らない。`git_cli.py` は labels と無関係。各レイヤはテストで mock しやすい。

### Resource resolution: package data

Phase 5 の `gh manage labels` は `config/labels.yml` を **CWD-relative** で読む(`DEFAULT_CONFIG_PATH = Path("config/labels.yml")`)。これは gh-manage 自身のリポジトリで実行する前提なら動くが、Phase 6 の `gh manage init` は **consumer repo の CWD で実行される** ため、gh-manage のリポジトリは見えない。

→ Phase 6 では gh-manage 内蔵データ(templates, profiles, labels.yml)を **package data** として扱い、`importlib.resources` で解決する。これにより CLI はどこから起動しても自身の data を読める。

Phase 6 で導入する **package-data の正規ロケーション**:

```
src/gh_manage/data/
├── labels.yml                        # Phase 5 の config/labels.yml が移動
├── profiles/
│   └── python-service.yml            # NEW
└── templates/
    ├── ci/python-ci.yml              # NEW
    └── claude-md/default.md          # NEW
```

**Phase 5 への影響**(意図的な小さな変更):
- `config/labels.yml` を `src/gh_manage/data/labels.yml` に移動
- `commands/labels.py` の `DEFAULT_CONFIG_PATH` を `importlib.resources.files("gh_manage.data") / "labels.yml"` 相当に変更(1 行)
- `--config <path>` フラグは不変(明示 override は引き続きサポート)
- Phase 5 の既存テストは `--config` フラグで tmp_path fixtures を渡しているため変更不要
- repo ルートの `config/` ディレクトリは Phase 6 完了後は **削除**(`src/gh_manage/data/` が単一ソース)

**Hatchling ビルド**: 既存の `[tool.hatch.build.targets.wheel] packages = ["src/gh_manage"]` 設定により、`src/gh_manage/data/` 配下の `.yml` / `.md` も自動で wheel に含まれる(Hatchling のデフォルト挙動)。`pyproject.toml` の追加設定は不要。

**`importlib.resources` 利用パターン**:

```python
from importlib.resources import files

# Profile YAML
profile_path = files("gh_manage.data.profiles") / f"{profile_name}.yml"

# Templates root
templates_root = files("gh_manage.data") / "templates"

# Default labels.yml (Phase 5 互換)
default_labels_path = files("gh_manage.data") / "labels.yml"
```

`src/gh_manage/data/` 配下には `__init__.py` を空ファイルで置いて Python パッケージ化する(`importlib.resources` の `files()` API がパッケージ前提のため)。`profiles/` も同様に `__init__.py` を持つ。`templates/` 配下は `__init__.py` を持たない(traversable resource として扱う)。

### File layout (Phase 6 で追加されるもの)

```
src/gh_manage/
├── commands/
│   ├── init.py                       # 書き直し(現状はスタブ exit 1)
│   ├── apply.py                      # 書き直し(現状はスタブ exit 1)
│   └── labels.py                     # 1 行修正(DEFAULT_CONFIG_PATH を package data 解決に)
├── models/
│   └── profiles.py                   # NEW: ProfileSpec, FileEntry
├── data/                             # NEW: package data root
│   ├── __init__.py                   # NEW: 空(パッケージマーカー)
│   ├── labels.yml                    # MOVED from config/labels.yml
│   ├── profiles/
│   │   ├── __init__.py               # NEW: 空
│   │   └── python-service.yml        # NEW
│   └── templates/                    # NEW: traversable resource
│       ├── ci/python-ci.yml          # NEW
│       └── claude-md/default.md      # NEW
├── profile_sync.py                   # NEW: pure-function engine
└── git_cli.py                        # NEW: git CLI subprocess wrapper

config/                               # DELETED in Phase 6
                                      # (内容は src/gh_manage/data/ に移動)

tests/unit/
├── git_cli/
│   ├── __init__.py
│   └── test_git_cli.py
├── models/
│   └── test_profiles.py
├── profile_sync/
│   ├── __init__.py
│   ├── test_profile_sync.py
│   └── test_golden.py                # AC #4 の golden file test
├── cli/
│   ├── test_init.py
│   └── test_apply.py
└── fixtures/
    ├── profiles/
    │   ├── basic.yml                 # 2-file profile
    │   └── invalid_version.yml       # version=99 → SchemaVersionError
    └── templates/
        ├── ci/python-ci.yml
        └── claude-md/default.md
```

## Profile schema

### `config/profiles/python-service.yml`(MVP)

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
```

### Pydantic schema (`src/gh_manage/models/profiles.py`)

```python
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class FileEntry(BaseModel):
    source: str = Field(..., description="Path under templates/, relative")
    dest: str = Field(..., description="Path under target repo root, relative")
    skip_if_exists: bool = False

    @field_validator("source", "dest")
    @classmethod
    def _no_traversal(cls, v: str) -> str:
        # Security: prevent escape from templates_root or target
        if ".." in v.split("/") or v.startswith("/"):
            raise ValueError(f"Path must not contain '..' or be absolute: {v!r}")
        return v


class ProfileSpec(BaseModel):
    version: Literal[1]
    name: str
    description: str | None = None
    files: list[FileEntry]
```

### Schema versioning

- `version: 1` は strict literal で要求
- 未対応 version(例: `version: 2`)は `SchemaVersionError` で停止(Phase 5 の `LabelsConfig` と同パターン)
- migration framework は Phase 6 では実装しない(Phase 5 と同じ判断)

## Engine: `profile_sync.py`

### Diff data structure

```python
@dataclass(frozen=True)
class FileCreate:
    source: Path        # absolute under templates_root
    dest: Path          # absolute under target


@dataclass(frozen=True)
class FileOverwrite:
    """Existing file content differs and skip_if_exists is False.
    Will be written iff apply_files_diff(force=True)."""
    source: Path
    dest: Path


@dataclass(frozen=True)
class FileSkipExists:
    """skip_if_exists=True and dest exists. Never written, even with --force."""
    dest: Path


@dataclass(frozen=True)
class FileNoop:
    """dest exists with byte-identical content."""
    dest: Path


@dataclass(frozen=True)
class ProfileFilesDiff:
    creates: tuple[FileCreate, ...]
    overwrites: tuple[FileOverwrite, ...]
    skipped: tuple[FileSkipExists, ...]
    noops: tuple[FileNoop, ...]

    @property
    def is_empty(self) -> bool:
        """No actionable changes (creates or overwrites)."""
        return not (self.creates or self.overwrites)

    @property
    def has_overwrites(self) -> bool:
        return bool(self.overwrites)
```

### Pure-function API

```python
def compute_files_diff(
    profile: ProfileSpec,
    target_root: Path,
    templates_root: Path,
) -> ProfileFilesDiff:
    """Compute the file placement diff for a profile.

    For each profile.files entry, compares dest content to source content
    byte-for-byte. Classifies into one of {Create, Overwrite, SkipExists, Noop}
    based on existence + content + skip_if_exists flag.

    Pure: reads files but writes nothing. Raises ProfileError if a source
    template is missing under templates_root.
    """


def apply_files_diff(
    diff: ProfileFilesDiff,
    *,
    force: bool = False,
    progress: Callable[[str], None] = lambda _: None,
) -> None:
    """Apply the diff. Transactional with respect to overwrite conflicts.

    Behavior:
      - Creates always written.
      - Overwrites: written iff force=True. If force=False AND overwrites
        is non-empty, raises ProfileConflictError BEFORE touching the
        filesystem (no partial writes).
      - SkipExists / Noops: no IO.

    Mid-operation IO failures (disk full, permission denied) propagate as
    OSError. Recovery via `git status`; no rollback by design.

    `progress` is called with a one-line description before each write
    operation. CLI passes click.echo; tests pass list.append.
    """
```

### Errors

```python
class ProfileError(Exception):
    """Base for profile_sync errors."""


class ProfileConflictError(ProfileError):
    """Raised when apply_files_diff is called with overwrites and force=False.

    Contains the conflict list and an actionable message instructing
    the user to re-run with --force or remove the files manually.
    """
    def __init__(self, conflicts: tuple[FileOverwrite, ...]):
        self.conflicts = conflicts
        names = "\n  ".join(str(c.dest) for c in conflicts)
        super().__init__(
            f"{len(conflicts)} file(s) would be overwritten:\n  {names}\n"
            f"Re-run with --force to overwrite, or remove the files manually."
        )


class ProfileTemplateNotFoundError(ProfileError):
    """A profile.files entry references a source path that doesn't exist
    under templates_root."""
```

## Engine: `git_cli.py`

### 役割

`github_client.py` と対称な「local git CLI 用 transport + 型付きエラー」モジュール。Phase 6 では 1 つの subprocess wrapper(`get_origin_owner_repo`)と 1 つの pure parser(`parse_origin_url`)を実装するが、Phase 7+ で `is_clean_tree` / `current_branch` などを同じモジュールに追加する箱として作る。

### Error hierarchy

```python
class GitError(Exception):
    """Base for git CLI subprocess failures."""


class GitNotInstalledError(GitError):
    """`git` CLI missing on PATH."""


class NotAGitRepoError(GitError):
    """target is not inside a git repository."""


class NoOriginRemoteError(GitError):
    """git is set up but `origin` remote is not configured."""
```

各エラーは actionable message を持つ:
- `GitNotInstalledError`: "Install git from https://git-scm.com/ and try again."
- `NotAGitRepoError`: "Not a git repository: {path}. Run `git init` first."
- `NoOriginRemoteError`: "No `origin` remote configured. Run `git remote add origin git@github.com:OWNER/REPO.git`."

### API

```python
def parse_origin_url(url: str) -> str:
    """Parse a git remote URL into 'owner/repo' form. Pure.

    Supports:
      git@github.com:owner/repo.git    → owner/repo
      git@github.com:owner/repo        → owner/repo
      https://github.com/owner/repo.git → owner/repo
      https://github.com/owner/repo    → owner/repo

    Raises ValueError on unsupported URLs (e.g., gitlab.com, ssh non-github).
    Pure: no IO.
    """


def get_origin_owner_repo(target: Path) -> str:
    """Run `git remote get-url origin` in target and parse → 'owner/repo'.

    Raises:
      GitNotInstalledError — git not on PATH
      NotAGitRepoError     — target is not inside a git work tree
      NoOriginRemoteError  — git is OK but `origin` is not set
      GitError             — other git failures (catch-all)
    """
```

`get_origin_owner_repo` の内部:
1. `subprocess.run(["git", "-C", str(target), "remote", "get-url", "origin"], ...)`
2. `FileNotFoundError` → `GitNotInstalledError`
3. `returncode != 0` を分類:
   - stderr に "not a git repository" → `NotAGitRepoError`
   - stderr に "No such remote" or "fatal: No such remote 'origin'" → `NoOriginRemoteError`
   - その他 → `GitError`
4. stdout を `parse_origin_url` に渡して owner/repo を得る

## CLI commands

### `gh manage init`

```
gh manage init [<path>] --profile <name> [--dry-run] [--apply] [--force]
```

**Flags:**
- `path`: positional, default `.`
- `--profile <name>`: required, identifies `config/profiles/<name>.yml`
- `--dry-run`: boolean, default behavior(明示も可)
- `--apply`: boolean, mutually exclusive with `--dry-run`
- `--force`: boolean, allows overwriting non-skip files

**Flow:**

```
1. target = Path(path or ".")
2. Precheck:
   a. owner_repo = git_cli.get_origin_owner_repo(target)
      → raises NotAGitRepoError / NoOriginRemoteError if needed
3. profile_path = files("gh_manage.data.profiles") / f"{name}.yml"
   profile = load_config(profile_path, ProfileSpec)
   → raises ConfigError if profile yml is missing or schema mismatch
4. templates_root = files("gh_manage.data") / "templates"
5. files_diff = profile_sync.compute_files_diff(profile, target, templates_root)
6. labels_path = files("gh_manage.data") / "labels.yml"
   labels_config = load_config(labels_path, LabelsConfig)
7. current_labels = labels_api.list_labels(owner_repo)
8. labels_diff = labels_sync.compute_diff(current_labels, labels_config)
9. Print diff (Files section + Labels section)
10. If not --apply:
    "Dry-run: {N} file changes, {M} label changes. Re-run with --apply to execute."
    return
11. If --apply:
    profile_sync.apply_files_diff(files_diff, force=force, progress=click.echo)
    labels_sync.apply_diff(labels_diff, owner_repo, progress=click.echo)
    Print "Done. Next steps:
       git add .
       git commit -m 'chore: bootstrap with gh-manage init'"
12. --apply + --dry-run → click.UsageError, exit 2
```

### `gh manage apply`

```
gh manage apply [<path>] --profile <name> [--dry-run] [--apply] [--force] [--also-labels] [--also-protection]
```

**Flags:**
- 共通: path, --profile, --dry-run, --apply, --force(init と同じ)
- `--also-labels`: boolean, default false
- `--also-protection`: boolean, default false; **実行時に常に "not yet implemented" でエラー停止**

**Flow:**

```
1-4. Same as init (target, precheck, load profile from package data,
     resolve templates_root from package data)
5. files_diff = profile_sync.compute_files_diff(...)
6. If --also-protection:
   raise ClickException(
     "--also-protection is not yet implemented (scheduled for Phase 7). "
     "Re-run without --also-protection."
   )
7. If --also-labels:
   labels_path = files("gh_manage.data") / "labels.yml"
   labels_config = load_config(labels_path, LabelsConfig)
   current_labels = labels_api.list_labels(owner_repo)
   labels_diff = labels_sync.compute_diff(current_labels, labels_config)
8. Print diff (Files section [+ Labels section if --also-labels])
9. If not --apply: "Dry-run: ..." + return
10. If --apply:
    profile_sync.apply_files_diff(...)
    if --also-labels: labels_sync.apply_diff(...)
    Print "Applied N file changes [+ M label changes]."
```

apply は init と違って "Next steps" メッセージを出さない(既存リポへの適用なので bootstrap ではない)。

### Diff display format

```
Files:
  + create   .github/workflows/ci.yml      ← templates/ci/python-ci.yml
  ≈ skip     CLAUDE.md                     (skip_if_exists, content unchanged)
  = noop     CLAUDE.md                     (already up to date)
  ! conflict .github/dependabot.yml        (would overwrite, content differs)

Labels:
  + chore    color=e1e7eb  desc='Maintenance'
  ~ bug      color=d73a4a  desc='Bug fix'
  ...

Dry-run: 1 file change, 5 label changes. Re-run with --apply to execute.
```

エラー(`--apply` 時の conflict):

```
Files:
  ! conflict .github/dependabot.yml (would overwrite, content differs)

Error: 1 file(s) would be overwritten:
  /path/to/.github/dependabot.yml
Re-run with --force to overwrite, or remove the files manually.
```

### Templates root resolution

`templates_root = importlib.resources.files("gh_manage.data") / "templates"` で解決する。`src/gh_manage/data/` が Python パッケージ(`__init__.py` 持ち)なので `files()` API で直接アクセスできる。編集可能インストール(`uv pip install -e .`)/ wheel 配布のどちらでも同じパスで動く。

## Test strategy

### `tests/unit/git_cli/test_git_cli.py` (~10 cases)

`subprocess.run` を mock するパターンは `tests/unit/github_client/test_github_client.py` を踏襲。

- `parse_origin_url`: git@ form / https form / https with .git / https without .git / malformed → ValueError(5 cases)
- `get_origin_owner_repo`:
  - 成功: stdout に valid URL → owner/repo を返す
  - subprocess returncode != 0 + stderr "not a git repository" → NotAGitRepoError
  - subprocess returncode != 0 + stderr "No such remote 'origin'" → NoOriginRemoteError
  - FileNotFoundError → GitNotInstalledError
  - その他 → GitError
- 各エラーの actionable message が含まれることを assertion(2-3 cases)

### `tests/unit/models/test_profiles.py` (~6 cases)

- 有効な v1 profile が parse できる
- `name` 欠落 → ValidationError
- 空の `files` リスト → 有効(vacuous profile)
- `version: 99` → SchemaVersionError(`load_config` 経由)
- `skip_if_exists` のデフォルトが False
- `dest: ../../etc/passwd` → ValidationError(traversal 防止)
- `dest: /absolute/path` → ValidationError

### `tests/unit/profile_sync/test_profile_sync.py` (~12 cases)

`compute_files_diff` を `tmp_path` に対して呼び出す。fixtures は inline で組み立てる(profile を pydantic で構築、template ファイルを `tmp_path` に置く)。

- 空の target → 全エントリが Create
- 既存ファイル(同内容) → Noop
- 既存ファイル(内容違い) + skip_if_exists=False → Overwrite
- 既存ファイル(内容違い) + skip_if_exists=True → SkipExists
- 既存ファイル(同内容) + skip_if_exists=True → Noop(skipped ではない: 同内容なら触る必要なし)
- source 不在 → ProfileTemplateNotFoundError
- `is_empty` プロパティ
- `has_overwrites` プロパティ
- `apply_files_diff(force=False)` + overwrites あり → ProfileConflictError(filesystem 触らない、conflict 件数を message に含む)
- `apply_files_diff(force=True)` で overwrite を実行
- `apply_files_diff` で Create を書き、SkipExists / Noop は触らない
- `progress` callback が順番に呼ばれる

### `tests/unit/profile_sync/test_golden.py` (AC #4 の golden file test)

- `tests/fixtures/profiles/basic.yml` を読み込み、`tmp_path` に apply
- 各書き出されたファイルが `tests/fixtures/templates/<source>` と byte-for-byte 一致することを assert

### `tests/unit/cli/test_init.py` (~10 cases)

`CliRunner` + `tmp_path` + mocker(`git_cli.get_origin_owner_repo`, `labels_api.list_labels`, `labels_sync.apply_diff` を mock):

- Happy path: dry-run が files diff + labels diff を print、exit 0、apply_diff 未呼出
- Happy path: --apply で files が書き出され、`labels_sync.apply_diff` が呼ばれる
- Conflict: 既存 file 差分 + skip_if_exists=false + --force なし → exit 1、conflict メッセージ
- --force で conflict 上書き
- skip_if_exists=true は --force でも touch されない
- profile not found → ConfigError → exit 1
- not a git repo → NotAGitRepoError → exit 1、actionable msg
- no origin remote → NoOriginRemoteError → exit 1、actionable msg
- --apply + --dry-run → exit 2(UsageError)
- "Next steps" メッセージが --apply 後に表示される

### `tests/unit/cli/test_apply.py` (~10 cases)

init とほぼ同じだが追加で:

- デフォルト(--also-labels なし)で labels_api.list_labels が呼ばれない
- --also-labels で labels_api.list_labels が呼ばれる
- --also-labels --apply で labels_sync.apply_diff が呼ばれる
- --also-protection → exit 1、"Phase 7" を含むメッセージ
- "Next steps" メッセージが apply では表示されない
- --also-labels なしでも files の dry-run / apply は init と同じ挙動

### Phase 5 のテストとの非干渉性

Phase 5 のテスト(`tests/unit/cli/test_labels.py`, `tests/unit/labels_sync/`, `tests/unit/github_api/labels/`, `tests/unit/github_client/`, `tests/unit/test_repo_ref.py`, `tests/unit/config/`)は Phase 6 で touch しない。Phase 6 は新しいテストファイルを追加するだけで、既存の 102 件の pass を保つ。

## エラーハンドリング戦略

`commands/init.py` と `commands/apply.py` の `_handle_errors` decorator で catch する例外型:

```python
except (
    GhError,                       # gh API failures (Phase 5)
    ConfigError,                   # config load failures (Phase 5)
    GitError,                      # git CLI failures (Phase 6 NEW)
    ProfileError,                  # profile_sync failures (Phase 6 NEW)
) as e:
    raise click.ClickException(str(e)) from e
```

`ValueError`(`parse_origin_url` の malformed URL)はそのまま propagate せず、`get_origin_owner_repo` が `GitError` にラップする責務を持つ。

## YAGNI / 設計判断のメモ

### Pure file copy(変数置換しない)

理由: Phase 6 では 1 つの profile しかなく、置換が必要な variable が現実問題として存在しない(`templates/ci/python-ci.yml` は固定値 `python-version: "3.12"` でも consumer は init 後に edit すれば良い)。Phase 6.5 以降で必要性が出てきたら `string.Template` ベースの置換を追加する。

### `extra_labels` を Phase 6 に入れない

理由: profile-specific なラベルを実装すると `LabelsConfig.with_extra(...)` のようなマージ操作が必要になる。Phase 6 のテーマは file 配置 engine なので、labels は global `config/labels.yml` のみ使う最小実装にする。マージは Phase 6.5 で別 PR。

### Backup ディレクトリを作らない

理由: `.gh-manage-backup/` のような副作用は git history で代替できる。`init`/`apply` を実行するユーザーは git repo 内で作業しているので、`git diff HEAD` で変更を確認、`git checkout` で巻き戻せる。CLI が backup directory を作ると `.gitignore` への登録など追加運用が増える。

### Init failure rollback を実装しない

理由: `apply_files_diff` は overwrite check を最初に通すので、conflict による fail はファイルを触る前に発生する。途中の OSError(disk full, permission)で fail した場合は git status で回復可能(git index に登録されていない新規ファイルは visible、既存ファイルの変更も同様)。CLI 側で transactional rollback を実装すると複雑性が増し、エラーパスのテストも増える。

### Templates を package data として配布

理由: gh-manage は `pip install`(あるいは `uv tool install`)で配布される CLI ツール。templates が CWD などに依存していると、CLI を別ディレクトリから起動した時に動かない。`importlib.resources` で gh-manage パッケージのリソースとして解決すれば、どこから起動しても動く。

### `git_cli.py` を新規モジュールとして作る

理由: Phase 7+ で `is_clean_tree`, `current_branch`, `git rev-parse` 等が必要になる見込み。Phase 6 で 1 関数だけのために箱を用意するのは over-engineering に見えるが、Phase 5 で `github_client.py` が単一責務 + 型付きエラーで作られた成功体験があり、`git_cli.py` を Phase 7+ のために対称に作っておくのが整合的。`repo_ref.py` に追加すると pure parser モジュールに subprocess 知識が漏れ込み、後から分離が必要になる。

## Phase 5 との対称性チェック

| Phase 5 (labels) | Phase 6 (profile/files) |
|---|---|
| `commands/labels.py` | `commands/init.py` + `commands/apply.py` |
| `labels_sync.py`(pure engine) | `profile_sync.py`(pure engine) |
| `models/labels.py`(LabelsConfig) | `models/profiles.py`(ProfileSpec) |
| `github_api/labels.py`(resource) | (Phase 6 では使い回し、追加なし) |
| `github_client.py`(transport) | (Phase 6 では使い回し、追加なし) |
| (なし) | `git_cli.py`(transport, NEW) |
| `LabelsDiff`(creates/renames/updates/deletes tuples) | `ProfileFilesDiff`(creates/overwrites/skipped/noops tuples) |
| `compute_diff` + `apply_diff`(fail-fast) | `compute_files_diff` + `apply_files_diff`(transactional conflict check) |
| `--apply` / `--dry-run` mutually exclusive | 同じ |
| `_handle_errors` decorator | 同じ |
| `progress` callback | 同じ |

このパターン踏襲により、レビューアと将来の Phase の実装者が「Phase 5 と同じ構造」と理解しやすい。

## Open questions(plan で詰めるもの)

これらは設計上の判断ではなく、実装計画段階の細部:

- `src/gh_manage/data/templates/ci/python-ci.yml` の中身(consumer が `yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@main` を呼ぶ最小 yml)
- `src/gh_manage/data/templates/claude-md/default.md` の中身(プロジェクト名を空欄にしたスタブ)
- `src/gh_manage/data/profiles/python-service.yml` の正確な YAML(version field 含む)
- `git_cli.py` の stderr 文字列マッチング(`git` の locale によって変わる可能性 — `LC_ALL=C` で固定するか、別の検出方法を取るか)
- diff display の color(click の secho 使うか、plain text のまま)
- `src/gh_manage/data/__init__.py` と `src/gh_manage/data/profiles/__init__.py` の docstring(短く 1 行)
- `commands/labels.py:DEFAULT_CONFIG_PATH` の正確な書き換え方(`importlib.resources.files()` を module-level で評価するか lazy にするか — Python 3.12 では eager で問題なし)

これらは brainstorming セクションで固めなくても、writing-plans のステップで実装と一緒に決めて良い項目。
