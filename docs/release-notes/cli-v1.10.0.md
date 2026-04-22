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
