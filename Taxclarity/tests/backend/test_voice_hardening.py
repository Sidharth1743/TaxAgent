"""Tests for voice hardening features: session resumption, compression, thinking events."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test 1: connect() omits session_resumption without a stored handle
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_connect_config_omits_session_resumption_without_handle():
    """GeminiLiveProxy.connect() should only send session_resumption when a handle exists."""
    from backend.websocket_server import GeminiLiveProxy

    proxy = GeminiLiveProxy.__new__(GeminiLiveProxy)
    proxy.client = MagicMock()
    proxy.active_session = None
    proxy._session_cm = None
    proxy.session_alive = False
    proxy._resumption_handle = None

    # Mock the connect context manager
    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    proxy.client.aio.live.connect = MagicMock(return_value=mock_cm)

    await proxy.connect("test-session")

    call_kwargs = proxy.client.aio.live.connect.call_args
    config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
    assert "session_resumption" not in config, f"Unexpected session_resumption: {config}"


# ---------------------------------------------------------------------------
# Test 2: connect() config includes required tool declaration
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_connect_config_includes_geo_router_tool():
    """GeminiLiveProxy.connect() should publish the ask_geo_router tool."""
    from backend.websocket_server import GeminiLiveProxy

    proxy = GeminiLiveProxy.__new__(GeminiLiveProxy)
    proxy.client = MagicMock()
    proxy.active_session = None
    proxy._session_cm = None
    proxy.session_alive = False
    proxy._resumption_handle = None

    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    proxy.client.aio.live.connect = MagicMock(return_value=mock_cm)

    await proxy.connect("test-session")

    call_kwargs = proxy.client.aio.live.connect.call_args
    config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
    assert "tools" in config
    function_declarations = config["tools"][0]["function_declarations"]
    assert any(item["name"] == "ask_geo_router" for item in function_declarations)


# ---------------------------------------------------------------------------
# Test 3: reconnect passes the stored resumption handle
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reconnect_passes_resumption_handle():
    """After storing a resumption handle, connect() sends it to Gemini."""
    from backend.websocket_server import GeminiLiveProxy

    proxy = GeminiLiveProxy.__new__(GeminiLiveProxy)
    proxy.client = MagicMock()
    proxy.active_session = None
    proxy._session_cm = None
    proxy.session_alive = False
    proxy._resumption_handle = "test-handle-123"

    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    proxy.client.aio.live.connect = MagicMock(return_value=mock_cm)

    await proxy.connect("test-session")

    call_kwargs = proxy.client.aio.live.connect.call_args
    config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
    assert config["session_resumption"]["handle"] == "test-handle-123"


# ---------------------------------------------------------------------------
# Test 4: thinking event sent before tool call processing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_thinking_event_sent_before_tool_call():
    """A thinking event is sent to the WebSocket BEFORE process_voice_query runs."""
    from backend.websocket_server import _forward_gemini_responses, GeminiLiveProxy

    # Build a mock proxy that yields one tool_call response then stops
    mock_call = MagicMock()
    mock_call.name = "ask_geo_router"
    mock_call.id = "call-1"
    mock_call.args = {"tax_query": "section 44ADA"}

    mock_tool_call = MagicMock()
    mock_tool_call.function_calls = [mock_call]

    mock_response = MagicMock()
    mock_response.server_content = None
    mock_response.tool_call = mock_tool_call
    mock_response.session_resumption_update = None

    proxy = GeminiLiveProxy.__new__(GeminiLiveProxy)
    proxy.active_session = AsyncMock()
    proxy.session_alive = True
    proxy._resumption_handle = None

    # Make receive_response yield one response then stop
    async def mock_receive():
        yield mock_response
        # After yielding, mark WS as disconnected so the reconnect loop exits
        mock_ws_state.value = 0  # DISCONNECTED

    proxy.receive_response = mock_receive
    proxy.reconnect = AsyncMock()
    proxy.close = AsyncMock()

    # Track call order
    call_order = []

    mock_ws = AsyncMock()
    mock_ws_state = MagicMock()
    mock_ws_state.value = 1  # CONNECTED
    mock_ws.client_state = mock_ws_state

    async def tracking_send_json(data):
        call_order.append(("send_json", data))

    mock_ws.send_json = AsyncMock(side_effect=tracking_send_json)

    mock_routing_result = {
        "content": {
            "synthesized_response": "test answer",
            "claims": [],
            "sources": [],
            "jurisdiction": "india",
        }
    }

    with patch("backend.websocket_server.process_voice_query", new_callable=AsyncMock) as mock_pvq:
        async def tracking_pvq(query, user_id, session_id):
            call_order.append(("process_voice_query", {"query": query, "user_id": user_id, "session_id": session_id}))
            return mock_routing_result

        mock_pvq.side_effect = tracking_pvq

        # Patch send_tool_response to avoid import issues
        proxy.active_session.send_tool_response = AsyncMock()

        await _forward_gemini_responses(proxy, mock_ws, "user-1", "session-1")

    # Find the thinking event and process_voice_query in call_order
    thinking_idx = None
    pvq_idx = None
    for i, (name, _data) in enumerate(call_order):
        if name == "send_json" and isinstance(_data, dict) and _data.get("type") == "thinking":
            thinking_idx = i
        if name == "process_voice_query":
            pvq_idx = i

    assert thinking_idx is not None, f"No thinking event found in calls: {call_order}"
    assert pvq_idx is not None, f"No process_voice_query found in calls: {call_order}"
    assert thinking_idx < pvq_idx, (
        f"thinking event (index {thinking_idx}) should come before "
        f"process_voice_query (index {pvq_idx})"
    )


# ---------------------------------------------------------------------------
# Test 5: dual-model routing (Flash voice + flash-lite tool agents)
# ---------------------------------------------------------------------------
def test_dual_model_routing():
    """VOICE_MODEL remains a flash family model, GEO_ROUTER_MODEL stays flash-lite."""
    from config import GEO_ROUTER_MODEL, VOICE_MODEL

    assert "flash" in VOICE_MODEL, f"VOICE_MODEL should remain a flash model, got: {VOICE_MODEL}"
    assert "flash-lite" in GEO_ROUTER_MODEL, f"GEO_ROUTER_MODEL should contain flash-lite, got: {GEO_ROUTER_MODEL}"
