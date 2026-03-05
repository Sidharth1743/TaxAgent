#!/usr/bin/env python3
"""Fetch CAClubIndia pages using Scrapling."""

import argparse
import json
import re
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus

from scrapling import Fetcher, DynamicFetcher, StealthyFetcher

DEFAULT_CACLUBINDIA_URLS = [
    "https://www.caclubindia.com/experts/"
    "regarding-hackathon-prize-w-8ben-form-tax-treaty-benefit-115bb-115bbj-2952254.asp",
    "https://www.caclubindia.com/forum/"
    "gift-from-mother-in-law-to-daughter-in-law-259456.asp/unattended_threads.asp",
    "https://www.caclubindia.com/articles/"
    "tax-rules-for-freelancers-in-fy-2025-26-53668.asp",
]


def _page_text(page) -> str:
    # Normalize page text for simple block detection.
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
    ]
    return any(b in title or b in text for b in blockers)


def _fetch_with_fallbacks(url: str, wait_selector: str = "body"):
    # 1) Try plain HTTP first.
    page = Fetcher.get(url)
    if not _is_blocked(page):
        return page, "http"

    # 2) Try dynamic (Playwright) for JS-heavy pages.
    page = DynamicFetcher.fetch(url, wait_selector=wait_selector, network_idle=True)
    if not _is_blocked(page):
        return page, "dynamic"

    # 3) Try stealth for anti-bot protection.
    page = StealthyFetcher.fetch(
        url,
        wait_selector=wait_selector,
        network_idle=True,
        solve_cloudflare=True,
        timeout=60000,
    )
    return page, "stealth"


def _fetch_forum(url: str, mode: str, wait_selector: str = "body") -> Tuple[object, str]:
    if mode == "dynamic":
        page = DynamicFetcher.fetch(url, wait_selector=wait_selector, network_idle=True)
        return page, "dynamic"
    if mode == "stealth":
        page = StealthyFetcher.fetch(
            url,
            wait_selector=wait_selector,
            network_idle=True,
            solve_cloudflare=True,
            timeout=60000,
        )
        return page, "stealth"
    return _fetch_with_fallbacks(url, wait_selector=wait_selector)


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


def _extract_caclubindia_search(page) -> List[Dict[str, str]]:
    results = []
    seen = set()
    items = page.css("div.gsc-webResult, div.gs-webResult")
    for item in items:
        title = item.css(".gs-title a.gs-title::text").get()
        if not title:
            title = " ".join(item.css(".gs-title a.gs-title *::text").getall()).strip()
        url = item.css(".gs-title a.gs-title::attr(href)").get()
        snippet = item.css(".gs-snippet::text").get()
        if not snippet:
            snippet = " ".join(item.css(".gs-snippet *::text").getall()).strip()
        if not url:
            continue
        # Drop non-content/ads/login/browse pages
        if any(
            bad in url
            for bad in (
                "/pro/",
                "/login",
                "/register",
                "/browse.asp",
                "/browse.aspx",
                "javascript:",
            )
        ):
            continue
        if "search_results_new.asp" in url:
            continue
        # Allow only real content paths
        if not any(seg in url for seg in ("/experts/", "/forum/", "/articles/")):
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append(
            {
                "title": title or "",
                "url": url or "",
                "snippet": snippet or "",
            }
        )
    return results


def _build_search_url(query: str) -> str:
    return f"https://www.caclubindia.com/search_results_new.asp?q={quote_plus(query)}"


def _fetch_search_with_fallbacks(query: str):
    search_url = _build_search_url(query)
    wait_sel = ".gsc-resultsRoot, .gsc-webResult, .gs-webResult"

    # Try HTTP first.
    page = Fetcher.get(search_url)
    results = _extract_caclubindia_search(page)
    if results:
        return page, "http", results, search_url

    # Try dynamic.
    page = DynamicFetcher.fetch(search_url, wait_selector=wait_sel, network_idle=True)
    results = _extract_caclubindia_search(page)
    if results:
        return page, "dynamic", results, search_url

    # Try stealth.
    page = StealthyFetcher.fetch(
        search_url,
        wait_selector=wait_sel,
        network_idle=True,
        solve_cloudflare=True,
        timeout=60000,
    )
    results = _extract_caclubindia_search(page)
    return page, "stealth", results, search_url


def _extract_caclubindia_article(page) -> Dict[str, str]:
    title = (
        page.css("h1::text").get()
        or " ".join(page.css("h1 *::text").getall()).strip()
    ).strip()

    # Extract visible text nodes, excluding script/style content.
    text_nodes = page.xpath(
        "//body//text()[not(ancestor::script) and not(ancestor::style)]"
    ).getall()
    lines = [" ".join(t.split()) for t in text_nodes]
    lines = [t for t in lines if t]

    # Focus only the relevant section between title and similar/related blocks.
    start_idx = 0
    if title:
        for i, t in enumerate(lines):
            if title in t:
                start_idx = i
                break

    end_markers = [
        "Similar Resolved Queries",
        "Unanswered Queries",
        "Quick Links",
        "Browse by Category",
    ]
    end_idx = len(lines)
    for i in range(start_idx, len(lines)):
        if any(m in lines[i] for m in end_markers):
            end_idx = i
            break

    segment = lines[start_idx:end_idx]

    status = ""
    for t in segment:
        if "This query is" in t:
            status = t.replace("This query is :", "").strip()
            break

    # Parse posts (Querist / Expert) with date and body text.
    posts = []
    stop_phrases = [
        "You need to be the querist",
        "Summarize this with AI",
    ]

    # Identify role markers to split content cleanly.
    markers = []
    for idx, line in enumerate(segment):
        if "(Querist)" in line:
            markers.append((idx, "Querist"))
        elif "(Expert)" in line:
            markers.append((idx, "Expert"))

    for m_idx, (idx, role) in enumerate(markers):
        line = segment[idx]
        author = line.replace(f" ({role})", "").strip()
        if not author and idx > 0:
            author = segment[idx - 1].strip()

        next_idx = markers[m_idx + 1][0] if m_idx + 1 < len(markers) else len(segment)
        body_lines = []
        date = ""

        j = idx + 1
        while j < next_idx:
            if any(p in segment[j] for p in stop_phrases):
                break
            if "Message likes" in segment[j] or "* * *" in segment[j]:
                break
            if segment[j] == "Follow":
                j += 1
                continue

            if not date:
                found = _find_date(segment[j])
                if found:
                    date = found
                    rest = segment[j].replace(found, "").strip()
                    if rest:
                        body_lines.append(rest)
                    j += 1
                    continue

            body_lines.append(segment[j])
            j += 1

        body = "\n".join([p for p in body_lines if p]).strip()
        posts.append(
            {
                "author": author,
                "role": role,
                "date": date,
                "body": body,
            }
        )

    return {
        "title": title,
        "status": status,
        "posts": posts,
    }


def _find_date(text: str) -> Optional[str]:
    match = re.search(r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b", text)
    return match.group(0) if match else None


def _extract_caclubindia_forum(page) -> Dict[str, str]:
    title = (
        page.css("h1::text").get()
        or " ".join(page.css("h1 *::text").getall()).strip()
    ).strip()

    posts = []
    replies = []

    # New forum layout: explicit post and reply cards.
    post_nodes = page.css(".post-card .post-content")
    reply_nodes = page.css(".reply-card .post-content")
    if post_nodes or reply_nodes:
        for p in post_nodes:
            text = " ".join(p.css("p::text, li::text").getall()).strip()
            if text:
                posts.append({"author": "", "role": "Post", "date": "", "body": text})
        for r in reply_nodes:
            text = " ".join(r.css("p::text, li::text").getall()).strip()
            if text:
                replies.append(
                    {"author": "", "role": "Reply", "date": "", "body": text}
                )
        return {
            "title": title,
            "status": "",
            "posts": posts,
            "replies": replies,
        }

    def _clean_lines(nodes):
        lines = [" ".join(t.split()) for t in nodes]
        return [t for t in lines if t]

    def _extract_post_from_text(lines):
        author = ""
        date = ""
        body_lines = []

        for line in lines:
            if not author:
                m = re.search(r"Posted by\\s*[:\\-]?\\s*(.+)", line, re.I)
                if m:
                    author = m.group(1).strip()
                    continue
            if not date:
                found = _find_date(line)
                if found:
                    date = found
                    rest = line.replace(found, "").strip()
                    if rest:
                        body_lines.append(rest)
                    continue
            body_lines.append(line)

        body = "\n".join([b for b in body_lines if b]).strip()
        return author, date, body

    # Prefer structured containers.
    containers = page.css(
        "div[id^='post'], div[id*='post'], div.post, div.forum_post, "
        "div.post-container, div.msg, div.message, div.forum_message, "
        "td.msg, td.post, td.message"
    )

    for c in containers:
        text_nodes = c.xpath(".//text()[not(ancestor::script) and not(ancestor::style)]").getall()
        lines = _clean_lines(text_nodes)
        if not lines:
            continue

        # Skip huge containers that look like full-page blocks.
        if len(lines) > 800:
            continue

        author = (
            c.css(".author a::text, .username::text, .user-name::text, .author::text")
            .get()
            or ""
        ).strip()
        date = (
            c.css(".date::text, .postdate::text, .posted-on::text, .post-date::text")
            .get()
            or ""
        ).strip()
        if not date:
            date = _find_date(" ".join(lines)) or ""

        body = " ".join(
            c.css(
                ".postbody *::text, .message *::text, .content *::text, .post-content *::text"
            ).getall()
        ).strip()

        if not body:
            author, date, body = _extract_post_from_text(lines)

        if author or body:
            posts.append(
                {
                    "author": author,
                    "role": "",
                    "date": date,
                    "body": body,
                }
            )

    # Fallback: text segmentation from full page content.
    if not posts:
        text_nodes = page.xpath(
            "//body//text()[not(ancestor::script) and not(ancestor::style)]"
        ).getall()
        lines = _clean_lines(text_nodes)

        # Trim to the meaningful section.
        start_idx = 0
        if title:
            for i, t in enumerate(lines):
                if t.strip() == title or title in t:
                    start_idx = i
                    break
        end_markers = ["Summarize this with AI", "Leave a Reply", "Similar Threads"]
        end_idx = len(lines)
        for i in range(start_idx, len(lines)):
            if any(m in lines[i] for m in end_markers):
                end_idx = i
                break
        segment = lines[start_idx:end_idx]

        # Build author markers based on forum layout.
        author_idxs = []
        for i, t in enumerate(segment):
            if t.startswith("#### "):
                author_idxs.append(i)
            elif i > 0 and segment[i - 1] == "Image: User Avatar":
                author_idxs.append(i)
            elif t.lower().startswith("posted by"):
                author_idxs.append(i)

        for idx_i, idx in enumerate(author_idxs):
            next_idx = author_idxs[idx_i + 1] if idx_i + 1 < len(author_idxs) else len(segment)
            chunk = segment[idx:next_idx]
            author_line = chunk[0]
            author = author_line.replace("####", "").strip()
            author = author.replace("(Author)", "").strip()
            if author.lower().startswith("posted by"):
                author = author.split(":", 1)[-1].strip()

            # Remove common meta lines.
            meta_phrases = [
                "Points Joined",
                "Joined",
                "Reply",
                "Share",
                "Follow",
                "Report",
                "Replies (",
            ]
            cleaned = [c for c in chunk[1:] if not any(m in c for m in meta_phrases)]

            # Extract date from lines like: "On 01 August 2013 at 11:12"
            date = ""
            body_lines = []
            for line in cleaned:
                found = _find_date(line)
                if found and not date:
                    date = found
                    rest = line.replace(found, "").strip()
                    if rest and not rest.lower().startswith("on"):
                        body_lines.append(rest)
                    continue
                # Lines like "On 01 August 2013 at 11:12"
                if not date and line.lower().startswith("on "):
                    found = _find_date(line)
                    if found:
                        date = found
                        rest = line.replace(found, "").strip()
                        rest = rest.replace("on", "", 1).strip()
                        if rest:
                            body_lines.append(rest)
                        continue
                body_lines.append(line)

            body = "\n".join([b for b in body_lines if b]).strip()
            if author or body:
                posts.append(
                    {"author": author, "role": "", "date": date, "body": body}
                )

    return {
        "title": title,
        "status": "",
        "posts": posts,
        "replies": replies,
    }


def _extract_caclubindia_article_page(page) -> Dict[str, str]:
    title = (
        page.css("h1::text").get()
        or " ".join(page.css("h1 *::text").getall()).strip()
    ).strip()

    text_nodes = page.xpath(
        "//body//text()[not(ancestor::script) and not(ancestor::style)]"
    ).getall()
    lines = [" ".join(t.split()) for t in text_nodes]
    lines = [t for t in lines if t]

    start_idx = 0
    if title:
        for i, t in enumerate(lines):
            if t.strip() == title or title in t:
                start_idx = i
                break

    end_markers = [
        "Summarize this with AI",
        "Published by",
        "Comments",
        "Related Articles",
        "Popular Articles",
    ]
    end_idx = len(lines)
    for i in range(start_idx, len(lines)):
        if any(m in lines[i] for m in end_markers):
            end_idx = i
            break

    segment = lines[start_idx:end_idx]

    author = ""
    date = ""
    for i, t in enumerate(segment[:8]):
        if "Last updated:" in t:
            date = t.split("Last updated:")[-1].strip()
        if i > 0 and ("CA " in t or t.startswith("CA ")):
            author = t.replace(",", "").strip()
        if t.startswith("CA ") and not author:
            author = t.strip()

    content = "\n".join(segment[1:]).strip()

    return {
        "title": title,
        "author": author,
        "date": date,
        "content": content,
    }


def run(
    caclubindia_urls: List[str], forum_fetcher: str, dump_dir: Optional[str]
) -> Dict[str, Dict]:
    start = time.time()
    out = {
        "caclubindia": {"items": []},
        "meta": {},
    }

    for url in caclubindia_urls:
        c_wait = ".gsc-resultsRoot, .gsc-webResult, .gs-webResult, h1"
        if "/forum/" in url:
            c_page, c_method = _fetch_forum(url, forum_fetcher, wait_selector=c_wait)
        else:
            c_page, c_method = _fetch_with_fallbacks(url, wait_selector=c_wait)
        _maybe_dump_html(c_page, url, dump_dir)

        item = {
            "url": url,
            "method": c_method,
        }

        if "search_results_new.asp" in url:
            item["type"] = "search"
            item["results"] = _extract_caclubindia_search(c_page)
        elif "/forum/" in url:
            item["type"] = "forum"
            item["article"] = _extract_caclubindia_forum(c_page)
        elif "/articles/" in url:
            item["type"] = "article_page"
            item["article"] = _extract_caclubindia_article_page(c_page)
        else:
            item["type"] = "expert_thread"
            item["article"] = _extract_caclubindia_article(c_page)

        out["caclubindia"]["items"].append(item)

    out["meta"]["elapsed_sec"] = round(time.time() - start, 2)
    out["meta"]["timestamp"] = int(time.time())
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Fetch CAClubIndia pages using Scrapling."
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Search query (fetch first page links, then scrape each link)",
    )
    parser.add_argument(
        "--caclubindia-url",
        action="append",
        default=None,
        help="CAClubIndia URL (repeatable)",
    )
    parser.add_argument(
        "--forum-fetcher",
        choices=["auto", "dynamic", "stealth"],
        default="auto",
        help="Fetcher mode for forum URLs",
    )
    parser.add_argument(
        "--dump-html",
        default=None,
        help="Directory to dump raw HTML per URL",
    )
    parser.add_argument(
        "--adaptive",
        action="store_true",
        help="Enable Scrapling adaptive parsing for all fetchers",
    )
    parser.add_argument(
        "--auto-match",
        action="store_true",
        help="Enable Scrapling auto-match for all fetchers",
    )
    parser.add_argument(
        "--out",
        default="out.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--search-out",
        default="caclub_search.json",
        help="Output JSON path for search results",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=5,
        help="Limit number of links to fetch (0 = no limit)",
    )
    args = parser.parse_args()

    if args.adaptive:
        Fetcher.adaptive = True
        DynamicFetcher.adaptive = True
        StealthyFetcher.adaptive = True
    if args.auto_match:
        for cls in (Fetcher, DynamicFetcher, StealthyFetcher):
            if hasattr(cls, "auto_match"):
                cls.auto_match = True
            # Newer versions renamed auto_match -> adaptive; keep it robust.
            if hasattr(cls, "adaptive") and not args.adaptive:
                cls.adaptive = True

    urls = args.caclubindia_url or DEFAULT_CACLUBINDIA_URLS

    if args.query:
        page, method, search_results, search_url = _fetch_search_with_fallbacks(
            args.query
        )
        with open(args.search_out, "w", encoding="utf-8") as f:
            json.dump(
                {"query": args.query, "url": search_url, "method": method, "results": search_results},
                f,
                indent=2,
                ensure_ascii=True,
            )
        urls = [r["url"] for r in search_results if r.get("url")]
        if args.max_links and args.max_links > 0:
            urls = urls[: args.max_links]

    data = run(urls, args.forum_fetcher, args.dump_html)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)

    print(json.dumps(data, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
