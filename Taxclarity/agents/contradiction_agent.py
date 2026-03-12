"""Contradiction detection module for TaxAgent.

Identifies disagreements between claims from different source agents
using text heuristic comparison (no LLM calls). Imported directly as
a Python module by the root agent.
"""

import re
from collections import defaultdict
from typing import Any, Dict, List, Set


def _tokenize(text: str) -> Set[str]:
    """Extract lowercase word tokens from text, stripping punctuation."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard_similarity(a: Set[str], b: Set[str]) -> float:
    """Jaccard similarity coefficient between two token sets."""
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union)


_AMOUNT_PATTERN = re.compile(
    r"(\d[\d,]*\.?\d*)\s*(?:lakh|lakhs|crore|crores|k|million|billion|%|percent|rupees|rs\.?|inr|\$|usd)",
    re.IGNORECASE,
)

_NEGATION_PHRASES = [
    "not eligible",
    "not allowed",
    "not applicable",
    "not permitted",
    "not available",
    "cannot",
    "can not",
    "ineligible",
    "disallowed",
    "prohibited",
    "no deduction",
    "no exemption",
    "no benefit",
]

_AFFIRMATION_PHRASES = [
    "eligible",
    "allowed",
    "applicable",
    "permitted",
    "available",
    "can claim",
    "entitled",
    "qualifies",
    "deduction",
    "exemption",
    "benefit",
]


def _extract_amounts(text: str) -> List[str]:
    """Extract numeric amounts with units from text."""
    return _AMOUNT_PATTERN.findall(text.lower())


def _has_negation(text: str) -> bool:
    """Check if text contains negation phrases."""
    lower = text.lower()
    return any(phrase in lower for phrase in _NEGATION_PHRASES)


def _has_affirmation(text: str) -> bool:
    """Check if text contains affirmation phrases (without negation)."""
    lower = text.lower()
    if _has_negation(text):
        return False
    return any(phrase in lower for phrase in _AFFIRMATION_PHRASES)


def _amounts_conflict(amounts_a: List[str], amounts_b: List[str]) -> bool:
    """Check if two amount lists contain different values."""
    if not amounts_a or not amounts_b:
        return False
    # Normalize: strip commas
    norm_a = {a.replace(",", "") for a in amounts_a}
    norm_b = {b.replace(",", "") for b in amounts_b}
    # Conflict if no overlap
    return len(norm_a & norm_b) == 0


def _claims_conflict(claim_a: str, claim_b: str) -> tuple[bool, str]:
    """Determine if two claims on the same topic conflict.

    Returns (is_conflict, analysis_description).
    """
    # Check amount disagreement
    amounts_a = _extract_amounts(claim_a)
    amounts_b = _extract_amounts(claim_b)
    if _amounts_conflict(amounts_a, amounts_b):
        return True, f"Different amounts cited: {amounts_a} vs {amounts_b}"

    # Check eligibility/negation disagreement
    neg_a = _has_negation(claim_a)
    neg_b = _has_negation(claim_b)
    aff_a = _has_affirmation(claim_a)
    aff_b = _has_affirmation(claim_b)

    if (neg_a and aff_b) or (aff_a and neg_b):
        return True, "Sources disagree on eligibility/applicability"

    return False, ""


def _group_by_topic(claims: List[Dict[str, Any]], threshold: float = 0.3) -> List[List[Dict[str, Any]]]:
    """Group claims by topic similarity using Jaccard on tokens.

    Only groups claims from different sources together.
    """
    if not claims:
        return []

    token_cache = []
    for c in claims:
        token_cache.append(_tokenize(c.get("claim", "")))

    groups: List[List[int]] = []
    assigned = set()

    for i in range(len(claims)):
        if i in assigned:
            continue
        group = [i]
        assigned.add(i)
        for j in range(i + 1, len(claims)):
            if j in assigned:
                continue
            sim = _jaccard_similarity(token_cache[i], token_cache[j])
            if sim >= threshold:
                group.append(j)
                assigned.add(j)
        if len(group) > 1:
            groups.append(group)

    # Convert indices to claim dicts
    return [[claims[idx] for idx in g] for g in groups]


def detect_contradictions(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect contradictions between claims from different sources.

    Args:
        claims: List of claim dicts, each with keys:
            - claim (str): The claim text
            - citations (list[str]): URLs supporting the claim
            - source (str): Source agent name (e.g. "caclub", "taxtmi")

    Returns:
        List of contradiction dicts:
            - topic (str): Summary of the contested topic
            - positions (list[dict]): Each source's position with claim, source, citations
            - analysis (str): Description of the disagreement
    """
    if not claims or len(claims) < 2:
        return []

    # Need at least 2 different sources
    sources = {c.get("source") for c in claims}
    if len(sources) < 2:
        return []

    topic_groups = _group_by_topic(claims)
    contradictions = []

    for group in topic_groups:
        # Only check groups with claims from different sources
        group_sources = {c.get("source") for c in group}
        if len(group_sources) < 2:
            continue

        # Pairwise comparison across different sources
        found_conflict = False
        analysis = ""
        for i in range(len(group)):
            if found_conflict:
                break
            for j in range(i + 1, len(group)):
                if group[i].get("source") == group[j].get("source"):
                    continue
                is_conflict, desc = _claims_conflict(
                    group[i].get("claim", ""), group[j].get("claim", "")
                )
                if is_conflict:
                    found_conflict = True
                    analysis = desc
                    break

        if found_conflict:
            # Extract common topic tokens
            all_tokens = set()
            for c in group:
                all_tokens |= _tokenize(c.get("claim", ""))
            # Use first few shared tokens as topic summary
            topic = " ".join(sorted(all_tokens)[:6])

            positions = [
                {
                    "source": c.get("source", ""),
                    "claim": c.get("claim", ""),
                    "citations": c.get("citations", []),
                }
                for c in group
            ]
            contradictions.append({
                "topic": topic,
                "positions": positions,
                "analysis": analysis,
            })

    return contradictions
