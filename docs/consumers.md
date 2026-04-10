# Consumers

This page lists the repositories that have adopted gh-manage's reusable workflows, in chronological order. Each entry records:

- The consumer repo
- The gh-manage version used at adoption
- Any consumer-side prep required (code fixes, config changes)
- Discoveries surfaced by the integration

## yakkuro/llm-kb — first external consumer (2026-04-10)

- **Repo**: [yakkuro/llm-kb](https://github.com/yakkuro/llm-kb) — LLM-powered personal knowledge base (Python 3.12, FastAPI + typer + uv)
- **Adopted**: 2026-04-10 in [PR #14](https://github.com/yakkuro/llm-kb/pull/14)
- **gh-manage version**: `v0.2.1`
- **Reusable workflow**: `reusable-pr-gate-python.yml`
- **Phase**: This was the **Phase 3** validation milestone — first cross-repo invocation of any gh-manage reusable workflow.

### Consumer-side `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  pr-gate:
    uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v0.2.1
    with:
      python-version: "3.12"
      install-command: "uv sync --extra dev"
      gh-manage-ref: "v0.2.1"
```

Two non-default inputs:
- **`install-command: "uv sync --extra dev"`** — llm-kb uses PEP 621 `[project.optional-dependencies]` for its dev dependencies (pytest, pytest-asyncio, httpx). The reusable's default `uv sync` would skip these. Override to `uv sync --extra dev`.
- **`gh-manage-ref: "v0.2.1"`** — required since v0.2.1 (see `docs/usage/python.md` for the rationale). Must match the `@<ref>` on the `uses:` line.

### Consumer-side prep work

The gh-manage gate is stricter than llm-kb's previous CI (which only ran pytest). To pass the full gate, the adoption PR included three prep commits:

1. **`test: satisfy ruff 0.8.0 (F841 unused locals, E402 import order)`** — fixed 16 F841 + 2 E402 violations in `tests/`. All mechanical: dropped unused bindings (`db = Database(db_path)` → `Database(db_path)`, `arts = _seed_articles(...)` → `_seed_articles(...)`, etc.) and hoisted out-of-place imports in `test_llm.py`.
2. **`chore: configure mypy to pass gh-manage type-check gate`** — added `[tool.mypy] ignore_missing_imports = true` to `pyproject.toml` (suppressed 106 `import-untyped` errors from `src/{kb,server,cli}` packages without `py.typed` markers and a few stubless third-party deps). Plus one `# type: ignore[attr-defined]` on `pymupdf.Document` iteration in `src/kb/ingest/pdf.py`.
3. **`ci: adopt yakkuro/gh-manage@v0.2.0 reusable Python PR gate`** — replaced the existing minimal CI with the gh-manage reusable.

### Discoveries surfaced by Phase 3

The Phase 3 integration was the first time gh-manage's self-checkout pattern ran in a real cross-repo context. It surfaced **two major issues** that previous same-repo testing had not exposed:

1. **`access_level: none` blocked reusable workflow resolution** — `gh-manage`'s `Settings → Actions → General → Access` defaulted to `none`, preventing other repos in the same user account from even resolving the reusable workflow YAML. Fix: set `access_level: user` via the API:
   ```
   gh api --method PUT repos/yakkuro/gh-manage/actions/permissions/access -f access_level=user
   ```

2. **CRITICAL: self-checkout `git clone` failed because gh-manage was private** — even after `access_level: user`, the consumer's runner could not authenticate to clone gh-manage. The default `GITHUB_TOKEN` of llm-kb's runner has scope only over llm-kb itself, not over private external repos. Fix: switch gh-manage's visibility from private to public. The repo was audited first to scrub local-environment references and unrelated project names (see PR #4), then made public via `gh repo edit yakkuro/gh-manage --visibility public --accept-visibility-change-consequences`.

3. **CRITICAL: self-checkout pattern was fundamentally broken cross-repo** — even after the visibility flip, the workflow failed with `fatal: couldn't find remote ref refs/pull/14/merge`. The reusable workflow was parsing `github.workflow_ref` to determine which gh-manage ref to check out. The assumption was that `github.workflow_ref` reflects the called reusable workflow's ref. **It does not.** GitHub Actions populates `github.workflow_ref` with the **top-level caller's** workflow ref. In same-repo dogfood (Phase 1, Phase 2), the consumer ref happened to coincide with gh-manage's ref, masking the bug. In cross-repo (this Phase 3 test), the parser returned llm-kb's PR merge ref, which gh-manage does not contain.

   Fix shipped in [v0.2.1](https://github.com/yakkuro/gh-manage/releases/tag/v0.2.1): replace the implicit parser with a new required `gh-manage-ref` input. Consumers must pass the same `@<ref>` they used in `uses:`. The duplication is the unavoidable cost of self-referential cross-repo reusable workflows on GitHub Actions, where `uses:` lines do not allow dynamic values and there is no built-in context variable that exposes the called reusable workflow's own ref.

### What was validated

After all three discoveries were addressed, the cross-repo flow worked end-to-end:

- ✅ Consumer (llm-kb) runs `pull_request` event
- ✅ GitHub resolves `yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v0.2.1` (cross-repo workflow lookup)
- ✅ Reusable workflow's first step: checkout consumer (llm-kb) at PR merge SHA
- ✅ Reusable workflow's second step: checkout `yakkuro/gh-manage@v0.2.1` at the explicit `gh-manage-ref` input into `.gh-manage/`
- ✅ Composite actions resolved via `./.gh-manage/actions/<name>`
- ✅ Full pipeline ran: `uv sync --extra dev` → `ruff check` → `ruff format --check` → `mypy src` → `uv run pytest` (280/280 pass)
- ✅ Total wall time: ~1m17s

### Lessons for future consumers

- **Run gh-manage's tools locally before opening the adoption PR.** `uvx ruff@0.8.0 check .`, `uvx ruff@0.8.0 format --check .`, `uv run --with mypy==1.12.0 mypy src`, and the project's existing test command. Fix any failures BEFORE the adoption PR — gh-manage will not lower its bar for consumer-specific issues.
- **PEP 621 vs PEP 735**: if your project uses `[project.optional-dependencies]` for dev deps (instead of PEP 735 `[dependency-groups]`), override `install-command` to add the relevant extras (e.g., `"uv sync --extra dev"`).
- **mypy strict-by-default surprises**: `import-untyped` errors for your own modules (without `py.typed` markers) and for stubless third-party deps will fire. The minimum-friction fix is `[tool.mypy] ignore_missing_imports = true` in `pyproject.toml`. Tighten incrementally by adding `py.typed` markers to your own packages.
- **`gh-manage-ref` is required**: pin it to the same `@<ref>` you use in `uses:`. Mismatching them produces an obvious error at job start.

## Adding your repo

Open a PR against `yakkuro/gh-manage` adding a section to this file describing your adoption. Include the same fields as the llm-kb entry above. PRs that document discoveries (consumer-side prep work, edge cases) are especially valuable — they help future consumers skip the same pitfalls.
