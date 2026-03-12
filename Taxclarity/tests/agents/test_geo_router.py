import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Test keyword-based routing (fallback when no API key)
@pytest.mark.asyncio
async def test_keyword_route_india():
    from agents.adk.geo_router.agent import keyword_based_routing

    result = await keyword_based_routing("How do I claim Section 44ADA?")
    assert result["jurisdiction"] == "india"
    assert result["type"] == "single"
    assert result["method"] == "keyword"


@pytest.mark.asyncio
async def test_keyword_route_usa():
    from agents.adk.geo_router.agent import keyword_based_routing

    result = await keyword_based_routing("How do I file my W-2?")
    assert result["jurisdiction"] == "usa"
    assert result["type"] == "single"
    assert result["method"] == "keyword"


@pytest.mark.asyncio
async def test_keyword_route_both():
    from agents.adk.geo_router.agent import keyword_based_routing

    result = await keyword_based_routing("I work in India but have US clients, how is my income taxed?")
    assert result["jurisdiction"] == "both"
    assert result["type"] == "cross_border"
    assert result["method"] == "keyword"


def test_no_duplicate_routing():
    """Ensure only ONE keyword_based_routing function exists in the module source."""
    import agents.adk.geo_router.agent as geo_module

    source = inspect.getsource(geo_module)
    count = source.count("async def keyword_based_routing")
    assert count == 1, f"Expected 1 definition, found {count}"


def test_agent_endpoints_structure():
    """Verify AGENT_ENDPOINTS maps india->[8001,8002] and usa->[8004,8005]."""
    from agents.adk.geo_router.agent import AGENT_ENDPOINTS

    # India endpoints
    assert isinstance(AGENT_ENDPOINTS["india"], list)
    assert len(AGENT_ENDPOINTS["india"]) == 2
    assert "8001" in AGENT_ENDPOINTS["india"][0]
    assert "8002" in AGENT_ENDPOINTS["india"][1]

    # USA endpoints
    assert isinstance(AGENT_ENDPOINTS["usa"], list)
    assert len(AGENT_ENDPOINTS["usa"]) == 2
    assert "8004" in AGENT_ENDPOINTS["usa"][0]
    assert "8005" in AGENT_ENDPOINTS["usa"][1]


def test_geo_router_model():
    """Verify geo_router_agent uses gemini-3.1-flash-lite-preview."""
    from agents.adk.geo_router.agent import geo_router_agent

    if geo_router_agent is None:
        pytest.skip("ADK not installed -- cannot verify model attribute")
    assert geo_router_agent.model == "gemini-3.1-flash-lite-preview"


# Test A2A delegation function
@pytest.mark.asyncio
async def test_delegate_to_agent():
    from agents.adk.geo_router.agent import delegate_to_agent

    # Mock the HTTP call
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "test response"}

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await delegate_to_agent("http://localhost:8001", "test query")
        assert "status" in result
