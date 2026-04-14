"""Golden file test: AC #4 from the Phase 6 spec.

Loads a fixture profile, applies it to a tmp_path target, and asserts
each written file matches the fixture template byte-for-byte. If
templates contain timestamps or variable content, this test will be
brittle — fixture content is intentionally stable (no dates, no
version strings, no substitution).
"""

from __future__ import annotations

from pathlib import Path

from gh_manage.config import load_config
from gh_manage.models.profiles import ProfileSpec
from gh_manage.profile_sync import apply_files_diff, compute_files_diff

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "profile_sync"
PROFILES = FIXTURES / "profiles"
TEMPLATES = FIXTURES / "templates"


def test_basic_profile_golden_apply(tmp_path: Path) -> None:
    """Apply the `basic` fixture profile to an empty target_root and
    verify each written file matches its template byte-for-byte."""
    profile = load_config(PROFILES / "basic.yml", ProfileSpec)
    diff = compute_files_diff(profile, tmp_path, TEMPLATES)

    # Sanity: 2 creates, no overwrites/skips/noops
    assert len(diff.creates) == 2
    assert diff.overwrites == ()
    assert diff.skipped == ()
    assert diff.noops == ()

    apply_files_diff(diff, tmp_path, TEMPLATES)

    # Byte-for-byte comparison against the fixture sources
    written_ci = tmp_path / ".github/workflows/ci.yml"
    written_claude = tmp_path / "CLAUDE.md"
    assert written_ci.is_file()
    assert written_claude.is_file()
    assert written_ci.read_bytes() == (TEMPLATES / "ci/test-ci.yml").read_bytes()
    assert written_claude.read_bytes() == (TEMPLATES / "claude-md/test.md").read_bytes()


def test_basic_profile_idempotent(tmp_path: Path) -> None:
    """A second apply with the same target should produce all noops."""
    profile = load_config(PROFILES / "basic.yml", ProfileSpec)

    # First apply
    diff1 = compute_files_diff(profile, tmp_path, TEMPLATES)
    apply_files_diff(diff1, tmp_path, TEMPLATES)

    # Second compute should see all noops
    diff2 = compute_files_diff(profile, tmp_path, TEMPLATES)
    assert diff2.is_empty
    assert len(diff2.noops) == 2


def test_bundled_python_service_package_data_resolves_and_applies(
    tmp_path: Path,
) -> None:
    """L6 characterization test per Phase 0 design spec.

    Purpose: pin the raw-byte-copy behavior of apply_files_diff when it
    resolves bundled profile + templates via importlib.resources. Unique
    value is proving package-data resolution works for wheel installs;
    the byte-compare is a side effect of profile_sync's raw-copy
    invariant. See docs/specs/2026-04-14-phase-9-v1-hardening-design.md
    section 1 for the regression-check procedure and future-evolution
    note.
    """
    from importlib.resources import as_file, files

    profiles_root_ref = files("gh_manage.data.profiles")
    templates_root_ref = files("gh_manage.data.templates")

    with as_file(profiles_root_ref) as profiles_root:
        profile_path = profiles_root / "python-service.yml"
        profile = load_config(profile_path, ProfileSpec)

        with as_file(templates_root_ref) as templates_root:
            diff = compute_files_diff(profile, tmp_path, templates_root)
            assert len(diff.creates) == 2
            assert diff.overwrites == ()
            assert diff.skipped == ()
            assert diff.noops == ()

            apply_files_diff(diff, tmp_path, templates_root)

            for entry in profile.files:
                written = tmp_path / entry.dest
                source = templates_root / entry.source
                assert written.read_bytes() == source.read_bytes(), (
                    f"Bundled template {entry.source} did not apply byte-identically "
                    f"to {entry.dest}. If a placeholder-substitution feature was added "
                    f"to profile_sync, delete this test and Phase 6 fixture golden "
                    f"tests per the spec's Future Evolution note; do NOT mechanically "
                    f"update the expected-bytes computation."
                )
