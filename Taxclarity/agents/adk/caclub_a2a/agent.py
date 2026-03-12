#!/usr/bin/env python3
"""
CAClubIndia A2A agent (Google ADK).
Runs the CAClubIndia scraper via direct import and returns structured evidence.
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

from agents.caclub_agent import run as caclub_run
from config import SOURCE_AGENT_MODEL
from memory.pageindex_store import index_scraped_content, query_pageindex

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DATA_DIR = os.path.join(ROOT, "data")


async def fetch_caclub(query: str, max_links: int = 5) -> Dict[str, Any]:
    # --- STEP 1: Fast Cache Check via PageIndex ---
    cache_result = query_pageindex(query)
    if cache_result and cache_result.get("answer"):
        return {
            "query": query,
            "source": "caclub",
            "evidence": [{
                "title": "Cached Expertise (PageIndex)",
                "url": "internal://pageindex/caclub",
                "snippet": cache_result.get("answer"),
                "date": "",
                "reply_count": 0,
                "source": "caclub"
            }],
            "status": "cache_hit"
        }

    # --- STEP 2: Live Scrape (if cache miss) ---
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_key = hashlib.sha256(f"v2:{query}".encode("utf-8")).hexdigest()
    cache_path = os.path.join(DATA_DIR, f"caclub_cache_{cache_key}.json")
    if os.path.exists(cache_path) and (time.time() - os.path.getmtime(cache_path) < 600):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # Build search URL
    search_url = f"https://www.caclubindia.com/search_results_new.asp?q={quote_plus(query)}"

    # Phase 1: Fetch search results
    search_result = await asyncio.to_thread(
        caclub_run,
        [search_url],
        forum_fetcher="dynamic",
        dump_dir=DATA_DIR,
    )

    # Extract search results from the returned dict
    search_items = search_result.get("caclubindia", {}).get("items", [])
    search_data = []
    for item in search_items:
        if item.get("type") == "search":
            results = item.get("results", [])
            if isinstance(results, list):
                search_data.extend(results)

    # Phase 2: Fetch article/forum/thread pages
    article_urls = [r.get("url") for r in search_data if r.get("url")][:max_links]

    articles_result = {"caclubindia": {"items": []}}
    if article_urls:
        articles_result = await asyncio.to_thread(
            caclub_run,
            article_urls,
            forum_fetcher="dynamic",
            dump_dir=DATA_DIR,
        )

    # Build evidence from fetched items
    items = articles_result.get("caclubindia", {}).get("items", [])

    evidence = []
    for item in items:
        url = item.get("url", "")
        typ = item.get("type", "")
        article = item.get("article", {})
        if typ == "expert_thread":
            title = article.get("title", "")
            posts = article.get("posts", [])
            snippet = posts[0].get("body", "")[:400] if posts else ""
            date = posts[0].get("date") if posts else ""
            reply_count = max(0, len(posts) - 1)
        elif typ == "forum":
            title = article.get("title", "")
            posts = article.get("posts", [])
            replies = article.get("replies", [])
            snippet = posts[0].get("body", "")[:400] if posts else ""
            date = posts[0].get("date") if posts else ""
            reply_count = len(replies)
        elif typ == "article_page":
            title = article.get("title", "")
            snippet = article.get("content", "")[:400]
            date = article.get("date", "")
            reply_count = 0
        else:
            continue

        if not url or not title:
            continue
        if any(bad in url for bad in ("/browse.asp", "/pro/", "/login", "/register")):
            continue
        if not any(seg in url for seg in ("/experts/", "/forum/", "/articles/")):
            continue

        evidence.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "date": date,
                "reply_count": reply_count,
                "source": "caclub",
            }
        )

    payload = {"query": query, "source": "caclub", "evidence": evidence}
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)

    # Index in PageIndex for future fast retrieval
    index_scraped_content(query, "caclub", evidence)

    return payload


root_agent = Agent(
    name="caclub_a2a_agent",
    model=SOURCE_AGENT_MODEL,
    description="Fetches CAClubIndia evidence for a query.",
    instruction=(
        "You are a CAClubIndia evidence agent. "
        "Always call fetch_caclub and return ONLY the JSON it returns. "
        "Do not add commentary or extra text."
    ),
    tools=[fetch_caclub],
)

# A2A app
from backend.health import with_health_check

a2a_app = with_health_check(to_a2a(root_agent, port=8001))
