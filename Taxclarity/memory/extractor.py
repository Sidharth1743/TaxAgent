#!/usr/bin/env python3
"""Gemini-based structured extractor for tax memory graph."""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from config import EXTRACTOR_MODEL

try:
    from google import genai
    _HAS_GENAI = True
except ImportError:  # pragma: no cover - optional runtime dependency
    _HAS_GENAI = False


EXTRACTOR_PROMPT = """You are a structured extractor for tax-related user memory.
Return ONLY valid JSON matching this schema:
{
  "user_profile": {
    "jurisdiction_candidates": [string],
    "residency_status": string,
    "filing_status": string
  },
  "tax_entities": [
    {"name": string, "currency": string, "jurisdiction": string, "location": string, "form": string}
  ],
  "concepts": [string],
  "tax_forms": [string],
  "jurisdictions": [string],
  "ambiguities": [{"topic": string, "reason": string}],
  "intent": string,
  "resolution_status": "answered|unresolved|follow_up"
}
If a field is unknown, use empty string or empty array.
"""


def extract_memory(text: str) -> Dict[str, Any]:
    if not _HAS_GENAI:
        return {}
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        return {}
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=EXTRACTOR_MODEL,
        contents=[EXTRACTOR_PROMPT, text],
        config={"response_mime_type": "application/json"},
    )
    try:
        data = json.loads(resp.text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
