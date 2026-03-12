# Voice, Vision & Geo Router Implementation Design

> **For Claude:** This design precedes the implementation plan.

**Goal:** Add real-time voice conversation, live webcam vision, and geographic tax routing to TaxAgent

**Architecture:** Monolithic FastAPI backend with WebSocket proxy to Gemini Live API. React frontend using Google's multimodal-live-api-web-console boilerplate. Geo Router using ADK LlmAgent with A2A protocol and Agent Cards.

**Tech Stack:** Python (FastAPI, google-genai, google-adk), React + Vite, WebSocket, A2A Protocol

---

## 1. Voice Architecture (WebSocket + Gemini Live)

### Frontend (React)
- Clone `google-gemini/multimodal-live-api-web-console` to `frontend/`
- Use built-in AudioWorklet for 16-bit PCM audio at 16kHz
- WebSocket connects to `ws://localhost:8001/ws` (not directly to Google)

### Backend (FastAPI)
- New endpoint: `ws://localhost:8001/ws`
- Proxy receives base64 audio chunks → forwards to Gemini Live via `aio.live.connect`
- Handle VAD interruption signals from Gemini Live
- Stream responses back to frontend

### Integration Point
- Modify existing `agents/adk/root_agent/agent.py` to support WebSocket mode
- Create new `backend/websocket_server.py` for voice proxy

---

## 2. Vision Architecture

### Live Camera Pipeline (Webcam)
- React boilerplate already has `getUserMedia` and 1 FPS throttling
- Base64 JPEG frames sent over same WebSocket as audio
- Gemini Live processes frames as part of multimodal conversation

### Document Pipeline (PDFs) - DEFERRED
- Requires Google Cloud Document AI setup
- Route to specialized parsers (Form 16, W-2, 1099 series)
- Not in MVP scope

---

## 3. Geo Router Architecture

### ADK LlmAgent as Router
- Create new `agents/adk/geo_router/agent.py`
- System instruction: "Determine user's tax jurisdiction and delegate to appropriate cluster"

### Agent Cards (A2A Discovery)
- Each agent hosts `/.well-known/agent.json`
- Example card structure:
```json
{
  "name": "India Tax Agent",
  "description": "Indian tax compliance (Section 44ADA, 80C, Form 16)",
  "jurisdiction": "india",
  "capabilities": ["income_tax", "gst", "tds"]
}
```

### Execution Flow
1. User query → Geo Router LlmAgent
2. Agent reads `.well-known/agent.json` from each cluster
3. Generates Task ID, delegates via A2A HTTP
4. India Cluster (TaxTMI agent) handles Indian tax logic
5. USA Cluster (CAClub agent) handles US tax logic
6. Geo Router synthesizes final answer

---

## 4. Data Flow

```
[React UI] --WebSocket--> [FastAPI Voice Proxy] --aio.live.connect--> [Gemini Live API]
                                    |
                                    v
                            [ADK Geo Router]
                                    |
                    -----------------+-----------------
                    |                                   |
              [India Cluster]                     [USA Cluster]
            (TaxTMI Agent)                     (CAClub Agent)
```

---

## 5. File Changes Summary

| Component | Files |
|-----------|-------|
| Frontend | Clone to `frontend/` |
| Voice Proxy | Create `backend/websocket_server.py` |
| Geo Router | Create `agents/adk/geo_router/agent.py` |
| Agent Cards | Create `.well-known/agent.json` per agent |
| Integration | Modify `agents/adk/root_agent/agent.py` |

---

## 6. Deferred Items

- Google Cloud Document AI setup (PDF parsing)
- Production deployment (Docker, CI/CD)
- Authentication/authorization
- Session persistence
