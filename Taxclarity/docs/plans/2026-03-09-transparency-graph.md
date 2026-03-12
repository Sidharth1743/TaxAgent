# Transparency Graph Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a transparency-first graph panel that visualizes the live routing and evidence workflow alongside persisted memory so users can see what TaxClarity is looking at in real time.

**Architecture:** Keep the persisted graph in `backend.graph_api` and `memory.spanner_graph`, but add a frontend graph-state engine that merges that memory graph with transient websocket-driven workflow nodes. Enrich live backend payloads with graph event metadata, then render three modes in the panel: live flow, memory, and combined.

**Tech Stack:** FastAPI, Python, Next.js 16, React 19, TypeScript, Motion, react-force-graph-2d, pytest, eslint, next build

---

### Task 1: Define Graph Contracts

**Files:**
- Modify: `X:\taxy\TaxAgent\frontend-next\src\types\index.ts`
- Modify: `X:\taxy\TaxAgent\backend\live_orchestrator.py`
- Test: `X:\taxy\TaxAgent\tests\backend\test_live_orchestrator_graph_payload.py`

**Step 1: Write the failing test**

```python
import pytest


@pytest.mark.asyncio
async def test_live_query_content_includes_graph_events(monkeypatch):
    from backend.live_orchestrator import run_live_query

    async def fake_classifier(_query):
        return {"jurisdiction": "india", "confidence": 0.9}

    async def fake_call(_url, _query):
        return {
            "status": "success",
            "text": '{"source":"taxtmi","evidence":[{"title":"Section 80C","url":"https://example.com","snippet":"Deduction available","date":"2026-03-01","reply_count":3}]}',
        }

    monkeypatch.setattr("backend.live_orchestrator._classify_jurisdiction", fake_classifier)
    monkeypatch.setattr("backend.live_orchestrator._call_a2a_agent", fake_call)
    monkeypatch.setattr("backend.live_orchestrator._load_memory_context", lambda *_args, **_kwargs: {"prior_resolutions": [], "unresolved_queries": []})
    monkeypatch.setattr("backend.live_orchestrator._persist_memory", lambda *_args, **_kwargs: None)

    result = await run_live_query("What can I claim under 80C?", "user-1", "session-1")

    assert "graph_events" in result["content"]
    assert any(event["kind"] == "source_agent" for event in result["content"]["graph_events"])
    assert any(event["kind"] == "claim" for event in result["content"]["graph_events"])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests\backend\test_live_orchestrator_graph_payload.py -v`

Expected: FAIL because `graph_events` does not exist yet.

**Step 3: Write minimal implementation**

Add graph event builders in `backend/live_orchestrator.py` that emit:

```python
{
    "id": "source:india:taxtmi",
    "kind": "source_agent",
    "label": "TaxTMI",
    "status": "success",
    "region": "india",
}
```

and:

```python
{
    "id": "claim:0",
    "kind": "claim",
    "label": "Section 80C - Deduction available",
    "confidence": 0.8,
}
```

Include `graph_events` and a small `graph_summary` block in the returned `content`.

Update `frontend-next/src/types/index.ts` so `RoutingResult` understands:

```ts
export interface GraphEvent {
  id: string;
  kind: string;
  label: string;
  status?: string;
  region?: string;
  confidence?: number;
  parentId?: string;
}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests\backend\test_live_orchestrator_graph_payload.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/backend/test_live_orchestrator_graph_payload.py backend/live_orchestrator.py frontend-next/src/types/index.ts
git commit -m "feat: add transparency graph event payloads"
```

### Task 2: Build Frontend Graph State Engine

**Files:**
- Create: `X:\taxy\TaxAgent\frontend-next\src\lib\transparency-graph.ts`
- Create: `X:\taxy\TaxAgent\frontend-next\src\hooks\use-transparency-graph.ts`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\hooks\use-voice-session.ts`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\types\index.ts`
- Test: `X:\taxy\TaxAgent\frontend-next\src\lib\transparency-graph.spec.ts`
- Modify: `X:\taxy\TaxAgent\frontend-next\package.json`

**Step 1: Write the failing test**

Use a pure reducer-style test:

```ts
import { describe, expect, it } from "vitest";
import { reduceGraphState } from "./transparency-graph";

describe("reduceGraphState", () => {
  it("adds live query, source agent, and claim nodes from routing payload", () => {
    const next = reduceGraphState(
      undefined,
      {
        type: "routing_result",
        payload: {
          query: "What is 80C?",
          jurisdiction: "india",
          claims: [{ claim: "80C available", citations: [], confidence: 0.8 }],
          sources: ["TaxTMI"],
          graph_events: [
            { id: "query:1", kind: "query", label: "What is 80C?" },
            { id: "source:taxtmi", kind: "source_agent", label: "TaxTMI", status: "success" },
          ],
        },
      },
    );

    expect(next.live.nodes.some((node) => node.id === "query:1")).toBe(true);
    expect(next.live.nodes.some((node) => node.id === "source:taxtmi")).toBe(true);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx vitest run frontend-next/src/lib/transparency-graph.spec.ts`

Expected: FAIL because reducer and test tooling do not exist yet.

**Step 3: Write minimal implementation**

Add `vitest` as a dev dependency and create a reducer that accepts actions such as:

```ts
type GraphAction =
  | { type: "session_started"; payload: { sessionId: string } }
  | { type: "routing_result"; payload: RoutingResult }
  | { type: "memory_loaded"; payload: GraphData }
  | { type: "document_confirmed"; payload: { docId: string; stored: boolean } };
```

The state shape should be:

```ts
interface TransparencyGraphState {
  live: GraphData;
  memory: GraphData;
  combined: GraphData;
  timeline: GraphTimelineEvent[];
}
```

Update `use-voice-session.ts` to dispatch graph actions whenever:
- session connects
- camera becomes active
- content payload arrives
- document confirm succeeds

**Step 4: Run test to verify it passes**

Run:
- `npx vitest run frontend-next/src/lib/transparency-graph.spec.ts`
- `npm run lint`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend-next/package.json frontend-next/src/lib/transparency-graph.ts frontend-next/src/lib/transparency-graph.spec.ts frontend-next/src/hooks/use-transparency-graph.ts frontend-next/src/hooks/use-voice-session.ts frontend-next/src/types/index.ts
git commit -m "feat: add transparency graph state engine"
```

### Task 3: Redesign The Graph Panel

**Files:**
- Modify: `X:\taxy\TaxAgent\frontend-next\src\components\graph-panel.tsx`
- Create: `X:\taxy\TaxAgent\frontend-next\src\components\graph-mode-switch.tsx`
- Create: `X:\taxy\TaxAgent\frontend-next\src\components\graph-timeline.tsx`
- Create: `X:\taxy\TaxAgent\frontend-next\src\components\graph-legend.tsx`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\components\voice-shell.tsx`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\app\globals.css`

**Step 1: Write the failing test**

If UI tests are not yet available, write a minimal reducer-driven smoke assertion and use lint/build as the acceptance gate. Document the missing UI test framework inside the commit message and keep the rendering logic split into small components to preserve testability later.

Create a simple render contract snapshot test if you add React Testing Library. Otherwise use:

```ts
import { describe, expect, it } from "vitest";
import { getGraphModeLabel } from "./graph-mode-switch";

describe("graph mode labels", () => {
  it("returns a label for combined mode", () => {
    expect(getGraphModeLabel("combined")).toBe("Combined");
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx vitest run frontend-next/src/components/graph-mode-switch.spec.ts`

Expected: FAIL because the component helper does not exist yet.

**Step 3: Write minimal implementation**

Redesign the panel into:
- top canvas with richer `ForceGraph2D` node drawing
- mode switch for `live`, `memory`, `combined`
- timeline section for workflow events
- legend and trust copy
- improved empty/degraded states

Use a clear visual system:

```ts
const NODE_STYLES = {
  query: { color: "#7dd3fc", ring: "#38bdf8" },
  source_agent: { color: "#34d399", ring: "#10b981" },
  citation: { color: "#f59e0b", ring: "#fbbf24" },
  contradiction: { color: "#fb7185", ring: "#f43f5e" },
  memory: { color: "#c4b5fd", ring: "#8b5cf6" },
};
```

Use Motion for staggered section reveals and timeline entry animation. Keep the panel functional on desktop and mobile widths.

**Step 4: Run test to verify it passes**

Run:
- `npx vitest run frontend-next/src/components/graph-mode-switch.spec.ts`
- `npm run lint`
- `npm run build`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend-next/src/components/graph-panel.tsx frontend-next/src/components/graph-mode-switch.tsx frontend-next/src/components/graph-timeline.tsx frontend-next/src/components/graph-legend.tsx frontend-next/src/components/voice-shell.tsx frontend-next/src/app/globals.css
git commit -m "feat: redesign transparency graph panel"
```

### Task 4: Connect Memory Persistence Handoff

**Files:**
- Modify: `X:\taxy\TaxAgent\frontend-next\src\hooks\use-voice-session.ts`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\hooks\use-transparency-graph.ts`
- Modify: `X:\taxy\TaxAgent\frontend-next\src\components\document-card.tsx`
- Modify: `X:\taxy\TaxAgent\backend\graph_api.py`
- Test: `X:\taxy\TaxAgent\tests\backend\test_graph_api_document_confirm.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient
from backend.graph_api import app


def test_confirm_document_returns_spanner_storage_flag(monkeypatch):
    client = TestClient(app)

    # Seed in-memory document store in the module under test before POST
    # and patch store_document_data to return known identifiers.

    response = client.post(
        "/api/documents/doc-1/confirm",
        json={"user_id": "user-1", "corrections": {}},
    )

    assert response.status_code == 200
    assert "spanner_stored" in response.json()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests\backend\test_graph_api_document_confirm.py -v`

Expected: FAIL if the seeded confirm flow is not testable or the return shape is incomplete.

**Step 3: Write minimal implementation**

When confirm succeeds:
- emit a frontend graph action that marks the document node as persisted
- animate it into the memory cluster
- refresh persisted graph data

Keep the handoff truthful:

```ts
dispatch({
  type: "document_confirmed",
  payload: { docId: response.doc_id, stored: response.spanner_stored },
});
```

**Step 4: Run test to verify it passes**

Run:
- `pytest tests\backend\test_graph_api_document_confirm.py -v`
- `npm run lint`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/backend/test_graph_api_document_confirm.py backend/graph_api.py frontend-next/src/hooks/use-voice-session.ts frontend-next/src/hooks/use-transparency-graph.ts frontend-next/src/components/document-card.tsx
git commit -m "feat: animate transparency graph persistence handoff"
```

### Task 5: Final Integration Verification

**Files:**
- Modify if needed: `X:\taxy\TaxAgent\frontend-next\src\components\graph-panel.tsx`
- Modify if needed: `X:\taxy\TaxAgent\frontend-next\src\hooks\use-transparency-graph.ts`
- Test: `X:\taxy\TaxAgent\tests\backend\test_live_orchestrator_graph_payload.py`
- Test: `X:\taxy\TaxAgent\tests\backend\test_graph_api_document_confirm.py`
- Test: `X:\taxy\TaxAgent\frontend-next\src\lib\transparency-graph.spec.ts`

**Step 1: Run focused verification**

Run:

```bash
pytest tests/backend/test_live_orchestrator_graph_payload.py tests/backend/test_graph_api_document_confirm.py -q
npx vitest run frontend-next/src/lib/transparency-graph.spec.ts frontend-next/src/components/graph-mode-switch.spec.ts
cd frontend-next && npm run lint && npm run build
```

Expected:
- backend graph payload tests pass
- reducer/UI helper tests pass
- frontend lint/build pass

**Step 2: Manual smoke test**

1. Start `:8001`, `:8002`, `:8003`, and `:8006`
2. Open `http://localhost:3000`
3. Start a session
4. Ask an India query
5. Open graph panel
6. Verify:
   - `Live Flow` shows query -> jurisdiction -> source agents -> evidence
   - `Memory` shows persisted graph when available
   - `Combined` merges both
   - timeline explains source hits/misses and persistence

**Step 3: Final commit**

```bash
git add tests/backend/test_live_orchestrator_graph_payload.py tests/backend/test_graph_api_document_confirm.py frontend-next/src/lib/transparency-graph.spec.ts frontend-next/src/components/graph-mode-switch.spec.ts frontend-next/src/components/graph-panel.tsx frontend-next/src/hooks/use-transparency-graph.ts
git commit -m "feat: add transparency-first graph visualization"
```
