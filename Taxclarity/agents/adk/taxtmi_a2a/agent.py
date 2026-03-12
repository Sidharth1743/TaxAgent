#!/usr/bin/env python3
"""
TaxTMI A2A agent (Google ADK).
Runs the TaxTMI scraper via direct import and returns structured evidence.
"""

import hashlib
import json
import os
import time
import asyncio
from typing import Any, Dict
from urllib.parse import quote_plus

from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents.llm_agent import Agent

from agents.taxtmi_agent import run as taxtmi_run
from config import SOURCE_AGENT_MODEL
from memory.pageindex_store import index_scraped_content, query_pageindex

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DATA_DIR = os.path.join(ROOT, "data")


async def fetch_taxtmi(query: str, max_links: int = 5) -> Dict[str, Any]:
    # --- STEP 1: Fast Cache Check via PageIndex ---
    cache_result = query_pageindex(query)
    if cache_result and cache_result.get("answer"):
        return {
            "query": query,
            "source": "taxtmi",
            "evidence": [{
                "title": "Cached Expertise (PageIndex)",
                "url": "internal://pageindex/taxtmi",
                "snippet": cache_result.get("answer"),
                "date": "",
                "reply_count": 0,
                "source": "taxtmi"
            }],
            "status": "cache_hit"
        }

    # --- STEP 2: Live Scrape (if cache miss) ---
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_key = hashlib.sha256(query.encode("utf-8")).hexdigest()
    cache_path = os.path.join(DATA_DIR, f"taxtmi_cache_{cache_key}.json")
    if os.path.exists(cache_path) and (time.time() - os.path.getmtime(cache_path) < 600):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # Build search URL
    search_url = f"https://www.taxtmi.com/tmi_search?allSearchQueries={quote_plus(query)}"

    # Phase 1: Fetch search results
    search_result = await asyncio.to_thread(
        taxtmi_run,
        [search_url],
        dump_dir=DATA_DIR,
    )

    # Extract search results from the returned dict
    search_items = search_result.get("taxtmi", {}).get("items", [])
    search_data = []
    for item in search_items:
        if item.get("type") == "search":
            data = item.get("data", [])
            if isinstance(data, list):
                search_data.extend(data)
            elif isinstance(data, dict):
                search_data.extend(data.get("results", []))

    # Phase 2: Fetch article/forum pages
    article_urls = [r.get("url") for r in search_data if r.get("url")][:max_links]

    articles_result = {"taxtmi": {"items": []}}
    if article_urls:
        articles_result = await asyncio.to_thread(
            taxtmi_run,
            article_urls,
            dump_dir=DATA_DIR,
        )

    # Build evidence from fetched items
    items = articles_result.get("taxtmi", {}).get("items", [])

    evidence = []
    for item in items:
        url = item.get("url", "")
        typ = item.get("type", "")
        data = item.get("data", {})
        title = data.get("title", "")
        date = data.get("date", "")

        if typ == "forum":
            posts = data.get("posts", [])
            replies = data.get("replies", [])
            snippet = posts[0].get("body", "")[:400] if posts else ""
            reply_count = len(replies)
        elif typ in {"article", "news", "page"}:
            snippet = (data.get("summary") or data.get("content") or "")[:400]
            reply_count = len(data.get("replies", []))
        else:
            continue

        evidence.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "date": date,
                "reply_count": reply_count,
                "source": "taxtmi",
            }
        )

    payload = {"query": query, "source": "taxtmi", "evidence": evidence}
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)

    # Index in PageIndex for future fast retrieval
    index_scraped_content(query, "taxtmi", evidence)

    return payload


root_agent = Agent(
    name="taxtmi_a2a_agent",
    model=SOURCE_AGENT_MODEL,
    description="Fetches TaxTMI evidence for a query.",
    instruction=(
        "You are a TaxTMI evidence agent. "
        "Always call fetch_taxtmi and return ONLY the JSON it returns. "
        "Do not add commentary or extra text."
    ),
    tools=[fetch_taxtmi],
)

from backend.health import with_health_check

a2a_app = with_health_check(to_a2a(root_agent, port=8002))
