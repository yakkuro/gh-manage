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
    (empty tuple) is NEVER filtered — `()` is treated as "no declared
    coverage", not as "vacuously covered".

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
