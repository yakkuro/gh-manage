# Phase 8 — `gh manage drift` (drift scanner) design

**Date:** 2026-04-11
**Size:** Medium (3+ files, design judgments on check registry, Finding model, scenario fixture schema)
**Sizing Rationale:** 3 new source files, 4 modified test files, 11 fixture YAMLs, +~48 tests. Bigger than a Small (1-2 files) but one implementation plan can cover it end-to-end. Not Large (multi-phase / multi-subsystem).
**Target:** `yakkuro/gh-manage`
**Goal:** Ship a single-repo `gh manage drift` CLI that compares a consumer repo's current state (labels, branch protection, profile files) to the profile + policies defined in `gh-manage`, reporting per-finding drifts in stdout/JSON/markdown-file format. Tag `cli/v0.5.0`.

---

## Acceptance Criteria

- [ ] `gh manage drift --profile python-service` runs against `gh-manage` itself and prints a human-readable stdout report with 0 findings (or the actual drift state, if any)
- [ ] `gh manage drift --profile python-service --report-mode json` emits a stable JSON document whose top-level shape is `{"findings": [...], "summary": {...}}`
- [ ] `gh manage drift --profile python-service --report-mode markdown-file --output drift.md` writes a markdown report to `drift.md`
- [ ] `gh manage drift --profile python-service --severity high` filters findings to `critical` + `high` only
- [ ] `tests/unit/drift/` contains **≥11 scenario fixtures** covering labels, protection, profile_files checks
- [ ] `uv run pytest tests/unit/drift` all pass
- [ ] Coverage on `src/gh_manage/drift_sync.py` is **≥90%** (master spec L5 target)
- [ ] `register_check` decorator pattern lets a new check be added by writing a function + decorator, with zero orchestrator edits
- [ ] All 3 checks return `tuple[Finding, ...]` and are independently testable
- [ ] `_handle_errors` decorator in `commands/drift.py` catches `(GhError, ConfigError, GitError, ProfileError, ProtectionError, DriftError)`
- [ ] Path traversal defense in `_resolve_profile_path` follows Phase 6/7 pattern (regex pre-filter + `Path.resolve()` + `is_relative_to()` check)
- [ ] `gh manage drift` always exits 0 when the scan completes successfully, regardless of findings count
- [ ] Production check on `gh-manage` itself (golden test): `check_labels + check_protection + check_profile_files` against bundled production data returns zero findings
- [ ] Tag `cli/v0.5.0` points at the bump commit, GitHub release published, install smoke test passes
- [ ] 12 deferred items (see Out of Scope) are filed as GitHub Issues with labels `phase-8.5`, `deferred-from-phase-8`, and links to this spec + the feature PR

---

## Scope & Non-Goals

### In scope

- `src/gh_manage/drift_sync.py`: engine module with `Finding`, `ScanContext`, `DriftError`, check registry, 3 checks, 3 report formatters
- `src/gh_manage/commands/drift.py`: click CLI with `drift` command (single subcommand, no group)
- `src/gh_manage/cli.py`: register the new command
- 3 checks: `check_labels`, `check_protection`, `check_profile_files`
- 3 report modes: `stdout`, `json`, `markdown-file`
- `--severity <critical|high|medium|low>` filtering
- `--output <path>` optional destination (defaults to stdout for all modes)
- 11 scenario fixtures covering all 3 checks
- Golden/self-dogfood test
- Test count target: ~+48 new tests

### Out of Scope (deferred — filed as GitHub Issues post-merge)

See [Out of Scope](#out-of-scope--deferred-to-phase-85) section below for the full list and rationale. Summary: workflow pinning check, `--all` / `repos.yml`, Issue mode, weekly cron workflow, 24h double-check rule, `--fix` interactive mode, scheduled-mode rate limit retry, partial scan, directory-based fixture format, Unicode / high-cardinality report format edge cases, Rulesets API support, L6/L7 integration tests.

---

## Architecture

Phase 5/6/7 の 3-layer パターンを踏襲:

```
commands/drift.py (click CLI)
    ↓
drift_sync.py (engine: pure functions + check registry + report formatters)
    ↓
既存の resource layer を再利用:
  - github_api.labels                (Phase 5)
  - github_api.protection            (Phase 7)
  - models.profiles                  (Phase 2)
  - models.labels                    (Phase 1)
  - models.branch_protection         (Phase 7)
  - labels_sync.compute_diff         (Phase 5)  ─┐
  - protection_sync.compute_protection_diff (Phase 7)  ─┴─ 差分計算を再利用、Finding に adapter で変換
```

新規レイヤは `drift_sync.py` のみ。既存の `compute_diff` / `compute_protection_diff` は drift 検知のためにリファクタ不要で、その結果(`LabelsDiff`, `ProtectionDiff`)を Finding リストに変換する薄い adapter 関数を `drift_sync.py` 内に書く。

### Check registry pattern

```python
CheckFn = Callable[["ScanContext"], tuple[Finding, ...]]
_CHECKS: list[CheckFn] = []

def register_check(fn: CheckFn) -> CheckFn:
    _CHECKS.append(fn)
    return fn

@register_check
def check_labels(ctx: ScanContext) -> tuple[Finding, ...]: ...

@register_check
def check_protection(ctx: ScanContext) -> tuple[Finding, ...]: ...

@register_check
def check_profile_files(ctx: ScanContext) -> tuple[Finding, ...]: ...

def run_all_checks(ctx: ScanContext) -> tuple[Finding, ...]:
    return tuple(chain.from_iterable(check(ctx) for check in _CHECKS))
```

新 check 追加は `@register_check` を付けた関数を 1 つ書くだけで orchestrator を触らない(Phase 8.5 以降の `check_workflow_pinning` 追加が 1 ファイル 1 commit で完結)。

### `ScanContext` dataclass

checks が必要とする入力を 1 束にして渡す:

```python
@dataclass(frozen=True)
class ScanContext:
    path: Path                        # local repo root (for file checks)
    repo: str                         # "owner/repo" (for API checks)
    profile: ProfileSpec              # loaded profile
    labels_config: LabelsConfig       # loaded bundled labels.yml
    bp_config: BranchProtectionConfig | None  # None if profile.protection_policy is None
```

Checks は `ctx` から必要な情報だけを pull する。checks は互いを知らない(registry pattern)。

### IO 境界

`drift_sync.py` 内の check 関数は **label/protection API 呼び出しを直接行う**。これは `profile_sync` / `labels_sync` / `protection_sync` と対称的ではないが、scanner は「現状を取ってきて評価する」のが本質なので IO を中で持つ方が自然。fixture テストでは subprocess / API を mock する(Phase 5/7 と同じパターン)。

`check_profile_files` のみ `ctx.path` から直接 disk を読む(`importlib.resources` で template content を取得して比較)。

---

## Components

### New source files

| Path | Responsibility | 推定 LOC |
|---|---|---|
| `src/gh_manage/drift_sync.py` | Engine: `Finding` dataclass, `ScanContext`, `DriftError` hierarchy, `@register_check` registry, 3 check functions, `_filter_by_severity`, adapter functions, `format_stdout_report` / `format_json_report` / `format_markdown_report` pure functions | ~400 |
| `src/gh_manage/commands/drift.py` | click CLI: path + `--profile` + `--severity` + `--report-mode` + `--output` options, loads config via `load_config`, builds `ScanContext`, calls `run_all_checks`, invokes the right formatter, writes to stdout or file | ~150 |

### New test files

| Path | Purpose |
|---|---|
| `tests/unit/drift/__init__.py` | package marker |
| `tests/unit/drift/conftest.py` | `DriftScenario` pydantic model + `_load_scenarios()` glob loader + `tmp_repo_from_scenario()` helper that expands `repo_files` to a `tmp_path` tree (resolves `__USE_TEMPLATE__` sentinel via `importlib.resources`) |
| `tests/unit/drift/test_drift_sync.py` | L1-L5 tests: Finding frozen-ness, registry, filter, adapters, scenario-driven tests, golden test |
| `tests/unit/drift/test_report_format.py` | L6 tests: unit tests for 3 `format_*_report` functions |
| `tests/unit/cli/test_drift.py` | L7 tests: click tests for `gh manage drift` |

### New fixture files (11 scenarios)

| Directory | Scenarios |
|---|---|
| `tests/fixtures/drift-scenarios/labels/` | `missing-priority-labels.yml`, `extra-unknown-label.yml`, `color-mismatch.yml`, `description-mismatch.yml` |
| `tests/fixtures/drift-scenarios/protection/` | `enforce-admins-weakened.yml`, `required-contexts-shrunk.yml`, `reviews-removed.yml`, `allow-force-pushes-enabled.yml` |
| `tests/fixtures/drift-scenarios/profile_files/` | `claude-md-modified.yml`, `ci-yml-drifted.yml`, `missing-file.yml` |

### Modified source files

| Path | Change |
|---|---|
| `src/gh_manage/cli.py` | import `drift` from `commands.drift` and register: `main.add_command(drift)` |

### File section conventions

`drift_sync.py` は ~400 LOC になるので明示的な section comments でナビゲーションする:

```python
# ========== Data Model ==========
# Finding, ScanContext

# ========== Error Hierarchy ==========
# DriftError, DriftOutputError

# ========== Check Registry ==========
# _CHECKS, register_check, run_all_checks, _filter_by_severity

# ========== Adapters ==========
# _labels_diff_to_findings, _protection_diff_to_findings

# ========== Checks ==========
# check_labels, check_protection, check_profile_files

# ========== Report Formatters ==========
# format_stdout_report, format_json_report, format_markdown_report
```

1 ファイルで閉じる理由: Phase 7 の `protection_sync.py` が同様の 600 LOC 構成で扱いやすかった。`drift_sync.py` が 700 LOC を超えたら Phase 8.5 で `drift/checks/`, `drift/report/` のサブモジュール化を検討する。

---

## Data Model

### `Finding` dataclass

```python
@dataclass(frozen=True)
class Finding:
    """One drift finding. Frozen, comparable, hashable."""

    severity: Literal["critical", "high", "medium", "low"]
    check: str              # "labels" | "protection" | "profile_files"
    repo: str               # "owner/repo"
    field_path: str         # e.g. "labels[priority/critical]", "enforce_admins", "CLAUDE.md"
    current_value: Any      # 現在の値 (backward/after rendering)
    desired_value: Any      # 期待される値
    message: str            # 人間向け 1 行説明
    remediation: str | None = None  # 修復コマンド文字列
```

**粒度ルール: per-item**。10 個のラベルが欠けているなら 10 findings(1 item につき 1 finding)。group 化は report 層で必要に応じてやる(Finding 自体は atomic に保つ)。

**軸選択の理由**:
- `field_path` / `current_value` / `desired_value` は Phase 7 の `ProtectionFieldChange` と整合させ、report 層で before/after 差分を描画するのに load-bearing
- `data: dict` は型が緩すぎて後で拡張が効きにくいため採用しない
- `remediation` は `str | None`(最初は単一コマンド文字列)。後で list やテンプレート化する余地は残す
- `repo: str` は残す(将来 `--all` で複数 repo scan するときに必須)

### `ScanContext` dataclass

```python
@dataclass(frozen=True)
class ScanContext:
    path: Path
    repo: str
    profile: ProfileSpec
    labels_config: LabelsConfig
    bp_config: BranchProtectionConfig | None
```

### Error hierarchy

```python
class DriftError(Exception):
    """Base for drift_sync errors. Caught by commands/_handle_errors."""

class DriftOutputError(DriftError):
    """--output <path> への書き込み失敗。disk full, permissions, or
    parent directory missing."""
```

最小限。ほぼ既存エラー型(`GhError`, `ConfigError`, `GitError`, `ProfileError`, `ProtectionError`)を再利用する。

---

## CLI Interface

```
gh manage drift [<path>] --profile <name>
                [--severity <critical|high|medium|low>]
                [--report-mode <stdout|json|markdown-file>]
                [--output <path>]
```

- `[<path>]` デフォルト `.` (current directory)、Phase 7 と同じ `click.Path(exists=True, file_okay=False, path_type=Path)` + `Path.resolve()`
- `--profile` 必須、bundled profile 名 (e.g., `python-service`)。path traversal 防御は Phase 6/7 と同じ `_resolve_profile_path` pattern
- `--severity` default は最低レベル(`low`)。指定 severity 以上が表示される (階層: critical > high > medium > low)
- `--report-mode` default は `stdout`。値は `click.Choice(["stdout", "json", "markdown-file"])`
- `--output` default は `None`(stdout)。`None` なら全 mode で stdout に出力、path 指定時は file に書き込み

**Mode と destination は分離**:
- `--report-mode` = **format** (stdout / json / markdown-file)
- `--output` = **destination** (省略時 stdout、指定時 file)

これで `--report-mode json --output drift.json` と `--report-mode markdown-file --output drift.md` が対称に書ける。`--output` 省略時は全 mode で stdout に吐く(CI で `| jq '...'` したい場合や、markdown-file mode を stdout で `| less` したい場合に便利)。

### Exit codes

| Exit code | 条件 |
|---|---|
| 0 | scan completed successfully, regardless of findings count |
| 1 | domain error (GhError, ConfigError, GitError, ProfileError, ProtectionError, DriftError) → actionable message |
| 2 | click UsageError (invalid `--severity` value, invalid `--report-mode`, missing required `--profile`) |

**Drift 検出は exit 0**(spec 通り、「drift はレポート対象であってエラーではない」)。CI で drift を failing 扱いしたい場合は `--report-mode json` で parse させる方針。

---

## Data Flow

実行例: `gh manage drift --profile python-service --severity high --report-mode markdown-file --output drift.md`

```
1. CLI parsing (click)
   └─ path=".", profile="python-service", severity="high",
      report_mode="markdown-file", output="drift.md"

2. _handle_errors decorator wraps the entire body

3. target = path.resolve()

4. owner_repo = git_cli.get_origin_owner_repo(target)
   → "yakkuro/gh-manage"

5. Config loading
   profile       = load_config(_resolve_profile_path("python-service"), ProfileSpec)
   labels_config = load_config(_resolve_default_labels_path(), LabelsConfig)
   bp_config     = load_config(_resolve_branch_protection_path(), BranchProtectionConfig)
                   # profile.protection_policy が None なら bp_config も None

6. ctx = ScanContext(
       path=target, repo="yakkuro/gh-manage",
       profile=profile, labels_config=labels_config, bp_config=bp_config,
   )

7. findings = run_all_checks(ctx)

   check_labels(ctx):
     current = labels_api.list_labels(ctx.repo)
     diff    = labels_sync.compute_diff(current, ctx.labels_config)
     return _labels_diff_to_findings(diff, ctx.repo)

   check_protection(ctx):
     if ctx.profile.protection_policy is None:
         return ()
     policy = ctx.bp_config.policies[ctx.profile.protection_policy]
     try:
         current = protection_api.get_branch_protection(ctx.repo, "main")
     except GhNotFoundError:
         current = {}
     diff = compute_protection_diff(current, policy, ctx.profile, "main")
     return _protection_diff_to_findings(diff, ctx.repo)

   check_profile_files(ctx):
     findings = []
     for entry in ctx.profile.files:
         template = _read_template_content(entry.source)  # importlib.resources
         local = ctx.path / entry.dest
         if not local.exists():
             findings.append(missing_file_finding)
             continue
         if hash(local.read_text()) != hash(template):
             severity = "low" if entry.skip_if_exists else "medium"
             findings.append(content_mismatch_finding)
     return tuple(findings)

8. filtered = _filter_by_severity(all_findings, min_severity="high")
   階層: critical > high > medium > low

9. Format selection
   match report_mode:
       "stdout"        → format_stdout_report(filtered)
       "json"          → format_json_report(filtered)
       "markdown-file" → format_markdown_report(filtered)
   rendered = <str>

10. Output destination
    if output is None:
        click.echo(rendered)
    else:
        try:
            Path(output).write_text(rendered, encoding="utf-8")
        except OSError as e:
            raise DriftOutputError(
                f"Cannot write drift report to {output}: {e}. "
                f"Check disk space, write permissions, and that the parent "
                f"directory exists."
            ) from e
        click.echo(f"Report written to {output}")

11. return  # exit 0 always
```

### Severity mapping per check

| Check | 事象 | Severity | 根拠 |
|---|---|---|---|
| `check_labels` | profile にあって repo に無い | **high** | CI/ラベル運用が破綻する可能性 |
| `check_labels` | repo にあって profile に無い | **low** | ユーザーが意図的に追加した可能性あり、削除提案は慎重に |
| `check_labels` | color mismatch | **medium** | 視認性のみ、運用影響は小さい |
| `check_labels` | description mismatch | **low** | informational |
| `check_protection` | downgrade(Phase 7 の 13 rules で検出) | **critical** | セキュリティガード弱体化、最優先対処 |
| `check_protection` | non-downgrade drift(強化側の差分など) | **medium** | 意図的な強化の可能性もあり、critical ほどではない |
| `check_profile_files` | ファイルが存在しない(`skip_if_exists: false`) | **medium** | init が未実行、または削除された状態 |
| `check_profile_files` | 内容差分(`skip_if_exists: false`) | **medium** | consumer repo が手動編集されている |
| `check_profile_files` | 内容差分(`skip_if_exists: true`) | **low** | ユーザー編集許可されたファイル。informational |

### Report format shapes

**`format_stdout_report`** — 人間向けカラム表示:

```
Drift report for yakkuro/gh-manage (main)

  [CRITICAL] protection/enforce_admins
    Admin enforcement disabled (desired: True, current: False)
    Fix: gh manage protection sync . --profile python-service --apply

  [HIGH] labels[priority/critical]
    Label 'priority/critical' is missing from the repository
    Fix: gh manage labels sync . --apply

  [MEDIUM] labels[type/bug]
    Label 'type/bug' has drifted (color: d73a4a → d93f0b)
    Fix: gh manage labels sync . --apply

Summary: 1 critical, 1 high, 1 medium, 0 low — 3 findings total.
```

**`format_json_report`** — 安定した JSON schema:

```json
{
  "version": 1,
  "repo": "yakkuro/gh-manage",
  "findings": [
    {
      "severity": "critical",
      "check": "protection",
      "repo": "yakkuro/gh-manage",
      "field_path": "enforce_admins",
      "current_value": false,
      "desired_value": true,
      "message": "Admin enforcement disabled",
      "remediation": "gh manage protection sync . --profile python-service --apply"
    }
  ],
  "summary": {
    "critical": 1,
    "high": 0,
    "medium": 0,
    "low": 0,
    "total": 1
  }
}
```

**`format_markdown_report`** — GitHub-flavored markdown, Issue/PR 向け:

```markdown
# Drift report — `yakkuro/gh-manage` (main)

**Summary**: 1 critical, 1 high, 1 medium, 0 low — 3 findings

## Critical

### `protection/enforce_admins`

Admin enforcement disabled.

- **Current**: `False`
- **Desired**: `True`
- **Fix**: `gh manage protection sync . --profile python-service --apply`

## High

### `labels[priority/critical]`

Label `priority/critical` is missing from the repository.

- **Fix**: `gh manage labels sync . --apply`

## Medium

### `labels[type/bug]`

Label `type/bug` has drifted (color).

- **Current**: `d73a4a`
- **Desired**: `d93f0b`
- **Fix**: `gh manage labels sync . --apply`
```

---

## Error Handling

### `_handle_errors` decorator (`commands/drift.py`)

```python
except (
    GhError,
    ConfigError,
    GitError,
    ProfileError,
    ProtectionError,
    DriftError,
) as e:
    raise click.ClickException(str(e)) from e
```

### Error paths

| パス | 発生源 | 扱い |
|---|---|---|
| Profile 解決失敗(名前不正、ファイルなし) | `_resolve_profile_path` | `ConfigFileNotFoundError` → ClickException (exit 1) |
| Profile YAML invalid | `load_config` | `ConfigValidationError` → ClickException (exit 1) |
| git origin 未設定/parse 失敗 | `git_cli.get_origin_owner_repo` | `GitError` → ClickException (exit 1) |
| gh CLI 認証失敗 | `labels_api.list_labels` | `GhAuthError` → ClickException (exit 1, `gh auth login` 案内) |
| gh api rate limit | 同上 | `GhRateLimitError` → ClickException (exit 1) — scheduled mode retry は Phase 8.5+ |
| 404 on labels endpoint | `labels_api.list_labels` | `GhNotFoundError` → empty list として扱い(ラベル未設定) |
| 404 on protection endpoint | `protection_api.get_branch_protection` | `GhNotFoundError` → empty dict として扱い(drift として検出) |
| `profile.protection_policy is None` | N/A | `check_protection` が `()` を返す(エラーではない) |
| `profile.files: []` | N/A | `check_profile_files` が `()` を返す |
| `branch-protection.yml` に profile が参照する policy が無い | config load | `ProtectionPolicyNotFoundError` → ClickException (exit 1) |
| profile.files[] の local file が読めない(permissions 等) | `check_profile_files` | `OSError` → 伝播 → ClickException (exit 1) |
| `--output <path>` 書き込み失敗 | CLI output step | `OSError` → `DriftOutputError from e` → ClickException (exit 1) |
| `--severity` / `--report-mode` に不正値 | click validation | UsageError (exit 2) |

### Silent failure 禁止

- bare `except:` や `except Exception: pass` は一切書かない(Phase 5/6/7 と同じ原則)
- `check_profile_files` で file read が失敗したら skip せず raise(scheduled mode の partial scan は Phase 8.5 以降)
- `OSError` は必ず具体メッセージ付きで再 raise(permissions/disk/file-not-found を区別して actionable にする)

### Fail-fast vs partial scan

MVP は **fail-fast**(1 check が raise したら全体が abort)。理由:
- 実運用で drift scan が走るのは主に dev が手動で `gh manage drift` を叩くとき。エラーを silent に skip するより即座に表示した方が問題が早く分かる
- scheduled mode(`.github/workflows/drift-scanner.yml`)は Phase 8 では作らない
- Phase 8.5 で scheduled mode を追加するときに `--partial` flag を追加する余地を残す

**例外**: `GhNotFoundError` は例外ではなく **情報シグナル**として扱う。labels 404 → empty list、protection 404 → empty dict。

---

## Testing Strategy

TDD 必須。`superpowers:test-driven-development` スキルに従う。カバレッジ目標: `drift_sync.py` **90%**(L5 target)、`commands/drift.py` 85%(L4 target)。

### Test layer structure

| Layer | File | 対象 | Test count |
|---|---|---|---|
| L1: Finding/dataclass | `test_drift_sync.py::test_finding_*` | `Finding` frozen-ness, severity literal, equality | ~5 |
| L2: Registry | `test_drift_sync.py::test_registry_*` | `register_check`, `run_all_checks`, 呼び出し順序 | ~3 |
| L3: Severity filter | `test_drift_sync.py::test_filter_by_severity_*` | 階層比較, empty input, all severities | ~4 |
| L4: Adapter (diff → findings) | `test_drift_sync.py::test_labels_diff_to_findings`, `test_protection_diff_to_findings` | `LabelsDiff` / `ProtectionDiff` → `tuple[Finding]` の変換 | ~6 |
| L5: Scenario (fixture-driven) | `test_drift_sync.py::test_scenario` | 11 scenario YAML を pytest-parametrize | 11 |
| L5: Golden | `test_drift_sync.py::test_golden_production_data` | production config で `run_all_checks` → zero findings | 1 |
| L6: Report formatters | `test_report_format.py` | `format_*_report` unit tests | ~9 |
| L7: CLI | `test_cli/test_drift.py` | click invocation: 各 `--report-mode`, `--severity`, `--output`, path traversal, profile not found, GhAuthError, exit 0 | ~10 |

**合計見込: ~49 new tests**

### Scenario fixture schema

**1 scenario = 1 YAML ファイル**、check ごとにディレクトリ分け:

```yaml
# tests/fixtures/drift-scenarios/labels/missing-priority-labels.yml
name: missing-priority-labels
description: "Profile ships priority/* labels but repo has none"
check: labels
repo: yakkuro/test-fixture
profile: python-service
inputs:
  current_labels:
    - {name: "type/bug", color: "d73a4a", description: "..."}
    - {name: "type/feature", color: "a2eeef", description: "..."}
expected_findings:
  - severity: high
    check: labels
    field_path_contains: "priority/critical"
    message_contains: "missing"
  - severity: high
    check: labels
    field_path_contains: "priority/high"
    message_contains: "missing"
```

**Sentinel `__USE_TEMPLATE__`**: `inputs.repo_files` で「差分なし」(template content そのまま)を表現:

```yaml
inputs:
  repo_files:
    CLAUDE.md: |
      # MY PROJECT
      (local edits)
    .github/workflows/ci.yml: "__USE_TEMPLATE__"  # loader が template content で置換
```

### Scenario loader (`conftest.py`)

```python
class ExpectedFinding(BaseModel):
    severity: Literal["critical", "high", "medium", "low"]
    check: str
    field_path_contains: str | None = None
    message_contains: str | None = None

class ScenarioInputs(BaseModel):
    current_labels: list[dict[str, str]] | None = None
    current_protection: dict[str, Any] | None = None
    repo_files: dict[str, str] | None = None

class DriftScenario(BaseModel):
    name: str
    description: str
    check: Literal["labels", "protection", "profile_files"]
    repo: str
    profile: str
    inputs: ScenarioInputs
    expected_findings: list[ExpectedFinding]

def _load_scenarios() -> list[tuple[Path, DriftScenario]]:
    root = Path(__file__).parent.parent.parent / "fixtures" / "drift-scenarios"
    return [(yml, DriftScenario(**yaml.safe_load(yml.read_text())))
            for yml in sorted(root.rglob("*.yml"))]

@pytest.fixture(
    params=_load_scenarios(),
    ids=lambda p: p[0].stem,  # file stem がテスト名に
)
def drift_scenario(request) -> tuple[Path, DriftScenario]:
    return request.param
```

### Scenario test assertion

**順序非依存 + 完全一致**:

```python
def _matches(actual: Finding, expected: ExpectedFinding) -> bool:
    if actual.severity != expected.severity:
        return False
    if actual.check != expected.check:
        return False
    if expected.field_path_contains and expected.field_path_contains not in actual.field_path:
        return False
    if expected.message_contains and expected.message_contains not in actual.message:
        return False
    return True

def test_scenario(drift_scenario, mocker, tmp_path):
    _, scenario = drift_scenario

    # 1. Profile + config を package data から load
    profile = load_config(_resolve_profile_path(scenario.profile), ProfileSpec)
    labels_config = load_config(_resolve_default_labels_path(), LabelsConfig)
    bp_config = load_config(_resolve_branch_protection_path(), BranchProtectionConfig)

    # 2. repo_files を tmp_path に展開 (sentinel 解決)
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    if scenario.inputs.repo_files:
        for rel_path, content in scenario.inputs.repo_files.items():
            if content == "__USE_TEMPLATE__":
                content = _read_template_for(profile, rel_path)
            target = repo_path / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)

    # 3. API mock
    if scenario.inputs.current_labels is not None:
        mocker.patch(
            "gh_manage.drift_sync.labels_api.list_labels",
            return_value=[LabelInfo(**lbl) for lbl in scenario.inputs.current_labels],
        )
    if scenario.inputs.current_protection is not None:
        mocker.patch(
            "gh_manage.drift_sync.protection_api.get_branch_protection",
            return_value=scenario.inputs.current_protection,
        )

    # 4. ScanContext を組んで該当 check だけ呼ぶ
    ctx = ScanContext(
        path=repo_path, repo=scenario.repo, profile=profile,
        labels_config=labels_config, bp_config=bp_config,
    )
    check_fn = {"labels": check_labels,
                "protection": check_protection,
                "profile_files": check_profile_files}[scenario.check]
    findings = check_fn(ctx)

    # 5. 完全一致 + 順序非依存で assertion
    assert len(findings) == len(scenario.expected_findings), (
        f"Expected {len(scenario.expected_findings)} findings, got {len(findings)}: {findings}"
    )
    for expected in scenario.expected_findings:
        matches = [f for f in findings if _matches(f, expected)]
        assert matches, f"No finding matches expected {expected}; got {findings}"
```

### Mock boundaries

- `gh_manage.drift_sync.labels_api.list_labels` — drift_sync が `from gh_manage.github_api import labels as labels_api` でインポート。Phase 7 の protection sync と同じ mock パス pattern
- `gh_manage.drift_sync.protection_api.get_branch_protection` — 同パターン
- `git_cli.get_origin_owner_repo` は scenario test では mock せず、CLI test でのみ mock

### Golden test(self-dogfood)

Phase 7 と同様、production config(`branch-protection.yml`, `python-service.yml`, `labels.yml`)で `run_all_checks` を回して `findings == ()` になることを確認する test を 1 つ入れる。API は mock するが、config のロードと check ロジックは本物を通す。

---

## Out of Scope — Deferred to Phase 8.5+

以下はすべて Phase 8 feature PR マージ後に **GitHub Issues として起票**する(`gh issue create` で 12 件一括、ラベル `phase-8.5`, `deferred-from-phase-8`)。

| # | Item | Priority | 延期理由 |
|---|---|---|---|
| 1 | `check_workflow_pinning`(`@main` / missing tag detection) | medium | Content hash 比較は `check_profile_files` でカバー。Pinning validation は独立した関心事で MVP の 3 checks と orthogonal |
| 2 | `--all` flag + `config/repos.yml`(multi-repo scan) | high | 現時点で gh-manage が管理している repo は少数。まず single-repo の精度を確立する方が先 |
| 3 | `--report-mode issue`(GitHub Issue 自動生成/更新/クローズ) | high | Issue body format 設計 + state 管理 + 冪等性テストで 1 phase 相当のボリューム |
| 4 | `.github/workflows/drift-scanner.yml` weekly cron | high | cron は Issue mode とペア。Issue mode なしで cron だけ動かしても通知手段がない |
| 5 | 24h double-check rule for Issue auto-close | high | #3 と不可分 |
| 6 | `--fix` interactive mode | medium | 実運用で使いやすいかは drift scanner を回してみないと判断不能。MVP では remediation を markdown report に表示するだけ |
| 7 | Scheduled mode rate limit retry | medium | Scheduled mode 自体が Phase 8 にない |
| 8 | Partial scan on check failure / `--continue-on-error` | low | Fail-fast の方が debug しやすい |
| 9 | Directory-based fixture for complex profile_files scenarios | low | MVP の 3 scenario は inline で書ける |
| 10 | Report format edge cases(Unicode, high-cardinality, truncation) | low | Dogfood で発見次第 Issue 化 |
| 11 | Rulesets API support | low | GitHub の announcement 次第 |
| 12 | L6 golden file test for `templates/` + L7 real API integration test | medium | Master spec で Phase 9 の v1.0 release gate |

各 Issue は:
- タイトル: `[Phase 8.5+] <feature>`
- ラベル: `phase-8.5`, `deferred-from-phase-8`, `type/feature` or `type/refactor`
- 本文: この section の該当行を引用 + Phase 8 feature PR (#<number>) への link + この spec へのリンク

---

## Release Plan

1. Phase 8 feature PR: `feat/phase-8-drift` → `main`(squash merge)
2. `chore/bump-cli-v0.5.0` PR(3 箇所 + uv.lock): `pyproject.toml`, `src/gh_manage/__init__.py`, `tests/test_sanity.py`
3. Tag `cli/v0.5.0` on the bump commit
4. GitHub release note(Phase 7 の形式を踏襲、新 command + severity mapping + deferred items を記載)
5. Install smoke test:
   - `uv tool install --force --reinstall git+https://github.com/yakkuro/gh-manage@cli/v0.5.0`
   - `gh-manage --version` → `0.5.0`
   - `cd /tmp && gh-manage drift /home/server160/repos/gh-manage --profile python-service` → no findings, exit 0
6. Deferred items(12 件)を `gh issue create` で一括起票

## Related documents

- Master design: `docs/specs/2026-04-10-gh-manage-design.md` — Phase 8 AC, drift scanner section
- Phase 7 protection sync spec: `docs/specs/2026-04-11-phase-7-protection-design.md` — Finding structure reuse, downgrade rules
- Release checklist: `docs/release-checklist.md`
