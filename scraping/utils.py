#!/usr/bin/env python3
"""Shared scraping utilities used by multiple scrapers."""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from scrapling import Fetcher, DynamicFetcher, StealthyFetcher

SCRAPER_TIMEOUT_MS = int(os.getenv("SCRAPER_TIMEOUT_MS", "30000"))


def page_text(page) -> str:
    """Extract all visible text from a page, lowercased."""
    return " ".join(page.css("body *::text").getall()).lower()


def is_blocked(page, extra_patterns: Optional[List[str]] = None) -> bool:
    """Check if a page is showing a block/captcha page."""
    title = (page.css("title::text").get() or "").lower()
    text = page_text(page)
    blockers = [
        "captcha",
        "verify you are human",
        "access denied",
        "just a moment",
        "attention required",
        "cloudflare",
    ]
    if extra_patterns:
        blockers.extend(extra_patterns)
    return any(b in title or b in text for b in blockers)


def page_html(page) -> str:
    """Extract raw HTML from a scrapling page object."""
    for attr in ("html", "content", "text", "page_source"):
        if hasattr(page, attr):
            value = getattr(page, attr)
            if callable(value):
                try:
                    value = value()
                except Exception:
                    value = ""
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="ignore")
            if isinstance(value, str) and value.strip():
                return value
    if hasattr(page, "response"):
        resp = page.response
        for attr in ("text", "content"):
            if hasattr(resp, attr):
                value = getattr(resp, attr)
                if callable(value):
                    try:
                        value = value()
                    except Exception:
                        value = ""
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="ignore")
                if isinstance(value, str) and value.strip():
                    return value
    return ""


def fetch_with_fallbacks(
    url: str,
    wait_selector: str = "body",
    headers: Optional[Dict[str, str]] = None,
    timeout_ms: Optional[int] = None,
    extra_block_patterns: Optional[List[str]] = None,
) -> Tuple[object, str]:
    """Try HTTP → Dynamic → Stealth fetchers with fallback.

    Returns (page, method) tuple.
    """
    timeout = timeout_ms or SCRAPER_TIMEOUT_MS

    page = Fetcher.get(url, headers=headers or {})
    if not is_blocked(page, extra_block_patterns):
        return page, "http"

    page = DynamicFetcher.fetch(url, wait_selector=wait_selector, network_idle=True)
    if not is_blocked(page, extra_block_patterns):
        return page, "dynamic"

    page = StealthyFetcher.fetch(
        url,
        wait_selector=wait_selector,
        network_idle=True,
        solve_cloudflare=True,
        timeout=timeout,
        headers=headers or {},
    )
    return page, "stealth"


def safe_name(text: str, max_len: int = 120) -> str:
    """Create a filesystem-safe name from text."""
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_")
    return text[:max_len] or "doc"
