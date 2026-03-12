"""Tests for backend/websocket_server.py — module-level app export and security."""

from __future__ import annotations

import inspect


def test_module_level_app_exists():
    """The module exports a FastAPI `app` at module level."""
    from backend.websocket_server import app
    assert app is not None
    from fastapi import FastAPI
    assert isinstance(app, FastAPI)


def test_no_system_instruction_override():
    """The websocket_endpoint must NOT accept system_instruction from client payload."""
    import backend.websocket_server as mod
    _source = inspect.getsource(mod)
    # The security fix removes the override block.
    # There should be no data.get("system_instruction") or data["system_instruction"]
    # in the websocket_endpoint function.
    endpoint_source = inspect.getsource(mod.create_websocket_app)
    assert 'data.get("system_instruction")' not in endpoint_source, (
        "system_instruction override from client payload should be removed"
    )
    assert 'data["system_instruction"]' not in endpoint_source, (
        "system_instruction override from client payload should be removed"
    )


def test_voice_config_still_forwarded():
    """Voice config forwarding is preserved (not broken by security fix)."""
    import backend.websocket_server as mod
    endpoint_source = inspect.getsource(mod.create_websocket_app)
    assert 'data.get("voice"' in endpoint_source, (
        "voice config forwarding should be preserved"
    )


def test_response_modalities_still_forwarded():
    """response_modalities config forwarding is preserved."""
    import backend.websocket_server as mod
    endpoint_source = inspect.getsource(mod.create_websocket_app)
    assert 'data.get("response_modalities"' in endpoint_source, (
        "response_modalities config forwarding should be preserved"
    )
