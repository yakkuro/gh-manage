# gh-manage Phase 1 (reusable-pr-gate-python.yml) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `yakkuro/gh-manage@v0.1.0` containing a working Python PR-gate reusable workflow (`reusable-pr-gate-python.yml`) built from four composite actions (`log-gh-manage-version`, `setup-python-uv`, `run-ruff`, `run-mypy`), verified by three fixture projects (positive, lint-fail, test-fail) via a smoke-test workflow, and dogfooded by gh-manage's own CI on every PR.

**Architecture:** Three-layer CI infrastructure — Layer 3 reusable workflow composes Layer 2 composite actions, verified by fixture Python projects under `tests/fixtures/projects/`. The reusable workflow references its own composite actions via relative paths (`./actions/<name>`), which GitHub resolves from gh-manage's own source tree at the tag the consumer is pinning. Tool versions (uv, ruff, mypy) are pinned inside composite actions so every consumer gets reproducible results regardless of their local environment. Negative fixture testing uses `continue-on-error: true` on the reusable call plus a downstream `needs.<job>.result == 'failure'` assertion job.

**Tech Stack:**
- GitHub Actions (reusable workflows + composite actions)
- `actions/checkout@v4`, `actions/setup-python@v5`, `astral-sh/setup-uv@v4`
- Python 3.12 + `uv` for fixture projects
- `ruff` 0.8.0 (pinned), `mypy` 1.12.0 (pinned), `uv` 0.5.0 (pinned)
- `gh` CLI for branch push and PR creation
- `yamllint` (optional, via `uvx`) for local YAML syntax verification

**Preconditions (Phase 0 must be complete):**
- `~/repos/gh-manage/` is a git repo with 4 commits on `main`, pushed to `origin/main`
- `yakkuro/gh-manage` exists on GitHub as a private repository
- `uv run pytest` passes (2 sanity tests green)
- `uv run gh-manage --version` prints `0.0.0`
- 12 tracked files including spec, Phase 0 plan, CLAUDE.md, pyproject.toml, etc.

**Branch strategy:** All Phase 1 work happens on a new feature branch `feat/phase-1-python-reusable` off `main`. No direct commits to `main`. The final merge comes via PR, reviewed per the Codex + 3-agent review protocol (claude-dotfiles runtime workflow), then `v0.1.0` is tagged from `main` after merge.

**No git worktree:** Since gh-manage has a single contributor and the feature branch provides sufficient isolation from `main`, this plan does NOT use a worktree. Work is performed directly in `~/repos/gh-manage/` on the feature branch. If multi-session parallel development becomes needed later, a worktree can be created retroactively.

**Critical note for Red-Green test cycles:** Phase 0 discovered that `mv` preserves mtime, causing pytest's `.pyc` cache to become stale after restoring a file. When any task in this plan modifies a `.py` file and then restores it, **always run `touch <file>` after restoration** to invalidate the cache. This plan contains no Red-Green cycles on Python files (the Python code is already done in Phase 0), but keep this in mind.

---

## Pre-flight Checks

- [ ] **PF-1: Phase 0 state verified**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git log --oneline | head -5
  git status
  git branch --show-current
  git ls-files | wc -l
  uv run pytest -v
  uv run gh-manage --version
  ```

  Expected:
  - `git log` shows at least 4 commits ending with `009c584 chore: initial commit with base files, spec, and Phase 0 plan`
  - `git status` is clean
  - current branch is `main`
  - `git ls-files | wc -l` prints `12`
  - pytest passes 2/2
  - `gh-manage, version 0.0.0`

  If any check fails, STOP and re-run Phase 0 verification (`docs/plans/2026-04-10-phase-0-foundation.md` § Task 6).

- [ ] **PF-2: GitHub repo state**

  Run:
  ```bash
  gh repo view yakkuro/gh-manage --json name,visibility,defaultBranchRef
  gh api repos/yakkuro/gh-manage/git/ref/heads/main --jq .object.sha
  git rev-parse origin/main
  ```

  Expected:
  - JSON with `"visibility": "PRIVATE"` and `"defaultBranchRef":{"name":"main"}`
  - Remote `main` SHA matches local `origin/main` SHA

- [ ] **PF-3: Working directory is clean**

  Run:
  ```bash
  cd ~/repos/gh-manage
  test -z "$(git status --porcelain)" && echo "clean" || echo "DIRTY"
  ```

  Expected: `clean`. If `DIRTY`, STOP and ask the user.

- [ ] **PF-4: Create feature branch**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git checkout -b feat/phase-1-python-reusable
  git branch --show-current
  ```

  Expected: current branch is `feat/phase-1-python-reusable`.

---

## File Structure Overview

Phase 1 creates the following new files (15 total):

```
tests/fixtures/projects/python-sample/
├── pyproject.toml
├── src/python_sample/__init__.py
└── tests/test_add.py

tests/fixtures/projects/python-lint-fail/
├── pyproject.toml
├── src/python_lint_fail/__init__.py
└── tests/test_ok.py

tests/fixtures/projects/python-test-fail/
├── pyproject.toml
├── src/python_test_fail/__init__.py
└── tests/test_fail.py

actions/log-gh-manage-version/action.yml
actions/setup-python-uv/action.yml
actions/run-ruff/action.yml
actions/run-mypy/action.yml

.github/workflows/reusable-pr-gate-python.yml
.github/workflows/smoke-test.yml
.github/workflows/ci.yml            # gh-manage self-dogfood

docs/usage/python.md
CHANGELOG-reusable.md
```

And modifies one existing file:

```
pyproject.toml                       # add minimal ruff/mypy config if needed
```

---

## Part 1: Positive fixture project (`python-sample`)

### Task 1: Create `python-sample` fixture

**Files:**
- Create: `tests/fixtures/projects/python-sample/pyproject.toml`
- Create: `tests/fixtures/projects/python-sample/src/python_sample/__init__.py`
- Create: `tests/fixtures/projects/python-sample/tests/__init__.py`
- Create: `tests/fixtures/projects/python-sample/tests/test_add.py`

- [ ] **Step 1.1: Create the directory layout**

  Run:
  ```bash
  cd ~/repos/gh-manage
  mkdir -p tests/fixtures/projects/python-sample/src/python_sample
  mkdir -p tests/fixtures/projects/python-sample/tests
  ```

- [ ] **Step 1.2: Write `pyproject.toml`**

  Write file `tests/fixtures/projects/python-sample/pyproject.toml` with EXACTLY:
  ```toml
  [project]
  name = "python-sample"
  version = "0.0.0"
  description = "Positive fixture project for gh-manage smoke testing."
  requires-python = ">=3.12"
  dependencies = []

  [dependency-groups]
  dev = [
      "pytest>=8.0,<9",
  ]

  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"

  [tool.hatch.build.targets.wheel]
  packages = ["src/python_sample"]

  [tool.pytest.ini_options]
  testpaths = ["tests"]
  pythonpath = ["src"]
  ```

- [ ] **Step 1.3: Write `src/python_sample/__init__.py`**

  Write file `tests/fixtures/projects/python-sample/src/python_sample/__init__.py` with EXACTLY:
  ```python
  """Sample Python package used as a positive smoke-test fixture for gh-manage."""


  def add(a: int, b: int) -> int:
      """Return the sum of two integers."""
      return a + b
  ```

- [ ] **Step 1.4: Write `tests/__init__.py`**

  Write file `tests/fixtures/projects/python-sample/tests/__init__.py` with EXACTLY:
  ```python
  """Tests for python-sample."""
  ```

- [ ] **Step 1.5: Write `tests/test_add.py`**

  Write file `tests/fixtures/projects/python-sample/tests/test_add.py` with EXACTLY:
  ```python
  """Unit tests for python_sample.add."""

  from __future__ import annotations

  from python_sample import add


  def test_add_positive() -> None:
      assert add(1, 2) == 3


  def test_add_negative() -> None:
      assert add(-1, -1) == -2


  def test_add_zero() -> None:
      assert add(0, 0) == 0
  ```

- [ ] **Step 1.6: Verify python-sample passes ruff locally**

  Run:
  ```bash
  cd ~/repos/gh-manage/tests/fixtures/projects/python-sample
  uvx ruff@0.8.0 check .
  uvx ruff@0.8.0 format --check .
  echo "exit=$?"
  ```

  Expected: both commands exit 0 (no lint errors, formatting is clean).

  If `ruff format --check .` reports formatting differences, run `uvx ruff@0.8.0 format .` to auto-format, then re-verify. This is acceptable because the plan files above use standard Python formatting.

- [ ] **Step 1.7: Verify python-sample passes pytest locally**

  Run:
  ```bash
  cd ~/repos/gh-manage/tests/fixtures/projects/python-sample
  uv sync
  uv run pytest -v
  echo "exit=$?"
  ```

  Expected: 3 tests pass, exit 0. The `uv sync` step creates a local `.venv` inside the fixture directory — this is ignored by the top-level `.gitignore` (`.venv/` pattern).

- [ ] **Step 1.8: Verify python-sample passes mypy locally**

  Run:
  ```bash
  cd ~/repos/gh-manage/tests/fixtures/projects/python-sample
  uv run --with mypy==1.12.0 mypy src
  echo "exit=$?"
  ```

  Expected: `Success: no issues found in 1 source file`, exit 0.

  If mypy reports errors, inspect and fix. The sample code is deliberately simple and should have no type issues.

---

## Part 2: Negative fixture projects (`python-lint-fail`, `python-test-fail`)

### Task 2: Create `python-lint-fail` fixture

**Files:**
- Create: `tests/fixtures/projects/python-lint-fail/pyproject.toml`
- Create: `tests/fixtures/projects/python-lint-fail/src/python_lint_fail/__init__.py`
- Create: `tests/fixtures/projects/python-lint-fail/tests/__init__.py`
- Create: `tests/fixtures/projects/python-lint-fail/tests/test_ok.py`

- [ ] **Step 2.1: Create the directory layout**

  Run:
  ```bash
  cd ~/repos/gh-manage
  mkdir -p tests/fixtures/projects/python-lint-fail/src/python_lint_fail
  mkdir -p tests/fixtures/projects/python-lint-fail/tests
  ```

- [ ] **Step 2.2: Write `pyproject.toml`**

  Write file `tests/fixtures/projects/python-lint-fail/pyproject.toml` with EXACTLY:
  ```toml
  [project]
  name = "python-lint-fail"
  version = "0.0.0"
  description = "Negative fixture: contains an intentional lint error (unused import)."
  requires-python = ">=3.12"
  dependencies = []

  [dependency-groups]
  dev = [
      "pytest>=8.0,<9",
  ]

  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"

  [tool.hatch.build.targets.wheel]
  packages = ["src/python_lint_fail"]

  [tool.pytest.ini_options]
  testpaths = ["tests"]
  pythonpath = ["src"]
  ```

- [ ] **Step 2.3: Write `src/python_lint_fail/__init__.py` with intentional lint error**

  Write file `tests/fixtures/projects/python-lint-fail/src/python_lint_fail/__init__.py` with EXACTLY:
  ```python
  """Negative fixture — intentionally contains unused imports (ruff F401)."""

  import os  # noqa: F401 - intentional, will be removed below to produce F401
  import sys  # intentional unused import to fail ruff check

  # The fixture deliberately leaves sys unused to trigger F401.
  # os has a noqa to isolate the failure to exactly one unused import.


  def add(a: int, b: int) -> int:
      """Return the sum of two integers."""
      return a + b
  ```

  The intent: `sys` is unused → ruff `F401` fires → ruff check exits non-zero.
  `os` has `# noqa: F401` so only one F401 appears (cleaner error output).

- [ ] **Step 2.4: Write `tests/__init__.py`**

  Write file `tests/fixtures/projects/python-lint-fail/tests/__init__.py` with EXACTLY:
  ```python
  """Tests for python-lint-fail."""
  ```

- [ ] **Step 2.5: Write `tests/test_ok.py`**

  Tests must pass so we verify that lint-fail ONLY fails at the lint stage, not at the test stage:
  ```python
  """Tests for python_lint_fail. These pass — lint-fail only fails at ruff check."""

  from __future__ import annotations

  from python_lint_fail import add


  def test_add_works() -> None:
      assert add(2, 3) == 5
  ```

- [ ] **Step 2.6: Verify python-lint-fail FAILS ruff locally**

  Run:
  ```bash
  cd ~/repos/gh-manage/tests/fixtures/projects/python-lint-fail
  uvx ruff@0.8.0 check .
  echo "exit=$?"
  ```

  Expected: ruff reports at least one error (`F401: sys imported but unused`), exit code is non-zero (probably 1). This is the desired outcome for a negative fixture.

- [ ] **Step 2.7: Verify python-lint-fail PASSES pytest locally**

  Run:
  ```bash
  cd ~/repos/gh-manage/tests/fixtures/projects/python-lint-fail
  uv sync
  uv run pytest -v
  echo "exit=$?"
  ```

  Expected: 1 test passes, exit 0. This confirms the fixture fails ONLY at the lint stage.

### Task 3: Create `python-test-fail` fixture

**Files:**
- Create: `tests/fixtures/projects/python-test-fail/pyproject.toml`
- Create: `tests/fixtures/projects/python-test-fail/src/python_test_fail/__init__.py`
- Create: `tests/fixtures/projects/python-test-fail/tests/__init__.py`
- Create: `tests/fixtures/projects/python-test-fail/tests/test_fail.py`

- [ ] **Step 3.1: Create the directory layout**

  Run:
  ```bash
  cd ~/repos/gh-manage
  mkdir -p tests/fixtures/projects/python-test-fail/src/python_test_fail
  mkdir -p tests/fixtures/projects/python-test-fail/tests
  ```

- [ ] **Step 3.2: Write `pyproject.toml`**

  Write file `tests/fixtures/projects/python-test-fail/pyproject.toml` with EXACTLY:
  ```toml
  [project]
  name = "python-test-fail"
  version = "0.0.0"
  description = "Negative fixture: clean code but contains an intentionally failing test."
  requires-python = ">=3.12"
  dependencies = []

  [dependency-groups]
  dev = [
      "pytest>=8.0,<9",
  ]

  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"

  [tool.hatch.build.targets.wheel]
  packages = ["src/python_test_fail"]

  [tool.pytest.ini_options]
  testpaths = ["tests"]
  pythonpath = ["src"]
  ```

- [ ] **Step 3.3: Write `src/python_test_fail/__init__.py` (clean code)**

  Write file `tests/fixtures/projects/python-test-fail/src/python_test_fail/__init__.py` with EXACTLY:
  ```python
  """Negative fixture — code is clean, but tests intentionally fail."""


  def add(a: int, b: int) -> int:
      """Return the sum of two integers."""
      return a + b
  ```

- [ ] **Step 3.4: Write `tests/__init__.py`**

  Write file `tests/fixtures/projects/python-test-fail/tests/__init__.py` with EXACTLY:
  ```python
  """Tests for python-test-fail."""
  ```

- [ ] **Step 3.5: Write `tests/test_fail.py` with intentional failure**

  Write file `tests/fixtures/projects/python-test-fail/tests/test_fail.py` with EXACTLY:
  ```python
  """Intentionally failing tests to verify gh-manage reusable detects test failures."""

  from __future__ import annotations

  from python_test_fail import add


  def test_intentional_failure() -> None:
      result = add(1, 1)
      assert result == 3, "Intentional failure: 1 + 1 is not 3, verifying test-fail fixture fails"
  ```

- [ ] **Step 3.6: Verify python-test-fail PASSES ruff locally**

  Run:
  ```bash
  cd ~/repos/gh-manage/tests/fixtures/projects/python-test-fail
  uvx ruff@0.8.0 check .
  uvx ruff@0.8.0 format --check .
  echo "exit=$?"
  ```

  Expected: both commands exit 0. Code is clean; only tests fail.

  If `ruff format --check .` reports formatting differences, run `uvx ruff@0.8.0 format .` and re-verify.

- [ ] **Step 3.7: Verify python-test-fail FAILS pytest locally**

  Run:
  ```bash
  cd ~/repos/gh-manage/tests/fixtures/projects/python-test-fail
  uv sync
  uv run pytest -v
  echo "exit=$?"
  ```

  Expected: 1 test fails with assertion error `Intentional failure: 1 + 1 is not 3`, exit code is non-zero (typically 1).

- [ ] **Step 3.8: Verify python-test-fail PASSES mypy locally**

  Run:
  ```bash
  cd ~/repos/gh-manage/tests/fixtures/projects/python-test-fail
  uv run --with mypy==1.12.0 mypy src
  echo "exit=$?"
  ```

  Expected: `Success: no issues found`, exit 0. Source code is clean; only tests fail.

### Task 4: Commit all three fixtures

- [ ] **Step 4.1: Verify `.venv` directories are ignored**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git status --ignored tests/fixtures/projects/ | head -30
  ```

  Expected: `.venv/` appears in the "Ignored files" section, NOT in "Untracked files".

- [ ] **Step 4.2: Stage fixture files**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git add tests/fixtures/projects/
  git status
  ```

  Expected: 12 new files listed (4 per fixture × 3 fixtures). No `.venv` or `__pycache__` entries.

  If you see `.venv` or `__pycache__`, STOP, un-stage those paths with `git restore --staged <path>`, and investigate `.gitignore`.

- [ ] **Step 4.3: Commit fixtures**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git commit -m "test: add Python fixture projects for smoke testing (positive + 2 negative)"
  git log --oneline | head -3
  ```

  Expected: commit succeeds with 15 files changed. The new commit appears as the most recent log entry.

---

## Part 3: Composite actions (Layer 2)

### Task 5: Create `log-gh-manage-version` composite action

**Files:**
- Create: `actions/log-gh-manage-version/action.yml`

- [ ] **Step 5.1: Create directory**

  Run:
  ```bash
  cd ~/repos/gh-manage
  mkdir -p actions/log-gh-manage-version
  ```

- [ ] **Step 5.2: Write action.yml**

  Write file `actions/log-gh-manage-version/action.yml` with EXACTLY:
  ```yaml
  name: Log gh-manage version
  description: >
    Print the gh-manage action ref, repository, workflow SHA, and UTC timestamp
    to the workflow log for debugging and traceability.

  runs:
    using: composite
    steps:
      - name: Log gh-manage version info
        shell: bash
        run: |
          set -euo pipefail
          echo "::group::gh-manage version info"
          echo "action_ref:        ${GITHUB_ACTION_REF:-<unknown>}"
          echo "action_repository: ${GITHUB_ACTION_REPOSITORY:-<unknown>}"
          echo "workflow_sha:      ${GITHUB_SHA:-<unknown>}"
          echo "timestamp_utc:     $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
          echo "::endgroup::"
  ```

- [ ] **Step 5.3: Validate YAML syntax locally**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('actions/log-gh-manage-version/action.yml'))"
  echo "exit=$?"
  ```

  Expected: exit 0, no output. If YAML is malformed, the command will error with a parse error.

### Task 6: Create `setup-python-uv` composite action

**Files:**
- Create: `actions/setup-python-uv/action.yml`

- [ ] **Step 6.1: Create directory**

  Run:
  ```bash
  cd ~/repos/gh-manage
  mkdir -p actions/setup-python-uv
  ```

- [ ] **Step 6.2: Write action.yml**

  Write file `actions/setup-python-uv/action.yml` with EXACTLY:
  ```yaml
  name: Set up Python and uv
  description: >
    Install the requested Python version and a pinned uv release.
    uv handles virtualenv creation, dependency install, and tool running
    for all downstream gh-manage Python composite actions.

  inputs:
    python-version:
      description: "Python version to install (e.g., '3.12' or '3.12.5')."
      required: true
    uv-version:
      description: "uv release to install (pinned by default for reproducibility)."
      required: false
      default: "0.5.0"

  runs:
    using: composite
    steps:
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ inputs.python-version }}

      - name: Install uv (pinned)
        uses: astral-sh/setup-uv@v4
        with:
          version: ${{ inputs.uv-version }}

      - name: Verify uv is available
        shell: bash
        run: |
          set -euo pipefail
          uv --version
          python --version
  ```

- [ ] **Step 6.3: Validate YAML syntax**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('actions/setup-python-uv/action.yml'))"
  echo "exit=$?"
  ```

  Expected: exit 0.

### Task 7: Create `run-ruff` composite action

**Files:**
- Create: `actions/run-ruff/action.yml`

- [ ] **Step 7.1: Create directory**

  Run:
  ```bash
  cd ~/repos/gh-manage
  mkdir -p actions/run-ruff
  ```

- [ ] **Step 7.2: Write action.yml**

  Write file `actions/run-ruff/action.yml` with EXACTLY:
  ```yaml
  name: Run ruff
  description: >
    Install a pinned ruff release and run both `ruff check` and
    `ruff format --check` in the given working directory. Fails the step
    if either command reports issues.

  inputs:
    working-directory:
      description: "Directory where ruff should operate. Defaults to the repo root."
      required: false
      default: "."
    ruff-version:
      description: "ruff version pin. Bumping this is a gh-manage concern, not the consumer's."
      required: false
      default: "0.8.0"

  runs:
    using: composite
    steps:
      - name: Run ruff check
        shell: bash
        working-directory: ${{ inputs.working-directory }}
        env:
          RUFF_VERSION: ${{ inputs.ruff-version }}
        run: |
          set -euo pipefail
          echo "::group::ruff check"
          uvx "ruff==${RUFF_VERSION}" check .
          echo "::endgroup::"

      - name: Run ruff format --check
        shell: bash
        working-directory: ${{ inputs.working-directory }}
        env:
          RUFF_VERSION: ${{ inputs.ruff-version }}
        run: |
          set -euo pipefail
          echo "::group::ruff format --check"
          uvx "ruff==${RUFF_VERSION}" format --check .
          echo "::endgroup::"
  ```

- [ ] **Step 7.3: Validate YAML syntax**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('actions/run-ruff/action.yml'))"
  echo "exit=$?"
  ```

  Expected: exit 0.

### Task 8: Create `run-mypy` composite action

**Files:**
- Create: `actions/run-mypy/action.yml`

- [ ] **Step 8.1: Create directory**

  Run:
  ```bash
  cd ~/repos/gh-manage
  mkdir -p actions/run-mypy
  ```

- [ ] **Step 8.2: Write action.yml**

  Write file `actions/run-mypy/action.yml` with EXACTLY:
  ```yaml
  name: Run mypy
  description: >
    Run mypy on the project's `src/` directory using a pinned mypy release.
    mypy is invoked via `uv run --with mypy==<version>` so it sees the
    project's declared dependencies and resolves stubs correctly.

  inputs:
    working-directory:
      description: "Directory where mypy should operate. Defaults to the repo root."
      required: false
      default: "."
    mypy-version:
      description: "mypy version pin. Bumping this is a gh-manage concern."
      required: false
      default: "1.12.0"
    target:
      description: "Path (relative to working-directory) that mypy should type-check."
      required: false
      default: "src"

  runs:
    using: composite
    steps:
      - name: Run mypy
        shell: bash
        working-directory: ${{ inputs.working-directory }}
        env:
          MYPY_VERSION: ${{ inputs.mypy-version }}
          MYPY_TARGET: ${{ inputs.target }}
        run: |
          set -euo pipefail
          echo "::group::mypy ${MYPY_TARGET}"
          uv run --with "mypy==${MYPY_VERSION}" mypy "${MYPY_TARGET}"
          echo "::endgroup::"
  ```

- [ ] **Step 8.3: Validate YAML syntax**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('actions/run-mypy/action.yml'))"
  echo "exit=$?"
  ```

  Expected: exit 0.

### Task 9: Commit all four composite actions

- [ ] **Step 9.1: Stage and review**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git add actions/
  git status
  ```

  Expected: 4 new files listed under `actions/`:
  - `actions/log-gh-manage-version/action.yml`
  - `actions/run-mypy/action.yml`
  - `actions/run-ruff/action.yml`
  - `actions/setup-python-uv/action.yml`

- [ ] **Step 9.2: Commit**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git commit -m "feat: add Layer 2 composite actions (log-version, setup-python-uv, run-ruff, run-mypy)"
  git log --oneline | head -3
  ```

  Expected: commit succeeds with 4 files changed.

---

## Part 4: Reusable workflow (Layer 3)

### Task 10: Create `reusable-pr-gate-python.yml`

**Files:**
- Create: `.github/workflows/reusable-pr-gate-python.yml`

- [ ] **Step 10.1: Create the `.github/workflows/` directory**

  Run:
  ```bash
  cd ~/repos/gh-manage
  mkdir -p .github/workflows
  ```

- [ ] **Step 10.2: Write the reusable workflow**

  Write file `.github/workflows/reusable-pr-gate-python.yml` with EXACTLY:
  ```yaml
  name: Reusable PR Gate (Python)

  on:
    workflow_call:
      inputs:
        python-version:
          description: "Python version to install (required)."
          required: true
          type: string
        working-directory:
          description: "Project directory inside the repo. Defaults to repo root."
          required: false
          type: string
          default: "."
        install-command:
          description: "Dependency install command executed inside working-directory."
          required: false
          type: string
          default: "uv sync"
        test-command:
          description: "Test command executed inside working-directory."
          required: false
          type: string
          default: "uv run pytest"
        lint:
          description: "Run ruff check + format --check (fixed tool, internal pin)."
          required: false
          type: boolean
          default: true
        type-check:
          description: "Run mypy on `src/` (fixed tool, internal pin)."
          required: false
          type: boolean
          default: true
        setup-command:
          description: "Optional shell command executed after install, before tests."
          required: false
          type: string
          default: ""
        uv-version:
          description: "uv release pin passed through to setup-python-uv."
          required: false
          type: string
          default: "0.5.0"

  permissions:
    contents: read

  jobs:
    test:
      name: PR Gate
      runs-on: ubuntu-latest
      steps:
        - name: Checkout consumer repository
          uses: actions/checkout@v4
          with:
            fetch-depth: 0

        - name: Log gh-manage version
          uses: ./actions/log-gh-manage-version

        - name: Set up Python and uv
          uses: ./actions/setup-python-uv
          with:
            python-version: ${{ inputs.python-version }}
            uv-version: ${{ inputs.uv-version }}

        - name: Install dependencies
          shell: bash
          working-directory: ${{ inputs.working-directory }}
          env:
            INSTALL_CMD: ${{ inputs.install-command }}
          run: |
            set -euo pipefail
            echo "::group::install"
            eval "${INSTALL_CMD}"
            echo "::endgroup::"

        - name: Run ruff (if lint enabled)
          if: inputs.lint
          uses: ./actions/run-ruff
          with:
            working-directory: ${{ inputs.working-directory }}

        - name: Run mypy (if type-check enabled)
          if: inputs.type-check
          uses: ./actions/run-mypy
          with:
            working-directory: ${{ inputs.working-directory }}

        - name: Run setup command (if provided)
          if: inputs.setup-command != ''
          shell: bash
          working-directory: ${{ inputs.working-directory }}
          env:
            SETUP_CMD: ${{ inputs.setup-command }}
          run: |
            set -euo pipefail
            echo "::group::setup-command"
            if ! eval "${SETUP_CMD}"; then
              echo "::error::setup-command failed: ${SETUP_CMD}"
              exit 1
            fi
            echo "::endgroup::"

        - name: Run tests
          shell: bash
          working-directory: ${{ inputs.working-directory }}
          env:
            TEST_CMD: ${{ inputs.test-command }}
          run: |
            set -euo pipefail
            echo "::group::test"
            eval "${TEST_CMD}"
            echo "::endgroup::"
  ```

  **Design notes:**
  - `uses: ./actions/...` uses relative paths. For a reusable workflow called from another repository, GitHub resolves `./` against the reusable workflow's repository (gh-manage), not the caller's checkout. This is the standard pattern for reusable workflows bundling local composite actions.
  - `actions/checkout@v4` checks out the CALLER's repository (the consumer). The gh-manage composite actions are automatically made available by GitHub's reusable workflow mechanism.
  - The `install-command`, `setup-command`, and `test-command` inputs pass shell strings through `env:` to avoid command injection — `eval` is still a risk surface but is constrained because `workflow_call` inputs come from trusted callers (the reusable's access is gated by the caller's repo settings, not by untrusted user input).
  - `setup-command` failure is handled explicitly: the error message is emitted via `::error::` before exiting so the GitHub Actions log highlights it.
  - Job name is `test` (lowercase, stable across v0.x and v1.x major) — this is the name that appears in `required_status_checks.contexts` for branch protection.

- [ ] **Step 10.3: Validate YAML syntax**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/reusable-pr-gate-python.yml'))"
  echo "exit=$?"
  ```

  Expected: exit 0.

- [ ] **Step 10.4: Commit reusable workflow**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git add .github/workflows/reusable-pr-gate-python.yml
  git commit -m "feat: add reusable-pr-gate-python.yml Layer 3 workflow"
  git log --oneline | head -3
  ```

  Expected: commit succeeds with 1 file changed.

---

## Part 5: Smoke test workflow

### Task 11: Create `smoke-test.yml`

**Files:**
- Create: `.github/workflows/smoke-test.yml`

This is the test harness that runs the reusable workflow against each fixture and asserts:
- `python-sample` → PASS (positive)
- `python-lint-fail` → FAIL (expected failure at lint)
- `python-test-fail` → FAIL (expected failure at test)

Negative fixtures use `continue-on-error: true` on the reusable job plus a dependent verifier job that checks `needs.<job>.result == 'failure'`.

- [ ] **Step 11.1: Write smoke-test.yml**

  Write file `.github/workflows/smoke-test.yml` with EXACTLY:
  ```yaml
  name: Smoke Test

  on:
    pull_request:
      paths:
        - '.github/workflows/reusable-pr-gate-python.yml'
        - '.github/workflows/smoke-test.yml'
        - 'actions/**'
        - 'tests/fixtures/projects/**'
    push:
      branches:
        - main
      paths:
        - '.github/workflows/reusable-pr-gate-python.yml'
        - '.github/workflows/smoke-test.yml'
        - 'actions/**'
        - 'tests/fixtures/projects/**'
    workflow_dispatch:

  permissions:
    contents: read

  jobs:
    # ---------- Positive fixture ----------
    positive-python-sample:
      name: smoke / python-sample (expect pass)
      uses: ./.github/workflows/reusable-pr-gate-python.yml
      with:
        python-version: "3.12"
        working-directory: tests/fixtures/projects/python-sample

    # ---------- Negative fixture: lint failure ----------
    negative-python-lint-fail:
      name: smoke / python-lint-fail (expect fail)
      uses: ./.github/workflows/reusable-pr-gate-python.yml
      with:
        python-version: "3.12"
        working-directory: tests/fixtures/projects/python-lint-fail
      continue-on-error: true

    verify-python-lint-fail:
      name: verify / python-lint-fail failed as expected
      needs: negative-python-lint-fail
      if: always()
      runs-on: ubuntu-latest
      steps:
        - name: Assert negative fixture failed
          env:
            RESULT: ${{ needs.negative-python-lint-fail.result }}
          run: |
            set -euo pipefail
            echo "negative-python-lint-fail result: ${RESULT}"
            if [[ "${RESULT}" == "failure" ]]; then
              echo "✓ Expected failure achieved."
              exit 0
            fi
            echo "::error::python-lint-fail was expected to FAIL but got result=${RESULT}"
            exit 1

    # ---------- Negative fixture: test failure ----------
    negative-python-test-fail:
      name: smoke / python-test-fail (expect fail)
      uses: ./.github/workflows/reusable-pr-gate-python.yml
      with:
        python-version: "3.12"
        working-directory: tests/fixtures/projects/python-test-fail
      continue-on-error: true

    verify-python-test-fail:
      name: verify / python-test-fail failed as expected
      needs: negative-python-test-fail
      if: always()
      runs-on: ubuntu-latest
      steps:
        - name: Assert negative fixture failed
          env:
            RESULT: ${{ needs.negative-python-test-fail.result }}
          run: |
            set -euo pipefail
            echo "negative-python-test-fail result: ${RESULT}"
            if [[ "${RESULT}" == "failure" ]]; then
              echo "✓ Expected failure achieved."
              exit 0
            fi
            echo "::error::python-test-fail was expected to FAIL but got result=${RESULT}"
            exit 1
  ```

  **Design notes:**
  - `continue-on-error: true` on a reusable workflow call allows the caller workflow to proceed even when the reusable fails. The overall workflow status depends on all non-skipped jobs being either success OR having `continue-on-error: true`.
  - The `verify-*` jobs use `if: always()` so they run regardless of the upstream job's status, and they inspect `needs.<job>.result` to assert the expected outcome. If a negative fixture is accidentally "fixed" and starts passing, the verify job fails loudly.
  - If `continue-on-error` on a reusable job turns out not to work as expected during Task 14 verification, the fallback is to expand the smoke-test to inline the reusable's logic with `|| true` guards. See Task 14 for the iteration loop.

- [ ] **Step 11.2: Validate YAML syntax**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/smoke-test.yml'))"
  echo "exit=$?"
  ```

  Expected: exit 0.

- [ ] **Step 11.3: Commit smoke-test.yml**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git add .github/workflows/smoke-test.yml
  git commit -m "test: add smoke-test workflow with positive and negative fixture assertions"
  git log --oneline | head -5
  ```

  Expected: commit succeeds with 1 file changed. Log shows the most recent 5 commits including fixtures, composite actions, reusable workflow, and smoke test.

---

## Part 6: Push to GitHub and iterate on smoke-test

### Task 12: First push and smoke-test verification

This task executes against the GitHub Actions runner and will likely require iteration cycles. Expect to re-run after fixing issues.

- [ ] **Step 12.1: Push feature branch**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git push -u origin feat/phase-1-python-reusable
  ```

  Expected: push succeeds, upstream branch set.

- [ ] **Step 12.2: Wait for smoke-test workflow to start**

  Run:
  ```bash
  sleep 10
  gh run list --branch feat/phase-1-python-reusable --workflow smoke-test.yml --limit 5
  ```

  Expected: at least one run exists for `smoke-test.yml` with status `queued`, `in_progress`, or `completed`.

  If no run appears after 30 seconds, verify:
  - `.github/workflows/smoke-test.yml` exists on the remote: `gh api repos/yakkuro/gh-manage/contents/.github/workflows/smoke-test.yml?ref=feat/phase-1-python-reusable --jq .name`
  - The workflow's `on:` filters allow a push-to-non-main event (should, because `pull_request.paths` includes `.github/workflows/**`)
  - Actually, the current workflow only triggers on `pull_request` and `push` to `main` and `workflow_dispatch`. On first push of a feature branch, smoke-test will NOT run automatically. Use `workflow_dispatch` or open a draft PR.

- [ ] **Step 12.3: Trigger smoke-test manually via workflow_dispatch**

  Run:
  ```bash
  cd ~/repos/gh-manage
  gh workflow run smoke-test.yml --ref feat/phase-1-python-reusable
  sleep 5
  gh run list --branch feat/phase-1-python-reusable --workflow smoke-test.yml --limit 3
  ```

  Expected: a new run appears with status `queued` or `in_progress`.

- [ ] **Step 12.4: Watch the smoke-test run to completion**

  Run:
  ```bash
  cd ~/repos/gh-manage
  RUN_ID=$(gh run list --branch feat/phase-1-python-reusable --workflow smoke-test.yml --limit 1 --json databaseId --jq '.[0].databaseId')
  echo "Watching run: ${RUN_ID}"
  gh run watch "${RUN_ID}" --exit-status
  echo "final exit=$?"
  ```

  Expected: smoke-test completes with exit 0 (success).

  **Expected job outcomes:**
  - `positive-python-sample`: ✅ success
  - `negative-python-lint-fail`: ❌ failure (this is expected, `continue-on-error` marks it "neutral" for caller)
  - `verify-python-lint-fail`: ✅ success (confirms negative fixture failed as expected)
  - `negative-python-test-fail`: ❌ failure (expected)
  - `verify-python-test-fail`: ✅ success

  Note: GitHub may show individual reusable-call jobs with a red X even though the workflow overall is green. This is normal due to `continue-on-error`.

  If the run fails unexpectedly, proceed to Task 13 (iteration).

### Task 13: Iterate on smoke-test failures (if needed)

This task is conditional: execute only if Task 12 did not achieve a green smoke-test on the first try.

- [ ] **Step 13.1: Collect failure details**

  Run:
  ```bash
  cd ~/repos/gh-manage
  RUN_ID=$(gh run list --branch feat/phase-1-python-reusable --workflow smoke-test.yml --limit 1 --json databaseId --jq '.[0].databaseId')
  gh run view "${RUN_ID}" --log-failed
  ```

  Read the failure output carefully. Categorize the failure:
  - **Category A: YAML/syntax error** — the workflow file itself is malformed or references a missing action. Fix locally, commit, push, re-trigger via `gh workflow run`.
  - **Category B: Composite action failure** — an action step failed due to a shell error or tool pin issue. Fix the action.yml, commit, push, re-trigger.
  - **Category C: Fixture project failure** — the fixture doesn't behave as expected (e.g., python-sample fails lint unexpectedly). Fix the fixture, commit, push, re-trigger.
  - **Category D: `continue-on-error` on reusable doesn't work** — if the `negative-*` jobs cascade failure to the overall workflow despite `continue-on-error: true`, this means GitHub Actions treats reusable workflow calls differently. Fall back to the inline approach documented in Step 13.4.

- [ ] **Step 13.2: Apply fix locally**

  Based on the category from Step 13.1, edit the relevant file(s) in place. Examples:
  - Category A: fix YAML indentation or typo in `.github/workflows/*.yml`
  - Category B: fix shell command in `actions/*/action.yml`
  - Category C: fix fixture code in `tests/fixtures/projects/*/`

  After fixing:
  ```bash
  cd ~/repos/gh-manage
  git diff
  git add <edited-files>
  git commit -m "fix: <specific-thing-fixed>"
  git push
  ```

- [ ] **Step 13.3: Re-trigger and re-watch**

  Run:
  ```bash
  cd ~/repos/gh-manage
  gh workflow run smoke-test.yml --ref feat/phase-1-python-reusable
  sleep 5
  RUN_ID=$(gh run list --branch feat/phase-1-python-reusable --workflow smoke-test.yml --limit 1 --json databaseId --jq '.[0].databaseId')
  gh run watch "${RUN_ID}" --exit-status
  echo "final exit=$?"
  ```

  Expected: workflow completes successfully.

  Repeat Steps 13.1–13.3 until smoke-test is green. If you've iterated more than 5 times without progress, STOP and report to the user.

- [ ] **Step 13.4: Fallback — if `continue-on-error` on reusable calls does not work**

  If multiple iterations confirm that `continue-on-error: true` on `uses:` jobs does NOT allow the overall workflow to succeed when the reusable fails, restructure `smoke-test.yml` to use the inline-verification pattern:

  Replace the negative-fixture jobs with inline steps that run the reusable's logic manually inside a regular job, capturing exit codes:

  ```yaml
    negative-python-lint-fail-inline:
      name: smoke / python-lint-fail (inline, expect fail)
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
          with: { fetch-depth: 0 }
        - uses: actions/setup-python@v5
          with: { python-version: "3.12" }
        - uses: astral-sh/setup-uv@v4
          with: { version: "0.5.0" }
        - name: Run ruff (expect failure)
          working-directory: tests/fixtures/projects/python-lint-fail
          run: |
            set +e
            uvx "ruff==0.8.0" check .
            EXIT=$?
            if [[ ${EXIT} -eq 0 ]]; then
              echo "::error::python-lint-fail was expected to FAIL lint but ruff exited 0"
              exit 1
            fi
            echo "✓ Lint failed as expected (exit=${EXIT})"
  ```

  Apply the same pattern to `python-test-fail`. This is a known workaround; the trade-off is that the inline version does NOT test the full reusable workflow call path, only the tool behavior. Document this in `CHANGELOG-reusable.md` as a known limitation if used.

- [ ] **Step 13.5: Commit fallback if used**

  If Step 13.4 was applied:
  ```bash
  cd ~/repos/gh-manage
  git add .github/workflows/smoke-test.yml
  git commit -m "test: switch negative fixtures to inline pattern (continue-on-error on reusable not supported)"
  git push
  ```

---

## Part 7: gh-manage self-dogfood CI

### Task 14: Verify gh-manage passes ruff locally

gh-manage's own code must pass ruff + mypy before we add the dogfood CI workflow, otherwise the PR CI will fail.

- [ ] **Step 14.1: Run ruff against gh-manage source**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uvx "ruff@0.8.0" check src tests
  echo "check exit=$?"
  uvx "ruff@0.8.0" format --check src tests
  echo "format exit=$?"
  ```

  Expected: both commands exit 0.

  If `ruff check` reports issues, list them. Common issues: line length, unused imports, missing docstrings.
  If `ruff format --check` reports diffs, run `uvx "ruff@0.8.0" format src tests` to auto-format.

- [ ] **Step 14.2: If ruff check reports issues, decide whether to fix code or add config**

  If the issues are real (e.g., unused imports), fix them in the source file and re-run.

  If the issues are stylistic preferences gh-manage wants to override, add a minimal `[tool.ruff]` section to `pyproject.toml`:

  ```toml
  [tool.ruff]
  line-length = 100
  target-version = "py312"

  [tool.ruff.lint]
  select = ["E", "F", "W", "I"]
  ```

  (Only add this section if actually needed — do not over-configure preemptively.)

- [ ] **Step 14.3: Verify gh-manage passes mypy locally**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv run --with "mypy==1.12.0" mypy src
  echo "mypy exit=$?"
  ```

  Expected: `Success: no issues found in 2 source files` (for `__init__.py` and `cli.py`), exit 0.

  If mypy reports issues:
  - Add missing type hints to `src/gh_manage/__init__.py` or `src/gh_manage/cli.py`
  - If stubs are missing (unlikely for click 8), add `[tool.mypy]` section to `pyproject.toml`:
    ```toml
    [tool.mypy]
    python_version = "3.12"
    strict = false
    ignore_missing_imports = true
    ```

- [ ] **Step 14.4: Commit any fixes**

  If Steps 14.1–14.3 required changes:
  ```bash
  cd ~/repos/gh-manage
  git diff
  git add -u
  git commit -m "chore: ensure gh-manage source passes pinned ruff and mypy"
  ```

  If no changes were needed, skip this step.

### Task 15: Create `.github/workflows/ci.yml` for gh-manage dogfood

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 15.1: Write ci.yml**

  Write file `.github/workflows/ci.yml` with EXACTLY:
  ```yaml
  name: CI

  on:
    pull_request:
      branches:
        - main
    push:
      branches:
        - main
    workflow_dispatch:

  permissions:
    contents: read

  jobs:
    pr-gate:
      name: PR Gate (self-dogfood)
      uses: ./.github/workflows/reusable-pr-gate-python.yml
      with:
        python-version: "3.12"
        working-directory: "."
        install-command: "uv sync"
        test-command: "uv run pytest"
  ```

  **Design notes:**
  - This workflow calls the reusable via relative path `./.github/workflows/reusable-pr-gate-python.yml` — within the SAME repo, this is valid and always resolves to the current branch's copy.
  - The job name is `pr-gate` — this is what would appear in `required_status_checks.contexts` if we were to enable branch protection on gh-manage itself (Phase 7).
  - We set `working-directory: "."` explicitly even though that's the default, to make the intent clear.
  - Triggering on both `pull_request` AND `push: main` ensures the workflow runs on both PR review and after merge.

- [ ] **Step 15.2: Validate YAML syntax**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
  echo "exit=$?"
  ```

  Expected: exit 0.

- [ ] **Step 15.3: Commit ci.yml**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git add .github/workflows/ci.yml
  git commit -m "ci: add gh-manage self-dogfood CI using reusable-pr-gate-python"
  ```

- [ ] **Step 15.4: Push and verify CI runs**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git push
  sleep 10
  gh run list --branch feat/phase-1-python-reusable --workflow ci.yml --limit 3
  ```

  Expected: a CI run appears (triggered by the push, since push-to-main is the trigger — but we are on a feature branch, so only workflow_dispatch works).

  Since we are on a feature branch and `ci.yml` only triggers on `pull_request`/`push: main`/`workflow_dispatch`, the push alone will NOT trigger `ci.yml`. Either:
  - Trigger manually: `gh workflow run ci.yml --ref feat/phase-1-python-reusable`
  - Or open a draft PR (covered in Task 17)

  For now, trigger manually:
  ```bash
  cd ~/repos/gh-manage
  gh workflow run ci.yml --ref feat/phase-1-python-reusable
  sleep 5
  RUN_ID=$(gh run list --branch feat/phase-1-python-reusable --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId')
  gh run watch "${RUN_ID}" --exit-status
  echo "exit=$?"
  ```

  Expected: workflow completes with exit 0.

  If it fails:
  - Inspect `gh run view ${RUN_ID} --log-failed`
  - Most likely cause: gh-manage's own code doesn't pass ruff/mypy after all, or the relative path resolution doesn't work the way expected for same-repo reusable calls.
  - Fix iteratively. If same-repo relative-path resolution is the problem, the fix is to use the full `yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@feat/phase-1-python-reusable` pattern (absolute reference to the branch's copy).

---

## Part 8: Documentation

### Task 16: Create consumer usage docs

**Files:**
- Create: `docs/usage/python.md`

- [ ] **Step 16.1: Create the docs/usage directory**

  Run:
  ```bash
  cd ~/repos/gh-manage
  mkdir -p docs/usage
  ```

- [ ] **Step 16.2: Write docs/usage/python.md**

  Write file `docs/usage/python.md` with EXACTLY:
  ```markdown
  # Python PR Gate — Consumer Usage

  This guide shows how to use `yakkuro/gh-manage`'s reusable Python PR gate in your own repository.

  ## Prerequisites

  - Your project uses `uv` for dependency management and has a valid `pyproject.toml` at the working-directory root.
  - Your project has type hints on public functions (mypy will check `src/` by default).
  - Your code formatting matches `ruff format` defaults (the reusable runs `ruff format --check`).

  ## Minimal example

  Create `.github/workflows/ci.yml` in your repository:

  ```yaml
  name: CI

  on:
    pull_request:
      branches: [main]

  jobs:
    pr-gate:
      uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v0.1.0
      with:
        python-version: "3.12"
  ```

  That's it. The workflow will:

  1. Check out your repository
  2. Install Python 3.12 and the pinned `uv` version
  3. Run `uv sync` to install dependencies
  4. Run `ruff check .` and `ruff format --check .`
  5. Run `mypy src/`
  6. Run `uv run pytest`

  ## Inputs

  | Input | Type | Default | Description |
  |---|---|---|---|
  | `python-version` | string | **required** | Python version to install (e.g., `"3.12"`). |
  | `working-directory` | string | `"."` | Project directory inside the repo. Set this if your Python project lives in a subdirectory. |
  | `install-command` | string | `"uv sync"` | Dependency install command. |
  | `test-command` | string | `"uv run pytest"` | Test command. |
  | `lint` | boolean | `true` | Run `ruff check` and `ruff format --check`. |
  | `type-check` | boolean | `true` | Run `mypy src/`. |
  | `setup-command` | string | `""` | Optional shell command executed after install, before tests. |
  | `uv-version` | string | `"0.5.0"` | `uv` release pin. Override only if you need a newer release. |

  ## Tool versions

  gh-manage pins tool versions inside its composite actions for reproducibility:

  | Tool | Version |
  |---|---|
  | `uv` | 0.5.0 |
  | `ruff` | 0.8.0 |
  | `mypy` | 1.12.0 |

  These are pinned at the gh-manage level — consumers do not need to pin them in their own `pyproject.toml`. To upgrade a pinned tool, gh-manage must release a new version.

  ## Disabling individual checks

  If your project can't pass `mypy` yet (or you don't want it), disable it:

  ```yaml
  jobs:
    pr-gate:
      uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v0.1.0
      with:
        python-version: "3.12"
        type-check: false
  ```

  Same applies to `lint: false`. Disabling both is possible but defeats the purpose — consider whether you should be using this gate at all.

  ## Setup command for database or filesystem prep

  If your tests need a database or filesystem initialization step:

  ```yaml
  jobs:
    pr-gate:
      uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v0.1.0
      with:
        python-version: "3.12"
        setup-command: "uv run python scripts/init_db.py"
  ```

  The command runs after `install-command` and before `test-command`. Failure aborts the job with a clear error.

  ## Versioning

  `@v0.1.0` is the initial stable reusable workflow release. During the v0.x phase, use immutable version tags (`@v0.1.0`, `@v0.2.0`, etc.). A moving `@v1` tag will exist once gh-manage reaches v1.0.0.

  Pin to a specific immutable tag for production repositories. Use `@main` only for gh-manage development or deliberate tracking of the latest changes.

  ## Troubleshooting

  **ruff format --check fails but my code looks fine** — run `uvx "ruff==0.8.0" format .` locally to see the diff ruff proposes, and commit the result.

  **mypy reports missing stubs** — gh-manage's `run-mypy` composite action uses `uv run --with mypy==1.12.0 mypy src`, which sees your project's installed dependencies. If a dependency lacks type stubs, add the stubs to your `dev` dependency group or set `ignore_missing_imports = true` under `[tool.mypy]` in your `pyproject.toml`.

  **The reusable can't find my project** — double-check `working-directory` matches the path containing `pyproject.toml`.

  **I need a newer ruff/mypy than gh-manage pins** — open an issue on `yakkuro/gh-manage` asking for a pin bump. Do not fork.

  ## See also

  - Design spec: `docs/specs/2026-04-10-gh-manage-design.md`
  - Versioning strategy: `docs/versioning.md` (Phase 9 deliverable)
  ```

- [ ] **Step 16.3: Commit docs**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git add docs/usage/python.md
  git commit -m "docs: add Python PR gate consumer usage guide"
  ```

---

## Part 9: Changelog, PR, review, merge, tag

### Task 17: Create CHANGELOG-reusable.md

**Files:**
- Create: `CHANGELOG-reusable.md`

- [ ] **Step 17.1: Write CHANGELOG-reusable.md**

  Write file `CHANGELOG-reusable.md` with EXACTLY:
  ```markdown
  # Changelog — Reusable Workflows and Composite Actions

  All notable changes to `yakkuro/gh-manage`'s reusable workflows and composite actions are documented here. This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

  The CLI changelog lives in `CHANGELOG-cli.md`.

  ## [Unreleased]

  _Nothing yet._

  ## [0.1.0] - 2026-04-10

  First public release. This marks the initial usable state of gh-manage's Python PR gate.

  ### Added

  - **Reusable workflow `reusable-pr-gate-python.yml`** (Layer 3) — `install → lint → type-check → setup → test` pipeline for Python projects using `uv`. Inputs: `python-version` (required), `working-directory`, `install-command`, `test-command`, `lint`, `type-check`, `setup-command`, `uv-version`.
  - **Composite action `log-gh-manage-version`** (Layer 2) — emits gh-manage version info to workflow logs for traceability.
  - **Composite action `setup-python-uv`** (Layer 2) — installs a requested Python version and a pinned `uv` release. Pinned uv version: `0.5.0`.
  - **Composite action `run-ruff`** (Layer 2) — runs `ruff check .` and `ruff format --check .` with a pinned ruff release. Pinned ruff version: `0.8.0`.
  - **Composite action `run-mypy`** (Layer 2) — runs `mypy src/` via `uv run --with` with a pinned mypy release. Pinned mypy version: `1.12.0`.
  - **Smoke test workflow `.github/workflows/smoke-test.yml`** — verifies the reusable workflow against three fixture projects (`python-sample`, `python-lint-fail`, `python-test-fail`). Positive fixture expected to pass; negative fixtures verified via dependent `verify-*` jobs checking `needs.<job>.result == 'failure'`.
  - **Self-dogfood CI `.github/workflows/ci.yml`** — gh-manage's own PRs run through `reusable-pr-gate-python.yml` at the current feature branch.
  - **Consumer usage documentation** at `docs/usage/python.md`.

  ### Fixed

  _N/A — first release._

  ### Known limitations

  - Only Python 3.12+ is supported. Python 3.11 and below may work but are untested.
  - `mypy` is run against `src/` only. Projects that need to type-check other paths should disable `type-check` and add their own step.
  - The reusable does not currently support matrix-testing multiple Python versions in a single call.
  - GitHub Go, Rust, Java, and other runtimes are not supported in this release — only Python and (planned) TypeScript.

  [Unreleased]: https://github.com/yakkuro/gh-manage/compare/v0.1.0...HEAD
  [0.1.0]: https://github.com/yakkuro/gh-manage/releases/tag/v0.1.0
  ```

- [ ] **Step 17.2: Commit changelog**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git add CHANGELOG-reusable.md
  git commit -m "docs: add CHANGELOG-reusable.md with v0.1.0 entry"
  git log --oneline | head -10
  ```

  Expected: commit succeeds. Recent log shows all Phase 1 commits.

- [ ] **Step 17.3: Push all remaining commits**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git push
  ```

  Expected: push succeeds.

### Task 18: Open pull request

- [ ] **Step 18.1: Create PR**

  Run:
  ```bash
  cd ~/repos/gh-manage
  gh pr create --base main --head feat/phase-1-python-reusable \
    --title "feat: Phase 1 — reusable-pr-gate-python.yml with composite actions, smoke tests, dogfood CI" \
    --body "$(cat <<'EOF'
  ## Summary

  Ships gh-manage's first release-quality artifact: `reusable-pr-gate-python.yml` (Layer 3) composed from four Layer 2 composite actions, verified by a smoke-test workflow running against three fixture projects (1 positive + 2 negative), and dogfooded by gh-manage's own CI.

  This PR completes Phase 1 per `docs/plans/2026-04-10-phase-1-reusable-pr-gate-python.md` and the Phase 1 Acceptance Criteria in `docs/specs/2026-04-10-gh-manage-design.md`.

  ## What changed

  **Layer 2 composite actions (`actions/`):**
  - `log-gh-manage-version` — emits version info to workflow logs
  - `setup-python-uv` — installs Python and pinned `uv` (0.5.0)
  - `run-ruff` — runs `ruff check` + `ruff format --check` with pinned ruff (0.8.0)
  - `run-mypy` — runs `mypy src/` via `uv run --with` with pinned mypy (1.12.0)

  **Layer 3 reusable workflow (`.github/workflows/`):**
  - `reusable-pr-gate-python.yml` — `install → lint → type-check → setup → test` pipeline

  **Test harness (`.github/workflows/` + `tests/fixtures/`):**
  - `smoke-test.yml` — calls reusable on 3 fixture projects; uses `continue-on-error: true` + verify jobs for negative fixtures
  - `tests/fixtures/projects/python-sample/` — positive fixture (all checks pass)
  - `tests/fixtures/projects/python-lint-fail/` — ruff F401 failure fixture
  - `tests/fixtures/projects/python-test-fail/` — pytest failure fixture

  **Dogfood CI:**
  - `.github/workflows/ci.yml` — gh-manage's own PRs call `reusable-pr-gate-python.yml`

  **Docs:**
  - `docs/usage/python.md` — consumer usage guide
  - `CHANGELOG-reusable.md` — v0.1.0 entry

  ## Test plan

  - [ ] `smoke-test.yml` runs green (positive fixture passes; negative fixtures fail as expected, verify jobs succeed)
  - [ ] `ci.yml` (self-dogfood) runs green against this PR
  - [ ] Local verification of each fixture's expected outcome (lint + test locally)
  - [ ] YAML syntax validation of every workflow and composite action file
  - [ ] Manual spot-check of `docs/usage/python.md` for accuracy

  ## Release

  After merge, tag `v0.1.0` from `main`.

  ## Reviewers

  Per `claude-dotfiles/rules/workflow-review.md`, this PR will be reviewed by Codex (`codex-review-resilient.sh`) + three Claude reviewer agents (`superpowers:code-reviewer`, `pr-review-toolkit:silent-failure-hunter`, `code-reviewer`). All CRITICAL and HIGH findings must be addressed before merge.
  EOF
  )"
  ```

  Expected: PR is created, URL is printed.

- [ ] **Step 18.2: Capture PR number**

  Run:
  ```bash
  cd ~/repos/gh-manage
  PR_NUM=$(gh pr list --head feat/phase-1-python-reusable --json number --jq '.[0].number')
  echo "PR number: ${PR_NUM}"
  gh pr view ${PR_NUM}
  ```

  Expected: PR number is printed and basic PR info displays.

- [ ] **Step 18.3: Wait for PR CI (smoke-test + ci.yml)**

  Run:
  ```bash
  cd ~/repos/gh-manage
  PR_NUM=$(gh pr list --head feat/phase-1-python-reusable --json number --jq '.[0].number')
  gh pr checks ${PR_NUM} --watch
  echo "exit=$?"
  ```

  Expected: all checks eventually turn green, exit 0.

  If any check fails, return to Task 13 for iteration. Commits pushed to the feature branch will automatically re-trigger PR CI.

### Task 19: Cross-agent PR review

- [ ] **Step 19.1: Run Codex review via resilient wrapper**

  Run:
  ```bash
  cd ~/repos/gh-manage
  bash ~/repos/claude-dotfiles/scripts/codex-review-resilient.sh "Review PR for Phase 1 of gh-manage. Focus on: (1) correctness of the reusable workflow structure and relative action paths, (2) safety of eval in shell steps with user-supplied inputs, (3) completeness of the smoke test's negative-fixture verification pattern, (4) whether tool version pins are reproducible, (5) any missing error handling in composite actions. Base: main. Files changed: .github/workflows/*, actions/*, tests/fixtures/projects/*, docs/usage/python.md, CHANGELOG-reusable.md. Report CRITICAL/HIGH/MEDIUM/LOW findings."
  ```

  Expected: Codex review completes (may take several minutes). Findings are printed to stdout or stored in a result file.

- [ ] **Step 19.2: Dispatch three Claude reviewer agents in parallel**

  Per `rules/workflow-review.md`, dispatch three agents in a single message (the controller will do this, not documented here as runnable bash since it requires the Agent tool).

  Target reviewers:
  1. `superpowers:code-reviewer` — spec alignment and scope
  2. `pr-review-toolkit:silent-failure-hunter` — hidden error handling
  3. `code-reviewer` — project convention adherence

  Each reviewer receives:
  - The diff (`git diff main..feat/phase-1-python-reusable`)
  - The spec path: `docs/specs/2026-04-10-gh-manage-design.md`
  - The plan path: `docs/plans/2026-04-10-phase-1-reusable-pr-gate-python.md`

- [ ] **Step 19.3: Triage findings**

  For each reviewer's output:
  - **CRITICAL**: must fix before merge. Apply fix, commit, push, re-verify CI.
  - **HIGH**: should fix before merge unless there's a documented reason to defer.
  - **MEDIUM**: judgment call. Fix if quick; defer with a new Issue if not.
  - **LOW**: usually defer to `Open Questions` in the spec.

  Report triage decisions as a PR comment before merge.

### Task 20: Merge PR

- [ ] **Step 20.1: Verify all checks green**

  Run:
  ```bash
  cd ~/repos/gh-manage
  PR_NUM=$(gh pr list --head feat/phase-1-python-reusable --json number --jq '.[0].number')
  gh pr checks ${PR_NUM}
  ```

  Expected: all checks display as `pass` or similar green indicator.

- [ ] **Step 20.2: Squash merge**

  Run:
  ```bash
  cd ~/repos/gh-manage
  PR_NUM=$(gh pr list --head feat/phase-1-python-reusable --json number --jq '.[0].number')
  gh pr merge ${PR_NUM} --squash --delete-branch
  ```

  Expected: PR merges, feature branch is deleted on remote.

- [ ] **Step 20.3: Sync local main**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git checkout main
  git pull --ff-only
  git log --oneline | head -5
  ```

  Expected: local `main` is now at the squash merge commit. The feature branch is gone.

  Also prune the local feature branch:
  ```bash
  cd ~/repos/gh-manage
  git branch -d feat/phase-1-python-reusable
  ```

  Expected: local branch deleted.

### Task 21: Tag v0.1.0

- [ ] **Step 21.1: Verify current commit is on main**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git rev-parse HEAD
  git rev-parse origin/main
  git status
  ```

  Expected: HEAD, local `main`, and `origin/main` all point to the same commit. Working tree clean.

- [ ] **Step 21.2: Create annotated tag v0.1.0**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git tag -a v0.1.0 -m "v0.1.0: reusable-pr-gate-python.yml with Layer 2 composite actions, smoke tests, dogfood CI"
  git tag --list
  ```

  Expected: `v0.1.0` appears in the tag list.

- [ ] **Step 21.3: Push the tag**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git push origin v0.1.0
  gh api repos/yakkuro/gh-manage/git/ref/tags/v0.1.0 --jq '.object.sha'
  ```

  Expected: push succeeds, remote tag SHA is printed.

- [ ] **Step 21.4: Create GitHub release (optional, recommended)**

  Run:
  ```bash
  cd ~/repos/gh-manage
  gh release create v0.1.0 \
    --title "v0.1.0 — Reusable Python PR Gate" \
    --notes "$(cat <<'EOF'
  First release of gh-manage.

  **Highlights:**
  - Reusable workflow `reusable-pr-gate-python.yml` for Python projects using `uv`
  - Four composite actions pinning `uv` (0.5.0), `ruff` (0.8.0), `mypy` (1.12.0)
  - Consumer usage guide at `docs/usage/python.md`
  - Smoke test verifies positive + 2 negative fixture projects

  **Getting started:**

  Add to your `.github/workflows/ci.yml`:

  ```yaml
  jobs:
    pr-gate:
      uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v0.1.0
      with:
        python-version: "3.12"
  ```

  See `docs/usage/python.md` for full input reference and troubleshooting.

  Full changelog: `CHANGELOG-reusable.md`.
  EOF
  )"
  ```

  Expected: release is created. A release notification appears on the repo's releases page.

---

## Part 10: Phase 1 verification gate

### Task 22: Verify all Phase 1 Acceptance Criteria

Per the design spec's `Phase 1 (Python reusable)` section:

- [ ] **AC-P1-1: Reusable workflow exists**

  Run:
  ```bash
  gh api repos/yakkuro/gh-manage/contents/.github/workflows/reusable-pr-gate-python.yml?ref=v0.1.0 --jq .name
  ```

  Expected: `reusable-pr-gate-python.yml`

- [ ] **AC-P1-2: All four composite actions exist**

  Run:
  ```bash
  for a in log-gh-manage-version setup-python-uv run-ruff run-mypy; do
    gh api "repos/yakkuro/gh-manage/contents/actions/${a}/action.yml?ref=v0.1.0" --jq .name
  done
  ```

  Expected: four lines, each printing `action.yml`.

- [ ] **AC-P1-3: Positive fixture passes smoke test**

  Run:
  ```bash
  gh run list --workflow smoke-test.yml --branch main --limit 1 --json conclusion,name,databaseId
  ```

  Expected: most recent run on `main` has `"conclusion": "success"`.

- [ ] **AC-P1-4: Negative fixtures fail as expected in smoke test**

  Run:
  ```bash
  RUN_ID=$(gh run list --workflow smoke-test.yml --branch main --limit 1 --json databaseId --jq '.[0].databaseId')
  gh run view ${RUN_ID} --json jobs --jq '.jobs[] | {name: .name, conclusion: .conclusion}'
  ```

  Expected output includes:
  ```
  {"name":"smoke / python-sample (expect pass)","conclusion":"success"}
  {"name":"smoke / python-lint-fail (expect fail)","conclusion":"failure"}
  {"name":"verify / python-lint-fail failed as expected","conclusion":"success"}
  {"name":"smoke / python-test-fail (expect fail)","conclusion":"failure"}
  {"name":"verify / python-test-fail failed as expected","conclusion":"success"}
  ```

  (If using the fallback inline pattern from Task 13.4, the job names will differ but the overall workflow conclusion should still be `success`.)

- [ ] **AC-P1-5: gh-manage's own PR CI uses reusable-pr-gate-python.yml**

  Run:
  ```bash
  cd ~/repos/gh-manage
  grep -q "reusable-pr-gate-python.yml" .github/workflows/ci.yml && echo "ok" || echo "MISSING"
  ```

  Expected: `ok`.

- [ ] **AC-P1-6: Tag v0.1.0 exists**

  Run:
  ```bash
  gh api repos/yakkuro/gh-manage/git/ref/tags/v0.1.0 --jq '.object.type, .object.sha'
  ```

  Expected: two lines, `"tag"` (or `"commit"` for lightweight) followed by the SHA.

- [ ] **AC-P1-7: Declare Phase 1 complete**

  Report to the user:

  > "Phase 1 complete. `yakkuro/gh-manage@v0.1.0` released with reusable-pr-gate-python.yml, four composite actions, three fixture projects, smoke test, and self-dogfood CI all verified green. The reusable workflow is ready for external consumers (Phase 3 target: port-registry) and gh-manage itself uses it for every PR."

---

## Phase 1 Exit Checklist (summary)

- [ ] Feature branch `feat/phase-1-python-reusable` was created, used, and deleted after merge
- [ ] Three fixture projects (positive + 2 negative) created and verified locally
- [ ] Four composite actions created and YAML-validated locally
- [ ] `reusable-pr-gate-python.yml` created and YAML-validated
- [ ] `smoke-test.yml` created and runs green on GitHub (positive + 2 negative with verify jobs)
- [ ] `ci.yml` for gh-manage self-dogfood created and runs green on the PR
- [ ] gh-manage's own source passes ruff and mypy with the pinned versions
- [ ] `docs/usage/python.md` created
- [ ] `CHANGELOG-reusable.md` created with v0.1.0 entry
- [ ] PR opened, all CI green, Codex + 3 reviewer agents completed, findings triaged
- [ ] PR merged to `main` via squash
- [ ] Tag `v0.1.0` created and pushed
- [ ] GitHub release created
- [ ] All Phase 1 Acceptance Criteria (AC-P1-1 through AC-P1-7) verified

---

## Out of Scope for Phase 1

Explicitly NOT part of this plan — these belong to later phases:

- `reusable-pr-gate-typescript.yml` and TypeScript composite actions (Phase 2)
- Applying reusable workflow to an external consumer repo like `port-registry` (Phase 3)
- `reusable-pr-gate-go.yml` (deferred until Go consumer needs exist)
- `reusable-ci-review.yml` with gitleaks + size warning (deferred; not in Phase 1 acceptance criteria but will be added in a later Phase 1.x or Phase 2.x)
- `src/gh_manage/commands/*` CLI subcommands (Phase 4+)
- `config/labels.yml`, `config/branch-protection.yml`, `config/repos.yml` (Phase 4)
- `config/profiles/*.yml` (Phase 4)
- `templates/ci/`, `templates/issue/`, etc. (Phase 6)
- `drift-scanner.yml` and drift detection (Phase 8)
- Branch protection on `yakkuro/gh-manage` itself (Phase 7)
- External consumer adoption (Phase 3)

---

## Known Risks and Contingencies

| Risk | Impact | Contingency |
|---|---|---|
| `continue-on-error: true` on a reusable-workflow `uses:` job does NOT cause the overall workflow to succeed when the reusable fails | Negative smoke tests fail → overall smoke-test fails | Fall back to inline pattern (Step 13.4): verify negative fixtures by running ruff/pytest directly in a regular job with explicit exit-code checks |
| Relative action paths (`./actions/...`) don't resolve correctly for same-repo reusable calls in `ci.yml` | Dogfood CI fails to find the composite actions | Use explicit branch reference: `yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@feat/phase-1-python-reusable` during development, switch to `@v0.1.0` after tag exists |
| gh-manage's own `src/gh_manage/cli.py` fails mypy or ruff under pinned versions | Self-dogfood CI fails immediately | Fix the source or add minimal `[tool.mypy]` / `[tool.ruff]` config in `pyproject.toml` (Task 14) |
| `uvx ruff@0.8.0 format --check .` is stricter than expected and flags fixture files | smoke-test fails at format step | Run `uvx ruff@0.8.0 format .` against the fixture, commit the formatted version, re-run |
| `uv run --with mypy==1.12.0 mypy src` can't resolve the fixture's venv correctly | mypy step fails for fixtures | Pre-run `uv sync` in the fixture directory before the mypy step — the reusable workflow already does this via `install-command` which runs before `run-mypy`, so this should work |
| GitHub Actions rate limit during iteration | Can't re-run smoke-test frequently | Rate limits for workflow runs are generous for private repos; should not be an issue for Phase 1 |
| Codex review takes >5 minutes and hits internal timeout | Review step hangs | `codex-review-resilient.sh` has 3-stage fallback; if all 3 fail, proceed with the 3 Claude reviewer agents only and note the skip in PR comments |

---

## Notes for the Implementer

- **Bottom-up order:** Fixtures first, then composite actions, then reusable workflow, then smoke test, then dogfood CI. Each layer depends on the previous. Do not skip ahead.
- **Verify locally before pushing.** Every fixture check has a local verification step. Use them. The GitHub Actions feedback loop is 30-90 seconds per iteration; local iteration is < 5 seconds.
- **Pin tool versions religiously.** `ruff==0.8.0`, `mypy==1.12.0`, `uv 0.5.0` are declared in this plan. Do not substitute newer versions mid-execution without documenting the change in `CHANGELOG-reusable.md`.
- **Relative action paths:** The reusable workflow uses `./actions/<name>` which GitHub resolves from gh-manage's own repo (not the consumer's). This is correct and documented in the design notes of Task 10.
- **`continue-on-error` fallback:** If this pattern doesn't work on reusable jobs, Task 13.4 provides an inline alternative. Do not waste more than 2 iteration cycles trying to make `continue-on-error` work if it's not behaving — switch to the fallback.
- **Do not merge with failing CI.** The Phase 0 commit of the Phase 0 plan established the pattern: `main` is protected by intention, not yet by branch protection rules. Self-discipline matters.
- **Tag `v0.1.0` only AFTER merge to `main`.** The tag should point to a commit on `main`, not on the feature branch. Task 21 Step 21.1 verifies this.
- **No `@v0` moving tag.** Per the design spec, the moving `@v<major>` tag convention starts at `v1`. During the v0.x phase, only immutable tags exist.
- **Commit messages use Conventional Commits.** Examples used in this plan: `test:`, `feat:`, `ci:`, `docs:`, `chore:`, `fix:`.
- **When iterating on smoke-test failures, commit each fix as a separate commit** with a `fix:` prefix. This keeps the history readable and makes it easy to identify which iteration addressed which issue.
- **The final merge squashes all feature-branch commits into one.** This is intentional — the feature branch history is for development, the main history is for releases.
