# cli/v1.10.0 Pre-Release Preflight Sweep

**Date**: 2026-04-22
**Command**: `gh-manage drift --all --report-mode json`
**Scope**: 22 consumer repos in `src/gh_manage/data/repos.yml`

## Expected `apply --apply` Block Sites After v1.10.0

Repos listed below have `shape/*` blocking (critical/high) findings that
would cause `gh-manage apply --apply` (without `--allow-blocking`) to
abort after cli/v1.10.0 lands. This is the intended behavior: the new
gate surfaces pre-existing integrity issues before they mutate state.

### Repos with shape/* blocking findings

- **yakkuro/llm-kb**: [HIGH] shape/required-contexts-match — Profile 'python-service' declares required context 'PR Gate / PR Gate' but branch protection context mismatch
- **yakkuro/nade-nade**: [HIGH] shape/required-contexts-match — Profile 'ts-service' declares required context 'PR Gate / PR Gate' but branch protection context mismatch
- **yakkuro/picshop**: [HIGH] shape/required-contexts-match — Profile 'python-service' declares required context 'PR Gate / PR Gate' but branch protection context mismatch
- **yakkuro/rtvc-bench**: [HIGH] shape/required-contexts-match — Profile 'python-service' declares required context 'PR Gate / PR Gate' but branch protection context mismatch
- **yakkuro/scenario-engine**: [HIGH] shape/required-contexts-match — Profile 'python-service' declares required context 'PR Gate / PR Gate' but branch protection context mismatch
- **yakkuro/slack-agents**: [HIGH] shape/required-contexts-match — Profile 'python-service' declares required context 'PR Gate / PR Gate' but branch protection context mismatch
- **yakkuro/tts**: [HIGH] shape/required-contexts-match — Profile 'python-service' declares required context 'PR Gate / PR Gate' but branch protection context mismatch
- **yakkuro/vox-speak**: [HIGH] shape/required-contexts-match — Profile 'python-service' declares required context 'PR Gate / PR Gate' but branch protection context mismatch

**Count**: 8 repos with blocking findings. Remaining 14 repos have OK status.

## Interpretation

- **Expected**: the 8 Track B repos from #75 will appear here (profile says `python-service` or `ts-service` but they have bespoke CI with no reusable-pr-gate). Pre-apply sees `shape/required-contexts-match` HIGH (sync_protection=False for default apply without --also-protection).
- **Not expected**: additional repos outside Track B. The preflight shows zero surprises.

## Mitigation

Operators running `apply --apply` on these repos after v1.10.0 should either:

1. Run `gh-manage doctor <repo> --profile <name>` to see the blocking findings
2. Fix the declared profile (e.g., switch to a drift-only profile per #75)
3. Use `--allow-blocking` with documented rationale

## Summary

✓ All 22 repos scanned successfully.
✓ 8 repos blocked (exactly Track B scope).
✓ 14 repos OK (no blocking findings).
✓ Zero unexpected repos in the block list.

The new pre-apply gate is ready for release.
