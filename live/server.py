"""FastAPI server bridging browser WebSocket <-> Gemini Live API via ADK.

Uses ADK's runner.run_live() with LiveRequestQueue for proper streaming
with automatic tool execution.

Follows the ADK Gemini Live API Toolkit 4-phase lifecycle:
  Phase 1: Application Init (once at startup) - Agent, SessionService, Runner
  Phase 2: Session Init (per connection) - get/create Session, RunConfig, LiveRequestQueue
  Phase 3: Bidi-streaming - upstream(WS->Queue) + downstream(run_live->WS)
  Phase 4: Terminate - LiveRequestQueue.close()

Endpoints:
  GET  /              — Serve frontend/index.html
  WS   /ws/live       — Bidirectional audio streaming via ADK
  POST /api/vision    — Document image analysis
  GET  /api/graph     — Proxy to graph_api /graph
  GET  /api/users     — Proxy to graph_api /users
  GET  /api/sessions  — Proxy to graph_api /sessions
  GET  /health        — Health check
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from google.genai import types
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.agents.live_request_queue import LiveRequestQueue

from .tools import tool_functions
from .audio_utils import INPUT_SAMPLE_RATE, compute_rms

# Load environment
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(ROOT, ".env"))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GEMINI_LIVE_MODEL = os.getenv(
    "GEMINI_LIVE_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025"
)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GRAPH_API_URL = os.getenv("GRAPH_API_URL", "http://localhost:9000")

# Set API key for google-genai
os.environ.setdefault("GOOGLE_API_KEY", GOOGLE_API_KEY)

TAXCLARITY_PERSONA = """You are TaxClarity, a warm and knowledgeable AI tax advisor. Your voice is professional
but approachable — think trusted family accountant. You cover both Indian and US tax law,
with special expertise in NRI cross-border situations.

RULES:
- ALWAYS use search_tax_knowledge before answering tax questions. NEVER answer from memory alone.
- Cite specific URLs when making claims. Say "According to a CAClubIndia expert thread..." or similar.
- If a question spans India AND US tax, search both regions by using region="all".
- Detect jurisdiction from context: Section 80C → India, 401k → US, DTAA → cross-border.
- If unsure of jurisdiction, ASK the user.
- Use get_user_memory at the start of conversations to personalize advice.
- After answering a substantive question, call save_to_memory to build the user's profile.
- When the user shows a document, call analyze_document and explain what you see.
- Be concise in speech — long pauses lose the user. Aim for 2-3 sentences per response turn.
- When citing sources, mention the source name and key details so the user knows the advice is grounded.
- If search returns no results, honestly say you couldn't find specific sources and suggest the user consult a tax professional.
- For Indian tax: focus on Income Tax Act sections, CBDT circulars, and expert CA opinions.
- For US tax: focus on IRS publications, tax code sections, and professional tax advice.
- For cross-border (NRI/DTAA): always check both jurisdictions and the Double Tax Avoidance Agreement."""

# ---------------------------------------------------------------------------
# Phase 1: Application Initialization (once at startup)
# ---------------------------------------------------------------------------

APP_NAME = "taxclarity"

taxclarity_agent = Agent(
    name="taxclarity",
    model=GEMINI_LIVE_MODEL,
    instruction=TAXCLARITY_PERSONA,
    tools=tool_functions,
)

session_service = InMemorySessionService()

runner = Runner(
    app_name=APP_NAME,
    agent=taxclarity_agent,
    session_service=session_service,
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="TaxClarity Live Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
FRONTEND_DIR = os.path.join(ROOT, "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")

STATIC_DIR = os.path.join(ROOT, "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
async def health():
    return {"status": "ok", "model": GEMINI_LIVE_MODEL}


@app.get("/", response_class=HTMLResponse)
async def index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>TaxClarity — frontend/index.html not found</h1>", status_code=404)


# ---------------------------------------------------------------------------
# Graph API proxies
# ---------------------------------------------------------------------------

async def _proxy_graph(path: str, params: dict) -> JSONResponse:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{GRAPH_API_URL}/{path}", params=params)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=502)


@app.get("/api/graph")
async def api_graph(
    user_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
):
    params = {}
    if user_id:
        params["user_id"] = user_id
    if session_id:
        params["session_id"] = session_id
    return await _proxy_graph("graph", params)


@app.get("/api/users")
async def api_users():
    return await _proxy_graph("users", {})


@app.get("/api/sessions")
async def api_sessions(user_id: str = Query(...)):
    return await _proxy_graph("sessions", {"user_id": user_id})


# ---------------------------------------------------------------------------
# Document vision endpoint
# ---------------------------------------------------------------------------

@app.post("/api/vision")
async def api_vision(file: UploadFile = File(...)):
    """Analyze an uploaded tax document image using Gemini vision."""
    from google import genai as _genai
    try:
        image_bytes = await file.read()
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        mime_type = file.content_type or "image/jpeg"

        client = _genai.Client(api_key=GOOGLE_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        types.Part(text=
                            "Analyze this tax document. Extract all key fields: "
                            "document type, tax year, name, employer, gross income, "
                            "deductions, tax paid, any notable items. "
                            "Return as structured JSON."
                        ),
                    ]
                )
            ],
        )
        return JSONResponse(content={
            "status": "success",
            "analysis": response.text,
            "image_base64": image_b64,
            "mime_type": mime_type,
        })
    except Exception as e:
        logger.exception("Vision analysis failed")
        return JSONResponse(
            content={"status": "error", "error": str(e)},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Gemini Live WebSocket via ADK runner.run_live()
# ---------------------------------------------------------------------------

@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    """Bidirectional audio streaming via ADK runner.run_live().

    Follows the ADK 4-phase lifecycle pattern from the docs.
    """
    await ws.accept()
    logger.info("WebSocket client connected")

    # Default identifiers — can be overridden by client config message
    user_id = "anonymous"
    session_id = str(uuid.uuid4())

    # Phase 4 cleanup reference
    live_request_queue: Optional[LiveRequestQueue] = None

    try:
        # ==============================
        # Phase 2: Session Initialization
        # ==============================

        # Get or create ADK session (recommended pattern from docs)
        session = await session_service.get_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        if not session:
            session = await session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
        session_id = session.id

        # Create RunConfig — session-specific configuration
        # Native audio models require AUDIO response modality with transcription
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=["AUDIO"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            session_resumption=types.SessionResumptionConfig(),
        )

        # Create LiveRequestQueue in async context (best practice from docs)
        live_request_queue = LiveRequestQueue()

        await ws.send_json({"type": "connected", "model": GEMINI_LIVE_MODEL})

        # ==============================
        # Phase 3: Bidi-streaming
        # ==============================

        # --- Upstream: browser → ADK via LiveRequestQueue ---
        async def upstream_task() -> None:
            """Receives messages from WebSocket and sends to LiveRequestQueue."""
            try:
                while True:
                    message = await ws.receive()

                    if message.get("type") == "websocket.disconnect":
                        break

                    if "bytes" in message and message["bytes"]:
                        # Audio PCM from browser mic → send_realtime()
                        audio_blob = types.Blob(
                            data=message["bytes"],
                            mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}",
                        )
                        live_request_queue.send_realtime(audio_blob)

                    elif "text" in message and message["text"]:
                        try:
                            data = json.loads(message["text"])
                        except json.JSONDecodeError:
                            continue

                        msg_type = data.get("type", "")

                        if msg_type == "text":
                            # Text message → send_content() (no role, per docs)
                            text_content = data.get("content", "")
                            if text_content:
                                content = types.Content(
                                    parts=[types.Part(text=text_content)]
                                )
                                live_request_queue.send_content(content)

                        elif msg_type == "config":
                            # Client sends user config — log it
                            nonlocal user_id
                            user_id = data.get("user_id", "anonymous")
                            logger.info(f"Client config: user_id={user_id}")

                        elif msg_type == "image":
                            # Image data → send_realtime() with image mime
                            image_b64 = data.get("data", "")
                            mime = data.get("mime_type", "image/jpeg")
                            if image_b64:
                                image_bytes = base64.b64decode(image_b64)
                                image_blob = types.Blob(
                                    data=image_bytes,
                                    mime_type=mime,
                                )
                                live_request_queue.send_realtime(image_blob)
                                logger.info("Sent document image to Live API via send_realtime()")

            except WebSocketDisconnect:
                logger.debug("Client disconnected in upstream")
            except asyncio.CancelledError:
                logger.debug("Upstream task cancelled")
            except Exception:
                logger.exception("Upstream error")

        # --- Downstream: ADK events → browser ---
        async def downstream_task() -> None:
            """Receives Events from run_live() and sends to WebSocket."""
            try:
                async for event in runner.run_live(
                    user_id=user_id,
                    session_id=session_id,
                    live_request_queue=live_request_queue,
                    run_config=run_config,
                ):
                    # Audio and text content from model
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            # Audio output → send as binary WebSocket frame
                            if part.inline_data and part.inline_data.data:
                                await ws.send_bytes(part.inline_data.data)
                                level = compute_rms(part.inline_data.data)
                                if level > 0.01:
                                    await ws.send_json({
                                        "type": "audio_level",
                                        "level": round(level, 3),
                                    })
                            # Text output (including transcriptions)
                            elif part.text:
                                await ws.send_json({
                                    "type": "transcript" if event.partial else "text",
                                    "content": part.text,
                                })

                    # Input transcription (what user said via voice)
                    if event.input_transcription:
                        t = event.input_transcription
                        await ws.send_json({
                            "type": "input_transcription",
                            "content": t.text if hasattr(t, "text") else str(t),
                            "finished": getattr(t, "finished", True),
                        })

                    # Output transcription (what agent said via voice)
                    if event.output_transcription:
                        t = event.output_transcription
                        await ws.send_json({
                            "type": "output_transcription",
                            "content": t.text if hasattr(t, "text") else str(t),
                            "finished": getattr(t, "finished", True),
                        })

                    # Tool call events — ADK executes tools automatically,
                    # but we notify browser for UI feedback (source cards, etc.)
                    if event.get_function_calls():
                        for fc in event.get_function_calls():
                            await ws.send_json({
                                "type": "tool_call",
                                "name": fc.name,
                                "args": dict(fc.args) if fc.args else {},
                            })

                    if event.get_function_responses():
                        for fr in event.get_function_responses():
                            await ws.send_json({
                                "type": "tool_result",
                                "name": fr.name,
                                "result": fr.response if isinstance(fr.response, dict) else {"text": str(fr.response)},
                            })

                    # Turn completion signal
                    if event.turn_complete:
                        await ws.send_json({"type": "turn_complete"})

                    # Interruption signal
                    if event.interrupted:
                        await ws.send_json({"type": "interrupted"})

                    # Error events
                    if event.error_code:
                        await ws.send_json({
                            "type": "error",
                            "message": f"{event.error_code}: {event.error_message or ''}",
                        })

            except WebSocketDisconnect:
                logger.debug("Client disconnected in downstream")
            except asyncio.CancelledError:
                logger.debug("Downstream task cancelled")
            except Exception:
                logger.exception("Downstream error")

        # Run upstream and downstream concurrently (docs pattern)
        try:
            await asyncio.gather(
                upstream_task(),
                downstream_task(),
                return_exceptions=True,
            )
        except WebSocketDisconnect:
            logger.debug("Client disconnected normally")
        except Exception as e:
            logger.error(f"Streaming tasks error: {e}", exc_info=True)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected during setup")
    except Exception:
        logger.exception("WebSocket session error")
        try:
            await ws.send_json({"type": "error", "message": "Session setup failed"})
        except Exception:
            pass
    finally:
        # ==============================
        # Phase 4: Terminate Live API session
        # ==============================
        # Always close the queue, even if exceptions occurred (docs best practice)
        if live_request_queue is not None:
            logger.debug("Closing live_request_queue")
            live_request_queue.close()
        logger.info("WebSocket session ended")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    return app


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("LIVE_SERVER_PORT", "8080"))
    uvicorn.run(
        "live.server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )
