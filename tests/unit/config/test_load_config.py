"""Tests for gh_manage.config.load_config against LabelsConfig."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gh_manage.config import (
    ConfigFileNotFoundError,
    ConfigParseError,
    ConfigSchemaVersionError,
    ConfigValidationError,
    load_config,
)
from gh_manage.models.labels import LabelsConfig

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "config"


def test_load_valid_labels_yml_returns_typed_model() -> None:
    config = load_config(FIXTURES / "labels-valid.yml", LabelsConfig)
    assert isinstance(config, LabelsConfig)
    assert config.version == 1
    assert "type" in config.categories
    assert all(len(label.color) == 6 for label in config.categories["type"].labels)


def test_missing_file_raises_not_found() -> None:
    with pytest.raises(ConfigFileNotFoundError, match="Config file not found"):
        load_config(FIXTURES / "does-not-exist.yml", LabelsConfig)


def test_malformed_yaml_raises_parse_error() -> None:
    with pytest.raises(ConfigParseError, match="Failed to parse YAML"):
        load_config(FIXTURES / "labels-invalid-bad-yaml.yml", LabelsConfig)


def test_top_level_list_raises_parse_error() -> None:
    with pytest.raises(ConfigParseError, match="must contain a YAML mapping"):
        load_config(FIXTURES / "labels-invalid-not-mapping.yml", LabelsConfig)


def test_missing_version_raises_schema_version_error() -> None:
    with pytest.raises(
        ConfigSchemaVersionError, match="missing the required `version:`"
    ):
        load_config(FIXTURES / "labels-invalid-missing-version.yml", LabelsConfig)


def test_unsupported_version_raises_schema_version_error() -> None:
    with pytest.raises(ConfigSchemaVersionError, match="unsupported version"):
        load_config(FIXTURES / "labels-invalid-wrong-version.yml", LabelsConfig)


def test_bad_color_raises_validation_error() -> None:
    with pytest.raises(ConfigValidationError, match="failed validation"):
        load_config(FIXTURES / "labels-invalid-bad-color.yml", LabelsConfig)


def test_empty_category_raises_validation_error() -> None:
    with pytest.raises(ConfigValidationError, match="failed validation"):
        load_config(FIXTURES / "labels-invalid-empty-category.yml", LabelsConfig)


def test_validation_error_preserves_cause() -> None:
    """pydantic's ValidationError should be available via __cause__."""
    with pytest.raises(ConfigValidationError) as excinfo:
        load_config(FIXTURES / "labels-invalid-bad-color.yml", LabelsConfig)
    assert isinstance(excinfo.value.__cause__, ValidationError)
