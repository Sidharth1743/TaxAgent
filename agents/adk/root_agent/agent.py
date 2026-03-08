#!/usr/bin/env python3
"""
<<<<<<< HEAD
Root A2A agent orchestrating CAClubIndia, TaxTMI, TurboTax, and TaxProfBlog agents via ADK.
=======
Root A2A agent orchestrating CAClubIndia and TaxTMI agents via ADK.
>>>>>>> 431f43074796d50431746738d2e5a86ef7718384
Produces evidence-weighted answer with inline URL citations.
"""

import asyncio
import json
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx

from google.adk.agents.llm_agent import Agent
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from dotenv import load_dotenv

<<<<<<< HEAD
from memory.extractor import extract_memory
from memory.spanner_graph import load_config, get_client, fetch_memory_context, upsert_basic_user_session, write_memory

=======
>>>>>>> 431f43074796d50431746738d2e5a86ef7718384
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# Load environment variables (e.g., GOOGLE_API_KEY) from .env
load_dotenv(os.path.join(ROOT, ".env"))



async def _call_a2a_agent(agent_url: str, query: str) -> Dict[str, Any]:
    from a2a.client.client import ClientConfig
    from a2a.client.client_factory import ClientFactory
    from a2a.types import Message, Part, TaskQueryParams, TaskState, TextPart
    from a2a.client.errors import A2AClientTimeoutError

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


async def fetch_caclub_a2a(query: str) -> Dict[str, Any]:
    result = await _call_a2a_agent("http://localhost:8001", query)
    raw = result.get("raw")
    text = _extract_text_from_task(raw)
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None
    return {"source": "caclub", "parsed": parsed, "raw_text": text}


async def fetch_taxtmi_a2a(query: str) -> Dict[str, Any]:
    result = await _call_a2a_agent("http://localhost:8002", query)
    raw = result.get("raw")
    text = _extract_text_from_task(raw)
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None
    return {"source": "taxtmi", "parsed": parsed, "raw_text": text}


<<<<<<< HEAD
async def fetch_turbotax_a2a(query: str) -> Dict[str, Any]:
    result = await _call_a2a_agent("http://localhost:8003", query)
    raw = result.get("raw")
    text = _extract_text_from_task(raw)
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None
    return {"source": "turbotax", "parsed": parsed, "raw_text": text}


async def fetch_taxprofblog_a2a(query: str) -> Dict[str, Any]:
    result = await _call_a2a_agent("http://localhost:8004", query)
    raw = result.get("raw")
    text = _extract_text_from_task(raw)
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None
    return {"source": "taxprofblog", "parsed": parsed, "raw_text": text}


=======
>>>>>>> 431f43074796d50431746738d2e5a86ef7718384
async def fetch_both_a2a(query: str) -> Dict[str, Any]:
    caclub_res, taxtmi_res = await asyncio.gather(
        fetch_caclub_a2a(query), fetch_taxtmi_a2a(query)
    )
    return {"caclub": caclub_res, "taxtmi": taxtmi_res}


<<<<<<< HEAD
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
            citations = [u for u in citations if u in allowed_urls] or [next(iter(allowed_urls))]
        claims_out.append({"claim": claim_text, "citations": citations})

    message = draft.get("message") if isinstance(draft, dict) else None
    payload = {"query": query, "sources": sources, "claims": claims_out}
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


=======
>>>>>>> 431f43074796d50431746738d2e5a86ef7718384
def _evidence_from_parsed(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    evidence = []
    if not parsed:
        return evidence
    for ev in parsed.get("evidence", []):
        evidence.append(ev)
    return evidence


root_agent = Agent(
    name="taxclarity_root",
    model="gemini-3.1-flash-lite-preview",
<<<<<<< HEAD
    description="Reconciles CAClubIndia, TaxTMI, TurboTax, and TaxProfBlog evidence into a single cited answer.",
=======
    description="Reconciles CAClubIndia and TaxTMI evidence into a single cited answer.",
>>>>>>> 431f43074796d50431746738d2e5a86ef7718384
    instruction=(
        "You are the root agent. For every user query:\n"
        "1) If the user specifies a source directive, follow it:\n"
        "   - 'source:caclub' => only CAClubIndia\n"
        "   - 'source:taxtmi' => only TaxTMI\n"
<<<<<<< HEAD
        "   - 'source:turbotax' => only TurboTax\n"
        "   - 'source:taxprofblog' => only TaxProfBlog\n"
        "   - 'source:us' => TurboTax + TaxProfBlog\n"
        "   - 'source:all' => CAClubIndia + TaxTMI + TurboTax + TaxProfBlog\n"
        "   - 'source:both' or no directive => CAClubIndia + TaxTMI\n"
        "2) If source is both, call fetch_both_a2a (parallel) to get evidence.\n"
        "   If source is us, call fetch_us_a2a (parallel) to get evidence.\n"
        "   If source is all, call fetch_all_a2a (parallel) to get evidence.\n"
=======
        "   - 'source:both' or no directive => both\n"
        "2) If source is both, call fetch_both_a2a (parallel) to get evidence.\n"
>>>>>>> 431f43074796d50431746738d2e5a86ef7718384
        "   If source is single, call the matching single-source tool.\n"
        "3) Use ONLY the returned JSON evidence (title/url/snippet/date/reply_count).\n"
        "4) Merge evidence; if both sources support the same claim, raise confidence.\n"
        "5) Prefer replies (threads with responses) for higher confidence.\n"
<<<<<<< HEAD
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
        "12) ALWAYS call get_memory_context_tool next and use it as context.\n"
        "13) After drafting your answer JSON, call finalize_response and return ONLY its JSON.\n"
        "14) After returning, call persist_memory_tool to store memory (use session_id='session:'+uuid4()).\n"
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
    ],
=======
        "6) Provide the final answer with inline URL citations per claim.\n"
        "7) Keep citations as a list of URLs next to each claim.\n"
    ),
    tools=[fetch_caclub_a2a, fetch_taxtmi_a2a, fetch_both_a2a],
>>>>>>> 431f43074796d50431746738d2e5a86ef7718384
)


a2a_app = to_a2a(root_agent, port=8000)
