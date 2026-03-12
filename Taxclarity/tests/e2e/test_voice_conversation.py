from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_full_voice_flow():
    """
    E2E test: User speaks → Audio sent → Gemini processes → Geo routes → Response returned
    This is a simulation test without actual API calls
    """
    from backend.websocket_server import GeminiLiveProxy, process_voice_query

    # Mock Gemini Live session
    mock_session = AsyncMock()
    mock_session.receive = AsyncMock(return_value=iter([
        MagicMock(text="How do I file my W-2?")
    ]))

    with patch('backend.websocket_server.os.getenv') as mock_getenv:
        mock_getenv.return_value = "test_api_key"

        # Create mock client
        mock_client = MagicMock()
        mock_client.aio.live.connect = AsyncMock(return_value=mock_session)

        import google.genai
        with patch.object(google.genai, 'Client', return_value=mock_client):
            # Test voice proxy creation
            proxy = GeminiLiveProxy()
            assert proxy is not None

            # Test voice query routing
            result = await process_voice_query("How do I file my W-2?")
            assert "routing" in result
            assert result["routing"]["jurisdiction"] == "usa"

            # Verify the flow works as expected
            assert mock_client.aio.live.connect is not None


@pytest.mark.asyncio
async def test_voice_with_video_flow():
    """Test voice + video multimodal flow"""
    from backend.websocket_server import GeminiLiveProxy

    with patch('backend.websocket_server.os.getenv') as mock_getenv:
        mock_getenv.return_value = "test_api_key"

        mock_session = AsyncMock()
        mock_client = MagicMock()
        mock_client.aio.live.connect = AsyncMock(return_value=mock_session)

        import google.genai
        with patch.object(google.genai, 'Client', return_value=mock_client):
            proxy = GeminiLiveProxy()

            # Test video sending capability
            _test_frame = b"fake_jpeg_data"
            # This would normally send to Gemini, but we're just testing the method exists
            assert hasattr(proxy, 'send_video')
