"""Bridge drift scanner <-> doctor.

drift_sync's register_check wants `(ScanContext) -> tuple[Finding, ...]`.
doctor's run_checks wants `CheckContext`. This bridge is the adapter.

Error semantics (spec §4):
- DoctorCheckError from doctor is caught and converted into a single
  medium-severity `shape/check-error` finding. Keeps a per-repo scan
  failure from aborting a multi-repo drift scan.
- Any other exception propagates — it's a bug, and drift's caller
  already has a clear-traceback mode.
"""

from __future__ import annotations

from gh_manage.doctor.context import CheckContext
from gh_manage.doctor.errors import DoctorCheckError
from gh_manage.doctor.registry import run_checks as doctor_run_checks
from gh_manage.drift_sync import ScanContext, register_check
from gh_manage.findings import Finding


def _build_check_context(ctx: ScanContext) -> CheckContext:
    """Adapt a ScanContext to a doctor CheckContext."""
    ci_path = ctx.path / ".github" / "workflows" / "ci.yml"
    try:
        ci_text = ci_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        ci_text = ""

    profile_name = getattr(ctx.profile, "name", "unknown") if ctx.profile else "unknown"
    profile_required = (
        tuple(getattr(ctx.profile, "required_contexts", ()) or ())
        if ctx.profile
        else ()
    )

    return CheckContext(
        repo=ctx.repo,
        ci_yml_text=ci_text,
        profile_name=profile_name,
        required_contexts=ctx.live_required_contexts,
        profile_required_contexts=profile_required,
        source_hint=f"scan:{ctx.repo}",
    )


@register_check
def check_shape(ctx: ScanContext) -> tuple[Finding, ...]:
    """Drift check that delegates to doctor's shape/* checks."""
    try:
        doctor_ctx = _build_check_context(ctx)
        return doctor_run_checks(doctor_ctx)
    except DoctorCheckError as e:
        return (
            Finding(
                severity="medium",
                check="shape/check-error",
                repo=ctx.repo,
                field_path="doctor:bridge",
                current_value=None,
                desired_value=None,
                message=f"doctor check failed: {e}",
                remediation="Re-run `gh-manage doctor <repo>` for detail.",
            ),
        )
