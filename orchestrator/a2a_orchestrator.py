#!/usr/bin/env python3
"""
A2A orchestrator for CAClubIndia + TaxTMI agents.

Runs both agents with a search query, collects outputs, reconciles claims,
and emits final_result.json with inline citations.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AGENTS_DIR = os.path.join(ROOT, "agents")
DATA_DIR = os.path.join(ROOT, "data")


def _run(cmd: List[str]) -> None:
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)


def _norm(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\\s]+", " ", s)
    s = re.sub(r"\\s+", " ", s)
    return s


def _parse_date(text: str) -> Optional[datetime]:
    if not text:
        return None
    text = text.strip()
    # Try common formats.
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    # Try "Replied on May 8, 2023"
    m = re.search(r"([A-Za-z]+)\\s+(\\d{1,2}),\\s*(\\d{4})", text)
    if m:
        try:
            return datetime.strptime(m.group(0), "%B %d, %Y")
        except ValueError:
            try:
                return datetime.strptime(m.group(0), "%b %d, %Y")
            except ValueError:
                return None
    # Try "08 May 2023" embedded
    m = re.search(r"(\\d{1,2}\\s+[A-Za-z]+\\s+\\d{4})", text)
    if m:
        return _parse_date(m.group(1))
    return None


@dataclass
class Evidence:
    url: str
    source: str
    title: str
    snippet: str
    date: Optional[str]
    reply_count: int


def _extract_caclub_evidence(doc: Dict[str, Any]) -> List[Evidence]:
    items = doc.get("caclubindia", {}).get("items", [])
    out: List[Evidence] = []
    for item in items:
        url = item.get("url", "")
        typ = item.get("type", "")
        article = item.get("article", {})
        if typ == "expert_thread":
            title = article.get("title", "")
            posts = article.get("posts", [])
            reply_count = max(0, len(posts) - 1)
            snippet = posts[0].get("body", "")[:400] if posts else ""
            date = posts[0].get("date") if posts else ""
        elif typ == "forum":
            title = article.get("title", "")
            posts = article.get("posts", [])
            replies = article.get("replies", [])
            reply_count = len(replies)
            snippet = posts[0].get("body", "")[:400] if posts else ""
            date = posts[0].get("date") if posts else ""
        elif typ == "article_page":
            title = article.get("title", "")
            reply_count = 0
            snippet = article.get("content", "")[:400]
            date = article.get("date", "")
        else:
            continue
        out.append(
            Evidence(
                url=url,
                source="caclub",
                title=title,
                snippet=snippet,
                date=date,
                reply_count=reply_count,
            )
        )
    return out


def _extract_taxtmi_evidence(doc: Dict[str, Any]) -> List[Evidence]:
    items = doc.get("taxtmi", {}).get("items", [])
    out: List[Evidence] = []
    for item in items:
        url = item.get("url", "")
        typ = item.get("type", "")
        data = item.get("data", {})
        title = data.get("title", "")
        date = data.get("date", "")
        reply_count = 0
        snippet = ""
        if typ == "forum":
            posts = data.get("posts", [])
            replies = data.get("replies", [])
            reply_count = len(replies)
            snippet = posts[0].get("body", "")[:400] if posts else ""
            if not date and posts:
                date = posts[0].get("date", "")
        elif typ in {"article", "news", "page"}:
            snippet = (data.get("summary") or data.get("content") or "")[:400]
            replies = data.get("replies", [])
            reply_count = len(replies)
        else:
            continue
        out.append(
            Evidence(
                url=url,
                source="taxtmi",
                title=title,
                snippet=snippet,
                date=date,
                reply_count=reply_count,
            )
        )
    return out


def _merge_claims(evidence: List[Evidence]) -> List[Dict[str, Any]]:
    # Group by normalized title.
    buckets: Dict[str, List[Evidence]] = {}
    for ev in evidence:
        key = _norm(ev.title) or _norm(ev.url)
        buckets.setdefault(key, []).append(ev)

    now = datetime.utcnow()
    recency_cutoff = now - timedelta(days=365 * 3)

    claims: List[Dict[str, Any]] = []
    for _, evs in buckets.items():
        # Compute confidence
        sources = {e.source for e in evs}
        corroboration = 0.2 if len(sources) > 1 else 0.0
        replies_boost = 0.1 if any(e.reply_count > 0 for e in evs) else 0.0
        recency = 0.0
        for e in evs:
            dt = _parse_date(e.date or "")
            if dt and dt >= recency_cutoff:
                recency = max(recency, 0.2)
        # Authority equal; use 0.5 baseline authority.
        authority = 0.5
        relevance = 0.1
        base = 0.0
        confidence = min(1.0, base + authority + recency + corroboration + relevance + replies_boost)

        # Build claim text: title + first snippet
        title = evs[0].title or "Untitled"
        snippet = evs[0].snippet
        claim_text = title
        if snippet:
            claim_text = f"{title} — {snippet}"

        citations = [e.url for e in evs if e.url]
        claims.append(
            {
                "text": claim_text,
                "confidence": round(confidence, 3),
                "evidence": [
                    {
                        "url": e.url,
                        "source": e.source,
                        "date": e.date,
                        "reply_count": e.reply_count,
                    }
                    for e in evs
                ],
                "citations": citations,
                "notes": [],
            }
        )
    return claims


def main() -> None:
    parser = argparse.ArgumentParser(description="A2A orchestrator.")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--out", default=os.path.join(DATA_DIR, "final_result.json"))
    parser.add_argument("--search-out-dir", default=DATA_DIR)
    parser.add_argument("--results-out-dir", default=DATA_DIR)
    parser.add_argument("--max-links", type=int, default=0)
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)

    # Run CAClubIndia agent
    caclub_search = os.path.join(args.search_out_dir, "caclub_search.json")
    caclub_results = os.path.join(args.results_out_dir, "caclub_results.json")
    _run(
        [
            sys.executable,
            os.path.join(AGENTS_DIR, "caclub_agent.py"),
            "--query",
            args.query,
            "--search-out",
            caclub_search,
            "--out",
            caclub_results,
            "--max-links",
            str(args.max_links),
        ]
    )

    # Run TaxTMI agent
    taxtmi_search = os.path.join(args.search_out_dir, "taxtmi_search.json")
    taxtmi_results = os.path.join(args.results_out_dir, "taxtmi_results.json")
    _run(
        [
            sys.executable,
            os.path.join(AGENTS_DIR, "taxtmi_agent.py"),
            "--query",
            args.query,
            "--search-out",
            taxtmi_search,
            "--out",
            taxtmi_results,
            "--max-links",
            str(args.max_links),
        ]
    )

    # Load outputs
    caclub_doc = _load_json(caclub_results)
    taxtmi_doc = _load_json(taxtmi_results)

    evidence = []
    evidence.extend(_extract_caclub_evidence(caclub_doc))
    evidence.extend(_extract_taxtmi_evidence(taxtmi_doc))

    claims = _merge_claims(evidence)

    final = {
        "query": args.query,
        "generated_at": int(time.time()),
        "claims": claims,
    }
    _save_json(args.out, final)

    # A2A transcript (minimal)
    transcript = {
        "messages": [
            {"role": "orchestrator", "type": "search", "query": args.query},
            {"role": "agent", "agent_id": "caclub", "result": caclub_results},
            {"role": "agent", "agent_id": "taxtmi", "result": taxtmi_results},
            {"role": "orchestrator", "type": "final", "out": args.out},
        ]
    }
    _save_json(os.path.join(DATA_DIR, "a2a_transcript.json"), transcript)

    print(json.dumps(final, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
