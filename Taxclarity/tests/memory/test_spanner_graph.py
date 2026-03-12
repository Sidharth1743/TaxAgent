"""Tests for memory/spanner_graph.py — verifies UNNEST parameterization."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

# Mock the spanner module before importing spanner_graph
mock_spanner = MagicMock()
mock_spanner.param_types.STRING = "STRING"
mock_spanner.param_types.Array.return_value = "ARRAY<STRING>"
sys.modules["google.cloud"] = MagicMock()
sys.modules["google.cloud.spanner"] = mock_spanner


def _make_mock_database(rows=None):
    """Create a mock Spanner database that captures SQL and params."""
    if rows is None:
        rows = []

    mock_snapshot = MagicMock()
    mock_snapshot.__enter__ = MagicMock(return_value=mock_snapshot)
    mock_snapshot.__exit__ = MagicMock(return_value=False)
    mock_snapshot.execute_sql.return_value = rows

    mock_db = MagicMock()
    mock_db.snapshot.return_value = mock_snapshot

    return mock_db, mock_snapshot


def test_fetch_memory_context_empty_lists():
    """With empty concepts and entities, returns empty results immediately."""
    with patch.dict("sys.modules", {"google.cloud.spanner": mock_spanner, "google.cloud": MagicMock()}):
        from memory.spanner_graph import fetch_memory_context
        mock_db, _ = _make_mock_database()
        result = fetch_memory_context(mock_db, "user1", [], [])
        assert result == {"prior_resolutions": [], "unresolved_queries": []}


def test_fetch_memory_context_sql_uses_unnest_concepts():
    """SQL uses UNNEST(@concepts) with correct array param for multiple concepts."""
    with patch.dict("sys.modules", {"google.cloud.spanner": mock_spanner, "google.cloud": MagicMock()}):
        # Re-import to pick up the mock
        import importlib

        import memory.spanner_graph as sg
        importlib.reload(sg)

        mock_db, mock_snapshot = _make_mock_database()
        sg.fetch_memory_context(mock_db, "user1", ["80C", "80D"], [])

        call_args = mock_snapshot.execute_sql.call_args
        sql = call_args.args[0] if call_args.args else call_args.kwargs.get("sql", "")
        params = call_args.kwargs.get("params", {}) if "params" in (call_args.kwargs or {}) else call_args[1] if len(call_args.args) > 1 else {}

        # Check via kwargs
        if not params and call_args.kwargs:
            params = call_args.kwargs.get("params", {})

        assert "UNNEST(@concepts)" in sql, f"SQL should use UNNEST(@concepts), got: {sql}"
        assert params.get("concepts") == ["80C", "80D"], f"params should have concepts array, got: {params}"


def test_fetch_memory_context_sql_uses_unnest_entities():
    """SQL uses UNNEST(@entities) with correct array param for multiple entities."""
    with patch.dict("sys.modules", {"google.cloud.spanner": mock_spanner, "google.cloud": MagicMock()}):
        import importlib

        import memory.spanner_graph as sg
        importlib.reload(sg)

        mock_db, mock_snapshot = _make_mock_database()
        sg.fetch_memory_context(mock_db, "user1", [], ["CompanyA", "CompanyB"])

        call_args = mock_snapshot.execute_sql.call_args
        sql = call_args.args[0] if call_args.args else call_args.kwargs.get("sql", "")
        params = call_args.kwargs.get("params", {}) if call_args.kwargs else {}

        assert "UNNEST(@entities)" in sql, f"SQL should use UNNEST(@entities), got: {sql}"
        assert params.get("entities") == ["CompanyA", "CompanyB"], f"params should have entities array, got: {params}"
