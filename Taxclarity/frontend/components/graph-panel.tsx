"use client";

import { useEffect, useRef, useCallback, useState, useMemo } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { RefreshCwIcon, XIcon, SearchIcon, NetworkIcon } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface GraphNode {
  id: string;
  label: string;
  type: string;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
  degree?: number;
  isNew?: boolean;
}

interface GraphEdge {
  source: string | GraphNode;
  target: string | GraphNode;
  type: string;
}

export interface LiveGraphData {
  nodes: GraphNode[];
  edges: Array<{
    from: string;
    to: string;
    type: string;
  }>;
}

interface InspectedNode extends GraphNode {
  connections: string[];
}

export interface GraphPanelProps {
  userId?: string;
  sessionId?: string;
  apiUrl: string;
  className?: string;
  liveGraph?: LiveGraphData | null;
  refreshToken?: number;
}

// ---------------------------------------------------------------------------
// Node type config — neon palette on deep void
// ---------------------------------------------------------------------------

const NODE_CFG: Record<string, { color: string; glow: string; label: string; desc: string }> = {
  User:         { color: "#93c5fd", glow: "rgba(147,197,253,0.42)", label: "U", desc: "User Profile" },
  Session:      { color: "#5eead4", glow: "rgba(94,234,212,0.38)",  label: "S", desc: "Session" },
  Query:        { color: "#38bdf8", glow: "rgba(56,189,248,0.44)",  label: "Q", desc: "Tax Query" },
  Concept:      { color: "#fbbf24", glow: "rgba(251,191,36,0.40)",  label: "C", desc: "Tax Concept" },
  TaxEntity:    { color: "#34d399", glow: "rgba(52,211,153,0.38)",  label: "E", desc: "Tax Entity" },
  Resolution:   { color: "#f59e0b", glow: "rgba(245,158,11,0.40)",  label: "R", desc: "Resolution" },
  Jurisdiction: { color: "#fb7185", glow: "rgba(251,113,133,0.38)", label: "J", desc: "Jurisdiction" },
  TaxForm:      { color: "#c4b5fd", glow: "rgba(196,181,253,0.38)", label: "F", desc: "Tax Form" },
  Ambiguity:    { color: "#f87171", glow: "rgba(248,113,113,0.42)", label: "!", desc: "Ambiguity" },
};
const FALLBACK = { color: "#94a3b8", glow: "rgba(148,163,184,0.28)", label: "?", desc: "Unknown" };
const nc = (t: string) => NODE_CFG[t] || FALLBACK;

const BASE_R = 9;
const MAX_EXTRA_R = 9; // degree can add up to 9px extra

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function GraphPanel({ userId, sessionId, apiUrl, className, liveGraph, refreshToken }: GraphPanelProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const simRef = useRef<any>(null);
  const nodesRef = useRef<GraphNode[]>([]);
  const linksRef = useRef<GraphEdge[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);

  const [inspected, setInspected] = useState<InspectedNode | null>(null);
  const [search, setSearch] = useState("");
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set(Object.keys(NODE_CFG)));
  const [stats, setStats] = useState<Record<string, number>>({});
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);
  const [loading, setLoading] = useState(false);

  // All node types present in current graph
  const presentTypes = useMemo(
    () => Object.keys(NODE_CFG).filter((t) => (stats[t] ?? 0) > 0),
    [stats]
  );

  // Filtered nodes for rendering
  const visibleNodeIds = useMemo(() => {
    const q = search.toLowerCase();
    return new Set(
      nodesRef.current
        .filter((n) => activeTypes.has(n.type) && (!q || (n.label || n.id).toLowerCase().includes(q)))
        .map((n) => n.id)
    );
  }, [search, activeTypes, nodeCount]); // nodeCount triggers re-memo on refresh

  // ---------------------------------------------------------------------------
  // D3 render
  // ---------------------------------------------------------------------------

  const renderGraph = useCallback(() => {
    const svg = svgRef.current;
    if (!svg) return;

    import("d3").then((d3) => {
      const container = svg.parentElement!;
      const w = container.clientWidth || 400;
      const h = container.clientHeight || 400;

      const sel = d3.select(svg).attr("viewBox", `0 0 ${w} ${h}`);

      // ---- one-time setup ----
      if (!simRef.current) {
        const defs = sel.append("defs");

        // Arrow marker per node type
        Object.entries(NODE_CFG).forEach(([type, cfg]) => {
          defs.append("marker")
            .attr("id", `arrow-${type}`)
            .attr("viewBox", "0 -4 8 8")
            .attr("refX", 18)
            .attr("refY", 0)
            .attr("markerWidth", 5)
            .attr("markerHeight", 5)
            .attr("orient", "auto")
            .append("path")
            .attr("d", "M0,-4L8,0L0,4")
            .attr("fill", cfg.color)
            .attr("opacity", 0.55);
        });
        defs.append("marker")
          .attr("id", "arrow-Unknown")
          .attr("viewBox", "0 -4 8 8").attr("refX", 18).attr("refY", 0)
          .attr("markerWidth", 5).attr("markerHeight", 5).attr("orient", "auto")
          .append("path").attr("d", "M0,-4L8,0L0,4").attr("fill", FALLBACK.color).attr("opacity", 0.4);

        // Glow filter
        const glow = defs.append("filter").attr("id", "tc-glow")
          .attr("x", "-60%").attr("y", "-60%").attr("width", "220%").attr("height", "220%");
        glow.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", "3.5").attr("result", "blur");
        const merge = glow.append("feMerge");
        merge.append("feMergeNode").attr("in", "blur");
        merge.append("feMergeNode").attr("in", "SourceGraphic");

        const softGlow = defs.append("filter").attr("id", "tc-soft-glow")
          .attr("x", "-120%").attr("y", "-120%").attr("width", "340%").attr("height", "340%");
        softGlow.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", "9").attr("result", "blur");
        const softMerge = softGlow.append("feMerge");
        softMerge.append("feMergeNode").attr("in", "blur");
        softMerge.append("feMergeNode").attr("in", "SourceGraphic");

        sel.append("g").attr("class", "tc-world");

        const zoom = d3.zoom<SVGSVGElement, unknown>()
          .scaleExtent([0.15, 5])
          .on("zoom", (e) => sel.select(".tc-world").attr("transform", e.transform.toString()));
        sel.call(zoom as any);

        simRef.current = d3.forceSimulation<GraphNode>()
          .force("link", d3.forceLink<GraphNode, GraphEdge>().id((d) => d.id).distance(70).strength(0.25))
          .force("charge", d3.forceManyBody().strength(-140))
          .force("center", d3.forceCenter(w / 2, h / 2))
          .force("collision", d3.forceCollide<GraphNode>().radius((d) => BASE_R + Math.min((d.degree ?? 0) * 1.2, MAX_EXTRA_R) + 8))
          .alphaDecay(0.025);
      }

      const world = sel.select<SVGGElement>(".tc-world");
      const sim = simRef.current;
      const nodes = nodesRef.current.filter((n) => visibleNodeIds.has(n.id));
      const links = linksRef.current.filter((e) => {
        const sid = typeof e.source === "object" ? e.source.id : e.source;
        const tid = typeof e.target === "object" ? e.target.id : e.target;
        return visibleNodeIds.has(sid) && visibleNodeIds.has(tid);
      });

      // Compute degree centrality
      const degreeMap: Record<string, number> = {};
      links.forEach((e) => {
        const s = typeof e.source === "object" ? e.source.id : e.source as string;
        const t = typeof e.target === "object" ? e.target.id : e.target as string;
        degreeMap[s] = (degreeMap[s] ?? 0) + 1;
        degreeMap[t] = (degreeMap[t] ?? 0) + 1;
      });
      nodes.forEach((n) => { n.degree = degreeMap[n.id] ?? 0; });

      // ---- edges ----
      const linkSel = world.selectAll<SVGLineElement, GraphEdge>(".tc-link")
        .data(links, (d: any) => `${d.source?.id ?? d.source}→${d.target?.id ?? d.target}`);
      linkSel.exit().remove();
      const linkEnter = linkSel.enter().append("line").attr("class", "tc-link")
        .attr("stroke-opacity", 0)
        .attr("stroke-width", 1.15)
        .attr("stroke", (d) => {
          const tid = typeof d.target === "object" ? (d.target as GraphNode).type : "";
          return nc(tid).color;
        })
        .attr("stroke-linecap", "round")
        .attr("marker-end", (d) => {
          const tid = typeof d.target === "object" ? (d.target as GraphNode).type : "";
          return `url(#arrow-${NODE_CFG[tid] ? tid : "Unknown"})`;
        });
      linkEnter.transition().duration(500).attr("stroke-opacity", 0.32);
      const linkAll = linkEnter.merge(linkSel as any);

      // ---- nodes ----
      const nodeSel = world.selectAll<SVGGElement, GraphNode>(".tc-node")
        .data(nodes, (d: GraphNode) => d.id);

      nodeSel.exit().transition().duration(300).attr("opacity", 0).remove();

      const nodeEnter = nodeSel.enter().append("g")
        .attr("class", "tc-node")
        .attr("opacity", 0)
        .attr("cursor", "pointer")
        .call(
          d3.drag<SVGGElement, GraphNode>()
            .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
            .on("drag",  (e, d) => { d.fx = e.x; d.fy = e.y; })
            .on("end",   (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
        );

      // Outer halo ring
      nodeEnter.append("circle")
        .attr("class", "tc-halo")
        .attr("r", (d) => BASE_R + Math.min((d.degree ?? 0) * 1.2, MAX_EXTRA_R) + 6)
        .attr("fill", "none")
        .attr("stroke", (d) => nc(d.type).color)
        .attr("stroke-width", 1)
        .attr("stroke-opacity", 0.2)
        .attr("filter", "url(#tc-soft-glow)");

      // Inner filled circle
      nodeEnter.append("circle")
        .attr("class", "tc-body")
        .attr("r", (d) => BASE_R + Math.min((d.degree ?? 0) * 1.2, MAX_EXTRA_R))
        .attr("fill", (d) => nc(d.type).color)
        .attr("fill-opacity", 0.18)
        .attr("stroke", (d) => nc(d.type).color)
        .attr("stroke-width", 1.6)
        .attr("filter", "url(#tc-glow)");

      // Letter label
      nodeEnter.append("text")
        .attr("text-anchor", "middle")
        .attr("dominant-baseline", "central")
        .attr("font-size", (d) => (BASE_R + Math.min((d.degree ?? 0) * 1.2, MAX_EXTRA_R)) * 0.7)
        .attr("font-weight", 700)
        .attr("fill", (d) => nc(d.type).color)
        .attr("font-family", "var(--font-geist-mono), monospace")
        .text((d) => nc(d.type).label);

      // Text label below
      nodeEnter.append("text")
        .attr("class", "tc-label")
        .attr("text-anchor", "middle")
        .attr("dy", (d) => BASE_R + Math.min((d.degree ?? 0) * 1.2, MAX_EXTRA_R) + 12)
        .attr("font-size", 7)
        .attr("fill", "rgba(226,232,240,0.72)")
        .attr("font-family", "var(--font-geist-mono), monospace")
        .text((d) => (d.label || d.id).slice(0, 20));

      // New node pulse animation
      nodeEnter.filter((d) => !!d.isNew)
        .select(".tc-body")
        .attr("stroke-opacity", 0.9)
        .transition().duration(800)
        .attr("stroke-opacity", 0.5)
        .transition().duration(800)
        .attr("stroke-opacity", 1);

      nodeEnter.transition().duration(400).attr("opacity", 1);

      // Click handler → inspector
      nodeEnter.on("click", (_, d) => {
        const conns = links
          .filter((e) => {
            const s = typeof e.source === "object" ? e.source.id : e.source;
            const t = typeof e.target === "object" ? e.target.id : e.target;
            return s === d.id || t === d.id;
          })
          .map((e) => {
            const s = typeof e.source === "object" ? (e.source as GraphNode).label || e.source.id : e.source as string;
            const t = typeof e.target === "object" ? (e.target as GraphNode).label || e.target.id : e.target as string;
            return s === (d.label || d.id) ? `→ ${t}` : `← ${s}`;
          });
        setInspected({ ...d, connections: conns });
      });

      // Hover highlight
      nodeEnter
        .on("mouseenter", function(this: SVGGElement, _, d) {
          d3.select(this).select(".tc-body")
            .transition().duration(150)
            .attr("fill-opacity", 0.32)
            .attr("stroke-width", 2.2);
        })
        .on("mouseleave", function(this: SVGGElement) {
          d3.select(this).select(".tc-body")
            .transition().duration(150)
            .attr("fill-opacity", 0.18)
            .attr("stroke-width", 1.6);
        });

      const nodeAll = nodeEnter.merge(nodeSel as any);

      sim.nodes(nodes).on("tick", () => {
        linkAll
          .attr("x1", (d: any) => d.source.x)
          .attr("y1", (d: any) => d.source.y)
          .attr("x2", (d: any) => d.target.x)
          .attr("y2", (d: any) => d.target.y);
        nodeAll.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
      });

      (sim.force("link") as any).links(links);
      sim.alpha(0.6).restart();
    });
  }, [visibleNodeIds]);

  // ---------------------------------------------------------------------------
  // Data fetch
  // ---------------------------------------------------------------------------

  const applyGraphData = useCallback((data: { nodes?: any[]; edges?: any[]; links?: any[] }) => {
    const oldMap = new Map(nodesRef.current.map((n) => [n.id, n]));
    const prevIds = new Set(oldMap.keys());

    nodesRef.current = (data.nodes || []).map((n: any) => {
      const old = oldMap.get(n.id);
      return {
        id: n.id,
        label: n.label || n.id,
        type: n.type || "Unknown",
        x: old?.x,
        y: old?.y,
        isNew: !prevIds.has(n.id),
      };
    });

    const nodeIds = new Set(nodesRef.current.map((n) => n.id));
    const rawEdges = data.edges || data.links || [];
    linksRef.current = rawEdges
      .filter((e: any) => nodeIds.has(e.from || e.source) && nodeIds.has(e.to || e.target))
      .map((e: any) => ({
        source: e.from || e.source,
        target: e.to || e.target,
        type: e.type || "",
      }));

    const s: Record<string, number> = {};
    nodesRef.current.forEach((n) => { s[n.type] = (s[n.type] ?? 0) + 1; });
    setStats(s);
    setNodeCount(nodesRef.current.length);
    setEdgeCount(linksRef.current.length);
    renderGraph();
  }, [renderGraph]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      if (liveGraph) {
        applyGraphData(liveGraph);
        return;
      }
      if (!apiUrl || !userId) {
        applyGraphData({ nodes: [], edges: [] });
        return;
      }
      const params = new URLSearchParams();
      params.set("user_id", userId);
      if (sessionId) params.set("session_id", sessionId);
      const resp = await fetch(`${apiUrl}/api/graph/${encodeURIComponent(userId)}?${params.toString()}`);
      const data = await resp.json();
      applyGraphData(data);
    } catch {
      // graph API may not be running in dev
    } finally {
      setLoading(false);
    }
  }, [apiUrl, applyGraphData, liveGraph, sessionId, userId]);

  useEffect(() => {
    renderGraph();
    refresh();
  }, [renderGraph, refresh, refreshToken]);

  // Re-render when filters change
  useEffect(() => {
    renderGraph();
  }, [renderGraph, search, activeTypes]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className={cn("relative flex flex-col h-full overflow-hidden rounded-[1.4rem] border border-white/10 bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.16),_transparent_32%),radial-gradient(circle_at_85%_20%,_rgba(251,191,36,0.12),_transparent_28%),linear-gradient(180deg,rgba(8,12,24,0.98),rgba(3,5,12,1))] shadow-[0_24px_80px_rgba(2,8,23,0.65)]", className)}>
      <div className="pointer-events-none absolute inset-0 opacity-80">
        <div className="absolute inset-x-0 top-0 h-24 bg-[linear-gradient(180deg,rgba(148,163,184,0.10),transparent)]" />
        <div className="absolute inset-0 bg-[linear-gradient(rgba(148,163,184,0.045)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.04)_1px,transparent_1px)] bg-[size:28px_28px] opacity-[0.08]" />
        <div className="absolute left-[-20%] top-24 h-48 w-48 rounded-full bg-cyan-400/12 blur-3xl" />
        <div className="absolute right-[-15%] bottom-16 h-44 w-44 rounded-full bg-amber-400/10 blur-3xl" />
        <div className="absolute left-[18%] bottom-10 h-32 w-32 rounded-full bg-emerald-400/8 blur-3xl" />
      </div>

      {/* ── Stats row ── */}
      <div className="relative flex items-center gap-3 px-3 py-2 border-b border-white/10 flex-wrap shrink-0 bg-black/10 backdrop-blur-md">
        <div className="flex items-center gap-1.5 mr-1 rounded-full border border-cyan-400/15 bg-cyan-400/5 px-2 py-1">
          <NetworkIcon className="size-3 text-cyan-200/70" />
          <span className="text-[10px] font-mono text-slate-300">
            {nodeCount}N · {edgeCount}E
          </span>
        </div>
        {presentTypes.map((t) => (
          <div key={t} className="flex items-center gap-1">
            <span
              className="size-1.5 rounded-full shrink-0"
              style={{ background: nc(t).color, boxShadow: `0 0 4px ${nc(t).color}` }}
            />
            <span className="text-[9px] font-mono" style={{ color: nc(t).color }}>
              {t} <span className="opacity-60">{stats[t]}</span>
            </span>
          </div>
        ))}
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={refresh}
          disabled={loading}
          className="ml-auto shrink-0 border border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
          title="Refresh graph"
        >
          <RefreshCwIcon className={cn("size-3", loading && "animate-spin")} />
        </Button>
      </div>

      {/* ── Search + type filter ── */}
      <div className="relative flex items-center gap-2 px-3 py-2 border-b border-white/10 shrink-0 bg-black/10 backdrop-blur-md">
        <div className="relative flex-1">
          <SearchIcon className="absolute left-2 top-1/2 -translate-y-1/2 size-3 text-slate-400/60 pointer-events-none" />
          <input
            type="text"
            placeholder="Filter nodes…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={cn(
              "w-full rounded-xl border border-white/10 bg-white/5 pl-6 pr-2 py-1.5 text-[11px] font-mono",
              "text-slate-100 placeholder:text-slate-400/55",
              "focus:outline-none focus:border-cyan-300/45 focus:bg-white/8",
              "transition-colors"
            )}
          />
        </div>
      </div>

      {/* ── Type filter chips ── */}
      {presentTypes.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-3 py-2 border-b border-white/10 shrink-0 bg-black/5">
          {presentTypes.map((t) => {
            const active = activeTypes.has(t);
            return (
              <button
                key={t}
                onClick={() => {
                  setActiveTypes((prev) => {
                    const next = new Set(prev);
                    if (next.has(t)) next.delete(t);
                    else next.add(t);
                    return next;
                  });
                }}
                className={cn(
                  "flex items-center gap-1 rounded-full px-2.5 py-1 text-[9px] font-mono border transition-all",
                  active
                    ? "border-current/35 bg-white/8 shadow-[0_0_0_1px_rgba(255,255,255,0.02)]"
                    : "border-white/10 bg-transparent opacity-45"
                )}
                style={active ? { color: nc(t).color, boxShadow: `0 0 18px ${nc(t).glow}` } : { color: nc(t).color }}
                title={nc(t).desc}
              >
                <span
                  className="size-1.5 rounded-full shrink-0"
                  style={{ background: active ? nc(t).color : "currentColor", opacity: active ? 1 : 0.4 }}
                />
                {t}
              </button>
            );
          })}
          {activeTypes.size < presentTypes.length && (
            <button
              onClick={() => setActiveTypes(new Set(Object.keys(NODE_CFG)))}
              className="rounded-full border border-dashed border-white/15 px-2.5 py-1 text-[9px] font-mono text-slate-400 transition-colors hover:border-white/25"
            >
              show all
            </button>
          )}
        </div>
      )}

      {/* ── SVG canvas ── */}
        <div ref={containerRef} className="relative flex-1 overflow-hidden">
        <svg
          ref={svgRef}
          className="w-full h-full cursor-grab active:cursor-grabbing"
          style={{ background: "transparent" }}
        />

        {/* Empty state */}
        {nodeCount === 0 && !loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 pointer-events-none">
            <NetworkIcon className="size-8 text-slate-500/25" />
            <p className="px-4 text-center text-[11px] font-mono text-slate-400/45">
              Knowledge graph builds as you<br />have conversations
            </p>
          </div>
        )}

        {/* Node inspector overlay */}
        {inspected && (
          <div
            className={cn(
              "absolute top-3 right-3 w-52 rounded-lg border border-border bg-card/90 backdrop-blur-md",
              "overflow-hidden border-white/10 bg-slate-950/88 shadow-lg shadow-black/30 animate-fade-in"
            )}
          >
            {/* Header */}
            <div
              className="flex items-center justify-between px-3 py-2 border-b border-border/60"
              style={{ borderLeftColor: nc(inspected.type).color, borderLeftWidth: 2 }}
            >
              <div>
                <div
                  className="text-[9px] font-mono font-bold uppercase tracking-widest"
                  style={{ color: nc(inspected.type).color }}
                >
                  {nc(inspected.type).desc}
                </div>
                <div className="text-xs font-medium text-foreground leading-tight mt-0.5 truncate max-w-[150px]">
                  {inspected.label || inspected.id}
                </div>
              </div>
              <button
                onClick={() => setInspected(null)}
                className="text-muted-foreground/50 hover:text-muted-foreground transition-colors"
              >
                <XIcon className="size-3.5" />
              </button>
            </div>

            {/* Stats */}
            <div className="flex divide-x divide-border/60 border-b border-border/60">
              <div className="flex-1 px-3 py-2 text-center">
                <div className="text-sm font-mono font-semibold text-foreground">{inspected.degree ?? 0}</div>
                <div className="text-[9px] text-muted-foreground">connections</div>
              </div>
              <div className="flex-1 px-3 py-2 text-center">
                <div
                  className="text-sm font-mono font-semibold"
                  style={{ color: nc(inspected.type).color }}
                >
                  {nc(inspected.type).label}
                </div>
                <div className="text-[9px] text-muted-foreground">type</div>
              </div>
            </div>

            {/* Connections */}
            {inspected.connections.length > 0 && (
              <div className="px-3 py-2 max-h-32 overflow-y-auto">
                <div className="text-[9px] font-mono text-muted-foreground/60 uppercase mb-1.5">Edges</div>
                {inspected.connections.slice(0, 8).map((c, i) => (
                  <div key={i} className="text-[10px] font-mono text-muted-foreground py-0.5 truncate">
                    {c}
                  </div>
                ))}
                {inspected.connections.length > 8 && (
                  <div className="text-[9px] text-muted-foreground/50 mt-1">
                    +{inspected.connections.length - 8} more
                  </div>
                )}
              </div>
            )}

            {/* ID */}
            <div className="px-3 py-1.5 border-t border-border/40 bg-secondary/20">
              <div className="text-[9px] font-mono text-muted-foreground/50 truncate">{inspected.id}</div>
            </div>
          </div>
        )}

        {/* Zoom hint */}
        <div className="absolute bottom-2 right-3 text-[8px] font-mono text-muted-foreground/25 text-right select-none pointer-events-none">
          scroll to zoom · drag to pan
        </div>
      </div>
    </div>
  );
}
