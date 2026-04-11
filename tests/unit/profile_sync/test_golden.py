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
