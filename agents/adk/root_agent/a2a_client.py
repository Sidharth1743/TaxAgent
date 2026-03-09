#!/usr/bin/env python3
"""A2A client helpers and fetch factories for sub-agent communication."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, Optional

import httpx


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


async def _fetch_single(agent_url: str, source: str, query: str) -> Dict[str, Any]:
    result = await _call_a2a_agent(agent_url, query)
    raw = result.get("raw")
    text = _extract_text_from_task(raw)
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None
    return {"source": source, "parsed": parsed, "raw_text": text}


async def fetch_caclub_a2a(query: str) -> Dict[str, Any]:
    return await _fetch_single("http://localhost:8001", "caclub", query)


async def fetch_taxtmi_a2a(query: str) -> Dict[str, Any]:
    return await _fetch_single("http://localhost:8002", "taxtmi", query)


async def fetch_turbotax_a2a(query: str) -> Dict[str, Any]:
    return await _fetch_single("http://localhost:8003", "turbotax", query)


async def fetch_taxprofblog_a2a(query: str) -> Dict[str, Any]:
    return await _fetch_single("http://localhost:8004", "taxprofblog", query)


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
