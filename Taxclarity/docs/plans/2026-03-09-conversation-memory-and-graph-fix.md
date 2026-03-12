# Conversation Memory And Graph Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the transparency atlas orphan-link crash and make live sessions remember prior conversation context across sessions.

**Architecture:** Correct graph event source linkage in the live orchestrator, defensively prune orphan links in the frontend reducer, and add a dedicated Spanner-backed conversation memory layer for turns and rolling summaries. Load remembered context into the Gemini Live system instruction at session start and surface the same context in the transparency atlas.

**Tech Stack:** FastAPI, Gemini Live API, Google Cloud Spanner, Next.js 16, React, react-force-graph-2d, Vitest, pytest.

---

### Task 1: Fix graph link integrity

**Files:**
- Modify: `X:\taxy\TaxAgent\backend\live_orchestrator.py`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\lib\transparency-graph.ts`
- Test: `X:\taxy\TaxAgent\tests\backend\test_live_orchestrator_graph_payload.py`
- Test: `X:\taxy\TaxAgent\frontend-next\src\lib\transparency-graph.spec.ts`

1. Add a regional source lookup when building citation graph events.
2. Drop links whose source or target node does not exist in the reducer.
3. Add tests covering `both` jurisdiction source links and orphan-link filtering.

### Task 2: Add conversation memory persistence

**Files:**
- Modify: `X:\taxy\TaxAgent\memory\spanner_graph.py`
- Test: `X:\taxy\TaxAgent\tests\backend\test_conversation_memory.py`

1. Add `ConversationTurns` and `ConversationSummaries` tables plus helper functions.
2. Add deterministic rolling summary generation from recent turns.
3. Add tests for summary generation and conversation context formatting helpers.

### Task 3: Load memory into live sessions

**Files:**
- Modify: `X:\taxy\TaxAgent\backend\websocket_server.py`
- Modify: `X:\taxy\TaxAgent\backend\memory_bank.py`

1. Load prior conversation context on session start.
2. Persist user and agent turns during live use.
3. Inject compact continuity context into the Gemini Live system prompt.

### Task 4: Surface remembered context in the atlas

**Files:**
- Modify: `X:\taxy\TaxAgent\frontend-next\src\types\index.ts`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\lib\ws-client.ts`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\hooks\use-transparency-graph.ts`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\hooks\use-voice-session.ts`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\lib\transparency-graph.ts`

1. Add a websocket event for loaded conversation memory context.
2. Render remembered topics, summary, and prior turn counts as memory nodes/timeline events.

### Task 5: Validate end to end

**Files:**
- Test: `X:\taxy\TaxAgent\tests\backend\test_live_orchestrator_graph_payload.py`
- Test: `X:\taxy\TaxAgent\tests\backend\test_conversation_memory.py`
- Test: `X:\taxy\TaxAgent\frontend-next\src\lib\transparency-graph.spec.ts`

1. Run focused backend tests.
2. Run Vitest reducer tests.
3. Run `npm run lint`.
4. Run `npm run build`.
