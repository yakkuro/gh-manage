"""Tests for drift_sync/context.py — scan_id ContextVar."""

from __future__ import annotations

from contextvars import copy_context

from gh_manage.drift_sync.context import scan_id_var


def test_scan_id_var_defaults_to_empty_string():
    ctx = copy_context()
    assert ctx.run(scan_id_var.get) == ""


def test_scan_id_var_set_and_reset():
    token = scan_id_var.set("test-uuid")
    try:
        assert scan_id_var.get() == "test-uuid"
    finally:
        scan_id_var.reset(token)
    assert scan_id_var.get() == ""


def test_scan_id_var_importable_from_drift_sync_namespace():
    from gh_manage.drift_sync import scan_id_var as exported

    assert exported is scan_id_var
