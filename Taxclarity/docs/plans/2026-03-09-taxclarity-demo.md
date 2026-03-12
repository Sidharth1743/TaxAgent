# TaxClarity Demo Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build one reliable TaxClarity demo flow across `frontend-next`, live websocket voice, A2A tax agents, citations, document upload, tax computation, and graph persistence.

**Architecture:** Keep `frontend-next` as the only demo UI and route all live query handling through a shared backend orchestration layer used by the websocket server and, if needed, the root agent adapter. Preserve real integrations with Gemini Live, A2A wrappers, PageIndex, and Spanner, while making payload normalization, contradiction detection, and persistence deterministic in code.

**Tech Stack:** Next.js 16, React 19, TypeScript, FastAPI, google-genai, Google ADK A2A wrappers, pytest, Spanner helpers, PageIndex helpers.

---

### Task 1: Create shared orchestration tests

**Files:**
- Create: `X:\taxy\TaxAgent\tests\backend\test_live_orchestrator.py`
- Modify: `X:\taxy\TaxAgent\backend\websocket_server.py`
- Modify: `X:\taxy\TaxAgent\agents\adk\geo_router\agent.py`

**Step 1: Write the failing test**

```python
import pytest

from backend.live_orchestrator import normalize_live_result


def test_normalize_live_result_builds_frontend_content_payload():
    raw = {
        "query": "tax saving options",
        "jurisdiction": "india",
        "delegation_results": {
            "india:http://localhost:8001": {
                "status": "success",
                "evidence": [
                    {
                        "title": "Section 80C",
                        "url": "https://example.com/80c",
                        "snippet": "80C allows deductions",
                        "date": "2026-02-01",
                        "reply_count": 3,
                        "source": "caclub",
                    }
                ],
            }
        },
    }

    payload = normalize_live_result(raw)

    assert payload["jurisdiction"] == "india"
    assert payload["claims"]
    assert payload["claims"][0]["citations"][0]["url"] == "https://example.com/80c"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_live_orchestrator.py::test_normalize_live_result_builds_frontend_content_payload -v`
Expected: FAIL with import error because `backend.live_orchestrator` does not exist.

**Step 3: Write minimal implementation**

Create a new backend orchestration module with:

```python
def normalize_live_result(raw: dict) -> dict:
    return {
        "query": raw["query"],
        "jurisdiction": raw["jurisdiction"],
        "sources": [],
        "claims": [],
        "contradictions": [],
        "synthesized_response": "",
    }
```

Then extend it until the test passes with structured citation objects.

**Step 4: Run test to verify it passes**

Run: `pytest tests/backend/test_live_orchestrator.py::test_normalize_live_result_builds_frontend_content_payload -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/backend/test_live_orchestrator.py backend/live_orchestrator.py
git commit -m "feat: add shared live orchestration module"
```

### Task 2: Unify live backend orchestration

**Files:**
- Create: `X:\taxy\TaxAgent\backend\live_orchestrator.py`
- Modify: `X:\taxy\TaxAgent\backend\websocket_server.py`
- Modify: `X:\taxy\TaxAgent\agents\adk\geo_router\agent.py`
- Modify: `X:\taxy\TaxAgent\agents\adk\root_agent\agent.py`
- Test: `X:\taxy\TaxAgent\tests\backend\test_websocket_server.py`
- Test: `X:\taxy\TaxAgent\tests\agents\test_geo_router.py`

**Step 1: Write the failing test**

Add tests that verify:

```python
@pytest.mark.asyncio
async def test_process_voice_query_returns_structured_content():
    result = await process_voice_query("How do I save tax in India?", user_id="u1", session_id="s1")
    assert "content" in result
    assert "jurisdiction" in result["content"]
```

and:

```python
def test_geo_router_extracts_task_text_consistently():
    payload = {"status": "success", "response_text": "{\"evidence\": []}"}
    assert extract_agent_text(payload) == "{\"evidence\": []}"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_websocket_server.py::test_process_voice_query_returns_structured_content tests/agents/test_geo_router.py::test_geo_router_extracts_task_text_consistently -v`
Expected: FAIL because current signatures and extraction helpers do not match.

**Step 3: Write minimal implementation**

Implement:

- a shared `run_live_query()` entrypoint in `backend/live_orchestrator.py`
- deterministic normalization of delegated agent responses
- a single response extraction helper shared by geo-router/root paths
- `process_voice_query()` passing through `user_id` and `session_id`
- websocket `content` events built from shared orchestrator output

**Step 4: Run test to verify it passes**

Run: `pytest tests/backend/test_websocket_server.py tests/agents/test_geo_router.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/live_orchestrator.py backend/websocket_server.py agents/adk/geo_router/agent.py agents/adk/root_agent/agent.py tests/backend/test_websocket_server.py tests/agents/test_geo_router.py
git commit -m "feat: unify live query orchestration"
```

### Task 3: Persist memory from live conversations

**Files:**
- Modify: `X:\taxy\TaxAgent\backend\live_orchestrator.py`
- Modify: `X:\taxy\TaxAgent\memory\spanner_graph.py`
- Modify: `X:\taxy\TaxAgent\backend\memory_bank.py`
- Test: `X:\taxy\TaxAgent\tests\memory\test_spanner_graph.py`
- Test: `X:\taxy\TaxAgent\tests\backend\test_integration.py`

**Step 1: Write the failing test**

Add a test asserting that successful live orchestration invokes persistence with `user_id` and `session_id`:

```python
@pytest.mark.asyncio
async def test_live_query_persists_memory_when_answer_generated():
    calls = []

    async def fake_persist(*args, **kwargs):
        calls.append(kwargs)

    result = await run_live_query(
        "What deductions can I claim?",
        user_id="user-1",
        session_id="session-1",
        persist_fn=fake_persist,
    )

    assert calls
    assert calls[0]["user_id"] == "user-1"
    assert calls[0]["session_id"] == "session-1"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_integration.py::test_live_query_persists_memory_when_answer_generated -v`
Expected: FAIL because live orchestration does not yet persist explicit session memory.

**Step 3: Write minimal implementation**

Update the live orchestrator so persistence happens in code after a successful structured result, and keep graceful no-config behavior when Spanner is unavailable.

**Step 4: Run test to verify it passes**

Run: `pytest tests/backend/test_integration.py::test_live_query_persists_memory_when_answer_generated tests/memory/test_spanner_graph.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/live_orchestrator.py backend/memory_bank.py memory/spanner_graph.py tests/backend/test_integration.py tests/memory/test_spanner_graph.py
git commit -m "feat: persist live conversation memory"
```

### Task 4: Complete document extraction, confirm, and compute flow

**Files:**
- Modify: `X:\taxy\TaxAgent\backend\graph_api.py`
- Modify: `X:\taxy\TaxAgent\backend\document_extractor.py`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\components\document-card.tsx`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\types\index.ts`
- Test: `X:\taxy\TaxAgent\tests\backend\test_graph_endpoints.py`
- Test: `X:\taxy\TaxAgent\tests\agents\test_calculation_agent.py`

**Step 1: Write the failing test**

Add a graph API test:

```python
def test_confirm_then_compute_returns_tax_summary(client):
    upload = client.post("/api/documents/upload", files={"file": ("form16.pdf", b"pdf", "application/pdf")})
    doc_id = upload.json()["doc_id"]

    client.post(f"/api/documents/{doc_id}/confirm", json={"user_id": "user-1"})
    compute = client.post(f"/api/documents/{doc_id}/compute", json={"additional_deductions": {"deductions_80c": 105000}})

    assert compute.status_code == 200
    assert "computation" in compute.json()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_graph_endpoints.py::test_confirm_then_compute_returns_tax_summary -v`
Expected: FAIL because the current frontend/document flow does not consistently model compute-ready data.

**Step 3: Write minimal implementation**

Make the Graph API and frontend use a stable confirmed-document model that includes:

- confirmed state
- optional compute result
- clear supported form behavior

Add UI actions on `DocumentCard` to trigger compute after confirm and render the returned calculation summary.

**Step 4: Run test to verify it passes**

Run: `pytest tests/backend/test_graph_endpoints.py tests/agents/test_calculation_agent.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/graph_api.py backend/document_extractor.py frontend-next/src/components/document-card.tsx frontend-next/src/types/index.ts tests/backend/test_graph_endpoints.py tests/agents/test_calculation_agent.py
git commit -m "feat: add visible document compute flow"
```

### Task 5: Finish frontend session and transcript state machine

**Files:**
- Modify: `X:\taxy\TaxAgent\frontend-next\src\hooks\use-voice-session.ts`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\lib\ws-client.ts`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\components\voice-shell.tsx`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\components\chat-panel.tsx`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\components\voice-orb.tsx`

**Step 1: Write the failing test**

Create frontend-oriented logic tests or hook tests asserting:

```typescript
it("enters thinking state when server sends thinking", () => {
  // mount hook
  // emit websocket thinking event
  // expect orbState toBe("thinking")
})
```

and:

```typescript
it("adds user transcript entry before sending text turn", () => {
  // call sendTextTurn("hello")
  // expect transcript[0].role === "user"
})
```

**Step 2: Run test to verify it fails**

Run: `npm test` or the project’s chosen frontend test command after adding the test harness.
Expected: FAIL because the current hook never sets `thinking` and does not append user turns.

**Step 3: Write minimal implementation**

Update session state so:

- websocket `thinking` drives orb state
- websocket `content` updates source surfaces consistently
- typed or explicit text turns append user transcript entries
- mobile source panel also receives contradictions
- text-only mode no longer forces microphone acquisition

**Step 4: Run test to verify it passes**

Run: `npm run lint`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend-next/src/hooks/use-voice-session.ts frontend-next/src/lib/ws-client.ts frontend-next/src/components/voice-shell.tsx frontend-next/src/components/chat-panel.tsx frontend-next/src/components/voice-orb.tsx
git commit -m "feat: complete live frontend session states"
```

### Task 6: Revamp the visible TaxClarity UI

**Files:**
- Modify: `X:\taxy\TaxAgent\frontend-next\src\app\globals.css`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\components\voice-shell.tsx`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\components\source-panel.tsx`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\components\source-card.tsx`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\components\graph-panel.tsx`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\components\document-card.tsx`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\components\settings-dialog.tsx`

**Step 1: Write the failing test**

Add manual acceptance checkpoints rather than automated pixel tests:

- orb state is obvious
- camera preview is visible during active sessions
- sources and contradictions are visible
- graph and document surfaces feel integrated
- desktop and mobile layouts both expose core features

**Step 2: Run test to verify it fails**

Run: `npm run dev`
Expected: current UI feels sparse and hides too much state.

**Step 3: Write minimal implementation**

Refine the shell into a more explicit product surface:

- stronger visual framing and layout hierarchy
- visible session, camera, and evidence status
- clearer source and graph affordances
- visible compute/document outputs
- mobile-safe overlays and panels

**Step 4: Run test to verify it passes**

Run: `npm run lint`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend-next/src/app/globals.css frontend-next/src/components/voice-shell.tsx frontend-next/src/components/source-panel.tsx frontend-next/src/components/source-card.tsx frontend-next/src/components/graph-panel.tsx frontend-next/src/components/document-card.tsx frontend-next/src/components/settings-dialog.tsx
git commit -m "feat: revamp taxclarity demo interface"
```

### Task 7: Fix proxy and runtime configuration

**Files:**
- Modify: `X:\taxy\TaxAgent\nginx.conf`
- Modify: `X:\taxy\TaxAgent\Dockerfile`
- Modify: `X:\taxy\TaxAgent\run.ps1`
- Modify: `X:\taxy\TaxAgent\start_servers.ps1`
- Modify: `X:\taxy\TaxAgent\frontend-next\.env.local`
- Modify: `X:\taxy\TaxAgent\frontend-next\README.md`

**Step 1: Write the failing test**

Add configuration checks or smoke tests asserting:

```python
def test_nginx_proxies_document_endpoints():
    text = Path("nginx.conf").read_text()
    assert "/api/documents/" in text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_proxy_config.py -v`
Expected: FAIL because `/api/documents/*` is not proxied today.

**Step 3: Write minimal implementation**

Update the runtime so:

- nginx proxies `/api/documents/*`
- the chosen shipped frontend is `frontend-next`
- frontend URLs are env-driven and proxy-safe
- local launch scripts start the same primary stack

**Step 4: Run test to verify it passes**

Run: `pytest tests/backend/test_proxy_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add nginx.conf Dockerfile run.ps1 start_servers.ps1 frontend-next/.env.local frontend-next/README.md
git commit -m "fix: align runtime and proxy configuration"
```

### Task 8: Full regression and demo verification

**Files:**
- Modify: `X:\taxy\TaxAgent\tests\backend\test_websocket_server.py`
- Modify: `X:\taxy\TaxAgent\tests\backend\test_integration.py`
- Modify: `X:\taxy\TaxAgent\tests\e2e\test_voice_conversation.py`
- Modify: `X:\taxy\TaxAgent\README.md`

**Step 1: Write the failing test**

Add an integration test covering:

```python
def test_end_to_end_demo_payload_contains_claims_and_sources():
    # mock live dependencies
    # run websocket/orchestrator path
    # assert claims, citations, and jurisdiction are present
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/backend/test_integration.py tests/e2e/test_voice_conversation.py -v`
Expected: FAIL until the unified flow is wired.

**Step 3: Write minimal implementation**

Bring tests in line with the real websocket server API and document the final runbook in `README.md`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/agents tests/backend tests/memory -v`
Expected: PASS except any explicitly quarantined live-manual tests.

**Step 5: Commit**

```bash
git add tests/backend/test_websocket_server.py tests/backend/test_integration.py tests/e2e/test_voice_conversation.py README.md
git commit -m "test: verify taxclarity demo integration"
```
