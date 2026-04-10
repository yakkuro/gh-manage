"""YAML config loading with pydantic validation."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

_TModel = TypeVar("_TModel", bound=BaseModel)


class ConfigError(Exception):
    """Base exception for config loading failures."""


class ConfigFileNotFoundError(ConfigError):
    """Config file does not exist at the given path."""


class ConfigParseError(ConfigError):
    """YAML syntax error or top-level node is not a mapping."""


class ConfigSchemaVersionError(ConfigError):
    """`version:` field missing or not in supported_versions."""


class ConfigValidationError(ConfigError):
    """pydantic validation failed. Original ValidationError on __cause__."""


def load_config(
    path: Path | str,
    model_cls: type[_TModel],
    supported_versions: tuple[int, ...] = (1,),
) -> _TModel:
    """Load a YAML config file and validate it against `model_cls`.

    Raises a ConfigError subclass with an actionable message on any failure.
    Paths in error messages are always absolute so users can identify the file
    regardless of the current working directory.
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise ConfigFileNotFoundError(
            f"Config file not found: {path}. Check the path and try again."
        )

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigParseError(
            f"Failed to parse YAML in {path}: {e}. Check the file for syntax errors."
        ) from e
    except UnicodeDecodeError as e:
        raise ConfigParseError(
            f"Config file {path} is not valid UTF-8: {e}. "
            f"Re-save the file with UTF-8 encoding and try again."
        ) from e
    except OSError as e:
        raise ConfigFileNotFoundError(
            f"Cannot read config file {path}: {e}. "
            f"Check that the file exists and is readable by the current user."
        ) from e

    if not isinstance(raw, dict):
        raise ConfigParseError(
            f"Config file {path} must contain a YAML mapping at top level, "
            f"got {type(raw).__name__}."
        )

    version = raw.get("version")
    if version is None:
        raise ConfigSchemaVersionError(
            f"Config file {path} is missing the required `version:` field. "
            f"Supported versions: {supported_versions}."
        )
    if version not in supported_versions:
        raise ConfigSchemaVersionError(
            f"Config file {path} uses unsupported version {version!r}. "
            f"This gh-manage release supports versions {supported_versions}. "
            f"Upgrade gh-manage or downgrade the config file's `version:` "
            f"field to one of the supported versions."
        )

    try:
        return model_cls(**raw)
    except ValidationError as e:
        raise ConfigValidationError(
            f"Config file {path} failed validation:\n{e}"
        ) from e
