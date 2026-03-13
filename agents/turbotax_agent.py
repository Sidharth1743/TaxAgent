#!/usr/bin/env python3
"""Fetch TurboTax pages using Scrapling."""

import argparse
import base64
import json
import os
import re
import time
import urllib.parse
import urllib.request
import logging
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from scrapling import Fetcher, DynamicFetcher, StealthyFetcher

from scraping.utils import (
    is_blocked as _is_blocked_shared,
    page_text as _page_text_shared,
    page_html as _page_html_shared,
)

logger = logging.getLogger(__name__)

DEFAULT_TURBOTAX_URLS = [
    "https://turbotax.intuit.com/search/#?cludoquery=tax%20on%20hackathon%20winning&cludopage=1",
]


def _page_text(page) -> str:
    return _page_text_shared(page)


def _is_blocked(page) -> bool:
    return _is_blocked_shared(page, extra_patterns=["enable javascript"])


def _fetch_with_fallbacks(url: str, wait_selector: str = "body", allow_browser: bool = True):
    page = Fetcher.get(url)
    if not _is_blocked(page) and len(_page_html(page)) > 200:
        return page, "http"

    if not allow_browser:
        return page, "http"

    try:
        page = DynamicFetcher.fetch(url, wait_selector=wait_selector, network_idle=True)
        if not _is_blocked(page) and len(_page_html(page)) > 200:
            return page, "dynamic"
    except Exception:
        pass

    try:
        page = StealthyFetcher.fetch(
            url,
            wait_selector=wait_selector,
            network_idle=True,
            solve_cloudflare=True,
            timeout=60000,
        )
        return page, "stealth"
    except Exception:
        return page, "http"


def _maybe_dump_html(page, url: str, dump_dir: Optional[str]) -> None:
    if not dump_dir:
        return
    os.makedirs(dump_dir, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", url).strip("_") or "page"
    path = f"{dump_dir}/{safe}.html"
    try:
        html = _page_html(page)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        # Best-effort dump to aid debugging.
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass


def _page_html(page) -> str:
    return _page_html_shared(page)


def _extract_title(page) -> str:
    return (
        page.css("meta[property='og:title']::attr(content)").get()
        or page.css("meta[name='title']::attr(content)").get()
        or page.css("h1::text").get()
        or " ".join(page.css("h1 *::text").getall()).strip()
        or page.css("title::text").get()
        or ""
    ).strip()


def _extract_cludo_config(page) -> Dict[str, str]:
    html = _page_html(page)
    if not html:
        return {}
    # Try to locate Cludo config in scripts or inline JSON.
    patterns = {
        "customerId": r"customerId['\"]?\s*[:=]\s*['\"](\d+)['\"]",
        "engineId": r"engineId['\"]?\s*[:=]\s*['\"](\d+)['\"]",
        "language": r"language['\"]?\s*[:=]\s*['\"]([a-zA-Z-]+)['\"]",
        "searchApiUrl": r"searchApiUrl['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]",
        "apiUrl": r"apiUrl['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]",
        "searchKey": r"searchKey['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]",
        "searchApiKey": r"searchApiKey['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]",
        "siteKey": r"siteKey['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]",
    }
    out: Dict[str, str] = {}
    for key, pat in patterns.items():
        m = re.search(pat, html)
        if m:
            out[key] = m.group(1)
    # Also check for data attributes in HTML.
    for key, attr in (
        ("customerId", "data-cludo-customer-id"),
        ("engineId", "data-cludo-engine-id"),
        ("searchKey", "data-cludo-search-key"),
    ):
        if key in out:
            continue
        m = re.search(rf"{attr}=['\"]([^'\"]+)['\"]", html)
        if m:
            out[key] = m.group(1)
    return out


def _fetch_cludo_search(
    query: str, page: int, config: Dict[str, str], debug_out: Optional[str] = None
) -> (List[Dict[str, str]], Dict[str, str]):
    customer_id = config.get("customerId")
    engine_id = config.get("engineId")
    if not customer_id or not engine_id:
        return [], {"error": "missing_customer_or_engine"}
    base = (
        config.get("searchApiUrl")
        or config.get("apiUrl")
        or "https://api-us1.cludo.com/api/v3"
    ).rstrip("/")
    search_key = config.get("searchKey") or config.get("searchApiKey")
    site_key = config.get("siteKey")
    auth_header = None
    if site_key:
        auth_header = f"SiteKey {site_key}"
    elif search_key:
        raw = f"{customer_id}:{engine_id}:{search_key}".encode("utf-8")
        auth_header = f"SiteKey {base64.b64encode(raw).decode('ascii')}"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://turbotax.intuit.com",
        "Referer": "https://turbotax.intuit.com/",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
        ),
    }
    if auth_header:
        headers["Authorization"] = auth_header

    endpoints = [
        f"{base}/{customer_id}/{engine_id}/search",
        f"{base}/{customer_id}/{engine_id}/search?query={quote_plus(query)}&page={page}&perPage=10",
        f"{base}/search?customerId={customer_id}&engineId={engine_id}&query={quote_plus(query)}&page={page}&perPage=10",
    ]

    data = None
    last_error = ""
    for idx, url in enumerate(endpoints):
        try:
            if idx == 0:
                body = json.dumps(
                    {
                        "query": query,
                        "page": page,
                        "perPage": 10,
                        "filters": [],
                        "useStrictSearch": False,
                    }
                ).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers=headers,
                    method="POST",
                )
            else:
                req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if data:
                break
        except Exception as e:
            last_error = str(e)
            continue

    if not data:
        return [], {"error": last_error or "no_data"}

    results = []
    def _field_value(val):
        if isinstance(val, dict):
            if "Value" in val:
                return val.get("Value") or ""
            if "value" in val:
                return val.get("value") or ""
        if isinstance(val, list) and val:
            return val[0]
        return val or ""

    def _add_item(item: Dict[str, object]) -> None:
        href = _field_value(
            item.get("url")
            or item.get("Url")
            or item.get("link")
            or item.get("Link")
        )
        title = _field_value(
            item.get("title")
            or item.get("Title")
            or item.get("name")
            or item.get("Name")
        )
        snippet = _field_value(
            item.get("description")
            or item.get("Description")
            or item.get("summary")
            or item.get("Summary")
            or item.get("content")
            or item.get("Content")
        )
        content = _field_value(item.get("Content") or item.get("content"))
        if href:
            results.append(
                {
                    "title": title,
                    "url": href,
                    "snippet": snippet,
                    "content": content,
                }
            )

    # Common v3 shapes.
    items = (
        data.get("results")
        or data.get("Results")
        or data.get("response", {}).get("results")
        or data.get("Response", {}).get("Results")
        or []
    )
    for item in items:
        if isinstance(item, dict):
            _add_item(item)

    # Newer v3 shapes (as seen in TurboTax): TypedDocuments / TopHits.
    for group in data.get("TypedDocuments", []) or []:
        if not isinstance(group, dict):
            continue
        docs = group.get("Documents")
        if docs:
            for doc in docs:
                if isinstance(doc, dict):
                    _add_item(doc)
            continue
        fields = group.get("Fields")
        if isinstance(fields, dict):
            _add_item(fields)

    top_hits = data.get("TopHits") or []
    for doc in top_hits:
        if isinstance(doc, dict):
            _add_item(doc)
    debug = {
        "error": "",
        "result_count": len(results),
        "top_keys": sorted(list(data.keys()))[:25],
    }
    if debug_out:
        try:
            with open(debug_out, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=True)
        except Exception:
            debug["error"] = "failed_to_write_debug_out"
    return results, debug


def _extract_search_results(page) -> List[Dict[str, str]]:
    results = []
    seen = set()

    items = page.css("ul.cludo_results-list li.cludo_result")
    for item in items:
        a = item.css("a[data-cludo-result='searchresult']")
        href = a.css("::attr(href)").get() or ""
        title = " ".join(a.css("h3 *::text, h3::text").getall()).strip()
        snippet = " ".join(
            item.css("p.cludo-theme-result-description *::text, p *::text").getall()
        ).strip()
        if not href:
            continue
        if href in seen:
            continue
        seen.add(href)
        results.append({"title": title, "url": href, "snippet": snippet})

    return results


def _extract_article(page) -> Dict[str, str]:
    title = _extract_title(page)

    article_root = page.css(
        "article[data-testid='container'], article, div[data-sb-field-path='.htmlContent']"
    )
    content = ""
    if article_root:
        root = article_root[0]
        text_nodes = root.xpath(
            ".//text()[not(ancestor::script) and not(ancestor::style)]"
        ).getall()
        content = " ".join([" ".join(t.split()) for t in text_nodes]).strip()

    if not content:
        text_nodes = page.xpath(
            "//body//text()[not(ancestor::script) and not(ancestor::style)]"
        ).getall()
        content = " ".join([" ".join(t.split()) for t in text_nodes]).strip()

    return {
        "title": title,
        "author": "",
        "date": "",
        "content": content,
    }


def _build_search_url(query: str, page: int = 1) -> str:
    q = quote_plus(query)
    return f"https://turbotax.intuit.com/search/#?cludoquery={q}&cludopage={page}"


def _parse_search_url(url: str) -> Dict[str, str]:
    # Extract cludoquery/cludopage from hash fragment.
    m_q = re.search(r"cludoquery=([^&]+)", url)
    m_p = re.search(r"cludopage=(\d+)", url)
    return {
        "query": m_q.group(1).replace("+", " ") if m_q else "",
        "page": m_p.group(1) if m_p else "1",
    }


def run(
    urls: List[str],
    dump_dir: Optional[str],
    allow_browser: bool = True,
    prefetched_articles: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, object]:
    start = time.time()
    out = {"turbotax": {"items": []}, "meta": {}}

    prefetched_articles = prefetched_articles or {}

    for url in urls:
        if url in prefetched_articles:
            item = {
                "url": url,
                "method": "cludo",
                "type": "article",
                "data": prefetched_articles[url],
            }
            out["turbotax"]["items"].append(item)
            continue
        page, method = _fetch_with_fallbacks(
            url, wait_selector="body", allow_browser=allow_browser
        )
        _maybe_dump_html(page, url, dump_dir)
        item = {"url": url, "method": method}

        if "turbotax.intuit.com/search/" in url:
            item["type"] = "search"
            data = _extract_search_results(page)
            if not data:
                config = _extract_cludo_config(page)
                parsed = _parse_search_url(url)
                data, _ = _fetch_cludo_search(
                    parsed.get("query", ""), int(parsed.get("page", "1")), config
                )
            item["data"] = data
        else:
            item["type"] = "article"
            item["data"] = _extract_article(page)

        out["turbotax"]["items"].append(item)

    out["meta"]["elapsed_sec"] = round(time.time() - start, 2)
    out["meta"]["timestamp"] = int(time.time())
    return out


def main():
    parser = argparse.ArgumentParser(description="Fetch TurboTax pages using Scrapling.")
    parser.add_argument(
        "--query",
        default=None,
        help="Search query (fetch first page links, then scrape each link)",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=None,
        help="TurboTax URL (repeatable)",
    )
    parser.add_argument(
        "--dump-html",
        default=None,
        help="Directory to dump raw HTML per URL",
    )
    parser.add_argument("--out", default="turbotax.json", help="Output JSON path")
    parser.add_argument(
        "--search-out",
        default="turbotax_search.json",
        help="Output JSON path for search results",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=5,
        help="Limit number of links to fetch (0 = no limit)",
    )
    parser.add_argument(
        "--cludo-customer-id",
        default=None,
        help="Override Cludo customerId (optional)",
    )
    parser.add_argument(
        "--cludo-engine-id",
        default=None,
        help="Override Cludo engineId (optional)",
    )
    parser.add_argument(
        "--cludo-search-key",
        default=None,
        help="Override Cludo search key (optional)",
    )
    parser.add_argument(
        "--cludo-site-key",
        default=None,
        help="Override Cludo site key (base64 token without 'SiteKey ' prefix)",
    )
    parser.add_argument(
        "--cludo-api-url",
        default=None,
        help="Override Cludo API base URL (optional)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not fall back to browser scraping if Cludo API fails",
    )
    parser.add_argument(
        "--no-article-browser",
        action="store_true",
        help="Do not use browser fetchers for article pages",
    )
    parser.add_argument(
        "--cludo-debug-out",
        default=None,
        help="Write raw Cludo API JSON response to this path (optional)",
    )
    args = parser.parse_args()

    urls = args.url or DEFAULT_TURBOTAX_URLS

    if args.query:
        search_url = _build_search_url(args.query, page=1)
        # Prefer direct Cludo API when config is provided to avoid slow JS pages.
        config = {
            "customerId": args.cludo_customer_id or os.getenv("CLUDO_CUSTOMER_ID") or "",
            "engineId": args.cludo_engine_id or os.getenv("CLUDO_ENGINE_ID") or "",
            "searchKey": args.cludo_search_key or os.getenv("CLUDO_SEARCH_KEY") or "",
            "siteKey": args.cludo_site_key or os.getenv("CLUDO_SITE_KEY") or "",
            "searchApiUrl": args.cludo_api_url or os.getenv("CLUDO_API_URL") or "",
        }
        config = {k: v for k, v in config.items() if v}
        method = "cludo"
        search_results = []
        cludo_debug = {}

        if not config.get("customerId") or not config.get("engineId"):
            logger.info(
                "cludo_config_missing",
                customer_id=bool(config.get("customerId")),
                engine_id=bool(config.get("engineId")),
                site_key=bool(config.get("siteKey")),
                api_url=bool(config.get("searchApiUrl")),
            )

        if config.get("customerId") and config.get("engineId"):
            search_results, cludo_debug = _fetch_cludo_search(
                args.query, 1, config, debug_out=args.cludo_debug_out
            )

        if not search_results and not args.no_browser:
            # Cludo search config is on the base search page (hash is client-side).
            base_search_url = "https://turbotax.intuit.com/search/"
            try:
                page_obj, method = _fetch_with_fallbacks(
                    base_search_url, wait_selector="body"
                )
                _maybe_dump_html(page_obj, base_search_url, args.dump_html)
                search_results = _extract_search_results(page_obj)
                extracted = _extract_cludo_config(page_obj)
                config = {**extracted, **config}
                if not search_results:
                    search_results, cludo_debug = _fetch_cludo_search(
                        args.query, 1, config, debug_out=args.cludo_debug_out
                    )
            except Exception:
                method = method or "error"

        # Build prefetched articles from Cludo content if available.
        prefetched_articles = {}
        for r in search_results:
            content = r.get("content", "")
            if content and r.get("url"):
                prefetched_articles[r["url"]] = {
                    "title": r.get("title", ""),
                    "author": "",
                    "date": "",
                    "content": content,
                }

        # Write slim search results (avoid huge content blobs).
        slim_results = [
            {k: v for k, v in r.items() if k in ("title", "url", "snippet")}
            for r in search_results
        ]

        with open(args.search_out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "query": args.query,
                    "url": search_url,
                    "method": method,
                    "results": slim_results,
                    "cludo_config": config,
                    "cludo_debug": cludo_debug if "cludo_debug" in locals() else {},
                },
                f,
                indent=2,
                ensure_ascii=True,
            )
        urls = [r["url"] for r in search_results if r.get("url")]
        if args.max_links and args.max_links > 0:
            urls = urls[: args.max_links]

    data = run(
        urls,
        args.dump_html,
        allow_browser=not args.no_article_browser,
        prefetched_articles=locals().get("prefetched_articles"),
    )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)

    print(json.dumps(data, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
