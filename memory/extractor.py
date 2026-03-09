#!/usr/bin/env python3
"""Gemini-based structured extractor for tax memory graph."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - optional runtime dependency
    genai = None

logger = logging.getLogger(__name__)

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

_configured = False


def _ensure_configured() -> bool:
    global _configured
    if not genai:
        return False
    if _configured:
        return True
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        return False
    genai.configure(api_key=api_key)
    _configured = True
    return True


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def extract_memory(text: str, max_retries: int = 3) -> Dict[str, Any]:
    if not _ensure_configured():
        return {}

    model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

    for attempt in range(max_retries):
        try:
            resp = model.generate_content([EXTRACTOR_PROMPT, text])
            raw = _strip_code_fences(resp.text)
            data = json.loads(raw)
            if not isinstance(data, dict):
                logger.warning("Extractor returned non-dict (attempt %d)", attempt + 1)
                continue
            if "concepts" not in data or "intent" not in data:
                logger.warning("Extractor response missing required keys (attempt %d)", attempt + 1)
                continue
            return data
        except Exception:
            logger.exception("Extractor attempt %d failed", attempt + 1)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    logger.error("All %d extractor attempts failed for input length %d", max_retries, len(text))
    return {}
