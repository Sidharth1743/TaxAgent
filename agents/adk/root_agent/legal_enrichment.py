#!/usr/bin/env python3
"""Legal enrichment tool — runs Indian Kanoon + Casemine scrapers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple

from .query_utils import (
    _directive_sources,
    _extract_section_queries,
    _build_casemine_query,
    _safe_slug,
)


def _run_script(cmd: List[str], root: str, timeout: int = 120) -> Tuple[bool, str]:
    try:
        result = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return False, (result.stderr or result.stdout or "").strip()
        return True, (result.stdout or "").strip()
    except subprocess.TimeoutExpired as e:
        return False, f"Timeout after {timeout}s: {e.stdout or ''}"
    except Exception as e:
        return False, str(e)


def run_legal_enrichment_tool(query: str, draft_json: str) -> Dict[str, Any]:
    """Run Indian Kanoon + Casemine enrichment in parallel."""
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

    try:
        draft = json.loads(draft_json)
    except Exception:
        draft = {}

    sources = _directive_sources(query)
    if sources == ["TurboTax", "TaxProfBlog"]:
        return {
            "section_queries": [],
            "judgement_query": "",
            "sections": [],
            "judgements": [],
            "errors": [],
            "section_text_dir": "",
            "judgement_text_dir": "",
        }

    claim_texts = []
    for c in (draft.get("claims") or []):
        if isinstance(c, dict):
            claim_texts.append(c.get("claim") or c.get("text") or "")
        elif isinstance(c, str):
            claim_texts.append(c)
    draft_text = " ".join([query] + claim_texts)

    section_queries = _extract_section_queries(draft_text)
    casemine_query = _build_casemine_query(query, draft_text)

    slug = _safe_slug(query)
    ts = int(time.time())
    section_out = os.path.join(ROOT, "data", f"indiankanoon_{slug}_{ts}.json")
    casemine_out = os.path.join(ROOT, "data", f"casemine_{slug}_{ts}.json")
    section_text_dir = os.path.join(ROOT, "indiankanoon_text", f"{slug}_{ts}")
    casemine_text_dir = os.path.join(ROOT, "casemine_text", f"{slug}_{ts}")

    section_cmds = []
    for sec_query in section_queries[:2]:
        section_cmds.append(
            [
                sys.executable,
                os.path.join(ROOT, "scraping", "taxkanoon.py"),
                "--query",
                sec_query,
                "--out",
                section_out,
                "--search-out",
                os.path.join(ROOT, "data", f"indiankanoon_search_{slug}_{ts}.json"),
                "--text-out-dir",
                section_text_dir,
            ]
        )

    casemine_cmd = [
        sys.executable,
        os.path.join(ROOT, "scraping", "casemine.py"),
        "--query",
        casemine_query,
        "--out",
        casemine_out,
        "--text-out-dir",
        casemine_text_dir,
        "--cookie-file",
        os.path.join(ROOT, "data", "casemine_cookies.txt"),
    ]

    results = {
        "section_queries": section_queries,
        "judgement_query": casemine_query,
        "sections": [],
        "judgements": [],
        "errors": [],
    }

    def _run_sections():
        if not section_cmds:
            return
        for cmd in section_cmds:
            ok, msg = _run_script(cmd, ROOT)
            if not ok:
                results["errors"].append({"stage": "indiankanoon", "error": msg})
        if os.path.exists(section_out):
            try:
                with open(section_out, "r", encoding="utf-8") as f:
                    results["sections"] = json.load(f).get("indiankanoon", {}).get("items", [])
            except Exception:
                pass

    def _run_casemine():
        ok, msg = _run_script(casemine_cmd, ROOT)
        if not ok:
            results["errors"].append({"stage": "casemine", "error": msg})
        if os.path.exists(casemine_out):
            try:
                with open(casemine_out, "r", encoding="utf-8") as f:
                    results["judgements"] = json.load(f).get("casemine", {}).get("results", [])
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_run_sections), pool.submit(_run_casemine)]
        for f in futures:
            f.result()

    results["section_text_dir"] = section_text_dir if section_queries else ""
    results["judgement_text_dir"] = casemine_text_dir
    return results
