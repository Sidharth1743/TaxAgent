"""Tests for memory/extractor.py — verifies google.genai SDK migration."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


def test_extract_memory_no_api_key():
    """extract_memory returns {} when GOOGLE_API_KEY is empty."""
    with patch.dict("os.environ", {"GOOGLE_API_KEY": ""}):
        from memory.extractor import extract_memory
        assert extract_memory("test") == {}


def test_extract_memory_uses_new_sdk():
    """extract_memory calls genai.Client + client.models.generate_content."""
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({"concepts": ["80C"], "intent": "deduction"})

    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.return_value = mock_resp

    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
        with patch("memory.extractor.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client_instance
            # Ensure _HAS_GENAI is True
            with patch("memory.extractor._HAS_GENAI", True):
                from memory.extractor import extract_memory
                result = extract_memory("section 80C deduction")

    mock_genai.Client.assert_called_once_with(api_key="test-key")
    call_kwargs = mock_client_instance.models.generate_content.call_args
    assert call_kwargs.kwargs["model"] == "gemini-3.1-flash-lite-preview"
    assert "response_mime_type" in str(call_kwargs.kwargs.get("config", {}))
    assert result == {"concepts": ["80C"], "intent": "deduction"}


def test_extract_memory_handles_bad_json():
    """extract_memory returns {} when Gemini returns non-JSON text."""
    mock_resp = MagicMock()
    mock_resp.text = "not valid json at all"

    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.return_value = mock_resp

    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
        with patch("memory.extractor.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client_instance
            with patch("memory.extractor._HAS_GENAI", True):
                from memory.extractor import extract_memory
                result = extract_memory("some query")

    assert result == {}


def test_no_old_sdk_import():
    """Verify that google.generativeai is NOT imported anywhere in extractor."""
    import inspect

    import memory.extractor as mod
    source = inspect.getsource(mod)
    assert "google.generativeai" not in source, (
        "Old SDK google.generativeai should not be used"
    )
