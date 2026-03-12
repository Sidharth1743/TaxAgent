#!/usr/bin/env python3
"""
Root A2A agent orchestrating CAClubIndia, TaxTMI, TurboTax, and TaxProfBlog agents via ADK.
Produces evidence-weighted answer with inline URL citations.
"""

import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional

from agents.calculation_agent import compute_tax_liability

import httpx
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents.llm_agent import Agent

from config import (
    CACLUB_AGENT_URL,
    ROOT_AGENT_MODEL,
    TAXPROFBLOG_AGENT_URL,
    TAXTMI_AGENT_URL,
    TURBOTAX_AGENT_URL,
)
from agents.contradiction_agent import detect_contradictions
from memory.extractor import extract_memory
from memory.pageindex_store import query_pageindex, ask_document
from memory.spanner_graph import (
    fetch_memory_context,
    get_client,
    load_config,
    upsert_basic_user_session,
    write_memory,
)


async def _call_a2a_agent(agent_url: str, query: str) -> Dict[str, Any]:
    from a2a.client.client import ClientConfig
    from a2a.client.client_factory import ClientFactory
    from a2a.client.errors import A2AClientTimeoutError
    from a2a.types import Message, Part, TaskQueryParams, TaskState, TextPart

    httpx_client = httpx.AsyncClient(timeout=httpx.Timeout(180.0))
    try:
        client = await ClientFactory.connect(
            agent_url,
            client_config=ClientConfig(
                streaming=False, polling=True, httpx_client=httpx_client
            ),
            resolver_http_kwargs={"timeout": 180.0},
        )
    except A2AClientTimeoutError as e:
        return {"raw": None, "error": f"Agent card timeout: {e}"}

    message = Message(
        messageId=str(uuid.uuid4()),
        role="user",
        parts=[Part(root=TextPart(text=query))],
    )

    task_id: Optional[str] = None
    try:
        async for result in client.send_message(message):
            if isinstance(result, tuple):
                result = result[0]
            if hasattr(result, "kind") and result.kind == "task":
                task_id = result.id
            elif hasattr(result, "kind") and result.kind == "message":
                return {"raw": result}
    except A2AClientTimeoutError as e:
        return {"raw": None, "error": f"Send message timeout: {e}"}

    if not task_id:
        return {"raw": None, "error": "No task returned"}

    # Poll for completion
    for _ in range(180):
        try:
            task = await client.get_task(
                TaskQueryParams(id=task_id, historyLength=50)
            )
        except A2AClientTimeoutError as e:
            return {"raw": None, "error": f"Get task timeout: {e}"}
        if task.status.state in {
            TaskState.completed,
            TaskState.failed,
            TaskState.canceled,
            TaskState.rejected,
        }:
            return {"raw": task}
        await asyncio.sleep(1)
    return {"raw": None, "error": "Timed out waiting for task"}


def _extract_text_from_task(task: Any) -> str:
    if not task:
        return ""
    # Prefer status message
    msg = getattr(task.status, "message", None) if hasattr(task, "status") else None
    if msg and getattr(msg, "parts", None):
        out = []
        for p in msg.parts:
            part = getattr(p, "root", None) or p
            if hasattr(part, "text"):
                out.append(part.text)
        return "\n".join(out)
    # Fallback to history
    history = getattr(task, "history", None) or []
    parts = []
    for m in history:
        if getattr(m, "role", "") == "agent":
            for p in getattr(m, "parts", []) or []:
                part = getattr(p, "root", None) or p
                if hasattr(part, "text"):
                    parts.append(part.text)
    return "\n".join(parts)


def _make_fetcher(source_name: str, agent_url: str):
    """Factory that creates an async A2A fetch function for a given source."""
    async def _fetch(query: str) -> Dict[str, Any]:
        result = await _call_a2a_agent(agent_url, query)
        raw = result.get("raw")
        text = _extract_text_from_task(raw)
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        return {"source": source_name, "parsed": parsed, "raw_text": text}
    _fetch.__name__ = f"fetch_{source_name}_a2a"
    _fetch.__doc__ = f"Fetch evidence from {source_name} via A2A"
    return _fetch


fetch_caclub_a2a = _make_fetcher("caclub", CACLUB_AGENT_URL)
fetch_taxtmi_a2a = _make_fetcher("taxtmi", TAXTMI_AGENT_URL)
fetch_turbotax_a2a = _make_fetcher("turbotax", TURBOTAX_AGENT_URL)
fetch_taxprofblog_a2a = _make_fetcher("taxprofblog", TAXPROFBLOG_AGENT_URL)


async def fetch_both_a2a(query: str) -> Dict[str, Any]:
    caclub_res, taxtmi_res = await asyncio.gather(
        fetch_caclub_a2a(query), fetch_taxtmi_a2a(query)
    )
    return {"caclub": caclub_res, "taxtmi": taxtmi_res}


async def fetch_us_a2a(query: str) -> Dict[str, Any]:
    turbotax_res, taxprof_res = await asyncio.gather(
        fetch_turbotax_a2a(query), fetch_taxprofblog_a2a(query)
    )
    return {"turbotax": turbotax_res, "taxprofblog": taxprof_res}


async def fetch_all_a2a(query: str) -> Dict[str, Any]:
    caclub_res, taxtmi_res, turbotax_res, taxprof_res = await asyncio.gather(
        fetch_caclub_a2a(query),
        fetch_taxtmi_a2a(query),
        fetch_turbotax_a2a(query),
        fetch_taxprofblog_a2a(query),
    )
    return {
        "caclub": caclub_res,
        "taxtmi": taxtmi_res,
        "turbotax": turbotax_res,
        "taxprofblog": taxprof_res,
    }


def _directive_sources(query: str) -> List[str]:
    q = query.lower()
    if "source:us" in q:
        return ["TurboTax", "TaxProfBlog"]
    if "source:all" in q:
        return ["CAClubIndia", "TaxTMI", "TurboTax", "TaxProfBlog"]
    if "source:turbotax" in q:
        return ["TurboTax"]
    if "source:taxprofblog" in q:
        return ["TaxProfBlog"]
    if "source:caclub" in q:
        return ["CAClubIndia"]
    if "source:taxtmi" in q:
        return ["TaxTMI"]
    # default both
    return ["CAClubIndia", "TaxTMI"]


def _flatten_evidence(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not parsed:
        return []
    if isinstance(parsed, dict) and "evidence" in parsed:
        ev = parsed.get("evidence", [])
        return [e for e in ev if isinstance(e, dict)]
    return parsed.get("evidence", [])


def finalize_response(query: str, evidence: Dict[str, Any], draft_json: str) -> Dict[str, Any]:
    """Enforce sources and URL citations based on directive."""
    sources = _directive_sources(query)
    if "source:" not in query.lower():
        # Infer from evidence keys when directive is absent in the provided query.
        keys = set((evidence or {}).keys())
        inferred = []
        if "turbotax" in keys:
            inferred.append("TurboTax")
        if "taxprofblog" in keys:
            inferred.append("TaxProfBlog")
        if "caclub" in keys:
            inferred.append("CAClubIndia")
        if "taxtmi" in keys:
            inferred.append("TaxTMI")
        if inferred:
            sources = inferred
    # Parse draft
    try:
        draft = json.loads(draft_json)
    except Exception:
        draft = {"query": query, "sources": sources, "claims": []}

    # Collect allowed URLs from evidence
    allowed_urls = set()
    for src_key, payload in (evidence or {}).items():
        parsed = None
        if isinstance(payload, dict):
            parsed = payload.get("parsed")
            if parsed is None and "evidence" in payload:
                parsed = payload
        for ev in _flatten_evidence(parsed or {}):
            url = ev.get("url") or ev.get("link")
            if isinstance(url, str) and url.startswith("http"):
                allowed_urls.add(url)

    # Normalize claims
    claims_out = []
    for c in draft.get("claims", []) if isinstance(draft, dict) else []:
        claim_text = c.get("claim") or c.get("text") or ""
        citations = c.get("citations") or []
        # Keep only URLs; if empty, attach one from evidence or draft URLs
        citations = [u for u in citations if isinstance(u, str) and u.startswith("http")]
        if allowed_urls:
            citations = [u for u in citations if u in allowed_urls]
        claims_out.append({"claim": claim_text, "citations": citations})

    # Drop claims with no valid citations (no fabrication fallback)
    claims_out = [c for c in claims_out if c["citations"]]

    message = draft.get("message") if isinstance(draft, dict) else None
    payload = {"query": query, "sources": sources, "claims": claims_out}

    # Flag when all claims were dropped due to lack of evidence
    if not claims_out:
        payload["no_evidence"] = True
        payload["message"] = "I couldn't find expert evidence for this topic"
    if message:
        payload["message"] = message
    return payload


def get_memory_context_tool(query: str, user_id: str) -> Dict[str, Any]:
    cfg = load_config()
    if not cfg:
        return {"prior_resolutions": [], "unresolved_queries": []}
    try:
        db = get_client(cfg)
        extracted = extract_memory(query)
        concepts = extracted.get("concepts", []) if extracted else []
        entities = [e.get("name", "") for e in extracted.get("tax_entities", []) if isinstance(e, dict)]
        return fetch_memory_context(db, user_id, concepts, entities, limit=3)
    except Exception:
        return {"prior_resolutions": [], "unresolved_queries": []}


def is_smalltalk_tool(query: str) -> Dict[str, Any]:
    q = (query or "").strip().lower()
    if not q:
        return {"is_smalltalk": True, "intent": "empty"}
    smalltalk = {
        "hi",
        "hello",
        "hey",
        "yo",
        "sup",
        "good morning",
        "good afternoon",
        "good evening",
        "thanks",
        "thank you",
        "thx",
        "ok",
        "okay",
        "cool",
        "nice",
    }
    if q in smalltalk or len(q.split()) <= 2:
        return {"is_smalltalk": True, "intent": "smalltalk"}
    return {"is_smalltalk": False, "intent": "tax_query"}


def smalltalk_response_tool(query: str) -> Dict[str, Any]:
    friendly = "Hi! Thanks for your message."
    q = (query or "").strip()
    if q:
        friendly = f"Thanks for sharing: \"{q}\"."
    message = (
        f"{friendly} By the way, I am your dedicated Tax Advisor. "
        "I have specialized features to help you with: "
        "Memory Context (I can remember your past filings and specific tax situation), "
        "Data Retrieval (I can fetch a2a financial data and account details), and "
        "Finalization (I can help finalize your tax responses and persist them to your record). "
        "How should I help you today?"
    )
    return {"query": q or "smalltalk", "sources": [], "message": message, "claims": []}


def persist_memory_tool(query: str, user_id: str, session_id: str, answer_json: str) -> Dict[str, Any]:
    cfg = load_config()
    if not cfg:
        return {"ok": False, "reason": "no_spanner_config"}
    try:
        db = get_client(cfg)
        upsert_basic_user_session(db, user_id, session_id)
        extracted = extract_memory(query + "\n\n" + answer_json)
        if not extracted:
            extracted = {}
        write_memory(
            db,
            user_id=user_id,
            session_id=session_id,
            query_text=query,
            intent=extracted.get("intent", ""),
            resolution_status=extracted.get("resolution_status", "answered"),
            confidence=0.6,
            concepts=extracted.get("concepts", []) or [],
            tax_entities=extracted.get("tax_entities", []) or [],
            jurisdictions=extracted.get("jurisdictions", []) or [],
            tax_forms=extracted.get("tax_forms", []) or [],
            ambiguities=extracted.get("ambiguities", []) or [],
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def check_contradictions(claims_json: str) -> Dict[str, Any]:
    """Check for contradictions between source claims.

    Args:
        claims_json: JSON string of claims list, each with keys:
            claim (str), citations (list[str]), source (str)

    Returns:
        Dict with 'contradictions' list (may be empty if sources agree).
    """
    try:
        claims = json.loads(claims_json)
    except Exception:
        return {"contradictions": [], "error": "Invalid JSON"}
    if not isinstance(claims, list):
        return {"contradictions": [], "error": "Expected a list of claims"}
    result = detect_contradictions(claims)
    return {"contradictions": result}


def compute_tax_tool(fields_json: str, form_type: str, jurisdiction: str) -> Dict[str, Any]:
    """Compute tax liability from extracted document fields.

    Args:
        fields_json: JSON string of field name->value pairs (from document extraction)
        form_type: "w2", "1099", or "form16"
        jurisdiction: "usa" or "india"

    Returns:
        Tax computation result with liability amounts and optimization suggestions.
    """
    try:
        fields = json.loads(fields_json)
    except Exception:
        return {"error": "Invalid fields JSON"}
    return compute_tax_liability(fields, form_type, jurisdiction)


def check_pageindex_tool(query: str) -> Dict[str, Any]:
    """Check PageIndex for previously indexed expert content before scraping.

    Call this BEFORE calling any scraper agent. If it returns content,
    you can skip scraping and use the cached expert evidence directly.

    Args:
        query: The user's tax question.

    Returns:
        Dict with 'hit' (bool), 'answer' (str if hit), 'source' ('pageindex').
        If hit=False, proceed with normal scraper flow.
    """
    result = query_pageindex(query)
    if result:
        return {"hit": True, "answer": result["answer"], "source": "pageindex"}
    return {"hit": False}


def ask_pageindex_document_tool(doc_id: str, question: str) -> Dict[str, Any]:
    """Ask a question about a document uploaded to PageIndex.

    Use when the user asks follow-up questions about an uploaded tax form
    that was submitted to PageIndex.

    Args:
        doc_id: The PageIndex document ID (from upload).
        question: The user's question about the document.

    Returns:
        Dict with 'answer' key on success, 'error' on failure.
    """
    answer = ask_document(doc_id, question)
    if answer:
        return {"answer": answer}
    return {"error": "Could not get answer from PageIndex"}


root_agent = Agent(
    name="taxclarity_root",
    model=ROOT_AGENT_MODEL,
    description="Reconciles CAClubIndia, TaxTMI, TurboTax, and TaxProfBlog evidence into a single cited answer.",
    instruction=(
        "You are the root agent. For every user query:\n"
        "1) If the user specifies a source directive, follow it:\n"
        "   - 'source:caclub' => only CAClubIndia\n"
        "   - 'source:taxtmi' => only TaxTMI\n"
        "   - 'source:turbotax' => only TurboTax\n"
        "   - 'source:taxprofblog' => only TaxProfBlog\n"
        "   - 'source:us' => TurboTax + TaxProfBlog\n"
        "   - 'source:all' => CAClubIndia + TaxTMI + TurboTax + TaxProfBlog\n"
        "   - 'source:both' or no directive => CAClubIndia + TaxTMI\n"
        "2) If source is both, call fetch_both_a2a (parallel) to get evidence.\n"
        "   If source is us, call fetch_us_a2a (parallel) to get evidence.\n"
        "   If source is all, call fetch_all_a2a (parallel) to get evidence.\n"
        "   If source is single, call the matching single-source tool.\n"
        "3) Use ONLY the returned JSON evidence (title/url/snippet/date/reply_count).\n"
        "4) Merge evidence; if both sources support the same claim, raise confidence.\n"
        "5) Prefer replies (threads with responses) for higher confidence.\n"
        "6) Return ONLY valid JSON (no markdown, no prose).\n"
        "7) JSON schema:\n"
        "   {\n"
        "     \"query\": string,\n"
        "     \"sources\": [string],\n"
        "     \"message\": string (optional, for smalltalk),\n"
        "     \"claims\": [\n"
        "       {\n"
        "         \"claim\": string,\n"
        "         \"citations\": [string]\n"
        "       }\n"
        "     ]\n"
        "   }\n"
        "8) Citations MUST be URLs from evidence items. Do NOT use source names as citations.\n"
        "9) Always include a non-empty citations list per claim; if evidence is weak, still cite the closest relevant URL.\n"
        "10) The \"sources\" list MUST exactly match the data sources you called:\n"
        "    - source:us => [\"TurboTax\", \"TaxProfBlog\"]\n"
        "    - source:both => [\"CAClubIndia\", \"TaxTMI\"]\n"
        "    - source:all => [\"CAClubIndia\", \"TaxTMI\", \"TurboTax\", \"TaxProfBlog\"]\n"
        "    - single source => only that source.\n"
        "11) ALWAYS call is_smalltalk_tool first.\n"
        "    - If is_smalltalk=true, call smalltalk_response_tool and return ONLY its JSON.\n"
        "11.5) BEFORE calling any scraper agent (fetch_caclub_a2a, fetch_taxtmi_a2a, etc.), "
        "call check_pageindex_tool first. If it returns hit=true, use its answer as cached "
        "expert evidence and skip scraping. Only call scraper agents if hit=false.\n"
        "12) ALWAYS call get_memory_context_tool next and use it as context.\n"
        "13) After drafting your answer JSON, call finalize_response and return ONLY its JSON.\n"
        "14) After finalizing, call check_contradictions with your claims JSON to detect source disagreements. Include any contradictions in your response.\n"
        "15) After returning, call persist_memory_tool to store memory (use session_id='session:'+uuid4()).\n"
        "16) When the user has uploaded a tax document and confirmed the data, or provides income/salary figures, "
        "call compute_tax_tool to calculate their tax liability. Present the results conversationally, "
        "highlighting the recommended regime and optimization suggestions.\n"
        "17) If a document was uploaded to PageIndex (doc_id available), use ask_pageindex_document_tool "
        "for follow-up questions about the document's content.\n"
    ),
    tools=[
        fetch_caclub_a2a,
        fetch_taxtmi_a2a,
        fetch_turbotax_a2a,
        fetch_taxprofblog_a2a,
        fetch_both_a2a,
        fetch_us_a2a,
        fetch_all_a2a,
        get_memory_context_tool,
        is_smalltalk_tool,
        smalltalk_response_tool,
        persist_memory_tool,
        finalize_response,
        check_contradictions,
        compute_tax_tool,
        check_pageindex_tool,
        ask_pageindex_document_tool,
    ],
)


from backend.health import with_health_check

a2a_app = with_health_check(to_a2a(root_agent, port=8000))
