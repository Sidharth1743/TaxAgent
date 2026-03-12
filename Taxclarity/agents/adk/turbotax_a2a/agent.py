#!/usr/bin/env python3
"""TurboTax A2A agent (Google ADK).
Runs the TurboTax scraper via direct import and returns structured evidence.
"""

import hashlib
import json
import os
import time
import asyncio
from typing import Any, Dict
from urllib.parse import quote_plus

from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent

from agents.turbotax_agent import run as turbotax_run
from config import CLUDO_CUSTOMER_ID, CLUDO_ENGINE_ID, SOURCE_AGENT_MODEL
from memory.pageindex_store import index_scraped_content

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "data")


async def fetch_turbotax(query: str, max_links: int = 5) -> Dict[str, Any]:
    os.makedirs(DATA_DIR, exist_ok=True)

    # SHA256 file cache (600s TTL)
    cache_key = hashlib.sha256(f"turbotax:{query}".encode("utf-8")).hexdigest()
    cache_path = os.path.join(DATA_DIR, f"turbotax_cache_{cache_key}.json")
    if os.path.exists(cache_path) and (time.time() - os.path.getmtime(cache_path) < 600):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # Build search URL
    search_url = f"https://turbotax.intuit.com/search/#?cludoquery={quote_plus(query)}&cludopage=1"

    # Optional Cludo config (preferred for TurboTax search).
    cludo_customer = CLUDO_CUSTOMER_ID
    cludo_engine = CLUDO_ENGINE_ID

    # Phase 1: Fetch search results
    allow_browser = not (cludo_customer and cludo_engine)
    search_result = await asyncio.to_thread(
        turbotax_run,
        [search_url],
        dump_dir=DATA_DIR,
        allow_browser=allow_browser,
    )

    # Extract search results from the returned dict
    search_items = search_result.get("turbotax", {}).get("items", [])
    search_data = []
    for item in search_items:
        if item.get("type") == "search":
            data = item.get("data", [])
            if isinstance(data, list):
                search_data.extend(data)
            elif isinstance(data, dict):
                search_data.extend(data.get("results", []))

    # Phase 2: Fetch article pages from search results
    article_urls = [r.get("url") for r in search_data if r.get("url")][:max_links]

    # Build prefetched articles from Cludo content if available
    prefetched_articles = {}
    for r in search_data:
        content = r.get("content", "")
        if content and r.get("url"):
            prefetched_articles[r["url"]] = {
                "title": r.get("title", ""),
                "author": "",
                "date": "",
                "content": content,
            }

    articles_result = {}
    if article_urls:
        articles_result = await asyncio.to_thread(
            turbotax_run,
            article_urls,
            dump_dir=DATA_DIR,
            allow_browser=allow_browser,
            prefetched_articles=prefetched_articles,
        )

    # Build evidence from articles, cross-referencing with search data
    articles_by_url = {}
    for item in articles_result.get("turbotax", {}).get("items", []):
        if item.get("type") == "article":
            articles_by_url[item.get("url")] = item.get("data", {})

    evidence = []
    for r in search_data[:max_links]:
        url = r.get("url")
        payload = {
            "title": r.get("title", ""),
            "url": url,
            "snippet": r.get("snippet", ""),
        }
        if url in articles_by_url:
            payload["article"] = articles_by_url[url]
        evidence.append(payload)

    result = {"query": query, "source": "turbotax", "evidence": evidence}

    # Write to cache
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=True)

    # Index in PageIndex for future fast retrieval
    index_scraped_content(query, "turbotax", evidence)

    return result


root_agent = Agent(
    name="turbotax_a2a_agent",
    model=SOURCE_AGENT_MODEL,
    description="Fetches TurboTax evidence for a query.",
    instruction=(
        "You are a TurboTax evidence agent. "
        "Always call fetch_turbotax and return ONLY the JSON it returns. "
        "Do not add any extra text."
    ),
    tools=[fetch_turbotax],
)

from backend.health import with_health_check

a2a_app = with_health_check(to_a2a(root_agent, port=8005))
