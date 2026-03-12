from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
import structlog

from agents.contradiction_agent import detect_contradictions
from config import (
    CACLUB_AGENT_URL,
    TAXPROFBLOG_AGENT_URL,
    TAXTMI_AGENT_URL,
    TURBOTAX_AGENT_URL,
)
from memory.extractor import extract_memory
from memory.spanner_graph import (
    fetch_memory_context,
    get_client,
    load_config,
    upsert_basic_user_session,
    write_memory,
)

logger = structlog.get_logger(__name__)

SOURCE_ENDPOINTS = {
    "india": {
        "caclub": CACLUB_AGENT_URL,
        "taxtmi": TAXTMI_AGENT_URL,
    },
    "usa": {
        "taxprofblog": TAXPROFBLOG_AGENT_URL,
        "turbotax": TURBOTAX_AGENT_URL,
    },
}

SOURCE_LABELS = {
    "caclub": "CAClubIndia",
    "taxtmi": "TaxTMI",
    "turbotax": "TurboTax",
    "taxprofblog": "TaxProfBlog",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"


def _source_status_payload(
    *,
    source: str,
    region: str,
    status: str,
    error: str = "",
    evidence_count: int = 0,
) -> dict[str, Any]:
    return {
        "source": source,
        "label": SOURCE_LABELS.get(source, source),
        "region": region,
        "status": status,
        "error": error,
        "evidence_count": evidence_count,
    }


def _build_graph_events(
    *,
    session_id: str,
    query: str,
    jurisdiction: str,
    source_statuses: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    memory_context: dict[str, Any],
) -> list[dict[str, Any]]:
    query_id = f"query:{_slug(query)}"
    session_node_id = f"session:{session_id}"
    jurisdiction_id = f"jurisdiction:{jurisdiction}"

    events: list[dict[str, Any]] = [
        {
            "id": session_node_id,
            "kind": "session",
            "label": f"Session {session_id[:8]}",
            "status": "active",
        },
        {
            "id": query_id,
            "kind": "query",
            "label": query,
            "status": "active",
            "parentId": session_node_id,
        },
        {
            "id": jurisdiction_id,
            "kind": "jurisdiction",
            "label": jurisdiction.title(),
            "status": "selected",
            "parentId": query_id,
        },
    ]
    source_regions = {
        status["source"]: status["region"]
        for status in source_statuses
        if status.get("source") and status.get("region")
    }

    for source_status in source_statuses:
        source_event_id = f"source:{source_status['region']}:{source_status['source']}"
        events.append(
            {
                "id": source_event_id,
                "kind": "source_agent",
                "label": source_status["label"],
                "status": source_status["status"],
                "region": source_status["region"],
                "parentId": jurisdiction_id,
                "evidenceCount": source_status.get("evidence_count", 0),
                "error": source_status.get("error", ""),
            }
        )

    for index, claim in enumerate(claims):
        claim_id = f"claim:{index}"
        events.append(
            {
                "id": claim_id,
                "kind": "claim",
                "label": claim.get("claim", ""),
                "confidence": claim.get("confidence", 0.0),
                "status": "supported",
                "parentId": query_id,
            }
        )

        for citation_index, citation in enumerate(claim.get("citations", [])):
            citation_id = f"citation:{index}:{citation_index}"
            source_region = source_regions.get(citation.get("source", ""), jurisdiction)
            source_id = f"source:{source_region}:{citation.get('source', '')}"
            events.append(
                {
                    "id": citation_id,
                    "kind": "citation",
                    "label": citation.get("title") or citation.get("url", ""),
                    "status": "cited",
                    "parentId": claim_id,
                    "sourceId": source_id,
                    "url": citation.get("url", ""),
                }
            )

    for index, contradiction in enumerate(contradictions):
        events.append(
            {
                "id": f"contradiction:{index}",
                "kind": "contradiction",
                "label": contradiction.get("topic", f"Conflict {index + 1}"),
                "status": "conflict",
                "parentId": query_id,
            }
        )

    prior_count = len(memory_context.get("prior_resolutions", []))
    unresolved_count = len(memory_context.get("unresolved_queries", []))
    events.append(
        {
            "id": f"memory:{session_id}",
            "kind": "memory",
            "label": "Memory context",
            "status": "loaded" if prior_count or unresolved_count else "empty",
            "parentId": session_node_id,
            "priorCount": prior_count,
            "unresolvedCount": unresolved_count,
        }
    )

    return events


def _norm(text: str) -> str:
    normalized = text.lower().strip()
    normalized = re.sub(r"[^a-z0-9\s]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _parse_date(text: str | None) -> datetime | None:
    if not text:
        return None

    cleaned = text.strip()
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue

    match = re.search(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})", cleaned)
    if match:
        return _parse_date(match.group(1))

    return None


def _extract_agent_text(task: Any) -> str:
    if not task:
        return ""

    status = getattr(task, "status", None)
    message = getattr(status, "message", None) if status else None
    if message and getattr(message, "parts", None):
        output: list[str] = []
        for part in message.parts:
            root = getattr(part, "root", None) or part
            text = getattr(root, "text", None)
            if text:
                output.append(text)
        if output:
            return "\n".join(output)

    history = getattr(task, "history", None) or []
    output = []
    for item in history:
        if getattr(item, "role", "") != "agent":
            continue
        for part in getattr(item, "parts", []) or []:
            root = getattr(part, "root", None) or part
            text = getattr(root, "text", None)
            if text:
                output.append(text)
    return "\n".join(output)


async def _call_a2a_agent(agent_url: str, query: str) -> dict[str, Any]:
    from a2a.client.client import ClientConfig
    from a2a.client.client_factory import ClientFactory
    from a2a.client.errors import A2AClientTimeoutError
    from a2a.types import Message, Part, TaskQueryParams, TaskState, TextPart

    httpx_client = httpx.AsyncClient(timeout=httpx.Timeout(180.0))
    try:
        client = await ClientFactory.connect(
            agent_url,
            client_config=ClientConfig(
                streaming=False,
                polling=True,
                httpx_client=httpx_client,
            ),
            resolver_http_kwargs={"timeout": 180.0},
        )
    except A2AClientTimeoutError as exc:
        await httpx_client.aclose()
        return {"status": "error", "error": f"Agent card timeout: {exc}"}
    except Exception as exc:
        await httpx_client.aclose()
        return {"status": "error", "error": str(exc)}

    message = Message(
        messageId=str(uuid.uuid4()),
        role="user",
        parts=[Part(root=TextPart(text=query))],
    )

    task_id: str | None = None
    try:
        async for result in client.send_message(message):
            if isinstance(result, tuple):
                result = result[0]
            if hasattr(result, "kind") and result.kind == "task":
                task_id = result.id
            elif hasattr(result, "kind") and result.kind == "message":
                return {"status": "success", "raw": result, "text": _extract_agent_text(result)}
    except A2AClientTimeoutError as exc:
        return {"status": "error", "error": f"Send message timeout: {exc}"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    finally:
        if not task_id:
            await httpx_client.aclose()

    if not task_id:
        return {"status": "error", "error": "No task returned"}

    try:
        for _ in range(180):
            task = await client.get_task(TaskQueryParams(id=task_id, historyLength=50))
            if task.status.state in {
                TaskState.completed,
                TaskState.failed,
                TaskState.canceled,
                TaskState.rejected,
            }:
                return {"status": "success", "raw": task, "text": _extract_agent_text(task)}
            await asyncio.sleep(1)
    except A2AClientTimeoutError as exc:
        return {"status": "error", "error": f"Get task timeout: {exc}"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    finally:
        await httpx_client.aclose()

    return {"status": "error", "error": "Timed out waiting for task"}


def _parse_agent_payload(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _extract_evidence(source: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = payload.get("evidence", [])
    if not isinstance(evidence, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        title = str(item.get("title", "")).strip() or SOURCE_LABELS.get(source, source)
        snippet = str(item.get("snippet", "")).strip()
        date = str(item.get("date", "")).strip()
        reply_count = item.get("reply_count", 0)
        try:
            reply_count = int(reply_count)
        except (TypeError, ValueError):
            reply_count = 0

        normalized.append(
            {
                "source": source,
                "title": title,
                "url": url,
                "snippet": snippet,
                "date": date,
                "reply_count": reply_count,
            }
        )

    return normalized


def _score_claim(evidence_items: list[dict[str, Any]]) -> float:
    if not evidence_items:
        return 0.0

    unique_sources = {item["source"] for item in evidence_items}
    score = 0.45
    if len(unique_sources) > 1:
        score += 0.2
    if any(item.get("reply_count", 0) > 0 for item in evidence_items):
        score += 0.1

    cutoff = datetime.utcnow() - timedelta(days=365 * 3)
    if any((parsed := _parse_date(item.get("date"))) and parsed >= cutoff for item in evidence_items):
        score += 0.15

    if any(item.get("snippet") for item in evidence_items):
        score += 0.05

    return round(min(score, 0.95), 2)


def _build_claim_text(evidence_items: list[dict[str, Any]]) -> str:
    primary = evidence_items[0]
    title = primary.get("title", "")
    snippet = primary.get("snippet", "")
    if snippet:
        snippet = snippet.replace("\n", " ").strip()
        if len(snippet) > 180:
            snippet = f"{snippet[:177].rstrip()}..."
        return f"{title} - {snippet}"
    return title


def merge_evidence_into_claims(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        key = _norm(item.get("title") or item.get("url") or item.get("snippet", ""))
        if not key:
            continue
        buckets.setdefault(key, []).append(item)

    claims = []
    for grouped in buckets.values():
        citations = []
        for item in grouped:
            citations.append(
                {
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "date": item.get("date", ""),
                    "reply_count": item.get("reply_count", 0),
                    "source": item.get("source", ""),
                }
            )

        claims.append(
            {
                "claim": _build_claim_text(grouped),
                "citations": citations,
                "confidence": _score_claim(grouped),
            }
        )

    claims.sort(
        key=lambda item: (
            item.get("confidence", 0),
            max((citation.get("reply_count", 0) for citation in item.get("citations", [])), default=0),
        ),
        reverse=True,
    )
    return claims


def synthesize_response(
    query: str,
    claims: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    source_statuses: list[dict[str, Any]],
) -> str:
    if not claims:
        failed_sources = [item.get("label", item.get("source", "source")) for item in source_statuses if item.get("status") == "error"]
        if failed_sources:
            failed = ", ".join(failed_sources)
            return (
                f"I could not reach the connected tax evidence agents for this question. "
                f"The unavailable sources were: {failed}."
            )
        return "I could not retrieve usable tax evidence for that question from the connected sources."

    lines = [f"For your query about {query}, here are the strongest supported points."]
    for claim in claims[:3]:
        lines.append(f"- {claim['claim']}")

    if contradictions:
        lines.append(
            "I also found conflicting views across sources, so you should review the contradiction panel before relying on a final filing decision."
        )

    return " ".join(lines)


def _build_contradiction_input(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contradiction_claims: list[dict[str, Any]] = []
    for claim in claims:
        for citation in claim.get("citations", []):
            contradiction_claims.append(
                {
                    "source": citation.get("source", ""),
                    "claim": claim.get("claim", ""),
                    "citations": [citation.get("url", "")] if citation.get("url") else [],
                }
            )
    return contradiction_claims


def _load_memory_context(query: str, user_id: str) -> dict[str, Any]:
    cfg = load_config()
    if not cfg:
        return {"prior_resolutions": [], "unresolved_queries": []}

    try:
        db = get_client(cfg)
        extracted = extract_memory(query) or {}
        concepts = extracted.get("concepts", []) or []
        entities = [
            entity.get("name", "")
            for entity in extracted.get("tax_entities", [])
            if isinstance(entity, dict) and entity.get("name")
        ]
        return fetch_memory_context(db, user_id, concepts, entities, limit=3)
    except Exception as exc:
        logger.warning("memory_context_fetch_failed", error=str(exc), user_id=user_id)
        return {"prior_resolutions": [], "unresolved_queries": []}


def _persist_memory(query: str, user_id: str, session_id: str, answer_json: str) -> None:
    cfg = load_config()
    if not cfg:
        return

    try:
        db = get_client(cfg)
        upsert_basic_user_session(db, user_id, session_id)
        extracted = extract_memory(f"{query}\n\n{answer_json}") or {}
        write_memory(
            db,
            user_id=user_id,
            session_id=session_id,
            query_text=query,
            intent=extracted.get("intent", "tax_query"),
            resolution_status=extracted.get("resolution_status", "answered"),
            confidence=0.7,
            concepts=extracted.get("concepts", []) or [],
            tax_entities=extracted.get("tax_entities", []) or [],
            jurisdictions=extracted.get("jurisdictions", []) or [],
            tax_forms=extracted.get("tax_forms", []) or [],
            ambiguities=extracted.get("ambiguities", []) or [],
        )
    except Exception as exc:
        logger.warning("live_memory_persist_failed", error=str(exc), user_id=user_id, session_id=session_id)


async def _classify_jurisdiction(query: str) -> dict[str, Any]:
    from agents.adk.geo_router.agent import determine_jurisdiction_with_llm, keyword_based_routing

    try:
        result = await determine_jurisdiction_with_llm(query)
        if result.get("jurisdiction") in {"india", "usa", "both"}:
            return result
    except Exception as exc:
        logger.warning("jurisdiction_llm_failed", error=str(exc))

    fallback = await keyword_based_routing(query)
    return {
        "jurisdiction": fallback.get("jurisdiction", "both"),
        "reasoning": fallback.get("method", "keyword"),
        "confidence": 0.5,
    }


async def run_live_query(query: str, user_id: str, session_id: str) -> dict[str, Any]:
    routing = await _classify_jurisdiction(query)
    jurisdiction = routing.get("jurisdiction", "both")
    selected = ["india", "usa"] if jurisdiction == "both" else [jurisdiction]
    memory_context = _load_memory_context(query, user_id)

    tasks = []
    labels: list[tuple[str, str]] = []
    for region in selected:
        for source, endpoint in SOURCE_ENDPOINTS.get(region, {}).items():
            tasks.append(_call_a2a_agent(endpoint, query))
            labels.append((region, source))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    delegation_results: dict[str, Any] = {}
    all_evidence: list[dict[str, Any]] = []
    sources: list[str] = []
    source_statuses: list[dict[str, Any]] = []

    for (region, source), result in zip(labels, results):
        key = f"{region}:{source}"
        if isinstance(result, Exception):
            delegation_results[key] = {"status": "error", "error": str(result)}
            source_statuses.append(
                _source_status_payload(
                    source=source,
                    region=region,
                    status="error",
                    error=str(result),
                )
            )
            continue

        text = result.get("text", "")
        parsed = _parse_agent_payload(text)
        evidence = _extract_evidence(source, parsed)
        delegation_results[key] = {
            "status": result.get("status", "success"),
            "source": source,
            "region": region,
            "text": text,
            "parsed": parsed,
            "evidence": evidence,
        }
        source_statuses.append(
            _source_status_payload(
                source=source,
                region=region,
                status=result.get("status", "success"),
                error=result.get("error", ""),
                evidence_count=len(evidence),
            )
        )
        if evidence:
            all_evidence.extend(evidence)
            sources.append(SOURCE_LABELS.get(source, source))

    claims = merge_evidence_into_claims(all_evidence)
    contradictions = detect_contradictions(_build_contradiction_input(claims))
    synthesized = synthesize_response(query, claims, contradictions, source_statuses)
    graph_events = _build_graph_events(
        session_id=session_id,
        query=query,
        jurisdiction=jurisdiction,
        source_statuses=source_statuses,
        claims=claims,
        contradictions=contradictions,
        memory_context=memory_context,
    )

    content = {
        "query": query,
        "jurisdiction": jurisdiction,
        "sources": list(dict.fromkeys(sources)),
        "claims": claims,
        "contradictions": contradictions,
        "source_statuses": source_statuses,
        "graph_events": graph_events,
        "graph_summary": {
            "session_id": session_id,
            "active_sources": len(source_statuses),
            "claim_count": len(claims),
            "contradiction_count": len(contradictions),
            "memory_loaded": bool(
                memory_context.get("prior_resolutions")
                or memory_context.get("unresolved_queries")
            ),
        },
        "synthesized_response": synthesized,
        "memory_context": memory_context,
    }

    if claims:
        _persist_memory(query, user_id, session_id, json.dumps(content))

    return {
        "routing": routing,
        "delegation_results": delegation_results,
        "content": content,
    }
