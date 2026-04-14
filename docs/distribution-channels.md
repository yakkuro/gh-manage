# Distribution Channels

gh-manage is distributed through **Git tags only**. There is no PyPI package, no Homebrew formula, and no standalone binary. This document explains what is published where, and why the channel decisions were made.

The short version: a single Git repository (`yakkuro/gh-manage`) holds three independent deliverables, and each deliverable is consumed by pointing at a Git tag on that repository. No intermediate registry, no separate release artifacts, no duplicate version metadata to keep in sync.

## What ships where

| Deliverable | Channel | Consumer install command | Why this channel |
|---|---|---|---|
| Reusable workflows | Git tags on `yakkuro/gh-manage` | `uses: yakkuro/gh-manage/.github/workflows/reusable-pr-gate-python.yml@v1.0.0` in consumer `.github/workflows/*.yml` | GitHub Actions reusable workflow is the native mechanism for cross-repo workflow sharing. Git tags are the canonical pin format. |
| Python CLI (`gh-manage`) | Git tags on `yakkuro/gh-manage` | `uv tool install git+https://github.com/yakkuro/gh-manage@cli/v1.0.0` | `uv tool install` accepts `git+<url>@<ref>` URLs directly, so Git tags are first-class installable artifacts. No separate publishing step required. |
| Bundled configuration + templates | Inside the CLI wheel | (automatic — CLI resolves via `importlib.resources`) | Bundled data must stay version-locked to the CLI that consumes it. Shipping separately would create a schema-drift risk. |

## Why NOT PyPI

PyPI is the obvious alternative for a Python CLI. gh-manage does not use it for four reasons:

1. **Internal tool, single org.** gh-manage targets `yakkuro/*` repositories specifically. PyPI's discoverability and index value add nothing for an internal tool.
2. **Git tag ↔ wheel version 1:1.** With Git tags as the install source, the `cli/vX.Y.Z` tag is always the wheel's version. No risk of "PyPI has v1.0.0 but the tag is v1.0.1" drift. With PyPI, every release would require a second publishing step that could silently diverge (this actually happened once in Phase 6 and motivated `docs/release-checklist.md`).
3. **Extra release-workflow complexity.** PyPI publishing requires `twine` + credentials + a release-trigger workflow. For 1-2 releases per week, this is not worth the maintenance surface.
4. **`uv tool install git+` is simple enough.** One command, no credentials, no intermediate steps, works on fresh machines.

## Why bundled data lives inside the CLI wheel

gh-manage's CLI wheel bundles all its configuration data — `labels.yml`, `branch-protection.yml`, `profile.yml` definitions, `repos.yml`, and the file templates in `data/templates/` — inside the installed Python package. Consumers never download this data separately; the CLI resolves it at runtime via `importlib.resources.files()`.

This is a deliberate design choice. Shipping the data separately (e.g., as a separate Git submodule, a downloaded config tarball, or a second PyPI package) would create two independent version surfaces that could drift. If a consumer runs `gh-manage init` against `python-service` version 1.2 but the CLI installed is still at 1.1, the `profile.yml` schema validator might accept a new field that the 1.1 engine does not understand — and the failure mode would be silent data corruption, not a helpful version-mismatch error.

By binding bundled data to the CLI wheel version 1:1, gh-manage gets one version number to reason about: `cli/vX.Y.Z` is the entire consumable artifact for the CLI track. The L6 characterization test (`test_bundled_python_service_package_data_resolves_and_applies`) pins this resolution path.

## Why NOT Homebrew / GitHub Releases binaries

- **Single OS target.** gh-manage runs on Linux servers, developer macOS, and GitHub Actions `ubuntu-latest`. No need for multi-OS binary builds or platform-specific formulas.
- **`uv` handles Python dependencies transparently.** A Homebrew formula would need to shell out to `uv` anyway, and would add one more place to update on every release.
- **No static binary demand.** Users who run `gh-manage` already have Python 3.12 + `uv` on their machines (the same stack used for every yakkuro repo). A static binary solves a non-problem.

## Future distribution channels

gh-manage will reconsider these channels if any of the following happen:

- **Org external adoption.** If repositories outside `yakkuro/` start consuming gh-manage, PyPI may become worth publishing to.
- **`gh extension` ecosystem growth.** GitHub's `gh extension` model allows distributing CLI tools through the `gh` CLI itself; if this becomes the dominant distribution channel, gh-manage may publish as a `gh` extension.
- **Binary distribution demand.** If someone wants to use gh-manage without Python installed, a static binary (built via `pyinstaller` or similar) could be distributed through GitHub Releases.

No work on any of these is planned for v1.0. They are tracked as "considerations" only, not commitments.

## Why `uv tool install` (and not `pipx install` or `pip install --user`)

gh-manage standardizes on `uv tool install` for three reasons:

- **Python version management is built in.** `uv` installs the CLI into an isolated managed Python environment that matches gh-manage's declared `requires-python` (3.12+). With `pipx` or `pip install --user`, the user must separately ensure a compatible Python is available on `PATH`.
- **`git+` URL is a first-class install source.** `uv tool install git+https://...@cli/v1.0.0` Just Works. `pipx` supports `git+` URLs but with slightly more verbose syntax, and `pip install --user` does not bind a tag to a version automatically.
- **Reproducible upgrades.** `uv tool install --force --reinstall` re-fetches the exact tagged commit every time. No stale caches, no "I already installed this version" surprises.

That said, `pipx` and `pip install --user` are NOT formally blocked. Consumers who prefer them can install `gh-manage` with `pipx install git+https://github.com/yakkuro/gh-manage@cli/v1.0.0` — the wheel metadata is the same. They just lose the Python-version-management benefit.

## Install verification

After installing the CLI, verify the wheel version matches the tag you installed from:

```bash
gh-manage --version
```

Expected output: `gh-manage, version X.Y.Z` where `X.Y.Z` matches the `cli/vX.Y.Z` tag you installed. If it does not match, the bundled `pyproject.toml` version was not bumped before the tag was pushed — see [`release-checklist.md`](release-checklist.md) for the force-update recovery procedure.

Additional verification that the bundled data resolved correctly through `importlib.resources`:

```bash
cd /tmp && gh-manage labels show gh-manage
```

Expected: outputs the 14 labels from the bundled `labels.yml` (8 type + 6 meta). Running this from `/tmp` (not the repo) proves that the CLI does not depend on the current working directory containing any gh-manage source files.

## Reference

- [`versioning.md`](versioning.md) — semver policy, stability promise, pinning recommendations
- [`release-checklist.md`](release-checklist.md) — the pre/tag/post release procedure
- [`CHANGELOG-reusable.md`](../CHANGELOG-reusable.md) and [`CHANGELOG-cli.md`](../CHANGELOG-cli.md) — release history per track
