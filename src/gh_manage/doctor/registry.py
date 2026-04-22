"""Doctor check registry.

Deliberately parallel to drift_sync.py's _CHECKS registry rather than
sharing a single global. This keeps drift's check lifecycle (labels /
protection / profile_files) decoupled from doctor's shape/* checks.

register_check is a decorator factory: @register_check("shape/foo")
attaches the name to the function for later name-based filtering.
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import chain
from typing import TypeVar

from gh_manage.doctor.context import CheckContext
from gh_manage.doctor.errors import DoctorError
from gh_manage.findings import Finding

CheckFn = Callable[[CheckContext], "tuple[Finding, ...]"]
_F = TypeVar("_F", bound=CheckFn)

_CHECKS: list[CheckFn] = []


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
        original = check_name[len(prefix) :]
        for fn in _CHECKS:
            if getattr(fn, "__doctor_check_name__", None) == original:
                return getattr(fn, "__doctor_resolves_with__", ())
    return ()


def run_checks(ctx: CheckContext) -> tuple[Finding, ...]:
    """Run every registered check in registration order."""
    return tuple(chain.from_iterable(fn(ctx) for fn in _CHECKS))


def run_named_checks(ctx: CheckContext, names: tuple[str, ...]) -> tuple[Finding, ...]:
    """Run only the checks whose registered name is in `names`.

    Raises DoctorError if any name is unknown.
    """
    name_set = set(names)
    known = {getattr(fn, "__doctor_check_name__", None) for fn in _CHECKS}
    missing = name_set - known
    if missing:
        raise DoctorError(
            f"Unknown doctor check(s): {sorted(missing)}. "
            f"Known: {sorted(n for n in known if n)}."
        )
    selected = [
        fn for fn in _CHECKS if getattr(fn, "__doctor_check_name__", None) in name_set
    ]
    return tuple(chain.from_iterable(fn(ctx) for fn in selected))
