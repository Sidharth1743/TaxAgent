"""Tests for graph data and insights REST endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.document_extractor import ExtractedDocument, FormField
from memory.spanner_graph import analyze_insights, fetch_user_graph


# ---------------------------------------------------------------------------
# Helpers: build mock Spanner snapshot results
# ---------------------------------------------------------------------------


def _mock_database_with_data():
    """Return a mock database that simulates Spanner snapshot reads.

    Graph structure:
      user1 --HAS_SESSION--> sess1 --CONTAINS--> q1
      q1 --REFERENCES--> concept1 (Section 44ADA)
      q1 --INVOLVES--> entity1 (Salary Income, india)
      q1 --RESOLVED_BY--> res1 (answered)
      entity1 --GOVERNED_BY--> jur1 (india)
      user1 --OWNS--> entity1
    """
    db = MagicMock()

    edges = [
        ("e1", "user1", "sess1", "HAS_SESSION"),
        ("e2", "sess1", "q1", "CONTAINS"),
        ("e3", "q1", "concept1", "REFERENCES"),
        ("e4", "q1", "entity1", "INVOLVES"),
        ("e5", "entity1", "jur1", "GOVERNED_BY"),
        ("e6", "q1", "res1", "RESOLVED_BY"),
        ("e7", "user1", "entity1", "OWNS"),
    ]

    table_rows = {
        "Users": [("user1", "2026-01-01")],
        "Sessions": [("sess1", "user1", "2026-01-01")],
        "Queries": [("q1", "sess1", "section 80D health insurance", "deduction", "2026-01-01")],
        "Concepts": [("concept1", "Section 44ADA")],
        "TaxEntities": [("entity1", "Salary Income", "INR", "india", "Mumbai")],
        "Jurisdictions": [("jur1", "india")],
        "TaxForms": [],
        "Resolutions": [("res1", "q1", "answered", 0.9, "2026-01-01")],
        "Ambiguities": [],
    }

    snapshot = MagicMock()

    def execute_sql_side_effect(sql, **kwargs):
        params = kwargs.get("params", {})

        # --- fetch_user_graph: BFS edge queries ---
        if "FROM Edges" in sql and "UNNEST(@node_ids)" in sql:
            node_ids = params.get("node_ids", [])
            return [e for e in edges if e[1] in node_ids or e[2] in node_ids]

        # --- fetch_user_graph: node label lookups ---
        for table_name, rows in table_rows.items():
            if f"FROM {table_name}" in sql and "UNNEST(@node_ids)" in sql:
                node_ids = params.get("node_ids", [])
                return [r for r in rows if r[0] in node_ids]

        # --- analyze_insights: jurisdiction join query ---
        if "Jurisdictions" in sql and "GOVERNED_BY" in sql and "OWNS" in sql:
            user_id = params.get("user_id", "")
            if user_id == "user1":
                return [("india",)]
            return []

        # --- analyze_insights: concept join query ---
        if "Concepts" in sql and "REFERENCES" in sql and "HAS_SESSION" in sql:
            user_id = params.get("user_id", "")
            if user_id == "user1":
                return [("Section 44ADA",)]
            return []

        # --- analyze_insights: resolution status join query ---
        if "Resolutions" in sql and "RESOLVED_BY" in sql and "HAS_SESSION" in sql:
            user_id = params.get("user_id", "")
            if user_id == "user1":
                return [("answered",)]
            return []

        return []

    snapshot.execute_sql = execute_sql_side_effect
    snapshot.__enter__ = lambda s: s
    snapshot.__exit__ = lambda s, *a: None
    db.snapshot.return_value = snapshot
    return db


def _mock_empty_database():
    """Return a mock database with no data for any user."""
    db = MagicMock()
    snapshot = MagicMock()
    snapshot.execute_sql = lambda sql, **kw: []
    snapshot.__enter__ = lambda s: s
    snapshot.__exit__ = lambda s, *a: None
    db.snapshot.return_value = snapshot
    return db


# ---------------------------------------------------------------------------
# Tests: fetch_user_graph
# ---------------------------------------------------------------------------


class TestFetchUserGraph:

    def test_returns_nodes_and_links_keys(self):
        db = _mock_database_with_data()
        result = fetch_user_graph(db, "user1")
        assert "nodes" in result
        assert "links" in result

    def test_each_node_has_required_fields(self):
        db = _mock_database_with_data()
        result = fetch_user_graph(db, "user1")
        assert len(result["nodes"]) > 0, "Expected at least one node"
        for node in result["nodes"]:
            assert "id" in node
            assert "label" in node
            assert "type" in node
            assert "color" in node

    def test_node_types_correctly_colored(self):
        db = _mock_database_with_data()
        result = fetch_user_graph(db, "user1")
        color_map = {
            "User": "#8b5cf6",
            "Session": "#3b82f6",
            "Concept": "#22c55e",
            "TaxEntity": "#f97316",
            "Jurisdiction": "#ef4444",
            "TaxForm": "#14b8a6",
            "Resolution": "#eab308",
            "Ambiguity": "#6b7280",
        }
        for node in result["nodes"]:
            if node["type"] in color_map:
                assert node["color"] == color_map[node["type"]], (
                    f"Node type {node['type']} should be {color_map[node['type']]} "
                    f"but got {node['color']}"
                )

    def test_each_link_has_required_fields(self):
        db = _mock_database_with_data()
        result = fetch_user_graph(db, "user1")
        node_ids = {n["id"] for n in result["nodes"]}
        assert len(result["links"]) > 0, "Expected at least one link"
        for link in result["links"]:
            assert "source" in link
            assert "target" in link
            assert "type" in link
            assert link["source"] in node_ids, f"Link source {link['source']} not in node ids"
            assert link["target"] in node_ids, f"Link target {link['target']} not in node ids"

    def test_empty_user_returns_empty_graph(self):
        db = _mock_empty_database()
        result = fetch_user_graph(db, "nonexistent_user")
        assert result == {"nodes": [], "links": []}


# ---------------------------------------------------------------------------
# Tests: analyze_insights
# ---------------------------------------------------------------------------


class TestAnalyzeInsights:

    def test_returns_list_of_dicts(self):
        db = _mock_database_with_data()
        result = analyze_insights(db, "user1")
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, dict)
            assert "type" in item
            assert "message" in item
            assert "section" in item
            assert "potential_savings" in item

    def test_detects_missing_india_deductions(self):
        """User has india jurisdiction but no 80C concept -> should suggest 80C."""
        db = _mock_database_with_data()
        result = analyze_insights(db, "user1")
        messages = [r["message"] for r in result]
        # User has Section 44ADA concept but not 80C, so 80C should be suggested
        assert any("80C" in m for m in messages), f"Expected 80C suggestion in {messages}"

    def test_empty_user_returns_empty_list(self):
        db = _mock_empty_database()
        result = analyze_insights(db, "nonexistent_user")
        assert result == []


# ---------------------------------------------------------------------------
# Tests: FastAPI endpoints
# ---------------------------------------------------------------------------


class TestGraphAPIEndpoints:

    @patch("backend.graph_api.get_graph_database")
    def test_get_graph_returns_200(self, mock_get_db):
        mock_get_db.return_value = _mock_database_with_data()
        from backend.graph_api import app

        client = TestClient(app)
        resp = client.get("/api/graph/user1")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "links" in data

    @patch("backend.graph_api.get_graph_database")
    def test_get_insights_returns_200(self, mock_get_db):
        mock_get_db.return_value = _mock_database_with_data()
        from backend.graph_api import app

        client = TestClient(app)
        resp = client.get("/api/graph/user1/insights")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_compute_w2_normalizes_raw_box_labels(self):
        from backend.graph_api import _document_store, app

        doc = ExtractedDocument(
            doc_id="w2-raw-doc",
            form_type="w2",
            jurisdiction="usa",
            raw_text="",
            fields=[
                FormField(name="1 Wages, tips, other compensation", value="95000", confidence=0.98),
                FormField(name="2 Federal income tax withheld", value="12000", confidence=0.98),
            ],
        )
        _document_store[doc.doc_id] = doc

        client = TestClient(app)
        try:
            resp = client.post(f"/api/documents/{doc.doc_id}/compute", json={"filing_status": "single"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["computation"]["federal_tax"] > 0
            assert data["computation"]["standard_deduction"] == 15000
        finally:
            _document_store.pop(doc.doc_id, None)
