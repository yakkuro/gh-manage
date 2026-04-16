# Phase 10 Tier List — 2026-04-16 (corrected)

## Summary

Scanned 23 candidate Python repos. Corrected per spec rules:
- `install-command` override → Tier 2 (not 1.5)
- Auto-fixable ruff violations (I001, F841) → Tier 1 (ruff --fix resolves)

| Tier | Count | Repos |
|---|---|---|
| Tier 1 | 6 | shorts-factory, polyagent, multi-agents, polytrader, voice-works, shelf-brain |
| Tier 1.5 | 1 | port-registry (type-check: false) |
| Tier 2 → salvage (uv.lock gen) | 4 | git-digest, image-ocr, tg-commander, repo-init |
| Tier 2 → salvage (code fix) | 1 | codelens (F821 import fixes) |
| Tier 3 → salvage (add test) | 1 | deep-research (trivial test) |
| Tier 3 (excluded) | 10 | see below |
| **New adoptable total** | **13** | 7 existing + 13 new = **20** |

## Tier 1 — ready (default inputs, ordered by cleanliness score)

| Rank | Repo | uv.lock | src/ | tests | Ruff | Format | Score | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | shorts-factory | Y | Y | 11 | clean | clean | 4.0 | **Canary #1** |
| 2 | polyagent | Y | Y | 12 | clean | clean | 4.0 | **Canary #2** |
| 3 | multi-agents | Y | Y | 3 | clean | clean | 3.3 | |
| 4 | polytrader | Y | Y | ? | 1 F841 auto-fix | clean | 3.0 | reclassified from T2; F841 resolved by --fix |
| 5 | voice-works | Y | Y | ? | I001 auto-fix | clean | 3.0 | reclassified from T2; I001 resolved by --fix |
| 6 | shelf-brain | Y | Y | ? | I001 auto-fix | needs format | 2.0 | reclassified from T2; auto-fix + format |

## Tier 1.5 — ready with one whitelisted override

| Rank | Repo | Override | uv.lock | src/ | tests | Score | Notes |
|---|---|---|---|---|---|---|---|
| 1 | port-registry | `type-check: false` | Y | N | 14 | 4.0 | No src/ dir; largest test suite |

## Tier 2 → salvage: uv.lock generation

These repos have pyproject + src/ + tests but no committed uv.lock. Adoption PR includes `uv lock && git add uv.lock` as a pre-step. Default `uv sync` install-command is used (no override needed once lock exists).

| Repo | src/ | tests | Ruff | Notes |
|---|---|---|---|---|
| git-digest | Y | 7 | clean | generate uv.lock in adoption PR |
| image-ocr | Y | 5 | clean | generate uv.lock in adoption PR |
| tg-commander | Y | 3 | clean | generate uv.lock in adoption PR |
| repo-init | Y | 3 | clean | generate uv.lock in adoption PR |

## Tier 2 → salvage: code fix (codelens)

| Repo | Issue | Fix |
|---|---|---|
| codelens | 12 F821 undefined names + 1 F841 | Fix missing imports in src/indexer/cli.py, src/api/server.py, src/mcp/server.py, tests/test_repo_summary.py |

## Tier 3 → salvage: add test (deep-research)

| Repo | Has pyproject | Has uv.lock | Has src/ | Tests | Fix |
|---|---|---|---|---|---|
| deep-research | Y | Y | Y | 0 | Add 1 trivial smoke test (e.g., test imports succeed) |

## Tier 3 — excluded

| Repo | Reason |
|---|---|
| researcher | No pyproject.toml |
| MoneyPrinterV2 | No pyproject.toml |
| claude-insight | No pyproject.toml |
| autodev | No pyproject.toml |
| vaporwave-generator | No pyproject.toml |
| anichat | No pyproject.toml |
| waifuforge | No pyproject.toml |
| vtube | No tests (0 test files) |
| matome | Python 3.11 (requires 3.12) |
| ychat | Python 3.10 (requires 3.12) |

## Adoption order

1. **Canary**: shorts-factory, polyagent (Tier 1 cleanest, scores 4.0)
2. **Batch 1**: multi-agents, polytrader, voice-works, shelf-brain (Tier 1 remaining)
3. **Batch 2**: port-registry (T1.5) + git-digest, image-ocr, tg-commander (T2 salvage, uv.lock gen)
4. **Batch 3**: repo-init (T2 salvage, uv.lock gen) + codelens (T2 code fix) + deep-research (T3 salvage, add test)

## repos.yml profile corrections

- nade-nade: `python-service` → `ts-service` (actually TypeScript) — fixed in Phase 10 setup PR
