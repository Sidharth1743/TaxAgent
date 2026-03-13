#!/usr/bin/env python3
"""Fetch TaxTMI pages using Scrapling."""

import argparse
import json
import re
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus

from scrapling import Fetcher, DynamicFetcher, StealthyFetcher

DEFAULT_TAXTMI_URLS = [
    "https://www.taxtmi.com/forum/issue?id=120217&allSearchQueries=tax%20on%20hackathon%20winning",
    "https://www.taxtmi.com/forum/issue?id=111703&allSearchQueries=tax%20for%20freelancers",
    "https://www.taxtmi.com/article/detailed?id=11385&allSearchQueries=tax%20for%20freelancers",
    "https://www.taxtmi.com/news?id=71100&allSearchQueries=tax%20for%20freelancers",
    "https://www.taxtmi.com/article/detailed?id=15163&allSearchQueries=tax%20for%20freelancers",
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


def _find_date(text: str) -> Optional[str]:
    match = re.search(r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b", text)
    return match.group(0) if match else None


def _extract_title(page) -> str:
    return (
        page.css("meta[property='og:title']::attr(content)").get()
        or page.css("meta[name='title']::attr(content)").get()
        or page.css("h1.title::text").get()
        or page.css("h1::text").get()
        or " ".join(page.css("h1.title *::text").getall()).strip()
        or " ".join(page.css("h1 *::text").getall()).strip()
        or page.css("title::text").get()
        or ""
    ).strip()


def _extract_body_by_selectors(page, selectors: List[str]) -> str:
    best = ""
    for sel in selectors:
        nodes = page.css(sel)
        for node in nodes:
            text_nodes = node.xpath(
                ".//text()[not(ancestor::script) and not(ancestor::style)]"
            ).getall()
            candidate = " ".join([" ".join(t.split()) for t in text_nodes]).strip()
            if len(candidate) > len(best):
                best = candidate
    return best


def _extract_article_like(page) -> Dict[str, str]:
    title = _extract_title(page)

    # TaxTMI news layout (per provided HTML).
    news_root = page.css("div.right-content")
    if news_root:
        news_root = news_root[0]
        title_node = news_root.css("#content_title::text").get() or news_root.css(
            ".title::text"
        ).get()
        date_node = news_root.css(".sub-title h2::text").get()
        content_text = " ".join(
            news_root.css("#content-div p::text, #content-div p *::text").getall()
        ).strip()
        if title_node or content_text:
            return {
                "title": (title_node or title).strip(),
                "author": "",
                "date": (date_node or "").strip(),
                "content": content_text,
            }

    # TaxTMI article layout (per provided HTML).
    article_root = page.css(".ans .query[data-type='Article']")
    if article_root:
        article_root = article_root[0]
        content_node = article_root.css(".desc .text")
        summary_node = article_root.css(".desc .summary")
        content_text = ""
        summary_text = ""
        if summary_node:
            summary_text = " ".join(
                summary_node[0]
                .xpath(".//text()[not(ancestor::script) and not(ancestor::style)]")
                .getall()
            ).strip()
        if content_node:
            content_text = " ".join(
                content_node[0]
                .xpath(".//text()[not(ancestor::script) and not(ancestor::style)]")
                .getall()
            ).strip()
        author = (
            article_root.css(".user .name::text").get()
            or article_root.css(".user .name *::text").get()
            or ""
        ).strip()
        date = (article_root.css(".info .date::text").get() or "").strip()
        if not date:
            date = _find_date(summary_text or content_text) or ""

        replies = []
        for ans in page.css(".answer .reply"):
            reply_text = " ".join(
                ans.css(".content .text p::text, .content .text li::text").getall()
            ).strip()
            reply_author = ans.css(".content .user .name::text").get() or ""
            reply_date = ans.css(".content .user .date::text").get() or ""
            if reply_text:
                replies.append(
                    {
                        "author": reply_author.strip(),
                        "date": reply_date.strip(),
                        "body": reply_text,
                    }
                )

        return {
            "title": title,
            "author": author,
            "date": date,
            "summary": summary_text,
            "content": content_text,
            "replies": replies,
        }

    selectors = [
        "div.article-detail",
        "div.article-details",
        "div.article-detail-content",
        "div.article-content",
        "div#article",
        "div.post-content",
        "div#article_content",
        "div#content",
        "div#articletext",
        "div#article-body",
        "div.articleBody",
        "div.article",
        "div.detail-article",
        "div.detail-article-content",
        "div.detail-news",
        "div.news_detail",
        "div.news-details",
        "div.news",
    ]
    content = _extract_body_by_selectors(page, selectors)
    if not content:
        text_nodes = page.xpath(
            "//body//text()[not(ancestor::script) and not(ancestor::style)]"
        ).getall()
        content = " ".join([" ".join(t.split()) for t in text_nodes]).strip()

    author = (
        page.css(".author a::text, .author::text, .author-name::text").get() or ""
    ).strip()
    date = (
        page.css("meta[property='article:published_time']::attr(content)").get()
        or page.css(".date::text, .posted-on::text, .post-date::text").get()
        or ""
    ).strip()
    if not date:
        date = _find_date(content) or ""

    return {
        "title": title,
        "author": author,
        "date": date,
        "content": content,
    }


def _extract_forum_issue(page) -> Dict[str, object]:
    title = _extract_title(page)

    # TaxTMI forum layout (per provided HTML).
    issue_root = page.css(".ans .query[data-type='Article']")
    if issue_root:
        issue_root = issue_root[0]
        asked_by = (
            issue_root.css(".user .name::text").get()
            or issue_root.css(".user .name *::text").get()
            or ""
        ).strip()
        asked_on = (issue_root.css(".info .date::text").get() or "").strip()
        issue_text = " ".join(
            issue_root.css(".desc .text p::text, .desc .text li::text").getall()
        ).strip()

        posts = []
        if issue_text:
            posts.append(
                {
                    "author": asked_by,
                    "role": "Post",
                    "date": asked_on,
                    "body": issue_text,
                }
            )

        replies = []
        for ans in page.css(".answer .reply"):
            reply_text = " ".join(
                ans.css(".content .text p::text, .content .text li::text").getall()
            ).strip()
            reply_author = ans.css(".content .user .name::text").get() or ""
            reply_date = ans.css(".content .user .date::text").get() or ""
            if reply_text:
                replies.append(
                    {
                        "author": reply_author.strip(),
                        "date": reply_date.strip(),
                        "body": reply_text,
                    }
                )

        return {
            "title": title,
            "status": "",
            "posts": posts,
            "replies": replies,
        }

    # TaxTMI forum layout varies; try explicit post/reply containers first.
    post_nodes = page.css(
        ".post-card .post-content, .issue-card .post-content, "
        ".issue-desc, .issue-description, .issue-content"
    )
    reply_nodes = page.css(
        ".reply-card .post-content, .answer-card .post-content, "
        ".reply-desc, .reply-content, .answer-content"
    )

    posts = []
    replies = []

    for p in post_nodes:
        text = " ".join(p.css("p::text, li::text").getall()).strip()
        if text:
            posts.append({"author": "", "role": "Post", "date": "", "body": text})

    for r in reply_nodes:
        text = " ".join(r.css("p::text, li::text").getall()).strip()
        if text:
            replies.append({"author": "", "role": "Reply", "date": "", "body": text})

    # Fallback: use common forum containers.
    if not posts and not replies:
        containers = page.css(
            "div.post, div.post-container, div.message, div.reply, div.answer, "
            "div.forum-post, div.forum-reply, div.issue, div.issue-detail, "
            "div.issue_detail, div.issue_details"
        )
        for c in containers:
            text = " ".join(c.css("p::text, li::text").getall()).strip()
            if text:
                posts.append({"author": "", "role": "Post", "date": "", "body": text})

    return {
        "title": title,
        "status": "",
        "posts": posts,
        "replies": replies,
    }


def _extract_search_results(page) -> List[Dict[str, str]]:
    results = []

    # TaxTMI search layout (per provided HTML).
    notif = page.css("#allNotifs .notific")
    if notif:
        for n in notif:
            a = n.css("a.redirect")
            href = a.css("::attr(href)").get() or ""
            title = " ".join(a.css("*::text").getall()).strip()
            snippet = " ".join(
                n.css(".scroll *::text, .desc *::text").getall()
            ).strip()
            kind = " ".join(n.css(".law.type::text").getall()).strip()
            law = " ".join(n.css(".law:not(.type)::text").getall()).strip()
            if href and not href.startswith("http"):
                href = "https://www.taxtmi.com" + href
            if href:
                results.append(
                    {
                        "title": title,
                        "url": href,
                        "type": kind,
                        "law": law,
                        "snippet": snippet,
                    }
                )
        return _dedupe_results(results)

    containers = page.css(
        "div.search-result, div.searchResult, div.search_results, div.results, "
        "div.result, div.query, div.ans"
    )

    def _get_link(node) -> str:
        href = node.css("::attr(href)").get() or ""
        if href:
            return href
        # Some TaxTMI cards use data-href/data-link.
        return (
            node.css("::attr(data-href)").get()
            or node.css("::attr(data-link)").get()
            or ""
        )

    def add_result(href: str, title: str):
        if not href:
            return
        href = href.strip()
        if not href.startswith("http"):
            href = "https://www.taxtmi.com" + href
        if "taxtmi.com" not in href:
            return
        title = (title or "").strip() or href
        # Drop obvious navigation links.
        if any(
            href.endswith(suffix)
            for suffix in ("/news", "/newsletter", "/newsletter/", "/newsletters")
        ):
            return
        if title in {"Budget 2026", "Newsletters Archive", "Free  News", "News"}:
            return
        results.append({"title": title, "url": href})

    for c in containers:
        for node in c.css("a, [data-href], [data-link]"):
            href = _get_link(node)
            title = " ".join(node.css("*::text").getall()).strip()
            add_result(href, title)

    # Fallback: scan all anchors if container parsing yields nothing.
    if not results:
        for a in page.css("a, [data-href], [data-link]"):
            href = _get_link(a)
            title = " ".join(a.css("*::text").getall()).strip()
            add_result(href, title)

    # Keep only content URLs with IDs, after collection.
    filtered = []
    for r in results:
        href = r["url"]
        if re.search(r"/forum/issue\\?id=\\d+", href):
            filtered.append(r)
        elif re.search(r"/article/detailed\\?id=\\d+", href):
            filtered.append(r)
        elif re.search(r"/news\\?id=\\d+", href):
            filtered.append(r)
        elif re.search(r"/judgements/|/judgement/", href):
            filtered.append(r)

    filtered = _dedupe_results(filtered)
    if filtered:
        return filtered

    # Fallback: extract known URL patterns from raw HTML/JS when results are rendered client-side.
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
    if not html:
        return []

    pattern = re.compile(
        r"https?://(?:www\.)?taxtmi\.com/(?:forum/issue\\?id=\\d+|article/detailed\\?id=\\d+|news\\?id=\\d+|judgements?/[^\"'\\s>]+)",
        re.I,
    )
    urls = []
    seen = set()
    for match in pattern.findall(html):
        url = match.split("#", 1)[0]
        if url in seen:
            continue
        seen.add(url)
        urls.append({"title": url, "url": url})
    return urls


def _dedupe_results(results: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    uniq = []
    for r in results:
        key = (r.get("url", ""), (r.get("title") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq


def _build_search_url(query: str, page: int = 1) -> str:
    q = quote_plus(query)
    if page <= 1:
        return f"https://www.taxtmi.com/tmi_search?allSearchQueries={q}"
    return (
        "https://www.taxtmi.com/tmi_search?"
        f"allSearchQueries={q}&page={page}&lawId=&catId=&searchIn=aiMain&from=&to=&sort=relevance"
    )


def run(urls: List[str], dump_dir: Optional[str]) -> Dict[str, object]:
    start = time.time()
    out = {"taxtmi": {"items": []}, "meta": {}}

    for url in urls:
        page, method = _fetch_with_fallbacks(url, wait_selector="body")
        _maybe_dump_html(page, url, dump_dir)
        item = {"url": url, "method": method}

        if "/tmi_search" in url:
            item["type"] = "search"
            item["data"] = _extract_search_results(page)
        elif "/forum/issue" in url:
            item["type"] = "forum"
            item["data"] = _extract_forum_issue(page)
        elif "/article/" in url:
            item["type"] = "article"
            item["data"] = _extract_article_like(page)
        elif "/news" in url:
            item["type"] = "news"
            item["data"] = _extract_article_like(page)
        else:
            item["type"] = "page"
            item["data"] = _extract_article_like(page)

        out["taxtmi"]["items"].append(item)

    out["meta"]["elapsed_sec"] = round(time.time() - start, 2)
    out["meta"]["timestamp"] = int(time.time())
    return out


def main():
    parser = argparse.ArgumentParser(description="Fetch TaxTMI pages using Scrapling.")
    parser.add_argument(
        "--query",
        default=None,
        help="Search query (fetch first page links, then scrape each link)",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=None,
        help="TaxTMI URL (repeatable)",
    )
    parser.add_argument(
        "--dump-html",
        default=None,
        help="Directory to dump raw HTML per URL",
    )
    parser.add_argument("--out", default="taxtmi.json", help="Output JSON path")
    parser.add_argument(
        "--search-out",
        default="taxtmi_search.json",
        help="Output JSON path for search results",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=5,
        help="Limit number of links to fetch (0 = no limit)",
    )
    args = parser.parse_args()

    urls = args.url or DEFAULT_TAXTMI_URLS

    if args.query:
        search_url = _build_search_url(args.query, page=1)
        page_obj, method = _fetch_with_fallbacks(search_url, wait_selector="#allNotifs")
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
