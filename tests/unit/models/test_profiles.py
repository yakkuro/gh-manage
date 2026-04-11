"""Tests for gh_manage.models.profiles — ProfileSpec + FileEntry."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gh_manage.config import ConfigSchemaVersionError, load_config
from gh_manage.models.profiles import FileEntry, ProfileSpec

FIXTURES = (
    Path(__file__).parent.parent.parent / "fixtures" / "profile_sync" / "profiles"
)


# FileEntry validators
def test_file_entry_minimal_valid() -> None:
    e = FileEntry(source="ci/python-ci.yml", dest=".github/workflows/ci.yml")
    assert e.skip_if_exists is False


def test_file_entry_skip_if_exists_default_false() -> None:
    e = FileEntry(source="a", dest="b")
    assert e.skip_if_exists is False


def test_file_entry_rejects_absolute_dest() -> None:
    with pytest.raises(ValidationError, match="absolute"):
        FileEntry(source="ci.yml", dest="/etc/passwd")


def test_file_entry_rejects_dotdot_in_dest() -> None:
    with pytest.raises(ValidationError, match=r"\.\."):
        FileEntry(source="ci.yml", dest="../../etc/passwd")


def test_file_entry_rejects_absolute_source() -> None:
    with pytest.raises(ValidationError, match="absolute"):
        FileEntry(source="/etc/passwd", dest="foo.yml")


def test_file_entry_rejects_dotdot_in_source() -> None:
    with pytest.raises(ValidationError, match=r"\.\."):
        FileEntry(source="../etc/passwd", dest="foo.yml")


def test_file_entry_rejects_empty_dest() -> None:
    with pytest.raises(ValidationError, match="empty"):
        FileEntry(source="ci.yml", dest="")


def test_file_entry_rejects_empty_source() -> None:
    with pytest.raises(ValidationError, match="empty"):
        FileEntry(source="", dest="ci.yml")


# ProfileSpec
def test_profile_spec_minimal_valid() -> None:
    p = ProfileSpec(
        version=1,
        name="python-service",
        files=[FileEntry(source="a", dest="b")],
    )
    assert p.description is None


def test_profile_spec_with_description() -> None:
    p = ProfileSpec(
        version=1,
        name="python-service",
        description="Python service repo",
        files=[],
    )
    assert p.description == "Python service repo"


def test_profile_spec_empty_files_is_valid() -> None:
    """A vacuous profile (no files) is technically valid — apply does nothing."""
    p = ProfileSpec(version=1, name="empty", files=[])
    assert p.files == []


def test_profile_spec_rejects_unknown_version() -> None:
    with pytest.raises(ValidationError):
        ProfileSpec(version=99, name="x", files=[])  # type: ignore[arg-type]


def test_profile_spec_missing_name_raises() -> None:
    with pytest.raises(ValidationError):
        ProfileSpec(version=1, files=[])  # type: ignore[call-arg]


def test_profile_spec_duplicate_dest_raises() -> None:
    """Two file entries writing to the same dest is a silent shadowing
    bug at apply time. Schema must reject it."""
    with pytest.raises(ValidationError, match="Duplicate dest"):
        ProfileSpec(
            version=1,
            name="dup",
            files=[
                FileEntry(source="a.yml", dest="x.yml"),
                FileEntry(source="b.yml", dest="x.yml"),
            ],
        )


# load_config integration
def test_load_config_invalid_version_yml_raises_schema_version_error() -> None:
    with pytest.raises(ConfigSchemaVersionError):
        load_config(FIXTURES / "invalid_version.yml", ProfileSpec)


def test_load_config_duplicate_dest_yml_raises() -> None:
    from gh_manage.config import ConfigValidationError

    with pytest.raises(ConfigValidationError, match="Duplicate dest"):
        load_config(FIXTURES / "duplicate_dest.yml", ProfileSpec)
