#!/usr/bin/env python3
"""Smalltalk detection and response tools."""

from __future__ import annotations

from typing import Any, Dict


def is_smalltalk_tool(query: str) -> Dict[str, Any]:
    q = (query or "").strip().lower()
    if not q:
        return {"is_smalltalk": True, "intent": "empty"}
    smalltalk = {
        "hi", "hello", "hey", "yo", "sup",
        "good morning", "good afternoon", "good evening",
        "thanks", "thank you", "thx",
        "ok", "okay", "cool", "nice",
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
