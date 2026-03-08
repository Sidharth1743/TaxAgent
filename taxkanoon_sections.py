#!/usr/bin/env python3
"""Fetch Indian Kanoon search results and section content."""

import argparse
import json
import re
import time
from typing import Dict, List, Optional
from urllib.parse import quote_plus
import os

from scrapling import Fetcher, DynamicFetcher, StealthyFetcher

BASE_URL = "https://indiankanoon.org"


def _page_text(page) -> str:
    return " ".join(page.css("body *::text").getall()).lower()


def _is_blocked(page) -> bool:
    title = (page.css("title::text").get() or "").lower()
    text = _page_text(page)
    blockers = ["captcha", "verify you are human", "access denied"]
    return any(b in title or b in text for b in blockers)


def _fetch_with_fallbacks(url: str, wait_selector: str = "body"):
    page = Fetcher.get(url)
    if not _is_blocked(page):
        return page, "http"

    page = DynamicFetcher.fetch(url, wait_selector=wait_selector, network_idle=True)
    if not _is_blocked(page):
        return page, "dynamic"

    page = StealthyFetcher.fetch(
        url,
        wait_selector=wait_selector,
        network_idle=True,
        solve_cloudflare=True,
        timeout=60000,
    )
    return page, "stealth"


def _build_search_url(query: str) -> str:
    return f"{BASE_URL}/search/?formInput={quote_plus(query)}"


def _extract_search_results(page) -> List[Dict[str, str]]:
    results = []
    items = page.css(".results-list article.result")
    for item in items:
        title = " ".join(item.css("h4.result_title *::text").getall()).strip()
        href = item.css("h4.result_title a::attr(href)").get() or ""
        if href and href.startswith("/"):
            href = BASE_URL + href
        headline = " ".join(item.css(".headline *::text").getall()).strip()
        source = " ".join(item.css(".hlbottom .docsource::text").getall()).strip()
        cited_by = (
            " ".join(item.css(".hlbottom .cite_tag::text").getall()).strip()
        )
        if href:
            results.append(
                {
                    "title": title,
                    "url": href,
                    "headline": headline,
                    "docsource": source,
                    "cited_by": cited_by,
                }
            )
    return results


def _extract_section(page) -> Dict[str, str]:
    title = " ".join(page.css(".doc_title *::text, h2.doc_title *::text").getall()).strip()
    docsource = " ".join(page.css(".docsource_main *::text").getall()).strip()

    # Pull the akoma-ntoso section content if present.
    akn = page.css(".akoma-ntoso")
    content = ""
    if akn:
        text_nodes = akn[0].xpath(
            ".//text()[not(ancestor::script) and not(ancestor::style)]"
        ).getall()
        content = " ".join([" ".join(t.split()) for t in text_nodes]).strip()

    # Fallback to body text
    if not content:
        text_nodes = page.xpath(
            "//body//text()[not(ancestor::script) and not(ancestor::style)]"
        ).getall()
        content = " ".join([" ".join(t.split()) for t in text_nodes]).strip()

    return {"title": title, "docsource": docsource, "content": content}


def _safe_name(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_")
    return text[:120] or "doc"


def run(urls: List[str], text_out_dir: Optional[str] = None) -> Dict[str, object]:
    start = time.time()
    out = {"indiankanoon": {"items": []}, "meta": {}}

    if text_out_dir:
        os.makedirs(text_out_dir, exist_ok=True)

    for url in urls:
        page, method = _fetch_with_fallbacks(url, wait_selector="body")
        item = {"url": url, "method": method}

        if "/search/" in url:
            item["type"] = "search"
            item["results"] = _extract_search_results(page)
        else:
            item["type"] = "section"
            item["data"] = _extract_section(page)
            if text_out_dir:
                title = item["data"].get("title", "") or url
                filename = _safe_name(title)
                path = f"{text_out_dir}/{filename}.txt"
                with open(path, "w", encoding="utf-8") as f:
                    f.write(item["data"].get("content", ""))

        out["indiankanoon"]["items"].append(item)

    out["meta"]["elapsed_sec"] = round(time.time() - start, 2)
    out["meta"]["timestamp"] = int(time.time())
    return out


def main():
    parser = argparse.ArgumentParser(description="Fetch Indian Kanoon sections.")
    parser.add_argument("--query", default=None, help="Search query")
    parser.add_argument("--url", action="append", default=None, help="Doc URL")
    parser.add_argument("--out", default="indiankanoon.json", help="Output JSON")
    parser.add_argument("--search-out", default="indiankanoon_search.json", help="Search output JSON")
    parser.add_argument(
        "--text-out-dir",
        default="indiankanoon_text",
        help="Directory to write each section content as .txt",
    )
    parser.add_argument("--max-links", type=int, default=5, help="Limit links")
    args = parser.parse_args()

    urls = args.url or []

    if args.query:
        search_url = _build_search_url(args.query)
        page, method = _fetch_with_fallbacks(search_url, wait_selector=".results-list")
        results = _extract_search_results(page)
        with open(args.search_out, "w", encoding="utf-8") as f:
            json.dump(
                {"query": args.query, "url": search_url, "method": method, "results": results},
                f,
                indent=2,
                ensure_ascii=True,
            )
        urls = [r["url"] for r in results if r.get("url")]
        if args.max_links and args.max_links > 0:
            urls = urls[: args.max_links]

    data = run(urls, text_out_dir=args.text_out_dir)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)

    print(json.dumps(data, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
