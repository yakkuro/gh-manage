# gh-manage

**Status:** early development — not yet released.

GitHub-based CI/CD, Issue management, and operational system for `yakkuro/*` repositories.

`gh-manage` distributes reusable GitHub Actions workflows, composite actions, Issue/PR templates, label definitions, and branch protection policies across multiple repositories under a single declarative source.

## Scope

- Reusable workflows for Python and TypeScript PR quality gates
- CI-driven policy review (gitleaks, size warning — distinct from Claude-runtime review)
- Cross-repository label and branch protection management via a `gh` CLI extension
- New-repository bootstrapping via `gh manage init`
- Scheduled drift detection with Issue-based reporting

## Design

See the [design specification](docs/specs/2026-04-10-gh-manage-design.md) for the full architecture, component decomposition, versioning strategy, and rollout plan.

## License

MIT. See [LICENSE](LICENSE).
