#!/usr/bin/env python3
"""
Root A2A agent orchestrating CAClubIndia and TaxTMI agents via ADK.
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


async def fetch_both_a2a(query: str) -> Dict[str, Any]:
    caclub_res, taxtmi_res = await asyncio.gather(
        fetch_caclub_a2a(query), fetch_taxtmi_a2a(query)
    )
    return {"caclub": caclub_res, "taxtmi": taxtmi_res}


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
    description="Reconciles CAClubIndia and TaxTMI evidence into a single cited answer.",
    instruction=(
        "You are the root agent. For every user query:\n"
        "1) If the user specifies a source directive, follow it:\n"
        "   - 'source:caclub' => only CAClubIndia\n"
        "   - 'source:taxtmi' => only TaxTMI\n"
        "   - 'source:both' or no directive => both\n"
        "2) If source is both, call fetch_both_a2a (parallel) to get evidence.\n"
        "   If source is single, call the matching single-source tool.\n"
        "3) Use ONLY the returned JSON evidence (title/url/snippet/date/reply_count).\n"
        "4) Merge evidence; if both sources support the same claim, raise confidence.\n"
        "5) Prefer replies (threads with responses) for higher confidence.\n"
        "6) Provide the final answer with inline URL citations per claim.\n"
        "7) Keep citations as a list of URLs next to each claim.\n"
    ),
    tools=[fetch_caclub_a2a, fetch_taxtmi_a2a, fetch_both_a2a],
)


a2a_app = to_a2a(root_agent, port=8000)
