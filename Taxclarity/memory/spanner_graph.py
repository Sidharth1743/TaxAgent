#!/usr/bin/env python3
"""Spanner graph storage for user tax memory."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Tuple

from config import SPANNER_DATABASE_ID, SPANNER_INSTANCE_ID, SPANNER_PROJECT_ID

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
    project_id = SPANNER_PROJECT_ID.strip()
    instance_id = SPANNER_INSTANCE_ID.strip()
    database_id = SPANNER_DATABASE_ID.strip()
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
    """CREATE TABLE ConversationTurns (
        turn_id STRING(128) NOT NULL,
        user_id STRING(128) NOT NULL,
        session_id STRING(128) NOT NULL,
        role STRING(32) NOT NULL,
        text STRING(MAX) NOT NULL,
        created_at TIMESTAMP NOT NULL
    ) PRIMARY KEY (turn_id)""",
    """CREATE TABLE ConversationSummaries (
        summary_id STRING(128) NOT NULL,
        user_id STRING(128) NOT NULL,
        session_id STRING(128) NOT NULL,
        summary STRING(MAX) NOT NULL,
        updated_at TIMESTAMP NOT NULL
    ) PRIMARY KEY (summary_id)""",
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


_LOW_QUALITY_ADVISOR_MARKERS = (
    "my next step",
    "i'm focusing",
    "i am focusing",
    "i'm currently focused",
    "i am currently focused",
    "i've noted",
    "i have noted",
    "i've acknowledged",
    "i have acknowledged",
    "i need to",
    "i'll ask",
    "i will ask",
    "clarifying tax inquiry",
    "clarifying the query",
    "clarifying the inquiry",
    "acknowledge and inquire",
    "determining tax implications",
    "addressing the form 16 inquiry",
)


def _normalize_memory_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _is_low_quality_advisor_text(text: str) -> bool:
    clean_text = _normalize_memory_text(text)
    if not clean_text:
        return True

    lowered = clean_text.lower()
    if any(marker in lowered for marker in _LOW_QUALITY_ADVISOR_MARKERS):
        return True

    if re.match(r"^advisor:\s*\*\*", lowered):
        return True

    return False


def _sanitize_turn(role: str, text: str) -> str:
    clean_text = _normalize_memory_text(text)
    if not clean_text:
        return ""
    if role == "agent" and _is_low_quality_advisor_text(clean_text):
        return ""
    return clean_text


_conversation_schema_ensured = False


def ensure_schema(database) -> None:
    op = database.update_ddl(DDL_STATEMENTS)
    op.result(timeout=600)
    try:
        op = database.update_ddl([GRAPH_DDL])
        op.result(timeout=600)
    except Exception:
        # Graph DDL may already exist or not supported.
        pass


def ensure_conversation_schema(database) -> None:
    global _conversation_schema_ensured
    if _conversation_schema_ensured:
        return

    try:
        op = database.update_ddl(
            [
                statement
                for statement in DDL_STATEMENTS
                if "ConversationTurns" in statement or "ConversationSummaries" in statement
            ]
        )
        op.result(timeout=600)
    except Exception:
        # Tables may already exist.
        pass

    _conversation_schema_ensured = True


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


def build_conversation_summary(turns: List[Dict[str, str]], max_items: int = 4) -> str:
    """Create a compact, deterministic summary from recent turns."""
    if not turns:
        return ""

    user_topics: List[str] = []
    agent_actions: List[str] = []

    for turn in turns[-12:]:
        text = _sanitize_turn(turn.get("role", ""), turn.get("text", ""))
        if not text:
            continue
        clipped = text[:180].rstrip()
        if turn.get("role") == "user":
            if clipped not in user_topics:
                user_topics.append(clipped)
        else:
            if clipped not in agent_actions:
                agent_actions.append(clipped)

    parts: List[str] = []
    if user_topics:
        topics = "; ".join(user_topics[-max_items:])
        parts.append(f"Recent user questions: {topics}")
    if agent_actions:
        actions = "; ".join(agent_actions[-max_items:])
        parts.append(f"Recent advisor guidance: {actions}")

    return " | ".join(parts)[:1200]


def append_conversation_turn(
    database,
    user_id: str,
    session_id: str,
    role: str,
    text: str,
) -> Optional[str]:
    clean_text = _sanitize_turn(role, text)
    if not clean_text:
        return None

    ensure_conversation_schema(database)
    upsert_basic_user_session(database, user_id, session_id)

    now = _now_ts()
    turn_id = _id("turn")
    with database.batch() as batch:
        batch.insert_or_update(
            table="ConversationTurns",
            columns=("turn_id", "user_id", "session_id", "role", "text", "created_at"),
            values=[(turn_id, user_id, session_id, role, clean_text, now)],
        )
        batch.insert_or_update(
            table="Edges",
            columns=("edge_id", "from_id", "to_id", "type", "created_at"),
            values=[(_id("edge"), session_id, turn_id, "HAS_TURN", now)],
        )

    return turn_id


def fetch_recent_conversation_turns(
    database,
    user_id: str,
    limit: int = 8,
) -> List[Dict[str, str]]:
    ensure_conversation_schema(database)

    sql = """
    SELECT role, text, created_at
    FROM ConversationTurns
    WHERE user_id = @user_id
    ORDER BY created_at DESC
    LIMIT @limit
    """
    params = {"user_id": user_id, "limit": limit}
    param_types = {}
    if spanner:
        param_types["user_id"] = spanner.param_types.STRING
        param_types["limit"] = spanner.param_types.INT64

    turns: List[Dict[str, str]] = []
    with database.snapshot() as snapshot:
        rows = snapshot.execute_sql(sql, params=params, param_types=param_types)
        for row in rows:
            role = str(row[0])
            text = _sanitize_turn(role, str(row[1]))
            if not text:
                continue
            turns.append(
                {
                    "role": role,
                    "text": text,
                    "created_at": str(row[2]),
                }
            )
    turns.reverse()
    return turns


def upsert_conversation_summary(
    database,
    user_id: str,
    session_id: str,
    summary: str,
) -> Optional[str]:
    clean_summary = _normalize_memory_text(summary)
    if not clean_summary:
        return None

    ensure_conversation_schema(database)
    upsert_basic_user_session(database, user_id, session_id)

    now = _now_ts()
    summary_id = f"summary_{session_id}"
    with database.batch() as batch:
        batch.insert_or_update(
            table="ConversationSummaries",
            columns=("summary_id", "user_id", "session_id", "summary", "updated_at"),
            values=[(summary_id, user_id, session_id, clean_summary, now)],
        )
        batch.insert_or_update(
            table="Edges",
            columns=("edge_id", "from_id", "to_id", "type", "created_at"),
            values=[(_id("edge"), user_id, summary_id, "HAS_MEMORY", now)],
        )

    return summary_id


def refresh_conversation_summary(
    database,
    user_id: str,
    session_id: str,
    window: int = 10,
) -> str:
    recent_turns = fetch_recent_conversation_turns(database, user_id=user_id, limit=window)
    summary = build_conversation_summary(recent_turns)
    upsert_conversation_summary(database, user_id=user_id, session_id=session_id, summary=summary)
    return summary


def fetch_recent_conversation_context(
    database,
    user_id: str,
    turn_limit: int = 8,
    summary_limit: int = 2,
) -> Dict[str, Any]:
    ensure_conversation_schema(database)

    turns = fetch_recent_conversation_turns(database, user_id=user_id, limit=turn_limit)

    summary_sql = """
    SELECT summary, updated_at
    FROM ConversationSummaries
    WHERE user_id = @user_id
    ORDER BY updated_at DESC
    LIMIT @limit
    """
    params = {"user_id": user_id, "limit": summary_limit}
    param_types = {}
    if spanner:
        param_types["user_id"] = spanner.param_types.STRING
        param_types["limit"] = spanner.param_types.INT64

    summaries: List[Tuple[str, str]] = []
    with database.snapshot() as snapshot:
        rows = snapshot.execute_sql(summary_sql, params=params, param_types=param_types)
        for row in rows:
            summaries.append((str(row[0]), str(row[1])))

    latest_summary = ""
    for summary, _updated_at in summaries:
        candidate = _normalize_memory_text(summary)
        if candidate and not _is_low_quality_advisor_text(candidate):
            latest_summary = candidate
            break
    if not latest_summary:
        latest_summary = build_conversation_summary(turns)
    prior_topics: List[str] = []
    for turn in turns:
        if turn["role"] != "user":
            continue
        snippet = turn["text"][:90].strip()
        if snippet and snippet not in prior_topics:
            prior_topics.append(snippet)

    return {
        "summary": latest_summary,
        "recent_turns": turns,
        "prior_topics": prior_topics[:5],
        "loaded": bool(latest_summary or turns),
    }


def format_conversation_context_prompt(context: Dict[str, Any]) -> str:
    if not context.get("loaded"):
        return ""

    parts: List[str] = []
    summary = _normalize_memory_text(context.get("summary") or "")
    if summary:
        parts.append(f"Conversation summary: {summary}")

    prior_topics = context.get("prior_topics") or []
    if prior_topics:
        parts.append(f"Prior topics: {', '.join(prior_topics[:5])}")

    recent_turns = context.get("recent_turns") or []
    if recent_turns:
        serialized_turns = []
        for turn in recent_turns[-8:]:
            role = "User" if turn.get("role") == "user" else "Advisor"
            text = _sanitize_turn(turn.get("role", ""), turn.get("text") or "")
            if text:
                serialized_turns.append(f"{role}: {text[:220]}")
        if serialized_turns:
            parts.append("Recent turns:\n" + "\n".join(serialized_turns))

    return "\n\n".join(parts).strip()


# ---------------------------------------------------------------------------
# Graph visualization and insights
# ---------------------------------------------------------------------------

_NODE_COLOR_MAP = {
    "User": "#8b5cf6",
    "Session": "#3b82f6",
    "ConversationTurn": "#38bdf8",
    "ConversationSummary": "#a78bfa",
    "Concept": "#22c55e",
    "TaxEntity": "#f97316",
    "Jurisdiction": "#ef4444",
    "TaxForm": "#14b8a6",
    "Resolution": "#eab308",
    "Ambiguity": "#6b7280",
}

# Map edge types to (source_table_type, target_table_type)
_EDGE_TYPE_MAP = {
    "HAS_SESSION": ("User", "Session"),
    "HAS_TURN": ("Session", "ConversationTurn"),
    "HAS_MEMORY": ("User", "ConversationSummary"),
    "CONTAINS": ("Session", "Query"),
    "REFERENCES": ("Query", "Concept"),
    "INVOLVES": ("Query", "TaxEntity"),
    "GOVERNED_BY": ("TaxEntity", "Jurisdiction"),
    "REPORTED_ON": ("TaxEntity", "TaxForm"),
    "LINKED_TO": ("TaxForm", "Jurisdiction"),
    "OWNS": ("User", "TaxEntity"),
    "RESOLVED_BY": ("Query", "Resolution"),
    "CITES": ("Resolution", "Concept"),
}

# Map node type to (table_name, id_column, label_column)
_TABLE_INFO = {
    "User": ("Users", "user_id", "user_id"),
    "Session": ("Sessions", "session_id", "session_id"),
    "ConversationTurn": ("ConversationTurns", "turn_id", "text"),
    "ConversationSummary": ("ConversationSummaries", "summary_id", "summary"),
    "Query": ("Queries", "query_id", "text"),
    "Concept": ("Concepts", "concept_id", "name"),
    "TaxEntity": ("TaxEntities", "entity_id", "name"),
    "Jurisdiction": ("Jurisdictions", "jurisdiction_id", "name"),
    "TaxForm": ("TaxForms", "form_id", "name"),
    "Resolution": ("Resolutions", "resolution_id", "status"),
    "Ambiguity": ("Ambiguities", "ambiguity_id", "topic"),
}


def fetch_user_graph(database, user_id: str) -> Dict[str, Any]:
    """Fetch the full knowledge graph for a user as D3-compatible JSON.

    Returns ``{"nodes": [...], "links": [...]}`` where each node has
    ``id``, ``label``, ``type``, ``color`` and each link has ``source``,
    ``target``, ``type``.
    """
    try:
        # Step 1: Get all edges reachable from this user via BFS
        sql = """
        SELECT edge_id, from_id, to_id, type
        FROM Edges
        WHERE from_id = @user_id OR to_id = @user_id
        """
        params = {"user_id": user_id}
        param_types = {}
        if spanner:
            param_types["user_id"] = spanner.param_types.STRING

        all_edges: List[tuple] = []
        visited_ids: set = {user_id}
        frontier: set = {user_id}

        with database.snapshot() as snapshot:
            # BFS: expand frontier by querying edges involving frontier nodes
            for _ in range(6):  # max depth
                if not frontier:
                    break
                frontier_list = list(frontier)
                edge_sql = """
                SELECT edge_id, from_id, to_id, type
                FROM Edges
                WHERE from_id IN UNNEST(@node_ids) OR to_id IN UNNEST(@node_ids)
                """
                edge_params = {"node_ids": frontier_list}
                edge_param_types = {}
                if spanner:
                    edge_param_types["node_ids"] = spanner.param_types.Array(
                        spanner.param_types.STRING
                    )
                rows = list(
                    snapshot.execute_sql(
                        edge_sql, params=edge_params, param_types=edge_param_types
                    )
                )
                new_frontier: set = set()
                for row in rows:
                    edge_tuple = (row[0], row[1], row[2], row[3])
                    if edge_tuple not in all_edges:
                        all_edges.append(edge_tuple)
                    for nid in (row[1], row[2]):
                        if nid not in visited_ids:
                            visited_ids.add(nid)
                            new_frontier.add(nid)
                frontier = new_frontier

        if not all_edges:
            return {"nodes": [], "links": []}

        # Step 2: Determine node types from edge types
        node_type_map: Dict[str, str] = {}
        node_type_map[user_id] = "User"
        for _, from_id, to_id, edge_type in all_edges:
            mapping = _EDGE_TYPE_MAP.get(edge_type)
            if mapping:
                src_type, tgt_type = mapping
                if from_id not in node_type_map:
                    node_type_map[from_id] = src_type
                if to_id not in node_type_map:
                    node_type_map[to_id] = tgt_type

        # Step 3: Fetch labels for each node type
        node_labels: Dict[str, str] = {}
        nodes_by_type: Dict[str, List[str]] = {}
        for nid, ntype in node_type_map.items():
            nodes_by_type.setdefault(ntype, []).append(nid)

        with database.snapshot() as snapshot:
            for ntype, nids in nodes_by_type.items():
                info = _TABLE_INFO.get(ntype)
                if not info:
                    for nid in nids:
                        node_labels[nid] = nid
                    continue
                table_name, id_col, label_col = info
                label_sql = f"SELECT {id_col}, {label_col} FROM {table_name} WHERE {id_col} IN UNNEST(@node_ids)"
                label_params = {"node_ids": nids}
                label_param_types = {}
                if spanner:
                    label_param_types["node_ids"] = spanner.param_types.Array(
                        spanner.param_types.STRING
                    )
                rows = list(
                    snapshot.execute_sql(
                        label_sql, params=label_params, param_types=label_param_types
                    )
                )
                for row in rows:
                    label = str(row[1]) if row[1] else row[0]
                    if ntype in {"ConversationTurn", "ConversationSummary"} and len(label) > 96:
                        label = f"{label[:93].rstrip()}..."
                    node_labels[row[0]] = label
                # Fill any missing
                for nid in nids:
                    if nid not in node_labels:
                        node_labels[nid] = nid

        # Step 4: Build D3 output
        # Query type has no color in map, treat as Session color
        nodes = []
        for nid, ntype in node_type_map.items():
            display_type = ntype
            color = _NODE_COLOR_MAP.get(ntype, "#9ca3af")
            nodes.append({
                "id": nid,
                "label": node_labels.get(nid, nid),
                "type": display_type,
                "color": color,
            })

        links = []
        node_id_set = set(node_type_map.keys())
        for _, from_id, to_id, edge_type in all_edges:
            if from_id in node_id_set and to_id in node_id_set:
                links.append({
                    "source": from_id,
                    "target": to_id,
                    "type": edge_type,
                })

        return {"nodes": nodes, "links": links}

    except Exception:
        return {"nodes": [], "links": []}


def analyze_insights(database, user_id: str) -> List[Dict[str, Any]]:
    """Analyze user's knowledge graph and suggest unclaimed deductions.

    Returns a list of dicts with ``type``, ``message``, ``section``,
    ``potential_savings`` keys.
    """
    try:
        # Fetch user's jurisdictions, concepts, and resolutions
        jurisdictions: List[str] = []
        concepts: List[str] = []
        resolution_statuses: List[str] = []

        with database.snapshot() as snapshot:
            # Get jurisdictions via: user->OWNS->entity->GOVERNED_BY->jurisdiction
            jur_sql = """
            SELECT DISTINCT j.name
            FROM Edges e1
            JOIN Edges e2 ON e2.from_id = e1.to_id AND e2.type = 'GOVERNED_BY'
            JOIN Jurisdictions j ON j.jurisdiction_id = e2.to_id
            WHERE e1.from_id = @user_id AND e1.type = 'OWNS'
            """
            jur_params = {"user_id": user_id}
            jur_param_types = {}
            if spanner:
                jur_param_types["user_id"] = spanner.param_types.STRING
            for row in snapshot.execute_sql(jur_sql, params=jur_params, param_types=jur_param_types):
                jurisdictions.append(str(row[0]).lower())

            # Get concepts via: user->HAS_SESSION->session->CONTAINS->query->REFERENCES->concept
            concept_sql = """
            SELECT DISTINCT c.name
            FROM Edges e1
            JOIN Edges e2 ON e2.from_id = e1.to_id AND e2.type = 'CONTAINS'
            JOIN Edges e3 ON e3.from_id = e2.to_id AND e3.type = 'REFERENCES'
            JOIN Concepts c ON c.concept_id = e3.to_id
            WHERE e1.from_id = @user_id AND e1.type = 'HAS_SESSION'
            """
            for row in snapshot.execute_sql(concept_sql, params=jur_params, param_types=jur_param_types):
                concepts.append(str(row[0]).lower())

            # Get resolution statuses
            res_sql = """
            SELECT r.status
            FROM Edges e1
            JOIN Edges e2 ON e2.from_id = e1.to_id AND e2.type = 'CONTAINS'
            JOIN Edges e3 ON e3.from_id = e2.to_id AND e3.type = 'RESOLVED_BY'
            JOIN Resolutions r ON r.resolution_id = e3.to_id
            WHERE e1.from_id = @user_id AND e1.type = 'HAS_SESSION'
            """
            for row in snapshot.execute_sql(res_sql, params=jur_params, param_types=jur_param_types):
                resolution_statuses.append(str(row[0]))

        if not jurisdictions and not concepts and not resolution_statuses:
            return []

        insights: List[Dict[str, Any]] = []
        concept_text = " ".join(concepts)

        # India deduction gaps
        if "india" in jurisdictions:
            if "80d" not in concept_text and "health insurance" not in concept_text:
                insights.append({
                    "type": "deduction_gap",
                    "message": "You haven't claimed Section 80D -- potential savings of Rs 25,000",
                    "section": "80D",
                    "potential_savings": "Rs 25,000",
                })
            if "80c" not in concept_text:
                insights.append({
                    "type": "deduction_gap",
                    "message": "You haven't claimed Section 80C -- potential savings of Rs 1,50,000",
                    "section": "80C",
                    "potential_savings": "Rs 1,50,000",
                })
            if "hra" not in concept_text:
                insights.append({
                    "type": "deduction_gap",
                    "message": "You haven't claimed HRA exemption -- potential savings depend on rent paid",
                    "section": "HRA",
                    "potential_savings": None,
                })

        # USA deduction gaps
        if "usa" in jurisdictions:
            if "hsa" not in concept_text and "health savings" not in concept_text:
                insights.append({
                    "type": "deduction_gap",
                    "message": "You haven't explored HSA contributions -- potential savings of $3,850",
                    "section": "HSA",
                    "potential_savings": "$3,850",
                })
            if "ira" not in concept_text and "retirement" not in concept_text:
                insights.append({
                    "type": "deduction_gap",
                    "message": "You haven't explored IRA deductions -- potential savings of $6,500",
                    "section": "IRA",
                    "potential_savings": "$6,500",
                })

        # Unresolved queries
        for status in resolution_statuses:
            if status != "answered":
                insights.append({
                    "type": "unresolved",
                    "message": "You have unresolved tax queries -- consider revisiting them",
                    "section": None,
                    "potential_savings": None,
                })
                break  # Only one suggestion for unresolved

        return insights

    except Exception:
        return []


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

    concept_clause = "c.name IN UNNEST(@concepts)" if concepts else ""
    entity_clause = "e.name IN UNNEST(@entities)" if entities else ""
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
        params["concepts"] = concepts
        param_types["concepts"] = spanner.param_types.Array(spanner.param_types.STRING)
    if entities:
        params["entities"] = entities
        param_types["entities"] = spanner.param_types.Array(spanner.param_types.STRING)

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


# ---------------------------------------------------------------------------
# Document data storage (for confirmed form uploads)
# ---------------------------------------------------------------------------

_MONETARY_KEYWORDS = {"wages", "income", "tax", "salary", "deduction", "tds", "medicare"}


def _is_monetary_field(field_name: str) -> bool:
    """Check if a field name refers to a monetary value."""
    name_lower = field_name.lower()
    return any(kw in name_lower for kw in _MONETARY_KEYWORDS)


def store_document_data(
    database,
    user_id: str,
    doc_id: str,
    form_type: str,
    jurisdiction: str,
    fields: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Store confirmed document data as TaxForm + TaxEntity nodes with edges.

    Creates a TaxForm node for the document, TaxEntity nodes for monetary
    fields, and OWNS/REPORTED_ON/LINKED_TO edges connecting them.

    Returns dict with form_id, entity_ids, and jurisdiction_id.
    """
    now = _now_ts()

    # Friendly form name
    form_names = {"w2": "W-2", "1099": "1099", "form16": "Form 16"}
    form_display = form_names.get(form_type, form_type)

    # Upsert jurisdiction node
    jur_id = _id("jur")
    with database.batch() as batch:
        batch.insert_or_update(
            table="Jurisdictions",
            columns=("jurisdiction_id", "name"),
            values=[(jur_id, jurisdiction)],
        )

    # Create TaxForm node
    form_id = doc_id
    with database.batch() as batch:
        batch.insert_or_update(
            table="TaxForms",
            columns=("form_id", "name", "jurisdiction"),
            values=[(form_id, form_display, jurisdiction)],
        )

    # Ensure user exists
    with database.batch() as batch:
        batch.insert_or_update(
            table="Users",
            columns=("user_id", "created_at"),
            values=[(user_id, now)],
        )

    # Create TaxEntity nodes for monetary fields
    entity_ids: List[str] = []
    currency = "USD" if jurisdiction == "usa" else "INR"
    edges = []

    for field in fields:
        field_name = field.get("name", "")
        if not _is_monetary_field(field_name):
            continue

        eid = _id("entity")
        entity_ids.append(eid)

        with database.batch() as batch:
            batch.insert_or_update(
                table="TaxEntities",
                columns=("entity_id", "name", "currency", "jurisdiction", "location"),
                values=[(eid, field_name, currency, jurisdiction, "")],
            )

        edges.append(("OWNS", user_id, eid))
        edges.append(("REPORTED_ON", eid, form_id))

    # Form -> Jurisdiction edge
    edges.append(("LINKED_TO", form_id, jur_id))

    # Write all edges
    with database.batch() as batch:
        for typ, from_id, to_id in edges:
            batch.insert_or_update(
                table="Edges",
                columns=("edge_id", "from_id", "to_id", "type", "created_at"),
                values=[(_id("edge"), from_id, to_id, typ, now)],
            )

    return {
        "form_id": form_id,
        "entity_ids": entity_ids,
        "jurisdiction_id": jur_id,
    }
