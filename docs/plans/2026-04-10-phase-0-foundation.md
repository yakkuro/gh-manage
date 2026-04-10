# gh-manage Phase 0 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Initialize the `gh-manage` repository with git, a GitHub remote under `yakkuro`, a Python 3.12 project skeleton managed by `uv`, a pytest setup that runs green, and minimal documentation stubs. Phase 0 intentionally contains no implementation code beyond scaffolding.

**Architecture:** Python 3.12 project with src layout (`src/gh_manage/`), `uv` for dependency management, `pytest` for testing, `hatchling` as build backend, `gh-manage` shim at repo root for future gh extension entrypoint. Directory skeleton follows the spec's § Repository Layout, but only the subset needed for Phase 0 (scaffolding for Python package + tests + docs). Subsequent phases will create their own top-level directories (`actions/`, `config/`, `templates/`, `scripts/`).

**Tech Stack:**
- Python 3.12
- `uv` (package and env management)
- `hatchling` (build backend)
- `pytest` 8 + `pytest-cov` + `pytest-mock`
- `click` 8 (CLI framework — locked in here so that Phase 4 can start immediately)
- `pydantic` v2 (schema validation — placeholder dependency for Phase 4)
- `pyyaml` (config file parsing — placeholder dependency for Phase 4)
- `git`, `gh` CLI (infrastructure)

**Assumptions:**
- `~/repos/gh-manage/` already exists as an empty directory containing only `docs/specs/2026-04-10-gh-manage-design.md` and `docs/plans/` (empty).
- `gh auth status` reports an active authentication for the `yakkuro` account.
- `uv` is installed and on PATH.
- `git` 2.x is installed.
- The working directory for all shell commands is `~/repos/gh-manage/` unless otherwise stated.

**Interpretation of Phase 0 Acceptance Criterion "pytest が 0 test で成功する":** The literal reading is impossible because `pytest` returns exit code 5 when no tests are collected. This plan interprets the criterion as "pytest runs without errors and all collected tests pass," and adds a single sanity test (`tests/test_sanity.py::test_sanity`) to make pytest's exit code 0. The sanity test also verifies that the `src` layout is resolvable as a pytest `pythonpath`.

---

## Pre-flight Checks

- [ ] **PF-1: Verify gh authentication**

  Run:
  ```bash
  gh auth status
  ```
  Expected: output includes `Logged in to github.com as yakkuro` (account name may differ — must match the owner used in the spec).

  If not authenticated, run `gh auth login` interactively and retry.

- [ ] **PF-2: Verify uv is installed**

  Run:
  ```bash
  uv --version
  ```
  Expected: prints a uv version (e.g., `uv 0.5.0`). If missing, install via `curl -LsSf https://astral.sh/uv/install.sh | sh` or the user's preferred method, then retry.

- [ ] **PF-3: Verify git is installed**

  Run:
  ```bash
  git --version
  ```
  Expected: prints a git version (e.g., `git version 2.43.0`).

- [ ] **PF-4: Verify working directory and existing files**

  Run:
  ```bash
  cd ~/repos/gh-manage
  pwd
  ls -la
  test -f docs/specs/2026-04-10-gh-manage-design.md && echo "spec: ok" || echo "spec: MISSING"
  ```
  Expected:
  - `pwd` prints `/home/server160/repos/gh-manage`
  - `docs/` directory exists (contains `plans/` and `specs/`)
  - No `.git/` directory yet
  - spec: ok

  If the spec file is missing, STOP. Something is wrong with the handoff from brainstorming.

- [ ] **PF-5: Verify there is no existing GitHub repo at `yakkuro/gh-manage`**

  Run:
  ```bash
  gh repo view yakkuro/gh-manage 2>&1 || echo "REPO_ABSENT"
  ```
  Expected: either `REPO_ABSENT` (shown when `gh repo view` fails) or an existing repo.

  If the repo already exists on GitHub, STOP and consult the user before proceeding. Do NOT force-push, delete, or overwrite an existing repo without explicit approval.

---

## Task 1: Initialize local git repository with base files

**Files:**
- Create: `~/repos/gh-manage/.gitignore`
- Create: `~/repos/gh-manage/LICENSE`
- Create: `~/repos/gh-manage/README.md`

**Steps:**

- [ ] **Step 1.1: Initialize git repo with main branch**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git init -b main
  ```
  Expected output: `Initialized empty Git repository in /home/server160/repos/gh-manage/.git/`

- [ ] **Step 1.2: Create `.gitignore`**

  Write file `~/repos/gh-manage/.gitignore` with exactly this content:
  ```
  # Python
  __pycache__/
  *.py[cod]
  *$py.class
  *.egg-info/
  .pytest_cache/
  .mypy_cache/
  .ruff_cache/
  .coverage
  .coverage.*
  htmlcov/
  dist/
  build/

  # uv / virtualenv
  .venv/
  venv/

  # IDE and OS
  .vscode/
  .idea/
  *.swp
  *.swo
  .DS_Store
  Thumbs.db

  # gh-manage runtime artifacts
  .gh-manage-backup/
  .gh-manage-reports/

  # Scratchpads
  .scratch/
  ```

- [ ] **Step 1.3: Create `LICENSE` (MIT)**

  Write file `~/repos/gh-manage/LICENSE` with exactly this content:
  ```
  MIT License

  Copyright (c) 2026 yakkuro

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in all
  copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
  SOFTWARE.
  ```

- [ ] **Step 1.4: Create `README.md`**

  Write file `~/repos/gh-manage/README.md` with exactly this content:
  ```markdown
  # gh-manage

  **Status:** early development — not yet released.

  GitHub-based CI/CD, Issue management, and operational system for `yakkuro/*` repositories.

  `gh-manage` distributes reusable GitHub Actions workflows, composite actions, Issue/PR templates, label definitions, and branch protection policies across multiple repositories under a single declarative source.

  ## Scope

  - Reusable workflows for Python and TypeScript PR quality gates
  - CI-driven policy review (gitleaks, size warning — distinct from Claude-runtime review)
  - Cross-repository label and branch protection management via a `gh` CLI extension
  - New-repository bootstrapping via `gh manage init`
  - Scheduled drift detection with Issue-based reporting

  ## Design

  See the [design specification](docs/specs/2026-04-10-gh-manage-design.md) for the full architecture, component decomposition, versioning strategy, and rollout plan.

  ## License

  MIT. See [LICENSE](LICENSE).
  ```

- [ ] **Step 1.5: Verify the three files exist**

  Run:
  ```bash
  cd ~/repos/gh-manage
  ls -la .gitignore LICENSE README.md
  wc -l .gitignore LICENSE README.md
  ```
  Expected: three files listed with non-zero sizes. `.gitignore` ≈ 30 lines, `LICENSE` ≈ 21 lines, `README.md` ≈ 25 lines.

- [ ] **Step 1.6: Stage and commit the base files plus the existing spec**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git add .gitignore LICENSE README.md docs/specs/2026-04-10-gh-manage-design.md docs/plans/2026-04-10-phase-0-foundation.md
  git status
  ```
  Expected: `git status` shows all five files as `new file` under "Changes to be committed".

  Then commit:
  ```bash
  git commit -m "chore: initial commit with base files, spec, and Phase 0 plan"
  ```
  Expected output includes `5 files changed` or similar, with the SHA prefix of a new commit.

---

## Task 2: Create Python package skeleton (src layout)

**Files:**
- Create: `~/repos/gh-manage/src/gh_manage/__init__.py`
- Create: `~/repos/gh-manage/src/gh_manage/cli.py`
- Create: `~/repos/gh-manage/tests/__init__.py`
- Create: `~/repos/gh-manage/tests/test_sanity.py`

**Steps:**

- [ ] **Step 2.1: Create the `src/gh_manage/` directory and package init**

  Run:
  ```bash
  cd ~/repos/gh-manage
  mkdir -p src/gh_manage
  ```

  Write file `~/repos/gh-manage/src/gh_manage/__init__.py` with exactly this content:
  ```python
  """gh-manage: GitHub-based CI/CD, Issue management, and operational system."""

  __version__ = "0.0.0"
  ```

- [ ] **Step 2.2: Create a minimal CLI entry stub**

  Write file `~/repos/gh-manage/src/gh_manage/cli.py` with exactly this content:
  ```python
  """Entry point for the gh-manage CLI.

  Phase 0 provides only a --version stub. Full command wiring lands in Phase 4.
  """

  from __future__ import annotations

  import click

  from gh_manage import __version__


  @click.group(help="gh-manage — GitHub-based CI/CD, Issue management, and operations.")
  @click.version_option(version=__version__, prog_name="gh-manage")
  def main() -> None:
      """Root command group. Subcommands are added in later phases."""


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 2.3: Create the `tests/` directory with an `__init__.py`**

  Run:
  ```bash
  cd ~/repos/gh-manage
  mkdir -p tests
  ```

  Write file `~/repos/gh-manage/tests/__init__.py` with exactly this content:
  ```python
  """Test suite for gh-manage."""
  ```

- [ ] **Step 2.4: Write the sanity test (fail-first TDD)**

  Write file `~/repos/gh-manage/tests/test_sanity.py` with exactly this content:
  ```python
  """Sanity tests that verify the Phase 0 scaffolding is wired correctly."""

  from __future__ import annotations

  import gh_manage


  def test_package_version_is_defined() -> None:
      assert hasattr(gh_manage, "__version__")
      assert isinstance(gh_manage.__version__, str)
      assert gh_manage.__version__ == "0.0.0"


  def test_cli_module_is_importable() -> None:
      from gh_manage import cli

      assert hasattr(cli, "main")
      assert callable(cli.main)
  ```

- [ ] **Step 2.5: Verify files are in place**

  Run:
  ```bash
  cd ~/repos/gh-manage
  find src tests -type f -name '*.py' | sort
  ```
  Expected output (exact):
  ```
  src/gh_manage/__init__.py
  src/gh_manage/cli.py
  tests/__init__.py
  tests/test_sanity.py
  ```

Note: we do NOT commit yet. The package is not installable until Task 3 creates `pyproject.toml`.

---

## Task 3: Set up `pyproject.toml` and run `uv sync`

**Files:**
- Create: `~/repos/gh-manage/pyproject.toml`
- Created by `uv sync`: `~/repos/gh-manage/uv.lock`
- Created by `uv sync`: `~/repos/gh-manage/.venv/` (ignored by .gitignore)

**Steps:**

- [ ] **Step 3.1: Create `pyproject.toml`**

  Write file `~/repos/gh-manage/pyproject.toml` with exactly this content:
  ```toml
  [project]
  name = "gh-manage"
  version = "0.0.0"
  description = "GitHub-based CI/CD, Issue management, and operational system for yakkuro/* repositories."
  readme = "README.md"
  license = { file = "LICENSE" }
  requires-python = ">=3.12"
  authors = [
      { name = "yakkuro" },
  ]
  keywords = ["github", "ci", "cd", "devops", "automation"]
  classifiers = [
      "Development Status :: 2 - Pre-Alpha",
      "Environment :: Console",
      "Intended Audience :: Developers",
      "License :: OSI Approved :: MIT License",
      "Operating System :: POSIX :: Linux",
      "Programming Language :: Python :: 3",
      "Programming Language :: Python :: 3.12",
      "Topic :: Software Development :: Build Tools",
  ]
  dependencies = [
      "click>=8.1,<9",
      "pydantic>=2.5,<3",
      "pyyaml>=6.0,<7",
  ]

  [project.scripts]
  gh-manage = "gh_manage.cli:main"

  [project.urls]
  Homepage = "https://github.com/yakkuro/gh-manage"
  Repository = "https://github.com/yakkuro/gh-manage"
  Issues = "https://github.com/yakkuro/gh-manage/issues"

  [dependency-groups]
  dev = [
      "pytest>=8.0,<9",
      "pytest-cov>=5.0,<6",
      "pytest-mock>=3.12,<4",
  ]

  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"

  [tool.hatch.build.targets.wheel]
  packages = ["src/gh_manage"]

  [tool.pytest.ini_options]
  minversion = "8.0"
  testpaths = ["tests"]
  pythonpath = ["src"]
  addopts = [
      "--strict-markers",
      "--strict-config",
      "-ra",
  ]
  ```

- [ ] **Step 3.2: Run `uv sync` to create the virtualenv and install dependencies**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv sync
  ```
  Expected output:
  - uv resolves and installs Python 3.12 if not available locally
  - Creates `.venv/` in the working directory
  - Creates `uv.lock`
  - Installs `click`, `pydantic`, `pyyaml`, `pytest`, `pytest-cov`, `pytest-mock` and their transitive deps
  - Final summary line reports installed package count (format: `Installed <N> packages in <duration>`)

  If this fails due to network or Python version issues, STOP and surface the error to the user. Do not skip.

- [ ] **Step 3.3: Verify `uv.lock` was created**

  Run:
  ```bash
  cd ~/repos/gh-manage
  ls -la uv.lock
  wc -l uv.lock
  ```
  Expected: `uv.lock` exists with more than 100 lines (transitive dependency tree).

- [ ] **Step 3.4: Verify the package is importable and version is accessible**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv run python -c "import gh_manage; print(gh_manage.__version__)"
  ```
  Expected output:
  ```
  0.0.0
  ```

- [ ] **Step 3.5: Verify the CLI --version works via uv run**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv run gh-manage --version
  ```
  Expected output:
  ```
  gh-manage, version 0.0.0
  ```

  If this prints a different format (e.g., click's default), it is still acceptable as long as the exit code is 0 and the version string `0.0.0` appears. If the command is not found, verify `[project.scripts]` in `pyproject.toml` matches `gh-manage = "gh_manage.cli:main"` and re-run `uv sync`.

- [ ] **Step 3.6: Run the sanity test suite**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv run pytest -v
  ```
  Expected output:
  - `collected 2 items` (the two sanity tests from Task 2)
  - Both tests PASS
  - Exit code 0 (confirm by running `echo $?` immediately after)

- [ ] **Step 3.7: Red-Green verification of the sanity test**

  Temporarily break the sanity test to confirm pytest is actually running it. Run:
  ```bash
  cd ~/repos/gh-manage
  sed -i.bak 's/__version__ == "0.0.0"/__version__ == "9.9.9"/' tests/test_sanity.py
  uv run pytest tests/test_sanity.py::test_package_version_is_defined -v
  ```
  Expected: test FAILS with an assertion error about the version mismatch.

  Then restore:
  ```bash
  cd ~/repos/gh-manage
  mv tests/test_sanity.py.bak tests/test_sanity.py
  uv run pytest tests/test_sanity.py -v
  ```
  Expected: both tests PASS.

- [ ] **Step 3.8: Stage and commit Task 2 + Task 3 artifacts**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git add pyproject.toml uv.lock src/ tests/
  git status
  ```
  Expected: `src/gh_manage/__init__.py`, `src/gh_manage/cli.py`, `tests/__init__.py`, `tests/test_sanity.py`, `pyproject.toml`, `uv.lock` listed as new files. `.venv/` must NOT appear (it is ignored).

  Then commit:
  ```bash
  git commit -m "feat: add Python package skeleton and sanity tests"
  ```
  Expected: commit succeeds with 6 files changed.

---

## Task 4: Create gh-manage local `CLAUDE.md`

**Files:**
- Create: `~/repos/gh-manage/CLAUDE.md`

**Steps:**

- [ ] **Step 4.1: Write the local `CLAUDE.md`**

  Write file `~/repos/gh-manage/CLAUDE.md` with exactly this content:
  ```markdown
  # gh-manage — Local Claude Rules

  This file provides project-specific Claude Code instructions for the `gh-manage` repository. It does NOT replace the global rules in `~/.claude/CLAUDE.md` (maintained in `claude-dotfiles`); it supplements them with gh-manage-specific conventions.

  ## Project overview

  `gh-manage` is the GitHub-based CI/CD, Issue management, and operational system for `yakkuro/*` repositories. It distributes reusable workflows, composite actions, Issue/PR templates, label definitions, and branch protection policies. See [the design spec](docs/specs/2026-04-10-gh-manage-design.md) for full architecture.

  ## Portability principle (load-bearing)

  `gh-manage` must NOT depend on `claude-dotfiles` at runtime. The reverse direction is allowed: `claude-dotfiles` may reference `gh-manage` documentation, but `gh-manage` is self-contained and must remain installable and operable without any Claude harness.

  Do not add runtime dependencies on `claude-dotfiles` scripts, rules, or skills. If you find yourself reaching into `~/repos/claude-dotfiles/`, pause and reconsider.

  ## Tech stack (locked in Phase 0)

  - Python 3.12, managed by `uv`
  - `hatchling` build backend, src layout (`src/gh_manage/`)
  - `click` 8.x for CLI
  - `pydantic` v2 for schema validation
  - `pyyaml` for config files
  - `pytest` 8 + `pytest-cov` + `pytest-mock`
  - `gh` CLI (subprocess) for GitHub API interactions — no direct REST client

  ## Development conventions

  - **TDD is mandatory.** Write the failing test first, confirm Red, write the implementation, confirm Green, then refactor. This inherits the `superpowers:test-driven-development` rules from the global claude-dotfiles harness.
  - **No silent failures.** Bare `except: pass` and swallowed errors are forbidden. Every exception must be handled explicitly with user-visible context.
  - **Error messages must be actionable.** Every error should describe what happened AND what the user should do next.
  - **All `gh api` calls go through `src/gh_manage/github_client.py`** — this constraint takes effect when Phase 4 adds the CLI, but plan code accordingly from the start.
  - **All composite action shell scripts must start with `set -euo pipefail`** — this constraint takes effect when Phase 1 adds composite actions.

  ## Git and PR workflow

  - Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `ci:`, `build:`.
  - Branch from `main` using `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, etc.
  - **Direct commits to `main` are forbidden.** Always use a PR (enforced by branch protection starting in Phase 7).
  - **PR review is required before merge:** the Codex + three-reviewer-agent protocol defined in `claude-dotfiles/rules/workflow-review.md` runs against every PR. That review is a Claude runtime workflow and lives in `claude-dotfiles` — do NOT port it into `gh-manage`.
  - PR titles follow Conventional Commits.

  ## Scope boundaries (do not implement in gh-manage)

  These belong elsewhere or are explicitly deferred. Do not add them without updating the design spec:

  - Claude runtime workflows (subagents, skills, hooks, rules/workflow-review.md)
  - Cross-repo dashboard UI (domain F, deferred)
  - Release management for other repos (domain G, deferred)
  - Dependency management / Dependabot distribution (domain H, deferred)
  - GitHub Enterprise support (out of scope — yakkuro org only)
  - PyPI publishing (deferred until post v1.0)
  - `act` / nektos local Actions execution

  See the design spec's `## Non-Goals` section for the authoritative list.

  ## Reference documents

  - Design spec: `docs/specs/2026-04-10-gh-manage-design.md`
  - Phase 0 plan: `docs/plans/2026-04-10-phase-0-foundation.md`
  - Global rules: `~/.claude/CLAUDE.md` (from `claude-dotfiles`)
  ```

- [ ] **Step 4.2: Verify the file was written**

  Run:
  ```bash
  cd ~/repos/gh-manage
  wc -l CLAUDE.md
  head -3 CLAUDE.md
  ```
  Expected: non-zero line count (~60 lines), first line is `# gh-manage — Local Claude Rules`.

- [ ] **Step 4.3: Commit `CLAUDE.md`**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git add CLAUDE.md
  git commit -m "docs: add local CLAUDE.md with gh-manage conventions"
  ```
  Expected: commit succeeds with 1 file changed.

---

## Task 5: Create the GitHub repository and push

**Files:** none created locally. Task 5 affects `yakkuro/gh-manage` on GitHub and `~/repos/gh-manage/.git/config`.

**Steps:**

- [ ] **Step 5.1: Confirm with the user before creating the GitHub repo**

  If this plan is being executed by a subagent or autonomous flow, pause here and surface a confirmation to the user. Creating a GitHub repository is an action visible outside the local machine and should be explicitly confirmed.

  Prompt the user with:
  > "About to create `yakkuro/gh-manage` as a **private** repository on GitHub, then push the local `main` branch. Proceed?"

  Do not continue until the user confirms.

- [ ] **Step 5.2: Create the GitHub repository**

  Run:
  ```bash
  cd ~/repos/gh-manage
  gh repo create yakkuro/gh-manage \
      --private \
      --description "GitHub-based CI/CD, Issue management, and operational system for yakkuro/* repositories." \
      --source=. \
      --remote=origin
  ```
  Expected output:
  - `✓ Created repository yakkuro/gh-manage on GitHub`
  - `✓ Added remote https://github.com/yakkuro/gh-manage.git`

  Note: `--source=.` configures the existing local repo as the source, and `--remote=origin` wires the remote. We do NOT pass `--push` so that the push is an explicit, separate step below.

- [ ] **Step 5.3: Verify remote is configured**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git remote -v
  ```
  Expected output (both lines):
  ```
  origin	https://github.com/yakkuro/gh-manage.git (fetch)
  origin	https://github.com/yakkuro/gh-manage.git (push)
  ```

  If the remote URL uses `git@github.com:` (SSH form), that is equally acceptable.

- [ ] **Step 5.4: Push the `main` branch**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git push -u origin main
  ```
  Expected: push succeeds, upstream branch is set to `origin/main`. Output ends with `branch 'main' set up to track 'origin/main'.`

- [ ] **Step 5.5: Verify the repo is visible on GitHub**

  Run:
  ```bash
  gh repo view yakkuro/gh-manage --json name,url,visibility,defaultBranchRef
  ```
  Expected JSON output includes:
  - `"name": "gh-manage"`
  - `"url": "https://github.com/yakkuro/gh-manage"`
  - `"visibility": "PRIVATE"`
  - `"defaultBranchRef": {"name": "main"}`

---

## Task 6: Verify all Phase 0 acceptance criteria

**Files:** none modified. This task is the Phase 0 exit gate.

Run every check below and confirm each one passes. If any check fails, STOP and diagnose before declaring Phase 0 complete.

- [ ] **AC-1: Repository exists on GitHub**

  Run:
  ```bash
  gh repo view yakkuro/gh-manage --json name,visibility 2>&1
  ```
  Expected: JSON with `"name": "gh-manage"` and `"visibility": "PRIVATE"`.

- [ ] **AC-2: Local `uv sync` succeeds**

  Run:
  ```bash
  cd ~/repos/gh-manage
  rm -rf .venv
  uv sync
  ```
  Expected: fresh virtualenv is recreated, all dependencies install, no errors.

- [ ] **AC-3: `uv run pytest` exits 0**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv run pytest -v
  echo "exit=$?"
  ```
  Expected: 2 tests collected, 2 passed, `exit=0`.

- [ ] **AC-4: Spec file is committed and pushed**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git log --oneline -- docs/specs/2026-04-10-gh-manage-design.md
  git ls-tree -r origin/main -- docs/specs/2026-04-10-gh-manage-design.md
  ```
  Expected:
  - `git log` shows at least one commit touching the spec
  - `git ls-tree` lists the file on `origin/main`

- [ ] **AC-5: All Phase 0 files are committed and clean working tree**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git status
  ```
  Expected: `nothing to commit, working tree clean`.

- [ ] **AC-6: `gh-manage --version` works**

  Run:
  ```bash
  cd ~/repos/gh-manage
  uv run gh-manage --version
  ```
  Expected: `gh-manage, version 0.0.0`.

- [ ] **AC-7: File inventory matches Phase 0 expectation**

  Run:
  ```bash
  cd ~/repos/gh-manage
  git ls-files | sort
  ```
  Expected output (exact list):
  ```
  .gitignore
  CLAUDE.md
  LICENSE
  README.md
  docs/plans/2026-04-10-phase-0-foundation.md
  docs/specs/2026-04-10-gh-manage-design.md
  pyproject.toml
  src/gh_manage/__init__.py
  src/gh_manage/cli.py
  tests/__init__.py
  tests/test_sanity.py
  uv.lock
  ```
  Total: 12 tracked files.

  If the list contains additional files, investigate — they may have been accidentally committed from `.venv/` or `__pycache__/`. Unstage with `git rm --cached <file>` and add to `.gitignore`.

  If files are missing, re-check earlier tasks.

- [ ] **AC-8: Declare Phase 0 complete**

  Report to the user:
  > "Phase 0 complete. `yakkuro/gh-manage` exists at https://github.com/yakkuro/gh-manage with 12 tracked files, `uv sync` and `uv run pytest` both pass. Ready to plan Phase 1 (reusable-pr-gate-python.yml)."

---

## Phase 0 Exit Checklist (summary)

- [ ] `yakkuro/gh-manage` exists on GitHub as a private repo
- [ ] Local `main` branch is pushed to `origin/main`
- [ ] `uv sync` creates `.venv` and `uv.lock` successfully
- [ ] `uv run pytest -v` collects 2 tests and both pass
- [ ] `uv run gh-manage --version` prints `0.0.0`
- [ ] `git ls-files` lists exactly 12 files
- [ ] `git status` is clean
- [ ] Design spec and Phase 0 plan are committed on `origin/main`
- [ ] Local `CLAUDE.md` exists and is committed
- [ ] No Phase 1+ artifacts (composite actions, reusable workflows, templates, config) exist yet

---

## Out of Scope for Phase 0

Explicitly NOT part of this plan — these belong to later phases:

- `.github/workflows/reusable-pr-gate-python.yml` and any reusable workflow (Phase 1)
- `actions/*/action.yml` composite actions (Phase 1)
- `tests/fixtures/projects/` fixture projects (Phase 1)
- `config/labels.yml`, `config/branch-protection.yml`, `config/repos.yml`, `config/profiles/*.yml` (Phase 4)
- `templates/ci/`, `templates/issue/`, `templates/pr/`, `templates/claude-md/` (Phase 6)
- `src/gh_manage/commands/*.py` (Phase 4 onwards — one command per phase)
- `src/gh_manage/schemas/*.py` (Phase 4)
- `src/gh_manage/github_client.py` (Phase 4)
- `tests/fixtures/drift-scenarios/*.yml` (Phase 8)
- `.github/workflows/drift-scanner.yml` (Phase 8)
- `.github/workflows/smoke-test.yml` (Phase 1)
- `.github/workflows/release.yml` (Phase 9 — possibly earlier for tag automation)
- Branch protection on `yakkuro/gh-manage` itself (Phase 7 — self-application)
- `docs/cli/*.md`, `docs/usage/*.md`, `docs/architecture.md`, `docs/quick-start.md`, `docs/versioning.md`, `docs/distribution-channels.md`, `docs/release-checklist.md`, `docs/maintenance.md`, `docs/secrets-rotation.md`, `docs/consumers.md`, `docs/deprecations.md`, `docs/migrations/*.md` (distributed across phases — these are NOT created as empty stubs now)
- `CHANGELOG-reusable.md`, `CHANGELOG-cli.md` (Phase 9)
- `gh-manage` extension shim at repo root (Phase 4 — gh extension discovery)
- `tags` of any kind, including `v0.0.1` (Phase 1 is the first tag)

---

## Notes for the Implementer

- **Do not create empty placeholder directories** beyond what Task 2 and Task 3 require. Creating `actions/.gitkeep`, `config/.gitkeep`, `templates/.gitkeep` etc. would pollute git history with phantom directories and obscure the "does this file exist because it's needed?" signal in later phases.
- **Do not add linter configuration** (`ruff`, `mypy`) or their config files yet. Phase 1 introduces `run-ruff` and `run-mypy` composite actions that will also drive the CLI-side tooling choices; locking them in now risks rework.
- **Do not attempt to write any reusable workflow, composite action, or CLI subcommand.** Phase 0 is strictly scaffolding.
- **If `gh repo create` fails** because the repo already exists, STOP and ask the user how to proceed. Do not delete or force-overwrite.
- **Commit messages use Conventional Commits.** Task 1 commit: `chore: initial commit ...`, Task 2+3 combined commit: `feat: add Python package skeleton ...`, Task 4 commit: `docs: add local CLAUDE.md ...`. Do not squash these — each commit represents a meaningful, independently revertible unit.
- **Frequency of commits:** Phase 0 produces 3 commits total (base files + spec, python skeleton, CLAUDE.md). The push in Task 5 carries all three.
