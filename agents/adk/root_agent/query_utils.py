#!/usr/bin/env python3
"""Query parsing and text utilities for the root agent."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple


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


def _flatten_evidence(parsed: dict) -> list:
    if not parsed:
        return []
    if isinstance(parsed, dict) and "evidence" in parsed:
        ev = parsed.get("evidence", [])
        return [e for e in ev if isinstance(e, dict)]
    return parsed.get("evidence", [])


def _safe_slug(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_")
    return text[:80] or "query"


def _extract_sections_and_act(text: str) -> Tuple[List[str], Optional[str]]:
    if not text:
        return [], None
    sections = set()
    for m in re.finditer(r"\\bsection\\s+(\\d+[a-zA-Z]*)", text, flags=re.IGNORECASE):
        sections.add(m.group(1).upper())
    for m in re.finditer(r"\\bsec\\.?\\s*(\\d+[a-zA-Z]*)", text, flags=re.IGNORECASE):
        sections.add(m.group(1).upper())
    act = None
    act_match = re.search(r"([A-Z][A-Za-z\\s&,-]+ Act,? \\d{4})", text)
    if act_match:
        act = act_match.group(1).strip()
    return sorted(sections), act


def _extract_section_queries(text: str) -> List[str]:
    sections, act = _extract_sections_and_act(text)
    if not sections:
        return []
    queries = []
    for sec in sections:
        if act:
            queries.append(f"section {sec} {act} doctypes:laws")
        else:
            queries.append(f"section {sec} doctypes:laws")
    return queries


def _compact_query(text: str, max_words: int = 6) -> str:
    if not text:
        return ""
    stop = {
        "the", "a", "an", "of", "in", "on", "for", "to", "and", "or",
        "with", "from", "is", "are", "was", "were", "tax", "taxes", "income",
    }
    words = [w for w in re.findall(r"[A-Za-z0-9]+", text.lower()) if w not in stop]
    return " ".join(words[:max_words])


def _build_casemine_query(user_query: str, draft_text: str) -> str:
    sections, act = _extract_sections_and_act(draft_text)
    if sections:
        sec = sections[0]
        if act:
            return f"section {sec} {act}"
        return f"section {sec}"
    compact = _compact_query(user_query) or _compact_query(draft_text)
    return compact or user_query
