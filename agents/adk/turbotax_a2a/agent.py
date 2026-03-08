#!/usr/bin/env python3
"""TurboTax A2A agent (Google ADK).
Runs the TurboTax scraper and returns structured evidence.
"""

import json
import os
import subprocess
from typing import Any, Dict

from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENT_SCRIPT = os.path.join(ROOT, "agents", "turbotax_agent.py")
DATA_DIR = ROOT


def fetch_turbotax(query: str, max_links: int = 5) -> Dict[str, Any]:
    # Optional Cludo config via env (preferred for TurboTax search).
    cludo_customer = os.getenv("CLUDO_CUSTOMER_ID", "")
    cludo_engine = os.getenv("CLUDO_ENGINE_ID", "")
    cludo_site_key = os.getenv("CLUDO_SITE_KEY", "")
    cludo_api_url = os.getenv("CLUDO_API_URL", "")

    args = [
        "python3",
        AGENT_SCRIPT,
        "--query",
        query,
        "--max-links",
        str(max_links),
        "--out",
        os.path.join(DATA_DIR, "turbotax.json"),
        "--search-out",
        os.path.join(DATA_DIR, "turbotax_search.json"),
    ]

    if cludo_customer:
        args += ["--cludo-customer-id", cludo_customer]
    if cludo_engine:
        args += ["--cludo-engine-id", cludo_engine]
    if cludo_site_key:
        args += ["--cludo-site-key", cludo_site_key]
    if cludo_api_url:
        args += ["--cludo-api-url", cludo_api_url]

    # If Cludo config is provided, avoid browser fallback and article browsing.
    if cludo_customer and cludo_engine:
        args += ["--no-browser", "--no-article-browser"]

    subprocess.run(args, check=False, capture_output=True, text=True)

    search_out = os.path.join(DATA_DIR, "turbotax_search.json")
    results_out = os.path.join(DATA_DIR, "turbotax.json")

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

    # Build evidence list from results with article content (prefer Cludo content).
    items = doc.get("turbotax", {}).get("items", [])
    articles_by_url = {}
    for item in items:
        if item.get("type") == "article":
            articles_by_url[item.get("url")] = item.get("data", {})

    for r in search_doc.get("results", [])[:max_links]:
        url = r.get("url")
        payload = {
            "title": r.get("title", ""),
            "url": url,
            "snippet": r.get("snippet", ""),
        }
        if url in articles_by_url:
            payload["article"] = articles_by_url[url]
        evidence.append(payload)

    payload = {"query": query, "source": "turbotax", "evidence": evidence}
    return payload


root_agent = Agent(
    name="turbotax_a2a_agent",
    model="gemini-3.1-flash-lite-preview",
    description="Fetches TurboTax evidence for a query.",
    instruction=(
        "You are a TurboTax evidence agent. "
        "Always call fetch_turbotax and return ONLY the JSON it returns. "
        "Do not add any extra text."
    ),
    tools=[fetch_turbotax],
)

a2a_app = to_a2a(root_agent, port=8003)
