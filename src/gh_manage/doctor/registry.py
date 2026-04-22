"""Doctor check registry.

Deliberately parallel to drift_sync.py's _CHECKS registry rather than
sharing a single global. This keeps drift's check lifecycle (labels /
protection / profile_files) decoupled from doctor's shape/* checks.

register_check is a decorator factory: @register_check("shape/foo")
attaches the name to the function for later name-based filtering.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from itertools import chain
from typing import TypeVar

from gh_manage.doctor.context import CheckContext
from gh_manage.doctor.errors import CiYmlParseError, DoctorCheckError, DoctorError
from gh_manage.findings import Finding

log = logging.getLogger(__name__)

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
