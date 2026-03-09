#!/usr/bin/env python3
"""Fetch Casemine judgements from search query."""

import argparse
import json
import os
import re
import time
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from scrapling import Fetcher, DynamicFetcher, StealthyFetcher
from parsel import Selector
from dotenv import load_dotenv

from scraping.utils import (
    fetch_with_fallbacks as _fetch_with_fallbacks,
    is_blocked as _is_blocked,
    page_text as _page_text,
    page_html as _page_html_util,
)

BASE_URL = "https://www.casemine.com"
API_URL = "https://www.casemine.com/search/opinion"


def _build_search_url(query: str) -> str:
    return f"{BASE_URL}/search/in/{quote_plus(query)}"


def _build_api_url(query: str, start: int = 0, sort: str = "_score") -> str:
    return f"{API_URL}?start={start}&sort={quote_plus(sort)}&query={quote_plus(query)}"


def _safe_name(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_")
    return text[:120] or "judgement"


def _page_html(page) -> str:
    return _page_html_util(page)


def _dump_html(page, dump_path: Optional[str]) -> None:
    if not dump_path:
        return
    try:
        with open(dump_path, "w", encoding="utf-8") as f:
            f.write(_page_html(page))
    except Exception:
        pass


def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_results(page_or_selector) -> List[Dict[str, str]]:
    results = []
    items = page_or_selector.css("#opinions .cite-info-box, #show_citetext_area .cite-info-box")
    for item in items:
        title = " ".join(
            item.css(".cite-message .tcenter a *::text, .cite-message .tcenter a::text").getall()
        ).strip()
        url = item.css(".cite-message .tcenter a::attr(href)").get() or ""
        if url and url.startswith("/"):
            url = BASE_URL + url
        court = " ".join(
            item.css(".cite-message .tcenter small *::text, .cite-message .tcenter small::text").getall()
        ).strip()
        snippet = " ".join(
            item.css(".cite-message .opinion-snippet *::text, .cite-message .opinion-snippet::text").getall()
        ).strip()
        cited_in_title = " ".join(
            item.css(".cite-message_info .cmi-text a *::text, .cite-message_info .cmi-text a::text").getall()
        ).strip()
        cited_in_url = item.css(".cite-message_info .cmi-text a::attr(href)").get() or ""
        if cited_in_url and cited_in_url.startswith("/"):
            cited_in_url = BASE_URL + cited_in_url
        cited_in_court = " ".join(
            item.css(".cite-message_info .cmi-text small *::text, .cite-message_info .cmi-text small::text").getall()
        ).strip()

        if title and url:
            results.append(
                {
                    "title": title,
                    "url": url,
                    "court": court,
                    "snippet": snippet,
                    "cited_in_title": cited_in_title,
                    "cited_in_url": cited_in_url,
                    "cited_in_court": cited_in_court,
                }
            )
    # Fallback: try to parse generic blocks if container missing.
    if results:
        return results

    items = page_or_selector.css(".cite-info-box")
    for item in items:
        title = " ".join(
            item.css(".tcenter a *::text, .tcenter a::text").getall()
        ).strip()
        url = item.css(".tcenter a::attr(href)").get() or ""
        if url and url.startswith("/"):
            url = BASE_URL + url
        court = " ".join(item.css(".tcenter small *::text, .tcenter small::text").getall()).strip()
        snippet = " ".join(item.css(".opinion-snippet *::text, .opinion-snippet::text").getall()).strip()
        cited_in_title = " ".join(item.css(".cmi-text a *::text, .cmi-text a::text").getall()).strip()
        cited_in_url = item.css(".cmi-text a::attr(href)").get() or ""
        if cited_in_url and cited_in_url.startswith("/"):
            cited_in_url = BASE_URL + cited_in_url
        cited_in_court = " ".join(item.css(".cmi-text small *::text, .cmi-text small::text").getall()).strip()
        if title and url:
            results.append(
                {
                    "title": title,
                    "url": url,
                    "court": court,
                    "snippet": snippet,
                    "cited_in_title": cited_in_title,
                    "cited_in_url": cited_in_url,
                    "cited_in_court": cited_in_court,
                }
            )
    return results


def _fetch_api_results(query: str, headers: Dict[str, str], start: int = 0) -> List[Dict[str, str]]:
    url = _build_api_url(query, start=start)
    page = Fetcher.get(url, headers=headers)
    try:
        data = page.json()
    except Exception:
        try:
            data = json.loads(_page_html(page))
        except Exception:
            return []

    results = []
    for item in data.get("result", []) or []:
        title = item.get("tjidTitle", "") or ""
        court = item.get("tjidCourtName", "") or ""
        tjid = item.get("tjidId", "") or ""
        tpid = item.get("tpid", "") or ""
        fpid = item.get("fpid", "") or ""
        fjid_title = item.get("fjidTitle", "") or ""
        fjid_court = item.get("fjidCourtName", "") or ""
        fjid_id = item.get("fjidId", "") or ""
        snippet_html = " ".join(item.get("snippet", []) or [])
        snippet = _strip_tags(snippet_html)
        url = f"{BASE_URL}/judgement/in/{tjid}#{tpid}" if tjid else ""
        cited_in_url = f"{BASE_URL}/judgement/in/{fjid_id}#{fpid}" if fjid_id else ""
        if title and url:
            results.append(
                {
                    "title": title,
                    "url": url,
                    "court": court,
                    "snippet": snippet,
                    "cited_in_title": fjid_title,
                    "cited_in_url": cited_in_url,
                    "cited_in_court": fjid_court,
                }
            )
    return results


def run(
    url: Optional[str],
    text_out_dir: Optional[str] = None,
    dump_html: Optional[str] = None,
    html_file: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    query: Optional[str] = None,
) -> Dict[str, object]:
    start = time.time()
    method = "file" if html_file else "http"
    if html_file:
        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()
        selector = Selector(text=html)
        results = _extract_results(selector)
    else:
        # Prefer JSON API (more reliable than HTML)
        results = _fetch_api_results(query or "", headers or {}, start=0)
        if not results:
            page, method = _fetch_with_fallbacks(
                url, wait_selector="#opinions, #show_citetext_area", headers=headers
            )
            html = _page_html(page)
            _dump_html(page, dump_html)
            selector = Selector(text=html)
            results = _extract_results(selector)

    if text_out_dir:
        os.makedirs(text_out_dir, exist_ok=True)
        for r in results:
            name = _safe_name(r["title"])
            path = os.path.join(text_out_dir, f"{name}.txt")
            lines = [
                r["title"],
                r["court"],
                "",
                r["snippet"],
                "",
                f"Cited in: {r['cited_in_title']}",
                r["cited_in_court"],
            ]
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join([l for l in lines if l is not None]))

    return {
        "casemine": {"query_url": url, "method": method, "results": results},
        "meta": {"elapsed_sec": round(time.time() - start, 2), "timestamp": int(time.time())},
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch Casemine search judgements.")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--out", default="casemine.json", help="Output JSON")
    parser.add_argument("--text-out-dir", default="casemine_text", help="Write each result to .txt")
    parser.add_argument("--dump-html", default="casemine_debug.html", help="Dump raw HTML")
    parser.add_argument("--html-file", default=None, help="Parse results from local HTML file")
    parser.add_argument("--cookie", default=None, help="Cookie header value for authenticated requests")
    parser.add_argument("--cookie-file", default="casemine_cookies.txt", help="Path to cookie file")
    parser.add_argument("--user-agent", default=None, help="User-Agent override")
    parser.add_argument("--start", type=int, default=0, help="API start offset")
    args = parser.parse_args()

    load_dotenv()

    search_url = _build_search_url(args.query) if not args.html_file else None
    headers = {
        "User-Agent": args.user_agent
        or "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36",
        "Accept-Language": "en-US,en;q=0.6",
        "Referer": search_url or f"{BASE_URL}/search/in/{quote_plus(args.query)}",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }
    cookie_value = args.cookie or os.getenv("CASEMINE_COOKIE", "")
    if not cookie_value and args.cookie_file and os.path.exists(args.cookie_file):
        with open(args.cookie_file, "r", encoding="utf-8") as f:
            cookie_value = f.read().strip()
    if cookie_value:
        headers["Cookie"] = cookie_value
    data = run(
        search_url,
        text_out_dir=args.text_out_dir,
        dump_html=args.dump_html,
        html_file=args.html_file,
        headers=headers,
        query=args.query,
    )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)

    print(json.dumps(data, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
