# Transparency Graph Design

## Goal

Turn the current memory graph into a transparency surface that shows where TaxClarity is looking, which agents it routes to, what evidence it finds, where contradictions appear, and what gets persisted into long-term memory.

## Problem

The current graph panel only visualizes persisted Spanner memory. That creates two product problems:

1. It looks empty until a document is uploaded or a memory write succeeds.
2. It does not explain the live workflow, so the system still feels like a black box.

The user wants the graph to visualize the live routing, source lookup, evidence gathering, contradiction checks, storage handoff, and final memory relationships.

## Constraints

- Do not expose chain-of-thought or hidden model reasoning.
- Show observable workflow only.
- Keep persisted knowledge in Spanner; do not overload Spanner with transient execution-state.
- Work even when Graph API, Document AI, or Spanner are unavailable.
- Preserve the current live voice flow as the primary interaction path.

## Approaches

### 1. Hybrid Live + Memory Graph

Build a transient live graph in the frontend from websocket events and merge it with the persisted memory graph fetched from Graph API.

Pros:
- Works before any data is persisted.
- Directly visualizes current workflow.
- Minimal backend refactor compared to a new graph service.

Cons:
- Requires a frontend graph-state engine.
- Needs enriched live payloads from the backend.

### 2. Backend-Owned Transparency Graph

Move both transient and persisted graph assembly to backend services and stream a canonical graph model to the frontend.

Pros:
- Cleanest long-term architecture.
- One graph contract.

Cons:
- More backend scope than needed right now.
- Slower path to a usable demo.

### 3. Frontend-Only Derived Graph

Infer graph state only from existing transcript and routing payloads without expanding contracts.

Pros:
- Fastest initial build.

Cons:
- Too brittle.
- Not trustworthy enough for transparency.
- Hard to keep aligned with persistence and source status.

## Recommendation

Use the hybrid live + memory graph approach.

It gives the user live visibility immediately, reuses the existing persisted graph API, and keeps transient workflow state out of Spanner.

## Product Behavior

The graph panel becomes a "Transparency Atlas" with three conceptual lanes:

- Observe
  - Camera
  - User query
  - Active session
  - Jurisdiction routing
- Verify
  - Source agents
  - Evidence nodes
  - Citations
  - Contradictions
  - Confidence signals
- Remember
  - Persisted user node
  - Sessions
  - Queries
  - Concepts
  - Tax entities
  - Tax forms
  - Insights

During a live turn:

1. The query node appears.
2. The jurisdiction node activates.
3. Source agent nodes pulse while fetching.
4. Evidence and citation nodes animate outward from successful sources.
5. Contradiction links flash amber where relevant.
6. Persisted nodes settle into a stable memory cluster after confirmed storage.

The panel should remain useful even when persistence is unavailable. In that case it still shows the live flow, with the memory lane marked unavailable or empty.

## Data Model

### Persistent Graph

Continue using:

- `GET /api/graph/{user_id}`
- `GET /api/graph/{user_id}/insights`

This layer remains the source of truth for long-term knowledge.

### Live Transparency Graph

Build a transient graph from websocket events and routing payloads.

Node types:

- `session`
- `camera`
- `query`
- `jurisdiction`
- `source_agent`
- `claim`
- `citation`
- `contradiction`
- `document`
- `insight`

Edge types:

- `observes`
- `routes_to`
- `queries`
- `supports`
- `conflicts_with`
- `persists_to`
- `suggests`

Merge rules:

- Live nodes are vivid and animated.
- Memory nodes are calmer and denser.
- When a live node later appears in persisted memory, it transitions from active state to stable state.

## UI Design

The graph drawer becomes a full-height cinematic panel with:

1. Graph hero canvas
   - Staggered node reveals
   - Active halos on source agents
   - Dotted signal lines from query to routing to sources
   - Confidence heat on evidence nodes
   - Amber conflict edges for contradictions

2. Timeline strip
   - Human-readable workflow events
   - Example:
     - Listening to camera feed
     - Routing to India sources
     - TaxTMI returned 2 results
     - CAClub returned no evidence
     - Persisted Section 80C to memory

3. Mode switch
   - `Live Flow`
   - `Memory`
   - `Combined`

4. Better empty and degraded states
   - Before first query: guided sample topology
   - Graph API unavailable: show live flow only
   - No insights yet: explain why and what triggers them

## Backend Changes

Extend the live orchestration payload with graph-friendly metadata:

- source statuses
- evidence counts
- contradiction topics
- graph event labels
- persistence-confirmation events

Do not emit chain-of-thought. Emit only observable execution events.

The Graph API can stay mostly unchanged for phase one, but should eventually support richer metadata if persisted graph presentation needs stronger labels or node grouping.

## Frontend Changes

Add a graph-state engine that:

- ingests websocket events
- builds transient nodes and edges
- merges persisted graph data on fetch
- supports `live`, `memory`, and `combined` modes
- exposes a timeline of workflow events

Redesign the graph panel around that state engine rather than binding directly to raw fetch responses.

## Testing

Backend:

- verify live routing payloads include graph event metadata
- verify source failures produce explicit graph status nodes

Frontend:

- reducer tests for live graph state assembly
- tests for mode switching
- tests for empty/degraded states
- tests for persistence handoff transitions where feasible

## Success Criteria

- The graph is meaningful before document upload.
- Users can see which sources are being queried in real time.
- Users can see what evidence and contradictions influenced the answer.
- Persisted memory appears as part of the same story, not a separate empty panel.
- The panel remains useful when Graph API or Spanner is unavailable.
