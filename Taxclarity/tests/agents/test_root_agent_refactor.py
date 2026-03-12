"""Tests for root agent factory pattern and no-evidence abort."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from agents.adk.root_agent.agent import _make_fetcher, finalize_response


class TestMakeFetcher:
    """Test the _make_fetcher factory function."""

    @pytest.mark.asyncio
    async def test_factory_returns_async_callable(self):
        """_make_fetcher returns an async callable with correct source name."""
        fetcher = _make_fetcher("caclub", "http://localhost:8001")
        assert callable(fetcher)
        assert fetcher.__name__ == "fetch_caclub_a2a"

    @pytest.mark.asyncio
    async def test_factory_calls_a2a_and_returns_dict(self):
        """Factory-created fetcher calls _call_a2a_agent and returns structured dict."""
        mock_task = AsyncMock()
        mock_task.status.message.parts = []

        with patch(
            "agents.adk.root_agent.agent._call_a2a_agent",
            new_callable=AsyncMock,
            return_value={"raw": mock_task},
        ):
            fetcher = _make_fetcher("caclub", "http://localhost:8001")
            result = await fetcher("test query")

        assert result["source"] == "caclub"
        assert "parsed" in result
        assert "raw_text" in result

    @pytest.mark.asyncio
    async def test_factory_different_sources(self):
        """Factory creates distinct fetchers for different sources."""
        f1 = _make_fetcher("caclub", "http://localhost:8001")
        f2 = _make_fetcher("taxtmi", "http://localhost:8002")
        assert f1.__name__ == "fetch_caclub_a2a"
        assert f2.__name__ == "fetch_taxtmi_a2a"


class TestFinalizeResponseNoEvidence:
    """Test finalize_response drops uncited claims and sets no_evidence flag."""

    def test_drops_claims_with_no_valid_citations(self):
        """Claims whose citations don't match allowed URLs are dropped entirely."""
        evidence = {
            "caclub": {
                "parsed": {
                    "evidence": [
                        {"url": "https://caclub.example.com/real"}
                    ]
                }
            }
        }
        draft = json.dumps({
            "query": "test",
            "sources": ["CAClubIndia"],
            "claims": [
                {
                    "claim": "Valid claim",
                    "citations": ["https://caclub.example.com/real"],
                },
                {
                    "claim": "Fabricated claim",
                    "citations": ["https://fake.example.com/nowhere"],
                },
            ],
        })
        result = finalize_response("test", evidence, draft)
        # Only the valid claim should remain
        assert len(result["claims"]) == 1
        assert result["claims"][0]["claim"] == "Valid claim"

    def test_no_evidence_flag_when_all_claims_dropped(self):
        """When ALL claims are dropped, result includes no_evidence=True."""
        evidence = {
            "caclub": {
                "parsed": {
                    "evidence": [
                        {"url": "https://caclub.example.com/real"}
                    ]
                }
            }
        }
        draft = json.dumps({
            "query": "test",
            "sources": ["CAClubIndia"],
            "claims": [
                {
                    "claim": "Bad claim",
                    "citations": ["https://fake.example.com/nowhere"],
                },
            ],
        })
        result = finalize_response("test", evidence, draft)
        assert result["no_evidence"] is True
        assert "message" in result
        assert result["claims"] == []

    def test_no_fabrication_fallback(self):
        """Claims with no matching URL are NOT given a random fallback URL."""
        evidence = {
            "caclub": {
                "parsed": {
                    "evidence": [
                        {"url": "https://caclub.example.com/article1"}
                    ]
                }
            }
        }
        draft = json.dumps({
            "query": "test",
            "sources": ["CAClubIndia"],
            "claims": [
                {
                    "claim": "Claim with wrong URL",
                    "citations": ["https://wrong.example.com/fake"],
                },
            ],
        })
        result = finalize_response("test", evidence, draft)
        # The claim should be dropped, not given a fallback URL
        assert len(result["claims"]) == 0
