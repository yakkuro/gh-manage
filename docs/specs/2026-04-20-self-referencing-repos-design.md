# Self-Referencing Repos: drift scanner exemption (Issue #72)

**Status**: design
**Date**: 2026-04-20
**Issue**: #72
**Related**: #20 (drift-fleet rollout), PRs #67–#73

## Problem

`check_profile_files` compares each entry in `ProfileSpec.files` against the
bundled template content via SHA256 hash. The bundled `ci/python-ci.yml`
template pins:

```yaml
uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.0.0
```

This is correct for **external consumer repos** that import gh-manage's
reusables at a tagged version. But **gh-manage itself** publishes those
reusables and cannot pin to its own tag without bootstrap pain. Its local
`.github/workflows/ci.yml` therefore uses a local-path reference:

```yaml
uses: ./.github/workflows/reusable-pr-gate-python.yml
```

The two will never hash-match. The drift scanner reports a forever-MEDIUM
on `profile_files/.github/workflows/ci.yml` for gh-manage on every scan.
This is the last persistent self-drift finding (post #69, #70, #73).

## Non-Goals

- Solving the broader "templates with variable substitution" problem.
  When/if more templates need substitution (e.g., per-repo Python version),
  that's a separate spec.
- Detecting self-referencing automatically from git remote analysis. The
  exemption is opt-in via explicit config to keep behavior predictable.

## Design

### Schema change: `RepoEntry.self_referencing`

Add a single boolean field to `gh_manage.models.repos.RepoEntry`:

```python
class RepoEntry(BaseModel):
    name: str
    profile: str
    enabled: bool = True
    self_referencing: bool = False  # NEW
```

Default `False` preserves current behavior for all 22 entries. Only
`yakkuro/gh-manage` gets `self_referencing: true` in `repos.yml`.

### ScanContext extension

Add the same field to `ScanContext` (frozen dataclass):

```python
@dataclass(frozen=True)
class ScanContext:
    ...
    self_referencing: bool = False
```

The field flows from `RepoEntry` (in `--all` mode) or from a `repos.yml`
lookup (in single-repo mode) into the context that checks read.

### Per-entry skip in `check_profile_files`

When `ctx.self_referencing` is True, `check_profile_files` skips entries
whose **template content** references the scanning repo's own URL pattern:

```python
def _is_self_referencing_template(template_content: str, repo: str) -> bool:
    """True if the template uses `<repo>/.github/workflows/` — a path that
    a self-hosted repo cannot mirror locally."""
    return f"{repo}/.github/workflows/" in template_content
```

Detection is content-based (not name-based) so that:
- New self-referencing templates work automatically — no per-entry config
- Non-self-referencing entries (e.g., CLAUDE.md) still drift-check, so
  `skip_if_exists=True` LOW findings still fire (the user-editable signal
  remains useful)

When the skip fires, log at INFO level:

```python
log.info(
    "skipping self-referencing template %s for %s "
    "(template references %s/.github/workflows/)",
    entry.source, ctx.repo, ctx.repo,
)
```

This makes the exemption visible in scan logs (and the structured-logging
artifacts uploaded by the cron, per PR #68).

### CLI plumbing

Two paths reach `_scan_single_repo`:

1. **`--all` mode** (`_scan_worker`): already has `RepoEntry`. Pass
   `entry.self_referencing` through `_scan_single_repo` to `ScanContext`.

2. **Single-repo mode** (`gh manage drift .`): no `RepoEntry` in scope.
   Look up `owner_repo` (derived from `git_cli.get_origin_owner_repo`)
   in the bundled `repos.yml`. If the owner_repo matches an entry, use
   that entry's `self_referencing`. If not found (ad-hoc scan of an
   unregistered repo), default to `False`.

The lookup is cheap (small list, in-memory parse). It happens once per
scan, before `ScanContext` is built.

### Where the lookup lives

A new helper in `commands/_shared.py`:

```python
def _resolve_self_referencing(owner_repo: str) -> bool:
    """Look up `owner_repo` in bundled repos.yml. Return self_referencing
    flag if found; False otherwise.

    Centralized so both `_scan_single_repo` and `_scan_worker` use the same
    semantics. Failures (missing repos.yml, parse error) are logged and
    return False — drift checks should not abort because of this lookup."""
```

For `_scan_worker`, the helper is bypassed since the entry is already in
hand. For single-repo mode, the helper is invoked once per scan.

## Acceptance criteria (from #72)

- [x] gh-manage `drift .` reports no `profile_files/.github/workflows/ci.yml` finding
- [x] External consumer repos still receive the finding when their ci.yml drifts
  (verified: `self_referencing` defaults to False; only gh-manage opts in)
- [x] Decision documented in a design note (this file)

## Test plan

1. **RepoEntry schema**: `self_referencing` field, defaults to False, accepts True.
2. **ScanContext field**: `self_referencing` field, defaults to False.
3. **`_is_self_referencing_template` helper**:
   - Returns True for content containing `yakkuro/gh-manage/.github/workflows/`.
   - Returns False for content without the pattern.
   - Returns False even when `self_referencing=True` if the template is
     non-matching (e.g., CLAUDE.md).
4. **`check_profile_files` behavior**:
   - With `self_referencing=False`, ci.yml drift produces a MEDIUM finding (today's behavior).
   - With `self_referencing=True` and self-ref template, ci.yml is skipped.
   - With `self_referencing=True`, CLAUDE.md still produces LOW on drift.
5. **CLI lookup helper** `_resolve_self_referencing`:
   - Returns True for `yakkuro/gh-manage` after the repos.yml update.
   - Returns False for an unregistered repo.
   - Returns False (with log) when repos.yml is missing or unparseable.
6. **Drift scenario fixture**: new `tests/fixtures/drift-scenarios/profile_files/self-referencing-ci.yml`
   covering the skipped-by-self-referencing case.
7. **Golden test** (`test_golden_production_data_zero_drift`): unchanged —
   already mocks no drift, so unaffected.
8. **`bundled_repos_yml_loads`**: regression check — gh-manage entry now has
   `self_referencing: true` and still loads.

## Migration

None. New field has a safe default; the only repos.yml change marks gh-manage.

## Future considerations

If/when other repos publish reusable workflows under `yakkuro/<repo>/.github/workflows/`,
they can opt in by setting `self_referencing: true` in their `repos.yml` entry.
The detection helper will pick up their own URL automatically (via `ctx.repo`).
