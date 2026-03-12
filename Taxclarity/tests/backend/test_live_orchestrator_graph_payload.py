import pytest


@pytest.mark.asyncio
async def test_live_query_content_includes_graph_events(monkeypatch):
    from backend.live_orchestrator import run_live_query

    async def fake_classifier(_query: str):
        return {"jurisdiction": "india", "confidence": 0.9}

    async def fake_call(_url: str, _query: str):
        return {
            "status": "success",
            "text": (
                '{"source":"taxtmi","evidence":['
                '{"title":"Section 80C","url":"https://example.com/80c","snippet":"Deduction available",'
                '"date":"2026-03-01","reply_count":3}'
                "]}"
            ),
        }

    monkeypatch.setattr("backend.live_orchestrator._classify_jurisdiction", fake_classifier)
    monkeypatch.setattr("backend.live_orchestrator._call_a2a_agent", fake_call)
    monkeypatch.setattr(
        "backend.live_orchestrator._load_memory_context",
        lambda *_args, **_kwargs: {"prior_resolutions": [], "unresolved_queries": []},
    )
    monkeypatch.setattr("backend.live_orchestrator._persist_memory", lambda *_args, **_kwargs: None)

    result = await run_live_query("What can I claim under 80C?", "user-1", "session-1")

    assert "graph_events" in result["content"]
    assert any(event["kind"] == "source_agent" for event in result["content"]["graph_events"])
    assert any(event["kind"] == "claim" for event in result["content"]["graph_events"])


def test_build_graph_events_uses_regional_source_ids_for_both_jurisdiction():
    from backend.live_orchestrator import _build_graph_events

    events = _build_graph_events(
        session_id="session-1",
        query="Hackathon prize tax",
        jurisdiction="both",
        source_statuses=[
            {
                "source": "taxtmi",
                "label": "TaxTMI",
                "region": "india",
                "status": "success",
                "evidence_count": 1,
            }
        ],
        claims=[
            {
                "claim": "Prize may be taxable",
                "confidence": 0.82,
                "citations": [
                    {
                        "source": "taxtmi",
                        "url": "https://example.com/prize",
                        "title": "Prize taxability",
                    }
                ],
            }
        ],
        contradictions=[],
        memory_context={"prior_resolutions": [], "unresolved_queries": []},
    )

    citation_event = next(event for event in events if event["kind"] == "citation")
    assert citation_event["sourceId"] == "source:india:taxtmi"
