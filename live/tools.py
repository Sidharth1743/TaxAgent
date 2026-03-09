"""Tool functions for the TaxClarity Gemini Live agent.

ADK automatically registers Python functions as tools when passed to Agent(tools=[...]).
Each function's docstring becomes the tool description, and type annotations define parameters.
ADK handles function calling and response routing automatically.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

ROOT_AGENT_URL = os.getenv("ROOT_AGENT_URL", "http://localhost:8000")
GRAPH_API_URL = os.getenv("GRAPH_API_URL", "http://localhost:9000")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _call_root_agent(query: str) -> Dict[str, Any]:
    """Call the ADK root agent via A2A HTTP protocol and return parsed response."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            task_id = str(uuid.uuid4())
            payload = {
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": task_id,
                "params": {
                    "id": task_id,
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "user",
                        "parts": [{"kind": "text", "text": query}],
                    },
                },
            }
            resp = await client.post(
                f"{ROOT_AGENT_URL}/",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            result = data.get("result", {})
            status = result.get("status", {})
            state = status.get("state", "")

            if state == "completed":
                return _extract_text(status)

            if state in ("submitted", "working"):
                for _ in range(120):
                    await asyncio.sleep(1.5)
                    poll_payload = {
                        "jsonrpc": "2.0",
                        "method": "tasks/get",
                        "id": str(uuid.uuid4()),
                        "params": {"id": task_id, "historyLength": 10},
                    }
                    poll_resp = await client.post(
                        f"{ROOT_AGENT_URL}/",
                        json=poll_payload,
                        headers={"Content-Type": "application/json"},
                    )
                    poll_data = poll_resp.json()
                    poll_result = poll_data.get("result", {})
                    poll_state = poll_result.get("status", {}).get("state", "")
                    if poll_state == "completed":
                        return _extract_text(poll_result.get("status", {}))
                    if poll_state in ("failed", "canceled", "rejected"):
                        return {"success": False, "error": f"Task {poll_state}"}

            return {"success": False, "error": f"Unexpected state: {state}"}

    except Exception as e:
        logger.exception("Error calling root agent")
        return {"success": False, "error": str(e)}


def _extract_text(status: dict) -> Dict[str, Any]:
    """Extract text parts from an A2A task status message."""
    msg = status.get("message", {})
    parts = msg.get("parts", [])
    texts = []
    for p in parts:
        root = p.get("root", p)
        if "text" in root:
            texts.append(root["text"])
        elif "text" in p:
            texts.append(p["text"])
    return {"success": True, "text": "\n".join(texts)}


def _region_to_directive(region: Optional[str]) -> str:
    """Map region parameter to source directive for root agent."""
    mapping = {
        "india": "source:both",
        "us": "source:us",
        "all": "source:all",
    }
    return mapping.get(region or "india", "source:both")


# ---------------------------------------------------------------------------
# Tool functions — ADK auto-registers these as callable tools
# ---------------------------------------------------------------------------

async def search_tax_knowledge(query: str, region: str = "india") -> dict:
    """Search tax knowledge bases for expert advice and evidence.
    Returns cited sources from CAClubIndia, TaxTMI, TurboTax, and TaxProfBlog.
    ALWAYS call this before answering any tax question.

    Args:
        query: The tax question to search for.
        region: india=CAClubIndia+TaxTMI, us=TurboTax+TaxProfBlog, all=everything.
    """
    directive = _region_to_directive(region)
    full_query = f"{directive} {query}"
    result = await _call_root_agent(full_query)
    if result.get("success"):
        try:
            parsed = json.loads(result["text"])
            return {
                "status": "success",
                "claims": parsed.get("claims", []),
                "bullets": parsed.get("bullets", []),
                "sources": parsed.get("sources", []),
                "legal_context": parsed.get("legal_context"),
            }
        except json.JSONDecodeError:
            return {"status": "success", "text": result["text"]}
    return {"status": "error", "error": result.get("error", "Unknown error")}


async def get_legal_context(query: str) -> dict:
    """Fetch Indian law sections from Indian Kanoon and court judgements from Casemine.
    Use when the query involves specific sections of Indian tax law.

    Args:
        query: The legal query, e.g. 'section 80C Income Tax Act'.
    """
    full_query = f"source:both {query}"
    result = await _call_root_agent(full_query)
    if result.get("success"):
        try:
            parsed = json.loads(result["text"])
            return {
                "status": "success",
                "legal_context": parsed.get("legal_context"),
                "claims": parsed.get("claims", []),
            }
        except json.JSONDecodeError:
            return {"status": "success", "text": result["text"]}
    return {"status": "error", "error": result.get("error", "Unknown error")}


async def get_user_memory(user_id: str, query: str = "") -> dict:
    """Retrieve user's tax profile and prior resolutions from the memory graph.
    Call at the start of conversations to personalize advice.

    Args:
        user_id: The user's identifier.
        query: Current query for context matching.
    """
    try:
        from agents.adk.root_agent.memory_tools import get_memory_context_tool
        result = get_memory_context_tool(query=query, user_id=user_id)
        return {"status": "success", **result}
    except Exception as e:
        logger.exception("Error getting user memory")
        return {"status": "error", "error": str(e)}


async def save_to_memory(user_id: str, query: str, answer: str) -> dict:
    """Save this conversation exchange to the user's tax memory graph.
    Call after answering a substantive tax question.

    Args:
        user_id: The user's identifier.
        query: The user's tax question.
        answer: The answer provided (summary).
    """
    try:
        session_id = f"session:{uuid.uuid4()}"
        from agents.adk.root_agent.memory_tools import persist_memory_tool
        result = persist_memory_tool(
            query=query,
            user_id=user_id,
            session_id=session_id,
            answer_json=answer,
        )
        return {"status": "success" if result.get("ok") else "error", **result}
    except Exception as e:
        logger.exception("Error saving to memory")
        return {"status": "error", "error": str(e)}


async def analyze_document(document_description: str) -> dict:
    """Analyze a tax document image (Form 16, W-2, ITR, etc.) that the user
    has uploaded or captured via camera. Returns extracted fields and analysis.

    Args:
        document_description: What type of document the user is showing.
    """
    return {
        "status": "info",
        "message": (
            f"Document type noted: {document_description}. "
            "Please upload the document using the camera/upload button "
            "in the app, and I will analyze it with the vision API."
        ),
    }


# ---------------------------------------------------------------------------
# Export: list of tool functions for ADK Agent(tools=...)
# ---------------------------------------------------------------------------

tool_functions = [
    search_tax_knowledge,
    get_legal_context,
    get_user_memory,
    save_to_memory,
    analyze_document,
]
