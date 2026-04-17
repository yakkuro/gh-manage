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


def register_check(name: str) -> Callable[[_F], _F]:
    """Decorator factory: register a check under `name`."""

    def _decorator(fn: _F) -> _F:
        fn.__doctor_check_name__ = name  # type: ignore[attr-defined]
        _CHECKS.append(fn)
        return fn

    return _decorator


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
