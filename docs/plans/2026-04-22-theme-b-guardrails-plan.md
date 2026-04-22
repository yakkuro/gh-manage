# Theme B Guardrails — Prevention Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install a pre-apply doctor gate in `init` and `apply` (cli/v1.10.0) that refuses repository mutations when blocking-severity findings would remain after a semantic filter, closing the #46-class admin-merge gap.

**Architecture:** Reuse the existing `gh_manage.doctor` framework (PR #53, cli/v1.3.0). Add `ApplyScope` + `filter_pre_apply_findings` in a new `doctor/semantic_filter.py`. Augment `register_check` with a `resolves_with` kwarg and add per-check exception isolation to `run_checks`. Wire a shared `run_pre_apply_doctor` helper into both commands with a single `--allow-blocking` override flag. No reusable workflow YAML changes.

**Tech Stack:** Python 3.12, `uv`, `click` 8.x, `pydantic` v2, `pytest` 8 + `pytest-mock`, `pyyaml`. Lint/format pinned to `uvx ruff@0.8.0`.

**Spec:** `docs/specs/2026-04-22-theme-b-guardrails-prevention-layer-design.md`

---

## File Structure

### Created

| Path | Responsibility |
|---|---|
| `src/gh_manage/doctor/semantic_filter.py` | `ApplyScope` dataclass + `filter_pre_apply_findings` function |
| `tests/unit/doctor/test_semantic_filter.py` | Full filter behavior coverage (all ApplyScope × resolves_with combos) |
| `tests/unit/data/test_ci_templates.py` | Template invariance gate (canonical `jobs.pr-gate` shape, both python + typescript) |
| `tests/unit/commands/test_shared_pre_apply_doctor.py` | Unit tests for the shared helper |

### Modified

| Path | Changes |
|---|---|
| `src/gh_manage/doctor/registry.py` | Add `resolves_with` support on `register_check`; add `get_check_resolves_with` with synthetic-name prefix-strip lookup; rewrite `run_checks` with per-check exception isolation |
| `src/gh_manage/doctor/checks.py` | Pass `resolves_with=(...)` to each of the 3 existing `@register_check` calls |
| `src/gh_manage/commands/_shared.py` | Add `run_pre_apply_doctor` helper |
| `src/gh_manage/commands/apply.py` | Add `--allow-blocking` flag, flag validation, pre-apply doctor call |
| `src/gh_manage/commands/init.py` | Add `--allow-blocking` flag, flag validation, pre-apply doctor call, delete post-apply rollback block, convert post-apply to warning-only |
| `tests/unit/doctor/test_registry.py` | Extend with per-check isolation tests + `get_check_resolves_with` tests |
| `tests/unit/commands/test_apply.py` | Add pre-apply block / filter / override / healing tests |
| `tests/unit/commands/test_init.py` | Replace rollback tests with pre-apply block / filter / override tests |
| `docs/versioning.md` | cli/v1.10.0 entry |

### Release artifacts

| Path | Responsibility |
|---|---|
| `docs/release-notes/cli-v1.10.0.md` (or GitHub Release body) | User-facing release notes (content from spec §9) |

---

## Branch & PR strategy

- Current branch: `docs/theme-b-guardrails-spec` (holds spec + this plan).
- All implementation happens on a new branch `feat/theme-b-guardrails-v1.10` branched from `main` after the spec/plan PR merges. OR, if the spec PR is kept open, implementation piggybacks on the same branch (decided at PR-creation time).
- Each task commits independently. No squash until PR merge.
- After implementation complete: 4-reviewer PR review per `claude-dotfiles/rules/workflow-review.md`, then merge + tag cli/v1.10.0.

---

## Phase 1 — Semantic filter + registry augmentation

### Task 1: Extend `register_check` decorator with `resolves_with` kwarg

**Files:**
- Modify: `src/gh_manage/doctor/registry.py`
- Test: `tests/unit/doctor/test_registry.py` (extend)

- [ ] **Step 1: Write failing test — decorator accepts and stores `resolves_with`**

Append to `tests/unit/doctor/test_registry.py`:

```python
def test_register_check_stores_resolves_with_tuple():
    from gh_manage.doctor import registry
    from gh_manage.doctor.context import CheckContext
    from gh_manage.findings import Finding

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/test-with-resolves", resolves_with=("sync_files",))
        def _c(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        assert getattr(_c, "__doctor_resolves_with__", None) == ("sync_files",)
    finally:
        registry._CHECKS[:] = before


def test_register_check_resolves_with_defaults_to_empty():
    from gh_manage.doctor import registry
    from gh_manage.doctor.context import CheckContext
    from gh_manage.findings import Finding

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/test-no-resolves")
        def _c(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        assert getattr(_c, "__doctor_resolves_with__", None) == ()
    finally:
        registry._CHECKS[:] = before
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/unit/doctor/test_registry.py::test_register_check_stores_resolves_with_tuple tests/unit/doctor/test_registry.py::test_register_check_resolves_with_defaults_to_empty -v
```

Expected: `FAIL` — `TypeError: register_check() got an unexpected keyword argument 'resolves_with'`.

- [ ] **Step 3: Add `resolves_with` kwarg and attribute**

Replace `register_check` in `src/gh_manage/doctor/registry.py`:

```python
def register_check(
    name: str,
    *,
    resolves_with: tuple[str, ...] = (),
) -> Callable[[_F], _F]:
    """Decorator factory: register a check under `name`.

    `resolves_with` declares which `ApplyScope` domains (sync_files,
    sync_labels, sync_protection) will resolve this check's findings
    as a side-effect of `init` / `apply` running. Used by
    `doctor.semantic_filter.filter_pre_apply_findings` to drop
    findings that the current apply invocation will fix.

    Default `()` is the conservative choice: a check without a
    declared resolves_with is NEVER filtered (always blocking).
    """

    def _decorator(fn: _F) -> _F:
        fn.__doctor_check_name__ = name  # type: ignore[attr-defined]
        fn.__doctor_resolves_with__ = resolves_with  # type: ignore[attr-defined]
        _CHECKS.append(fn)
        return fn

    return _decorator
```

- [ ] **Step 4: Run tests — should pass**

```bash
uv run pytest tests/unit/doctor/test_registry.py -v
```

Expected: all registry tests PASS including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/doctor/registry.py tests/unit/doctor/test_registry.py
git commit -m "feat(doctor): add resolves_with kwarg to register_check"
```

---

### Task 2: Add `get_check_resolves_with` lookup with synthetic-name handling

**Files:**
- Modify: `src/gh_manage/doctor/registry.py`
- Test: `tests/unit/doctor/test_registry.py` (extend)

- [ ] **Step 1: Write failing test**

Append to `tests/unit/doctor/test_registry.py`:

```python
def test_get_check_resolves_with_returns_registered_tuple():
    from gh_manage.doctor import registry
    from gh_manage.doctor.context import CheckContext
    from gh_manage.findings import Finding

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/known", resolves_with=("sync_files",))
        def _c(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        assert registry.get_check_resolves_with("shape/known") == ("sync_files",)
    finally:
        registry._CHECKS[:] = before


def test_get_check_resolves_with_synthetic_prefix_strip():
    """shape/check-error:<original> maps to original's resolves_with."""
    from gh_manage.doctor import registry
    from gh_manage.doctor.context import CheckContext
    from gh_manage.findings import Finding

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check(
            "shape/original",
            resolves_with=("sync_protection",),
        )
        def _c(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        assert registry.get_check_resolves_with(
            "shape/check-error:shape/original"
        ) == ("sync_protection",)
    finally:
        registry._CHECKS[:] = before


def test_get_check_resolves_with_unknown_returns_empty():
    from gh_manage.doctor import registry

    assert registry.get_check_resolves_with("shape/does-not-exist") == ()


def test_get_check_resolves_with_unknown_synthetic_returns_empty():
    from gh_manage.doctor import registry

    assert registry.get_check_resolves_with(
        "shape/check-error:shape/nonexistent"
    ) == ()
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/unit/doctor/test_registry.py -k "resolves_with" -v
```

Expected: the 4 new tests FAIL with `AttributeError: module 'gh_manage.doctor.registry' has no attribute 'get_check_resolves_with'`.

- [ ] **Step 3: Implement `get_check_resolves_with`**

Append to `src/gh_manage/doctor/registry.py` (after `register_check`):

```python
def get_check_resolves_with(check_name: str) -> tuple[str, ...]:
    """Return the `resolves_with` tuple for a check name.

    Three cases handled:

    1. Plain registered name (e.g. `"shape/job-shape-coherence"`) —
       direct lookup against the registry.
    2. Synthetic error name `"shape/check-error:<original>"` emitted
       by `run_checks` when a check raised CiYmlParseError or
       DoctorCheckError — strip the prefix and re-lookup the original.
    3. Unknown name — return `()` (conservative default, matches the
       "unset resolves_with is never filtered" invariant).
    """
    for fn in _CHECKS:
        if getattr(fn, "__doctor_check_name__", None) == check_name:
            return getattr(fn, "__doctor_resolves_with__", ())
    prefix = "shape/check-error:"
    if check_name.startswith(prefix):
        original = check_name[len(prefix):]
        for fn in _CHECKS:
            if getattr(fn, "__doctor_check_name__", None) == original:
                return getattr(fn, "__doctor_resolves_with__", ())
    return ()
```

- [ ] **Step 4: Run tests — should pass**

```bash
uv run pytest tests/unit/doctor/test_registry.py -v
```

Expected: all PASS including the 4 new tests.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/doctor/registry.py tests/unit/doctor/test_registry.py
git commit -m "feat(doctor): add get_check_resolves_with with synthetic-name strip"
```

---

### Task 3: Rewrite `run_checks` with per-check exception isolation

**Files:**
- Modify: `src/gh_manage/doctor/registry.py`
- Test: `tests/unit/doctor/test_registry.py` (extend)

- [ ] **Step 1: Write failing tests — per-check isolation**

Append to `tests/unit/doctor/test_registry.py`:

```python
def test_run_checks_isolates_ci_yml_parse_error():
    """If one check raises CiYmlParseError, it becomes a synthetic
    LOW diagnostic and other checks' findings are preserved."""
    from gh_manage.doctor import registry
    from gh_manage.doctor.context import CheckContext
    from gh_manage.doctor.errors import CiYmlParseError
    from gh_manage.findings import Finding

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/bad", resolves_with=("sync_files",))
        def _bad(ctx: CheckContext) -> tuple[Finding, ...]:
            raise CiYmlParseError("synthetic parse failure")

        @registry.register_check("shape/good", resolves_with=())
        def _good(ctx: CheckContext) -> tuple[Finding, ...]:
            return (
                Finding(
                    severity="high",
                    check="shape/good",
                    repo=ctx.repo,
                    field_path="x",
                    current_value=None,
                    desired_value=None,
                    message="good fired",
                ),
            )

        findings = registry.run_checks(_ctx())
        assert len(findings) == 2
        synthetic = [f for f in findings if f.check.startswith("shape/check-error:")]
        good = [f for f in findings if f.check == "shape/good"]
        assert len(synthetic) == 1
        assert synthetic[0].severity == "low"
        assert synthetic[0].check == "shape/check-error:shape/bad"
        assert "synthetic parse failure" in synthetic[0].message
        assert len(good) == 1
        assert good[0].severity == "high"
    finally:
        registry._CHECKS[:] = before


def test_run_checks_isolates_doctor_check_error():
    from gh_manage.doctor import registry
    from gh_manage.doctor.context import CheckContext
    from gh_manage.doctor.errors import DoctorCheckError
    from gh_manage.findings import Finding

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/broken", resolves_with=("sync_protection",))
        def _broken(ctx: CheckContext) -> tuple[Finding, ...]:
            raise DoctorCheckError("unexpected failure")

        findings = registry.run_checks(_ctx())
        assert len(findings) == 1
        assert findings[0].check == "shape/check-error:shape/broken"
        assert findings[0].severity == "low"
    finally:
        registry._CHECKS[:] = before


def test_run_checks_propagates_non_check_exceptions():
    """Only CiYmlParseError / DoctorCheckError are caught. Other
    exception classes (including arbitrary Python errors) propagate."""
    import pytest

    from gh_manage.doctor import registry
    from gh_manage.doctor.context import CheckContext
    from gh_manage.findings import Finding

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/kaboom")
        def _kaboom(ctx: CheckContext) -> tuple[Finding, ...]:
            raise ValueError("unmodeled failure")

        with pytest.raises(ValueError):
            registry.run_checks(_ctx())
    finally:
        registry._CHECKS[:] = before


def test_synthetic_finding_carries_original_resolves_with():
    """The synthetic check-error finding's resolves_with lookup must
    return the original check's declared domains."""
    from gh_manage.doctor import registry
    from gh_manage.doctor.context import CheckContext
    from gh_manage.doctor.errors import CiYmlParseError
    from gh_manage.findings import Finding

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check("shape/foo", resolves_with=("sync_files",))
        def _foo(ctx: CheckContext) -> tuple[Finding, ...]:
            raise CiYmlParseError("boom")

        findings = registry.run_checks(_ctx())
        synthetic_name = findings[0].check
        assert synthetic_name == "shape/check-error:shape/foo"
        assert registry.get_check_resolves_with(synthetic_name) == ("sync_files",)
    finally:
        registry._CHECKS[:] = before
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/unit/doctor/test_registry.py -k "run_checks or synthetic" -v
```

Expected: the 4 new tests FAIL because current `run_checks` uses `chain.from_iterable` and aborts on first exception.

- [ ] **Step 3: Rewrite `run_checks` with per-check try/except**

Replace `run_checks` in `src/gh_manage/doctor/registry.py`:

```python
import logging

from gh_manage.doctor.errors import CiYmlParseError, DoctorCheckError, DoctorError
from gh_manage.findings import Finding

log = logging.getLogger(__name__)


def run_checks(ctx: CheckContext) -> tuple[Finding, ...]:
    """Run every registered check with per-check exception isolation.

    If a check raises `CiYmlParseError` or `DoctorCheckError`, its
    output is replaced with a synthetic LOW finding
    (`check="shape/check-error:<original_name>"`) whose `resolves_with`
    — looked up via `get_check_resolves_with` — mirrors the original
    check's declaration. Other exception classes propagate.
    """
    all_findings: list[Finding] = []
    for fn in _CHECKS:
        check_name = getattr(fn, "__doctor_check_name__", "<unknown>")
        try:
            all_findings.extend(fn(ctx))
        except (CiYmlParseError, DoctorCheckError) as exc:
            log.warning(
                "doctor check %r raised %s; emitting synthetic LOW diagnostic",
                check_name,
                type(exc).__name__,
            )
            all_findings.append(
                Finding(
                    severity="low",
                    check=f"shape/check-error:{check_name}",
                    repo=ctx.repo,
                    field_path=check_name,
                    current_value="check_error",
                    desired_value="check_passes",
                    message=(
                        f"Doctor check {check_name!r} failed to run: {exc}. "
                        f"Other checks continued; the pre-apply filter "
                        f"treats this as if {check_name!r} emitted no findings."
                    ),
                    remediation=(
                        "Fix the underlying cause of the check failure. "
                        "For ci.yml parse errors, either repair the YAML "
                        "manually or proceed with apply (which rewrites "
                        "ci.yml from the profile template)."
                    ),
                )
            )
    return tuple(all_findings)
```

Also update the top-of-file imports — remove `from itertools import chain` if unused, or leave it if `run_named_checks` still uses it. Check the current state:

```bash
grep -n "chain" src/gh_manage/doctor/registry.py
```

If `chain.from_iterable` is still used elsewhere, keep the import; if `run_named_checks` uses it, refactor it to use the same try/except pattern — but only if it was raising on exceptions before. Since `run_named_checks` is not on the init/apply hot path (only the `--check` CLI option uses it), leave its behavior as-is for now.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/doctor/test_registry.py -v
```

Expected: all PASS including the 4 new isolation tests. Existing `test_register_check_adds_to_registry_and_run_checks_executes_all` should still pass (no exceptions in that fixture, so the per-check try block is a no-op).

- [ ] **Step 5: Run full doctor test subset to catch regressions**

```bash
uv run pytest tests/unit/doctor/ -v
```

Expected: all PASS. Checks raise `CiYmlParseError` for malformed YAML; the new behavior converts those to synthetic findings, which may change assertions in other tests. If `tests/unit/doctor/test_checks.py` has tests that expect `CiYmlParseError` to propagate from `run_checks`, update them (they should expect the synthetic finding now).

- [ ] **Step 6: Commit**

```bash
git add src/gh_manage/doctor/registry.py tests/unit/doctor/test_registry.py
git commit -m "feat(doctor): per-check exception isolation in run_checks"
```

---

### Task 4: Update existing checks with `resolves_with` declarations

**Files:**
- Modify: `src/gh_manage/doctor/checks.py`
- Test: existing doctor check tests (no new tests; behavior unchanged)

- [ ] **Step 1: Update the 3 `@register_check` decorators**

In `src/gh_manage/doctor/checks.py`:

```python
@register_check(
    "shape/job-shape-coherence",
    resolves_with=("sync_files",),
)
def check_job_shape_coherence(ctx: CheckContext) -> tuple[Finding, ...]:
    # ... body unchanged ...
```

```python
@register_check(
    "shape/reusable-adoption",
    resolves_with=("sync_files",),
)
def check_reusable_adoption(ctx: CheckContext) -> tuple[Finding, ...]:
    # ... body unchanged ...
```

```python
@register_check(
    "shape/required-contexts-match",
    resolves_with=("sync_protection",),
)
def check_required_contexts_match(ctx: CheckContext) -> tuple[Finding, ...]:
    # ... body unchanged ...
```

- [ ] **Step 2: Run all doctor tests**

```bash
uv run pytest tests/unit/doctor/ -v
```

Expected: all PASS. No behavior change for these tests (resolves_with is consumed by filter, not by check logic).

- [ ] **Step 3: Verify `get_check_resolves_with` returns the right tuples**

Quick interactive sanity (one-shot):

```bash
uv run python -c "
from gh_manage.doctor import checks  # force registration
from gh_manage.doctor.registry import get_check_resolves_with
print('job-shape-coherence:', get_check_resolves_with('shape/job-shape-coherence'))
print('reusable-adoption:', get_check_resolves_with('shape/reusable-adoption'))
print('required-contexts-match:', get_check_resolves_with('shape/required-contexts-match'))
"
```

Expected output:

```
job-shape-coherence: ('sync_files',)
reusable-adoption: ('sync_files',)
required-contexts-match: ('sync_protection',)
```

- [ ] **Step 4: Commit**

```bash
git add src/gh_manage/doctor/checks.py
git commit -m "feat(doctor): declare resolves_with for all shape/* checks"
```

---

### Task 5: Create `semantic_filter.py` with `ApplyScope` + filter

**Files:**
- Create: `src/gh_manage/doctor/semantic_filter.py`
- Test: `tests/unit/doctor/test_semantic_filter.py`

- [ ] **Step 1: Write failing tests first**

Create `tests/unit/doctor/test_semantic_filter.py`:

```python
"""Tests for doctor.semantic_filter (spec §2)."""

from __future__ import annotations

import pytest

from gh_manage.findings import Finding


def _f(check: str, severity: str = "high") -> Finding:
    return Finding(
        severity=severity,
        check=check,
        repo="yakkuro/example",
        field_path="x",
        current_value=None,
        desired_value=None,
        message="msg",
    )


def test_apply_scope_is_frozen_dataclass():
    from gh_manage.doctor.semantic_filter import ApplyScope

    s = ApplyScope(sync_files=True, sync_labels=False, sync_protection=False)
    with pytest.raises(Exception):
        s.sync_files = False  # type: ignore[misc]


def test_filter_drops_finding_when_scope_covers_resolves_with():
    """sync_files=True filters out shape/job-shape-coherence
    (resolves_with=('sync_files',))."""
    from gh_manage.doctor import checks  # noqa: F401 — force registration
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=True, sync_labels=False, sync_protection=False)
    findings = (_f("shape/job-shape-coherence", "critical"),)
    filtered = filter_pre_apply_findings(findings, scope)
    assert filtered == ()


def test_filter_keeps_finding_when_scope_does_not_cover():
    """sync_protection=False keeps shape/required-contexts-match findings."""
    from gh_manage.doctor import checks  # noqa: F401
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=False)
    finding = _f("shape/required-contexts-match", "high")
    filtered = filter_pre_apply_findings((finding,), scope)
    assert len(filtered) == 1
    assert filtered[0].check == "shape/required-contexts-match"


def test_filter_unknown_check_never_dropped():
    """A check not in the registry is conservatively kept (invariant 1)."""
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=True)
    finding = _f("shape/fabricated-in-test", "high")
    filtered = filter_pre_apply_findings((finding,), scope)
    assert len(filtered) == 1


def test_filter_synthetic_error_name_resolves_via_prefix_strip():
    """shape/check-error:<registered> inherits the registered check's
    resolves_with and is filtered accordingly."""
    from gh_manage.doctor import checks  # noqa: F401
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=True, sync_labels=False, sync_protection=False)
    finding = _f("shape/check-error:shape/job-shape-coherence", "low")
    filtered = filter_pre_apply_findings((finding,), scope)
    assert filtered == ()


def test_filter_requires_all_domains_in_resolves_with():
    """AND semantics: a check with resolves_with=(A, B) is filtered
    only when BOTH A and B are in scope."""
    from gh_manage.doctor import registry
    from gh_manage.doctor.context import CheckContext
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check(
            "shape/needs-both",
            resolves_with=("sync_files", "sync_protection"),
        )
        def _c(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        finding = _f("shape/needs-both", "high")

        # Only sync_files → keeps
        s1 = ApplyScope(sync_files=True, sync_labels=False, sync_protection=False)
        assert filter_pre_apply_findings((finding,), s1) == (finding,)

        # Both → drops
        s2 = ApplyScope(sync_files=True, sync_labels=False, sync_protection=True)
        assert filter_pre_apply_findings((finding,), s2) == ()
    finally:
        registry._CHECKS[:] = before


def test_filter_empty_scope_keeps_everything():
    from gh_manage.doctor import checks  # noqa: F401
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=False, sync_labels=False, sync_protection=False)
    findings = (
        _f("shape/job-shape-coherence", "critical"),
        _f("shape/required-contexts-match", "high"),
        _f("shape/reusable-adoption", "medium"),
    )
    filtered = filter_pre_apply_findings(findings, scope)
    assert len(filtered) == 3


def test_filter_preserves_finding_order():
    from gh_manage.doctor import checks  # noqa: F401
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=False, sync_labels=False, sync_protection=False)
    findings = (
        _f("shape/job-shape-coherence", "critical"),
        _f("shape/required-contexts-match", "high"),
    )
    filtered = filter_pre_apply_findings(findings, scope)
    assert filtered[0].check == "shape/job-shape-coherence"
    assert filtered[1].check == "shape/required-contexts-match"


def test_filter_ignores_severity_only_checks_check_name():
    """A low-severity finding with matching resolves_with is still
    filtered (invariant 3). This is a no-op at the block gate but
    matters for any consumer that enumerates filtered findings."""
    from gh_manage.doctor import checks  # noqa: F401
    from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings

    scope = ApplyScope(sync_files=True, sync_labels=False, sync_protection=False)
    finding = _f("shape/job-shape-coherence", "low")
    filtered = filter_pre_apply_findings((finding,), scope)
    assert filtered == ()
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/unit/doctor/test_semantic_filter.py -v
```

Expected: all FAIL with `ModuleNotFoundError: No module named 'gh_manage.doctor.semantic_filter'`.

- [ ] **Step 3: Create `semantic_filter.py`**

Create `src/gh_manage/doctor/semantic_filter.py`:

```python
"""ApplyScope + pre-apply doctor finding filter (spec §2).

Doctor findings from `doctor.run_on_path` are "informational" by
default. For init/apply's pre-apply gate, some findings are about to
be resolved by the same invocation that triggered the check (e.g., a
shape/job-shape-coherence finding on a repo whose ci.yml init is
about to overwrite). Those findings should not block.

`ApplyScope` enumerates which repository-state domains the current
invocation will mutate. `filter_pre_apply_findings` drops findings
whose registered `resolves_with` tuple is fully covered by the scope.
"""

from __future__ import annotations

from dataclasses import dataclass

from gh_manage.doctor.registry import get_check_resolves_with
from gh_manage.findings import Finding


@dataclass(frozen=True)
class ApplyScope:
    """The set of repository-state domains that this invocation will mutate.

    A doctor finding is pre-apply-filterable iff every domain in the
    check's `resolves_with` tuple is True in this scope — i.e., this
    apply invocation will (attempt to) resolve the finding as a
    side-effect of running. Findings outside scope remain blocking.

    Frozen to prevent mutation during filter iteration and to enable
    safe sharing if filtering is ever parallelized.

    Domain semantics:
    - sync_files=True: ci.yml and other profile files will be
      rewritten from bundled templates. shape/* checks about ci.yml
      content are resolved by this action.
    - sync_labels=True: label set will be synchronized to labels.yml.
      No current doctor check uses this domain; reserved for future.
    - sync_protection=True: branch protection will be synchronized.
      shape/required-contexts-match findings are resolved.

    Profiles whose `protection_policy` is None cannot set
    `sync_protection=True` (init/apply refuses to touch protection
    in that case); protection findings therefore remain blocking and
    the operator must resolve them manually before init/apply
    succeeds.
    """

    sync_files: bool
    sync_labels: bool
    sync_protection: bool


def filter_pre_apply_findings(
    findings: tuple[Finding, ...],
    scope: ApplyScope,
) -> tuple[Finding, ...]:
    """Drop findings whose resolving-domain tuple is fully covered by scope.

    Conservative default: a check without a registered `resolves_with`
    (empty tuple) is NEVER filtered — `()` does not satisfy the
    "all-in-scope" check vacuously here because we treat an empty
    tuple as "no declared coverage", not as "vacuously covered".

    AND semantics: a check declaring `resolves_with=(A, B)` is only
    filtered when both A and B are True in scope.
    """
    scope_map = {
        "sync_files": scope.sync_files,
        "sync_labels": scope.sync_labels,
        "sync_protection": scope.sync_protection,
    }
    kept: list[Finding] = []
    for f in findings:
        resolves = get_check_resolves_with(f.check)
        if resolves and all(scope_map.get(d, False) for d in resolves):
            continue  # this apply will resolve it — not blocking
        kept.append(f)
    return tuple(kept)
```

- [ ] **Step 4: Run tests — all should pass**

```bash
uv run pytest tests/unit/doctor/test_semantic_filter.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Run full doctor test suite**

```bash
uv run pytest tests/unit/doctor/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/gh_manage/doctor/semantic_filter.py tests/unit/doctor/test_semantic_filter.py
git commit -m "feat(doctor): add ApplyScope + filter_pre_apply_findings"
```

---

## Phase 2 — Template invariance regression gate

### Task 6: Create `test_ci_templates.py`

**Files:**
- Test: `tests/unit/data/test_ci_templates.py` (NEW)

- [ ] **Step 1: Write the test file directly (expected Green immediately since templates already comply)**

Create `tests/unit/data/test_ci_templates.py`:

```python
"""Bundled ci/* templates — canonical shape regression gate (spec §4).

These tests fail if any bundled ci.yml template drifts away from the
`jobs.pr-gate: { name: "PR Gate" }` shape that branch-protection
requires. The canonical shape produces the status context
"PR Gate / PR Gate" when run; branch protection is hard-coded to
require that exact context.

If a PR edits the templates and breaks the shape, CI fails. See
yakkuro/gh-manage#46 for the incident where three consumer repos
had to be admin-merged because of this invariant breaking.

NOTE: Add any new bundled ci/* template to the parametrize list
manually — this test is not auto-discovered.
"""

from __future__ import annotations

import re
from importlib.resources import files

import pytest
import yaml

_REUSABLE_USES_PYTHON = re.compile(
    r"^yakkuro/gh-manage/\.github/workflows/reusable-pr-gate-python\.yml@.+$"
)
_REUSABLE_USES_TS = re.compile(
    r"^yakkuro/gh-manage/\.github/workflows/reusable-pr-gate-typescript\.yml@.+$"
)


@pytest.mark.parametrize(
    "filename, uses_re",
    [
        ("python-ci.yml", _REUSABLE_USES_PYTHON),
        ("ts-ci.yml", _REUSABLE_USES_TS),
    ],
)
def test_bundled_ci_template_preserves_canonical_shape(
    filename: str, uses_re: re.Pattern[str]
) -> None:
    text = (
        files("gh_manage.data") / "templates" / "ci" / filename
    ).read_text(encoding="utf-8")

    parsed = yaml.safe_load(text)

    assert isinstance(parsed, dict), (
        f"{filename}: top-level must be a mapping"
    )
    assert "jobs" in parsed and "pr-gate" in parsed["jobs"], (
        f"{filename}: must declare `jobs.pr-gate` — see spec "
        f"docs/specs/2026-04-22-theme-b-guardrails-prevention-layer-design.md §4"
    )
    pr_gate = parsed["jobs"]["pr-gate"]
    assert pr_gate.get("name") == "PR Gate", (
        f"{filename}: `jobs.pr-gate.name` must be exactly 'PR Gate' to "
        f"produce status context 'PR Gate / PR Gate'. See "
        f"yakkuro/gh-manage#46."
    )
    uses_value = pr_gate.get("uses", "")
    assert uses_re.match(uses_value), (
        f"{filename}: `jobs.pr-gate.uses` must reference reusable-pr-gate; "
        f"got {uses_value!r}"
    )
```

- [ ] **Step 2: Run tests — expected PASS**

```bash
uv run pytest tests/unit/data/test_ci_templates.py -v
```

Expected: both parametrized tests PASS (current templates already comply — this is a regression gate, not a forward-change test).

- [ ] **Step 3: Verify the test actually fails when templates drift (Red check)**

Sanity check: temporarily break the template and re-run to confirm test catches drift. Run:

```bash
cp src/gh_manage/data/templates/ci/python-ci.yml /tmp/python-ci-backup.yml
# Corrupt the template
sed -i 's/name: PR Gate/name: Something Else/' src/gh_manage/data/templates/ci/python-ci.yml
uv run pytest tests/unit/data/test_ci_templates.py -v
# Expected: test FAILS with message about "name must be exactly 'PR Gate'"

# Restore
cp /tmp/python-ci-backup.yml src/gh_manage/data/templates/ci/python-ci.yml
rm /tmp/python-ci-backup.yml
uv run pytest tests/unit/data/test_ci_templates.py -v
# Expected: test PASSES again
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/data/test_ci_templates.py
git commit -m "test(data): canonical shape regression gate for bundled ci templates"
```

---

## Phase 3 — Shared helper `run_pre_apply_doctor`

### Task 7: Add `run_pre_apply_doctor` to `_shared.py`

**Files:**
- Modify: `src/gh_manage/commands/_shared.py`
- Test: `tests/unit/commands/test_shared_pre_apply_doctor.py` (NEW)

- [ ] **Step 1: Write failing tests**

Create `tests/unit/commands/test_shared_pre_apply_doctor.py`:

```python
"""Tests for commands._shared.run_pre_apply_doctor (spec §3.1)."""

from __future__ import annotations

from pathlib import Path

import click
import pytest
from pytest_mock import MockerFixture

from gh_manage.doctor.semantic_filter import ApplyScope
from gh_manage.findings import Finding


def _finding(
    check: str = "shape/required-contexts-match",
    severity: str = "high",
) -> Finding:
    return Finding(
        severity=severity,
        check=check,
        repo="yakkuro/example",
        field_path="x",
        current_value=None,
        desired_value=None,
        message="msg",
    )


def test_pass_when_no_findings(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch("gh_manage.commands._shared.doctor.run_on_path", return_value=())
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=True)
    run_pre_apply_doctor(
        tmp_path, profile_name="python-service", scope=scope, allow_blocking=False
    )


def test_pass_when_only_filtered_findings(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """shape/required-contexts-match is filtered when sync_protection=True."""
    from gh_manage.doctor import checks  # noqa: F401 — force registration

    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(_finding(severity="high"),),
    )
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=True)
    run_pre_apply_doctor(
        tmp_path, profile_name="python-service", scope=scope, allow_blocking=False
    )


def test_pass_when_only_low_or_medium_findings(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Low/medium are not in the blocking set even if unfiltered."""
    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(_finding(check="shape/fabricated", severity="medium"),),
    )
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=False, sync_labels=False, sync_protection=False)
    run_pre_apply_doctor(
        tmp_path, profile_name="python-service", scope=scope, allow_blocking=False
    )


def test_blocks_on_unfiltered_high(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    from gh_manage.doctor import checks  # noqa: F401

    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(_finding(check="shape/required-contexts-match", severity="high"),),
    )
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=False)
    with pytest.raises(click.ClickException) as exc_info:
        run_pre_apply_doctor(
            tmp_path, profile_name="python-service", scope=scope, allow_blocking=False
        )
    assert "Pre-apply doctor" in str(exc_info.value.message)
    assert "--allow-blocking" in str(exc_info.value.message)


def test_blocks_on_unfiltered_critical(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(_finding(check="shape/fabricated", severity="critical"),),
    )
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=False, sync_labels=False, sync_protection=False)
    with pytest.raises(click.ClickException):
        run_pre_apply_doctor(
            tmp_path, profile_name="python-service", scope=scope, allow_blocking=False
        )


def test_allow_blocking_bypasses_block(
    mocker: MockerFixture, tmp_path: Path, capsys
) -> None:
    from gh_manage.doctor import checks  # noqa: F401

    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(_finding(check="shape/required-contexts-match", severity="high"),),
    )
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=False)
    run_pre_apply_doctor(
        tmp_path, profile_name="python-service", scope=scope, allow_blocking=True
    )
    captured = capsys.readouterr()
    assert "--allow-blocking" in captured.err
    assert "blocking finding" in captured.err


def test_setup_error_propagates(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """DoctorError from run_on_path (profile missing, repos.yml corrupt,
    etc.) propagates to the caller without being swallowed."""
    from gh_manage.doctor.errors import DoctorError

    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        side_effect=DoctorError("profile not found"),
    )
    from gh_manage.commands._shared import run_pre_apply_doctor

    scope = ApplyScope(sync_files=True, sync_labels=True, sync_protection=True)
    with pytest.raises(DoctorError):
        run_pre_apply_doctor(
            tmp_path, profile_name="bogus", scope=scope, allow_blocking=False
        )
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/unit/commands/test_shared_pre_apply_doctor.py -v
```

Expected: all FAIL with `ImportError: cannot import name 'run_pre_apply_doctor' from 'gh_manage.commands._shared'`.

- [ ] **Step 3: Add helper to `_shared.py`**

Append to `src/gh_manage/commands/_shared.py`:

```python
from gh_manage import doctor
from gh_manage.doctor.report import format_stdout as _doctor_format_stdout
from gh_manage.doctor.semantic_filter import ApplyScope, filter_pre_apply_findings
from gh_manage.findings import Finding, Severity


def run_pre_apply_doctor(
    target: Path,
    profile_name: str,
    scope: ApplyScope,
    allow_blocking: bool,
) -> None:
    """Block the caller if pre-apply doctor finds unresolved blocking findings.

    Raises `click.ClickException` on block. Returns None on pass. Emits
    a loud stderr warning when `allow_blocking=True` bypasses a block.

    Exception handling:
    - Per-check exceptions (CiYmlParseError, DoctorCheckError) are
      caught INSIDE `doctor.registry.run_checks` and converted to
      synthetic LOW findings (see spec §3.1.1). No handling needed
      here.
    - Setup errors (DoctorError subclasses raised from run_on_path
      itself — profile missing, repos.yml corrupt, git_cli failure,
      GitHub API error before any check runs) propagate.
    """
    blocking_severities: tuple[Severity, ...] = ("critical", "high")

    findings = doctor.run_on_path(target, profile_name=profile_name)
    filtered = filter_pre_apply_findings(findings, scope)
    blocking = tuple(f for f in filtered if f.severity in blocking_severities)

    log.info(
        "pre-apply doctor: findings=%d filtered=%d blocking=%d allow_blocking=%s",
        len(findings),
        len(findings) - len(filtered),
        len(blocking),
        allow_blocking,
    )

    if not blocking:
        return

    if allow_blocking:
        click.echo(
            f"WARNING: --allow-blocking: proceeding despite "
            f"{len(blocking)} blocking finding(s).",
            err=True,
        )
        return

    raise click.ClickException(
        _format_blocking_message(blocking, target)
    )


def _format_blocking_message(
    blocking: tuple[Finding, ...],
    target: Path,
) -> str:
    """Compose the user-facing pre-apply block message."""
    repo_label = str(target)
    prefix = (
        "Pre-apply doctor found blocking-severity finding(s) that this "
        "invocation will not resolve:\n"
    )
    body = _doctor_format_stdout(blocking, repo=repo_label)
    suffix = (
        "\n"
        "To proceed anyway (not recommended), re-run with --allow-blocking.\n"
        "To see all findings (including non-blocking), run:\n"
        f"    gh-manage doctor {target}"
    )
    return prefix + "\n" + body + "\n" + suffix
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/commands/test_shared_pre_apply_doctor.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Run existing `_shared.py` tests to ensure no regression**

```bash
uv run pytest tests/unit/commands/test_shared.py tests/unit/commands/test_shared_self_referencing.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/gh_manage/commands/_shared.py tests/unit/commands/test_shared_pre_apply_doctor.py
git commit -m "feat(commands): add run_pre_apply_doctor helper with semantic filter"
```

---

## Phase 4 — `apply` command integration

### Task 8: Add `--allow-blocking` flag and validation to `apply`

**Files:**
- Modify: `src/gh_manage/commands/apply.py`
- Test: `tests/unit/commands/test_apply.py` (extend)

- [ ] **Step 1: Write failing validation test**

Append to `tests/unit/commands/test_apply.py`:

```python
def test_apply_dry_run_with_allow_blocking_raises_usage_error(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """--dry-run + --allow-blocking is a user mistake; fail fast."""
    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(
        main,
        [
            "apply",
            str(tmp_path),
            "--profile",
            "python-service",
            "--dry-run",
            "--allow-blocking",
        ],
    )
    assert result.exit_code == 2  # Click UsageError exits 2
    assert "--allow-blocking requires --apply" in (result.stderr or result.output)


def test_apply_allow_blocking_without_apply_raises_usage_error(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """--allow-blocking without --apply is also invalid (default is dry-run)."""
    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(
        main,
        ["apply", str(tmp_path), "--profile", "python-service", "--allow-blocking"],
    )
    assert result.exit_code == 2
    assert "--allow-blocking requires --apply" in (result.stderr or result.output)
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/unit/commands/test_apply.py::test_apply_dry_run_with_allow_blocking_raises_usage_error tests/unit/commands/test_apply.py::test_apply_allow_blocking_without_apply_raises_usage_error -v
```

Expected: FAIL with `Usage error: no such option: --allow-blocking`.

- [ ] **Step 3: Add `--allow-blocking` click option and validation**

In `src/gh_manage/commands/apply.py`:

Add the option below the existing `@click.option("--also-protection", ...)`:

```python
@click.option(
    "--allow-blocking",
    is_flag=True,
    help=(
        "Bypass the pre-apply doctor block gate. Use only when a "
        "blocking finding is known and intentional — emits a loud "
        "WARNING to stderr. Requires --apply."
    ),
)
```

Add the `allow_blocking: bool` parameter to the `apply()` function signature (right after `also_protection: bool`):

```python
def apply(
    path: Path,
    profile_name: str,
    dry_run: bool,
    apply_flag: bool,
    force: bool,
    also_labels: bool,
    also_protection: bool,
    allow_blocking: bool,
) -> None:
```

Add validation just after the existing `if apply_flag and dry_run` check:

```python
    if apply_flag and dry_run:
        raise click.UsageError("--apply and --dry-run are mutually exclusive.")

    if allow_blocking and not apply_flag:
        raise click.UsageError(
            "--allow-blocking requires --apply; it has no effect in dry-run mode."
        )
```

- [ ] **Step 4: Run validation tests — should pass**

```bash
uv run pytest tests/unit/commands/test_apply.py -k "allow_blocking and usage_error" -v
```

Expected: both tests PASS.

- [ ] **Step 5: Run full apply test suite**

```bash
uv run pytest tests/unit/commands/test_apply.py -v
```

Expected: all PASS (no regression — pre-apply doctor is not yet wired in, so no blocking behavior change).

- [ ] **Step 6: Commit**

```bash
git add src/gh_manage/commands/apply.py tests/unit/commands/test_apply.py
git commit -m "feat(apply): add --allow-blocking flag with UsageError validation"
```

---

### Task 9: Wire pre-apply doctor into `apply`

**Files:**
- Modify: `src/gh_manage/commands/apply.py`
- Test: `tests/unit/commands/test_apply.py` (extend)

- [ ] **Step 1: Write failing tests — blocking behavior**

Append to `tests/unit/commands/test_apply.py`:

```python
def test_apply_blocks_on_unfiltered_high_finding(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """--apply without --also-protection: HIGH shape/required-contexts-match
    is NOT filtered (sync_protection=False) and blocks."""
    from gh_manage.doctor import checks  # noqa: F401

    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    mocker.patch(
        "gh_manage.commands.apply.labels_api.list_labels", return_value=[]
    )
    # Pre-apply doctor is invoked via commands._shared
    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(
            Finding(
                severity="high",
                check="shape/required-contexts-match",
                repo="yakkuro/example",
                field_path="x",
                current_value=None,
                desired_value=None,
                message="m",
            ),
        ),
    )
    # If we get past pre-apply, post-apply doctor is also patched (returns zero)
    mocker.patch(
        "gh_manage.commands.apply._doctor.run_on_path", return_value=(), create=True
    )

    runner = CliRunner(mix_stderr=False)
    with (
        patch(
            "gh_manage.commands.apply.profile_sync.apply_files_diff", return_value=[]
        ),
        patch("gh_manage.commands.apply.labels_sync.apply_diff"),
    ):
        result = runner.invoke(
            main,
            ["apply", str(tmp_path), "--profile", "python-service", "--apply"],
        )

    # Pre-apply block raises ClickException → exit 1
    assert result.exit_code == 1
    assert "Pre-apply doctor" in result.output or "Pre-apply doctor" in (
        result.stderr or ""
    )


def test_apply_also_protection_first_time_succeeds(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """--also-protection filters shape/required-contexts-match — first-time
    adoption (empty protection) proceeds."""
    from gh_manage.doctor import checks  # noqa: F401

    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    mocker.patch(
        "gh_manage.commands.apply.labels_api.list_labels", return_value=[]
    )
    mocker.patch(
        "gh_manage.commands.apply.protection_api.get_branch_protection",
        return_value={},
    )
    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(
            Finding(
                severity="high",
                check="shape/required-contexts-match",
                repo="yakkuro/example",
                field_path="x",
                current_value=None,
                desired_value=None,
                message="m",
            ),
        ),
    )

    runner = CliRunner(mix_stderr=False)
    with (
        patch(
            "gh_manage.commands.apply.profile_sync.apply_files_diff", return_value=[]
        ),
        patch(
            "gh_manage.commands.apply.protection_sync.apply_protection_diff",
        ),
    ):
        result = runner.invoke(
            main,
            [
                "apply",
                str(tmp_path),
                "--profile",
                "python-service",
                "--also-protection",
                "--apply",
            ],
        )

    # High finding is filtered — apply proceeds, exit 0
    assert result.exit_code == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_apply_allow_blocking_bypasses_pre_apply_block(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    from gh_manage.doctor import checks  # noqa: F401

    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    mocker.patch(
        "gh_manage.commands.apply.labels_api.list_labels", return_value=[]
    )
    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(
            Finding(
                severity="high",
                check="shape/required-contexts-match",
                repo="yakkuro/example",
                field_path="x",
                current_value=None,
                desired_value=None,
                message="m",
            ),
        ),
    )
    runner = CliRunner(mix_stderr=False)
    with (
        patch(
            "gh_manage.commands.apply.profile_sync.apply_files_diff", return_value=[]
        ),
        patch("gh_manage.commands.apply.labels_sync.apply_diff"),
    ):
        result = runner.invoke(
            main,
            [
                "apply",
                str(tmp_path),
                "--profile",
                "python-service",
                "--apply",
                "--allow-blocking",
            ],
        )

    assert result.exit_code == 0
    assert "--allow-blocking" in (result.stderr or "")


def test_apply_dry_run_skips_pre_apply_doctor(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch(
        "gh_manage.commands.apply.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    run_on_path_mock = mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path"
    )
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(
        main,
        ["apply", str(tmp_path), "--profile", "python-service", "--dry-run"],
    )
    assert result.exit_code == 0
    run_on_path_mock.assert_not_called()
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/unit/commands/test_apply.py -k "blocks_on_unfiltered or first_time_succeeds or allow_blocking_bypasses or dry_run_skips" -v
```

Expected: first three FAIL (pre-apply not yet wired); `dry_run_skips` may pass if mock isn't called anyway — verify manually.

- [ ] **Step 3: Wire pre-apply doctor into `apply`**

In `src/gh_manage/commands/apply.py`, add the scope computation + pre-apply call after the diff-print/dry-run-early-return and before the downgrade check. Locate this existing block:

```python
    if not apply_flag:
        click.echo(...)
        return

    # Pre-apply validation: fail fast on protection downgrade BEFORE any ...
    if (
        protection_diff is not None
        and not protection_diff.is_empty
        and protection_diff.has_downgrades
    ):
        raise click.ClickException(...)
```

Insert the new pre-apply doctor call **between** `return` (end of dry-run path) and the existing downgrade check. That means: if we reach this point, `apply_flag` is True. Full insertion:

```python
    if not apply_flag:
        click.echo(
            f"\nDry-run: {n_file_changes} file changes, "
            f"{n_label_changes} label changes, "
            f"{n_protection_changes} protection changes. Re-run with --apply to execute."
        )
        return

    # NEW — Pre-apply doctor gate (spec §3)
    from gh_manage.commands._shared import run_pre_apply_doctor
    from gh_manage.doctor.semantic_filter import ApplyScope

    scope = ApplyScope(
        sync_files=True,
        sync_labels=also_labels,
        sync_protection=also_protection,
    )
    run_pre_apply_doctor(
        target,
        profile_name=profile_name,
        scope=scope,
        allow_blocking=allow_blocking,
    )
    # END NEW

    # Pre-apply validation: fail fast on protection downgrade ...
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/commands/test_apply.py -v
```

Expected: all PASS, including the 4 new tests.

- [ ] **Step 5: Re-verify the existing `test_apply_prints_doctor_warnings_to_stderr` still passes**

The existing test mocks `shape/job-shape-coherence` with a critical finding. That check has `resolves_with=("sync_files",)` and apply's scope has `sync_files=True`, so the finding is filtered out of pre-apply (PASS). Post-apply then emits it as a warning (existing behavior).

```bash
uv run pytest tests/unit/commands/test_apply.py::test_apply_prints_doctor_warnings_to_stderr -v
```

Expected: PASS (exit 0, stderr contains "critical").

- [ ] **Step 6: Commit**

```bash
git add src/gh_manage/commands/apply.py tests/unit/commands/test_apply.py
git commit -m "feat(apply): wire pre-apply doctor gate before mutations"
```

---

## Phase 5 — `init` command integration

### Task 10: Delete post-apply rollback block from `init`

**Files:**
- Modify: `src/gh_manage/commands/init.py`
- Test: `tests/unit/commands/test_init.py` (delete obsolete rollback tests)

- [ ] **Step 1: Inventory existing rollback tests**

```bash
grep -n "rollback\|critical.*rollback\|test_init.*critical" tests/unit/commands/test_init.py
```

List the test function names that will be deleted.

- [ ] **Step 2: Delete the post-apply CRITICAL rollback block from `init.py`**

In `src/gh_manage/commands/init.py`, locate the block that starts:

```python
    # Post-apply doctor gate (spec §5.B).
    # Critical findings trigger rollback: remove files init created
    # ...
    findings = doctor_pkg.run_on_path(target, profile_name=profile_name)
    critical = tuple(f for f in findings if f.severity == "critical")
    if critical:
        ...
        raise click.ClickException(
            "init aborted due to critical doctor findings; rolled back "
            "files. See docs/specs/2026-04-17-doctor-guardrail-design.md §5."
        )
```

Delete the entire block (from the `# Post-apply doctor gate (spec §5.B).` comment through the final `raise click.ClickException(...)`). Keep the subsequent `n_protection_changes_final = ...` and `log.info(...)` + `click.echo("\nDone. Next steps:")` block intact.

Replace with the apply-pattern warning block (matching what `apply.py` does):

```python
    # Post-apply doctor warnings (mirrors apply.py, spec §3.2)
    from gh_manage.doctor import report as _doctor_report
    from gh_manage.doctor.errors import DoctorCheckError

    try:
        findings = doctor_pkg.run_on_path(target, profile_name=profile_name)
    except DoctorCheckError as exc:
        log.warning("post-init doctor check failed: %s", exc)
        click.echo(f"WARNING: post-init doctor check failed: {exc}", err=True)
        findings = ()

    blocking = tuple(f for f in findings if f.severity in ("critical", "high"))
    if blocking:
        click.echo("", err=True)
        click.echo(
            "WARNING: post-init doctor surfaced blocking-severity findings:",
            err=True,
        )
        click.echo(
            _doctor_report.format_stdout(blocking, repo=owner_repo),
            err=True,
        )
        click.echo(
            "Not failing init — run `gh-manage doctor` to review.",
            err=True,
        )
```

Also remove the local import `from gh_manage.doctor import report as doctor_report` at the top if it's no longer used elsewhere (the rollback path was the sole consumer).

- [ ] **Step 3: Remove obsolete rollback tests from `test_init.py`**

Delete all tests that exercise the CRITICAL rollback path (identified in Step 1). Typical names: `test_init_critical_triggers_rollback`, `test_init_rollback_deletes_created_files`, `test_init_rollback_warns_on_delete_failure`, etc.

- [ ] **Step 4: Run full init test suite**

```bash
uv run pytest tests/unit/commands/test_init.py -v
```

Expected: all remaining tests PASS. (The deleted tests no longer exist; surviving tests test other paths.)

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/commands/init.py tests/unit/commands/test_init.py
git commit -m "refactor(init): replace post-apply rollback with warning-only pattern"
```

---

### Task 11: Add `--allow-blocking` flag + validation to `init`

**Files:**
- Modify: `src/gh_manage/commands/init.py`
- Test: `tests/unit/commands/test_init.py` (extend)

- [ ] **Step 1: Write failing validation tests**

Append to `tests/unit/commands/test_init.py`:

```python
def test_init_dry_run_with_allow_blocking_raises_usage_error(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch(
        "gh_manage.commands.init.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(
        main,
        [
            "init",
            str(tmp_path),
            "--profile",
            "python-service",
            "--dry-run",
            "--allow-blocking",
        ],
    )
    assert result.exit_code == 2
    assert "--allow-blocking requires --apply" in (result.stderr or result.output)


def test_init_allow_blocking_without_apply_raises_usage_error(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch(
        "gh_manage.commands.init.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service", "--allow-blocking"],
    )
    assert result.exit_code == 2
    assert "--allow-blocking requires --apply" in (result.stderr or result.output)
```

(If `test_init.py` does not yet import `MockerFixture` / `patch` / `main`, add the imports at the top matching `test_apply.py`.)

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/unit/commands/test_init.py -k "allow_blocking" -v
```

Expected: FAIL with `Usage error: no such option: --allow-blocking`.

- [ ] **Step 3: Add flag + parameter + validation in `init.py`**

Add the click option below existing `@click.option("--force", ...)`:

```python
@click.option(
    "--allow-blocking",
    is_flag=True,
    help=(
        "Bypass the pre-apply doctor block gate. Use only when a "
        "blocking finding is known and intentional — emits a loud "
        "WARNING to stderr. Requires --apply."
    ),
)
```

Add parameter to the function signature:

```python
def init(
    path: Path,
    profile_name: str,
    dry_run: bool,
    apply_flag: bool,
    force: bool,
    allow_blocking: bool,
) -> None:
```

Add validation after the existing mutex check:

```python
    if apply_flag and dry_run:
        raise click.UsageError("--apply and --dry-run are mutually exclusive.")

    if allow_blocking and not apply_flag:
        raise click.UsageError(
            "--allow-blocking requires --apply; it has no effect in dry-run mode."
        )
```

- [ ] **Step 4: Run tests — validation should pass; existing init tests should still pass**

```bash
uv run pytest tests/unit/commands/test_init.py -v
```

Expected: all PASS (validation tests + everything else).

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/commands/init.py tests/unit/commands/test_init.py
git commit -m "feat(init): add --allow-blocking flag with UsageError validation"
```

---

### Task 12: Wire pre-apply doctor into `init`

**Files:**
- Modify: `src/gh_manage/commands/init.py`
- Test: `tests/unit/commands/test_init.py` (extend)

- [ ] **Step 1: Write failing tests — pre-apply behavior**

Append to `tests/unit/commands/test_init.py`:

```python
def test_init_first_time_adoption_succeeds(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Profile declares required_contexts; live protection is empty →
    shape/required-contexts-match HIGH is filtered by sync_protection=True
    scope (init always sets sync_protection when profile has policy)."""
    from gh_manage.doctor import checks  # noqa: F401

    mocker.patch(
        "gh_manage.commands.init.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    mocker.patch(
        "gh_manage.commands.init.labels_api.list_labels", return_value=[]
    )
    mocker.patch(
        "gh_manage.commands.init.protection_api.get_branch_protection",
        return_value={},
    )
    mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path",
        return_value=(
            Finding(
                severity="high",
                check="shape/required-contexts-match",
                repo="yakkuro/example",
                field_path="x",
                current_value=None,
                desired_value=None,
                message="m",
            ),
        ),
    )
    runner = CliRunner(mix_stderr=False)
    with (
        patch(
            "gh_manage.commands.init.profile_sync.apply_files_diff", return_value=[]
        ),
        patch("gh_manage.commands.init.labels_sync.apply_diff"),
        patch(
            "gh_manage.commands.init.protection_sync.apply_protection_diff",
        ),
    ):
        result = runner.invoke(
            main,
            ["init", str(tmp_path), "--profile", "python-service", "--apply"],
        )
    assert result.exit_code == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_init_blocks_on_unfiltered_blocking_finding(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Inject a finding whose resolves_with is NOT covered by init's scope."""
    from gh_manage.doctor import registry
    from gh_manage.doctor.context import CheckContext
    from gh_manage.findings import Finding

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        # Register a throwaway check that produces a HIGH finding
        # resolvable only by sync_labels=False (i.e., never filtered
        # since init sync_labels=True; we instead key off an unknown
        # domain to ensure non-coverage).
        @registry.register_check(
            "shape/test-blocks-init", resolves_with=("sync_unknown_domain",)
        )
        def _c(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        mocker.patch(
            "gh_manage.commands.init.git_cli.get_origin_owner_repo",
            return_value="yakkuro/example",
        )
        mocker.patch(
            "gh_manage.commands.init.labels_api.list_labels", return_value=[]
        )
        mocker.patch(
            "gh_manage.commands._shared.doctor.run_on_path",
            return_value=(
                Finding(
                    severity="high",
                    check="shape/test-blocks-init",
                    repo="yakkuro/example",
                    field_path="x",
                    current_value=None,
                    desired_value=None,
                    message="unfilterable",
                ),
            ),
        )
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(
            main,
            ["init", str(tmp_path), "--profile", "python-service", "--apply"],
        )
        assert result.exit_code == 1
        assert "Pre-apply doctor" in (result.output or result.stderr or "")
    finally:
        registry._CHECKS[:] = before


def test_init_allow_blocking_bypasses(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    from gh_manage.doctor import registry
    from gh_manage.doctor.context import CheckContext
    from gh_manage.findings import Finding

    before = list(registry._CHECKS)
    try:
        registry._CHECKS.clear()

        @registry.register_check(
            "shape/test-blocks-init-v2", resolves_with=("sync_unknown",)
        )
        def _c(ctx: CheckContext) -> tuple[Finding, ...]:
            return ()

        mocker.patch(
            "gh_manage.commands.init.git_cli.get_origin_owner_repo",
            return_value="yakkuro/example",
        )
        mocker.patch(
            "gh_manage.commands.init.labels_api.list_labels", return_value=[]
        )
        mocker.patch(
            "gh_manage.commands.init.protection_api.get_branch_protection",
            return_value={},
        )
        mocker.patch(
            "gh_manage.commands._shared.doctor.run_on_path",
            return_value=(
                Finding(
                    severity="high",
                    check="shape/test-blocks-init-v2",
                    repo="yakkuro/example",
                    field_path="x",
                    current_value=None,
                    desired_value=None,
                    message="unfilterable",
                ),
            ),
        )
        runner = CliRunner(mix_stderr=False)
        with (
            patch(
                "gh_manage.commands.init.profile_sync.apply_files_diff",
                return_value=[],
            ),
            patch("gh_manage.commands.init.labels_sync.apply_diff"),
            patch(
                "gh_manage.commands.init.protection_sync.apply_protection_diff",
            ),
        ):
            result = runner.invoke(
                main,
                [
                    "init",
                    str(tmp_path),
                    "--profile",
                    "python-service",
                    "--apply",
                    "--allow-blocking",
                ],
            )
        assert result.exit_code == 0, (
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "--allow-blocking" in (result.stderr or "")
    finally:
        registry._CHECKS[:] = before


def test_init_dry_run_skips_pre_apply_doctor(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch(
        "gh_manage.commands.init.git_cli.get_origin_owner_repo",
        return_value="yakkuro/example",
    )
    mocker.patch(
        "gh_manage.commands.init.labels_api.list_labels", return_value=[]
    )
    run_on_path_mock = mocker.patch(
        "gh_manage.commands._shared.doctor.run_on_path"
    )
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(
        main,
        ["init", str(tmp_path), "--profile", "python-service", "--dry-run"],
    )
    assert result.exit_code == 0
    run_on_path_mock.assert_not_called()
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/unit/commands/test_init.py -k "first_time or blocks_on_unfiltered or allow_blocking_bypasses or dry_run_skips" -v
```

Expected: most FAIL (pre-apply not yet wired).

- [ ] **Step 3: Wire pre-apply doctor into `init`**

In `src/gh_manage/commands/init.py`, locate this existing block near the dry-run early-return:

```python
    if not apply_flag:
        n_protection = len(protection_diff.changes) if protection_diff else 0
        click.echo(
            f"\nDry-run: {len(files_diff.creates) + len(files_diff.overwrites)} "
            f"file changes, {labels_diff.total_changes} label changes, "
            f"{n_protection} protection changes. "
            f"Re-run with --apply to execute."
        )
        return

    # Pre-apply validation: fail fast on protection downgrade BEFORE any
    # side-effect ...
    if (
        protection_diff is not None
        and not protection_diff.is_empty
        and protection_diff.has_downgrades
    ):
        raise click.ClickException(...)
```

Insert the pre-apply doctor call **between** the `return` at the end of the dry-run branch and the downgrade check:

```python
    if not apply_flag:
        ...
        return

    # NEW — Pre-apply doctor gate (spec §3)
    from gh_manage.commands._shared import run_pre_apply_doctor
    from gh_manage.doctor.semantic_filter import ApplyScope

    scope = ApplyScope(
        sync_files=True,
        sync_labels=True,
        sync_protection=(profile.protection_policy is not None),
    )
    run_pre_apply_doctor(
        target,
        profile_name=profile_name,
        scope=scope,
        allow_blocking=allow_blocking,
    )
    # END NEW

    # Pre-apply validation: fail fast on protection downgrade ...
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/commands/test_init.py -v
```

Expected: all PASS, including the 4 new tests.

- [ ] **Step 5: Commit**

```bash
git add src/gh_manage/commands/init.py tests/unit/commands/test_init.py
git commit -m "feat(init): wire pre-apply doctor gate before mutations"
```

---

## Phase 6 — Release preparation

### Task 13: Update `docs/versioning.md` with cli/v1.10.0 entry

**Files:**
- Modify: `docs/versioning.md`

- [ ] **Step 1: Read existing versioning doc**

```bash
head -50 docs/versioning.md
```

Note the entry format used for previous CLI releases (e.g., cli/v1.9.0).

- [ ] **Step 2: Add cli/v1.10.0 entry**

Add a new entry at the top of the CLI version history table (or per-version bullet list, whichever format the existing file uses). Use this content:

```markdown
### cli/v1.10.0 (2026-04-22 — planned)

- **Prevention-layer guardrails (Theme B)**: `init --apply` and `apply --apply` now run the doctor framework before mutating any repository state. Findings whose resolving domain (sync_files / sync_labels / sync_protection) is NOT covered by the current invocation cause a `ClickException` with zero side-effects.
- Added `--allow-blocking` flag to `init` and `apply` as an explicit override.
- Removed `init`'s post-apply CRITICAL rollback; superseded by the pre-apply gate.
- Added regression test for bundled ci.yml template canonical shape.
- Spec: `docs/specs/2026-04-22-theme-b-guardrails-prevention-layer-design.md`
```

- [ ] **Step 3: Run a quick syntax check on the updated file**

```bash
uv run python -c "print(open('docs/versioning.md').read()[:200])"
```

(Or open the file to confirm it reads cleanly.)

- [ ] **Step 4: Commit**

```bash
git add docs/versioning.md
git commit -m "docs: versioning.md — cli/v1.10.0 entry"
```

---

### Task 14: Draft release notes

**Files:**
- Create: `docs/release-notes/cli-v1.10.0.md` (NEW) — or use the body directly in the GitHub Release; this file is the source of truth

- [ ] **Step 1: Check whether a release-notes directory exists**

```bash
ls docs/release-notes/ 2>/dev/null || ls docs/ | grep -i "release\|notes"
```

If `docs/release-notes/` does not exist, create it:

```bash
mkdir -p docs/release-notes
```

- [ ] **Step 2: Write the release notes file**

Create `docs/release-notes/cli-v1.10.0.md`:

```markdown
# cli/v1.10.0 — Prevention-layer guardrails (Theme B)

## Breaking-ish behavior change

`gh-manage init --apply` and `gh-manage apply --apply` now run the
doctor framework before mutating any repository state. If any
`critical` or `high` severity finding remains after the semantic
filter (which drops findings the current invocation is about to
resolve), the command aborts with exit code 1 and zero side-effects.

To proceed past the new gate when the finding is known and
intentional, pass `--allow-blocking`.

## What changed

- Added `--allow-blocking` flag to `init` and `apply`.
- Pre-apply doctor integration in both commands.
- `init`'s post-apply CRITICAL rollback removed — pre-apply gate
  subsumes its guarantee.
- New regression test that bundled `ci/*.yml` templates preserve
  `jobs.pr-gate: { name: "PR Gate" }`.

## Migration

If your CI runs `gh-manage apply --apply` and starts failing after
this release:

1. Run `gh-manage doctor <path> --profile <name>` to see the
   blocking findings.
2. Apply the suggested `Fix:` remediation, OR
3. If intentional (rare), re-run `apply` with `--allow-blocking`.

## Non-changes

- Reusable workflow YAML unchanged.
- Drift scanner behavior unchanged.
- Doctor standalone command unchanged.

## References

- Spec: `docs/specs/2026-04-22-theme-b-guardrails-prevention-layer-design.md`
- Plan: `docs/plans/2026-04-22-theme-b-guardrails-plan.md`
- Closes Theme B prevention half of #48 (linter half deferred to cli/v1.11)
```

- [ ] **Step 3: Commit**

```bash
git add docs/release-notes/cli-v1.10.0.md
git commit -m "docs: draft release notes for cli/v1.10.0"
```

---

### Task 15: Pre-release doctor sweep (operational verification, not code)

**Files:** (none modified; produces a log to attach to the PR)

- [ ] **Step 1: Run `gh-manage doctor` against all 22 consumer repos**

```bash
uv run gh-manage drift --all --report-mode json 2>&1 > /tmp/v1.10-preflight.json
```

(We reuse `drift --all` as a proxy because `doctor --all` is not implemented; the shape findings in drift's JSON output reflect what pre-apply would see.)

- [ ] **Step 2: Summarize expected blocks**

Run this analysis script:

```bash
uv run python -c "
import json, re, sys
text = open('/tmp/v1.10-preflight.json').read()
dec = json.JSONDecoder()
i = 0
results = []
while i < len(text):
    while i < len(text) and text[i] != '{':
        i += 1
    if i >= len(text):
        break
    try:
        obj, end = dec.raw_decode(text, i)
        if 'repo' in obj and 'findings' in obj:
            results.append(obj)
        i = end
    except Exception:
        i += 1
print(f'Scanned {len(results)} repos')
for r in results:
    shape_blocking = [
        f for f in r['findings']
        if f['check'].startswith('shape/') and f['severity'] in ('critical', 'high')
    ]
    if shape_blocking:
        print(f\"  {r['repo']:30} shape-blocking={len(shape_blocking)}\")
        for f in shape_blocking:
            print(f\"    [{f['severity'].upper()}] {f['check']}\")
"
```

Expected output: list of repos where future `apply` will block without `--allow-blocking`. Compare against the known Track B 8 repos from #75. If new repos appear, file a follow-up issue (not a blocker for this release).

- [ ] **Step 3: Record findings in the PR description**

Add a markdown table to the PR description summarizing which repos will fail a default `gh-manage apply --apply` after v1.10 ships, so operators know what to expect.

No commit needed for this task — output is attached to the PR.

---

## Phase 7 — Release

### Task 16: Create pull request

- [ ] **Step 1: Verify all tests pass, lint clean, types clean**

```bash
uv run pytest
uvx ruff@0.8.0 format --check src/ tests/
uvx ruff@0.8.0 check src/ tests/
uv run mypy src/
```

Expected: all green. If any fails, fix before proceeding.

- [ ] **Step 2: Verify git status is clean**

```bash
git status
git log --oneline main..HEAD
```

Review the commit history for completeness.

- [ ] **Step 3: Push branch**

```bash
git push -u origin HEAD
```

- [ ] **Step 4: Create PR**

```bash
gh pr create --title "feat: Theme B guardrails prevention layer (cli/v1.10.0)" --body "$(cat <<'EOF'
## Summary

Implements Theme B (#48) prevention-layer guardrails for `cli/v1.10.0`. `init --apply` and `apply --apply` now run a pre-apply doctor gate that blocks on unfiltered critical/high findings. Closes the #46-class admin-merge gap.

## Scope

Bundle 1 from brainstorming (2026-04-22):
- init template hardening (canonical shape regression test)
- apply precondition (pre-apply doctor gate)
- CLI-only changes; no reusable workflow YAML changes

## Design

- Spec: `docs/specs/2026-04-22-theme-b-guardrails-prevention-layer-design.md`
- Plan: `docs/plans/2026-04-22-theme-b-guardrails-plan.md`

## New behavior summary

| Command | Old | New |
|---|---|---|
| `init --apply` | Post-apply CRITICAL rollback; other severities warning | Pre-apply filter + block on crit+high; post-apply warning-only |
| `apply --apply` | Post-apply warning-only for crit+high | Pre-apply filter + block on crit+high; post-apply warning unchanged |
| `doctor` | Standalone, unchanged | Unchanged |

Override: `--allow-blocking` flag on init and apply. `--dry-run + --allow-blocking` raises `UsageError`.

## Test plan

- [x] Unit tests for `semantic_filter.py` (9 tests, all ApplyScope × resolves_with combos)
- [x] Unit tests for registry per-check isolation (4 tests)
- [x] Unit tests for `get_check_resolves_with` (4 tests including synthetic prefix strip)
- [x] Unit tests for `run_pre_apply_doctor` helper (7 tests)
- [x] Extended tests for `apply` (pre-apply block / filter / override / heal)
- [x] Replaced `init` rollback tests with pre-apply equivalents
- [x] Template invariance regression test for bundled ci.yml files
- [x] Pre-release sweep of 22 consumer repos — documented expected block sites in this PR (see comment below)

## Pre-release sweep

[Attach results from Task 15]

Closes Theme B prevention half of #48. Linter half deferred to cli/v1.11.
Ref #75 (Track B workflow dependency).
EOF
)"
```

- [ ] **Step 5: Record PR URL**

Note the returned PR URL for the 4-agent review in Task 17.

---

### Task 17: 4-agent PR review per `workflow-review.md`

**All 4 reviewers MUST complete before merge.**

- [ ] **Step 1: Compute diff size to pick code-reviewer model**

```bash
git diff main..HEAD --stat | tail -1
```

- [ ] **Step 2: Run 4 reviewers in parallel (single message, multiple Agent tool uses)**

Dispatch in one message:

- `Agent(subagent_type="superpowers:code-reviewer", prompt="Review PR #<N> against spec docs/specs/2026-04-22-theme-b-guardrails-prevention-layer-design.md and plan docs/plans/2026-04-22-theme-b-guardrails-plan.md. Check spec compliance, plan compliance, scope creep. git diff main..HEAD.")`
- `Agent(subagent_type="pr-review-toolkit:silent-failure-hunter", prompt="Review PR #<N> for silent failures, swallowed exceptions, inadequate error handling. git diff main..HEAD.")`
- `Agent(subagent_type="code-reviewer", model=<haiku|sonnet|opus based on diff size>, prompt="Review PR #<N> for project conventions compliance, code quality. CLAUDE.md is project-level context. git diff main..HEAD.")`
- `Bash("bash scripts/codex-review-resilient.sh 'Review PR #<N> on gh-manage repo for correctness, edge cases, and integration soundness. Spec and plan linked in PR description.'")`

- [ ] **Step 3: Address CRITICAL/HIGH findings**

For each reviewer's CRITICAL/HIGH finding: fix → commit → push. Cycle until all 4 return clean (CRITICAL/HIGH = 0) or findings are rejected with documented rationale (false positives).

- [ ] **Step 4: Merge PR after all reviews clean + CI green**

```bash
gh pr checks <PR-number> --watch
gh pr merge <PR-number> --squash --delete-branch
```

- [ ] **Step 5: Tag cli/v1.10.0 release**

```bash
git checkout main
git pull
git tag -a cli/v1.10.0 -m "cli/v1.10.0 — Theme B prevention-layer guardrails"
git push origin cli/v1.10.0
```

- [ ] **Step 6: Create GitHub Release**

```bash
gh release create cli/v1.10.0 \
  --title "cli/v1.10.0 — Theme B prevention-layer guardrails" \
  --notes-file docs/release-notes/cli-v1.10.0.md
```

- [ ] **Step 7: Post-release observation**

Monitor the next weekly drift-scanner cron run for regressions. Update memory if new learnings surface.

---

## Self-Review Checklist

Before handing off to execution:

- [ ] **Spec coverage**: Every AC in spec §10 maps to a task above?
  - AC "`uv run pytest` green" → Task 16 Step 1
  - AC "`uvx ruff@0.8.0 format --check` passes" → Task 16 Step 1
  - AC "`uv run mypy src/` passes" → Task 16 Step 1
  - AC "fresh-repo first-time adoption works" → Task 12 tests
  - AC "apply with mismatched context blocks; --allow-blocking proceeds" → Task 9 tests
  - AC "Track B pre-existing repo blocks as expected" → Task 15 sweep
  - AC "template regression test passes" → Task 6
  - AC "init rollback code deleted" → Task 10
  - AC "release notes published" → Task 14 + Task 17 Step 6
  - AC "4-agent PR review clean" → Task 17

- [ ] **Placeholder scan**: Every task has complete code (no "TODO", "similar to Task N", "implement later")? ✓ verified

- [ ] **Type consistency**: `ApplyScope(sync_files, sync_labels, sync_protection)` signature consistent across Tasks 5, 9, 12? ✓

- [ ] **Import consistency**: `from gh_manage.commands._shared import run_pre_apply_doctor` and `from gh_manage.doctor.semantic_filter import ApplyScope` used identically in Tasks 9 and 12? ✓

- [ ] **Commit message discipline**: each task commits once; conventional commits (`feat:`, `refactor:`, `test:`, `docs:`) used consistently? ✓

- [ ] **TDD order**: Red (failing test) → Green (minimal impl) → Commit in every code task? ✓ (Task 6 is Green-first because it's a regression gate on existing correct code — explicitly called out in Step 3 "verify failure mode with temporary corruption")
