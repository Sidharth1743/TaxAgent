"use client";

import {
  startTransition,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import ForceGraph2D from "react-force-graph-2d";
import { motion } from "motion/react";
import { Activity, Lightbulb, Network, Radar, Sparkles, X } from "lucide-react";

import { GraphLegend } from "@/components/graph-legend";
import { GraphModeSwitch, getGraphModeLabel } from "@/components/graph-mode-switch";
import { GraphTimeline } from "@/components/graph-timeline";
import { Button } from "@/components/ui/button";
import type {
  PersistedGraphData,
  TransparencyGraphDataset,
  TransparencyGraphMode,
  TransparencyGraphNode,
  TransparencyGraphState,
} from "@/types";

interface Insight {
  type: string;
  message: string;
  section?: string;
  potential_savings?: string;
}

interface GraphPanelProps {
  userId: string;
  visible: boolean;
  onClose: () => void;
  refreshKey?: number;
  graphState: TransparencyGraphState;
  headline: string;
  onMemoryLoadStart: () => void;
  onMemoryLoaded: (payload: PersistedGraphData) => void;
  onMemoryLoadFailed: (error: string) => void;
}

function EmptyAtlas({ mode }: { mode: TransparencyGraphMode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-5 px-8 text-center">
      <div className="rounded-full border border-cyan-400/20 bg-cyan-400/10 p-4 text-cyan-200 shadow-[0_0_50px_rgba(34,211,238,0.12)]">
        <Radar className="size-8" />
      </div>
      <div className="space-y-2">
        <p className="text-base font-semibold text-slate-100">
          {mode === "memory" ? "Memory graph is waiting for persisted knowledge" : "Transparency atlas is armed"}
        </p>
        <p className="max-w-sm text-sm leading-6 text-slate-400">
          {mode === "memory"
            ? "Ask a question, confirm a document, or let a memory write complete to see long-term relationships settle here."
            : "Start a question and the atlas will animate routing, source lookup, evidence formation, and memory handoff in real time."}
        </p>
      </div>
      <div className="grid w-full max-w-md gap-3">
        <div className="rounded-[24px] border border-white/10 bg-white/[0.04] p-4 text-left">
          <p className="text-[11px] uppercase tracking-[0.22em] text-cyan-300">Observe</p>
          <p className="mt-2 text-sm text-slate-300">Camera, query, jurisdiction, and source activation appear first.</p>
        </div>
        <div className="rounded-[24px] border border-white/10 bg-white/[0.04] p-4 text-left">
          <p className="text-[11px] uppercase tracking-[0.22em] text-amber-300">Verify</p>
          <p className="mt-2 text-sm text-slate-300">Claims, citations, and contradictions flare into view as evidence lands.</p>
        </div>
        <div className="rounded-[24px] border border-white/10 bg-white/[0.04] p-4 text-left">
          <p className="text-[11px] uppercase tracking-[0.22em] text-violet-300">Remember</p>
          <p className="mt-2 text-sm text-slate-300">Stored entities cool into the memory cluster after confirmation.</p>
        </div>
      </div>
    </div>
  );
}

export function GraphPanel({
  userId,
  visible,
  onClose,
  refreshKey = 0,
  graphState,
  headline,
  onMemoryLoadStart,
  onMemoryLoaded,
  onMemoryLoadFailed,
}: GraphPanelProps) {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<TransparencyGraphMode>("combined");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 520, height: 420 });

  useEffect(() => {
    if (!visible) return;

    const node = containerRef.current;
    if (!node) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      setCanvasSize({
        width: Math.max(320, Math.floor(entry.contentRect.width)),
        height: Math.max(360, Math.floor(entry.contentRect.height)),
      });
    });

    observer.observe(node);
    return () => observer.disconnect();
  }, [visible]);

  useEffect(() => {
    if (!visible) return;

    let mounted = true;
    startTransition(() => {
      setLoading(true);
      onMemoryLoadStart();
    });

    const apiUrl =
      process.env.NEXT_PUBLIC_GRAPH_API_URL ||
      (typeof window !== "undefined" ? window.location.origin : "http://localhost:8006");

    Promise.all([
      fetch(`${apiUrl}/api/graph/${userId}`).then(async (response) => {
        if (!response.ok) {
          throw new Error(`Graph fetch failed (${response.status})`);
        }
        return response.json();
      }),
      fetch(`${apiUrl}/api/graph/${userId}/insights`).then(async (response) => {
        if (!response.ok) {
          throw new Error(`Insights fetch failed (${response.status})`);
        }
        return response.json();
      }),
    ])
      .then(([graphResponse, insightsResponse]) => {
        if (!mounted) return;
        onMemoryLoaded(graphResponse);
        setInsights(insightsResponse);
        setLoading(false);
      })
      .catch((error) => {
        if (!mounted) return;
        onMemoryLoadFailed("Graph service unavailable. Live flow remains visible.");
        setInsights([]);
        setLoading(false);
        console.error("Failed to load graph data", error);
      });

    return () => {
      mounted = false;
    };
  }, [onMemoryLoadFailed, onMemoryLoadStart, onMemoryLoaded, refreshKey, userId, visible]);

  const activeDataset = useMemo<TransparencyGraphDataset>(() => {
    if (mode === "live") return graphState.live;
    if (mode === "memory") return graphState.memory;
    return graphState.combined;
  }, [graphState.combined, graphState.live, graphState.memory, mode]);
  const deferredDataset = useDeferredValue(activeDataset);

  const atlasStatus = loading
    ? "Refreshing memory layer"
    : graphState.memoryStatus === "error"
      ? "Memory unavailable, live flow active"
      : graphState.memoryStatus === "ready"
        ? "Live and memory layers synchronized"
        : "Waiting for graph activity";

  if (!visible) return null;

  return (
    <div className="absolute inset-y-0 right-0 z-40 flex w-full flex-col border-l border-white/10 bg-[linear-gradient(180deg,rgba(2,6,23,0.98),rgba(7,18,37,0.96))] shadow-2xl backdrop-blur-2xl lg:w-[620px]">
      <div className="sticky top-0 z-10 border-b border-white/10 bg-slate-950/90 px-4 py-4 backdrop-blur-xl">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-slate-100">
              <Network className="size-5 text-cyan-300" />
              <h2 className="font-semibold">Transparency Atlas</h2>
            </div>
            <p className="max-w-md text-sm leading-6 text-slate-300">{headline}</p>
            <div className="flex flex-wrap items-center gap-3">
              <GraphModeSwitch value={mode} onChange={setMode} />
              <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5">
                <Activity className="size-3.5 text-cyan-300" />
                <span className="text-[11px] uppercase tracking-[0.2em] text-slate-300">{atlasStatus}</span>
              </div>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="rounded-full text-slate-400 hover:bg-white/10 hover:text-white"
          >
            <X className="size-5" />
          </Button>
        </div>
      </div>

      <div className="flex flex-1 flex-col overflow-y-auto">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          className="border-b border-white/10 px-4 py-4"
        >
          <div className="rounded-[32px] border border-white/10 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.16),transparent_35%),radial-gradient(circle_at_bottom_right,rgba(168,85,247,0.14),transparent_30%),rgba(255,255,255,0.03)] p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <p className="text-[11px] uppercase tracking-[0.26em] text-slate-400">
                  {getGraphModeLabel(mode)}
                </p>
                <p className="mt-1 text-sm text-slate-200">
                  Follow how the session observes, verifies, and remembers this turn.
                </p>
              </div>
              <GraphLegend />
            </div>
            {graphState.memoryError && (
              <div className="mb-3 rounded-[22px] border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
                {graphState.memoryError}
              </div>
            )}

            <div
              ref={containerRef}
              className="relative overflow-hidden rounded-[28px] border border-white/10 bg-[linear-gradient(180deg,rgba(3,7,18,0.96),rgba(8,18,36,0.92))]"
              style={{ minHeight: 420 }}
            >
              <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(34,211,238,0.12),transparent_26%),radial-gradient(circle_at_80%_20%,rgba(251,191,36,0.1),transparent_24%),radial-gradient(circle_at_50%_90%,rgba(168,85,247,0.12),transparent_28%)]" />
              {loading && graphState.memoryStatus === "loading" ? (
                <div className="absolute inset-0 z-10 flex items-center justify-center">
                  <div className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-4 py-2 text-xs uppercase tracking-[0.22em] text-cyan-100">
                    Syncing memory layer
                  </div>
                </div>
              ) : deferredDataset.nodes.length === 0 ? (
                <EmptyAtlas mode={mode} />
              ) : (
                <ForceGraph2D
                  graphData={deferredDataset}
                  width={canvasSize.width}
                  height={canvasSize.height}
                  backgroundColor="rgba(0,0,0,0)"
                  cooldownTicks={80}
                  d3AlphaDecay={0.03}
                  linkDirectionalArrowLength={3.5}
                  linkDirectionalArrowRelPos={1}
                  nodeRelSize={5}
                  linkColor={(link) => (link as { color?: string }).color ?? "#334155"}
                  nodeCanvasObject={(node, ctx, globalScale) => {
                    const graphNode = node as unknown as TransparencyGraphNode;
                    const label = graphNode.label || graphNode.id;
                    const fontSize = Math.max(10, 14 / globalScale);
                    const radius = 7 + ((graphNode.emphasis ?? 0.7) * 7);

                    ctx.save();
                    ctx.shadowBlur = graphNode.status === "conflict" ? 26 : 18;
                    ctx.shadowColor = graphNode.color;
                    ctx.fillStyle = graphNode.color;
                    ctx.beginPath();
                    ctx.arc(graphNode.x ?? 0, graphNode.y ?? 0, radius, 0, 2 * Math.PI, false);
                    ctx.fill();

                    ctx.shadowBlur = 0;
                    ctx.strokeStyle = graphNode.layer === "memory" ? "rgba(196,181,253,0.6)" : "rgba(125,211,252,0.65)";
                    ctx.lineWidth = 1.2;
                    ctx.beginPath();
                    ctx.arc(graphNode.x ?? 0, graphNode.y ?? 0, radius + 4, 0, 2 * Math.PI, false);
                    ctx.stroke();

                    ctx.font = `${fontSize}px ui-sans-serif`;
                    ctx.textAlign = "center";
                    ctx.textBaseline = "top";
                    ctx.fillStyle = "rgba(226,232,240,0.92)";
                    ctx.fillText(label, graphNode.x ?? 0, (graphNode.y ?? 0) + radius + 8);
                    ctx.restore();
                  }}
                />
              )}
            </div>
          </div>
        </motion.div>

        <div className="grid gap-4 px-4 py-4 xl:grid-cols-[1.1fr_0.9fr]">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="rounded-[30px] border border-white/10 bg-white/[0.03] p-4"
          >
            <div className="mb-4 flex items-center gap-2">
              <Sparkles className="size-4 text-cyan-300" />
              <h3 className="text-sm font-semibold uppercase tracking-[0.22em] text-slate-200">
                Workflow Narrative
              </h3>
            </div>
            <div className="mb-4 grid gap-2 sm:grid-cols-3">
              <div className="rounded-[20px] border border-white/10 bg-slate-950/50 px-3 py-2">
                <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Nodes</p>
                <p className="mt-1 text-lg font-semibold text-slate-100">{deferredDataset.nodes.length}</p>
              </div>
              <div className="rounded-[20px] border border-white/10 bg-slate-950/50 px-3 py-2">
                <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Links</p>
                <p className="mt-1 text-lg font-semibold text-slate-100">{deferredDataset.links.length}</p>
              </div>
              <div className="rounded-[20px] border border-white/10 bg-slate-950/50 px-3 py-2">
                <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Layer</p>
                <p className="mt-1 text-lg font-semibold text-slate-100">{getGraphModeLabel(mode)}</p>
              </div>
            </div>
            <GraphTimeline events={graphState.timeline} />
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.09 }}
            className="rounded-[30px] border border-white/10 bg-white/[0.03] p-4"
          >
            <div className="mb-4 flex items-center gap-2">
              <Lightbulb className="size-4 text-amber-300" />
              <h3 className="text-sm font-semibold uppercase tracking-[0.22em] text-slate-200">
                Proactive Insights
              </h3>
            </div>

            {insights.length > 0 ? (
              <div className="space-y-3">
                {insights.map((insight, index) => (
                  <motion.div
                    key={`${insight.type}-${index}`}
                    initial={{ opacity: 0, x: 12 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: Math.min(index * 0.05, 0.2) }}
                    className="rounded-[24px] border border-white/10 bg-slate-950/60 p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs uppercase tracking-[0.18em] text-amber-300">{insight.type}</p>
                        <p className="mt-2 text-sm leading-6 text-slate-200">{insight.message}</p>
                      </div>
                      {insight.potential_savings && (
                        <span className="rounded-full bg-emerald-400/12 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-200">
                          {insight.potential_savings}
                        </span>
                      )}
                    </div>
                  </motion.div>
                ))}
              </div>
            ) : (
              <div className="rounded-[24px] border border-dashed border-white/10 bg-white/[0.02] p-4 text-sm leading-6 text-slate-400">
                Insights appear once TaxClarity has enough persisted knowledge to suggest next steps with confidence.
              </div>
            )}
          </motion.div>
        </div>
      </div>
    </div>
  );
}
