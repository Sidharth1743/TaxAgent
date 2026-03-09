#!/usr/bin/env python3
"""Memory tools for the root agent — fetch and persist to Spanner graph."""

from __future__ import annotations

from typing import Any, Dict

from memory.extractor import extract_memory
from memory.spanner_graph import (
    load_config,
    get_client,
    fetch_memory_context,
    upsert_basic_user_session,
    write_memory,
)

from .query_utils import _extract_sections_and_act


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
        concepts = extracted.get("concepts", []) or []
        section_refs, act = _extract_sections_and_act(query + " " + answer_json)
        for sec in section_refs:
            label = f"Section {sec}"
            if act:
                label = f"{label} ({act})"
            if label not in concepts:
                concepts.append(label)
        write_memory(
            db,
            user_id=user_id,
            session_id=session_id,
            query_text=query,
            intent=extracted.get("intent", ""),
            resolution_status=extracted.get("resolution_status", "answered"),
            confidence=0.6,
            concepts=concepts,
            tax_entities=extracted.get("tax_entities", []) or [],
            jurisdictions=extracted.get("jurisdictions", []) or [],
            tax_forms=extracted.get("tax_forms", []) or [],
            ambiguities=extracted.get("ambiguities", []) or [],
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "reason": str(e)}
