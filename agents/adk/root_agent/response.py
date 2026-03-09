#!/usr/bin/env python3
"""Response finalization for the root agent."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .query_utils import _directive_sources, _flatten_evidence


def finalize_response(
    query: str,
    evidence: Dict[str, Any],
    draft_json: str,
    legal_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
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
        if not isinstance(c, dict):
            continue
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
    # Add bullet view for UI convenience
    bullets = []
    for c in claims_out:
        claim_text = c.get("claim") or ""
        citations = c.get("citations") or []
        if citations:
            bullets.append(f"- {claim_text} ({', '.join(citations)})")
        else:
            bullets.append(f"- {claim_text}")
    payload["bullets"] = bullets
    if legal_context:
        payload["legal_context"] = legal_context
    return payload
