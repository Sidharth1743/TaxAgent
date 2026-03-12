"""PageIndex vectorless memory store for financial-grade retrieval.

Wraps the PageIndex Python SDK to provide:
- Indexing scraped expert content for future fast retrieval
- Querying indexed content before scraping (cache-first pattern)
- Submitting uploaded tax documents for reasoning-based Q&A
"""

import hashlib
import os
import tempfile
import structlog
from typing import Any, Dict, List, Optional

from config import PAGEINDEX_API_KEY, PAGEINDEX_ENABLED

logger = structlog.get_logger(__name__)

_client = None


def get_pageindex_client():
    """Lazy singleton PageIndex client."""
    global _client
    if _client is None:
        if not PAGEINDEX_API_KEY:
            raise RuntimeError("PAGEINDEX_API_KEY not configured")
        from pageindex import PageIndexClient
        _client = PageIndexClient(api_key=PAGEINDEX_API_KEY)
    return _client


def index_scraped_content(query: str, source: str, evidence: List[Dict[str, Any]]) -> Optional[str]:
    """Index scraped evidence in PageIndex for future retrieval.

    Converts evidence items into a structured text document and submits
    to PageIndex. Returns the doc_id on success, None on failure.

    Args:
        query: The original user query that produced this evidence.
        source: Source name (e.g., "caclub", "taxtmi", "turbotax", "taxprofblog").
        evidence: List of evidence dicts with keys: title, url, snippet, date, reply_count.
    """
    if not PAGEINDEX_ENABLED:
        return None
    if not evidence:
        return None

    try:
        client = get_pageindex_client()

        # Build a structured text document from evidence
        lines = [f"Tax Query: {query}", f"Source: {source}", ""]
        for i, item in enumerate(evidence, 1):
            lines.append(f"--- Evidence {i} ---")
            lines.append(f"Title: {item.get('title', 'N/A')}")
            lines.append(f"URL: {item.get('url', '')}")
            lines.append(f"Date: {item.get('date', 'N/A')}")
            lines.append(f"Reply Count: {item.get('reply_count', 0)}")
            lines.append(f"Content: {item.get('snippet', '')}")
            lines.append("")

        content = "\n".join(lines)

        # Create a deterministic doc name from query+source for deduplication
        content_hash = hashlib.sha256(f"{query}:{source}".encode()).hexdigest()[:12]
        doc_name = f"tax_{source}_{content_hash}.txt"

        # Write to temp file and submit
        tmp_path = os.path.join(tempfile.gettempdir(), doc_name)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)

        result = client.submit_document(tmp_path)
        doc_id = result.get("doc_id")
        logger.info("pageindex.indexed", source=source, query=query[:50], doc_id=doc_id)

        # Clean up temp file
        os.unlink(tmp_path)
        return doc_id

    except Exception as e:
        logger.warning("pageindex.index_failed", source=source, error=str(e))
        return None


def query_pageindex(query: str, doc_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Query PageIndex for previously indexed content.

    Uses the chat_completions API for reasoning-based retrieval.
    Returns a dict with 'answer' and 'source' keys on success, None on miss/failure.

    Args:
        query: The user's tax question.
        doc_id: Optional specific doc_id to query against. If None, queries across all indexed docs.
    """
    if not PAGEINDEX_ENABLED:
        return None

    try:
        client = get_pageindex_client()

        kwargs = {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Answer this tax question using only the indexed content. "
                        f"If the indexed content does not contain relevant information, "
                        f"respond with exactly 'NO_MATCH'.\n\n"
                        f"Question: {query}"
                    ),
                }
            ],
        }
        if doc_id:
            kwargs["doc_id"] = doc_id

        response = client.chat_completions(**kwargs)

        # Handle streaming vs non-streaming response
        if isinstance(response, str):
            answer = response
        elif isinstance(response, dict):
            answer = response.get("content", "") or response.get("message", "")
        else:
            answer = str(response)

        if not answer or "NO_MATCH" in answer:
            logger.debug("pageindex.cache_miss", query=query[:50])
            return None

        logger.info("pageindex.cache_hit", query=query[:50])
        return {"answer": answer, "source": "pageindex"}

    except Exception as e:
        logger.warning("pageindex.query_failed", error=str(e))
        return None


def submit_document_to_pageindex(file_path: str) -> Optional[str]:
    """Submit a document (PDF, image) to PageIndex for reasoning-based Q&A.

    Used when user uploads a tax form -- the document is indexed in PageIndex
    so subsequent questions about it can be answered via chat_completions.

    Args:
        file_path: Path to the document file.

    Returns:
        doc_id on success, None on failure.
    """
    if not PAGEINDEX_ENABLED:
        return None

    try:
        client = get_pageindex_client()
        result = client.submit_document(file_path)
        doc_id = result.get("doc_id")
        logger.info("pageindex.document_submitted", file_path=file_path, doc_id=doc_id)
        return doc_id

    except Exception as e:
        logger.warning("pageindex.document_submit_failed", error=str(e))
        return None


def ask_document(doc_id: str, question: str) -> Optional[str]:
    """Ask a question about a previously submitted document.

    Args:
        doc_id: The PageIndex doc_id from submit_document_to_pageindex.
        question: The user's question about the document.

    Returns:
        Answer string on success, None on failure.
    """
    if not PAGEINDEX_ENABLED:
        return None

    try:
        client = get_pageindex_client()
        response = client.chat_completions(
            messages=[{"role": "user", "content": question}],
            doc_id=doc_id,
        )

        if isinstance(response, str):
            return response
        elif isinstance(response, dict):
            return response.get("content", "") or response.get("message", "")
        return str(response)

    except Exception as e:
        logger.warning("pageindex.ask_document_failed", doc_id=doc_id, error=str(e))
        return None
