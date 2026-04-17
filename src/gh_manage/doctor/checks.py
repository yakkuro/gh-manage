"""Doctor α checks — spec §3.

Each check reads the CheckContext and returns zero or more Findings.
Checks are pure: they do not perform IO beyond parsing ci_yml_text.
"""

from __future__ import annotations

import re

import yaml

from gh_manage.doctor.context import CheckContext
from gh_manage.doctor.errors import CiYmlParseError
from gh_manage.doctor.registry import register_check
from gh_manage.findings import Finding

# A job is a "reusable-pr-gate job" iff its `uses:` value matches this
# regex. Indirection via another composite workflow is NOT traced.
_REUSABLE_USES_RE = re.compile(
    r"^yakkuro/gh-manage/\.github/workflows/"
    r"reusable-pr-gate-(python|typescript)\.yml@.+$"
)


def _parse_ci_yml(text: str, source_hint: str) -> dict:
    if not text.strip():
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise CiYmlParseError(
            f"Failed to parse ci.yml ({source_hint}) as YAML: {e}"
        ) from e
    if not isinstance(data, dict):
        raise CiYmlParseError(
            f"ci.yml ({source_hint}) top-level must be a mapping, got "
            f"{type(data).__name__}."
        )
    return data


def _iter_reusable_jobs(ci_yml: dict):
    jobs = ci_yml.get("jobs") or {}
    if not isinstance(jobs, dict):
        return
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        uses = job.get("uses")
        if isinstance(uses, str) and _REUSABLE_USES_RE.match(uses):
            yield job_id, job


@register_check("shape/job-shape-coherence")
def check_job_shape_coherence(ctx: CheckContext) -> tuple[Finding, ...]:
    """critical: produced status context must match protection's
    required context. Spec §3 check 1."""
    ci_yml = _parse_ci_yml(ctx.ci_yml_text, ctx.source_hint)
    findings: list[Finding] = []
    required_set = set(ctx.required_contexts)

    for job_id, job in _iter_reusable_jobs(ci_yml):
        display = job.get("name") or job_id
        produced = f"{display} / PR Gate"
        if produced in required_set:
            continue
        findings.append(
            Finding(
                severity="critical",
                check="shape/job-shape-coherence",
                repo=ctx.repo,
                field_path=f".github/workflows/ci.yml:jobs.{job_id}",
                current_value=produced,
                desired_value=sorted(ctx.required_contexts),
                message=(
                    f"Job 'jobs.{job_id}' produces status context "
                    f"{produced!r} but branch protection requires one of "
                    f"{sorted(ctx.required_contexts)!r}."
                ),
                remediation=(
                    "Rename the job id to 'pr-gate' AND set "
                    "'name: \"PR Gate\"', OR update branch protection "
                    f"to require {produced!r}."
                ),
            )
        )

    return tuple(findings)


@register_check("shape/reusable-adoption")
def check_reusable_adoption(ctx: CheckContext) -> tuple[Finding, ...]:
    """medium: flag repos in repos.yml that don't use a reusable-pr-gate.

    Severity is medium because bespoke CI is sometimes intentional
    (e.g., shelf-brain's postgres service requirement). The finding
    makes the choice explicit rather than silent.

    Spec §3 check 2.
    """
    ci_yml = _parse_ci_yml(ctx.ci_yml_text, ctx.source_hint)
    has_reusable = any(True for _ in _iter_reusable_jobs(ci_yml))
    if has_reusable:
        return ()
    if not ctx.ci_yml_text.strip():
        msg = (
            "No .github/workflows/ci.yml found; repo lists in repos.yml "
            f"with profile {ctx.profile_name!r} but uses no reusable "
            "gh-manage workflow."
        )
    else:
        msg = (
            "ci.yml is present but no job uses the reusable-pr-gate "
            f"workflow; profile {ctx.profile_name!r} expects adoption."
        )
    return (
        Finding(
            severity="medium",
            check="shape/reusable-adoption",
            repo=ctx.repo,
            field_path=".github/workflows/ci.yml",
            current_value="bespoke (no reusable-pr-gate-*)",
            desired_value=(
                "uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-*.yml@<ref>"
            ),
            message=msg,
            remediation=(
                "Adopt the reusable workflow, OR remove the repo from "
                "repos.yml if intentionally bespoke."
            ),
        ),
    )


@register_check("shape/required-contexts-match")
def check_required_contexts_match(ctx: CheckContext) -> tuple[Finding, ...]:
    """Diff profile's declared required_contexts vs live protection.

    Missing (profile declares, protection lacks): severity high.
    Extra (protection enforces, profile doesn't declare): severity medium.

    Spec §3 check 3.
    """
    expected = set(ctx.profile_required_contexts)
    actual = set(ctx.required_contexts)
    findings: list[Finding] = []

    for missing in sorted(expected - actual):
        findings.append(
            Finding(
                severity="high",
                check="shape/required-contexts-match",
                repo=ctx.repo,
                field_path=f"branches/*/protection:required_status_checks.contexts[{missing}]",
                current_value=sorted(actual),
                desired_value=sorted(expected),
                message=(
                    f"Profile {ctx.profile_name!r} declares required "
                    f"context {missing!r} but branch protection is not "
                    f"enforcing it. PRs can merge without this gate."
                ),
                remediation=(
                    f"Run `gh-manage protection sync {ctx.repo} "
                    f"--profile {ctx.profile_name} --apply` to enforce."
                ),
            )
        )

    for extra in sorted(actual - expected):
        findings.append(
            Finding(
                severity="medium",
                check="shape/required-contexts-match",
                repo=ctx.repo,
                field_path=f"branches/*/protection:required_status_checks.contexts[{extra}]",
                current_value=sorted(actual),
                desired_value=sorted(expected),
                message=(
                    f"Branch protection requires context {extra!r} but "
                    f"profile {ctx.profile_name!r} does not declare it. "
                    f"Either the profile is incomplete or the protection "
                    f"is carrying a legacy requirement."
                ),
                remediation=(
                    "Add the context to the profile's required_contexts, "
                    "OR drop it from branch protection."
                ),
            )
        )

    return tuple(findings)
