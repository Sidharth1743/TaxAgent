from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

import structlog

from backend.errors import MemoryJobDlqError, SqlPersistenceError, VertexMemoryError
from config import (
    MEMORY_JOB_MAX_CONCURRENCY,
    MEMORY_RETRY_BASE_DELAY_SECONDS,
    MEMORY_RETRY_MAX_ATTEMPTS,
    MEMORY_TOPIC_LIMIT,
    USE_CLOUD_SQL_MEMORY,
)
from memory.sql_memory_store import CloudSqlMemoryStore
from memory.vertex_memory_bank import VertexMemoryBankAdapter

logger = structlog.get_logger(__name__)

_service: "MemoryService | None" = None


def _topic_candidates(text: str) -> list[str]:
    clean = " ".join((text or "").split()).strip()
    if not clean:
        return []
    candidates = [clean[:180]]
    lowered = clean.lower()
    for marker in ("form 16", "w-2", "w2", "1099", "80c", "80d", "h-1b", "hackathon", "cash prize"):
        if marker in lowered and marker not in candidates:
            candidates.append(marker.upper() if marker.startswith("w") else marker)
    return candidates[:4]


class MemoryService:
    def __init__(self) -> None:
        self.sql_store = None
        self.sql_store_mode = "disabled"
        if USE_CLOUD_SQL_MEMORY:
            try:
                self.sql_store = CloudSqlMemoryStore()
                self.sql_store_mode = "configured"
            except Exception as exc:
                logger.warning("cloud_sql_store_init_failed", error=str(exc), fallback="sqlite:///taxagent_memory.db")
                try:
                    self.sql_store = CloudSqlMemoryStore(database_url="sqlite:///taxagent_memory.db")
                    self.sql_store_mode = "sqlite-fallback"
                except Exception as fallback_exc:
                    logger.error("sqlite_memory_store_init_failed", error=str(fallback_exc))
                    self.sql_store = None
                    self.sql_store_mode = "failed"
        self.vertex = VertexMemoryBankAdapter()
        self._semaphore = asyncio.Semaphore(MEMORY_JOB_MAX_CONCURRENCY)
        self._topic_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_job_status: dict[str, dict[str, Any]] = {}

    async def append_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        role: str,
        text: str,
        importance_score: float = 1.0,
    ) -> str | None:
        if not self.sql_store:
            return None
        try:
            return await asyncio.to_thread(
                self.sql_store.append_turn,
                user_id,
                session_id,
                role,
                text,
                importance_score,
            )
        except Exception as exc:
            raise SqlPersistenceError(str(exc)) from exc

    async def load_conversation_context(self, *, user_id: str) -> dict[str, Any]:
        if not self.sql_store:
            return {"summary": "", "recent_turns": [], "prior_topics": [], "loaded": False, "prompt": "", "top_topics": []}
        try:
            context = await asyncio.to_thread(self.sql_store.fetch_context, user_id, MEMORY_TOPIC_LIMIT, 8)
            context["vertex_memories"] = await self.vertex.retrieve_memories(
                user_id=user_id,
                query=context.get("summary", ""),
                limit=3,
            )
            return context
        except Exception as exc:
            logger.warning("memory_context_load_failed", user_id=user_id, error=str(exc))
            return {"summary": "", "recent_turns": [], "prior_topics": [], "loaded": False, "prompt": "", "top_topics": []}

    async def enqueue_summary_refresh(self, *, user_id: str, session_id: str) -> None:
        asyncio.create_task(self._run_summary_refresh(user_id=user_id, session_id=session_id))

    async def _run_summary_refresh(self, *, user_id: str, session_id: str) -> None:
        async with self._topic_locks[user_id]:
            if not self.sql_store:
                return
            try:
                summary = await asyncio.to_thread(self.sql_store.refresh_summary, user_id, session_id, 10)
                recent_context = await asyncio.to_thread(self.sql_store.fetch_context, user_id, MEMORY_TOPIC_LIMIT, 6)
                topics = recent_context.get("prior_topics", [])[:MEMORY_TOPIC_LIMIT]
                await asyncio.to_thread(self.sql_store.upsert_topics, user_id, session_id, topics, None, 0.5)
                self._last_job_status[f"summary:{user_id}:{session_id}"] = {"ok": True, "summary": summary}
                logger.info("memory_summary_refreshed", user_id=user_id, session_id=session_id)
            except Exception as exc:
                self._last_job_status[f"summary:{user_id}:{session_id}"] = {"ok": False, "error": str(exc)}
                logger.warning("memory_summary_refresh_failed", user_id=user_id, session_id=session_id, error=str(exc))

    async def enqueue_turn_memory(
        self,
        *,
        user_id: str,
        session_id: str,
        role: str,
        text: str,
        turn_id: str | None = None,
    ) -> None:
        asyncio.create_task(
            self._run_turn_memory(
                user_id=user_id,
                session_id=session_id,
                role=role,
                text=text,
                turn_id=turn_id,
            )
        )

    async def _run_turn_memory(
        self,
        *,
        user_id: str,
        session_id: str,
        role: str,
        text: str,
        turn_id: str | None,
    ) -> None:
        topics = _topic_candidates(text) if role == "user" else []
        if self.sql_store and topics:
            try:
                async with self._topic_locks[user_id]:
                    await asyncio.to_thread(self.sql_store.upsert_topics, user_id, session_id, topics, turn_id, 1.0)
            except Exception as exc:
                logger.warning("memory_topic_upsert_failed", user_id=user_id, session_id=session_id, error=str(exc))

        if role == "user" and text.strip():
            await self._enqueue_vertex_job(
                job_type="turn_memory",
                user_id=user_id,
                session_id=session_id,
                payload={"text": text, "topics": topics},
                coro_factory=lambda: self.vertex.inject_direct_memory(
                    user_id=user_id,
                    text=f"User discussed: {text.strip()[:300]}",
                    metadata={"topics": topics, "session_id": session_id},
                ),
            )

    async def store_document_memory(
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
        if not self.sql_store:
            raise SqlPersistenceError("SQL store not configured")
        try:
            result = await asyncio.to_thread(
                self.sql_store.store_document,
                user_id=user_id,
                doc_id=doc_id,
                filename=filename,
                form_type=form_type,
                jurisdiction=jurisdiction,
                raw_payload=raw_payload,
                raw_text=raw_text,
                fields=fields,
                tables=tables,
                confirmed=confirmed,
            )
        except Exception as exc:
            raise SqlPersistenceError(str(exc)) from exc

        facts = [f"User uploaded a {form_type.upper()} document ({filename})."]
        for field in fields[:6]:
            if field.get("name") and field.get("value"):
                facts.append(f"{field['name']} is {field['value']}.")

        await self._enqueue_vertex_job(
            job_type="document_memory",
            user_id=user_id,
            doc_id=doc_id,
            payload={"doc_id": doc_id, "facts": facts, "form_type": form_type},
            coro_factory=lambda: self.vertex.inject_direct_memory(
                user_id=user_id,
                text=" ".join(facts)[:1200],
                metadata={"doc_id": doc_id, "form_type": form_type, "jurisdiction": jurisdiction},
            ),
        )
        return result

    async def fetch_document_fields(self, doc_id: str) -> dict[str, str]:
        if not self.sql_store:
            return {}
        return await asyncio.to_thread(self.sql_store.fetch_document_fields, doc_id)

    async def fetch_graph(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        if not self.sql_store:
            return {"nodes": [], "links": []}
        return await asyncio.to_thread(self.sql_store.fetch_graph, user_id)

    async def fetch_insights(self, user_id: str) -> list[dict[str, Any]]:
        if not self.sql_store:
            return []
        return await asyncio.to_thread(self.sql_store.fetch_insights, user_id)

    async def debug_status(self) -> dict[str, Any]:
        dlq = self.sql_store.dlq_stats() if self.sql_store else {"dlq_backlog": 0}
        return {
            "memory_provider": "vertex_sql",
            "sql_enabled": bool(self.sql_store),
            "sql_mode": self.sql_store_mode,
            "vertex_enabled": bool(self.vertex.enabled),
            "last_jobs": self._last_job_status,
            **dlq,
        }

    async def _enqueue_vertex_job(
        self,
        *,
        job_type: str,
        payload: dict[str, Any],
        coro_factory,
        user_id: str | None = None,
        session_id: str | None = None,
        doc_id: str | None = None,
    ) -> None:
        asyncio.create_task(
            self._run_vertex_job(
                job_type=job_type,
                payload=payload,
                user_id=user_id,
                session_id=session_id,
                doc_id=doc_id,
                coro_factory=coro_factory,
            )
        )

    async def _run_vertex_job(
        self,
        *,
        job_type: str,
        payload: dict[str, Any],
        coro_factory,
        user_id: str | None = None,
        session_id: str | None = None,
        doc_id: str | None = None,
    ) -> None:
        async with self._semaphore:
            delay = MEMORY_RETRY_BASE_DELAY_SECONDS
            last_error = ""
            for attempt in range(1, MEMORY_RETRY_MAX_ATTEMPTS + 1):
                try:
                    await coro_factory()
                    self._last_job_status[f"{job_type}:{user_id or 'anon'}:{session_id or doc_id or 'global'}"] = {
                        "ok": True,
                        "attempt": attempt,
                    }
                    logger.info(
                        "vertex_memory_job_succeeded",
                        job_type=job_type,
                        user_id=user_id,
                        session_id=session_id,
                        doc_id=doc_id,
                        attempt=attempt,
                    )
                    return
                except VertexMemoryError as exc:
                    last_error = str(exc)
                    logger.warning(
                        "vertex_memory_job_retry",
                        job_type=job_type,
                        user_id=user_id,
                        session_id=session_id,
                        doc_id=doc_id,
                        attempt=attempt,
                        error=last_error,
                    )
                    if attempt < MEMORY_RETRY_MAX_ATTEMPTS:
                        await asyncio.sleep(delay)
                        delay *= 2

            try:
                if self.sql_store:
                    await asyncio.to_thread(
                        self.sql_store.write_dlq,
                        job_type=job_type,
                        payload=payload,
                        error=last_error or "unknown vertex memory error",
                        retry_count=MEMORY_RETRY_MAX_ATTEMPTS,
                        user_id=user_id,
                        session_id=session_id,
                        doc_id=doc_id,
                    )
                self._last_job_status[f"{job_type}:{user_id or 'anon'}:{session_id or doc_id or 'global'}"] = {
                    "ok": False,
                    "error": last_error or "unknown vertex memory error",
                    "dlq": True,
                }
            except Exception as exc:
                raise MemoryJobDlqError(str(exc)) from exc


def get_memory_service() -> MemoryService:
    global _service
    if _service is None:
        _service = MemoryService()
    return _service
