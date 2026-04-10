# Phase 5 — Labels Sync (Design Spec)

## Metadata

- **Date**: 2026-04-11
- **Size**: Medium
- **Target**: `yakkuro/gh-manage`
- **Related**: [`docs/specs/2026-04-10-gh-manage-design.md`](./2026-04-10-gh-manage-design.md) (§ Python CLI, § `github_client.py`, § `commands/labels.py`, § Phase 5 Acceptance Criteria), [`docs/specs/2026-04-10-phase-4-cli-skeleton-design.md`](./2026-04-10-phase-4-cli-skeleton-design.md) (establishes `load_config` + `LabelsConfig` + stub command tree)
- **Supersedes**: nothing; first real domain command on the CLI track
- **Ships**: `cli/v0.2.0`

## Sizing Rationale

**Medium**. Phase 5 replaces Phase 4's `labels` stub with the first real domain command and introduces two new modules: `src/gh_manage/github_client.py` (`gh api` subprocess transport + label CRUD helpers) and `src/gh_manage/labels_sync.py` (pure-function diff computation + apply). It also modifies `src/gh_manage/models/labels.py` to add `old_name: str | None` for rename support, adds `config/labels.yml` with real label definitions for gh-manage's self-dogfood, rewrites `src/gh_manage/commands/labels.py` into a click group with 3 subcommands, and adds 3 new test files totaling ~53 tests. Design judgement is required on the github_client shape (resolved: generic + label helpers in the same file), rename strategy (resolved: explicit `old_name` field with a PATCH rename API call), testing approach (resolved: 2-layer mocking), subcommand scope (resolved: sync + diff + show), config file content (resolved: type + meta categories exercising rename/create/noop), repo argument format (resolved: accept both bare name and `owner/repo`), and the exit code convention for dry-run vs diff (resolved: `git diff --quiet` style for diff, plan-success semantics for sync dry-run). Smaller than Phase 4 (which added the whole CLI scaffolding) but comparable in depth because of the number of new abstractions. A single implementation plan can execute it without sub-decomposition.

## Goal

Ship `cli/v0.2.0` — the first **real** command on gh-manage's CLI tag track. Implement `gh manage labels sync <repo> [--apply] [--dry-run] [--prune]`, `gh manage labels diff <repo>`, and `gh manage labels show <repo>` so a user can synchronize GitHub repo labels against `config/labels.yml` as a single source of truth. Self-dogfood by running `gh manage labels sync gh-manage --apply` to apply gh-manage's own Conventional-Commits-aligned labels (3 renames + 5 creates from the default GitHub labels). Establish the 3-layer architecture pattern (`github_client` → `labels_sync` → `commands/labels`) that Phase 7 (protection sync) and Phase 8 (drift scanner) will reuse.

## Acceptance Criteria

Direct mapping from `docs/specs/2026-04-10-gh-manage-design.md` § Phase 5 (lines 860-866), with Phase 5-internal refinements:

- [ ] `gh manage labels sync gh-manage --apply` completes successfully and the resulting labels on `yakkuro/gh-manage` match `config/labels.yml` exactly
- [ ] `gh manage labels diff gh-manage` exits 0 with "No diff." immediately after the sync above
- [ ] `gh manage labels sync gh-manage` (dry-run default) prints a plan without modifying the repo, exit 0
- [ ] `gh manage labels sync yakkuro/gh-manage` (explicit `owner/repo` form per Q6 C) works identically
- [ ] `gh manage labels diff gh-manage` before the sync exits 1 with 3 renames + 5 creates visible
- [ ] `gh manage labels show gh-manage` lists all 14 current labels sorted by name, exit 0
- [ ] `gh manage labels sync <repo> --apply --dry-run` exits 2 with click usage error (mutually exclusive)
- [ ] `gh manage labels sync <nonexistent-repo>` exits 1 with `GhNotFoundError` message mentioning `gh auth status`
- [ ] `gh manage labels sync <repo>` with unauthenticated `gh` exits 1 with `GhAuthError` mentioning `gh auth login`
- [ ] `uv run pytest tests/unit/github_client` passes — ~16 tests covering run_gh_api, CRUD helpers, and the 6-subclass `GhError` hierarchy
- [ ] `uv run pytest tests/unit/labels_sync` passes — ~19 tests covering compute_diff algorithm (rename detection, color normalization, prune logic) and apply_diff execution order
- [ ] `uv run pytest tests/unit/cli/test_labels.py` passes — ~18 tests covering click argument parsing, exit codes, error display
- [ ] `uv run pytest` in total passes — 84 tests (31 from Phase 4 + 53 new)
- [ ] Line coverage ≥ 90% on new modules (`github_client.py`, `labels_sync.py`, `commands/labels.py`)
- [ ] `CHANGELOG-cli.md` has a `[0.2.0] - 2026-04-11` entry
- [ ] `docs/usage/cli.md` updated with a `labels` subcommand section and the self-dogfood walkthrough
- [ ] Annotated tag `cli/v0.2.0` exists on `main` after merge
- [ ] GitHub Release `cli/v0.2.0` published with `--latest=false` (reusable track's `v0.2.1` stays latest)
- [ ] 4-reviewer cross-agent review complete with no open CRITICAL/HIGH findings
- [ ] gh-manage's own `ci.yml` (Python self-dogfood via `reusable-pr-gate-python.yml`) remains green through the entire PR

## Architecture

### Directory layout after Phase 5

```
gh-manage/
├── config/
│   └── labels.yml                            # NEW — gh-manage's own label definitions
├── src/gh_manage/
│   ├── github_client.py                      # NEW — generic run_gh + run_gh_api + label CRUD
│   ├── labels_sync.py                        # NEW — pure functions: compute_diff + apply_diff
│   ├── models/
│   │   └── labels.py                         # MODIFY — add old_name: str | None = None
│   └── commands/
│       └── labels.py                         # REWRITE — stub → click group with 3 subcommands
├── tests/
│   ├── unit/
│   │   ├── cli/
│   │   │   └── test_labels.py                # NEW — CliRunner + github_client monkey-patched
│   │   ├── github_client/
│   │   │   ├── __init__.py                   # NEW
│   │   │   └── test_github_client.py         # NEW — subprocess.run mocked
│   │   └── labels_sync/
│   │       ├── __init__.py                   # NEW
│   │       └── test_labels_sync.py           # NEW — pure-function tests
│   └── fixtures/config/
│       └── labels-valid-with-rename.yml      # NEW — fixture with old_name field
├── CHANGELOG-cli.md                          # MODIFY — add [0.2.0] entry
└── docs/usage/cli.md                         # MODIFY — add labels subcommand section
```

### 3-layer responsibility (Tier 2 architecture)

```
Layer 3: CLI (commands/labels.py)
  └─ click group "labels" with 3 subcommands: sync / diff / show
     Thin click adapter (~100 lines). No business logic.
     - Parses args (repo, --apply, --prune, --dry-run, --config)
     - Calls labels_sync functions
     - Formats output (plain text diff per Q7 A)
     - Maps exit codes per Q8 A convention
     - Catches GhError/ConfigError → click.ClickException

Layer 2: Domain logic (labels_sync.py)
  └─ Pure functions, no click, no subprocess:
     - compute_diff(current: list[Label], desired: LabelsConfig, *, prune: bool) -> LabelsDiff
     - apply_diff(diff: LabelsDiff, repo: str, *, progress: Callable[[str], None]) -> None
     Fully unit-testable without mocks.
     LabelsDiff is a frozen dataclass (renames, creates, updates, deletes).
     apply_diff calls github_client.{create,update,delete}_label directly.
     Tests monkey-patch those 3 functions.

Layer 1: gh API transport (github_client.py)
  └─ Generic: run_gh(args) + run_gh_api(endpoint, method, fields, paginate)
     Label helpers: list_labels / create_label / update_label / delete_label
     Label dataclass: (name, color, description) — normalized
     All subprocess.run calls for `gh` go through this module.
     Error hierarchy: GhError + 6 subclasses with actionable messages.
     Unit-tested with subprocess.run mocked via pytest-mock.
```

### Dependency direction (strict, no cycles)

```
commands/labels.py
       │
       ▼
labels_sync.py ──────────┐
       │                 │
       ▼                 ▼
github_client.py    models/labels.py
       │                 │
       ▼                 ▼
  [subprocess]       [pydantic v2]
```

- `commands/labels.py` imports from `labels_sync`, `github_client`, `config`, `models.labels`
- `labels_sync.py` imports from `github_client` (for the `Label` dataclass and CRUD calls) and `models.labels` (for `LabelsConfig`, `LabelSpec`)
- `github_client.py` imports only stdlib + `pydantic` (for no-op; label is a dataclass)
- **No upward references. No circular imports.**

### Key design decisions (from brainstorming Q1-Q8)

- **Q1 B**: Subcommand scope = `sync` + `diff` + `show`. No `--all` batch mode in Phase 5.
- **Q2 B**: `github_client.py` holds both the generic `run_gh` / `run_gh_api` layer AND the domain-specific label CRUD helpers (`list_labels`, `create_label`, `update_label`, `delete_label`). Phase 7 will add `list_protection` / `update_protection` to the same file.
- **Q3 A**: Rename via explicit `old_name: str | None` field on `LabelSpec`. `update_label(repo, current_name, new_label)` handles both rename and non-rename PATCH. Preserves existing Issue label assignments.
- **Q4 B**: 2-layer mock testing. `test_github_client.py` mocks `subprocess.run`. `test_labels_sync.py` uses pure functions (no mocks). `test_labels.py` uses `CliRunner` + monkey-patched `github_client` module functions.
- **Q5 B**: `config/labels.yml` has 2 categories (type + meta) totaling 14 labels. Type category includes 3 renames (`bug` → `fix`, `documentation` → `docs`, `enhancement` → `feat`) and 5 pure creates (`chore`, `refactor`, `test`, `ci`, `perf`). Meta category has 6 labels that match GitHub's current defaults exactly (noop).
- **Q6 C**: `<repo>` argument accepts both bare name (`gh-manage` → `yakkuro/gh-manage`) and qualified (`yakkuro/gh-manage`, `other-org/other-repo`). Logic: `if "/" in repo: use as-is, else: prepend "yakkuro/"`.
- **Q7 A**: Plain text diff output only. `+` create, `-` delete, `~` update/rename, `=` unchanged. Click's `style()` for tty color. Internal diff structure is already typed (`LabelsDiff`), so adding JSON output in Phase 5.1 is a single `.render()` method.
- **Q8 A**: `--apply` + `--prune` double-gated with no interactive prompts. Default dry-run. Fail-fast on first error. Exit code conventions: sync=0/1/2 (success/runtime/usage), diff=0/1 (no diff / diff present, git-diff-quiet style), show=0.

### Non-goals for cli/v0.2.0

- **Batch operations** — `labels sync --all` is not implemented. `repos.yml` schema lands in Phase 6.
- **JSON output** — `--format json` deferred to Phase 5.1 or later. Internal `LabelsDiff` structure is already typed, so adding JSON is cheap.
- **Interactive confirmation prompts** — `--apply` is the confirmation; no additional prompts.
- **Rollback on partial failure** — operations are idempotent; re-running after fixing the cause picks up remaining work.
- **Rename heuristics** — only explicit `old_name` triggers rename. No color/description-based guessing.
- **Label colors uniqueness enforcement** — multiple labels can share a color (schema-level only checks 6-char hex).
- **Rate-limit retry** — GhRateLimitError is raised immediately. No sleep/retry loop. (Main spec notes scheduled runs may add this in Phase 8.)
- **Label protection** — no mechanism to mark a label as "never delete me". Users rely on `--prune` being opt-in.
- **Multi-account `gh auth`** — uses whatever the current `gh` CLI auth context is. No `--user` flag.
- **Custom owner default via env var** — `yakkuro` is hardcoded. If needed later, `GH_MANAGE_DEFAULT_OWNER` is trivial to add.

## Components

### `config/labels.yml` (new)

gh-manage's own label definitions. Self-dogfood source of truth.

```yaml
version: 1
categories:
  type:
    description: "Conventional Commits type labels"
    labels:
      - { name: "fix",      old_name: "bug",           color: "d73a4a", description: "Bug fix (fix:)" }
      - { name: "feat",     old_name: "enhancement",   color: "a2eeef", description: "New feature (feat:)" }
      - { name: "docs",     old_name: "documentation", color: "0075ca", description: "Documentation changes (docs:)" }
      - { name: "chore",    color: "e1e7eb", description: "Maintenance / housekeeping (chore:)" }
      - { name: "refactor", color: "ffd866", description: "Refactor without behavior change (refactor:)" }
      - { name: "test",     color: "c5def5", description: "Test additions / changes (test:)" }
      - { name: "ci",       color: "b4a5ff", description: "CI/CD changes (ci:)" }
      - { name: "perf",     color: "5319e7", description: "Performance improvements (perf:)" }
  meta:
    description: "Meta / status labels"
    labels:
      - { name: "duplicate",        color: "cfd3d7", description: "This issue or PR already exists" }
      - { name: "good first issue", color: "7057ff", description: "Good for newcomers" }
      - { name: "help wanted",      color: "008672", description: "Extra attention is needed" }
      - { name: "invalid",          color: "e4e669", description: "Not actionable" }
      - { name: "question",         color: "d876e3", description: "Further information is requested" }
      - { name: "wontfix",          color: "ffffff", description: "This will not be worked on" }
```

**Colors preserved from GitHub defaults** for the 3 renames (`d73a4a`, `a2eeef`, `0075ca`) and the 6 meta labels to minimize visual churn. `chore` gets `e1e7eb` (light gray) which differs slightly from `duplicate`'s `cfd3d7` so the two aren't visually identical. Other type colors are pleasant pastels consistent with GitHub's default palette.

**Self-dogfood diff (predicted before the first sync)**:
- 3 renames: `bug`→`fix`, `documentation`→`docs`, `enhancement`→`feat` (colors unchanged, descriptions updated)
- 5 creates: `chore`, `refactor`, `test`, `ci`, `perf`
- 6 updates for meta labels: **none expected** (colors and descriptions match GitHub defaults exactly)
- 0 deletes: `--prune` not used in self-dogfood

### `src/gh_manage/github_client.py` (new)

Full module scaffold. Implementation details finalized in writing-plans phase.

```python
"""gh CLI subprocess transport + label CRUD helpers.

All `gh` subprocess invocations for gh-manage go through this module.
Error handling maps `gh api` failures to a typed GhError hierarchy with
actionable messages.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


# Error hierarchy — 6 subclasses of GhError for specific failure modes
class GhError(Exception):
    """Base class for gh CLI subprocess failures. Never raised directly."""


class GhNotInstalledError(GhError):
    """`gh` CLI missing on PATH — FileNotFoundError on subprocess.run."""


class GhAuthError(GhError):
    """Authentication failure — 401 or `gh auth` not logged in."""


class GhNotFoundError(GhError):
    """404 — repository or resource missing."""


class GhPermissionError(GhError):
    """403 — token lacks required scope or repository is restricted."""


class GhRateLimitError(GhError):
    """429 — GitHub API rate limit exhausted."""


class GhAPIError(GhError):
    """Other non-2xx response (catch-all)."""


@dataclass(frozen=True)
class Label:
    """A GitHub label in normalized form.

    - color is always lowercase 6-char hex (GitHub accepts either case but
      returns lowercase; we normalize for consistent comparison).
    - description is always a string, never None — GitHub returns null for
      unset descriptions but we normalize to "" so comparisons don't break.
    """

    name: str
    color: str
    description: str


def run_gh(args: list[str]) -> str:
    """Run `gh <args>` and return stdout.

    Raises GhNotInstalledError if gh is not on PATH.
    Raises GhAPIError on non-zero exit (or a more specific subclass if the
    stderr pattern is recognized).
    """
    ...


def run_gh_api(
    endpoint: str,
    method: str = "GET",
    fields: dict[str, str] | None = None,
    paginate: bool = False,
) -> Any:
    """Run `gh api <endpoint>` and return parsed JSON.

    Builds argv as:
      gh api <endpoint> [-X <method>] [-f key=value ...] [--paginate]

    Classifies non-zero exits into GhError subclasses by pattern-matching
    stderr:
      - "HTTP 404" / "Not Found" → GhNotFoundError
      - "Bad credentials" / "not logged in" / "HTTP 401" → GhAuthError
      - "HTTP 403" / "Forbidden" → GhPermissionError
      - "rate limit" → GhRateLimitError
      - else → GhAPIError (with truncated stderr in message)
    FileNotFoundError (gh not on PATH) → GhNotInstalledError.
    """
    ...


def list_labels(repo: str) -> list[Label]:
    """GET /repos/{repo}/labels, auto-paginated.

    `repo` must be in `owner/repo` form (CLI layer normalizes bare names).
    Returns a list of Label instances with color lowercased and description
    never None.
    """
    ...


def create_label(repo: str, label: Label) -> None:
    """POST /repos/{repo}/labels with {name, color, description}."""
    ...


def update_label(repo: str, current_name: str, new_label: Label) -> None:
    """PATCH /repos/{repo}/labels/{current_name}.

    If new_label.name != current_name → body includes `new_name` field
    (rename). Otherwise → body has only `color` and `description`.
    """
    ...


def delete_label(repo: str, name: str) -> None:
    """DELETE /repos/{repo}/labels/{name}."""
    ...
```

### `src/gh_manage/labels_sync.py` (new)

Pure-function diff computation + apply. No click, no subprocess (except via `github_client`).

```python
"""Pure-function label diff computation and application.

All functions here are click/subprocess independent. Tests can exercise
compute_diff with in-memory data and apply_diff with monkey-patched
github_client module functions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from gh_manage import github_client
from gh_manage.github_client import Label
from gh_manage.models.labels import LabelsConfig


@dataclass(frozen=True)
class LabelRename:
    old_name: str
    new_label: Label


@dataclass(frozen=True)
class LabelCreate:
    label: Label


@dataclass(frozen=True)
class LabelUpdate:
    label: Label  # same name, updated color/description


@dataclass(frozen=True)
class LabelDelete:
    name: str


@dataclass(frozen=True)
class LabelsDiff:
    renames: tuple[LabelRename, ...]
    creates: tuple[LabelCreate, ...]
    updates: tuple[LabelUpdate, ...]
    deletes: tuple[LabelDelete, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.renames or self.creates or self.updates or self.deletes)

    @property
    def total_changes(self) -> int:
        return (
            len(self.renames) + len(self.creates)
            + len(self.updates) + len(self.deletes)
        )


def compute_diff(
    current: list[Label],
    desired: LabelsConfig,
    *,
    prune: bool = False,
) -> LabelsDiff:
    """Compute the diff between current repo labels and desired config.

    Algorithm:
      1. Build a name→Label map of current labels.
      2. For each LabelSpec in (flattened) desired.categories:
         a. If spec.name matches a current name:
            - Compare color (case-insensitive) and description (None==empty).
            - If differs → LabelUpdate, else skip.
            - Mark current entry as "consumed".
         b. Elif spec.old_name is set and matches a current name:
            - Emit LabelRename(old_name=spec.old_name, new_label=Label(...)).
            - Mark current entry as "consumed".
         c. Else → LabelCreate.
      3. For each unconsumed current label:
         - If prune=True → LabelDelete.
         - Else → ignore.

    Returns LabelsDiff with operations grouped by type. Empty tuples for
    any empty bucket.

    Normalization:
      - Color: lowercase for both sides before comparison.
      - Description: None or "" treated as equivalent (GitHub returns "" for
        null descriptions after github_client normalization).
    """
    ...


def apply_diff(
    diff: LabelsDiff,
    repo: str,
    *,
    progress: Callable[[str], None] = lambda _: None,
) -> None:
    """Apply diff operations in fail-fast order.

    Execution order:
      1. Renames — first so subsequent creates don't collide with old names.
      2. Creates — new labels.
      3. Updates — color/description changes on same-name labels.
      4. Deletes — last so a failed delete doesn't orphan dependent state.

    Each operation is dispatched to github_client.{create,update,delete}_label.
    On first GhError, the exception propagates to the caller; partial progress
    is NOT rolled back (operations are idempotent — re-run picks up where it
    left off).

    `progress` is called with a one-line human-readable description before
    each operation. CLI layer uses click.echo; tests pass a no-op lambda.
    """
    for rename in diff.renames:
        progress(f"~ {rename.old_name} → {rename.new_label.name}")
        github_client.update_label(repo, rename.old_name, rename.new_label)
    for create in diff.creates:
        progress(f"+ {create.label.name}")
        github_client.create_label(repo, create.label)
    for update in diff.updates:
        progress(f"≈ {update.label.name}")
        github_client.update_label(repo, update.label.name, update.label)
    for delete in diff.deletes:
        progress(f"- {delete.name}")
        github_client.delete_label(repo, delete.name)
```

### `src/gh_manage/models/labels.py` (modify)

Phase 4's `LabelSpec` gains one optional field:

```python
class LabelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    color: str = Field(pattern=r"^[0-9a-fA-F]{6}$")
    description: str | None = None
    old_name: str | None = None    # NEW — Q3 A, for rename via PATCH new_name
```

Backward compatible: `old_name` defaults to `None`, existing Phase 4 fixtures validate unchanged.

### `src/gh_manage/commands/labels.py` (rewrite)

Phase 4's stub is replaced by a click group with 3 subcommands.

```python
"""gh manage labels — sync, diff, show GitHub repo labels."""

from __future__ import annotations

import functools
import sys
from pathlib import Path
from typing import Callable

import click

from gh_manage import github_client, labels_sync
from gh_manage.config import ConfigError, load_config
from gh_manage.github_client import GhError, Label
from gh_manage.labels_sync import LabelsDiff
from gh_manage.models.labels import LabelSpec, LabelsConfig


DEFAULT_OWNER = "yakkuro"
DEFAULT_CONFIG_PATH = Path("config/labels.yml")


def _parse_repo(repo: str) -> str:
    """Normalize bare name to owner/repo (Q6 C)."""
    if "/" in repo:
        return repo
    return f"{DEFAULT_OWNER}/{repo}"


def _format_diff(diff: LabelsDiff) -> str:
    """Render LabelsDiff as plain text per Q7 A."""
    ...


def _handle_errors(func: Callable) -> Callable:
    """Decorator: catch GhError/ConfigError and re-raise as click.ClickException."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (GhError, ConfigError) as e:
            raise click.ClickException(str(e)) from e
    return wrapper


@click.group(help="Synchronize GitHub repo labels against config/labels.yml.")
def labels() -> None:
    """Entry group for labels subcommands."""


@labels.command(
    help="Apply config/labels.yml to a repo. Default is dry-run; pass --apply to execute."
)
@click.argument("repo")
@click.option("--apply", "apply_flag", is_flag=True,
              help="Actually execute changes (default is dry-run).")
@click.option("--prune", is_flag=True,
              help="Delete labels not in config (requires --apply).")
@click.option("--dry-run", is_flag=True,
              help="Explicit dry-run (redundant with default; conflicts with --apply).")
@click.option("--config", "config_path",
              type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_CONFIG_PATH,
              help="Path to labels.yml.")
@_handle_errors
def sync(repo: str, apply_flag: bool, prune: bool, dry_run: bool, config_path: Path) -> None:
    if apply_flag and dry_run:
        raise click.UsageError("--apply and --dry-run are mutually exclusive.")

    qualified = _parse_repo(repo)
    config = load_config(config_path, LabelsConfig)
    current = github_client.list_labels(qualified)

    diff = labels_sync.compute_diff(current, config, prune=prune)

    if diff.is_empty:
        click.echo("No changes.")
        return

    click.echo(_format_diff(diff))

    if not apply_flag:
        click.echo(f"\nDry-run: {diff.total_changes} changes. Re-run with --apply to execute.")
        return

    labels_sync.apply_diff(diff, qualified, progress=click.echo)
    click.echo(f"\nApplied {diff.total_changes} changes.")


@labels.command("diff",
                help="Show diff between config/labels.yml and a repo. "
                     "Exit 0 if no diff, 1 if diff present (git diff --quiet style).")
@click.argument("repo")
@click.option("--prune", is_flag=True,
              help="Include would-be deletes in diff.")
@click.option("--config", "config_path",
              type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_CONFIG_PATH)
@_handle_errors
def diff_cmd(repo: str, prune: bool, config_path: Path) -> None:
    qualified = _parse_repo(repo)
    config = load_config(config_path, LabelsConfig)
    current = github_client.list_labels(qualified)

    diff = labels_sync.compute_diff(current, config, prune=prune)

    if diff.is_empty:
        click.echo("No diff.")
        sys.exit(0)

    click.echo(_format_diff(diff))
    sys.exit(1)


@labels.command("show",
                help="List current labels on a repo (read-only).")
@click.argument("repo")
@_handle_errors
def show(repo: str) -> None:
    qualified = _parse_repo(repo)
    current = github_client.list_labels(qualified)
    for label in sorted(current, key=lambda lb: lb.name):
        click.echo(f"{label.name}  color={label.color}  desc={label.description!r}")
```

**cli.py integration**: `src/gh_manage/cli.py` already imports `from gh_manage.commands import labels as labels_cmd` and calls `main.add_command(labels_cmd.labels)`. When Phase 4's `labels()` stub becomes the new click group, this registration continues to work because `labels_cmd.labels` now refers to the group (same attribute name, different kind of object). **No `cli.py` change needed.**

### `CHANGELOG-cli.md` (modify)

Add a `[0.2.0] - 2026-04-11` entry above the existing `[0.1.0]`:

```markdown
## [0.2.0] - 2026-04-11

First real domain command: `gh manage labels sync/diff/show`. Phase 5 milestone. Self-dogfooded by applying gh-manage's own Conventional-Commits-aligned labels via `gh manage labels sync gh-manage --apply`.

### Added

- **`src/gh_manage/github_client.py`** — subprocess transport for `gh` and `gh api`, with a 6-subclass `GhError` hierarchy (`GhNotInstalledError`, `GhAuthError`, `GhNotFoundError`, `GhPermissionError`, `GhRateLimitError`, `GhAPIError`). All error messages include actionable next steps. Label CRUD helpers: `list_labels`, `create_label`, `update_label` (handles rename via `new_name` body field), `delete_label`. Colors normalized to lowercase; null descriptions normalized to "".
- **`src/gh_manage/labels_sync.py`** — pure-function diff computation (`compute_diff`) and application (`apply_diff`). Typed `LabelsDiff` dataclass with `LabelRename`, `LabelCreate`, `LabelUpdate`, `LabelDelete` buckets. Rename detection via explicit `old_name` field on `LabelSpec`. Fail-fast execution order: renames → creates → updates → deletes.
- **`src/gh_manage/commands/labels.py`** — click group with 3 subcommands: `sync`, `diff`, `show`. Default dry-run; `--apply` to execute; `--prune` to include deletes. Plain-text diff output. `<repo>` accepts both bare name and `owner/repo`. Unified error handling decorator converts `GhError`/`ConfigError` to `click.ClickException`.
- **`config/labels.yml`** — gh-manage's own label definitions. Type category (Conventional Commits: `fix`, `feat`, `docs`, `chore`, `refactor`, `test`, `ci`, `perf`) with rename mappings from GitHub defaults. Meta category with 6 preserved labels.
- **`tests/unit/github_client/test_github_client.py`** — ~16 tests with `subprocess.run` mocked, covering happy paths, color/description normalization, and 6 error classification branches.
- **`tests/unit/labels_sync/test_labels_sync.py`** — ~19 pure-function tests covering compute_diff (rename detection, color normalization, prune logic) and apply_diff (execution order, progress callback, fail-fast behavior).
- **`tests/unit/cli/test_labels.py`** — ~18 CliRunner tests covering all 3 subcommands, repo argument normalization, exit codes, and error display.
- **`tests/fixtures/config/labels-valid-with-rename.yml`** — fixture with `old_name` field for backward-compatible LabelsConfig parsing test.

### Changed

- **`src/gh_manage/models/labels.py`** — `LabelSpec` gains `old_name: str | None = None` field (Q3 A). Backward-compatible: existing Phase 4 fixtures validate unchanged.
- **`src/gh_manage/__init__.py`** — `__version__` bumped from `"0.1.0"` to `"0.2.0"`.
- **`pyproject.toml`** — `version` bumped from `"0.1.0"` to `"0.2.0"`.
- **`tests/test_sanity.py`** — expected `__version__` bumped to `"0.2.0"`.
- **`docs/usage/cli.md`** — new "labels" subcommand section, self-dogfood walkthrough, updated roadmap (marking Phase 5 as shipped).

### Known limitations

- **No `--format json`** — diff output is plain text only. Phase 5.1 may add JSON via a `.render()` method on `LabelsDiff`.
- **No batch mode (`--all`)** — single-repo only. Multi-repo requires `repos.yml` schema which lands in Phase 6.
- **No rate-limit retry** — `GhRateLimitError` is raised immediately. Scheduled runs may add retry in Phase 8.
- **No rollback on partial failure** — operations are idempotent; re-running picks up remaining work.
- **Rename is not heuristic** — only explicit `old_name` triggers rename. Renaming without `old_name` becomes create+delete.
- **`yakkuro` is the hardcoded default owner** — can be overridden by passing `<owner>/<repo>`. No env var override yet.
```

### `docs/usage/cli.md` (modify)

Add a new section `## labels` after the existing roadmap table, containing:

- `gh manage labels sync <repo> [--apply] [--prune] [--config PATH]` — description + usage
- `gh manage labels diff <repo> [--prune]` — description + usage + exit code note
- `gh manage labels show <repo>` — description + usage
- Self-dogfood walkthrough showing the 3 commands against `gh-manage`
- Error message examples for `GhNotFoundError`, `GhAuthError`

Update the roadmap table to mark `labels` as shipped in `cli/v0.2.0`.

## Data Flow

### Flow A: `gh manage labels sync gh-manage` (dry-run default)

```
1. `./gh-manage labels sync gh-manage`
2. Shell wrapper → uv run python -m gh_manage labels sync gh-manage
3. __main__.py → cli.main(prog_name="gh-manage") → routes to commands.labels.sync
4. _parse_repo("gh-manage") → "yakkuro/gh-manage" (Q6 C)
5. load_config(Path("config/labels.yml"), LabelsConfig)
   - Phase 4's generic loader, raises ConfigFileNotFoundError if missing
6. github_client.list_labels("yakkuro/gh-manage")
   a. Runs: gh api repos/yakkuro/gh-manage/labels --paginate
   b. On 0 exit: json.loads(stdout) → list[dict]
   c. Normalizes: Label(name, color.lower(), description or "")
   d. Returns list[Label]
7. labels_sync.compute_diff(current, config, prune=False)
   a. Flatten desired.categories → 14 LabelSpec
   b. For each spec:
      - "fix" (old_name: "bug"): name not in current, old_name "bug" IS in current
        → LabelRename(old_name="bug", new_label=Label(name="fix", ...))
      - "feat" (old_name: "enhancement"): same → LabelRename
      - "docs" (old_name: "documentation"): same → LabelRename
      - "chore", "refactor", "test", "ci", "perf": not in current → LabelCreate x5
      - "duplicate": name match, same color/desc → noop
      - "good first issue", "help wanted", "invalid", "question", "wontfix": same → noop
   c. Returns LabelsDiff(renames=3, creates=5, updates=0, deletes=0)
8. is_empty=False → print diff
9. apply_flag=False → print "Dry-run: 8 changes. Re-run with --apply to execute."
10. Exit 0
```

### Flow B: `gh manage labels sync gh-manage --apply`

```
1-8. Same as Flow A
9. apply_flag=True → labels_sync.apply_diff(diff, "yakkuro/gh-manage", progress=click.echo)
   a. 3 renames:
      - click.echo("~ bug → fix")
      - github_client.update_label("yakkuro/gh-manage", "bug", Label(name="fix", ...))
        → PATCH /repos/yakkuro/gh-manage/labels/bug with body {new_name:"fix", color:"d73a4a", description:"..."}
      - Same for documentation → docs, enhancement → feat
   b. 5 creates:
      - click.echo("+ chore")
      - github_client.create_label("yakkuro/gh-manage", Label(name="chore", ...))
        → POST /repos/yakkuro/gh-manage/labels
      - Same for refactor, test, ci, perf
10. click.echo("Applied 8 changes.")
11. Exit 0
```

### Flow C: `gh manage labels diff gh-manage` after sync

```
1-7. Same as Flow A (fetches current, computes diff with prune=False)
8. All 14 labels match exactly → is_empty=True
9. click.echo("No diff.")
10. sys.exit(0)
```

### Flow D: `gh manage labels diff gh-manage` before sync

```
1-7. Same as Flow A
8. is_empty=False → click.echo(formatted diff showing 3 renames + 5 creates)
9. sys.exit(1)   ← git diff --quiet style
```

### Flow E: `gh manage labels show gh-manage`

```
1. Route to commands.labels.show
2. _parse_repo → "yakkuro/gh-manage"
3. github_client.list_labels → list[Label]  (no config, no diff)
4. Sort by name, print each: "name  color=XXXXXX  desc='...'"
5. Exit 0
```

### Flow F: Error — `labels sync yakkuro/does-not-exist`

```
1-5. Same as Flow A
6. github_client.list_labels:
   a. gh api returns exit 1, stderr "HTTP 404: Not Found"
   b. run_gh_api pattern-matches "http 404" → raises GhNotFoundError(
        "GitHub API returned 404 for repos/yakkuro/does-not-exist/labels. "
        "Check the resource name and your auth status with `gh auth status`.")
7. _handle_errors decorator catches GhError → click.ClickException
8. click prints "Error: GitHub API returned 404 ..." to stderr
9. Exit 1
```

### Flow G: Error — `gh` not authenticated

```
1-5. Same as Flow A
6. github_client.list_labels:
   a. gh api returns exit 1, stderr "You are not logged in to any GitHub hosts. Run `gh auth login`"
   b. run_gh_api pattern-matches "not logged in" → raises GhAuthError(
        "The `gh` CLI is not authenticated or the token is invalid. "
        "Run `gh auth login` (or `gh auth refresh`) and try again.")
7. _handle_errors → click.ClickException
8. Exit 1 with stderr "Error: The `gh` CLI is not authenticated ..."
```

### Flow H: `gh` CLI missing from PATH

```
1-5. Same as Flow A
6. github_client.list_labels:
   a. subprocess.run raises FileNotFoundError
   b. run_gh_api catches → raises GhNotInstalledError(
        "The `gh` CLI is required but was not found on PATH. "
        "Install it from https://cli.github.com/ and run `gh auth login`.")
7. _handle_errors → click.ClickException
8. Exit 1
```

## Error Handling

### Guiding principles (from `CLAUDE.md`)

- **No silent failures** — every failure mode has a typed exception with actionable message
- **Actionable messages** — describe what happened + what to do next
- **`raise ... from e`** — preserve `__cause__` for debugging

### `GhError` hierarchy (in `github_client.py`)

```
GhError                             # base, never raised directly
├── GhNotInstalledError              # `gh` CLI missing on PATH
├── GhAuthError                      # 401 or `gh auth status` failing
├── GhNotFoundError                  # 404
├── GhPermissionError                # 403
├── GhRateLimitError                 # 429 / rate-limit exhausted
└── GhAPIError                       # other non-2xx (catch-all)
```

### Exception messages (exact wording, locked in)

- **GhNotInstalledError**: `"The ` + `` `gh` `` + ` CLI is required but was not found on PATH. Install it from https://cli.github.com/ and run ` + `` `gh auth login` `` + `."`
- **GhAuthError**: `"The ` + `` `gh` `` + ` CLI is not authenticated or the token is invalid. Run ` + `` `gh auth login` `` + ` (or ` + `` `gh auth refresh` `` + `) and try again."`
- **GhNotFoundError**: `f"GitHub API returned 404 for {endpoint}. Check the resource name and your auth status with ` + `` `gh auth status` `` + `."`
- **GhPermissionError**: `f"Permission denied on {endpoint}. Your ` + `` `gh` `` + ` token may lack the required scope. Run ` + `` `gh auth refresh -s repo` `` + ` to add ` + `` `repo` `` + ` scope."`
- **GhRateLimitError**: `f"GitHub API rate limit exceeded while calling {endpoint}. Wait for the reset window (see ` + `` `gh api rate_limit` `` + `) and retry."`
- **GhAPIError**: `f"GitHub API call failed: {endpoint} (exit {returncode}). stderr: {stderr.strip()[:500]}. Re-run with ` + `` GH_DEBUG=api `` + ` to see the full request/response."`

Tests assert substring matches (e.g., `match="Run ` + `gh auth login`"`), not full-string equality, to allow minor wording refinements without breaking tests.

### Error classification logic in `run_gh_api`

```python
def run_gh_api(endpoint, method="GET", fields=None, paginate=False):
    try:
        result = subprocess.run([...], capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise GhNotInstalledError("The `gh` CLI is required ...") from e

    if result.returncode == 0:
        return json.loads(result.stdout)

    stderr_lower = result.stderr.lower()
    if "rate limit" in stderr_lower:
        raise GhRateLimitError(f"GitHub API rate limit exceeded ...")
    if "http 404" in stderr_lower or "not found" in stderr_lower:
        raise GhNotFoundError(f"GitHub API returned 404 ...")
    if any(marker in stderr_lower for marker in ("bad credentials", "not logged in", "http 401")):
        raise GhAuthError("The `gh` CLI is not authenticated ...")
    if "http 403" in stderr_lower or "forbidden" in stderr_lower:
        raise GhPermissionError(f"Permission denied ...")
    raise GhAPIError(f"GitHub API call failed: {endpoint} (exit {result.returncode}). ...")
```

Classification order matters: rate limit first (it can contain "403" in some cases), then specific codes, then catch-all.

### CLI layer: `_handle_errors` decorator

```python
def _handle_errors(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (GhError, ConfigError) as e:
            raise click.ClickException(str(e)) from e
    return wrapper
```

Applied to all 3 subcommands. `click.ClickException` prints `Error: <msg>` to stderr and exits 1.

### Exit code convention

| Command | Success | Runtime error | Usage error |
|---|---|---|---|
| `labels sync` (dry-run) | 0 (plan generated) | 1 (`GhError`/`ConfigError`) | 2 (bad flags) |
| `labels sync --apply` | 0 (applied) | 1 (partial or full failure, fail-fast) | 2 |
| `labels sync --apply --dry-run` | n/a | n/a | 2 (mutually exclusive) |
| `labels diff` | 0 (no diff) OR 1 (diff present) | 1 (also 1 — ambiguous, acceptable for Phase 5) | 2 |
| `labels show` | 0 | 1 (`GhError`) | 2 |

**Ambiguity note on `labels diff`**: both "diff present" and "runtime error" use exit 1. CI scripts that need to distinguish can check stderr content (diff present → empty stderr, error → "Error: ..." on stderr). A `--exit-zero` flag may be added in Phase 5.1 if needed.

### Partial-failure semantics (fail-fast per Q8 A)

- `apply_diff` iterates operations and calls `github_client.{create,update,delete}_label` directly
- On first `GhError`, the exception propagates up through `apply_diff` to the click command
- No rollback — prior successful operations stay committed on the GitHub side
- `_handle_errors` converts to `click.ClickException`, click exits 1 with stderr message
- User fixes the cause (auth, permission, etc.) and re-runs — operations are idempotent
- Progress callback has already printed all successful operations, so the user can see exactly where execution stopped

## Testing Strategy

### Test organization (3 new test files)

```
tests/
├── unit/
│   ├── cli/
│   │   └── test_labels.py                   # NEW — CliRunner + github_client monkey-patched
│   ├── github_client/
│   │   ├── __init__.py                      # NEW
│   │   └── test_github_client.py            # NEW — subprocess.run mocked
│   └── labels_sync/
│       ├── __init__.py                      # NEW
│       └── test_labels_sync.py              # NEW — pure-function tests
└── fixtures/config/
    └── labels-valid-with-rename.yml         # NEW
```

### Layer 1 — `test_github_client.py` (~16 tests)

`subprocess.run` is mocked via `pytest-mock` in every test. Tests exercise the exact code path the reusable gate will run.

```python
# Happy path (6 tests)
def test_list_labels_parses_json_response(mocker)
def test_list_labels_auto_paginates(mocker)
def test_create_label_sends_correct_body(mocker)
def test_update_label_with_rename_uses_new_name_field(mocker)
def test_update_label_without_rename_omits_new_name(mocker)
def test_delete_label_calls_correct_endpoint(mocker)

# Normalization (2 tests)
def test_list_labels_normalizes_color_to_lowercase(mocker)
def test_list_labels_converts_null_description_to_empty_string(mocker)

# Error classification (6 parametrized cases)
@pytest.mark.parametrize("stderr,expected_exc", [
    ("HTTP 404: Not Found\n", GhNotFoundError),
    ("You are not logged in to any GitHub hosts.\n", GhAuthError),
    ("Bad credentials\n", GhAuthError),
    ("HTTP 403: Forbidden\n", GhPermissionError),
    ("API rate limit exceeded\n", GhRateLimitError),
    ("Some unknown error\n", GhAPIError),
])
def test_run_gh_api_error_classification(mocker, stderr, expected_exc)

# Not installed (1 test)
def test_run_gh_api_filenotfound_raises_gh_not_installed(mocker)

# Actionable messages (1 test)
def test_gh_error_messages_contain_actionable_hints(mocker)
```

### Layer 2 — `test_labels_sync.py` (~19 tests)

Pure function tests. `Label` and `LabelsConfig` built in-memory. No mocks in `compute_diff` tests; `apply_diff` tests monkey-patch `github_client.{create,update,delete}_label`.

```python
# compute_diff happy paths (6 tests)
def test_empty_repo_with_all_new_labels_produces_creates_only()
def test_matching_labels_produce_empty_diff()
def test_color_mismatch_produces_update()
def test_description_mismatch_produces_update()
def test_color_case_insensitive_match()        # d73a4a == D73A4A
def test_none_description_equals_empty_string()

# compute_diff rename logic (3 tests, Q3 A)
def test_old_name_match_produces_rename_not_create()
def test_rename_with_color_change_still_single_rename()
def test_name_match_preferred_over_old_name_match()

# compute_diff prune logic (3 tests)
def test_prune_false_ignores_extra_labels()
def test_prune_true_emits_deletes_for_extras()
def test_prune_does_not_delete_label_matched_via_old_name()

# compute_diff edge cases (2 tests)
def test_empty_desired_config_no_changes_without_prune()
def test_empty_desired_config_with_prune_deletes_everything()

# apply_diff execution order (3 tests)
def test_apply_diff_calls_renames_before_creates(mocker)
def test_apply_diff_calls_deletes_last(mocker)
def test_apply_diff_fails_fast_on_first_error(mocker)

# apply_diff progress (1 test)
def test_apply_diff_progress_callback_invoked_in_order(mocker)

# LabelsDiff properties (1 test)
def test_labels_diff_is_empty_and_total_changes()
```

### Layer 3 — `test_labels.py` (~18 tests)

`CliRunner` for click subcommands. `github_client.list_labels` / `labels_sync.compute_diff` / `labels_sync.apply_diff` monkey-patched where needed.

```python
# sync command (10 tests)
def test_sync_dry_run_by_default(mocker)
def test_sync_explicit_dry_run_flag(mocker)
def test_sync_apply_calls_apply_diff(mocker)
def test_sync_apply_with_prune_passes_prune_to_compute_diff(mocker)
def test_sync_apply_and_dry_run_conflict_raises_usage_error()
def test_sync_bare_repo_prepends_yakkuro(mocker)
def test_sync_owner_slash_repo_passes_through(mocker)
def test_sync_empty_diff_prints_no_changes(mocker)
def test_sync_ghauth_error_displays_actionable_message(mocker)
def test_sync_config_not_found_displays_actionable_message(mocker)

# diff command (3 tests)
def test_diff_exit_zero_when_no_diff(mocker)
def test_diff_exit_one_when_diff_present(mocker)
def test_diff_prune_flag_shows_would_be_deletes(mocker)

# show command (2 tests)
def test_show_lists_current_labels_sorted(mocker)
def test_show_does_not_load_config(mocker)

# Repo arg normalization (1 parametrized test, 3 cases)
@pytest.mark.parametrize("input,expected", [
    ("gh-manage", "yakkuro/gh-manage"),
    ("yakkuro/gh-manage", "yakkuro/gh-manage"),
    ("other-org/other-repo", "other-org/other-repo"),
])
def test_parse_repo_normalization(input, expected)

# Error handling decorator (2 tests)
def test_handle_errors_converts_gh_error_to_click_exception(mocker)
def test_handle_errors_converts_config_error_to_click_exception(mocker)
```

### Fixture — `tests/fixtures/config/labels-valid-with-rename.yml`

```yaml
version: 1
categories:
  type:
    description: "Test category with rename support"
    labels:
      - name: "fix"
        old_name: "bug"
        color: "d73a4a"
        description: "Bug fix"
      - name: "feat"
        color: "a2eeef"
        description: "New feature"
```

### Test count summary

| File | Tests |
|---|---|
| `test_sanity.py` (existing) | 2 |
| `test_cli_entry.py` (existing) | 17 |
| `test_load_config.py` (existing) | 12 |
| `test_labels.py` (new) | ~18 |
| `test_labels_sync.py` (new) | ~19 |
| `test_github_client.py` (new) | ~16 |
| **Total** | **~84** |

Phase 4 had 31 tests. Phase 5 adds ~53 new tests → **84 tests total**.

### Coverage target

- **Line coverage ≥ 90%** on new modules (`github_client.py`, `labels_sync.py`, `commands/labels.py`)
- **Branch coverage ≥ 85%** on the same

Measured via `uv run pytest --cov=gh_manage --cov-report=term-missing`. `pytest-cov` is already in Phase 0's dev deps.

### Manual self-dogfood test (Phase 5 AC)

Performed during the PR as the concrete demonstration that the AC is met. Output captured into the PR description.

```bash
# Before state: gh-manage has 9 GitHub default labels
./gh-manage labels show gh-manage
# Expected: bug, documentation, duplicate, enhancement, good first issue,
#           help wanted, invalid, question, wontfix

# 1. Pre-sync diff (should show 3 renames + 5 creates)
./gh-manage labels diff gh-manage
# Expected exit 1, output:
#   ~ bug → fix
#     description: ... → "Bug fix (fix:)"
#   ~ documentation → docs
#     description: ... → "Documentation changes (docs:)"
#   ~ enhancement → feat
#     description: ... → "New feature (feat:)"
#   + chore
#   + refactor
#   + test
#   + ci
#   + perf

# 2. Dry-run summary
./gh-manage labels sync gh-manage
# Expected: same diff output + "Dry-run: 8 changes. Re-run with --apply to execute."
# Exit 0

# 3. Apply
./gh-manage labels sync gh-manage --apply
# Expected: progress lines for each op + "Applied 8 changes." Exit 0

# 4. Idempotency check
./gh-manage labels diff gh-manage
# Expected: "No diff." Exit 0

# 5. Final state
./gh-manage labels show gh-manage
# Expected: 14 labels sorted: chore, ci, docs, duplicate, feat, fix,
#           good first issue, help wanted, invalid, perf, question, refactor,
#           test, wontfix
```

This 5-step walkthrough IS the direct demonstration of Phase 5's primary AC. The PR description must include the full output as a code block.

### CI coverage

gh-manage's own `ci.yml` already invokes `reusable-pr-gate-python.yml` which runs ruff → ruff format --check → mypy src → pytest. The Phase 5 new tests are picked up automatically by pytest. No workflow changes needed.

### Red-Green verification in writing-plans phase

For each Layer 2 test (the critical ones in `test_labels_sync.py`), the writing-plans phase documents an explicit Red-Green verification step: write the test, confirm Red, implement, confirm Green, intentionally break one line of the implementation, confirm Red again, restore, confirm Green.

## Dependencies

### External (runtime)

- Phase 4 dependencies unchanged: `click>=8.1,<9`, `pydantic>=2.5,<3`, `pyyaml>=6.0,<7`
- `gh` CLI 2.x+ on the user's machine with `gh auth login` completed (documented in `docs/usage/cli.md` prerequisites)
- `uv` (documented in Phase 4)

### External (dev)

- Phase 4 dev deps unchanged: `pytest>=8.0,<9`, `pytest-cov>=5.0,<6`, `pytest-mock>=3.12,<4`, `types-PyYAML>=6.0`

**No new dependencies**. Phase 5 uses only what Phase 0-4 already pinned.

### Internal

- `src/gh_manage/config.py` (Phase 4) — reused unchanged for `load_config(Path("config/labels.yml"), LabelsConfig)`
- `src/gh_manage/models/labels.py` (Phase 4) — extended with `old_name` field
- `src/gh_manage/cli.py` (Phase 4) — no change (the existing `main.add_command(labels_cmd.labels)` registration continues to work)
- `src/gh_manage/__main__.py` (Phase 4) — no change
- `gh-manage` shell wrapper (Phase 4) — no change
- `reusable-pr-gate-python.yml` (Phase 1) — no change; picks up Phase 5 tests automatically

## Release Flow

1. Implementation on `feat/phase-5-labels-sync` branch
2. Commits logically separated (bootstrap → github_client → labels_sync → commands rewrite → config yml → docs → final verification)
3. CI green throughout
4. 4-reviewer cross-agent review (Codex + superpowers:code-reviewer + silent-failure-hunter + code-reviewer) before ready
5. Promote `CHANGELOG-cli.md` `[Unreleased]` → `[0.2.0] - 2026-04-11` pre-merge
6. Manual self-dogfood: run the 5-step walkthrough from § Testing Strategy against `yakkuro/gh-manage` before merging
7. Squash merge to `main`
8. On main: `git tag -a cli/v0.2.0 -m "cli/v0.2.0 — Phase 5 labels sync"` and `git push origin cli/v0.2.0`
9. `gh release create cli/v0.2.0 --latest=false --notes "..."` (reusable track's `v0.2.1` stays `latest`)
10. Smoke test: `gh extension install yakkuro/gh-manage` on a clean environment, run the 5-step walkthrough as the integration check
11. Handoff to Task #54 — post-Phase-5 light review/refactor checkpoint

## References

- [`docs/specs/2026-04-10-gh-manage-design.md`](./2026-04-10-gh-manage-design.md) — main design spec (§ `github_client.py`, § `commands/labels.py`, § Phase 5 Acceptance Criteria)
- [`docs/specs/2026-04-10-phase-4-cli-skeleton-design.md`](./2026-04-10-phase-4-cli-skeleton-design.md) — Phase 4 establishes `load_config`, `LabelsConfig`, and the click command tree
- [`pyproject.toml`](../../pyproject.toml) — existing dependency pins (no changes in Phase 5)
- [`CHANGELOG-cli.md`](../../CHANGELOG-cli.md) — CLI tag track changelog (modified by Phase 5)
- [`docs/usage/cli.md`](../usage/cli.md) — consumer guide (extended by Phase 5 with labels section)
- [Click 8 documentation](https://click.palletsprojects.com/en/8.1.x/) — `@click.group`, nested commands, `CliRunner`, `ClickException`, `UsageError`
- [GitHub REST API — Labels](https://docs.github.com/en/rest/issues/labels) — endpoint reference for `gh api` calls
- [`gh api` documentation](https://cli.github.com/manual/gh_api) — subprocess contract

## Appendix: Scope guard against common overreach

A non-exhaustive list of things NOT to do in Phase 5, to keep the PR focused:

- Do NOT add `--format json` / `--format table` to any subcommand — deferred to Phase 5.1
- Do NOT add `labels sync --all` or multi-repo batching — deferred to Phase 6 (needs `repos.yml`)
- Do NOT add `repos.yml` pydantic model — deferred to Phase 6
- Do NOT implement rate-limit retry/backoff — deferred to Phase 8 (scheduled runs)
- Do NOT add interactive confirmation prompts to `--apply` — Q8 A decided against
- Do NOT add `--yes` / `--force` flags — Q8 A decided against (they're for interactive prompts which don't exist)
- Do NOT add heuristic rename detection (color/description-based guessing) — only `old_name` triggers rename
- Do NOT add a `--user` flag to override `gh auth` — use the current `gh` auth context
- Do NOT add environment variable overrides (`GH_MANAGE_DEFAULT_OWNER`, etc.) — hardcoded `yakkuro` is fine for Phase 5
- Do NOT refactor the Phase 4 `load_config` / `LabelsConfig` beyond adding `old_name` — other changes wait for the Task #54 light review checkpoint
- Do NOT modify the reusable workflows, `gh-manage` shell wrapper, `__main__.py`, or `cli.py` beyond what's explicitly listed in § Components
- Do NOT add label colors uniqueness validation — schema only checks 6-char hex format
- Do NOT add label count limits — GitHub has its own limits; we pass through
- Do NOT add `protection` or `drift` or `init` / `apply` subcommand implementations — those are Phase 6/7/8
- Do NOT touch `pyproject.toml` beyond the version bump — no new dependencies
- Do NOT add `# type: ignore` comments without a justifying explanation
