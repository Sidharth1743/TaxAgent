import type {
  ConversationMemoryContext,
  GraphEvent,
  PersistedGraphData,
  RoutingResult,
  TransparencyGraphDataset,
  TransparencyGraphLink,
  TransparencyGraphNode,
  TransparencyGraphState,
  TransparencyTimelineEvent,
} from "@/types";

export type GraphAction =
  | { type: "session_started"; payload: { sessionId: string } }
  | { type: "camera_updated"; payload: { active: boolean; message?: string } }
  | { type: "conversation_memory_loaded"; payload: ConversationMemoryContext }
  | { type: "routing_result"; payload: RoutingResult }
  | { type: "memory_loading" }
  | { type: "memory_loaded"; payload: PersistedGraphData }
  | { type: "memory_load_failed"; payload: { error: string } }
  | { type: "document_confirmed"; payload: { docId: string; stored: boolean } };

const NODE_COLORS: Record<string, string> = {
  session: "#2dd4bf",
  camera: "#38bdf8",
  query: "#7dd3fc",
  jurisdiction: "#34d399",
  source_agent: "#10b981",
  claim: "#f59e0b",
  citation: "#fbbf24",
  contradiction: "#fb7185",
  document: "#c084fc",
  insight: "#22c55e",
  memory: "#a78bfa",
};

function nowIso(): string {
  return new Date().toISOString();
}

function emptyDataset(): TransparencyGraphDataset {
  return { nodes: [], links: [] };
}

export function createInitialTransparencyGraphState(): TransparencyGraphState {
  return {
    live: emptyDataset(),
    memory: emptyDataset(),
    combined: emptyDataset(),
    timeline: [],
    memoryStatus: "idle",
    memoryError: null,
  };
}

function pushTimeline(
  timeline: TransparencyTimelineEvent[],
  event: Omit<TransparencyTimelineEvent, "id" | "createdAt">,
): TransparencyTimelineEvent[] {
  const createdAt = nowIso();
  const duplicateCount = timeline.filter(
    (item) =>
      item.label === event.label &&
      item.detail === event.detail &&
      item.tone === event.tone,
  ).length;
  const next = [
    {
      id: `${createdAt}:${event.tone}:${duplicateCount}:${event.label}:${event.detail ?? ""}`,
      createdAt,
      ...event,
    },
    ...timeline,
  ];
  return next.slice(0, 24);
}

function upsertNode(nodes: TransparencyGraphNode[], node: TransparencyGraphNode): TransparencyGraphNode[] {
  const index = nodes.findIndex((item) => item.id === node.id);
  if (index === -1) {
    return [...nodes, node];
  }

  const next = [...nodes];
  next[index] = { ...next[index], ...node, meta: { ...next[index].meta, ...node.meta } };
  return next;
}

function upsertLink(links: TransparencyGraphLink[], link: TransparencyGraphLink): TransparencyGraphLink[] {
  const exists = links.some(
    (item) => item.source === link.source && item.target === link.target && item.type === link.type,
  );
  return exists ? links : [...links, link];
}

function mergeDatasets(...datasets: TransparencyGraphDataset[]): TransparencyGraphDataset {
  let nodes: TransparencyGraphNode[] = [];
  let links: TransparencyGraphLink[] = [];

  for (const dataset of datasets) {
    for (const node of dataset.nodes) {
      nodes = upsertNode(nodes, node);
    }
    for (const link of dataset.links) {
      links = upsertLink(links, link);
    }
  }

  const nodeIds = new Set(nodes.map((node) => node.id));
  return {
    nodes,
    links: links.filter((link) => nodeIds.has(String(link.source)) && nodeIds.has(String(link.target))),
  };
}

function mapGraphEvent(event: GraphEvent): TransparencyGraphNode {
  return {
    id: event.id,
    label: event.label,
    type: event.kind,
    color: NODE_COLORS[event.kind] ?? "#94a3b8",
    layer: "live",
    status: event.status,
    region: event.region,
    confidence: event.confidence,
    emphasis: event.kind === "source_agent" || event.kind === "contradiction" ? 1 : 0.75,
    meta: {
      evidenceCount: event.evidenceCount ?? 0,
      priorCount: event.priorCount ?? 0,
      unresolvedCount: event.unresolvedCount ?? 0,
      url: event.url ?? "",
      error: event.error ?? "",
    },
  };
}

function deriveLiveGraph(payload: RoutingResult): TransparencyGraphDataset {
  const nodes: TransparencyGraphNode[] = [];
  const links: TransparencyGraphLink[] = [];

  for (const event of payload.graph_events ?? []) {
    nodes.push(mapGraphEvent(event));
    if (event.parentId) {
      links.push({
        source: event.parentId,
        target: event.id,
        type: "supports",
        layer: "live",
        color: event.kind === "contradiction" ? "#fb7185" : "#155e75",
      });
    }
    if (event.sourceId) {
      links.push({
        source: event.sourceId,
        target: event.id,
        type: "supports",
        layer: "live",
        color: "#0f766e",
      });
    }
  }

  return mergeDatasets({ nodes, links });
}

function deriveTimeline(state: TransparencyGraphState, payload: RoutingResult): TransparencyTimelineEvent[] {
  let timeline = state.timeline;

  timeline = pushTimeline(timeline, {
    label: `Routing to ${payload.jurisdiction.toUpperCase()} workflow`,
    detail: `${payload.sources.length} active sources, ${payload.claims.length} claims`,
    tone: "info",
  });

  for (const status of payload.source_statuses ?? []) {
    timeline = pushTimeline(timeline, {
      label:
        status.status === "error"
          ? `${status.label} unreachable`
          : status.evidence_count
            ? `${status.label} returned ${status.evidence_count} evidence item${status.evidence_count === 1 ? "" : "s"}`
            : `${status.label} returned no evidence`,
      detail: status.error || status.region.toUpperCase(),
      tone:
        status.status === "error"
          ? "critical"
          : status.evidence_count
            ? "success"
            : "warning",
    });
  }

  for (const contradiction of payload.contradictions ?? []) {
    timeline = pushTimeline(timeline, {
      label: `Conflict detected: ${contradiction.topic}`,
      detail: contradiction.analysis,
      tone: "warning",
    });
  }

  return timeline;
}

function deriveConversationMemoryGraph(payload: ConversationMemoryContext): TransparencyGraphDataset {
  const nodes: TransparencyGraphNode[] = [];
  const links: TransparencyGraphLink[] = [];

  const memoryRootId = "memory:conversation";
  nodes.push({
    id: memoryRootId,
    label: "Conversation memory",
    type: "memory",
    color: NODE_COLORS.memory,
    layer: "live",
    status: payload.loaded ? "loaded" : "idle",
    emphasis: 0.88,
  });

  if (payload.summary) {
    nodes.push({
      id: "memory:summary",
      label: payload.summary.slice(0, 90),
      type: "memory",
      color: NODE_COLORS.memory,
      layer: "live",
      status: "loaded",
      emphasis: 0.72,
    });
    links.push({
      source: memoryRootId,
      target: "memory:summary",
      type: "persists_to",
      layer: "live",
      color: "#a78bfa",
    });
  }

  payload.prior_topics.slice(0, 3).forEach((topic, index) => {
    const id = `memory:topic:${index}`;
    nodes.push({
      id,
      label: topic.slice(0, 64),
      type: "memory",
      color: "#c084fc",
      layer: "live",
      status: "loaded",
      emphasis: 0.64,
    });
    links.push({
      source: memoryRootId,
      target: id,
      type: "references",
      layer: "live",
      color: "#8b5cf6",
    });
  });

  payload.recent_turns.slice(-4).forEach((turn, index) => {
    const id = `memory:turn:${index}:${turn.role}`;
    nodes.push({
      id,
      label: `${turn.role === "user" ? "User" : "Advisor"}: ${turn.text.slice(0, 68)}`,
      type: turn.role === "user" ? "query" : "memory",
      color: turn.role === "user" ? NODE_COLORS.query : NODE_COLORS.memory,
      layer: "live",
      status: "loaded",
      emphasis: 0.6,
    });
    links.push({
      source: memoryRootId,
      target: id,
      type: "supports",
      layer: "live",
      color: "#475569",
    });
  });

  return { nodes, links };
}

function convertMemoryGraph(payload: PersistedGraphData): TransparencyGraphDataset {
  return {
    nodes: payload.nodes.map((node) => ({
      id: node.id,
      label: node.label,
      type: node.type,
      color: node.color || NODE_COLORS.memory,
      layer: "memory",
      emphasis: 0.65,
    })),
    links: payload.links.map((link) => ({
      source: link.source,
      target: link.target,
      type: link.type,
      layer: "memory",
      color: "#334155",
    })),
  };
}

function updateCombined(state: TransparencyGraphState): TransparencyGraphDataset {
  return mergeDatasets(state.live, state.memory);
}

export function reduceGraphState(
  state: TransparencyGraphState = createInitialTransparencyGraphState(),
  action: GraphAction,
): TransparencyGraphState {
  switch (action.type) {
    case "session_started": {
      const live = mergeDatasets(state.live, {
        nodes: [
          {
            id: `session:${action.payload.sessionId}`,
            label: `Session ${action.payload.sessionId.slice(0, 8)}`,
            type: "session",
            color: NODE_COLORS.session,
            layer: "live",
            status: "active",
            emphasis: 1,
          },
        ],
        links: [],
      });

      const next = {
        ...state,
        live,
        timeline: pushTimeline(state.timeline, {
          label: "Live transparency session started",
          detail: action.payload.sessionId,
          tone: "info",
        }),
      };
      return { ...next, combined: updateCombined(next) };
    }
    case "camera_updated": {
      const live = mergeDatasets(state.live, {
        nodes: [
          {
            id: "camera:live",
            label: action.payload.active ? "Camera live" : "Camera waiting",
            type: "camera",
            color: NODE_COLORS.camera,
            layer: "live",
            status: action.payload.active ? "active" : "idle",
            emphasis: action.payload.active ? 0.95 : 0.55,
            meta: { message: action.payload.message ?? "" },
          },
        ],
        links: [],
      });
      const next = {
        ...state,
        live,
        timeline: pushTimeline(state.timeline, {
          label: action.payload.active ? "Camera feed connected" : "Camera feed waiting",
          detail: action.payload.message,
          tone: action.payload.active ? "success" : "info",
        }),
      };
      return { ...next, combined: updateCombined(next) };
    }
    case "conversation_memory_loaded": {
      const live = mergeDatasets(state.live, deriveConversationMemoryGraph(action.payload));
      const next = {
        ...state,
        live,
        timeline: pushTimeline(state.timeline, {
          label: action.payload.loaded
            ? `Loaded prior conversation context`
            : "No prior conversation context found",
          detail: action.payload.loaded
            ? `Reused ${action.payload.recent_turns.length} recent turns and ${action.payload.prior_topics.length} remembered topics`
            : "This session will start building memory from the current conversation.",
          tone: action.payload.loaded ? "success" : "info",
        }),
      };
      return { ...next, combined: updateCombined(next) };
    }
    case "routing_result": {
      const live = mergeDatasets(state.live, deriveLiveGraph(action.payload));
      const next = {
        ...state,
        live,
        timeline: deriveTimeline(state, action.payload),
      };
      return { ...next, combined: updateCombined(next) };
    }
    case "memory_loading":
      return { ...state, memoryStatus: "loading", memoryError: null };
    case "memory_loaded": {
      const memory = convertMemoryGraph(action.payload);
      const next = {
        ...state,
        memory,
        memoryStatus: "ready" as const,
        memoryError: null,
        timeline: pushTimeline(state.timeline, {
          label:
            action.payload.nodes.length > 0
              ? `Memory layer synchronized with ${action.payload.nodes.length} nodes`
              : "Memory layer synchronized with no persisted nodes yet",
          detail:
            action.payload.nodes.length > 0
              ? `${action.payload.links.length} stored relationship${action.payload.links.length === 1 ? "" : "s"}`
              : "Ask a question or confirm a document to create persistent relationships.",
          tone: action.payload.nodes.length > 0 ? "success" : "info",
        }),
      };
      return { ...next, combined: updateCombined(next) };
    }
    case "memory_load_failed":
      return {
        ...state,
        memoryStatus: "error",
        memoryError: action.payload.error,
        timeline: pushTimeline(state.timeline, {
          label: "Memory graph unavailable",
          detail: action.payload.error,
          tone: "warning",
        }),
      };
    case "document_confirmed": {
      const live = mergeDatasets(state.live, {
        nodes: [
          {
            id: `document:${action.payload.docId}`,
            label: action.payload.docId,
            type: "document",
            color: NODE_COLORS.document,
            layer: "live",
            status: action.payload.stored ? "stored" : "pending",
            emphasis: 0.9,
          },
          {
            id: "memory:handoff",
            label: action.payload.stored ? "Knowledge graph write" : "Memory handoff pending",
            type: "memory",
            color: NODE_COLORS.memory,
            layer: "live",
            status: action.payload.stored ? "stored" : "pending",
            emphasis: 0.82,
          },
        ],
        links: action.payload.stored
          ? [
              {
                source: `document:${action.payload.docId}`,
                target: "memory:handoff",
                type: "persists_to",
                layer: "live",
                color: "#a78bfa",
              },
            ]
          : [],
      });
      const next = {
        ...state,
        live,
        timeline: pushTimeline(state.timeline, {
          label: action.payload.stored ? "Document persisted to memory" : "Document confirm completed without storage",
          detail: action.payload.docId,
          tone: action.payload.stored ? "success" : "warning",
        }),
      };
      return { ...next, combined: updateCombined(next) };
    }
    default:
      return state;
  }
}

export function buildTimelineHeadline(state: TransparencyGraphState): string {
  const latest = state.timeline[0];
  return latest ? latest.label : "Transparency atlas is waiting for the next query.";
}
