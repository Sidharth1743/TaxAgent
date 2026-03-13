from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    desc,
    insert,
    select,
)
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from config import CLOUD_SQL_DATABASE_URL, MEMORY_TOPIC_LIMIT
from memory.spanner_graph import (
    _normalize_memory_text,
    _sanitize_turn,
    build_conversation_summary,
    format_conversation_context_prompt,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("user_id", String(128), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

sessions = Table(
    "sessions",
    metadata,
    Column("session_id", String(128), primary_key=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

conversation_turns = Table(
    "conversation_turns",
    metadata,
    Column("turn_id", String(128), primary_key=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("session_id", String(128), nullable=False, index=True),
    Column("role", String(32), nullable=False),
    Column("text", Text, nullable=False),
    Column("importance_score", Float, nullable=False, default=1.0),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

conversation_summaries = Table(
    "conversation_summaries",
    metadata,
    Column("summary_id", String(128), primary_key=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("session_id", String(128), nullable=False, index=True),
    Column("summary", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

conversation_topics = Table(
    "conversation_topics",
    metadata,
    Column("topic_id", String(128), primary_key=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("topic", String(512), nullable=False),
    Column("importance_score", Float, nullable=False, default=0.0),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("source_session_id", String(128)),
    Column("source_turn_id", String(128)),
)

document_uploads = Table(
    "document_uploads",
    metadata,
    Column("doc_id", String(128), primary_key=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("form_type", String(64), nullable=False),
    Column("jurisdiction", String(64), nullable=False),
    Column("filename", String(512)),
    Column("confirmed", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

document_extraction_raw = Table(
    "document_extraction_raw",
    metadata,
    Column("doc_id", String(128), primary_key=True),
    Column("raw_payload", JSON, nullable=False),
    Column("raw_text", Text, nullable=False, default=""),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

document_fields_normalized = Table(
    "document_fields_normalized",
    metadata,
    Column("field_id", String(128), primary_key=True),
    Column("doc_id", String(128), nullable=False, index=True),
    Column("field_name", String(128), nullable=False),
    Column("field_value", Text, nullable=False),
    Column("confidence", Float, nullable=False, default=0.0),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

document_table_rows = Table(
    "document_table_rows",
    metadata,
    Column("row_id", String(128), primary_key=True),
    Column("doc_id", String(128), nullable=False, index=True),
    Column("table_index", Integer, nullable=False),
    Column("row_index", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

document_table_cells = Table(
    "document_table_cells",
    metadata,
    Column("cell_id", String(128), primary_key=True),
    Column("row_id", String(128), nullable=False, index=True),
    Column("column_index", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("confidence", Float, nullable=False, default=0.0),
)

memory_job_dlq = Table(
    "memory_job_dlq",
    metadata,
    Column("job_id", String(128), primary_key=True),
    Column("job_type", String(128), nullable=False),
    Column("user_id", String(128), index=True),
    Column("session_id", String(128), index=True),
    Column("doc_id", String(128), index=True),
    Column("payload", JSON, nullable=False),
    Column("retry_count", Integer, nullable=False, default=0),
    Column("error", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def _topic_id(user_id: str, topic: str) -> str:
    return f"{user_id}:{topic[:180]}".strip()


def _summary_id(session_id: str) -> str:
    return f"summary:{session_id}"


def _field_id(doc_id: str, field_name: str) -> str:
    return f"{doc_id}:{field_name}"


class CloudSqlMemoryStore:
    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or CLOUD_SQL_DATABASE_URL
        connect_args = {"check_same_thread": False} if self.database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(
            self.database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        metadata.create_all(self.engine)

    def _upsert_insert(self, table: Table):
        dialect = self.engine.dialect.name
        if dialect == "sqlite":
            return sqlite_insert(table)
        if dialect == "postgresql":
            return postgresql_insert(table)
        raise ValueError(f"Unsupported SQL dialect for upsert operations: {dialect}")

    def upsert_user_session(self, user_id: str, session_id: str) -> None:
        now = _utcnow()
        with self.engine.begin() as conn:
            conn.execute(
                self._upsert_insert(users).values(user_id=user_id, created_at=now).on_conflict_do_nothing(index_elements=["user_id"])
            )
            conn.execute(
                self._upsert_insert(sessions)
                .values(session_id=session_id, user_id=user_id, started_at=now, updated_at=now)
                .on_conflict_do_update(
                    index_elements=["session_id"],
                    set_={"user_id": user_id, "updated_at": now},
                )
            )

    def append_turn(self, user_id: str, session_id: str, role: str, text: str, importance_score: float = 1.0) -> str | None:
        clean_text = _sanitize_turn(role, text)
        if not clean_text:
            return None
        self.upsert_user_session(user_id, session_id)
        turn_id = f"turn:{uuid.uuid4().hex}"
        with self.engine.begin() as conn:
            conn.execute(
                insert(conversation_turns).values(
                    turn_id=turn_id,
                    user_id=user_id,
                    session_id=session_id,
                    role=role,
                    text=clean_text,
                    importance_score=importance_score,
                    created_at=_utcnow(),
                )
            )
        return turn_id

    def fetch_recent_turns(self, user_id: str, limit: int = 8) -> list[dict[str, str]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                select(
                    conversation_turns.c.role,
                    conversation_turns.c.text,
                    conversation_turns.c.created_at,
                )
                .where(conversation_turns.c.user_id == user_id)
                .order_by(desc(conversation_turns.c.created_at))
                .limit(limit)
            ).fetchall()
        turns = [
            {
                "role": row.role,
                "text": row.text,
                "created_at": row.created_at.isoformat() if hasattr(row.created_at, "isoformat") else str(row.created_at),
            }
            for row in rows
            if _sanitize_turn(row.role, row.text)
        ]
        turns.reverse()
        return turns

    def upsert_summary(self, user_id: str, session_id: str, summary: str) -> None:
        clean_summary = _normalize_memory_text(summary)
        if not clean_summary:
            return
        self.upsert_user_session(user_id, session_id)
        with self.engine.begin() as conn:
            conn.execute(
                self._upsert_insert(conversation_summaries)
                .values(
                    summary_id=_summary_id(session_id),
                    user_id=user_id,
                    session_id=session_id,
                    summary=clean_summary,
                    updated_at=_utcnow(),
                )
                .on_conflict_do_update(
                    index_elements=["summary_id"],
                    set_={
                        "summary": clean_summary,
                        "updated_at": _utcnow(),
                    },
                )
            )

    def refresh_summary(self, user_id: str, session_id: str, window: int = 10) -> str:
        turns = self.fetch_recent_turns(user_id, limit=window)
        summary = build_conversation_summary(turns)
        self.upsert_summary(user_id, session_id, summary)
        return summary

    def upsert_topics(
        self,
        user_id: str,
        session_id: str,
        topics: Iterable[str],
        source_turn_id: str | None = None,
        increment: float = 1.0,
    ) -> None:
        now = _utcnow()
        with self.engine.begin() as conn:
            for topic in topics:
                clean_topic = _normalize_memory_text(topic)[:512]
                if not clean_topic:
                    continue
                topic_id = _topic_id(user_id, clean_topic)
                existing = conn.execute(
                    select(conversation_topics.c.importance_score).where(conversation_topics.c.topic_id == topic_id)
                ).first()
                new_score = float((existing.importance_score if existing else 0.0) + increment)
                conn.execute(
                    self._upsert_insert(conversation_topics)
                    .values(
                        topic_id=topic_id,
                        user_id=user_id,
                        topic=clean_topic,
                        importance_score=new_score,
                        last_seen_at=now,
                        source_session_id=session_id,
                        source_turn_id=source_turn_id,
                    )
                    .on_conflict_do_update(
                        index_elements=["topic_id"],
                        set_={
                            "importance_score": new_score,
                            "last_seen_at": now,
                            "source_session_id": session_id,
                            "source_turn_id": source_turn_id,
                        },
                    )
                )

    def fetch_context(self, user_id: str, topic_limit: int = MEMORY_TOPIC_LIMIT, turn_limit: int = 8) -> dict[str, Any]:
        turns = self.fetch_recent_turns(user_id, limit=turn_limit)
        with self.engine.begin() as conn:
            summary_row = conn.execute(
                select(conversation_summaries.c.summary)
                .where(conversation_summaries.c.user_id == user_id)
                .order_by(desc(conversation_summaries.c.updated_at))
                .limit(1)
            ).first()
            topic_rows = conn.execute(
                select(conversation_topics.c.topic, conversation_topics.c.importance_score, conversation_topics.c.last_seen_at)
                .where(conversation_topics.c.user_id == user_id)
                .order_by(desc(conversation_topics.c.importance_score), desc(conversation_topics.c.last_seen_at))
                .limit(topic_limit)
            ).fetchall()

        prior_topics = [row.topic for row in topic_rows if row.topic]
        summary = _normalize_memory_text(summary_row.summary) if summary_row else ""
        if not summary:
            summary = build_conversation_summary(turns)

        context = {
            "summary": summary,
            "recent_turns": turns,
            "prior_topics": prior_topics,
            "loaded": bool(summary or turns or prior_topics),
            "top_topics": [
                {"topic": row.topic, "importance_score": float(row.importance_score or 0.0)}
                for row in topic_rows
            ],
        }
        context["prompt"] = format_conversation_context_prompt(context)
        return context

    def store_document(
        self,
        *,
        user_id: str,
        doc_id: str,
        filename: str,
        form_type: str,
        jurisdiction: str,
        raw_payload: dict[str, Any],
        raw_text: str,
        fields: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        confirmed: bool,
    ) -> dict[str, Any]:
        now = _utcnow()
        with self.engine.begin() as conn:
            conn.execute(
                self._upsert_insert(document_uploads)
                .values(
                    doc_id=doc_id,
                    user_id=user_id,
                    form_type=form_type,
                    jurisdiction=jurisdiction,
                    filename=filename,
                    confirmed=1 if confirmed else 0,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["doc_id"],
                    set_={
                        "user_id": user_id,
                        "form_type": form_type,
                        "jurisdiction": jurisdiction,
                        "filename": filename,
                        "confirmed": 1 if confirmed else 0,
                        "updated_at": now,
                    },
                )
            )
            conn.execute(
                self._upsert_insert(document_extraction_raw)
                .values(doc_id=doc_id, raw_payload=raw_payload, raw_text=raw_text, updated_at=now)
                .on_conflict_do_update(
                    index_elements=["doc_id"],
                    set_={"raw_payload": raw_payload, "raw_text": raw_text, "updated_at": now},
                )
            )
            conn.execute(delete(document_fields_normalized).where(document_fields_normalized.c.doc_id == doc_id))
            for field in fields:
                conn.execute(
                    insert(document_fields_normalized).values(
                        field_id=_field_id(doc_id, field.get("name", "")),
                        doc_id=doc_id,
                        field_name=field.get("name", ""),
                        field_value=str(field.get("value", "")),
                        confidence=float(field.get("confidence", 0.0)),
                        updated_at=now,
                    )
                )

            existing_rows = conn.execute(
                select(document_table_rows.c.row_id).where(document_table_rows.c.doc_id == doc_id)
            ).fetchall()
            if existing_rows:
                row_ids = [row.row_id for row in existing_rows]
                conn.execute(delete(document_table_cells).where(document_table_cells.c.row_id.in_(row_ids)))
                conn.execute(delete(document_table_rows).where(document_table_rows.c.doc_id == doc_id))

            for table in tables:
                table_index = int(table.get("table_index", 0))
                for row in table.get("rows", []):
                    row_id = f"row:{uuid.uuid4().hex}"
                    conn.execute(
                        insert(document_table_rows).values(
                            row_id=row_id,
                            doc_id=doc_id,
                            table_index=table_index,
                            row_index=int(row.get("row_index", 0)),
                            updated_at=now,
                        )
                    )
                    for cell in row.get("cells", []):
                        conn.execute(
                            insert(document_table_cells).values(
                                cell_id=f"cell:{uuid.uuid4().hex}",
                                row_id=row_id,
                                column_index=int(cell.get("column_index", 0)),
                                text=str(cell.get("text", "")),
                                confidence=float(cell.get("confidence", 0.0)),
                            )
                        )
        return {
            "form_id": doc_id,
            "entity_ids": [field.get("name", "") for field in fields if field.get("name")],
            "jurisdiction_id": f"jurisdiction:{jurisdiction}",
            "stored": True,
        }

    def fetch_document_fields(self, doc_id: str) -> dict[str, str]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                select(document_fields_normalized.c.field_name, document_fields_normalized.c.field_value)
                .where(document_fields_normalized.c.doc_id == doc_id)
            ).fetchall()
        return {row.field_name: row.field_value for row in rows}

    def fetch_graph(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        nodes: list[dict[str, Any]] = [{"id": f"user:{user_id}", "label": user_id, "type": "User", "color": "#8b5cf6"}]
        links: list[dict[str, Any]] = []
        with self.engine.begin() as conn:
            session_rows = conn.execute(
                select(sessions.c.session_id, sessions.c.started_at)
                .where(sessions.c.user_id == user_id)
                .order_by(desc(sessions.c.started_at))
                .limit(8)
            ).fetchall()
            topic_rows = conn.execute(
                select(conversation_topics.c.topic, conversation_topics.c.importance_score)
                .where(conversation_topics.c.user_id == user_id)
                .order_by(desc(conversation_topics.c.importance_score), desc(conversation_topics.c.last_seen_at))
                .limit(MEMORY_TOPIC_LIMIT)
            ).fetchall()
            doc_rows = conn.execute(
                select(document_uploads.c.doc_id, document_uploads.c.form_type)
                .where(document_uploads.c.user_id == user_id)
                .order_by(desc(document_uploads.c.updated_at))
                .limit(6)
            ).fetchall()

        for row in session_rows:
            session_id = f"session:{row.session_id}"
            nodes.append({"id": session_id, "label": row.session_id, "type": "Session", "color": "#3b82f6"})
            links.append({"source": f"user:{user_id}", "target": session_id, "type": "HAS_SESSION"})

        for idx, row in enumerate(topic_rows):
            topic_id = f"topic:{idx}"
            nodes.append({"id": topic_id, "label": row.topic, "type": "Concept", "color": "#22c55e"})
            links.append({"source": f"user:{user_id}", "target": topic_id, "type": "REMEMBERS"})

        for row in doc_rows:
            form_id = f"form:{row.doc_id}"
            nodes.append({"id": form_id, "label": row.form_type.upper(), "type": "TaxForm", "color": "#14b8a6"})
            links.append({"source": f"user:{user_id}", "target": form_id, "type": "UPLOADED"})

        return {"nodes": nodes, "links": links}

    def fetch_insights(self, user_id: str) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                select(conversation_topics.c.topic)
                .where(conversation_topics.c.user_id == user_id)
                .order_by(desc(conversation_topics.c.importance_score), desc(conversation_topics.c.last_seen_at))
                .limit(MEMORY_TOPIC_LIMIT)
            ).fetchall()
        topics = [row.topic.lower() for row in rows]
        insights: list[dict[str, Any]] = []
        if not any("80c" in topic for topic in topics):
            insights.append(
                {
                    "type": "deduction_gap",
                    "message": "Section 80C has not appeared in recent memory; you may still have deduction room.",
                    "section": "80C",
                    "potential_savings": "Up to regime-dependent savings",
                }
            )
        return insights

    def write_dlq(
        self,
        *,
        job_type: str,
        payload: dict[str, Any],
        error: str,
        retry_count: int,
        user_id: str | None = None,
        session_id: str | None = None,
        doc_id: str | None = None,
    ) -> str:
        job_id = f"dlq:{uuid.uuid4().hex}"
        with self.engine.begin() as conn:
            conn.execute(
                insert(memory_job_dlq).values(
                    job_id=job_id,
                    job_type=job_type,
                    user_id=user_id,
                    session_id=session_id,
                    doc_id=doc_id,
                    payload=payload,
                    retry_count=retry_count,
                    error=error,
                    created_at=_utcnow(),
                )
            )
        return job_id

    def dlq_stats(self) -> dict[str, Any]:
        with self.engine.begin() as conn:
            count = conn.execute(select(memory_job_dlq.c.job_id)).fetchall()
        return {"dlq_backlog": len(count)}
