"use client";

import { cn } from "@/lib/utils";
import { ExternalLinkIcon } from "lucide-react";

export interface SourceItem {
  id: string;
  title: string;
  url?: string;
  snippet?: string;
  date?: string;
  source?: string;
  replyCount?: number;
}

const SOURCE_META: Record<string, { color: string; abbr: string; name: string }> = {
  caclub:       { color: "#3b82f6", abbr: "CA", name: "CAClubIndia" },
  caclubindia:  { color: "#3b82f6", abbr: "CA", name: "CAClubIndia" },
  taxtmi:       { color: "#14b8a6", abbr: "TM", name: "TaxTMI" },
  turbotax:     { color: "#a855f7", abbr: "TT", name: "TurboTax" },
  taxprofblog:  { color: "#f59e0b", abbr: "TP", name: "TaxProfBlog" },
  indiankanoon: { color: "#ec4899", abbr: "IK", name: "Indian Kanoon" },
  casemine:     { color: "#ef4444", abbr: "CM", name: "Casemine" },
};

function inferMeta(url?: string, source?: string) {
  const text = ((url || "") + " " + (source || "")).toLowerCase();
  for (const [key, val] of Object.entries(SOURCE_META)) {
    if (text.includes(key)) return val;
  }
  return { color: "#52525b", abbr: "??", name: source || "Source" };
}

function shortenUrl(url: string) {
  if (typeof url !== "string") return "";
  try {
    const u = new URL(url);
    return u.hostname.replace("www.", "") + u.pathname.slice(0, 20);
  } catch {
    return url.slice(0, 36);
  }
}

function SourceCard({ item }: { item: SourceItem }) {
  const meta = inferMeta(item.url, item.source);

  return (
    <div className="group relative rounded-lg border border-border bg-card p-3 transition-all duration-200 hover:border-ring hover:bg-accent animate-slide-in-right">
      {/* Accent top bar */}
      <div
        className="absolute top-0 left-0 right-0 h-[2px] rounded-t-lg opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ background: `linear-gradient(90deg, ${meta.color}, transparent)` }}
      />

      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <div
          className="size-5 rounded flex items-center justify-center text-[8px] font-bold font-mono text-white shrink-0"
          style={{ background: meta.color }}
        >
          {meta.abbr}
        </div>
        <span className="text-xs text-muted-foreground">{meta.name}</span>
        {item.date && <span className="text-[10px] font-mono text-muted-foreground/60 ml-auto">{item.date}</span>}
      </div>

      {/* Title */}
      <h4 className="text-xs font-medium text-foreground leading-snug line-clamp-2 mb-1">
        {item.title || "Untitled"}
      </h4>

      {/* Snippet */}
      {item.snippet && (
        <p className="text-[11px] text-muted-foreground leading-relaxed line-clamp-3 mb-2">
          {item.snippet}
        </p>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between">
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[10px] font-mono text-primary/70 hover:text-primary transition-colors"
          >
            <ExternalLinkIcon className="size-2.5" />
            {shortenUrl(item.url)}
          </a>
        ) : (
          <span />
        )}
        {item.replyCount != null && item.replyCount > 0 && (
          <span className="text-[10px] font-mono text-muted-foreground/60">{item.replyCount} replies</span>
        )}
      </div>
    </div>
  );
}

export function SourcePanel({ sources, className }: { sources: SourceItem[]; className?: string }) {
  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 h-10 border-b border-border shrink-0">
        <span className="text-xs font-medium text-muted-foreground tracking-wide uppercase font-mono">Sources</span>
        <span className="text-[10px] font-mono text-muted-foreground/60 tabular-nums bg-secondary px-1.5 py-0.5 rounded">
          {sources.length}
        </span>
      </div>

      {/* Cards */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {sources.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="size-8 rounded-lg border border-border flex items-center justify-center mb-2">
              <ExternalLinkIcon className="size-3.5 text-muted-foreground/50" />
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Sources appear as the<br />agent researches
            </p>
          </div>
        ) : (
          sources.map((s) => <SourceCard key={s.id} item={s} />)
        )}
      </div>
    </div>
  );
}

/** Extract SourceItems from a tool result. */
export function extractSources(result: any): SourceItem[] {
  const items: SourceItem[] = [];
  if (!result) return items;

  let counter = Date.now();

  (result.claims || []).forEach((claim: any) => {
    if (!claim) return;
    (claim.citations || []).forEach((citation: any) => {
      const url =
        typeof citation === "string"
          ? citation
          : citation?.url || citation?.link || citation?.href || "";
      if (url && typeof url !== "string") return;
      items.push({
        id: String(counter++),
        title: claim.claim || claim.text || "",
        url: url || "",
        snippet: citation?.snippet || "",
        date: citation?.date || "",
        source: citation?.source || (result.sources || [])[0] || "",
        replyCount: citation?.reply_count ?? citation?.replyCount,
      });
    });
  });

  if (!items.length && result.bullets) {
    result.bullets.forEach((b: string) => {
      const urlMatch = b.match(/https?:\/\/[^\s)]+/);
      items.push({
        id: String(counter++),
        title: b.replace(/^-\s*/, "").slice(0, 120),
        url: urlMatch ? urlMatch[0] : "",
        snippet: b,
      });
    });
  }

  if (result.legal_context) {
    const lc = result.legal_context;
    (lc.sections || []).forEach((s: any) => {
      items.push({
        id: String(counter++),
        title: s.title || s.section || "Law Section",
        url: s.url || "",
        snippet: s.text || s.snippet || "",
        source: "indiankanoon",
      });
    });
    (lc.judgements || []).forEach((j: any) => {
      items.push({
        id: String(counter++),
        title: j.title || "Court Judgement",
        url: j.url || "",
        snippet: j.snippet || j.text || "",
        source: "casemine",
      });
    });
  }

  return items;
}
