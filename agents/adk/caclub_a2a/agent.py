#!/usr/bin/env python3
"""
CAClubIndia A2A agent (Google ADK).
Runs the CAClubIndia scraper and returns structured evidence.
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
AGENT_SCRIPT = os.path.join(ROOT, "agents", "caclub_agent.py")
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


def _fetch_caclub_uncached(query: str, max_links: int = 5) -> Dict[str, Any]:
    search_out = os.path.join(DATA_DIR, "caclub_search.json")
    results_out = os.path.join(DATA_DIR, "caclub_results.json")

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
    items = doc.get("caclubindia", {}).get("items", [])

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

    return {"query": query, "source": "caclub", "evidence": evidence}


def fetch_caclub(query: str, max_links: int = 5) -> Dict[str, Any]:
    return cached_run(
        source_name="caclub",
        query=query,
        runner_fn=lambda q: _fetch_caclub_uncached(q, max_links),
        data_dir=DATA_DIR,
        cache_prefix="v2",
    )


root_agent = Agent(
    name="caclub_a2a_agent",
    model="gemini-3.1-flash-lite-preview",
    description="Fetches CAClubIndia evidence for a query.",
    instruction=(
        "You are a CAClubIndia evidence agent. "
        "Always call fetch_caclub and return ONLY the JSON it returns. "
        "Do not add commentary or extra text."
    ),
    tools=[fetch_caclub],
)

# A2A app
a2a_app = to_a2a(root_agent, port=8001)
