#!/usr/bin/env python3
"""Spanner graph storage for user tax memory."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from google.cloud import spanner
except Exception:  # pragma: no cover - optional runtime dependency
    spanner = None


@dataclass
class SpannerConfig:
    project_id: str
    instance_id: str
    database_id: str


def load_config() -> Optional[SpannerConfig]:
    project_id = os.getenv("SPANNER_PROJECT_ID", "").strip()
    instance_id = os.getenv("SPANNER_INSTANCE_ID", "").strip()
    database_id = os.getenv("SPANNER_DATABASE_ID", "").strip()
    if not (project_id and instance_id and database_id):
        return None
    return SpannerConfig(project_id, instance_id, database_id)


def get_client(cfg: SpannerConfig):
    if not spanner:
        raise RuntimeError("google-cloud-spanner is not installed")
    client = spanner.Client(project=cfg.project_id)
    instance = client.instance(cfg.instance_id)
    database = instance.database(cfg.database_id)
    return database


DDL_STATEMENTS = [
    """CREATE TABLE Users (
        user_id STRING(128) NOT NULL,
        created_at TIMESTAMP NOT NULL
    ) PRIMARY KEY (user_id)""",
    """CREATE TABLE Sessions (
        session_id STRING(128) NOT NULL,
        user_id STRING(128) NOT NULL,
        started_at TIMESTAMP NOT NULL
    ) PRIMARY KEY (session_id)""",
    """CREATE TABLE Queries (
        query_id STRING(128) NOT NULL,
        session_id STRING(128) NOT NULL,
        text STRING(MAX),
        intent STRING(256),
        created_at TIMESTAMP NOT NULL
    ) PRIMARY KEY (query_id)""",
    """CREATE TABLE TaxEntities (
        entity_id STRING(128) NOT NULL,
        name STRING(256),
        currency STRING(16),
        jurisdiction STRING(64),
        location STRING(256)
    ) PRIMARY KEY (entity_id)""",
    """CREATE TABLE Jurisdictions (
        jurisdiction_id STRING(128) NOT NULL,
        name STRING(64)
    ) PRIMARY KEY (jurisdiction_id)""",
    """CREATE TABLE TaxForms (
        form_id STRING(128) NOT NULL,
        name STRING(128),
        jurisdiction STRING(64)
    ) PRIMARY KEY (form_id)""",
    """CREATE TABLE Concepts (
        concept_id STRING(128) NOT NULL,
        name STRING(128)
    ) PRIMARY KEY (concept_id)""",
    """CREATE TABLE Resolutions (
        resolution_id STRING(128) NOT NULL,
        query_id STRING(128) NOT NULL,
        status STRING(32),
        confidence FLOAT64,
        created_at TIMESTAMP NOT NULL
    ) PRIMARY KEY (resolution_id)""",
    """CREATE TABLE Ambiguities (
        ambiguity_id STRING(128) NOT NULL,
        query_id STRING(128) NOT NULL,
        topic STRING(256),
        reason STRING(MAX),
        created_at TIMESTAMP NOT NULL
    ) PRIMARY KEY (ambiguity_id)""",
    """CREATE TABLE Edges (
        edge_id STRING(128) NOT NULL,
        from_id STRING(128) NOT NULL,
        to_id STRING(128) NOT NULL,
        type STRING(64) NOT NULL,
        created_at TIMESTAMP NOT NULL
    ) PRIMARY KEY (edge_id)""",
]


GRAPH_DDL = """CREATE PROPERTY GRAPH tax_graph
NODE TABLES (
  Users KEY (user_id) LABEL User,
  Sessions KEY (session_id) LABEL Session,
  Queries KEY (query_id) LABEL Query,
  TaxEntities KEY (entity_id) LABEL TaxEntity,
  Jurisdictions KEY (jurisdiction_id) LABEL Jurisdiction,
  TaxForms KEY (form_id) LABEL TaxForm,
  Concepts KEY (concept_id) LABEL Concept,
  Resolutions KEY (resolution_id) LABEL Resolution,
  Ambiguities KEY (ambiguity_id) LABEL Ambiguity
)
EDGE TABLES (
  Edges KEY (edge_id)
  SOURCE KEY (from_id) REFERENCES Users (user_id)
  DESTINATION KEY (to_id) REFERENCES Sessions (session_id)
  LABEL HAS_SESSION,
  Edges KEY (edge_id)
  SOURCE KEY (from_id) REFERENCES Sessions (session_id)
  DESTINATION KEY (to_id) REFERENCES Queries (query_id)
  LABEL CONTAINS,
  Edges KEY (edge_id)
  SOURCE KEY (from_id) REFERENCES Queries (query_id)
  DESTINATION KEY (to_id) REFERENCES Concepts (concept_id)
  LABEL REFERENCES,
  Edges KEY (edge_id)
  SOURCE KEY (from_id) REFERENCES Queries (query_id)
  DESTINATION KEY (to_id) REFERENCES TaxEntities (entity_id)
  LABEL INVOLVES,
  Edges KEY (edge_id)
  SOURCE KEY (from_id) REFERENCES TaxEntities (entity_id)
  DESTINATION KEY (to_id) REFERENCES Jurisdictions (jurisdiction_id)
  LABEL GOVERNED_BY,
  Edges KEY (edge_id)
  SOURCE KEY (from_id) REFERENCES TaxEntities (entity_id)
  DESTINATION KEY (to_id) REFERENCES TaxForms (form_id)
  LABEL REPORTED_ON,
  Edges KEY (edge_id)
  SOURCE KEY (from_id) REFERENCES TaxForms (form_id)
  DESTINATION KEY (to_id) REFERENCES Jurisdictions (jurisdiction_id)
  LABEL LINKED_TO,
  Edges KEY (edge_id)
  SOURCE KEY (from_id) REFERENCES Users (user_id)
  DESTINATION KEY (to_id) REFERENCES TaxEntities (entity_id)
  LABEL OWNS,
  Edges KEY (edge_id)
  SOURCE KEY (from_id) REFERENCES Queries (query_id)
  DESTINATION KEY (to_id) REFERENCES Resolutions (resolution_id)
  LABEL RESOLVED_BY,
  Edges KEY (edge_id)
  SOURCE KEY (from_id) REFERENCES Resolutions (resolution_id)
  DESTINATION KEY (to_id) REFERENCES Concepts (concept_id)
  LABEL CITES
)"""


def _now_ts():
    # Use explicit UTC timestamp to avoid commit-timestamp column requirements.
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def ensure_schema(database) -> None:
    op = database.update_ddl(DDL_STATEMENTS)
    op.result(timeout=600)
    try:
        op = database.update_ddl([GRAPH_DDL])
        op.result(timeout=600)
    except Exception:
        # Graph DDL may already exist or not supported.
        pass


def upsert_basic_user_session(
    database, user_id: str, session_id: str
) -> None:
    now = _now_ts()
    with database.batch() as batch:
        batch.insert_or_update(
            table="Users",
            columns=("user_id", "created_at"),
            values=[(user_id, now)],
        )
        batch.insert_or_update(
            table="Sessions",
            columns=("session_id", "user_id", "started_at"),
            values=[(session_id, user_id, now)],
        )


def write_memory(
    database,
    user_id: str,
    session_id: str,
    query_text: str,
    intent: str,
    resolution_status: str,
    confidence: float,
    concepts: List[str],
    tax_entities: List[Dict[str, str]],
    jurisdictions: List[str],
    tax_forms: List[str],
    ambiguities: List[Dict[str, str]],
) -> None:
    now = _now_ts()
    query_id = _id("query")
    resolution_id = _id("resolution")

    with database.batch() as batch:
        batch.insert_or_update(
            table="Queries",
            columns=("query_id", "session_id", "text", "intent", "created_at"),
            values=[(query_id, session_id, query_text, intent, now)],
        )
        batch.insert_or_update(
            table="Resolutions",
            columns=("resolution_id", "query_id", "status", "confidence", "created_at"),
            values=[(resolution_id, query_id, resolution_status, confidence, now)],
        )

    edges = []
    edges.append(("HAS_SESSION", user_id, session_id))
    edges.append(("CONTAINS", session_id, query_id))
    edges.append(("RESOLVED_BY", query_id, resolution_id))

    # Jurisdictions
    jur_ids = []
    with database.batch() as batch:
        for name in jurisdictions:
            jid = _id("jur")
            jur_ids.append((name, jid))
            batch.insert_or_update(
                table="Jurisdictions",
                columns=("jurisdiction_id", "name"),
                values=[(jid, name)],
            )

    # Concepts
    concept_ids = []
    with database.batch() as batch:
        for name in concepts:
            cid = _id("concept")
            concept_ids.append((name, cid))
            batch.insert_or_update(
                table="Concepts",
                columns=("concept_id", "name"),
                values=[(cid, name)],
            )
            edges.append(("REFERENCES", query_id, cid))
            edges.append(("CITES", resolution_id, cid))

    # Tax forms
    form_ids = []
    with database.batch() as batch:
        for name in tax_forms:
            fid = _id("form")
            form_ids.append((name, fid))
            batch.insert_or_update(
                table="TaxForms",
                columns=("form_id", "name", "jurisdiction"),
                values=[(fid, name, "")],
            )

    # Tax entities
    entity_ids = []
    with database.batch() as batch:
        for ent in tax_entities:
            eid = _id("entity")
            entity_ids.append((ent, eid))
            batch.insert_or_update(
                table="TaxEntities",
                columns=("entity_id", "name", "currency", "jurisdiction", "location"),
                values=[
                    (
                        eid,
                        ent.get("name", ""),
                        ent.get("currency", ""),
                        ent.get("jurisdiction", ""),
                        ent.get("location", ""),
                    )
                ],
            )
            edges.append(("INVOLVES", query_id, eid))
            edges.append(("OWNS", user_id, eid))

    # Link entities to jurisdictions/forms
    for ent, eid in entity_ids:
        if ent.get("jurisdiction"):
            for name, jid in jur_ids:
                if name.lower() == ent.get("jurisdiction", "").lower():
                    edges.append(("GOVERNED_BY", eid, jid))
        if ent.get("form"):
            for name, fid in form_ids:
                if name.lower() == ent.get("form", "").lower():
                    edges.append(("REPORTED_ON", eid, fid))

    # Ambiguities
    with database.batch() as batch:
        for amb in ambiguities:
            aid = _id("amb")
            batch.insert_or_update(
                table="Ambiguities",
                columns=("ambiguity_id", "query_id", "topic", "reason", "created_at"),
                values=[(aid, query_id, amb.get("topic", ""), amb.get("reason", ""), now)],
            )

    # Write edges
    with database.batch() as batch:
        for typ, from_id, to_id in edges:
            batch.insert(
                table="Edges",
                columns=("edge_id", "from_id", "to_id", "type", "created_at"),
                values=[(_id("edge"), from_id, to_id, typ, now)],
            )


def fetch_memory_context(
    database,
    user_id: str,
    concepts: List[str],
    entities: List[str],
    limit: int = 3,
) -> Dict[str, Any]:
    # Simple SQL retrieval: latest resolutions matching concepts or entities.
    if not concepts and not entities:
        return {"prior_resolutions": [], "unresolved_queries": []}

    concept_clause = " OR ".join(["c.name=@c" for _ in concepts]) if concepts else ""
    entity_clause = " OR ".join(["e.name=@e" for _ in entities]) if entities else ""
    where = " OR ".join([c for c in [concept_clause, entity_clause] if c]) or "1=0"

    sql = f"""
    SELECT q.text AS query_text, r.status AS status, r.created_at AS created_at
    FROM Queries q
    JOIN Resolutions r ON q.query_id = r.query_id
    LEFT JOIN Edges ec ON ec.from_id = q.query_id AND ec.type = 'REFERENCES'
    LEFT JOIN Concepts c ON c.concept_id = ec.to_id
    LEFT JOIN Edges ee ON ee.from_id = q.query_id AND ee.type = 'INVOLVES'
    LEFT JOIN TaxEntities e ON e.entity_id = ee.to_id
    WHERE {where}
    ORDER BY r.created_at DESC
    LIMIT {limit}
    """

    params = {}
    param_types = {}
    if concepts:
        params["c"] = concepts[0]
        param_types["c"] = spanner.param_types.STRING
    if entities:
        params["e"] = entities[0]
        param_types["e"] = spanner.param_types.STRING

    prior = []
    with database.snapshot() as snapshot:
        res = snapshot.execute_sql(sql, params=params, param_types=param_types)
        for row in res:
            prior.append(
                {
                    "query": row[0],
                    "status": row[1],
                    "created_at": str(row[2]),
                }
            )
    unresolved = [p for p in prior if p["status"] != "answered"]
    return {"prior_resolutions": prior, "unresolved_queries": unresolved}
