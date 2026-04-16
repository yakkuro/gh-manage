# Extract Shared Command Helpers

- **Date**: 2026-04-16
- **Size**: Small
- **Sizing Rationale**: 1 new file + 4 existing files modified. No design decisions beyond module placement.
- **Target**: yakkuro/gh-manage
- **Goal**: Eliminate security-critical code duplication across `commands/` by extracting shared helpers into `commands/_shared.py`.

## Background

Issue #38. Codebase review found that `_resolve_profile_path` (path traversal defense), `_handle_errors`, and 6 other helpers are copy-pasted across `commands/init.py`, `commands/apply.py`, `commands/drift.py`, and `commands/protection.py`. A security fix in any of these requires updating 3-4 files identically — a maintenance hazard.

## Design

### New file: `src/gh_manage/commands/_shared.py`

Contains all shared helpers extracted from the 4 command modules. The `_` prefix signals internal-to-commands usage.

#### Extracted functions

| Function | Source files | Notes |
|---|---|---|
| `handle_errors` | init, apply, drift, protection | Union of all domain exceptions |
| `VALID_PROFILE_NAME_RE` | init, apply, drift, protection | `re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")` |
| `resolve_profile_path(name: str) -> Path` | init, apply, drift, protection | Path traversal defense (load-bearing) |
| `resolve_templates_root() -> Path` | init, apply | |
| `resolve_default_labels_path() -> Path` | init, apply, drift | |
| `resolve_branch_protection_path() -> Path` | init, apply, drift, protection | |
| `resolve_backup_dir() -> Path` | init, apply, protection | |
| `resolve_repos_path() -> Path` | drift | Bundled repos.yml path |
| `format_files_diff(diff: ProfileFilesDiff) -> str` | init, apply | |

#### `handle_errors` exception list (union)

```python
_DOMAIN_ERRORS = (
    GhError, ConfigError, GitError, ProfileError, ProtectionError, DriftError,
)
```

Catching the superset at CLI layer is safe — exceptions that cannot occur for a given command are simply never raised.

### Modified files

Each of the 4 command files:
1. Remove the duplicated functions
2. Add `from gh_manage.commands._shared import handle_errors, resolve_profile_path, ...`
3. Replace `_handle_errors` references with `handle_errors`
4. No logic changes

### What does NOT change

- Command-specific click decorators and business logic
- Sync modules (labels_sync, profile_sync, protection_sync, drift_sync)
- Models, GitHub API layer, config.py
- Test files (tests call the public click commands, not the internal helpers)

## Acceptance Criteria

1. `uv run pytest tests/ -v` — all 417 tests pass (zero regressions)
2. `uvx ruff@0.8.0 check src/ tests/ && uvx ruff@0.8.0 format --check src/ tests/` — clean
3. `grep -r '_resolve_profile_path\|_handle_errors\|_VALID_PROFILE_NAME_RE' src/gh_manage/commands/init.py src/gh_manage/commands/apply.py src/gh_manage/commands/drift.py src/gh_manage/commands/protection.py` — zero matches (all private copies removed)
4. `grep -c 'resolve_profile_path' src/gh_manage/commands/_shared.py` — exactly 1 definition
