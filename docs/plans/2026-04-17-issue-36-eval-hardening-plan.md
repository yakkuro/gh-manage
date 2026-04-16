# Issue #36 — `eval` Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (default) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `eval "${CMD}"` with `${CMD}` (word splitting only) in `install-command` and `test-command` of both reusable PR-gate workflows, keeping `eval` in `setup-command` as a documented escape hatch, and ship as reusable-track `v1.1.0`.

**Architecture:** Two-line edits per workflow file (Python + TypeScript) plus input-description security notes. Regression coverage via three fixture jobs per language in a new smoke workflow. Release flow = annotated tag + GitHub Release + 22 consumer-side version-bump PRs in four batches.

**Tech Stack:** GitHub Actions (bash `set -euo pipefail`), pytest (positive fixture), pnpm (TS fixture), `gh` CLI for release and consumer rollout. Documentation in Markdown.

**Spec:** `docs/specs/2026-04-17-issue-36-eval-hardening-design.md`

**Branch (already created):** `fix/issue-36-eval-hardening`

---

## Plan-phase constraint resolution

Two spec-to-reality mismatches resolved here so task authors don't re-discover them:

1. **F2 fixture mechanism.** Spec sketches F2 as a sibling `jobs.<id>.uses:` + `continue-on-error: true` pair. `.github/workflows/smoke-test.yml:37-41` documents that **GitHub Actions does not honour `continue-on-error` at job level for `jobs.<id>.uses:`**. Plan F2 therefore uses a regular job that directly replicates the critical `${TEST_CMD}` run step with step-level `continue-on-error`, then asserts `PWNED_BY_INJECTION` is absent. This tests the same security property (word splitting vs shell interpretation) without invoking the full reusable workflow. F1 and F3 still use the reusable workflow via `jobs.<id>.uses:` because they are expected to pass — no `continue-on-error` needed.

2. **CHANGELOG file name.** Spec says `CHANGELOG.md`; repo actually splits into `CHANGELOG-reusable.md` (this is what we edit) and `CHANGELOG-cli.md` (untouched here).

---

## File structure

Edited:
- `.github/workflows/reusable-pr-gate-python.yml` — line 93 and 133 swap, input descriptions updated.
- `.github/workflows/reusable-pr-gate-typescript.yml` — same two lines, same description updates.
- `docs/usage/python.md` — `install-command` / `test-command` / `setup-command` sections.
- `docs/usage/typescript.md` — same three sections.
- `docs/versioning.md` — one-line note on minor-version behaviour changes.
- `CHANGELOG-reusable.md` — v1.1.0 section inserted under `## [Unreleased]`.

Created:
- `.github/workflows/eval-hardening-smoke.yml` — dedicated smoke workflow (F1/F2/F3 × {Python, TypeScript}).
- `docs/security.md` — trust-model page, ~100 lines.

Not modified:
- `src/gh_manage/data/repos.yml` — rollout happens on the consumer side, not here.

---

## Task 1: Edit `reusable-pr-gate-python.yml`

**Files:**
- Modify: `.github/workflows/reusable-pr-gate-python.yml:15-24` (input descriptions) and `:35-39` (setup-command description) and `:93` (install eval swap) and `:133` (test eval swap)

- [ ] **Step 1: Update `install-command` input description (lines 15-19)**

Replace:

```yaml
      install-command:
        description: "Dependency install command executed inside working-directory."
        required: false
        type: string
        default: "uv sync"
```

with:

```yaml
      install-command:
        description: "Dependency install command executed inside working-directory. Runs via shell word splitting (${CMD}), NOT eval. Shell metacharacters (pipes, quotes, redirects, $(), ;) are not interpreted; pass space-separated arguments only. For commands needing shell features, use setup-command or a committed shell script."
        required: false
        type: string
        default: "uv sync"
```

- [ ] **Step 2: Update `test-command` input description (lines 20-24)**

Replace:

```yaml
      test-command:
        description: "Test command executed inside working-directory."
        required: false
        type: string
        default: "uv run pytest"
```

with:

```yaml
      test-command:
        description: "Test command executed inside working-directory. Runs via shell word splitting (${CMD}), NOT eval. Shell metacharacters (pipes, quotes, redirects, $(), ;) are not interpreted; pass space-separated arguments only. For commands needing shell features, use setup-command or a committed shell script."
        required: false
        type: string
        default: "uv run pytest"
```

- [ ] **Step 3: Update `setup-command` input description (lines 35-39)**

Replace:

```yaml
      setup-command:
        description: "Optional shell command executed after install, before tests."
        required: false
        type: string
        default: ""
```

with:

```yaml
      setup-command:
        description: "Optional shell command executed after install, before tests. Runs via `eval` and interprets shell metacharacters (quotes, pipes, $()). SECURITY: only pass static literal values from trusted source. MUST NOT forward github.event.* fields, workflow_dispatch inputs, or any consumer-controlled string — doing so allows remote code execution in the PR gate. See docs/security.md."
        required: false
        type: string
        default: ""
```

- [ ] **Step 4: Swap line 93 — install step**

Replace:

```yaml
          echo "Running install-command: ${INSTALL_CMD}"
          eval "${INSTALL_CMD}"
```

with:

```yaml
          echo "Running install-command: ${INSTALL_CMD}"
          ${INSTALL_CMD}
```

- [ ] **Step 5: Swap line 133 — test step**

Replace:

```yaml
          echo "Running test-command: ${TEST_CMD}"
          eval "${TEST_CMD}"
```

with:

```yaml
          echo "Running test-command: ${TEST_CMD}"
          ${TEST_CMD}
```

- [ ] **Step 6: Verify setup-command step unchanged**

Open the file, confirm the `Run setup command (if provided)` step still contains `if ! eval "${SETUP_CMD}"; then` (around line 118). Do not edit.

- [ ] **Step 7: Local YAML syntax check**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/reusable-pr-gate-python.yml'))"`
Expected: command exits 0 with no output.

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/reusable-pr-gate-python.yml
git commit -m "fix(reusable): drop eval from install/test command in python PR gate

Closes part of #36. install-command and test-command now execute via
\${CMD} word splitting instead of eval \"\${CMD}\", so shell
metacharacters in the input value are passed as literal argv instead of
being interpreted. setup-command retains eval as the documented escape
hatch (image-ocr depends on single-quote preservation)."
```

---

## Task 2: Edit `reusable-pr-gate-typescript.yml`

Mirror Task 1 against the TypeScript workflow. Line numbers are identical (15-24 for install/test descriptions, 35-39 for setup-command, 93 for install swap, 133 for test swap).

**Files:**
- Modify: `.github/workflows/reusable-pr-gate-typescript.yml` (same lines as Task 1)

- [ ] **Step 1: Update `install-command` description (lines 15-19)**

Replace:

```yaml
      install-command:
        description: "Dependency install command executed inside working-directory."
        required: false
        type: string
        default: "pnpm install --frozen-lockfile"
```

with:

```yaml
      install-command:
        description: "Dependency install command executed inside working-directory. Runs via shell word splitting (${CMD}), NOT eval. Shell metacharacters (pipes, quotes, redirects, $(), ;) are not interpreted; pass space-separated arguments only. For commands needing shell features, use setup-command or a committed shell script."
        required: false
        type: string
        default: "pnpm install --frozen-lockfile"
```

- [ ] **Step 2: Update `test-command` description (lines 20-24)**

Replace:

```yaml
      test-command:
        description: "Test command executed inside working-directory."
        required: false
        type: string
        default: "pnpm test"
```

with:

```yaml
      test-command:
        description: "Test command executed inside working-directory. Runs via shell word splitting (${CMD}), NOT eval. Shell metacharacters (pipes, quotes, redirects, $(), ;) are not interpreted; pass space-separated arguments only. For commands needing shell features, use setup-command or a committed shell script."
        required: false
        type: string
        default: "pnpm test"
```

- [ ] **Step 3: Update `setup-command` description (lines 35-39)**

Replace:

```yaml
      setup-command:
        description: "Optional shell command executed after install, before tests."
        required: false
        type: string
        default: ""
```

with:

```yaml
      setup-command:
        description: "Optional shell command executed after install, before tests. Runs via `eval` and interprets shell metacharacters (quotes, pipes, $()). SECURITY: only pass static literal values from trusted source. MUST NOT forward github.event.* fields, workflow_dispatch inputs, or any consumer-controlled string — doing so allows remote code execution in the PR gate. See docs/security.md."
        required: false
        type: string
        default: ""
```

- [ ] **Step 4: Swap line 93 — install step**

Replace:

```yaml
          echo "Running install-command: ${INSTALL_CMD}"
          eval "${INSTALL_CMD}"
```

with:

```yaml
          echo "Running install-command: ${INSTALL_CMD}"
          ${INSTALL_CMD}
```

- [ ] **Step 5: Swap line 133 — test step**

Replace:

```yaml
          echo "Running test-command: ${TEST_CMD}"
          eval "${TEST_CMD}"
```

with:

```yaml
          echo "Running test-command: ${TEST_CMD}"
          ${TEST_CMD}
```

- [ ] **Step 6: Verify setup-command step unchanged**

Confirm the TypeScript file's `Run setup command (if provided)` step still contains `if ! eval "${SETUP_CMD}"; then`.

- [ ] **Step 7: Local YAML syntax check**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/reusable-pr-gate-typescript.yml'))"`
Expected: command exits 0.

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/reusable-pr-gate-typescript.yml
git commit -m "fix(reusable): drop eval from install/test command in typescript PR gate

Closes part of #36. Mirrors the python-side change: install-command and
test-command execute via \${CMD} word splitting; setup-command retains
eval as the documented escape hatch. No TypeScript consumer currently
uses setup-command, but the eval retention keeps parity with the python
workflow and reserves the escape hatch for future consumers."
```

---

## Task 3: Create smoke workflow `.github/workflows/eval-hardening-smoke.yml`

This workflow is the regression gate for the eval-hardening change. It runs on PRs that touch either reusable workflow or the smoke workflow itself.

**Files:**
- Create: `.github/workflows/eval-hardening-smoke.yml`

- [ ] **Step 1: Write the failing test (the smoke workflow itself)**

Create the file with all six fixture jobs (Python F1/F2/F3 + TypeScript F1/F2/F3). Full content:

```yaml
name: Eval Hardening Smoke

on:
  pull_request:
    paths:
      - '.github/workflows/reusable-pr-gate-python.yml'
      - '.github/workflows/reusable-pr-gate-typescript.yml'
      - '.github/workflows/eval-hardening-smoke.yml'
  push:
    branches:
      - main
    paths:
      - '.github/workflows/reusable-pr-gate-python.yml'
      - '.github/workflows/reusable-pr-gate-typescript.yml'
      - '.github/workflows/eval-hardening-smoke.yml'
  workflow_dispatch:

permissions:
  contents: read

jobs:
  # ========== Python ==========

  # F1 — Python positive: flags and paths exercise word-splitting of the
  # most common non-default install/test-command shape across the 22
  # bundled consumers.
  python-f1-flags-paths:
    name: eval-hardening / python-F1 (flags+paths, expect pass)
    uses: ./.github/workflows/reusable-pr-gate-python.yml
    with:
      python-version: "3.12"
      working-directory: tests/fixtures/projects/python-sample
      install-command: "uv sync --all-extras"
      test-command: "uv run pytest tests/ -v --tb=short"
      gh-manage-ref: ${{ github.sha }}

  # F2 — Python injection attempt. Spec sketches this with a sibling
  # jobs.<id>.uses: + continue-on-error job; smoke-test.yml documents
  # that job-level continue-on-error is not honoured for reusable
  # workflow calls, so we replicate the critical ${TEST_CMD} step in a
  # regular job with step-level continue-on-error, then assert.
  python-f2-injection:
    name: eval-hardening / python-F2 (injection neutralised)
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python and uv
        uses: ./actions/setup-python-uv
        with:
          python-version: "3.12"

      - name: Install fixture deps
        shell: bash
        working-directory: tests/fixtures/projects/python-sample
        run: |
          set -euo pipefail
          uv sync

      # Replicates the body of the reusable workflow's test step. The
      # key property under test: ${TEST_CMD} expands via word splitting
      # only; the ';' token becomes a literal positional argv to pytest.
      # This is exactly the same shell line as line 133 of
      # reusable-pr-gate-python.yml, so the fixture stays in sync with
      # the production change by construction.
      - name: Replicate reusable test step (expect failure, marker MUST NOT leak)
        id: inject
        continue-on-error: true
        shell: bash
        working-directory: tests/fixtures/projects/python-sample
        env:
          TEST_CMD: "uv run pytest tests/ ; echo PWNED_BY_INJECTION"
        run: |
          set -euo pipefail
          echo "::group::test"
          echo "Running test-command: ${TEST_CMD}"
          ${TEST_CMD}
          echo "::endgroup::"

      - name: Assert injection marker did not leak
        shell: bash
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          OUTCOME: ${{ steps.inject.outcome }}
        run: |
          set -euo pipefail
          # gh run view <RUN_ID> --log returns combined logs for ALL
          # jobs in the run (including this in-progress job's completed
          # prior steps). We do NOT filter by --job because
          # ${{ github.job }} is the job_id string, not the numeric
          # job ID that --job expects. The marker string is unique
          # enough that whole-run grep is sound.
          gh run view "${{ github.run_id }}" --log > /tmp/inject.log 2>&1 || true
          if grep -q 'PWNED_BY_INJECTION' /tmp/inject.log; then
            echo "::error::injection marker leaked — eval hardening regressed"
            exit 1
          fi
          # Secondary sanity check: the replication step should have
          # failed (pytest errors on the ';' extra argv). If it
          # succeeded, the fixture is wrong or pytest silently ignores
          # unknown positionals.
          if [[ "${OUTCOME}" != "failure" ]]; then
            echo "::error::expected replication step to fail with unknown argv; outcome=${OUTCOME}"
            exit 1
          fi
          echo "Injection neutralised: pytest errored on literal ';' arg and 'PWNED_BY_INJECTION' never executed."

  # F3 — Python quoted setup-command compatibility. Proves eval still
  # honours single quotes inside setup-command (the image-ocr pattern).
  python-f3-quoted-setup:
    name: eval-hardening / python-F3 (quoted setup, expect marker in log)
    uses: ./.github/workflows/reusable-pr-gate-python.yml
    with:
      python-version: "3.12"
      working-directory: tests/fixtures/projects/python-sample
      setup-command: "printf '%s\\n' 'quote-preservation-ok'"
      gh-manage-ref: ${{ github.sha }}

  # ========== TypeScript ==========

  # F1 — TypeScript positive: word splitting of pnpm install flags and
  # a non-default test invocation.
  typescript-f1-flags:
    name: eval-hardening / ts-F1 (flags, expect pass)
    uses: ./.github/workflows/reusable-pr-gate-typescript.yml
    with:
      node-version: "20"
      working-directory: tests/fixtures/projects/typescript-sample
      install-command: "pnpm install --frozen-lockfile"
      test-command: "pnpm test -- --run"
      gh-manage-ref: ${{ github.sha }}

  # F2 — TypeScript injection attempt. Same replication pattern as F2
  # Python; uses pnpm instead of uv.
  typescript-f2-injection:
    name: eval-hardening / ts-F2 (injection neutralised)
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Node and pnpm
        uses: ./actions/setup-node-pnpm
        with:
          node-version: "20"

      - name: Install fixture deps
        shell: bash
        working-directory: tests/fixtures/projects/typescript-sample
        run: |
          set -euo pipefail
          pnpm install --frozen-lockfile

      - name: Replicate reusable test step (expect failure, marker MUST NOT leak)
        id: inject
        continue-on-error: true
        shell: bash
        working-directory: tests/fixtures/projects/typescript-sample
        env:
          TEST_CMD: "pnpm test ; echo PWNED_BY_INJECTION"
        run: |
          set -euo pipefail
          echo "::group::test"
          echo "Running test-command: ${TEST_CMD}"
          ${TEST_CMD}
          echo "::endgroup::"

      - name: Assert injection marker did not leak
        shell: bash
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          OUTCOME: ${{ steps.inject.outcome }}
        run: |
          set -euo pipefail
          # See comment in python-f2-injection assert step for why we
          # do not filter --job.
          gh run view "${{ github.run_id }}" --log > /tmp/inject.log 2>&1 || true
          if grep -q 'PWNED_BY_INJECTION' /tmp/inject.log; then
            echo "::error::injection marker leaked — eval hardening regressed (typescript)"
            exit 1
          fi
          if [[ "${OUTCOME}" != "failure" ]]; then
            echo "::error::expected replication step to fail; outcome=${OUTCOME}"
            exit 1
          fi
          echo "Injection neutralised (typescript)."

  # F3 — TypeScript quoted setup-command. Guards against future TS
  # consumers adopting a quoted setup-command.
  typescript-f3-quoted-setup:
    name: eval-hardening / ts-F3 (quoted setup, expect marker in log)
    uses: ./.github/workflows/reusable-pr-gate-typescript.yml
    with:
      node-version: "20"
      working-directory: tests/fixtures/projects/typescript-sample
      setup-command: "printf '%s\\n' 'ts-quote-preservation-ok'"
      gh-manage-ref: ${{ github.sha }}
```

- [ ] **Step 2: Confirm fixture directories referenced actually exist**

Run: `ls tests/fixtures/projects/python-sample tests/fixtures/projects/typescript-sample`
Expected: both directories listed; each contains the project scaffolding used by the existing smoke-test.yml.

If either is missing, stop — the fixture assumes these already exist (they are used by `.github/workflows/smoke-test.yml`). Report the gap back rather than inventing a new fixture.

- [ ] **Step 3: YAML syntax check**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/eval-hardening-smoke.yml'))"`
Expected: exits 0.

- [ ] **Step 4: Shellcheck on the embedded bash blocks (best-effort)**

Run: `grep -c 'set -euo pipefail' .github/workflows/eval-hardening-smoke.yml`
Expected: ≥ 4 (one per non-trivial bash step: F2 install, F2 replicate, F2 assert, TS F2 install, TS F2 replicate, TS F2 assert).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/eval-hardening-smoke.yml
git commit -m "test(smoke): add eval-hardening regression fixtures (F1/F2/F3 × py,ts)

Adds a dedicated smoke workflow exercising three regression scenarios
per language:
- F1: flags-and-paths positive (most common non-default consumer shape).
- F2: injection attempt; asserts PWNED_BY_INJECTION does not appear in
  the job log, proving \${CMD} word splitting neutralises ';' + echo.
- F3: quoted setup-command; proves eval still honours single quotes for
  the image-ocr-style pip install -e '.[dev,bot]' pattern.

F2 replicates the critical test step inline instead of invoking the
reusable workflow with continue-on-error at job level, because GitHub
Actions does not honour continue-on-error for jobs.<id>.uses: (see
smoke-test.yml:37-41). Behavioural parity with the production workflow
is maintained because the replication uses the same env-var
indirection and the same set -euo pipefail; \${CMD} shell line.

Part of #36."
```

---

## Task 4: Create `docs/security.md`

**Files:**
- Create: `docs/security.md`

- [ ] **Step 1: Write the security doc**

Content:

```markdown
# Security Model — Reusable PR Gate Inputs

This page documents the execution mechanism and trust requirements for
the three consumer-supplied shell-command inputs on
`reusable-pr-gate-python.yml` and `reusable-pr-gate-typescript.yml`.
See `CHANGELOG-reusable.md` for release history.

## Trust model

| Input | Execution mechanism | Shell metacharacters | Required source |
|-------|---------------------|----------------------|-----------------|
| `install-command` | `${CMD}` (word splitting) | **Not interpreted** | Any source acceptable — the workflow neutralises shell injection by itself. Values with metacharacters will error out at the install binary, not execute. |
| `test-command` | `${CMD}` (word splitting) | **Not interpreted** | Same as `install-command`. |
| `setup-command` | `eval "${CMD}"` | **Interpreted** (quotes, `\|`, `$()`, `;`, etc.) | **Trusted source only.** Consumer is responsible for ensuring the value is a static literal and never comes from untrusted input. |

## What MUST NOT be forwarded to `setup-command`

The following sources are user-controlled in a typical GitHub
repository and must never flow into `setup-command`:

- `github.event.pull_request.title`
- `github.event.pull_request.body`
- `github.event.issue.title`
- `github.event.issue.body`
- `github.event.comment.body`
- `github.event.review.body`
- `inputs.*` from `workflow_dispatch` events triggered by non-maintainers
- Values fetched from external URLs, third-party APIs, or other
  repositories

Forwarding any of these to `setup-command` allows remote code execution
inside the PR-gate runner. The runner has `contents: read` on your
repo plus access to any secrets exposed to the workflow call, so the
blast radius is at minimum the workflow run's secret set.

## Safe patterns

The following patterns are safe because they use static literals
defined in the workflow file itself:

```yaml
# Safe: static literal
setup-command: "pip install -e '.[dev,bot]'"
```

```yaml
# Safe: static literal driven by a matrix value (the matrix list is
# defined in the workflow, not user-controlled).
strategy:
  matrix:
    extras: ["dev", "dev,bot", "dev,ml"]
setup-command: "pip install -e '.[${{ matrix.extras }}]'"
```

```yaml
# Safe: secret or input defined at the caller level by a maintainer.
# The value is still trusted because a maintainer authored the workflow
# file and chose what feeds in.
setup-command: "${{ secrets.MAINTAINER_DEFINED_SETUP }}"
```

## Unsafe patterns

```yaml
# UNSAFE: pull request body is attacker-controlled.
setup-command: "echo '${{ github.event.pull_request.body }}'"
```

```yaml
# UNSAFE: comment body is attacker-controlled.
setup-command: "run-${{ github.event.comment.body }}"
```

```yaml
# UNSAFE: workflow_dispatch input may be submitted by anyone with
# actions:write on the repo.
setup-command: "${{ inputs.user-provided-command }}"
```

## Version history

| Release | Behaviour |
|---------|-----------|
| v1.0.x | `install-command`, `test-command`, and `setup-command` all executed via `eval "${CMD}"`. Shell metacharacters in any of the three were interpreted, so forwarding untrusted input to any of them allowed RCE. |
| v1.1.0 (2026-04-XX) | `install-command` and `test-command` switched to `${CMD}` word splitting. `setup-command` still uses `eval` as a documented escape hatch for quote-preservation patterns (e.g., `pip install -e '.[dev,bot]'`). |

## Reporting a security issue

Do **not** open a public issue for a suspected vulnerability in this
workflow. Instead, use GitHub's private vulnerability reporting on the
`yakkuro/gh-manage` repository (`Security` tab → `Report a
vulnerability`).
```

- [ ] **Step 2: Confirm file is well-formed markdown**

Run: `python3 -c "import pathlib; t = pathlib.Path('docs/security.md').read_text(); assert 'Trust model' in t and 'Unsafe patterns' in t and 'Version history' in t; print(len(t.splitlines()), 'lines')"`
Expected: prints a line count roughly in the 80-120 range and exits 0.

- [ ] **Step 3: Commit**

```bash
git add docs/security.md
git commit -m "docs(security): add trust model for reusable PR-gate inputs

Covers the v1.1.0 input trust split: install-command and test-command
execute via word splitting, setup-command retains eval and requires a
trusted source. Enumerates the github.event.* fields that must never
flow into setup-command and gives safe / unsafe pattern examples.

Part of #36."
```

---

## Task 5: Update `docs/usage/python.md`, `docs/usage/typescript.md`, `docs/versioning.md`

**Files:**
- Modify: `docs/usage/python.md` — `install-command`, `test-command`, `setup-command` sections.
- Modify: `docs/usage/typescript.md` — same three sections.
- Modify: `docs/versioning.md` — one line under the v1.0.0 stability promise.

- [ ] **Step 1: Locate the `install-command` section in `docs/usage/python.md`**

Read the file, find the heading/section that documents `install-command`. Add a paragraph immediately after the existing description:

> **Shell handling (v1.1.0+):** `install-command` executes via `${CMD}` (shell word splitting), not `eval`. Shell metacharacters — pipes, quotes, redirects, `$()`, `;` — are passed to the install binary as literal arguments, not interpreted. If you need shell features, use `setup-command` or commit a shell script to the consumer repository and invoke it by path. See [docs/security.md](../security.md) for the trust model.

- [ ] **Step 2: Locate the `test-command` section in `docs/usage/python.md`**

Add the same paragraph pattern (adapted for test-command):

> **Shell handling (v1.1.0+):** `test-command` executes via `${CMD}` (shell word splitting), not `eval`. Same constraints as `install-command` above.

- [ ] **Step 3: Locate the `setup-command` section in `docs/usage/python.md`**

Add a security callout after the existing description:

> **SECURITY (v1.1.0+):** `setup-command` executes via `eval` and interprets shell metacharacters. Only pass **static literal** values from a trusted source. Never forward `github.event.*`, `workflow_dispatch` inputs, or any consumer-controlled string to this field. See [docs/security.md](../security.md) for the full trust model and list of unsafe patterns.

- [ ] **Step 4: Repeat Steps 1-3 for `docs/usage/typescript.md`**

Same three sections, same text. If the TypeScript doc's prose differs slightly (e.g., pnpm-specific phrasing), adapt the intro clause but keep the v1.1.0 note wording identical so they diff cleanly.

- [ ] **Step 5: Update `docs/versioning.md`**

Find the v1.0.0 stability-promise section. Add one line:

> Documented behaviour changes that tighten security (e.g., removing `eval` from already-risky inputs) may ship in a MINOR version if the change is announced in `CHANGELOG-reusable.md`'s `Security` section and does not alter the declared input surface. v1.1.0 is the first precedent: `install-command` and `test-command` behaviour changed from `eval` to word splitting, but the input types, names, defaults, and required flags are unchanged.

- [ ] **Step 6: Sanity scan**

Run: `grep -l "v1.1.0" docs/usage/python.md docs/usage/typescript.md docs/versioning.md docs/security.md`
Expected: all four files listed.

Run: `grep -c "docs/security.md\|security.md" docs/usage/python.md docs/usage/typescript.md`
Expected: each file ≥ 2 (one link from install-command/test-command section, one from setup-command section).

- [ ] **Step 7: Commit**

```bash
git add docs/usage/python.md docs/usage/typescript.md docs/versioning.md
git commit -m "docs(usage): annotate v1.1.0 shell-handling change in install/test/setup

Adds a 'Shell handling (v1.1.0+)' paragraph to install-command and
test-command sections of both usage guides, a security callout to
setup-command, and a note in versioning.md explaining the v1.1.0
precedent for MINOR-version security hardening.

All four documentation files now cross-link to docs/security.md.

Part of #36."
```

---

## Task 6: Add v1.1.0 entry to `CHANGELOG-reusable.md`

**Files:**
- Modify: `CHANGELOG-reusable.md` — insert section under `## [Unreleased]` (line 7).

- [ ] **Step 1: Replace the `## [Unreleased]` block**

Current content at `CHANGELOG-reusable.md:7-9`:

```markdown
## [Unreleased]

_Nothing yet._
```

Replace with:

```markdown
## [Unreleased]

_Nothing yet._

## [1.1.0] - 2026-04-XX

### Security

- **[Behaviour change]** `install-command` and `test-command` no longer interpret shell metacharacters. Previously both fields were executed via `eval "${CMD}"`, which allowed command injection when consumers passed values sourced from untrusted inputs (`github.event.*` fields, workflow_dispatch inputs). They now execute via `${CMD}` (shell word splitting only). Shell metacharacters in these inputs are passed to the install/test binary as literal arguments rather than interpreted.
  - All consumers listed in `src/gh_manage/data/repos.yml` as of 2026-04-17 (22 repos) were inspected manually and verified unaffected: none used shell metacharacters in `install-command` or `test-command`.
  - Consumers that need shell features (quotes, pipes, redirects) in these fields must migrate them to `setup-command` or to a committed shell script invoked by path.
  - `setup-command` continues to execute via `eval` as a documented escape hatch and is explicitly scoped as "trusted source only" — see `docs/security.md` for the full trust model.
  - Closes #36.

### Added

- `setup-command` input description now explicitly documents its trust requirements and links to `docs/security.md`.
- New `docs/security.md` covering the workflow input threat model, safe/unsafe patterns, and version history.
```

- [ ] **Step 2: Verify markdown structure**

Run: `grep -c '^## \[1.1.0\]' CHANGELOG-reusable.md`
Expected: 1.

- [ ] **Step 3: Confirm the v1.0.0 section is untouched**

Run: `grep -c '^## \[1.0.0\] - 2026-04-14' CHANGELOG-reusable.md`
Expected: 1.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG-reusable.md
git commit -m "docs(changelog): add v1.1.0 security entry for eval hardening

Documents the install-command / test-command eval→\${CMD} shift and
the setup-command trust-model clarification. Explicitly anchors the
'22 consumers verified unaffected' claim to repos.yml as of
2026-04-17 (the survey date) so the claim stays falsifiable.

Release tag / GitHub Release creation covered by the release
checklist, executed post-merge. Part of #36."
```

---

## Task 7: Open PR and run four-reviewer protocol

This is a procedural task; the four-reviewer review is mandated by
`~/.claude/rules/workflow-review.md`.

**Files:**
- No edits in this task — just PR creation and review handling.

- [ ] **Step 1: Push the branch**

```bash
git push -u origin fix/issue-36-eval-hardening
```

- [ ] **Step 2: Open PR against `main`**

Use the PR title `fix(reusable): harden install/test-command against eval injection (#36)`.

Body (use a HEREDOC with `gh pr create`):

```markdown
## Summary
- Swaps `eval "${CMD}"` → `${CMD}` in `install-command` and `test-command` of both reusable PR-gate workflows, retains `eval` in `setup-command` as the documented escape hatch (image-ocr compatibility).
- Adds F1/F2/F3 regression fixtures (per-language) in a new `eval-hardening-smoke.yml`.
- Ships as reusable-track `v1.1.0`; adds `docs/security.md`; updates usage guides, versioning.md, and CHANGELOG-reusable.md.

## Test plan
- [ ] Smoke workflow F1 Python passes (flags+paths).
- [ ] Smoke workflow F2 Python fails at the replicate step and passes the assertion step (PWNED_BY_INJECTION not present).
- [ ] Smoke workflow F3 Python shows `quote-preservation-ok` in log.
- [ ] TypeScript F1/F2/F3 equivalents.
- [ ] Existing `smoke-test.yml` still green (no regression in the main self-dogfood path).

## Spec and plan
- Spec: `docs/specs/2026-04-17-issue-36-eval-hardening-design.md`
- Plan: `docs/plans/2026-04-17-issue-36-eval-hardening-plan.md`

Closes #36.

Generated with [Claude Code](https://claude.ai/code)
```

Command:

```bash
gh pr create --title "fix(reusable): harden install/test-command against eval injection (#36)" --body "$(cat <<'EOF'
...body above...
EOF
)"
```

- [ ] **Step 3: Launch the four reviewers in parallel**

Follow `~/.claude/rules/workflow-review.md` exactly. All four reviews run in a single message of parallel Agent calls:

1. Codex — `bash scripts/codex-review-resilient.sh "<prompt>"` (prompt references the PR URL, the spec, the plan, and the diff).
2. `superpowers:code-reviewer` — pass the spec path and the plan path so the reviewer can validate plan compliance.
3. `pr-review-toolkit:silent-failure-hunter` — pass the diff; focus on the F2 assertion step (marker log scan is the load-bearing assertion).
4. `code-reviewer` (custom) — pass the diff; `git diff main..HEAD --stat | tail -1` shows line count; pick model per workflow-review.md's table.

- [ ] **Step 4: Address CRITICAL and HIGH findings**

For every CRITICAL: fix and push. Do not merge until zero CRITICAL remain.
For HIGH: fix unless there is a documented rationale to skip.
For MEDIUM/LOW: judge individually; skipped items must be annotated in the PR with rationale.

- [ ] **Step 5: Wait for CI green**

Run: `gh pr checks <PR_NUMBER> --watch`
Expected: all required checks pass, including `Eval Hardening Smoke` (the new workflow).

- [ ] **Step 6: Squash merge**

```bash
gh pr merge <PR_NUMBER> --squash --delete-branch
```

No commit step — the merge happens through `gh pr merge`.

---

## Task 8: Release `v1.1.0` (reusable track)

This task must run on `main` after Task 7's merge. It follows
`docs/release-checklist.md` in this repo.

**Files:**
- No edits — tagging and GitHub Release only.

- [ ] **Step 1: Sync local main**

```bash
git checkout main && git pull --ff-only origin main
```

- [ ] **Step 2: Confirm the CHANGELOG-reusable.md is the merged version**

Run: `grep -A1 '^## \[1.1.0\]' CHANGELOG-reusable.md | head -2`
Expected: prints `## [1.1.0] - 2026-04-XX` (or the real date once bumped) followed by the next line.

- [ ] **Step 3: Replace `2026-04-XX` in CHANGELOG with the actual release date**

Use `date -u +%F` to get today's UTC date. Update the header:

```bash
today=$(date -u +%F)
# In CHANGELOG-reusable.md, change "## [1.1.0] - 2026-04-XX" to "## [1.1.0] - ${today}"
```

Edit via the Edit tool, then commit:

```bash
git add CHANGELOG-reusable.md
git commit -m "chore(release): stamp v1.1.0 release date"
git push origin main
```

- [ ] **Step 4: Create annotated tag**

```bash
git tag -a v1.1.0 -m "Reusable workflows v1.1.0 — eval hardening (closes #36)

install-command and test-command switch from eval \"\${CMD}\" to
\${CMD} word splitting. setup-command retains eval as a documented
escape hatch. See CHANGELOG-reusable.md for the full entry and
docs/security.md for the trust model."
git push origin v1.1.0
```

- [ ] **Step 5: Create GitHub Release**

```bash
gh release create v1.1.0 \
  --title "Reusable workflows v1.1.0 — eval hardening" \
  --notes-file <(awk '/^## \[1.1.0\]/,/^## \[1.0.0\]/' CHANGELOG-reusable.md | sed '$d')
```

(`sed '$d'` strips the trailing separator line, which would otherwise be the start of the v1.0.0 header.)

- [ ] **Step 6: Verify the release is discoverable**

Run: `gh release view v1.1.0`
Expected: renders title, body with CHANGELOG excerpt, and the `v1.1.0` tag name.

- [ ] **Step 7: Observe one drift-scanner cron cycle**

The drift scanner is pinned to `@main` (not `@v1.1.0`), so it will pick up the post-merge workflow content immediately. The plan's correctness criterion is "no new critical drift findings in the next cron cycle after merge."

Run: `gh workflow list --repo yakkuro/gh-manage | grep -i drift`
Expected: drift workflow exists; note its next scheduled run in your task log.

After the next cron fires, check: `gh run list --workflow=drift-scanner.yml --repo yakkuro/gh-manage --limit 1`
Expected: latest run is green.

(If not green, open a follow-up Issue referencing #36 and halt the consumer rollout until resolved.)

---

## Task 9: Consumer rollout (22 PRs, 4 batches)

This task opens version-bump PRs against every repo listed in
`src/gh_manage/data/repos.yml` as of the release. The repos are
external (yakkuro/\*), so each PR is a separate branch in a separate
repository; the subagent-driven-development skill dispatches one
worker per consumer per batch.

**Files:**
- No edits in this repo — cross-repo PRs only.

- [ ] **Step 1: Snapshot the consumer list at release time**

Run: `python3 -c "import yaml; repos = yaml.safe_load(open('src/gh_manage/data/repos.yml'))['repos']; [print(r['full_name']) for r in repos]"`
Save the output to a scratch file (e.g., `/tmp/rollout-consumers.txt`). The plan's rollout acts on this snapshot; repos added after the snapshot are out of scope for this PR rollout (they pick up v1.1.0 on their next opt-in).

Expected output: 22 repository full_names.

- [ ] **Step 2: Split into 4 batches of 5-6 repos**

Strategy: alphabetical by full_name, batches of 6/6/5/5. Rationale:
alphabetical is deterministic and makes it easy to pick up a specific
batch without overlap. Save the batch assignments:

```text
batch-1: repos 1-6
batch-2: repos 7-12
batch-3: repos 13-17
batch-4: repos 18-22
```

- [ ] **Step 3: Dispatch batch-1 workers in parallel**

Each worker does, in the target consumer repo:

1. Clone the consumer to a temp worktree.
2. Create branch `chore/bump-gh-manage-v1.1.0`.
3. Edit `.github/workflows/ci.yml`:
   - Change `uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.0.0` → `@v1.1.0` (and same for typescript variant if present).
   - Change `gh-manage-ref: v1.0.0` → `gh-manage-ref: v1.1.0`.
4. Commit: `chore: bump gh-manage from v1.0.0 to v1.1.0 (security hardening)`
5. Push branch; open PR with body:

   ```markdown
   Bumps `gh-manage` from `v1.0.0` to `v1.1.0`.

   v1.1.0 hardens `install-command` and `test-command` against shell
   injection by switching from `eval "${CMD}"` to `${CMD}` word
   splitting. See yakkuro/gh-manage#36 and
   [CHANGELOG-reusable.md](https://github.com/yakkuro/gh-manage/blob/main/CHANGELOG-reusable.md).

   This repo's current install/test commands were manually inspected
   on 2026-04-17 and are compatible with the new behaviour.
   ```

6. Return the PR URL to the leader.

- [ ] **Step 4: Merge batch-1 PRs as each goes green**

For each batch-1 PR:

```bash
gh pr checks <consumer_PR_number> --repo yakkuro/<repo> --watch
```

**Flake handling (per spec §"Flake handling"):** if the PR gate fails
on the first run, re-run the failed job once. If it fails a second
time, treat as a real regression: park the PR (comment explaining why
it's on hold), investigate the consumer's command pattern for a missed
metachar dependency, and either migrate to `setup-command` or raise
it back to the spec. Never merge on flaky-green — require two
consecutive green runs for any consumer that failed at least once.

On two consecutive greens:

```bash
gh pr merge <consumer_PR_number> --repo yakkuro/<repo> --squash --delete-branch
```

- [ ] **Step 5: Repeat Steps 3-4 for batch-2, batch-3, batch-4**

Batches are serial (wait for previous batch to fully merge before
starting the next). Rationale: if batch-1 surfaces an unexpected
consumer pattern, we want to halt rollout before queuing more bump
PRs.

- [ ] **Step 6: Final verification**

After all 22 PRs merge:

```bash
# Run drift scanner once more to confirm pin drift is zero.
gh workflow run drift-scanner.yml --repo yakkuro/gh-manage
gh run list --workflow=drift-scanner.yml --repo yakkuro/gh-manage --limit 1
```

Expected: drift scanner run is green; no repo shows `gh-manage-ref`
pinned to `v1.0.0`.

Run: `gh issue view 36 --repo yakkuro/gh-manage`
Expected: closed (autoclose via the PR merge in Task 7).

- [ ] **Step 7: Document rollout completion**

Add a brief note to `docs/phase-10-canary-log.md` or the appropriate
rollout log with the merge dates of all 22 consumer PRs. Commit:

```bash
git checkout main && git pull --ff-only
git checkout -b chore/issue-36-rollout-complete
# edit docs/phase-10-canary-log.md
git add docs/phase-10-canary-log.md
git commit -m "docs(phase-10): record v1.1.0 consumer rollout completion

All 22 consumer PRs merged; gh-manage-ref pins uniformly at v1.1.0.
Drift scanner green post-rollout. Closes #36 rollout milestone."
git push -u origin chore/issue-36-rollout-complete
gh pr create --fill
```

Merge via four-reviewer flow (tiny doc-only PR; workflow-review.md
lets reviewers skip the full protocol but still requires at least one
pass).

---

## Execution handoff

Plan complete and saved to `docs/plans/2026-04-17-issue-36-eval-hardening-plan.md`.

**Execution mode:** subagent-driven (default per user memory — skip the inline-vs-subagent choice in writing-plans handoff).

Next step: invoke `superpowers:subagent-driven-development` and start with Task 1.
