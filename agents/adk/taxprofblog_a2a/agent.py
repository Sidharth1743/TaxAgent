#!/usr/bin/env python3
"""TaxProfBlog A2A agent (Google ADK).
Runs the TaxProfBlog scraper and returns structured evidence.
"""

import json
import os
import subprocess
from typing import Any, Dict

from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENT_SCRIPT = os.path.join(ROOT, "agents", "taxprofblog_agent.py")
DATA_DIR = ROOT


def fetch_taxprofblog(query: str, max_links: int = 5) -> Dict[str, Any]:
    args = [
        "python3",
        AGENT_SCRIPT,
        "--query",
        query,
        "--max-links",
        str(max_links),
        "--out",
        os.path.join(DATA_DIR, "taxprofblog.json"),
        "--search-out",
        os.path.join(DATA_DIR, "taxprofblog_search.json"),
    ]

    subprocess.run(args, check=False, capture_output=True, text=True)

    search_out = os.path.join(DATA_DIR, "taxprofblog_search.json")
    results_out = os.path.join(DATA_DIR, "taxprofblog.json")

    evidence = []
    try:
        with open(search_out, "r", encoding="utf-8") as f:
            search_doc = json.load(f)
    except Exception:
        search_doc = {}

    try:
        with open(results_out, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        doc = {}

    items = doc.get("taxprofblog", {}).get("items", [])
    articles_by_url = {}
    for item in items:
        if item.get("type") == "article":
            articles_by_url[item.get("url")] = item.get("data", {})

    for r in search_doc.get("results", [])[:max_links]:
        url = r.get("url")
        payload = {
            "title": r.get("title", ""),
            "url": url,
            "excerpt": r.get("excerpt", ""),
            "author": r.get("author", ""),
            "date": r.get("date", ""),
        }
        if url in articles_by_url:
            payload["article"] = articles_by_url[url]
        evidence.append(payload)

    payload = {"query": query, "source": "taxprofblog", "evidence": evidence}
    return payload


root_agent = Agent(
    name="taxprofblog_a2a_agent",
    model="gemini-3.1-flash-lite-preview",
    description="Fetches TaxProfBlog evidence for a query.",
    instruction=(
        "You are a TaxProfBlog evidence agent. "
        "Always call fetch_taxprofblog and return ONLY the JSON it returns. "
        "Do not add any extra text."
    ),
    tools=[fetch_taxprofblog],
)

a2a_app = to_a2a(root_agent, port=8004)
