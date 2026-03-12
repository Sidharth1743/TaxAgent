import { describe, expect, it } from "vitest";

import { reduceGraphState } from "@/lib/transparency-graph";

describe("reduceGraphState", () => {
  it("adds live query, source agent, and claim nodes from routing payload", () => {
    const next = reduceGraphState(undefined, {
      type: "routing_result",
      payload: {
        query: "What is 80C?",
        jurisdiction: "india",
        claims: [{ claim: "80C available", citations: [], confidence: 0.8 }],
        sources: ["TaxTMI"],
        source_statuses: [
          {
            source: "taxtmi",
            label: "TaxTMI",
            region: "india",
            status: "success",
            evidence_count: 1,
          },
        ],
        graph_events: [
          { id: "query:1", kind: "query", label: "What is 80C?" },
          { id: "source:taxtmi", kind: "source_agent", label: "TaxTMI", status: "success" },
          {
            id: "claim:1",
            kind: "claim",
            label: "80C available",
            confidence: 0.8,
            parentId: "query:1",
          },
        ],
      },
    });

    expect(next.live.nodes.some((node) => node.id === "query:1")).toBe(true);
    expect(next.live.nodes.some((node) => node.id === "source:taxtmi")).toBe(true);
    expect(next.live.nodes.some((node) => node.id === "claim:1")).toBe(true);
    expect(next.timeline[0]?.label).toContain("TaxTMI");
  });

  it("drops orphan links and adds remembered conversation context", () => {
    const withMemory = reduceGraphState(undefined, {
      type: "conversation_memory_loaded",
      payload: {
        loaded: true,
        summary: "User previously discussed Form 16 and Section 80C.",
        prior_topics: ["Form 16", "Section 80C"],
        recent_turns: [
          {
            role: "user",
            text: "Can you review my previous salary deductions?",
            created_at: "2026-03-09T00:00:00Z",
          },
          {
            role: "agent",
            text: "You still have unused 80C headroom.",
            created_at: "2026-03-09T00:00:01Z",
          },
        ],
      },
    });

    const withRouting = reduceGraphState(withMemory, {
      type: "routing_result",
      payload: {
        query: "What is 80C?",
        jurisdiction: "india",
        claims: [{ claim: "80C available", citations: [], confidence: 0.8 }],
        sources: ["TaxTMI"],
        source_statuses: [
          {
            source: "taxtmi",
            label: "TaxTMI",
            region: "india",
            status: "success",
            evidence_count: 1,
          },
        ],
        graph_events: [
          { id: "query:1", kind: "query", label: "What is 80C?" },
          {
            id: "citation:1",
            kind: "citation",
            label: "Missing source node",
            sourceId: "source:both:taxtmi",
          },
        ],
      },
    });

    expect(withRouting.live.nodes.some((node) => node.id === "memory:conversation")).toBe(true);
    expect(withRouting.live.links.some((link) => String(link.source) === "source:both:taxtmi")).toBe(false);
    expect(withRouting.timeline.some((event) => event.label.includes("Loaded prior conversation context"))).toBe(true);
  });

  it("creates unique timeline ids for repeated events", () => {
    const base = reduceGraphState(undefined, {
      type: "memory_loaded",
      payload: { nodes: [], links: [] },
    });

    const next = reduceGraphState(base, {
      type: "memory_loaded",
      payload: { nodes: [], links: [] },
    });

    expect(next.timeline[0]?.id).not.toBe(next.timeline[1]?.id);
    expect(next.timeline[0]?.label).toBe(next.timeline[1]?.label);
  });
});
