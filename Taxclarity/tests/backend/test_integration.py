
import pytest


@pytest.mark.asyncio
async def test_voice_query_routes_to_geo():
    """Test that voice queries are routed to the correct jurisdiction using keyword fallback"""
    from backend.websocket_server import process_voice_query

    # Test India routing (uses keyword fallback since no API key)
    result = await process_voice_query("How do I claim Section 44ADA for my freelance income?")
    assert "india" in result.get("routing", {}).get("jurisdiction", "")

    # Test USA routing
    result = await process_voice_query("How do I file my W-2?")
    assert "usa" in result.get("routing", {}).get("jurisdiction", "")
