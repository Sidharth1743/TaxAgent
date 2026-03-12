import asyncio
import base64
import json
import re
from array import array
from typing import Any, AsyncGenerator, Optional

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from fastapi.middleware.cors import CORSMiddleware

from backend.live_orchestrator import run_live_query
from config import GOOGLE_API_KEY, VOICE_MODEL

logger = structlog.get_logger(__name__)

# Import memory bank for proactive greetings
try:
    from backend.memory_bank import close_session, get_proactive_prompt
    MEMORY_BANK_AVAILABLE = True
except ImportError:
    MEMORY_BANK_AVAILABLE = False
    logger.warning("memory_bank_not_available")

# Cache to store session resumption handles across WebSocket disconnects
SESSION_HANDLES: dict[str, str] = {}

BASE_SYSTEM_INSTRUCTION = (
    "You are a helpful tax advisor assistant. "
    "You are connected to a multimodal session. YOU CAN SEE the user's camera feed directly. "
    "When the user holds up documents (like Form 16, payslips, or receipts) or asks you to 'look at this', YOU CAN SEE IT. "
    "Do not tell them to upload it if you can see it clearly. "
    "Answer tax questions clearly and concisely. "
    "DO NOT under any circumstances output or narrate your internal thought process. "
    "Do not say things like 'Clarifying the inquiry' or 'Adjusting my approach'. "
    "Just provide the direct answer to the user. "
    "Do not restart with a welcome or introduction after reconnects. Continue the current conversation naturally."
)

_INTERNAL_AGENT_MARKERS = (
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
    "to offer tax advice",
    "clarifying tax inquiry",
    "clarifying the query",
    "clarifying the inquiry",
    "acknowledge and inquire",
    "determining tax implications",
    "addressing the form 16 inquiry",
    "addressing the",
)


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _is_low_quality_agent_text(text: str) -> bool:
    clean_text = _normalize_text(text)
    if not clean_text:
        return True

    lowered = clean_text.lower()
    if clean_text.startswith("**"):
        return True

    if any(marker in lowered for marker in _INTERNAL_AGENT_MARKERS):
        return True

    if re.match(r"^advisor:\s*\*\*", lowered):
        return True

    if any(
        phrase in lowered
        for phrase in (
            "my initial assessment",
            "i will respond",
            "i will transition",
            "i acknowledge the user's",
            "i acknowledge the user",
            "i'm confirming",
            "i am confirming",
            "i'm ready to assist",
            "i am ready to assist",
        )
    ):
        return True

    return False


def _websocket_connected(websocket: WebSocket) -> bool:
    return websocket.client_state == WebSocketState.CONNECTED


async def _safe_send_json(
    websocket: WebSocket,
    payload: dict[str, Any],
    *,
    log_key: str = "websocket_send_not_deliverable",
    **log_ctx: Any,
) -> bool:
    if not _websocket_connected(websocket):
        return False
    try:
        await websocket.send_json(payload)
        return True
    except (WebSocketDisconnect, RuntimeError) as exc:
        logger.warning(log_key, error=str(exc), **log_ctx)
        return False


def _select_final_agent_text(raw_text: str, tool_answer: str) -> str:
    clean_tool_answer = _normalize_text(tool_answer)
    if clean_tool_answer:
        return clean_tool_answer

    clean_raw_text = _normalize_text(raw_text)
    if not clean_raw_text or _is_low_quality_agent_text(clean_raw_text):
        return ""

    return clean_raw_text


def _is_voiced_audio_chunk(b64_data: str, threshold: int = 450) -> bool:
    try:
        raw = base64.b64decode(b64_data)
    except Exception:
        return False

    if len(raw) < 4:
        return False

    pcm = array("h")
    pcm.frombytes(raw[: len(raw) - (len(raw) % 2)])
    if not pcm:
        return False

    peak = 0
    step = max(1, len(pcm) // 64)
    for idx in range(0, len(pcm), step):
        sample = abs(pcm[idx])
        if sample > peak:
            peak = sample
            if peak >= threshold:
                return True

    return False


def _append_ephemeral_turn(conversation_state: dict[str, Any], role: str, text: str) -> None:
    clean_text = _normalize_text(text)
    if not clean_text:
        return

    turns = conversation_state.setdefault("turns", [])
    if turns and turns[-1].get("role") == role and turns[-1].get("text") == clean_text:
        return

    turns.append({"role": role, "text": clean_text})
    if len(turns) > 10:
        del turns[:-10]


def _build_ephemeral_memory_prompt(conversation_state: dict[str, Any]) -> str:
    turns = conversation_state.get("turns") or []
    if not turns:
        return ""

    serialized = []
    for turn in turns[-6:]:
        role = "User" if turn.get("role") == "user" else "Advisor"
        text = _normalize_text(turn.get("text") or "")
        if text:
            serialized.append(f"{role}: {text[:220]}")

    if not serialized:
        return ""

    return "CURRENT SESSION CONTEXT:\n" + "\n".join(serialized)


def _compose_system_instruction(
    conversation_state: dict[str, Any],
    persistent_memory_prompt: str = "",
    proactive_prompt: str = "",
) -> str:
    blocks = [BASE_SYSTEM_INSTRUCTION]

    if persistent_memory_prompt:
        blocks.append(f"HISTORICAL MEMORY:\n{persistent_memory_prompt}")

    ephemeral_prompt = _build_ephemeral_memory_prompt(conversation_state)
    if ephemeral_prompt:
        blocks.append(ephemeral_prompt)

    if proactive_prompt:
        blocks.append(f"BACKGROUND TAX PROFILE:\n{proactive_prompt}")

    return "\n\n".join(block for block in blocks if block).strip()


async def _load_conversation_memory_context(user_id: str) -> dict[str, Any]:
    try:
        from memory.spanner_graph import (
            fetch_recent_conversation_context,
            format_conversation_context_prompt,
            get_client,
            load_config,
        )

        def _fetch() -> dict[str, Any]:
            cfg = load_config()
            if cfg is None:
                return {"summary": "", "recent_turns": [], "prior_topics": [], "loaded": False}
            database = get_client(cfg)
            context = fetch_recent_conversation_context(database, user_id=user_id)
            context["prompt"] = format_conversation_context_prompt(context)
            return context

        return await asyncio.to_thread(_fetch)
    except Exception as exc:
        logger.warning("conversation_memory_context_failed", user_id=user_id, error=str(exc))
        return {"summary": "", "recent_turns": [], "prior_topics": [], "loaded": False, "prompt": ""}


async def _store_conversation_turn(
    user_id: str,
    session_id: str,
    role: str,
    text: str,
    refresh_summary: bool = False,
) -> None:
    clean_text = _normalize_text(text)
    if not clean_text:
        return

    try:
        from memory.spanner_graph import (
            append_conversation_turn,
            get_client,
            load_config,
            refresh_conversation_summary,
        )

        def _write() -> None:
            cfg = load_config()
            if cfg is None:
                return
            database = get_client(cfg)
            append_conversation_turn(
                database,
                user_id=user_id,
                session_id=session_id,
                role=role,
                text=clean_text,
            )
            if refresh_summary:
                refresh_conversation_summary(
                    database,
                    user_id=user_id,
                    session_id=session_id,
                )

        await asyncio.to_thread(_write)
    except Exception as exc:
        logger.warning(
            "conversation_turn_store_failed",
            user_id=user_id,
            session_id=session_id,
            role=role,
            error=str(exc),
        )



class GeminiLiveProxy:
    def __init__(self):
        if not GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY environment variable not set")

        from google import genai
        # v1alpha is required for preview Live API models like
        # gemini-2.5-flash-native-audio-dialog (not available on v1beta default)
        self.client = genai.Client(
            api_key=GOOGLE_API_KEY,
            http_options={"api_version": "v1alpha"},
        )
        self.active_session = None
        self._session_cm = None
        self.session_alive = False  # True only when Gemini session is confirmed active
        self._resumption_handle: Optional[str] = None

    async def connect(
        self,
        session_id: str,
        system_instruction: str = (
            "You are a helpful tax advisor assistant. "
            "When greeting a user proactively, keep it brief and friendly."
        ),
        voice_name: str = "Aoede",
        response_modalities: list = None,
    ):
        """Connect to Gemini Live API

        Args:
            session_id: Unique session identifier.
            system_instruction: System prompt for the agent.
            voice_name: Voice name for speech output (e.g. Aoede, Puck, Charon).
            response_modalities: List of response types, e.g. ["AUDIO"] or ["TEXT"].
        """
        if response_modalities is None:
            response_modalities = ["AUDIO"]

        # Store config for auto-reconnect
        self._last_session_id = session_id
        self._last_system_instruction = system_instruction
        self._last_voice_name = voice_name
        self._last_response_modalities = response_modalities

        try:
            # Build the connect config.
            # NOTE: context_window_compression and session_resumption with a
            # null handle both cause 1007 on gemini-2.0-flash-live-001 — only
            # include session_resumption when we actually have a prior handle.
            live_config: dict = {
                "system_instruction": system_instruction,
                "response_modalities": response_modalities,
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {
                            "voice_name": voice_name
                        }
                    }
                },
                "tools": [{"function_declarations": [{
                    "name": "ask_geo_router",
                    "description": (
                        "Forward the user's explicit tax query to the Geo Router, "
                        "which will delegate to the correct India or USA tax clusters "
                        "to calculate tax liability or strategies."
                    ),
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "tax_query": {
                                "type": "STRING",
                                "description": "The specific tax question, numbers, or forms to evaluate."
                            }
                        },
                        "required": ["tax_query"]
                    }
                }]}],
            }

            # Only include session resumption when we have an actual handle
            if self._resumption_handle:
                live_config["session_resumption"] = {"handle": self._resumption_handle}

            logger.info("gemini_live_connect_payload", config=live_config)

            self._session_cm = self.client.aio.live.connect(
                model=VOICE_MODEL,
                config=live_config,
            )

            self.active_session = await self._session_cm.__aenter__()
            self.session_alive = True
            return self.active_session
        except Exception as e:
            logger.error("failed_to_connect_to_gemini_live", error=str(e))
            raise

    async def reconnect(self):
        """Reconnect using the same config as the last connect() call."""
        await self.close()
        return await self.connect(
            self._last_session_id,
            system_instruction=self._last_system_instruction,
            voice_name=self._last_voice_name,
            response_modalities=self._last_response_modalities,
        )

    async def send_audio_b64(self, b64_data: str):
        """Send base64-encoded audio directly to Gemini Live.

        Accepts the base64 string straight from the frontend so we
        skip the unnecessary decode→re-encode cycle.
        MIME type includes sample rate which is REQUIRED by the
        native-audio model — without it the session drops with 1011.
        """
        if not self.active_session or not self.session_alive:
            return  # silently drop — session is dead
        await self.active_session.send_realtime_input(
            audio={"mime_type": "audio/pcm;rate=16000", "data": b64_data}
        )

    async def send_video_b64(self, b64_data: str):
        """Send base64-encoded video frame directly to Gemini Live."""
        if not self.active_session or not self.session_alive:
            return
        try:
            raw_bytes = base64.b64decode(b64_data)
        except Exception:
            return
            
        await self.active_session.send_realtime_input(
            video={"mime_type": "image/jpeg", "data": raw_bytes}
        )

    async def send_text(self, text: str):
        """
        Send a text input to Gemini Live.

        Note: send_client_content is NOT supported by gemini-2.5-flash-native-audio-latest.
        The native-audio model only accepts send_realtime_input. Using send_client_content
        causes the Gemini WS to enter an unexpected state and then drop with 1011 keepalive
        timeout when the next audio frame arrives.
        """
        if not self.active_session or not self.session_alive:
            raise RuntimeError("Not connected to Gemini Live")
        await self.active_session.send_realtime_input(text=text)

    async def receive_response(self) -> AsyncGenerator[dict, None]:
        """Receive response stream from Gemini Live"""
        if not self.active_session:
            raise RuntimeError("Not connected to Gemini Live")
        async for response in self.active_session.receive():
            yield response

    async def close(self):
        """Close the Gemini Live session"""
        self.session_alive = False
        if self._session_cm:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception as e:
                logger.error("error_during_close", error=str(e))
            self._session_cm = None
            self.active_session = None


async def _forward_gemini_responses(
    proxy: GeminiLiveProxy,
    websocket: WebSocket,
    user_id: str,
    session_id: str,
    conversation_state: dict[str, Any],
):
    """
    Background asyncio.Task — continuously reads responses from Gemini Live
    and forwards audio, text, and control events to the browser WebSocket.

    Includes auto-reconnect: if the Gemini session times out (keepalive
    or inactivity), this function reconnects and resumes listening.
    """
    current_agent_chunks: list[str] = []
    try:
        async for response in proxy.receive_response():
            if not _websocket_connected(websocket):
                return

            server_content = getattr(response, "server_content", None)
            if server_content:
                if getattr(server_content, "interrupted", False):
                    current_agent_chunks = []
                    conversation_state["last_tool_answer"] = ""
                    await _safe_send_json(websocket, {"type": "interrupted"})

                if getattr(server_content, "turn_complete", False):
                    finalized_agent_text = _select_final_agent_text(
                        "".join(current_agent_chunks),
                        str(conversation_state.get("last_tool_answer", "")),
                    )
                    if (
                        finalized_agent_text
                        and finalized_agent_text != conversation_state.get("last_agent_text")
                    ):
                        _append_ephemeral_turn(conversation_state, "agent", finalized_agent_text)
                        await _store_conversation_turn(
                            user_id=user_id,
                            session_id=session_id,
                            role="agent",
                            text=finalized_agent_text,
                            refresh_summary=True,
                        )
                        conversation_state["last_agent_text"] = finalized_agent_text
                    current_agent_chunks = []
                    conversation_state["last_tool_answer"] = ""
                    await _safe_send_json(websocket, {"type": "turnComplete"})

                model_turn = getattr(server_content, "model_turn", None)
                if model_turn:
                    for part in getattr(model_turn, "parts", []):
                        part_text = getattr(part, "text", None)
                        if part_text:
                            current_agent_chunks.append(part_text)
                            if not _is_low_quality_agent_text(part_text):
                                await _safe_send_json(websocket, {
                                    "type": "text",
                                    "text": part_text,
                                })

                        inline_data = getattr(part, "inline_data", None)
                        if inline_data:
                            audio_b64 = getattr(inline_data, "data", None)
                            if audio_b64 is not None:
                                if isinstance(audio_b64, bytes):
                                    audio_b64 = base64.b64encode(audio_b64).decode("utf-8")
                                await _safe_send_json(websocket, {
                                    "type": "audio",
                                    "data": audio_b64,
                                })

            resumption_update = getattr(response, "session_resumption_update", None)
            if resumption_update:
                new_handle = getattr(resumption_update, "new_handle", None) or getattr(resumption_update, "handle", None)
                if new_handle:
                    proxy._resumption_handle = new_handle
                    SESSION_HANDLES[proxy._last_session_id] = new_handle
                    logger.info("session_resumption_handle_updated", session_id=proxy._last_session_id)

            tool_call = getattr(response, "tool_call", None)
            if tool_call:
                for call in getattr(tool_call, "function_calls", []):
                    if call.name != "ask_geo_router":
                        continue

                    args = getattr(call, "args", {}) or {}
                    query = args.get("tax_query", "")
                    logger.info("tool_call", function="ask_geo_router", tax_query=query)

                    if query and query != conversation_state.get("last_user_text"):
                        _append_ephemeral_turn(conversation_state, "user", query)
                        await _store_conversation_turn(
                            user_id=user_id,
                            session_id=session_id,
                            role="user",
                            text=query,
                        )
                        conversation_state["last_user_text"] = query

                    await _safe_send_json(websocket, {"type": "user_text", "text": query})
                    await _safe_send_json(websocket, {"type": "thinking"})
                    routing_result = await process_voice_query(
                        query,
                        user_id=user_id,
                        session_id=session_id,
                    )
                    answer = routing_result.get("content", {}).get(
                        "synthesized_response",
                        str(routing_result),
                    )
                    conversation_state["last_tool_answer"] = _normalize_text(answer)

                    content_event = {
                        "type": "content",
                        "content": routing_result.get("content", {}),
                    }
                    await _safe_send_json(websocket, content_event)
                    logger.info(
                        "routing_result_sent",
                        user_id=user_id,
                        session_id=session_id,
                        sources=len(routing_result.get("content", {}).get("sources", []) or []),
                        claims=len(routing_result.get("content", {}).get("claims", []) or []),
                    )

                    try:
                        from google.genai import types as genai_types
                        await proxy.active_session.send_tool_response(
                            function_responses=[
                                genai_types.FunctionResponse(
                                    id=call.id,
                                    name=call.name,
                                    response={"result": answer},
                                )
                            ]
                        )
                    except (ImportError, AttributeError, TypeError):
                        logger.warning("send_tool_response_unavailable_using_fallback")
                        await proxy.active_session.send_realtime_input(
                            tool_response={
                                "function_responses": [{
                                    "id": call.id,
                                    "name": call.name,
                                    "response": {"result": answer},
                                }]
                            }
                        )

        proxy.session_alive = False
        logger.warning("gemini_live_session_ended")
    except asyncio.CancelledError:
        logger.info("response_forwarding_task_cancelled")
        return
    except Exception as e:
        proxy.session_alive = False
        logger.error("response_forwarding_error", error=str(e))


def create_websocket_app() -> FastAPI:
    app = FastAPI()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        logger.info("websocket_client_connected", client=str(websocket.client))
        proxy = GeminiLiveProxy()
        session_id = "default"
        user_id = "anonymous"
        response_task: Optional[asyncio.Task] = None
        reconnect_lock = asyncio.Lock()
        audio_chunk_count = 0
        conversation_state: dict[str, Any] = {
            "last_user_text": None,
            "last_agent_text": None,
            "last_tool_answer": "",
            "turns": [],
            "persistent_memory_prompt": "",
            "proactive_prompt": "",
        }

        async def ensure_live_session(reason: str) -> bool:
            nonlocal response_task

            if proxy.session_alive and proxy.active_session:
                return True

            async with reconnect_lock:
                if proxy.session_alive and proxy.active_session:
                    return True

                try:
                    proxy._last_system_instruction = _compose_system_instruction(
                        conversation_state,
                        persistent_memory_prompt=conversation_state.get("persistent_memory_prompt", ""),
                        proactive_prompt=conversation_state.get("proactive_prompt", ""),
                    )
                    await proxy.reconnect()

                    if response_task and not response_task.done():
                        response_task.cancel()
                        try:
                            await response_task
                        except asyncio.CancelledError:
                            pass

                    response_task = asyncio.create_task(
                        _forward_gemini_responses(proxy, websocket, user_id, session_id, conversation_state)
                    )

                    await _safe_send_json(
                        websocket,
                        {"type": "reconnected"},
                        log_key="reconnect_notice_not_deliverable",
                        reason=reason,
                    )
                    logger.info("gemini_session_reconnected", reason=reason)
                    return True
                except Exception as exc:
                    logger.error("reconnect_attempt_failed", reason=reason, error=str(exc))
                    await _safe_send_json(
                        websocket,
                        {"type": "error", "message": f"Session reconnect failed: {exc}"},
                        log_key="reconnect_error_not_deliverable",
                        reason=reason,
                        error=str(exc),
                    )
                    return False

        try:
            session_started = False
            while True:
                if not _websocket_connected(websocket):
                    break
                try:
                    raw_message = await websocket.receive_text()
                except WebSocketDisconnect:
                    raise
                except RuntimeError as exc:
                    logger.info("websocket_receive_closed", error=str(exc))
                    break
                try:
                    data = json.loads(raw_message)
                except json.JSONDecodeError:
                    await _safe_send_json(websocket, {"type": "error", "message": "Invalid JSON"})
                    continue

                msg_type = data.get("type")

                # ── Session start ─────────────────────────────────────────
                if msg_type == "start" and not session_started:
                    try:
                        session_id = data.get("session_id", "default")
                        user_id = data.get("user_id", "anonymous")
                        logger.info(
                            "session_start_request",
                            user_id=user_id,
                            session_id=session_id,
                            voice=data.get("voice"),
                            response_modalities=data.get("response_modalities"),
                        )

                        # Read user-chosen config from the frontend SettingsDialog
                        voice_name = data.get("voice", "Aoede")
                        response_modalities = data.get("response_modalities", ["AUDIO"])
                        
                        # Fix #2: Gemini 2.5 native audio models crash with 1007 if "TEXT" is included
                        # Forcing it to just AUDIO.
                        if "TEXT" in response_modalities:
                            response_modalities.remove("TEXT")
                        if not response_modalities:
                            response_modalities = ["AUDIO"]

                        conversation_memory = await _load_conversation_memory_context(user_id)
                        memory_prompt = conversation_memory.get("prompt", "")
                        conversation_state["persistent_memory_prompt"] = memory_prompt

                        if MEMORY_BANK_AVAILABLE:
                            try:
                                proactive_prompt = await get_proactive_prompt(user_id)
                                if proactive_prompt:
                                    conversation_state["proactive_prompt"] = proactive_prompt
                                    logger.info("using_proactive_prompt", user_id=user_id)
                            except Exception as exc:
                                logger.warning("memory_bank_fetch_failed", error=str(exc))

                        system_instruction = _compose_system_instruction(
                            conversation_state,
                            persistent_memory_prompt=conversation_state.get("persistent_memory_prompt", ""),
                            proactive_prompt=conversation_state.get("proactive_prompt", ""),
                        )

                        # Try to resume conversation if we have a cached handle
                        cached_handle = SESSION_HANDLES.get(session_id)
                        if cached_handle:
                            proxy._resumption_handle = cached_handle
                            logger.info("resuming_previous_session", session_id=session_id)

                        await proxy.connect(
                            session_id,
                            system_instruction=system_instruction,
                            voice_name=voice_name,
                            response_modalities=response_modalities,
                        )
                        session_started = True
                        logger.info("session_started", user_id=user_id, session_id=session_id)

                        await _safe_send_json(websocket, {"type": "connected"})
                        await _safe_send_json(
                            websocket,
                            {"type": "memory_context", "memory_context": conversation_memory},
                        )

                        response_task = asyncio.create_task(
                            _forward_gemini_responses(proxy, websocket, user_id, session_id, conversation_state)
                        )

                    except Exception as exc:
                        logger.error("session_start_failed", error=str(exc), exc_info=True)
                        await _safe_send_json(
                            websocket,
                            {"type": "error", "message": str(exc)},
                            log_key="session_start_error_not_deliverable",
                            error=str(exc),
                        )
                        continue

                # ── Audio stream from browser mic ─────────────────────────
                elif msg_type == "audio":
                    if not session_started or not proxy.session_alive:
                        if not session_started:
                            continue
                        if not _is_voiced_audio_chunk(data["data"]):
                            continue
                        if not await ensure_live_session("audio"):
                            continue
                    try:
                        audio_chunk_count += 1
                        if audio_chunk_count == 1 or audio_chunk_count % 50 == 0:
                            logger.info(
                                "audio_chunk_received",
                                user_id=user_id,
                                session_id=session_id,
                                chunks=audio_chunk_count,
                            )
                        await proxy.send_audio_b64(data["data"])
                    except Exception as exc:
                        proxy.session_alive = False
                        logger.warning("audio_send_failed", error=str(exc))
                        await _safe_send_json(
                            websocket,
                            {"type": "error", "message": f"Audio send failed: {exc}"},
                        )

                # ── Video frame from browser camera ───────────────────────
                elif msg_type == "video":
                    if not session_started or not proxy.session_alive:
                        continue
                    try:
                        logger.info("video_frame_received", user_id=user_id, session_id=session_id)
                        await proxy.send_video_b64(data["data"])
                    except Exception as exc:
                        proxy.session_alive = False
                        logger.warning("video_send_failed", error=str(exc))

                # ── Text message from chat panel ──────────────────────────
                elif msg_type == "text":
                    if not session_started:
                        await _safe_send_json(websocket, {"type": "error", "message": "Session not started"})
                        continue
                    try:
                        text = data.get("text", "")
                        logger.info(
                            "text_received",
                            user_id=user_id,
                            session_id=session_id,
                            length=len(text or ""),
                        )
                        if not proxy.session_alive and not await ensure_live_session("text"):
                            continue
                        await proxy.send_text(text)
                        clean_text = _normalize_text(text)
                        if clean_text:
                            _append_ephemeral_turn(conversation_state, "user", clean_text)
                            await _store_conversation_turn(
                                user_id=user_id,
                                session_id=session_id,
                                role="user",
                                text=clean_text,
                            )
                            conversation_state["last_user_text"] = clean_text
                    except Exception as exc:
                        logger.error("text_send_failed", error=str(exc))
                        await _safe_send_json(
                            websocket,
                            {"type": "error", "message": f"Text send failed: {exc}"},
                        )

                # ── Interrupt (user speaking over AI) ─────────────────────
                elif msg_type == "interrupt":
                    try:
                        logger.info("interrupt_received", user_id=user_id, session_id=session_id)
                        if response_task and not response_task.done():
                            response_task.cancel()
                        await proxy.close()
                        await _safe_send_json(websocket, {"type": "interrupted"})
                        # Reconnect for next turn
                        proxy._last_system_instruction = _compose_system_instruction(
                            conversation_state,
                            persistent_memory_prompt=conversation_state.get("persistent_memory_prompt", ""),
                            proactive_prompt=conversation_state.get("proactive_prompt", ""),
                        )
                        await ensure_live_session("interrupt")
                    except Exception as exc:
                        logger.error("interrupt_failed", error=str(exc))

                # ── Stop session ──────────────────────────────────────────
                elif msg_type == "stop":
                    logger.info("stop_received", user_id=user_id, session_id=session_id)
                    if response_task and not response_task.done():
                        response_task.cancel()
                    await proxy.close()
                    await _safe_send_json(websocket, {"type": "stopped"})
                    break

        except WebSocketDisconnect:
            logger.info("websocket_client_disconnected")
            if MEMORY_BANK_AVAILABLE and session_started:
                try:
                    await close_session(session_id)
                except Exception as exc:
                    logger.error("failed_to_close_memory_bank_session", error=str(exc))
        except Exception as exc:
            logger.error("websocket_handler_error", error=str(exc), exc_info=True)
            await _safe_send_json(
                websocket,
                {"type": "error", "message": str(exc)},
                log_key="websocket_error_not_deliverable",
                error=str(exc),
            )
        finally:
            if response_task and not response_task.done():
                response_task.cancel()
                try:
                    await response_task
                except asyncio.CancelledError:
                    pass
            await proxy.close()

    return app


# Module-level app export so `uvicorn backend.websocket_server:app` works
app = create_websocket_app()


# ── Standalone run for testing / direct launch ─────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003, log_level="info")


# ── Voice + Geo Router Integration ────────────────────────────────────────────
async def process_voice_query(
    transcribed_text: str,
    user_id: str = "anonymous",
    session_id: str = "default",
) -> dict:
    """Process transcribed text through the shared live orchestrator."""
    try:
        return await run_live_query(
            transcribed_text,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception as exc:
        logger.warning("live_query_orchestration_failed", error=str(exc))
        try:
            from agents.adk.geo_router.agent import keyword_based_routing
            routing_info = await keyword_based_routing(transcribed_text)
            jurisdiction = routing_info.get("jurisdiction", "tax")
            return {
                "routing": routing_info,
                "content": {
                    "query": transcribed_text,
                    "sources": [],
                    "claims": [],
                    "contradictions": [],
                    "jurisdiction": jurisdiction,
                    "synthesized_response": (
                        f"Your query seems to be related to {jurisdiction} jurisdiction. "
                        "Please ask a more specific tax question."
                    ),
                },
            }
        except Exception:
            return {
                "content": {
                    "query": transcribed_text,
                    "sources": [],
                    "claims": [],
                    "contradictions": [],
                    "jurisdiction": "both",
                    "synthesized_response": (
                        "I couldn't process your query through the tax routing system. "
                        "Please ask your tax question directly."
                    ),
                },
            }
