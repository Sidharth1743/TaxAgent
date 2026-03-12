# TaxClarity Demo Integration Design

**Date:** 2026-03-09

**Objective:** unify the current fragmented frontend, websocket, routing, agent, document, and graph flows into one reliable live TaxClarity demo centered on `frontend-next` and the real backend services.

## Current State

The codebase contains the right building blocks but they are split across incompatible execution paths:

- `frontend-next` is the only frontend that already contains the intended TaxClarity surfaces: disclaimer, voice orb, chat rail, source cards, contradiction cards, graph panel, and document upload.
- `backend.websocket_server` is the real live-session entrypoint, but it currently performs orchestration inline and depends on weak geo-router payload assumptions.
- `agents/adk/geo_router/agent.py`, `agents/adk/root_agent/agent.py`, and `orchestrator/a2a_orchestrator.py` each implement overlapping parts of routing, synthesis, and evidence handling.
- Graph, document extraction, PageIndex, and tax computation exist, but they are not coherently connected into one visible user flow.

The result is that individual components work in isolation, but the end-to-end demo breaks when voice, citations, graph persistence, and document flows are exercised together.

## Product Target

The demo should support this visible flow inside `frontend-next`:

1. User lands on `/` and sees a polished TaxClarity UI with disclaimer gating.
2. Voice session starts with persistent `user_id` and per-session `session_id`.
3. Gemini Live receives audio/video and can answer with voice while the app shows listening, thinking, and speaking states.
4. Tax queries trigger real jurisdiction routing and real A2A delegation to source agents.
5. Deterministic evidence normalization produces claims, citations, contradictions, and jurisdiction badges for the source panel.
6. Document upload extracts fields, allows confirmation, persists graph state, and makes tax computation visible in the UI.
7. The graph panel and insights refresh from the same stored user context.
8. Returning sessions use persisted memory context when available.

## Recommended Architecture

Use one canonical orchestration spine for all live demo behavior:

`frontend-next` -> `backend.websocket_server` -> shared live orchestrator -> geo classification -> A2A source agents -> deterministic synthesis -> contradiction detection -> memory persistence -> websocket events -> frontend

This means:

- `frontend-next` becomes the only supported demo UI.
- `backend.websocket_server` remains the primary runtime entrypoint for live voice.
- `agents/adk/geo_router/agent.py` becomes a routing and delegation helper, not the place where final UI payloads are assembled.
- shared orchestration code replaces the duplicated logic now split across the CLI orchestrator, root agent, and websocket server.
- `agents/adk/root_agent/agent.py` either wraps the shared orchestrator or is treated as a secondary adapter, not the authoritative logic path.

## Backend Design

### Shared orchestration module

Create a backend module that performs:

- jurisdiction classification
- source fan-out selection
- A2A delegation using one consistent client path
- evidence normalization into a stable schema
- confidence scoring
- contradiction detection
- final synthesized response generation
- memory extraction and persistence

The old deterministic merge behavior in `orchestrator/a2a_orchestrator.py` should be converted into reusable library functions rather than left as a separate subprocess-oriented workflow.

### WebSocket flow

`backend.websocket_server` should:

- keep Gemini Live session management, audio/video forwarding, and reconnect handling
- pass `user_id`, `session_id`, and the transcribed query into the shared orchestrator
- emit explicit websocket events for:
  - `connected`
  - `thinking`
  - `text`
  - `audio`
  - `content`
  - `turnComplete`
  - `error`
- stop assembling citation payloads directly from raw geo-router return data

### Geo-router

`agents/adk/geo_router/agent.py` should:

- keep real LLM classification with keyword fallback
- keep real delegation to India and US clusters
- stop being responsible for final response synthesis for the frontend
- use one A2A response extraction path that matches the live wrappers and root agent assumptions

### Memory and graph

Conversation memory must become explicit code, not a prompt instruction:

- pass `user_id` and `session_id` through orchestration calls
- persist query-derived memory after successful evidence synthesis
- continue using Spanner where configured
- continue using PageIndex as cache-first and document-reasoning support
- make graph refresh reflect new stored memory and confirmed documents

### Document and compute

The document path should become a first-class demo feature:

- upload -> extract -> review/edit -> confirm -> graph persist
- add visible compute support from confirmed extracted data
- make the compute result available in the frontend as a structured card/panel
- keep the deterministic calculator in `agents/calculation_agent.py`

## Frontend Design

### Primary shell

Retain `frontend-next/src/components/voice-shell.tsx` as the root experience, but upgrade it into a richer single-screen workspace:

- left: conversation history and optional text input
- center: voice orb, camera preview, live status, and compute/document surfaces
- right: source evidence, contradictions, and graph toggle affordances

### Voice states

The orb state machine must fully represent:

- `idle`
- `listening`
- `thinking`
- `speaking`

These states should be driven by real websocket events instead of inferred only from incoming audio.

### Trust surfaces

Source visibility is central to the demo:

- source cards must always render consistent claim, citation, date, and confidence data
- contradiction cards must appear on both desktop and mobile
- jurisdiction badges should reflect India, USA, or cross-border outcomes
- graph and insight panels should feel connected to the current conversation, not like detached admin screens

### Camera and vision

The UI must make the camera flow obvious:

- show camera preview during active sessions
- expose visible camera status so the user knows frames are being sent
- present camera as a supported live input, while still keeping upload as the precise extraction path

This does not require fake OCR from the camera stream. The live demo should truthfully communicate that the model can see the feed during conversation, while upload remains the structured extraction path.

### Text fallback

The frontend should support text turns in addition to voice:

- append user messages explicitly to the transcript
- support typed questions when mic or live voice is unstable
- avoid a “Text Only” setting that still secretly requires microphone access

## Deployment and Runtime Design

The demo should behave consistently in local development and proxied/container deployment:

- stop hardcoding `localhost` where same-origin or env-based URLs are needed
- expose `/api/documents/*` alongside graph endpoints through `nginx.conf`
- align Docker and startup scripts to the chosen frontend and backend services
- remove or clearly demote legacy frontends from the active demo path

## Testing Strategy

Tests should focus on the seams that are currently breaking:

- websocket event sequencing and `thinking` state transitions
- orchestration normalization from delegated A2A results into frontend `content` payloads
- contradiction extraction with multiple sources
- document upload, confirm, and compute endpoint flow
- graph refresh after confirmed documents and persisted memory
- configuration and proxy path expectations

Unit tests should cover normalization and orchestration helpers. Integration tests should cover websocket and graph/document endpoints with mocks around external services.

## Non-Goals

This pass should not attempt:

- a fake offline demo mode
- a second frontend kept in parity with `frontend-next`
- full production-grade observability or auth
- speculative new product features unrelated to the stated TaxClarity flow

## Acceptance Criteria

The design is successful when:

- one local run path reliably starts the frontend and all live backend services
- the frontend visibly exposes disclaimer, voice, camera, sources, contradictions, graph, upload, and compute surfaces
- live tax queries return structured claims and citations from real source agents
- uploaded documents can be confirmed and then used for computation and graph updates
- session context is persisted and visible on return where infrastructure is configured
- failures surface clearly without silently degrading into broken or misleading UI
