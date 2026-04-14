# Release Checklist

This checklist covers the `cli/vX.Y.Z` release process for `gh-manage`. The CLI ships as a Python package installed via `uv tool install git+https://github.com/yakkuro/gh-manage@cli/vX.Y.Z`, so tag, wheel metadata, and GitHub release notes must all agree.

**History:** Phase 6 (`cli/v0.3.0`) originally shipped with the wheel metadata still at `0.2.0` — a mismatch that showed up as `gh-manage --version` printing "0.2.0" for a CLI tagged "v0.3.0". This checklist exists to prevent that from happening again. (The Phase 6 issue was caught and force-tag-corrected after the fact.)

## Before tagging a release

These steps MUST run on a clean `main` (no uncommitted changes), after the phase's feature PR has merged:

- [ ] **Bump the version in 3 places** via a dedicated `chore/bump-cli-vX.Y.Z` PR:
  - `pyproject.toml` — `version = "X.Y.Z"` under `[project]`
  - `src/gh_manage/__init__.py` — `__version__ = "X.Y.Z"`
  - `tests/test_sanity.py` — the `test_package_version_is_defined` assertion
- [ ] **Run `uv sync`** to update `uv.lock` with the new self-reference
- [ ] **Run the full gate** on the bump branch:
  - `uv run pytest` — all tests pass (the sanity test guards the bump)
  - `uv run ruff check src/ tests/` — clean
  - `uv run mypy src/` — no new errors
- [ ] **Open the bump PR**. It's a single-file-value-change with no logic, so the 4-reviewer cross-agent review can be skipped per `workflow-review.md`'s skip conditions. Merging directly after CI green is fine.
- [ ] **Verify the bump is on `main`** after merge: `git checkout main && git pull --ff-only`

## Tagging and releasing

After the bump commit lands on `main`:

- [ ] **Tag the bump commit** (NOT the feature merge commit):
  ```bash
  git tag cli/vX.Y.Z <bump-commit-sha>
  git push origin cli/vX.Y.Z
  ```
- [ ] **Create the GitHub release**:
  ```bash
  gh release create cli/vX.Y.Z \
    --title "cli/vX.Y.Z — Phase N: <feature name>" \
    --notes "..."
  ```
  Release notes must include: what changed, new commands, breaking-ish refactors, safety invariants, test coverage, cross-agent review summary, deferred follow-ups, related spec/plan paths, smoke-test plan.

## Post-release smoke test

Always run the install-based smoke test to verify package data resolves correctly:

- [ ] **Install from the published tag** (NOT from a local checkout):
  ```bash
  uv tool install --force --reinstall git+https://github.com/yakkuro/gh-manage@cli/vX.Y.Z
  ```
- [ ] **Verify the wheel version matches the tag**:
  ```bash
  gh-manage --version
  # Expected: "gh-manage, version X.Y.Z"
  ```
  If this prints a different version, the bump step was skipped — STOP and fix before announcing the release.
- [ ] **Verify package data resolution from a non-gh-manage CWD**:
  ```bash
  cd /tmp && gh-manage labels show gh-manage
  ```
  Expected: lists all 14 labels (proves bundled `labels.yml` is reachable via `importlib.resources` from any CWD).
- [ ] **Verify end-to-end init/apply paths** (for releases that add or touch init/apply):
  ```bash
  mkdir /tmp/release-smoke-<tag> && cd /tmp/release-smoke-<tag>
  git init -q && git remote add origin git@github.com:yakkuro/smoke-test-repo.git
  cd /tmp && gh-manage init --profile python-service /tmp/release-smoke-<tag>
  ```
  Expected: the command loads the profile from package data and reaches the labels API call before failing with a `GhNotFoundError` (because the smoke repo doesn't exist on GitHub). Getting that far proves profile + templates + `git_cli` + `labels_api` all work end-to-end in the installed wheel.

## L7 manual integration test — deferred at v1.0.0

For the v1.0.0 release, the L7 manual integration test (10 steps against a dedicated `yakkuro/gh-manage-test-fixture` repo, as defined in `docs/specs/2026-04-10-gh-manage-design.md` section "L7 Pre-release acceptance test シナリオ") was **deferred**. The 9-repo Phase C production dogfood run (drift scanner running for 4+ days against all 9 repos in `src/gh_manage/data/repos.yml` with zero HIGH or CRITICAL findings) is treated as equivalent end-to-end validation evidence for v1.0.0. If a future release requires re-adding L7 infrastructure (because production dogfood evidence is insufficient for a specific new feature or regression scenario), open a GitHub issue first to create `yakkuro/gh-manage-test-fixture` and `scripts/reset-fixture.sh`.

## If a release goes out with the version mismatch

If `gh-manage --version` reports the wrong version after a release, the fix path is:

1. Open a `chore/bump-cli-vX.Y.Z` PR with the 3-file bump (per the "Before tagging" section above)
2. Merge the bump PR
3. **Force-update the existing tag** to point at the bump commit:
   ```bash
   git tag -d cli/vX.Y.Z                       # delete local
   git push origin :refs/tags/cli/vX.Y.Z       # delete remote
   git tag cli/vX.Y.Z <bump-commit-sha>        # re-create on bump
   git push origin cli/vX.Y.Z                  # re-publish
   ```
4. **Re-publish the GitHub release** — deleting the remote tag demotes the release to a draft with an `untagged-...` URL. Restore it with:
   ```bash
   gh release edit cli/vX.Y.Z --draft=false --tag cli/vX.Y.Z
   ```
5. **Re-run the install smoke test** to confirm the fix.
6. **Document the incident** — add a line to the "History" section above so future maintainers know the pattern.

Force-updating a tag is a destructive operation per `git-workflow.md`. It's only acceptable when:
- The tag was created very recently (minutes to hours, not days)
- No external consumer has installed from the bad tag yet (check consumer repos and any distribution channel)
- The alternative (new `cli/vX.Y.Z+1` tag) would create a permanent "broken metadata" tag in the history that confuses future readers

## Related

- `docs/specs/2026-04-10-gh-manage-design.md` — Phase 9 AC explicitly lists `docs/release-checklist.md` as a deliverable
- `~/.claude/rules/git-workflow.md` — global rules on destructive git operations + PR-required workflow
- `~/.claude/rules/workflow-review.md` — 4-reviewer cross-agent review and its skip conditions
