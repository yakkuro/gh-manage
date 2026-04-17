"""Doctor-specific error hierarchy.

DoctorError is caught by commands/_shared.py::handle_errors via the
_DOMAIN_ERRORS tuple (added in a later task wiring).
"""

from __future__ import annotations


class DoctorError(Exception):
    """Base for all doctor errors. Caught by CLI handle_errors."""


class CiYmlParseError(DoctorError):
    """Raised when the target repo's ci.yml cannot be parsed as YAML
    or lacks the structure doctor expects."""


class DoctorCheckError(DoctorError):
    """Raised when a single check function fails unexpectedly.

    The drift bridge catches this and converts it to a
    `Finding(severity='medium', check='shape/check-error', ...)`."""
