import base64
from array import array
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.websocket_server import (
    GeminiLiveProxy,
    _is_low_quality_agent_text,
    _is_voiced_audio_chunk,
    _select_final_agent_text,
    create_websocket_app,
)


def test_websocket_app_created():
    app = create_websocket_app()
    assert app is not None
    assert hasattr(app, 'websocket')

def test_gemini_live_proxy_class_exists():
    """Test that GeminiLiveProxy class exists and can be instantiated"""
    with patch("backend.websocket_server.GOOGLE_API_KEY", "test_api_key"):
        import google.genai

        with patch.object(google.genai, "Client") as _mock_client_cls:
            proxy = GeminiLiveProxy()
            assert proxy is not None
            assert hasattr(proxy, 'connect')
            assert hasattr(proxy, 'send_audio_b64')
            assert hasattr(proxy, 'receive_response')


@pytest.mark.asyncio
async def test_audio_flow_integration():
    """Test audio flow with mocked Gemini client"""
    with patch("backend.websocket_server.GOOGLE_API_KEY", "test_api_key"):

        # Create mock session
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        # Create mock client
        mock_client = MagicMock()
        mock_client.aio.live.connect = MagicMock(return_value=mock_cm)

        import google.genai
        with patch.object(google.genai, 'Client', return_value=mock_client):
            proxy = GeminiLiveProxy()

            # Test connect
            await proxy.connect("test_session")
            mock_client.aio.live.connect.assert_called_once()

            # Test send audio
            test_audio = "dGVzdF9hdWRpb19kYXRh"
            await proxy.send_audio_b64(test_audio)

            mock_session.send_realtime_input.assert_called_once_with(
                audio={"mime_type": "audio/pcm;rate=16000", "data": test_audio}
            )


def test_select_final_agent_text_prefers_tool_answer_over_partial_model_text():
    assert _select_final_agent_text(
        "**Clarifying Tax Inquiry** My next step is to route the query.",
        "Cash prizes are taxable under Indian income tax rules.",
    ) == "Cash prizes are taxable under Indian income tax rules."


def test_low_quality_agent_text_is_not_used_for_memory():
    assert _is_low_quality_agent_text(
        "**Clarifying Tax Inquiry** I'm focusing on the question and my next step is to route it."
    )
    assert _select_final_agent_text(
        "**Clarifying Tax Inquiry** I'm focusing on the question and my next step is to route it.",
        "",
    ) == ""


def test_heading_style_agent_text_is_always_treated_as_low_quality():
    assert _is_low_quality_agent_text(
        "**Offering Initial Assistance** Hello. My initial assessment is the user provided a simple greeting."
    )


def test_voiced_audio_chunk_detects_silence_and_speech():
    silence = base64.b64encode((b"\x00\x00" * 160)).decode("utf-8")
    speechy = array("h", [0, 0, 1200, -1400] * 40).tobytes()
    speechy_b64 = base64.b64encode(speechy).decode("utf-8")

    assert not _is_voiced_audio_chunk(silence)
    assert _is_voiced_audio_chunk(speechy_b64)
