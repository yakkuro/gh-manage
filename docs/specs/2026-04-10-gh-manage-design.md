# gh-manage: GitHub-based CI/CD, Issue Management, and Operational System

**Date**: 2026-04-10 | **Size**: Large | **Target**: `yakkuro/gh-manage`

## Sizing Rationale

新規リポジトリ、複数モジュール(Python CLI、複数 reusable workflows、composite actions、config/templates/docs)、セキュリティ考慮(GitHub PAT、branch protection downgrade 防止)、長期運用を前提とした多層アーキテクチャ、10 フェーズのロールアウト計画。Medium では収まらない。

## Goal

`~/repos/` 配下の 55 リポジトリ(および将来作成されるリポジトリ)に対して、GitHub を活用した CI/CD、Issue 管理、ブランチ保護、規約コンプライアンスを**宣言的かつ継続的に**適用するためのツール群とポリシー基盤を構築する。claude-dotfiles のポータビリティを損なわず、claude-dotfiles から gh 関連の責務を分離する。

## Background

### 現状の課題

- `~/repos/` 配下に 55 リポジトリが存在し、うち 37 リポ(67%)には GitHub Actions ワークフローが一切ない
- CI ワークフローがあるリポでも設定がバラバラで、PR レビュー品質が再現不可能
- ラベル体系・Issue テンプレ・ブランチ保護ルールが各リポ任意で、規約のドリフトが蓄積している
- `claude-dotfiles` リポジトリ内に CI スクリプト、reusable workflow、レビュー関連ルールが混在しており、Claude ハーネスとしての責務が曖昧
- 既存の `reusable-pr-gate.yml` (claude-dotfiles) は未利用のまま 1 年以上経過し、プロジェクト固有環境変数の漏れ込み、`lock-validation` ジョブの常時実行、ランタイム分岐のハードコードなど、設計品質が低い
- 新規リポジトリを立ち上げるたびに同じセットアップを手作業で繰り返している

### 着想と判断

- `claude-dotfiles` のポータビリティ(外部依存ゼロ)を最優先する方針
- 既存の gh 関連資産にとらわれず、gh-manage をクリーンスレートで再構築する
- Claude ランタイムワークフロー(Codex + 3 エージェント PR レビュー等) は claude-dotfiles に残し、gh-manage は CI 駆動型の客観的レビューを担う補完関係を取る
- 情報アーキテクチャは X + Z のハイブリッド: claude-dotfiles が Claude auto-loaded rule の単一ソース、gh-manage は自分用のローカル `CLAUDE.md` のみ所持

## Architecture

### 責務スコープ(6 ドメイン)

| ドメイン | 内容 |
|---|---|
| A | CI/CD テンプレ配布(reusable workflows、composite actions、言語別ひな形) |
| B | PR レビュー自動化(CI 駆動型、Claude 非依存、gitleaks + size warning) |
| C | Issue 管理(ラベル体系、Issue テンプレ、ラベル同期、クロスリポ Issue 俯瞰) |
| D | 新規リポ bootstrap(`gh manage init` で `.github/`、`CLAUDE.md` スタブ、labels、保護ルール一括適用) |
| E | ブランチ保護 / ruleset 管理(宣言的ポリシー、CLI から適用、downgrade 防止) |
| I | 規約コンプライアンス検査(drift scanner、scheduled + on-demand、Issue 化) |

**除外ドメイン**(将来判断): F クロスリポダッシュボード / G リリース管理 / H 依存関係管理

### 配布チャネル(Architecture #3: Pull + Push + Scheduler のハイブリッド)

```
┌─────────────────────────────────────────────────────────┐
│ gh-manage リポジトリ                                    │
│                                                         │
│  Pull channel:                                          │
│    .github/workflows/reusable-pr-gate-python.yml        │
│    .github/workflows/reusable-pr-gate-typescript.yml    │
│    .github/workflows/reusable-pr-gate-go.yml (将来)     │
│    .github/workflows/reusable-ci-review.yml             │
│                                                         │
│  Push channel (CLI):                                    │
│    src/gh_manage/ (Python, gh extension)                │
│                                                         │
│  Scheduler channel:                                     │
│    .github/workflows/drift-scanner.yml                  │
│                                                         │
│  Declarative config (正本):                             │
│    config/labels.yml                                    │
│    config/branch-protection.yml                         │
│    config/repos.yml                                     │
│    config/profiles/*.yml                                │
│                                                         │
│  Distributed templates (配布素材):                      │
│    templates/ci/ templates/issue/ templates/pr/         │
│    templates/claude-md/                                 │
└─────────────────────────────────────────────────────────┘
   │ uses:@v1           │ gh manage apply     │ cron
   ↓                    ↓                     ↓
consumer repos      consumer repos       gh-manage が
(pull model)        (push model)         他リポを走査
```

### 3 層化された CI アーキテクチャ

長期運用での崩壊を防ぐため、ランタイムごとに reusable workflow を分割し、3 層で積み上げる:

```
Layer 3: Reusable workflows (トップレベル orchestration)
  ├─ reusable-pr-gate-python.yml
  ├─ reusable-pr-gate-typescript.yml
  ├─ reusable-pr-gate-go.yml (将来)
  └─ reusable-ci-review.yml

Layer 2: Composite actions (再利用可能な原子ステップ)
  actions/
  ├─ setup-python-uv/action.yml
  ├─ setup-node-pnpm/action.yml
  ├─ run-ruff/action.yml
  ├─ run-mypy/action.yml
  ├─ run-eslint/action.yml
  ├─ run-tsc/action.yml
  ├─ run-gitleaks/action.yml
  └─ log-gh-manage-version/action.yml

Layer 1: Pure shell scripts (CI 外で単体テストできる)
  scripts/checks/
  ├─ pr-size.sh
  └─ (将来拡張分)
```

- Layer 3 は組み合わせのみを担う(ロジックを持たない)
- Layer 2 は原子ステップ(composite action なのでネスト可能)
- Layer 1 は pytest + subprocess で単体テスト可能な純 shell
- 新ランタイム追加は Layer 2 + Layer 3 の追加のみで完結し、既存は触らない

### 情報アーキテクチャ(claude-dotfiles との関係)

```
claude-dotfiles (Claude harness, 全 Claude ルール正本)
  │ 参照リンクのみ(一方向)
  ↓
gh-manage (gh ワークフロー基盤、人間向け docs、CI 配布物)
  │ 配布
  ↓
consumer repos (.github/workflows/uses:, CLAUDE.md スタブ)
```

- claude-dotfiles は gh-manage を**実行時参照しない**(可搬性維持)
- `rules/workflow-review.md`, `rules/git-workflow.md`, `rules/codex-integration.md`, `rules/issue-driven-development.md` は claude-dotfiles に残す
- gh-manage 自身は自分用ローカル `CLAUDE.md` を持つ(他リポと同等)
- gh-manage の Claude ルールはグローバルルールには影響しない

## Repository Layout

```
gh-manage/
├── .github/
│   ├── workflows/
│   │   ├── reusable-pr-gate-python.yml
│   │   ├── reusable-pr-gate-typescript.yml
│   │   ├── reusable-ci-review.yml
│   │   ├── drift-scanner.yml           # cron schedule + workflow_dispatch
│   │   ├── smoke-test.yml              # fixture を使った dogfood 検証
│   │   ├── release.yml                 # tag push 時のリリース自動化
│   │   └── ci.yml                      # gh-manage 自身の PR CI (reusable を dogfood)
│   └── ISSUE_TEMPLATE/                 # gh-manage 自身の Issue テンプレ
│
├── gh-manage                           # gh extension entrypoint (shell shim)
│
├── src/gh_manage/                      # Python パッケージ (src layout)
│   ├── __init__.py
│   ├── cli.py                          # click/typer エントリ
│   ├── config.py                       # YAML ロード & pydantic validation
│   ├── github_client.py                # `gh api` subprocess ラッパー
│   ├── commands/
│   │   ├── init.py                     # [D] 新規リポ bootstrap
│   │   ├── apply.py                    # [D] 既存リポへの部分適用
│   │   ├── labels.py                   # [C] ラベル同期
│   │   ├── protection.py               # [E] branch protection 同期
│   │   ├── drift.py                    # [I] drift 検出
│   │   └── issues.py                   # [C] クロスリポ Issue リスト(gh search の薄い wrapper)
│   ├── schemas/
│   │   ├── __init__.py                 # version dispatcher
│   │   ├── labels_v1.py                # pydantic model
│   │   ├── profile_v1.py
│   │   ├── repos_v1.py
│   │   ├── protection_v1.py
│   │   └── migrations/                 # 将来の schema migration
│   └── models/
│
├── actions/                            # Layer 2: composite actions
│   ├── setup-python-uv/action.yml
│   ├── setup-node-pnpm/action.yml
│   ├── run-ruff/action.yml
│   ├── run-mypy/action.yml
│   ├── run-eslint/action.yml
│   ├── run-tsc/action.yml
│   ├── run-gitleaks/action.yml
│   └── log-gh-manage-version/action.yml
│
├── scripts/                            # Layer 1: pure shell scripts
│   └── checks/
│       └── pr-size.sh
│
├── config/                             # 宣言的 config (正本)
│   ├── labels.yml                      # 全リポ共通ラベル体系(カテゴリ型)
│   ├── branch-protection.yml           # ポリシー定義
│   ├── repos.yml                       # 管理対象リポ + profile 割当
│   └── profiles/
│       ├── python-lib.yml
│       ├── python-service.yml
│       ├── typescript-app.yml
│       ├── go-service.yml              # 将来
│       └── minimal.yml
│
├── templates/                          # consumer repo に配布される素材
│   ├── ci/
│   │   ├── python-ci.yml
│   │   └── typescript-ci.yml
│   ├── issue/
│   │   ├── bug_report.yml              # GitHub Issue Forms (YAML)
│   │   ├── feature_request.yml
│   │   └── config.yml
│   ├── pr/
│   │   └── pull_request_template.md
│   └── claude-md/
│       └── default.md                  # 新規リポ用 CLAUDE.md スタブ
│
├── tests/
│   ├── unit/                           # mock を使った単体テスト
│   │   ├── cli/
│   │   ├── config/
│   │   ├── drift/
│   │   ├── shell/                      # Layer 1 テスト
│   │   └── templates/                  # golden file テスト
│   ├── fixtures/
│   │   ├── projects/                   # Layer 3 smoke test 用
│   │   │   ├── python-sample/
│   │   │   ├── python-lint-fail/
│   │   │   ├── python-test-fail/
│   │   │   ├── typescript-sample/
│   │   │   ├── typescript-type-fail/
│   │   │   └── ...
│   │   ├── drift-scenarios/            # Layer 5 drift test 用 YAML
│   │   │   ├── clean-repo.yml
│   │   │   ├── missing-protection.yml
│   │   │   ├── label-color-mismatch.yml
│   │   │   └── ...
│   │   └── golden/                     # Layer 6 template テスト用
│   └── integration/                    # 実 API (L7)、手動/nightly
│
├── docs/
│   ├── README.md
│   ├── architecture.md
│   ├── quick-start.md
│   ├── distribution-channels.md
│   ├── versioning.md
│   ├── release-checklist.md
│   ├── maintenance.md
│   ├── secrets-rotation.md
│   ├── consumers.md                    # 導入事例
│   ├── deprecations.md
│   ├── cli/                            # コマンドごとのドキュメント
│   │   ├── init.md
│   │   ├── apply.md
│   │   ├── labels.md
│   │   ├── protection.md
│   │   └── drift.md
│   ├── usage/                          # consumer 向け利用ガイド
│   │   ├── python.md
│   │   └── typescript.md
│   ├── migrations/
│   │   ├── template.md
│   │   └── (将来 v1-to-v2.md 等)
│   └── specs/
│       └── 2026-04-10-gh-manage-design.md  # 本 spec
│
├── CHANGELOG-reusable.md
├── CHANGELOG-cli.md
├── pyproject.toml
├── uv.lock
├── CLAUDE.md                           # gh-manage 開発用ローカル Claude ルール
├── LICENSE                             # MIT or Apache-2.0
├── README.md
└── .gitignore
```

## Components

### Layer 3: Reusable Workflows

#### `reusable-pr-gate-python.yml`

- **責務**: Python リポジトリの PR 品質ゲート。install → lint → type-check → setup → test をランナブルな順序で実行
- **入力インターフェース**: `python-version`(必須)、`lint`(bool, default true)、`type-check`(bool, default true)、`install-command`(default "uv sync")、`test-command`(default "uv run pytest")、`setup-command`(optional)
- **重要設計**: コマンド文字列ではなく boolean による opt-in/opt-out。lint 実体(ruff)と type checker(mypy)は reusable 内部に固定(ベストプラクティス強制)
- **依存**: composite actions `setup-python-uv`, `run-ruff`, `run-mypy`, `log-gh-manage-version`
- **エラーケース**: lint/type-check/test の各ステップ失敗はジョブ全体の失敗として扱う。setup-command 失敗は明示的に "setup failed" とログに出す

#### `reusable-pr-gate-typescript.yml`

- **責務**: TypeScript/Node リポジトリの PR 品質ゲート
- **入力インターフェース**: `node-version`(必須)、`lint`(bool)、`type-check`(bool)、`package-manager`(pnpm/npm/yarn、default pnpm)、`install-command`(default "pnpm install --frozen-lockfile")、`test-command`(default "pnpm test")
- **依存**: composite actions `setup-node-pnpm`, `run-eslint`, `run-tsc`, `log-gh-manage-version`
- **v0.2.0 deviation**: v0.2.0 locks to pnpm only. The `package-manager` input is NOT implemented in this release — npm and yarn support are deferred to a future phase. `run-eslint` uses `pnpm exec eslint .` against the consumer's devDependencies (eslint 10.x flat config requires peer dependencies that do not resolve cleanly through `pnpm dlx`), while `run-tsc` pins TypeScript via `pnpm --package="typescript@<pin>" dlx tsc` (pnpm 10+ requires `--package` to disambiguate the multi-bin typescript package). See `docs/specs/2026-04-10-phase-2-typescript-design.md` for the full rationale.

#### `reusable-ci-review.yml`

- **責務**: CI 駆動型の政策レビュー(Claude 非依存)。初期ラインナップは gitleaks と size warning のみ
- **入力インターフェース**: `enable-gitleaks`(default true)、`enable-size-warning`(default true)、`max-diff-lines`(default 1000、warning のみ、fail しない)
- **意図的に含めない**: commitlint(Node 依存の強制を避けるため)、PR description check(脆さのため)、SAST(誤検知の害)、LLM レビュー(claude-dotfiles 側と衝突)

### Layer 2: Composite Actions

各 composite action は独立したディレクトリに `action.yml` を持つ。バージョンは gh-manage 本体の tag に追従。

**Layer 2 共通規約**:

- 全 composite action の shell ステップは `shell: bash` を明示し、スクリプト先頭に `set -euo pipefail` を必須とする(エラーを黙殺しない)
- action の `outputs` は `GITHUB_OUTPUT` 経由で明示的に宣言する(暗黙の env 変数エクスポートは禁止)
- 失敗時には stderr に「何が失敗したか」「次に何を確認すべきか」を出力する
- 内部で呼ぶ lint/test ツールのバージョンは action 内で pin する(consumer の環境に依存しない)
- action の `inputs` には全て description を書く(使う側のドキュメント化)

- **`setup-python-uv`**: Python と uv を install(uv バージョンも pin)
- **`setup-node-pnpm`**: Node と pnpm を install(pnpm バージョンも pin)
- **`run-ruff`**: `uv tool install ruff==<pinned>` 後に `ruff check .` と `ruff format --check .`。ruff のバージョンは composite action 内で固定
- **`run-mypy`**: `uv run mypy .`
- **`run-eslint`**: `pnpm exec eslint .`
- **`run-tsc`**: `pnpm exec tsc --noEmit`
- **`run-gitleaks`**: gitleaks をインストールして diff を走査。pinned version
- **`log-gh-manage-version`**: 実行中の gh-manage のタグ / commit SHA / timestamp をログに出力(debug 用)

### Layer 1: Shell Scripts

- **`scripts/checks/pr-size.sh`**: diff の行数を受け取り、閾値超過を warning として stderr に出す(exit 0)。pytest + subprocess で単体テスト可能

### Python CLI (`src/gh_manage/`)

#### `cli.py`

- **責務**: click または typer ベースのエントリポイント。各サブコマンドを登録
- **依存**: `commands/*` の各モジュール
- **サブコマンド**: `init`, `apply`, `labels`, `protection`, `drift`, `issues`

#### `config.py`

- **責務**: YAML config ファイルをロードし、schema version を検出して対応する pydantic model で validation
- **入力**: ファイルパス または Path オブジェクト
- **出力**: validated pydantic model インスタンス
- **エラーケース**: ファイル不在、YAML 構文エラー、schema version 未対応、pydantic validation 失敗 — それぞれ明確なエラーメッセージで raise

#### `github_client.py`

- **責務**: `gh api` と `gh` サブコマンドの subprocess 呼び出しを集約
- **インターフェース**:
  ```python
  def run_gh(args: list[str]) -> GhResult
  def run_gh_api(endpoint: str, method: str = "GET", fields: dict | None = None) -> dict
  ```
- **依存**: `gh` CLI が PATH に存在すること(ユーザーが事前に `gh auth login` 済み)
- **エラーケース**: gh CLI 不在、認証失敗、API エラー(rate limit 含む)— GhError 例外で raise。rate limit は retry-after を読んで待機する(scheduled 実行時のみ)

#### `commands/init.py`

- **責務**: 指定ディレクトリを新規 bootstrap する
- **インターフェース**:
  ```
  gh manage init [<path>] --profile <name> [--dry-run] [--force]
  ```
- **動作**:
  1. プロファイル読み込み
  2. プリチェック(git リポか、remote あるか、未コミット変更無いか)
  3. ファイル配置(skip_if_exists を尊重)
  4. git commit はしない
  5. 次のステップを案内出力
- **エラーケース**: プロファイル不在、ディレクトリが git リポでない、未コミット変更あり、上書き対象ファイルあり(--force なし)

#### `commands/apply.py`

- **責務**: 既存リポへの部分適用
- **インターフェース**:
  ```
  gh manage apply [<path>] [--also-labels] [--also-protection] [--all] [--dry-run] [--apply] [--force]
  ```

**`init` vs `apply` のコントラクト表**:

| コマンド | files 更新 | labels 同期 | protection 適用 | repos.yml 追加 | 用途 |
|---|---|---|---|---|---|
| `gh manage init` | ✅ | ✅ | ✅ | ❌ (手動 PR) | 新規リポのフルセットアップ |
| `gh manage apply` | ✅ | ❌ | ❌ | ❌ | **ファイルのみ更新**(デフォルト、最も安全) |
| `gh manage apply --also-labels` | ✅ | ✅ | ❌ | ❌ | ファイル + ラベル |
| `gh manage apply --also-protection` | ✅ | ❌ | ✅ | ❌ | ファイル + 保護 |
| `gh manage apply --all` | ✅ | ✅ | ✅ | ❌ | init 相当(repos.yml 追加なし) |

**設計原則**:
- `apply` のデフォルトは**ファイル更新のみ**(破壊範囲が最小の操作)
- labels / protection は明示 opt-in(事故防止)
- `apply --all` と `init` の違いは repos.yml への追加有無のみ
- どの mode でも dry-run がデフォルト、`--apply` で実際に実行
- `--force` は既存ファイルの上書き許可(file 部分のみに影響)

**init との共有**: 内部実装はほぼ共有。両方とも同じ _apply_profile 関数を呼び、機能フラグで分岐する

#### `commands/labels.py`

- **責務**: ラベル同期
- **インターフェース**:
  ```
  gh manage labels sync <repo> [--apply] [--dry-run] [--prune]
  gh manage labels diff <repo>
  gh manage labels show <repo>
  ```
- **安全設計**: デフォルト dry-run、`--apply` で実行。`--prune` を付けない限り削除しない

#### `commands/protection.py`

- **責務**: branch protection 同期
- **インターフェース**:
  ```
  gh manage protection sync <repo> [--apply] [--downgrade-allowed] [--yes]
  gh manage protection diff <repo>
  gh manage protection show <repo>
  ```
- **安全設計**:
  - デフォルト dry-run
  - downgrade(現行より弱いポリシーを適用しようとしたとき) を検出して `--downgrade-allowed` なしで拒否
  - 実行前に現行設定を `.gh-manage-backup/<repo>-<timestamp>.yml` に保存
  - Classic branch protection を使用(Rulesets は将来検討)

#### `commands/drift.py`

- **責務**: 規約コンプライアンス検査(最重要、最もテストされる)
- **インターフェース**:
  ```
  gh manage drift [--all | --repo <name>] [--profile <name>]
                  [--severity <critical|high|medium|low>]
                  [--report-mode stdout|json|issue|markdown-file]
                  [--fix] [--dry-run]
  ```
- **check 関数**: `check_labels`, `check_protection`, `check_workflows`, `check_templates`, `check_claude_md`
- **Issue 生成戦略**: 1 リポにつき最大 1 つの open drift Issue。既存 Issue があれば本文更新、無ければ新規作成。drift 全解消を「**24 時間以上の間隔を空けた 2 回連続の scheduled run** で検出」したら自動クローズ(race condition 防止)
- **`--fix` モード**: 対話的に各 finding に対して修復コマンドを提案・実行。critical は `all` を付けても個別確認を強制

#### `commands/issues.py`

- **責務**: クロスリポ Issue 一覧(`gh search issues` の薄い wrapper)
- **インターフェース**:
  ```
  gh manage issues list [--repo <name>] [--label <label>] [--state open|closed|all]
  ```

### Declarative Configs

#### `config/labels.yml`

```yaml
version: 1
categories:
  type:
    description: Type of issue or PR
    labels:
      - { name: "type/bug",      color: "d73a4a", description: "Something isn't working" }
      - { name: "type/feature",  color: "a2eeef", description: "New feature or request" }
      - { name: "type/docs",     color: "0075ca", description: "Documentation" }
      - { name: "type/refactor", color: "fbca04", description: "Code refactoring" }
      - { name: "type/chore",    color: "fef2c0", description: "Maintenance" }
  priority:
    description: Priority level
    labels:
      - { name: "priority/critical", color: "b60205" }
      - { name: "priority/high",     color: "d93f0b" }
      - { name: "priority/medium",   color: "fbca04" }
      - { name: "priority/low",      color: "c5def5" }
  status:
    description: Current status
    labels:
      - { name: "status/triage",      color: "ededed" }
      - { name: "status/in-progress", color: "0e8a16" }
      - { name: "status/blocked",     color: "d93f0b" }
      - { name: "status/needs-info",  color: "fbca04" }
```

#### `config/branch-protection.yml`

`contexts` は profile の `required_contexts` に上書きされる(Profile と Branch Protection の契約を参照)。policy の `contexts` フィールドは**下位互換のための fallback** として残すが、profile が `required_contexts` を定義している限り使われない。

```yaml
version: 1
policies:
  solo-default:
    description: "Solo-dev default (no review requirement)"
    target_branches: ["main"]
    required_status_checks:
      strict: true
      contexts: []                   # profile の required_contexts で上書き
    enforce_admins: false
    required_pull_request_reviews:
      required_approving_review_count: 0
      dismiss_stale_reviews: false
      require_code_owner_reviews: false
    required_conversation_resolution: true
    required_linear_history: true
    allow_force_pushes: false
    allow_deletions: false
  collaborative:
    description: "Collaborative repo with reviewers"
    target_branches: ["main"]
    required_status_checks:
      strict: true
      contexts: []                   # profile の required_contexts で上書き
    enforce_admins: true
    required_pull_request_reviews:
      required_approving_review_count: 1
      dismiss_stale_reviews: true
    required_conversation_resolution: true
    required_linear_history: true
    allow_force_pushes: false
    allow_deletions: false
  docs-only:
    description: "Documentation-only repo, minimal protection"
    target_branches: ["main"]
    required_status_checks: null
    enforce_admins: false
    required_pull_request_reviews:
      required_approving_review_count: 0
    allow_force_pushes: false
    allow_deletions: false
```

#### `config/repos.yml`

```yaml
version: 1
repos:
  - name: gh-manage
    profile: python-service
    enabled: true
  - name: port-registry
    profile: python-service
    enabled: true
  # ... (Phase 10 で段階的に追加)
```

#### `config/profiles/python-service.yml` (例)

```yaml
version: 1
name: python-service
description: "Python service repo (uv + ruff + mypy + pytest)"
files:
  - source: ci/python-ci.yml
    dest: .github/workflows/ci.yml
  - source: issue/bug_report.yml
    dest: .github/ISSUE_TEMPLATE/bug_report.yml
  - source: issue/feature_request.yml
    dest: .github/ISSUE_TEMPLATE/feature_request.yml
  - source: issue/config.yml
    dest: .github/ISSUE_TEMPLATE/config.yml
  - source: pr/pull_request_template.md
    dest: .github/pull_request_template.md
  - source: claude-md/default.md
    dest: CLAUDE.md
    skip_if_exists: true
extra_labels:
  - { name: "area/api",    color: "1d76db" }
  - { name: "area/worker", color: "006b75" }
protection_policy: solo-default
required_contexts:                  # このプロファイルが要求する CI check
  - "pr-gate / test"
  - "ci-review / gitleaks"
```

### Profile と Branch Protection の契約

`branch-protection.yml` の policy に定義される `contexts` は「ベースラインの必須 check」であり、**実際の `required_status_checks.contexts` は profile の `required_contexts` が上書きする**:

```
効果的な contexts = profile.required_contexts (完全置換)
```

この設計の目的:
- profile を変更して一部 workflow を無効化したとき、protection が自動追従する
- branch-protection policy は「レビュー必要数、linear history、force push 許可」などの**構造的ルール**に集中し、`contexts` は profile の責務になる
- 新 workflow を追加した profile は `required_contexts` に追加する、という明確なハンドシェイク

**drift scanner の verification**:

`check_protection` は以下を検証する:
1. repo の profile から `required_contexts` を取得
2. 現行 branch protection の `required_status_checks.contexts` が profile の `required_contexts` と一致しているか
3. 不一致の場合、「profile に定義されていない check が残っている」 vs 「profile が要求する check が抜けている」を区別して high severity finding を生成

**整合性違反の例**:

- profile から `"ci-review / gitleaks"` を削除 → 実 protection にはまだ残っている → 「未使用 check が protection に残っている」 high finding
- profile に新 check を追加 → 実 protection にはまだ無い → 「profile が要求する check が protection に無い」 high finding
- どちらも `gh manage protection sync <repo> --apply` で修復可能

## Data Model

### Config schema の自己記述バージョン

各 config ファイルは先頭に `version: <integer>` を持つ。CLI はロード時に version を読み、対応する pydantic schema に dispatch する。

- **schema 変更ポリシー**:
  - 追加(新しい optional フィールド)は version を据え置く
  - 構造変更(ネスト変更、フラット → カテゴリ型) は version bump
  - rename / 削除は version bump
- **migration**: `src/gh_manage/schemas/migrations/<from>_to_<to>.py` で変換関数を提供

**Mixed version の取り扱い**:

各 config ファイル(`labels.yml`, `branch-protection.yml`, `repos.yml`, `profiles/*.yml`)は**独立にバージョニングされ、独立にロードされる**。例えば `labels.yml` が v1 で `branch-protection.yml` が v2 であっても、両者は競合しない。CLI はそれぞれのファイルに対して個別の schema dispatcher を呼ぶ。

**early-fail ルール**:

- CLI が知らない version(未来の version)を検出したら即座に明確なエラーで停止する
- 例: `labels.yml` が `version: 3` で CLI は v1/v2 までしか対応していない → `SchemaVersionError: labels.yml version 3 is not supported by this CLI version (supported: 1, 2). Upgrade gh-manage CLI.`
- 旧 version(v1)の検出は警告付きで読める("deprecated")、自動 migration は `gh manage migrate-config` サブコマンドで明示実行

### Drift finding のデータモデル

```python
@dataclass(frozen=True)
class Finding:
    severity: Literal["critical", "high", "medium", "low"]
    check: str                    # 例: "branch_protection"
    repo: str
    message: str
    remediation: str | None       # 修復コマンド(--fix で使用)
    data: dict                    # 追加コンテキスト
```

### GitHub API レスポンスの取り扱い

`gh api` の出力を pydantic model で parse し、型付きで内部ロジックに渡す。生の JSON を touch するのは `github_client.py` のみ。

## Versioning Strategy

### タグ系統(2 系統独立)

| 系統 | タグ例 | 対象 |
|---|---|---|
| Reusable workflows + composite actions | `v0.1.0`, `v1.0.0`, `v1.2.3` | Layer 3 と Layer 2 |
| CLI (Python) | `cli/v0.1.0`, `cli/v1.0.0` | `src/gh_manage/` 全体 |

### Moving tag と immutable tag

- `v1` → 最新の `v1.x.x` を指す moving tag(consumer の自動追従用)
- `v1.2.3` → 不変の immutable tag(厳密 pin 用)

### 破壊的変更ポリシー

- reusable workflows: `inputs:` rename/削除、`jobs.<name>` rename、lint 厳格化は破壊的変更として扱い新 major タグ
- 同一 PR で `docs/migrations/v<N>-to-v<N+1>.md` を必須作成
- 旧 major は 6 ヶ月サポート
- job 名は semver major 内で不変(`required_status_checks.contexts` を守るため)

### v0 → v1.0.0 昇格条件

- [ ] CLI 主要サブコマンド(init, labels sync, protection sync, drift)が動作
- [ ] fixture テストが全 green
- [ ] 2 以上の consumer repo が `@v0.x.x` で 1 週間以上稼働
- [ ] docs(quick-start, architecture, versioning, migration-template)完成
- [ ] README 整備

### Templates の暗黙バージョン

`templates/` は独立バージョンを持たず、gh-manage 本体のタグに追従する。drift scanner が consumer repo の template ファイル hash と比較して drift を検出する。

**Template drift の比較基準**:

drift scanner は consumer の `.github/workflows/ci.yml` 内の `uses:` タグ(例: `yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.2.0`)を抽出し、**そのタグ時点の template hash** と consumer のファイル hash を比較する:

1. consumer の `uses:` から tag を抽出
2. gh-manage リポで `git show <tag>:templates/<file>` を実行して該当バージョンの template content を取得
3. content の SHA256 hash を計算し、consumer リポの同ファイル content hash と比較
4. 不一致の場合 medium severity で drift finding を報告

**tag 解釈のルール**:

- `@v1.2.0` (immutable) — そのタグ時点の hash で厳密比較
- `@v1` (moving) — 走査実行時点で `v1` が指す実タグ(例: `v1.2.3`) に解決してから比較
- `@main` — medium severity で warning `"should pin to a version tag"`(hash 比較はせず、pin 推奨のみ)
- `@<sha>` — 該当 commit の hash と比較

## Error Handling

### 全体方針

- **ユーザー境界(CLI 入力、YAML ファイル、GitHub API レスポンス)では strict validation**。内部関数間では trust
- エラーメッセージは **何が起きたか + 次に何をすべきか** を必ず含める
- silent failure を禁止(`except: pass` 禁止。空 catch なし)
- rate limit エラーは scheduled 実行時のみ retry(CLI 手動実行では即座にエラー表示)

### エラーカテゴリと扱い

| カテゴリ | 例 | 扱い |
|---|---|---|
| Config 不正 | YAML syntax, pydantic validation | `ConfigError`、file path + line + 修正提案 |
| gh CLI 問題 | 未 install, 認証失敗 | `AuthError`、`gh auth login` を案内 |
| Repo 問題 | 存在しない、archived, 権限不足 | `RepoError`、skip して続行(drift scan 時) |
| API rate limit | 403 with X-RateLimit headers | scheduled では待機、CLI では stop |
| Network failure | connection error | 3 回 retry、それでも失敗なら stop |
| Drift 検出(異常ではない) | drift finding | exit code 0 (drift は報告対象であってエラーではない) |

## Testing Strategy

テストは **7 層** で構成(§ 4 参照):

| 層 | 対象 | カバレッジ目標 |
|---|---|---|
| L1 Shell scripts | `scripts/checks/*.sh` | 80% |
| L2 Composite actions | `actions/*/action.yml` | smoke workflow binary |
| L3 Reusable workflows | `.github/workflows/reusable-*.yml` | smoke workflow binary |
| L4 Python CLI | `src/gh_manage/` | 85% |
| L5 Drift scanner | `src/gh_manage/commands/drift.py` | **90%** |
| L6 Templates | `templates/` | **100%** (golden file) |
| L7 実 API integration | fixture repo | pre-release gate (必須) + nightly (optional) |

### L7 Pre-release acceptance test シナリオ

L7 は pre-release gate として**必須**。リリースタグ push 前に以下のシナリオを手動で完走させ、`docs/release-checklist.md` のチェック項目として扱う:

1. `scripts/reset-fixture.sh` で `yakkuro/gh-manage-test-fixture` を空状態にリセット
2. `gh manage init --profile python-service --apply` で bootstrap
3. API 経由で workflow/issue template/PR template/CLAUDE.md が配置済みか確認
4. `gh manage labels sync --apply` でラベル同期、`labels diff` が差分ゼロ
5. `gh manage protection sync --apply` で保護適用、`protection show` が policy 通り
6. `gh manage drift` で finding ゼロを確認
7. 意図的にラベルを 1 つ手で削除して drift を作る
8. `gh manage drift` で該当 drift を検出する
9. `gh manage drift --fix --apply` で修復
10. 再度 `gh manage drift` で finding ゼロ

10 ステップ全成功 → pre-release gate pass。失敗 → リリース延期。

### 重要な判断

- **gh API は subprocess (`gh api`) 経由**で叩く。直接 REST client は使わない。認証統合と依存削減優先
- **mock は subprocess レイヤ**で行う
- **drift scanner はシナリオ駆動** — `tests/fixtures/drift-scenarios/*.yml` を pytest-parametrize で読み、期待 findings と比較。新パターン追加は YAML 1 ファイルで完結
- **smoke test の negative case** — `if: failure()` で失敗を成功扱いに反転する wrapper workflow で実現
- **TDD 必須** — claude-dotfiles の `superpowers:test-driven-development` スキルを継承。Red → Green → Refactor。テスト無しの機能追加禁止

### テスト実行階層

| Trigger | 実行層 |
|---|---|
| PR open/update | L1-L6 (~1 分) |
| Push to main | L1-L6 + smoke (L2, L3) |
| Nightly cron | L1-L7 |
| Pre-release manual | L1-L7 + 実リポ smoke |

## Security Considerations

### 認証

- gh CLI の `gh auth login` 状態を流用(CLI 実行時)
- scheduled drift-scanner は Fine-grained PAT を `secrets.GH_MANAGE_TOKEN` として使用
- PAT 権限: `contents: read`, `administration: read`, `issues: write`(自リポのみ)
- PAT 有効期限 1 年、`docs/secrets-rotation.md` でローテーション手順を明記

### 入力バリデーション

- 全 YAML config は pydantic で schema validation
- CLI 引数は click/typer の型検証
- repo 名は `^[A-Za-z0-9_-]+/[A-Za-z0-9._-]+$` の正規表現で validate(GitHub の `owner/repo` 形式、コマンドインジェクション防止)
- owner-less の短縮表記は CLI 側で `yakkuro/` prefix を付けて正規化してから validation にかける

### 外部コマンド実行

- `subprocess.run` 呼び出しは全て `shell=False` + list 形式の argv
- ユーザー入力を shell コマンドに直接埋め込まない
- `gh api` の `--field` 渡しも配列形式

### ブランチ保護の downgrade 防止

- `protection sync` は現行保護より弱いポリシーを適用しようとすると `--downgrade-allowed` なしで拒否
- 実行前に現行設定を backup ファイルに保存

### drift scanner の自動修復は行わない

- scheduled モードでは検出のみ、修復なし
- 修復は CLI の `--fix` で対話的に実行(critical は常に個別確認)

### gh-manage 自身の branch protection

- gh-manage 自身も `solo-default` policy で保護
- `main` への直 push 禁止、PR 経由必須
- Codex + 3 エージェントレビュー(claude-dotfiles の Claude ランタイム型)を PR 作成後に実施

## Rollout Plan

10 フェーズで段階的に構築(§ 5 参照):

| Phase | 目的 | 成果物 | 推定工数 |
|---|---|---|---|
| 0 | Foundation | リポ初期化、skeleton、pyproject.toml | 1 セッション |
| 1 | reusable-pr-gate-python.yml | Layer 1-3 の Python ライン、smoke test、dogfood | 2-3 セッション |
| 2 | reusable-pr-gate-typescript.yml | TypeScript ライン | 1-2 セッション |
| 3 | 外部 consumer 第 1 号 | port-registry への手動適用 | 1 セッション |
| 4 | CLI スケルトン + config loader | gh extension 雛形、pydantic schemas | 1-2 セッション |
| 5 | CLI labels sync | 最初の実コマンド、dogfood | 1-2 セッション |
| 6 | CLI init/apply | ファイル配置、golden file tests | 2-3 セッション |
| 7 | CLI protection sync | 宣言的保護適用、downgrade 防止 | 1-2 セッション |
| 8 | Drift scanner | 検査ロジック、scheduled workflow、Issue 生成 | 2-3 セッション |
| 9 | v1.0 ハードニング | カバレッジ達成、docs 完成、リリース | 1-2 セッション |
| 10 | 横展開 | yakkuro org の 20+ リポへ段階適用 | 4-6 週 |

### MVP ライン

**Phase 3 完了時点** — CLI 無しで reusable workflow が動き、1 consumer が稼働する最小単位。

### Go/No-Go チェックポイント

- After Phase 1: 3 層アーキテクチャが機能しているか
- After Phase 3: 外部 consumer で false positive/negative が許容範囲か
- After Phase 5: CLI UX が許容範囲か
- After Phase 8: drift scanner の精度が実運用に耐えるか
- Before Phase 10: v1.0 昇格条件を満たすか

各 checkpoint で「1 フェーズ戻る or 設計見直し」を許容する。

## Edge Cases

(spec-critique で追加洗い出し予定。現時点で想定されている主要ケース)

- **Repo が削除された状態で drift scanner が走る** → skip + warning、fail しない
- **Repo が archived** → 自動 skip、`enabled: true` のままでも
- **Default branch が main でない** → medium severity で検出、ただし自動修正しない
- **Consumer repo が `@v1` ではなく `@main` を参照** → medium severity warning、運用上の提案
- **Reusable workflow の job 名変更** → semver major の破壊的変更として扱い、`contexts` 設定も同時更新を migration guide で案内
- **Fine-grained PAT の期限切れ** → scheduled fail、ローカル CLI は gh CLI 認証で動作継続
- **GitHub API rate limit** → scheduled は retry-after に従い待機、CLI は即エラー
- **同一 repo への `labels sync` と `labels sync --prune` の競合** → CLI 側で排他制御なし(人間が判断)、ただし `--prune` は常に明示指定
- **`config/repos.yml` と実態の差** → drift scanner ログに warning、fail しない
- **新規リポで初めて `init` 実行、既存ファイルと衝突** → `--force` なしで stop、既存ファイル一覧を表示
- **CI 途中で GitHub Actions が rate limit** → workflow 全体を fail、retry は手動

## Acceptance Criteria

### Phase 0 (Foundation)

- [ ] `gh-manage` リポジトリが yakkuro org に存在する: `gh repo view yakkuro/gh-manage`
- [ ] ローカル `~/repos/gh-manage/` で `uv sync` が成功する
- [ ] `uv run pytest` が 0 test で成功する
- [ ] `docs/specs/2026-04-10-gh-manage-design.md` が存在し commit されている

### Phase 1 (Python reusable)

- [ ] `.github/workflows/reusable-pr-gate-python.yml` が存在する
- [ ] `actions/setup-python-uv/action.yml`, `actions/run-ruff/action.yml`, `actions/run-mypy/action.yml`, `actions/log-gh-manage-version/action.yml` が存在する
- [ ] `tests/fixtures/projects/python-sample/` で smoke-test.yml が green
- [ ] `tests/fixtures/projects/python-lint-fail/` で smoke-test.yml の negative check が green(失敗検出)
- [ ] gh-manage 自身の PR CI が reusable-pr-gate-python.yml を呼び出している
- [ ] タグ `v0.1.0` が打たれている

### Phase 2 (TypeScript reusable)

- [ ] `.github/workflows/reusable-pr-gate-typescript.yml` が存在する
- [ ] 関連 composite actions が存在する
- [ ] TypeScript fixture で smoke-test.yml が green
- [ ] タグ `v0.2.0` が打たれている

### Phase 3 (First external consumer)

- [ ] `port-registry` リポに `.github/workflows/ci.yml` が追加され、gh-manage reusable を `@v0.2.0` で参照している
- [ ] port-registry の PR で CI が green に通る
- [ ] `docs/consumers.md` に port-registry 導入事例が記載されている

### Phase 4 (CLI skeleton)

- [ ] `gh extension install yakkuro/gh-manage` が成功する
- [ ] `gh manage --version` が適切に出力する
- [ ] `gh manage --help` がサブコマンド一覧を表示する
- [ ] `uv run pytest tests/unit/config` が全 pass
- [ ] 不正な `labels.yml` で明確なエラーメッセージが出る
- [ ] タグ `cli/v0.1.0` が打たれている

### Phase 5 (labels sync)

- [ ] `gh manage labels sync gh-manage --apply` で gh-manage のラベルが `config/labels.yml` と一致
- [ ] `gh manage labels diff gh-manage` が差分ゼロを出力
- [ ] `gh manage labels sync port-registry --apply` が同様に動作
- [ ] `uv run pytest tests/unit/cli/test_labels.py` が全 pass
- [ ] タグ `cli/v0.2.0` が打たれている

### Phase 6 (init/apply)

- [ ] 空ディレクトリに `gh manage init --profile python-service` を実行するとプロファイル指定のファイル群が配置される
- [ ] `--dry-run` で副作用なしに diff 表示
- [ ] `--force` なしで既存ファイルを破壊しない
- [ ] `uv run pytest tests/unit/templates` (golden file test) が全 pass
- [ ] タグ `cli/v0.3.0` が打たれている

### Phase 7 (protection sync)

- [ ] `gh manage protection sync port-registry --apply` で `solo-default` policy が適用される
- [ ] 現行より弱いポリシーを適用しようとすると `--downgrade-allowed` なしで stop
- [ ] 実行前の現行設定が `.gh-manage-backup/` に保存される
- [ ] タグ `cli/v0.4.0` が打たれている

### Phase 8 (drift scanner)

- [ ] `tests/fixtures/drift-scenarios/` に 10 以上のシナリオが存在
- [ ] `uv run pytest tests/unit/drift` が全 pass(カバレッジ 90% 以上)
- [ ] `gh manage drift --repo gh-manage` が drift ゼロを出力
- [ ] port-registry の保護を意図的に壊した状態で `gh manage drift --repo port-registry` が critical finding を検出
- [ ] `.github/workflows/drift-scanner.yml` が weekly cron で 1 度以上成功し、fixture repo を正しくスキャン
- [ ] drift 検出時に gh-manage リポに Issue が 1 件作成される
- [ ] 再スキャンで drift 未解消なら同 Issue の本文更新のみ(新規作成されない)
- [ ] タグ `cli/v0.5.0` が打たれている

### Phase 9 (v1.0 release)

- [ ] L1 カバレッジ 80%, L4 85%, L5 90%, L6 100% を達成
- [ ] smoke-test.yml が全 fixture で green
- [ ] 手動 integration test (L7) が 1 度完走
- [ ] `docs/README.md`, `architecture.md`, `quick-start.md`, `versioning.md`, `distribution-channels.md` が完成
- [ ] `docs/consumers.md` に 2 件以上の導入事例
- [ ] `CHANGELOG-reusable.md`, `CHANGELOG-cli.md` が整備されている
- [ ] `docs/release-checklist.md` が存在
- [ ] 2 つ以上の consumer repo が `@v0.x.x` で 1 週間以上稼働
- [ ] タグ `v1.0.0` と `cli/v1.0.0` が同時に打たれている

### Phase 10 (Rollout)

- [ ] yakkuro org の active 20 リポ以上で gh-manage の reusable workflow が稼働
- [ ] drift scanner が weekly 実行され、critical finding ゼロ状態が 2 週連続

## Dependencies

### 外部ツール

- `gh` CLI(ユーザー環境にインストール済み、`gh auth login` 済み)
- `uv` (Python 依存管理)
- `git` 2.x+
- GitHub Actions ランナー: `ubuntu-latest`

### Python 依存(想定)

- `click` または `typer` (CLI)
- `pydantic` v2 (schema validation)
- `pyyaml` (YAML loader)
- `pytest`, `pytest-cov`, `pytest-mock` (test)
- `rich` (optional, CLI 出力整形)

### GitHub リソース

- `yakkuro/gh-manage` リポジトリ
- `yakkuro/gh-manage-test-fixture` リポジトリ(Phase 8 で作成)
- Fine-grained PAT `GH_MANAGE_TOKEN` (Phase 8 で発行)

## Non-Goals

以下は明示的に gh-manage のスコープ外とする:

- Claude ランタイムワークフロー(Codex + 3 エージェント PR レビュー等)— claude-dotfiles に残る
- 汎用 LLM レビュー / AI コード生成
- クロスリポダッシュボード UI(F ドメイン、将来判断)
- リリース管理(G ドメイン、将来判断)
- 依存関係管理 / Dependabot 配布(H ドメイン、将来判断)
- GitHub Enterprise サポート
- yakkuro org 以外への配布(理論上は可能だが初期はサポート対象外)
- `gh repo create` の代替(ユーザーが事前に実行)
- Claude Code の Subagent / Skill / Hook 定義(claude-dotfiles に残る)
- claude-dotfiles の auto-loaded rule
- セマンティックリリース自動化(conventional commits → 自動バージョン決定)
- monorepo tooling(changesets, lerna)
- mutation testing、property-based testing
- `act` (nektos/act) によるローカル Actions 実行

## Open Questions

spec-critique で指摘された MEDIUM/LOW 項目のうち、本 spec で未決定のまま残すもの。writing-plans 段階または該当 Phase で決定する。

### MEDIUM

- **M-1. Phase 期間の単位統一** — 現在 "1 セッション" と "4-6 週" が混在。`docs/rollout-plan.md` (別ドキュメント)で統一基準を定義し、本 spec からは参照のみにするか、本 spec 内で統一する
- **M-2. drift `markdown-file` 出力の仕様** — `--report-mode markdown-file` 選択時のファイル名規則(例: `drift-report-{timestamp}.md`)、出力先(CWD? `.gh-manage-reports/`?)、既存ファイル上書き動作
- **M-3. branch protection "downgrade" の具体定義** — どの変更を「弱体化」とみなすかの比較関数を `commands/protection.py` の実装前に決定。例: `required_approving_review_count` 減少、`enforce_admins: true → false`、`contexts` の削減、`allow_force_pushes: false → true` を downgrade 扱い
- **M-4. repos.yml の repo 発見機構** — 現在は手動記載を前提。`gh manage repos discover --org yakkuro` のような自動発見サブコマンドを追加するか、継続手動か
- **M-5. gh extension の権限フォールバック** — `yakkuro/gh-manage` が private になった / アクセス権を失った consumer のための fork 対応、homebrew tap 配布等

### LOW

- **L-1. docs 構造の完全性** — `docs/` 配下に必要なファイルが網羅されているか、リリース前レビュー
- **L-2. PR template のカスタマイズ戦略** — consumer が独自の PR template を持ちたいときの override 機構
- **L-3. エラーメッセージの一貫性パターン** — 全 CLI コマンドで共通のエラーメッセージ format(`[gh-manage] <category>: <message>\n  Hint: <next-action>`)を決定し、1 箇所で format する
- **L-4. Logging / observability 戦略** — drift scanner の実行ログを artifact に残す以外の観測手段(Slack 通知、メトリクス、等)は初期スコープ外だが、フック点を spec 化しておくべきか

## References

- `claude-dotfiles/rules/git-workflow.md` — 全リポ共通の Git 運用原則(継承)
- `claude-dotfiles/rules/workflow-review.md` — Cross-Agent Review 手順(Claude ランタイム型、claude-dotfiles に残る)
- `claude-dotfiles/rules/issue-driven-development.md` — Issue 駆動開発(継承)
- `claude-dotfiles/rules/codex-integration.md` — Codex 連携(claude-dotfiles に残る)
- `claude-dotfiles/rules/spec-driven.md` — Spec-Driven Development(本 spec が従うプロセス)
- `claude-dotfiles/.github/workflows/reusable-pr-gate.yml` — 旧 reusable workflow(参考、移行しない)
- `claude-dotfiles/templates/spec-large.md` — 本 spec のテンプレート
