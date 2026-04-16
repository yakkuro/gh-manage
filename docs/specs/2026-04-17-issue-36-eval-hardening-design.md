# Issue #36: Reusable Workflow `eval` Hardening — Design

**Status**: Approved for implementation
**Target release**: reusable track `v1.1.0`
**Author**: yakkuro (brainstorming session 2026-04-17)
**Closes**: [Issue #36](https://github.com/yakkuro/gh-manage/issues/36)

## Problem

`reusable-pr-gate-python.yml` and `reusable-pr-gate-typescript.yml` execute three
consumer-supplied string inputs via `eval "${CMD}"`:

- `install-command` (line 93 in both files)
- `setup-command` (line 118)
- `test-command` (line 133)

The values are passed through `env:` (so GitHub Actions expression injection,
`${{ }}` re-evaluation, is already prevented), but `eval` re-interprets shell
metacharacters contained in the value. If a consumer's `ci.yml` forwards an
untrusted value (for example
`test-command: ${{ github.event.comment.body }}`), a malicious actor can
append shell metacharacters (`;`, `$()`, pipes, redirects) and achieve remote
code execution inside the PR Gate job.

The PR Gate is a public reusable workflow called by any repository via
`uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@<ref>`,
so defence in depth at the workflow layer is warranted even though the primary
consumer-side mistake (forwarding untrusted input) must also be avoided.

## Prior attempt (reverted)

Commit `04870e8` (2026-04-16) removed `eval` from all three call sites by
replacing `eval "${CMD}"` with `${CMD}` (shell word splitting). Codex review
flagged a regression in `yakkuro/image-ocr`, whose consumer `ci.yml` contains:

```yaml
setup-command: "pip install -e '.[dev,bot]'"
```

Without `eval`, the single quotes reach `pip` as literal characters, so `pip`
tries to install a package literally named `'.[dev,bot]'` and fails. The change
was reverted in `7f0e16d` with a note that Issue #36 needs a different
approach.

## Design decisions (Q&A summary)

| # | Question | Decision |
|---|----------|----------|
| Q1 | Scope | **(a) Defence in depth** — remove `eval` from `install-command` and `test-command`, keep `eval` in `setup-command` as a documented escape hatch |
| Q2 | Versioning | **(ii) Minor bump** to `v1.1.0` — documented behaviour change, not a full major per `docs/versioning.md` |
| Q3 | `setup-command` handling | **(1) Documentation only** — description gets a security note, no runtime validation or deprecation |
| Q4 | Testing | **(B) Regression fixtures** — three fixtures: flags+path pattern, injection attempt (negative), image-ocr-style quoted setup (compatibility) |
| Q5 | Consumer rollout | **(1) Push (maintainer driven)** — release `v1.1.0`, then open 22 bump PRs against every `repos.yml` entry |

## Consumer-input survey (verified 2026-04-17)

All 22 bundled consumers (`src/gh_manage/data/repos.yml`) inspected. Only the
following fields and patterns are in active use:

| Pattern | Count | Field(s) |
|---------|-------|----------|
| `uv sync` (default) | majority | install-command |
| `uv sync --all-extras` / `uv sync --extra dev` / `uv sync --group dev` / `uv sync --extra bench --extra dev` | 6 repos | install-command |
| `uv run pytest` (default) | majority | test-command |
| `uv run pytest tests/ -v --tb=short` (and variants with `--ignore=`) | 4 repos | test-command |
| `uv run mypy packages/` | 1 repo (deep-research) | setup-command |
| `pip install -e '.[dev,bot]'` | **1 repo (image-ocr)** | setup-command |

No consumer uses shell metacharacters (`;`, `|`, `$()`, `` ` ``, `>`, `<`,
quotes) in `install-command` or `test-command`. The only metachar-dependent
value across all 22 consumers is image-ocr's quoted `setup-command`.

## Threat model

### In scope

- Consumer `ci.yml` forwards an externally-controlled value
  (`github.event.comment.body`, `github.event.issue.title`, inputs from
  workflow_dispatch, etc.) to `install-command` or `test-command`. Before
  `v1.1.0` this allowed RCE via `eval`. After `v1.1.0` the injected metachars
  are passed as literal argv to the install/test binary, which typically
  errors out.

### Out of scope (consumer-side responsibility)

- Consumer forwards untrusted input to `setup-command`. The input description
  will explicitly forbid this; enforcing it in the workflow is not feasible
  without a metachar allow-list, which we explicitly rejected (Q1 option (c)).
  **`setup-command` remains a security boundary that depends on consumer
  discipline.** If consumer mis-use of `setup-command` becomes a repeated
  pattern (e.g., surfaced by future drift-scanner checks or PR reviews), the
  next step is to add runtime deprecation warnings in a later minor release
  rather than a silent runtime check.
- Consumer repository write access attacks. An actor who can modify `ci.yml`
  already has full write and does not need injection.
- `gh-manage-ref` tampering (covered separately by existing ref-pin policies).

## Implementation changes

### 1. `.github/workflows/reusable-pr-gate-python.yml`

| Step | Line | Change |
|------|------|--------|
| Install dependencies | 93 | `eval "${INSTALL_CMD}"` → `${INSTALL_CMD}` |
| Run setup command | 118 | **unchanged** (`eval` retained) |
| Run tests | 133 | `eval "${TEST_CMD}"` → `${TEST_CMD}` |

Input descriptions (at the top of the file) are updated:

- `install-command` and `test-command`: add note that the value runs via
  `${CMD}` word splitting and does not support shell metacharacters.
- `setup-command`: add explicit security warning that the value is executed
  via `eval` and must come from a static literal, never an untrusted source.

### 2. `.github/workflows/reusable-pr-gate-typescript.yml`

Identical changes: lines 93 and 133 switch to `${CMD}`, line 118 retains
`eval`, input descriptions are updated.

### 3. Runtime behaviour after the change

`install-command` and `test-command` (change scope):

| Input value | Old (`eval`) | New (`${CMD}`) |
|-------------|--------------|---------------|
| `uv run pytest` | argv: `uv`, `run`, `pytest` | argv: `uv`, `run`, `pytest` ✓ |
| `uv sync --all-extras` | argv: `uv`, `sync`, `--all-extras` | argv: `uv`, `sync`, `--all-extras` ✓ |
| `uv run pytest tests/ -v --tb=short` | argv: 5 tokens | argv: 5 tokens ✓ |
| `uv run pytest ; echo PWNED` | runs `pytest`, then `echo` | argv: `uv`, `run`, `pytest`, `;`, `echo`, `PWNED` → pytest errors on extra args, job fails, `PWNED` never emitted |

`setup-command` (unchanged — `eval` retained as documented escape hatch):

| Input value | Behaviour |
|-------------|-----------|
| `pip install -e '.[dev,bot]'` | argv: `pip`, `install`, `-e`, `.[dev,bot]` (quotes stripped by `eval`). Used today by yakkuro/image-ocr. |
| Static literal with pipes, redirects, or `$()` | Executed by shell via `eval`. Consumer accepts the security responsibility per the input's description. |

### 4. Input → env-var → shell expansion (workflow wiring, unchanged)

The edit only changes the `run:` body of three steps; the step-level `env:`
block that binds the reusable-workflow `inputs.*` values to shell environment
variables is already in place and is preserved:

```yaml
- name: Install dependencies
  shell: bash
  working-directory: ${{ inputs.working-directory }}
  env:
    INSTALL_CMD: ${{ inputs.install-command }}  # unchanged binding
  run: |
    set -euo pipefail
    echo "::group::install"
    echo "Running install-command: ${INSTALL_CMD}"
    ${INSTALL_CMD}          # was: eval "${INSTALL_CMD}"
    echo "::endgroup::"
```

The same `env:` binding exists for `SETUP_CMD` and `TEST_CMD` in their
respective steps; none of the bindings move. This matters because the
security property (no GitHub Actions expression re-evaluation of
user-controlled input) relies on the env-var indirection, and that
indirection is preserved.

## Testing strategy

### Existing coverage

The self-dogfood CI in `.github/workflows/ci.yml` invokes
`reusable-pr-gate-python.yml` against gh-manage itself (simple `uv sync` +
`uv run pytest`). This continues to exercise the default path.

### New regression fixtures

Placed under `tests/fixtures/eval-hardening/` (or equivalent, to be confirmed
during planning) and invoked by a new smoke-test workflow or by extending an
existing one. Three fixtures:

**F1 — flags and paths (positive, real-world pattern)**

```yaml
install-command: "uv sync --all-extras"
test-command: "uv run pytest tests/ -v --tb=short"
```

Asserts: job succeeds. Validates word-splitting correctness for the most
common non-default pattern across the 22 consumers.

**F2 — injection attempt (negative)**

```yaml
test-command: "uv run pytest tests/ ; echo PWNED_BY_INJECTION"
```

Primary assertion (load-bearing): the string `PWNED_BY_INJECTION` does **not**
appear in the job log. Under the old `eval` behaviour, `;` terminates the
pytest command and the subsequent `echo` prints the marker; under the new
`${CMD}` behaviour, pytest receives `;`, `echo`, `PWNED_BY_INJECTION` as extra
positional arguments and errors out without emitting the marker.

Concrete implementation sketch (to be finalised during the plan phase):

```yaml
- name: Invoke reusable PR gate (expects pytest failure)
  id: invoke
  continue-on-error: true
  uses: ./.github/workflows/reusable-pr-gate-python.yml
  with:
    test-command: "uv run pytest tests/ ; echo PWNED_BY_INJECTION"
    # ... other required inputs

- name: Assert injection neutralised
  shell: bash
  run: |
    set -euo pipefail
    # Fetch the invoked job's logs via gh CLI (the fixture job runs in
    # the same run, so gh run view --log returns the combined output).
    gh run view "${{ github.run_id }}" --log \
      | tee /tmp/pr-gate-output.log
    if grep -q 'PWNED_BY_INJECTION' /tmp/pr-gate-output.log; then
      echo "::error::injection marker leaked — eval hardening regressed"
      exit 1
    fi
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Secondary assertion: the invoke step ends in failure (pytest errors on the
extra args). `continue-on-error: true` lets the workflow proceed past that
step; the primary assertion above is what gates success.

The deliberate choice to **not** use output redirection (`> /tmp/pwned` etc.)
keeps the marker observable in log output, so a single log-scan assertion is
sufficient to distinguish old vs new behaviour.

The plan phase will decide whether `gh run view --log` is the right
capture mechanism or whether a `script -c` wrapper inside the fixture is
preferable; both produce a greppable log.

**F3 — quoted setup-command (image-ocr compatibility)**

```yaml
setup-command: "printf '%s\\n' 'quote-preservation-ok'"
```

Asserts: the literal string `quote-preservation-ok` appears in the job log,
proving that single quotes in setup-command are still honoured by `eval`.
(A real `pip install -e '.[dev,bot]'` call would be slow; `printf` is a fast
equivalent that proves quote preservation.)

### TypeScript fixtures

Mirror F1 and F2 with `pnpm` equivalents:

```yaml
# F1
install-command: "pnpm install --frozen-lockfile"
test-command: "pnpm test -- --run"

# F2
test-command: "pnpm test ; echo PWNED_BY_INJECTION"
```

A minimal TS F3 is also included, to guard against future TS consumers
adopting a quoted setup-command and hitting divergent shell behaviour:

```yaml
# F3 (TypeScript)
setup-command: "printf '%s\\n' 'ts-quote-preservation-ok'"
```

Asserts: the literal string `ts-quote-preservation-ok` appears in the job
log. Reuses the same mechanism as the Python F3; only the command payload
differs so the fixture can stand alone in a TS matrix entry.

## Documentation changes

### New: `docs/security.md`

~100 lines, one page. Content outline:

- Trust model table for the three inputs (execution mechanism, metachar
  support, trusted-source requirement).
- Explicit examples of what MUST NOT be forwarded to `setup-command`.
- Version history (v1.0.x had `eval` on all three; v1.1.0 has `eval` only on
  `setup-command`).

### Updated: `docs/usage/python.md`, `docs/usage/typescript.md`

- In the `install-command` and `test-command` sections: "Only space-separated
  args are supported. For commands requiring quotes or other shell features,
  move them to `setup-command` or commit a shell script to the consumer
  repository."
- In the `setup-command` section: link to `docs/security.md` and restate the
  "trusted input only" rule.

### Updated: `CHANGELOG.md` (reusable track, top of file)

```markdown
## [1.1.0] - 2026-04-XX

### Security

- **[Behaviour change]** `install-command` and `test-command` no longer
  interpret shell metacharacters. Previously both fields were executed via
  `eval "${CMD}"`, which allowed command injection when consumers passed
  values sourced from untrusted inputs (PR events, issue bodies). They now
  execute via `${CMD}` (word splitting only).
  - All consumers listed in `src/gh_manage/data/repos.yml` as of 2026-04-17
    (22 repos) verified unaffected by manual inspection of each consumer's
    `ci.yml` install-command / test-command values.
  - Consumers using shell features (quotes, pipes, redirects) in
    install-command or test-command must migrate them to setup-command or a
    committed shell script.
  - Closes #36.

### Added

- `setup-command` input description now explicitly documents its trust
  requirements.
- New `docs/security.md` covering the workflow input threat model.
```

### Updated: `docs/versioning.md`

Add one line under the v1.0.0 stability promise noting that documented
behaviour changes may ship in minor versions and citing v1.1.0 as the
precedent.

## Release and consumer rollout

### Release flow (per `docs/release-checklist.md`)

1. Feature branch: `fix/issue-36-eval-hardening` containing workflow edits,
   fixtures, docs, CHANGELOG.
2. PR against `main`, four-reviewer protocol per
   `~/.claude/rules/workflow-review.md` (Codex + superpowers:code-reviewer +
   silent-failure-hunter + code-reviewer). The reviewers' scope is the
   workflow edits, fixtures, docs, and CHANGELOG only. The consumer rollout
   plan (Section "Consumer rollout") is validated separately by re-reading
   the spec against the then-current `repos.yml` before opening the 22 bump
   PRs — this is a pre-flight check, not a code review.
3. CI green + reviewers approve → squash merge.
4. On `main`: annotated tag `v1.1.0`, push.
5. GitHub Release with CHANGELOG `v1.1.0` section as release notes.
6. Drift scanner already pinned to `@main`, so it picks up the new workflow
   behaviour on the next weekly cron automatically — observe one cron cycle
   to confirm no regressions.

### Consumer rollout (22 PRs)

**Scope**: every repo listed in `src/gh_manage/data/repos.yml` at the time of
the release (currently 22, all `python-service` profile).

**Edit per consumer** in `.github/workflows/ci.yml`:

```yaml
uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.1.0  # was @v1.0.0
with:
  ...
  gh-manage-ref: v1.1.0  # was v1.0.0
```

**Execution** (subagent-driven, covered by the implementation plan):

- Split 22 repos into 4 batches of 5–6 repos each.
- Per batch, spawn parallel workers that each open one PR with:
  - Title: `chore: bump gh-manage from v1.0.0 to v1.1.0 (security hardening)`
  - Body: short note referencing `yakkuro/gh-manage#36`.
- Merge each PR after the consumer's CI (which now invokes the new v1.1.0
  workflow) goes green. Green CI is the per-consumer regression proof.

### Interaction with Phase 10

- Phase 10 AC① (20+ active repos on the reusable workflow) is already
  satisfied at 22/20 and is not affected.
- Phase 10 AC② (two consecutive weeks of zero critical drift findings) is
  not affected. Drift scanner checks **whether** each consumer's `ci.yml`
  specifies the expected reusable-workflow version pin and required inputs,
  not **how** that workflow executes internally. Two facts combine to keep
  AC② green across this change:
  1. The internal switch from `eval "${CMD}"` to `${CMD}` is invisible to
     the drift scanner (it does not inspect the reusable workflow's bash).
  2. The 22 consumer bump PRs update each `ci.yml`'s pin from `@v1.0.0` to
     `@v1.1.0` in lock-step with the bundled profile's expected pin, so the
     scanner sees pin-equality on the next cron after all bump PRs merge.

### Risks and rollback

| Risk | Mitigation |
|------|-----------|
| An undiscovered consumer pattern fails CI under word splitting. | Survey showed zero such patterns across the 22 consumers. If one surfaces during rollout, the consumer's PR fails CI; migrate that consumer's command to `setup-command` or a script, do not revert v1.1.0. |
| Tagging mistake (lightweight vs annotated, wrong commit). | Follow `docs/release-checklist.md`; use `git tag -a`. |
| Rollback needed post-release. | Create a new commit on `main` that restores `eval` in the two affected call sites, tag `v1.1.1`. Do not delete the `v1.1.0` tag. For unmerged consumer PRs with green CI, leave a comment linking the rollback commit and explaining the reason before closing, so that context is preserved on the PR timeline. |

## Non-goals

- Completely removing `eval` from `setup-command`. Considered and rejected
  (Q1): it would force image-ocr into a breaking migration today without
  providing proportional security gain, because `setup-command` values in all
  known consumers are static literals.
- Metacharacter allow-list / deny-list validation. Considered and rejected
  (Q1): implementation complexity (quote-handling edge cases) outweighs the
  benefit given that the word-splitting switch already neutralises the most
  common injection vectors.
- Deprecating `setup-command`. Considered and rejected (Q3): outside the
  scope of a security hardening patch; will be revisited during v2.0
  planning.
- Fixing unrelated issues (#40, #39, #29, #20). Tracked separately.

## Acceptance criteria

- [ ] `reusable-pr-gate-python.yml` and `reusable-pr-gate-typescript.yml`
  use `${CMD}` for `install-command` and `test-command`, retain `eval` for
  `setup-command`.
- [ ] Input descriptions reflect the new trust model.
- [ ] F1, F2, F3 (Python) and F1, F2, F3 (TypeScript) fixtures exist and are
  exercised by a dedicated smoke workflow (new file
  `.github/workflows/eval-hardening-smoke.yml`, preferred) on PRs that touch
  `.github/workflows/`. Extending the existing self-dogfood `ci.yml` is an
  acceptable alternative if the fixture matrix can be scoped to avoid
  perturbing the main PR gate.
- [ ] F2 assertion proves the string `PWNED_BY_INJECTION` does not appear in
  the job log after the test step.
- [ ] `docs/security.md` exists; `docs/usage/python.md`,
  `docs/usage/typescript.md`, `docs/versioning.md`, and `CHANGELOG.md`
  are updated.
- [ ] `v1.1.0` tag pushed, GitHub Release created.
- [ ] 22 consumer PRs opened, merged, with green CI for each.
- [ ] Issue #36 closed via the implementation PR.
