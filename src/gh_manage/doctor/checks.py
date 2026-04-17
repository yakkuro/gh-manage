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
