#!/usr/bin/env python3
"""
TaxTMI A2A agent (Google ADK).
Runs the TaxTMI scraper and returns structured evidence.
"""

import json
import os
import subprocess
from typing import Any, Dict, List

from google.adk.agents.llm_agent import Agent
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from dotenv import load_dotenv

from agents.adk.cache import cached_run

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
AGENT_SCRIPT = os.path.join(ROOT, "agents", "taxtmi_agent.py")
DATA_DIR = os.path.join(ROOT, "data")

# Load environment variables (e.g., GOOGLE_API_KEY) from .env
load_dotenv(os.path.join(ROOT, ".env"))



def _run(cmd: List[str]) -> None:
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _fetch_taxtmi_uncached(query: str, max_links: int = 5) -> Dict[str, Any]:
    search_out = os.path.join(DATA_DIR, "taxtmi_search.json")
    results_out = os.path.join(DATA_DIR, "taxtmi_results.json")

    _run(
        [
            "python",
            AGENT_SCRIPT,
            "--query",
            query,
            "--search-out",
            search_out,
            "--out",
            results_out,
            "--max-links",
            str(max_links),
        ]
    )

    doc = _load_json(results_out)
    items = doc.get("taxtmi", {}).get("items", [])

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

    return {"query": query, "source": "taxtmi", "evidence": evidence}


def fetch_taxtmi(query: str, max_links: int = 5) -> Dict[str, Any]:
    return cached_run(
        source_name="taxtmi",
        query=query,
        runner_fn=lambda q: _fetch_taxtmi_uncached(q, max_links),
        data_dir=DATA_DIR,
    )


root_agent = Agent(
    name="taxtmi_a2a_agent",
    model="gemini-3.1-flash-lite-preview",
    description="Fetches TaxTMI evidence for a query.",
    instruction=(
        "You are a TaxTMI evidence agent. "
        "Always call fetch_taxtmi and return ONLY the JSON it returns. "
        "Do not add commentary or extra text."
    ),
    tools=[fetch_taxtmi],
)

a2a_app = to_a2a(root_agent, port=8002)
