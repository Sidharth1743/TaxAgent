"""Tests for memory/pageindex_store.py.

Uses monkeypatching to avoid needing a real PageIndex API key.
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def reset_client():
    """Reset singleton client between tests."""
    import memory.pageindex_store as store
    store._client = None
    yield
    store._client = None


@pytest.fixture
def mock_config(monkeypatch):
    """Set config to enabled with fake key."""
    monkeypatch.setattr("memory.pageindex_store.PAGEINDEX_API_KEY", "test-key-123")
    monkeypatch.setattr("memory.pageindex_store.PAGEINDEX_ENABLED", True)


@pytest.fixture
def mock_client():
    """Mock PageIndexClient."""
    client = MagicMock()
    with patch("memory.pageindex_store.get_pageindex_client", return_value=client):
        yield client


def test_index_scraped_content_disabled(monkeypatch):
    """When PAGEINDEX_ENABLED is False, indexing returns None."""
    monkeypatch.setattr("memory.pageindex_store.PAGEINDEX_ENABLED", False)
    from memory.pageindex_store import index_scraped_content
    result = index_scraped_content("test query", "caclub", [{"title": "T", "url": "http://x"}])
    assert result is None


def test_index_scraped_content_empty_evidence(mock_config):
    """Empty evidence list returns None without calling API."""
    from memory.pageindex_store import index_scraped_content
    result = index_scraped_content("test", "caclub", [])
    assert result is None


def test_index_scraped_content_success(mock_config, mock_client):
    """Successful indexing returns doc_id."""
    mock_client.submit_document.return_value = {"doc_id": "doc-abc"}
    from memory.pageindex_store import index_scraped_content
    result = index_scraped_content(
        "section 80C",
        "caclub",
        [{"title": "80C Guide", "url": "http://caclub.com/80c", "snippet": "Limit is 1.5L", "date": "2024-01-01", "reply_count": 5}],
    )
    assert result == "doc-abc"
    mock_client.submit_document.assert_called_once()


def test_query_pageindex_disabled(monkeypatch):
    """When disabled, query returns None."""
    monkeypatch.setattr("memory.pageindex_store.PAGEINDEX_ENABLED", False)
    from memory.pageindex_store import query_pageindex
    assert query_pageindex("test") is None


def test_query_pageindex_cache_miss(mock_config, mock_client):
    """When PageIndex returns NO_MATCH, returns None."""
    mock_client.chat_completions.return_value = "NO_MATCH"
    from memory.pageindex_store import query_pageindex
    result = query_pageindex("obscure tax question")
    assert result is None


def test_query_pageindex_cache_hit(mock_config, mock_client):
    """When PageIndex returns content, returns answer dict."""
    mock_client.chat_completions.return_value = "Section 80C limit is Rs 1.5 lakh per year."
    from memory.pageindex_store import query_pageindex
    result = query_pageindex("what is 80C limit")
    assert result is not None
    assert result["answer"] == "Section 80C limit is Rs 1.5 lakh per year."
    assert result["source"] == "pageindex"


def test_submit_document_success(mock_config, mock_client):
    """Document submission returns doc_id."""
    mock_client.submit_document.return_value = {"doc_id": "doc-xyz"}
    from memory.pageindex_store import submit_document_to_pageindex
    result = submit_document_to_pageindex("/tmp/form16.pdf")
    assert result == "doc-xyz"


def test_ask_document_success(mock_config, mock_client):
    """Document Q&A returns answer string."""
    mock_client.chat_completions.return_value = "Total income is Rs 12,00,000"
    from memory.pageindex_store import ask_document
    result = ask_document("doc-xyz", "What is the total income?")
    assert result == "Total income is Rs 12,00,000"
