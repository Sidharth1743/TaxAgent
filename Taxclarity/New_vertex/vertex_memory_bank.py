from __future__ import annotations

import asyncio
from typing import Any

import structlog

from backend.errors import VertexMemoryError
from config import (
    USE_VERTEX_MEMORY,
    VERTEX_LOCATION,
    VERTEX_MEMORY_APP_ID,
    VERTEX_PROJECT_ID,
    VERTEX_REASONING_ENGINE_ID,
)

logger = structlog.get_logger(__name__)


class VertexMemoryBankAdapter:
    """Thin adapter shell for Vertex Memory Bank.

    Local/dev environments typically run with USE_VERTEX_MEMORY=false.
    In that mode this adapter becomes a no-op so the live app keeps working.
    """

    def __init__(self) -> None:
        self.enabled = bool(USE_VERTEX_MEMORY and VERTEX_PROJECT_ID and VERTEX_LOCATION)
        self._client = None

    def _agent_engine_name(self) -> str:
        agent_id = VERTEX_REASONING_ENGINE_ID or VERTEX_MEMORY_APP_ID
        if not agent_id:
            raise VertexMemoryError(
                "Vertex memory is enabled but no reasoning engine id or memory app id is configured"
            )
        if agent_id.startswith("projects/"):
            return agent_id
        return f"projects/{VERTEX_PROJECT_ID}/locations/{VERTEX_LOCATION}/reasoningEngines/{agent_id}"

    def _get_client(self):
        if self._client is None:
            try:
                import vertexai
            except Exception as exc:  # pragma: no cover - import failure depends on env
                raise VertexMemoryError(f"vertexai SDK unavailable: {exc}") from exc
            self._client = vertexai.Client(project=VERTEX_PROJECT_ID, location=VERTEX_LOCATION)
        return self._client

    async def inject_direct_memory(self, *, user_id: str, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled:
            return {"stored": False, "provider": "vertex", "reason": "disabled"}
        try:
            client = self._get_client()
            name = self._agent_engine_name()

            def _create():
                from vertexai import types

                config = None
                if metadata:
                    metadata_values = {
                        key: types.MemoryMetadataValue(string_value=str(value))
                        for key, value in metadata.items()
                    }
                    config = types.AgentEngineMemoryConfig(
                        display_name=f"memory-{user_id}",
                        description="TaxAgent user memory",
                        metadata=metadata_values,
                    )
                return client.agent_engines.memories.create(
                    name=name,
                    fact=text,
                    scope={"user_id": user_id},
                    config=config,
                )

            operation = await asyncio.to_thread(_create)
            logger.info(
                "vertex_memory_direct_injection_succeeded",
                user_id=user_id,
                agent_engine=name,
                operation_name=getattr(operation, "name", None),
            )
            response = getattr(operation, "response", None)
            return {
                "stored": True,
                "provider": "vertex",
                "mode": "direct",
                "operation_name": getattr(operation, "name", None),
                "memory_name": getattr(response, "name", None),
                "fact": getattr(response, "fact", text),
                "metadata": metadata or {},
            }
        except Exception as exc:  # pragma: no cover - defensive
            raise VertexMemoryError(str(exc)) from exc

    async def retrieve_memories(self, *, user_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        try:
            client = self._get_client()
            name = self._agent_engine_name()

            def _retrieve():
                from vertexai import types

                params = None
                if query.strip():
                    params = types.RetrieveMemoriesRequestSimilaritySearchParams(
                        searchQuery=query,
                        topK=limit,
                    )
                    return list(
                        client.agent_engines.memories.retrieve(
                            name=name,
                            scope={"user_id": user_id},
                            similarity_search_params=params,
                        )
                    )

                simple_params = types.RetrieveMemoriesRequestSimpleRetrievalParams(
                    pageSize=limit,
                )
                return list(
                    client.agent_engines.memories.retrieve(
                        name=name,
                        scope={"user_id": user_id},
                        simple_retrieval_params=simple_params,
                    )
                )

            memories = await asyncio.to_thread(_retrieve)
            normalized: list[dict[str, Any]] = []
            for item in memories:
                memory = getattr(item, "memory", None)
                if not memory:
                    continue
                normalized.append(
                    {
                        "name": getattr(memory, "name", ""),
                        "fact": getattr(memory, "fact", ""),
                        "scope": getattr(memory, "scope", {}) or {},
                        "topics": getattr(memory, "topics", []) or [],
                        "distance": getattr(item, "distance", None),
                    }
                )

            logger.info(
                "vertex_memory_retrieval_succeeded",
                user_id=user_id,
                agent_engine=name,
                query_preview=query[:120],
                limit=limit,
                result_count=len(normalized),
            )
            return normalized
        except Exception as exc:  # pragma: no cover - defensive
            raise VertexMemoryError(str(exc)) from exc
