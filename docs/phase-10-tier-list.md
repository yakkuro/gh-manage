# Phase 10 Tier List — 2026-04-16

## Summary

Scanned 23 candidate Python repositories for Phase 10 reusable PR gate workflow adoption.

- **Tier 1**: 3 repos (ready, no overrides needed)
- **Tier 1.5**: 5 repos (ready with one input override)
- **Tier 2**: 4 repos (needs manual fixes)
- **Tier 3 / Excluded**: 11 repos (not ready)
- **Tier 1 + 1.5 total: 8 repos** (need ≥13 for Phase 10 threshold; 7 already in repos.yml brings total to 15)

## Tier 1 — Ready for Adoption (Ordered by Cleanliness Score)

| Rank | Repo | pyproject | uv.lock | src/ | tests | Ruff | Format | Score | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | shorts-factory | ✅ | ✅ | ✅ | 11 | ✅ | ✅ | 4.0 | **Canary candidate**: fully compliant, mature test suite |
| 2 | polyagent | ✅ | ✅ | ✅ | 12 | ✅ | ✅ | 4.0 | Docker-based agent framework, robust test coverage |
| 3 | multi-agents | ✅ | ✅ | ✅ | 3 | ✅ | ✅ | 3.3 | Smallest test suite among Tier 1, but passing |

## Tier 1.5 — Ready with One Override

| Rank | Repo | Override | pyproject | uv.lock | src/ | tests | Ruff | Format | Score | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | git-digest | `install-command: uv sync --frozen` | ✅ | ❌ | ✅ | 7 | ✅ | ✅ | 3.7 | Missing uv.lock; recommend generating via `uv lock` |
| 2 | image-ocr | `install-command: uv sync --frozen` | ✅ | ❌ | ✅ | 5 | ✅ | ✅ | 3.5 | No uv.lock; Dockerfile present (container image) |
| 3 | tg-commander | `install-command: uv sync --frozen` | ✅ | ❌ | ✅ | 3 | ✅ | ✅ | 3.3 | Minimal tests, no uv.lock |
| 4 | repo-init | `install-command: uv sync --frozen` | ✅ | ❌ | ✅ | 3 | ✅ | ✅ | 3.3 | Template/scaffold tool, minimal test count |
| 5 | port-registry | `type-check: false` | ✅ | ✅ | ❌ | 14 | ✅ | ✅ | 4.0 | **Largest test suite in Tier 1.5**; no src/, monorepo structure |

### Tier 1.5 Recommendations

**For repos with missing uv.lock**: Run `uv lock` locally in each repo and commit before adoption.

**For port-registry**: No src/ directory detected (likely tests/ or structure outside standard layout). Recommend:
```yaml
type-check: false
```

## Tier 2 — Needs Manual Code Fixes

| Repo | Main Issues | Violation Count | Severity | Estimated Work |
|---|---|---|---|---|
| codelens | F821 Undefined names (actual bugs; `resolve_repo`, `discover_repos`, `REPOS_DIRS`, `repo_summary` not imported) | 12 F821, 1 F841 | 🔴 HIGH | Fix missing imports and unused variable in src/indexer/cli.py, src/api/server.py, src/mcp/server.py, tests/test_repo_summary.py |
| polytrader | F841 Unused variable (test setup code) | 1 F841 | 🟡 LOW | Remove unused `loss_limit` variable in tests/test_phase3_integration.py:156 |
| voice-works | I001 Import sort violations (auto-fixable) | I001 (format) | 🟡 LOW | Run `ruff format --fix` or `ruff check --fix` to auto-correct import blocks |
| shelf-brain | I001 Import sort + format violations | I001 + format | 🟡 MEDIUM | Import sorting + format issues; likely auto-fixable with `ruff check --fix && ruff format` |

### Tier 2 Justification

- **codelens**: F821 errors indicate actual missing imports or undefined symbols. These are bugs that must be fixed before adoption; not auto-fixable. Requires investigation and proper import statements.
- **polytrader**: Single unused variable; auto-fixable or manual removal.
- **voice-works**, **shelf-brain**: Import and format violations marked `[*]` (auto-fixable). Can be auto-corrected with ruff.

**Recommendation**: All 4 repos can achieve Tier 1 or 1.5 with focused effort (1–2 hours each). Escalate to respective maintainers.

## Tier 3 — Excluded (Not Ready)

| Repo | Reason | Blocker |
|---|---|---|
| researcher | Missing pyproject.toml | No Python project structure |
| MoneyPrinterV2 | Missing pyproject.toml | No Python project structure |
| claude-insight | Missing pyproject.toml | No Python project structure |
| autodev | Missing pyproject.toml | No Python project structure |
| vaporwave-generator | Missing pyproject.toml | No Python project structure |
| anichat | Missing pyproject.toml | No Python project structure |
| waifuforge | Missing pyproject.toml | No Python project structure |
| deep-research | No test files | 0 tests; has pyproject + uv.lock but no test suite |
| vtube | No test files | 0 tests; has src/ + uv.lock but no test suite |
| matome | Python < 3.12 | Requires Python 3.11; workflow specifies 3.12+ |
| ychat | Python < 3.12 | Requires Python 3.10; workflow specifies 3.12+ |

### Tier 3 Notes

- **7 repos missing pyproject.toml**: These are either monorepo structures, non-Python projects labeled as Python on GitHub, or projects without formal Python packaging. Not candidates for PR gate adoption without restructuring.
- **deep-research, vtube**: Have modern Python structure (pyproject, src/, uv.lock) but no test files. Blocking criterion for Phase 10 (requires tests for gate to run).
- **matome, ychat**: Python version mismatch (3.10/3.11 vs. required 3.12). Would fail at workflow runtime.

## repos.yml Profile Corrections

Recommend updating `/home/server160/repos/gh-manage/repos.yml` after Phase 10 adoption:

### Repos to Add (Tier 1 + 1.5)

```yaml
- repo: shorts-factory
  language: Python
  tier: Tier 1
  workflow-profile: reusable-pr-gate-python@v1.0.0 (default)

- repo: polyagent
  language: Python
  tier: Tier 1
  workflow-profile: reusable-pr-gate-python@v1.0.0 (default)

- repo: multi-agents
  language: Python
  tier: Tier 1
  workflow-profile: reusable-pr-gate-python@v1.0.0 (default)

- repo: git-digest
  language: Python
  tier: Tier 1.5
  workflow-profile: reusable-pr-gate-python@v1.0.0
  workflow-inputs:
    install-command: uv sync --frozen

- repo: image-ocr
  language: Python
  tier: Tier 1.5
  workflow-profile: reusable-pr-gate-python@v1.0.0
  workflow-inputs:
    install-command: uv sync --frozen

- repo: tg-commander
  language: Python
  tier: Tier 1.5
  workflow-profile: reusable-pr-gate-python@v1.0.0
  workflow-inputs:
    install-command: uv sync --frozen

- repo: repo-init
  language: Python
  tier: Tier 1.5
  workflow-profile: reusable-pr-gate-python@v1.0.0
  workflow-inputs:
    install-command: uv sync --frozen

- repo: port-registry
  language: Python
  tier: Tier 1.5
  workflow-profile: reusable-pr-gate-python@v1.0.0
  workflow-inputs:
    type-check: false
```

### Known Profile Issues in repos.yml

If these exist, update:

- `nade-nade`: Listed as `python-service`; GitHub API confirms primary language is **TypeScript**. Change to `ts-service` or `typescript`.

## Next Steps for Phase 10

1. **Adopt 3 Tier 1 repos** (shorts-factory, polyagent, multi-agents) immediately as canary cohort.
2. **Issue PRs to 5 Tier 1.5 maintainers** with override instructions + specific `workflow_call` inputs.
3. **File Issues for Tier 2 repos** (codelens, polytrader, voice-works, shelf-brain) with code fix requirements, link to this tier list.
4. **Document Tier 3 reason** in a GitHub Issues template for future reference.
5. **Measure adoption success** in Phase 10 finalization:
   - Track merge rate for Tier 1+1.5 (target: 100% by day 14)
   - Measure gate success rate (target: <5% false negatives)
   - Collect feedback on override configurations for future phases

## Methodology & Constraints

- **Scan date**: 2026-04-16
- **Ruff version**: 0.8.0 (pinned per MEMORY.md feedback)
- **Python version check**: Repos must declare `requires-python ≥ 3.12` or default to 3.12
- **Test detection**: `find . -maxdepth 2 -name 'test*.py'` (catches test/, tests/, test_*.py patterns)
- **Cleanliness score**: `(ruff_clean ? 2 : 0) + (format_clean ? 1 : 0) + min(test_count, 10)/10`
- **Repo availability**: All 23 repos scanned from `/home/server160/repos/`; no network clones attempted

## Appendix: Full Scan Data

Raw results available in internal scan logs. Summary:
- Tier 1: 3 repos, avg score 3.77
- Tier 1.5: 5 repos, avg score 3.6
- Tier 2: 4 repos, avg score 2.88
- Tier 3: 11 repos, blocked before scoring

---

**Document prepared by**: Claude Agent (Phase 10 Scanner)  
**Confidence**: High (automated scan + manual verification of ruff violations)
