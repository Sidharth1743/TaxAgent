#!/usr/bin/env python3
"""Fetch TaxProfBlog pages using Scrapling."""

import argparse
import json
import re
import time
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from scrapling import DynamicFetcher, Fetcher, StealthyFetcher

DEFAULT_TAXPROFBLOG_URLS = [
    "https://taxprofblog.aals.org/?s=tax+on+freelancer",
]


def _page_text(page) -> str:
    return " ".join(page.css("body *::text").getall()).lower()


def _is_blocked(page) -> bool:
    title = (page.css("title::text").get() or "").lower()
    text = _page_text(page)
    blockers = [
        "just a moment",
        "attention required",
        "cloudflare",
        "captcha",
        "verify you are human",
        "enable javascript",
    ]
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


def _maybe_dump_html(page, url: str, dump_dir: Optional[str]) -> None:
    if not dump_dir:
        return
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", url).strip("_")
    path = f"{dump_dir}/{safe}.html"
    try:
        html = ""
        for attr in ("html", "content", "text", "page_source"):
            if hasattr(page, attr):
                value = getattr(page, attr)
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="ignore")
                if isinstance(value, str) and value.strip():
                    html = value
                    break
        if not html and hasattr(page, "response"):
            resp = page.response
            for attr in ("text", "content"):
                if hasattr(resp, attr):
                    value = getattr(resp, attr)
                    if isinstance(value, bytes):
                        value = value.decode("utf-8", errors="ignore")
                    if isinstance(value, str) and value.strip():
                        html = value
                        break
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass


def _extract_title(page) -> str:
    return (
        page.css("meta[property='og:title']::attr(content)").get()
        or page.css("meta[name='title']::attr(content)").get()
        or page.css("h1.entry-title::text").get()
        or page.css("h1::text").get()
        or " ".join(page.css("h1 *::text").getall()).strip()
        or page.css("title::text").get()
        or ""
    ).strip()


def _extract_search_results(page) -> List[Dict[str, str]]:
    results = []
    seen = set()

    items = page.css("li.wp-block-post")
    for item in items:
        a = item.css("h2.wp-block-post-title a")
        href = a.css("::attr(href)").get() or ""
        title = " ".join(a.css("*::text").getall()).strip()
        excerpt = " ".join(
            item.css(".wp-block-post-excerpt__excerpt *::text").getall()
        ).strip()
        author = (
            item.css(".wp-block-post-author-name a::text").get()
            or item.css(".wp-block-post-author-name::text").get()
            or ""
        ).strip()
        date = (
            item.css("time::attr(datetime)").get()
            or item.css("time *::text").get()
            or ""
        ).strip()
        if not href:
            continue
        if href in seen:
            continue
        seen.add(href)
        results.append(
            {
                "title": title,
                "url": href,
                "excerpt": excerpt,
                "author": author,
                "date": date,
            }
        )

    return results


def _extract_article(page) -> Dict[str, str]:
    title = _extract_title(page)

    content_root = page.css("div.entry-content.wp-block-post-content, div.entry-content")
    content = ""
    if content_root:
        root = content_root[0]
        text_nodes = root.xpath(
            ".//text()[not(ancestor::script) and not(ancestor::style)]"
        ).getall()
        content = " ".join([" ".join(t.split()) for t in text_nodes]).strip()

    if not content:
        text_nodes = page.xpath(
            "//body//text()[not(ancestor::script) and not(ancestor::style)]"
        ).getall()
        content = " ".join([" ".join(t.split()) for t in text_nodes]).strip()

    author = (
        page.css(".wp-block-post-author-name a::text").get()
        or page.css(".wp-block-post-author-name::text").get()
        or ""
    ).strip()
    date = (
        page.css("time.entry-date::attr(datetime)").get()
        or page.css("time::attr(datetime)").get()
        or page.css("time *::text").get()
        or ""
    ).strip()

    return {
        "title": title,
        "author": author,
        "date": date,
        "content": content,
    }


def _build_search_url(query: str) -> str:
    return f"https://taxprofblog.aals.org/?s={quote_plus(query)}"


def run(urls: List[str], dump_dir: Optional[str]) -> Dict[str, object]:
    start = time.time()
    out = {"taxprofblog": {"items": []}, "meta": {}}

    for url in urls:
        page, method = _fetch_with_fallbacks(url, wait_selector="body")
        _maybe_dump_html(page, url, dump_dir)
        item = {"url": url, "method": method}

        if "taxprofblog.aals.org/?" in url and "s=" in url:
            item["type"] = "search"
            item["data"] = _extract_search_results(page)
        else:
            item["type"] = "article"
            item["data"] = _extract_article(page)

        out["taxprofblog"]["items"].append(item)

    out["meta"]["elapsed_sec"] = round(time.time() - start, 2)
    out["meta"]["timestamp"] = int(time.time())
    return out


def main():
    parser = argparse.ArgumentParser(description="Fetch TaxProfBlog pages using Scrapling.")
    parser.add_argument(
        "--query",
        default=None,
        help="Search query (fetch first page links, then scrape each link)",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=None,
        help="TaxProfBlog URL (repeatable)",
    )
    parser.add_argument(
        "--dump-html",
        default=None,
        help="Directory to dump raw HTML per URL",
    )
    parser.add_argument("--out", default="taxprofblog.json", help="Output JSON path")
    parser.add_argument(
        "--search-out",
        default="taxprofblog_search.json",
        help="Output JSON path for search results",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=5,
        help="Limit number of links to fetch (0 = no limit)",
    )
    args = parser.parse_args()

    urls = args.url or DEFAULT_TAXPROFBLOG_URLS

    if args.query:
        search_url = _build_search_url(args.query)
        page_obj, method = _fetch_with_fallbacks(
            search_url, wait_selector="li.wp-block-post"
        )
        search_results = _extract_search_results(page_obj)
        with open(args.search_out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "query": args.query,
                    "url": search_url,
                    "method": method,
                    "results": search_results,
                },
                f,
                indent=2,
                ensure_ascii=True,
            )
        urls = [r["url"] for r in search_results if r.get("url")]
        if args.max_links and args.max_links > 0:
            urls = urls[: args.max_links]

    data = run(urls, args.dump_html)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)

    print(json.dumps(data, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
