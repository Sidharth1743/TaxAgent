"use client";

import { ExternalLink } from "lucide-react";
import { motion } from "motion/react";

import { Badge } from "@/components/ui/badge";
import { ConfidenceMeter } from "@/components/confidence-meter";
import type { Claim, Citation, SourceName } from "@/types";

interface SourceCardProps {
  claim: Claim;
  index?: number;
}

export const sourceConfig: Record<
  SourceName,
  { displayName: string; className: string }
> = {
  caclub: {
    displayName: "CAClubIndia",
    className: "bg-orange-500/20 text-orange-300",
  },
  taxtmi: {
    displayName: "TaxTMI",
    className: "bg-amber-500/20 text-amber-300",
  },
  turbotax: {
    displayName: "TurboTax",
    className: "bg-blue-500/20 text-blue-300",
  },
  taxprofblog: {
    displayName: "TaxProfBlog",
    className: "bg-sky-500/20 text-sky-300",
  },
};

function getRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "";

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDays = Math.floor(diffHr / 24);
  const diffMonths = Math.floor(diffDays / 30);
  const diffYears = Math.floor(diffDays / 365);

  if (diffYears > 0) return `${diffYears} year${diffYears > 1 ? "s" : ""} ago`;
  if (diffMonths > 0)
    return `${diffMonths} month${diffMonths > 1 ? "s" : ""} ago`;
  if (diffDays > 0) return `${diffDays} day${diffDays > 1 ? "s" : ""} ago`;
  if (diffHr > 0) return `${diffHr} hour${diffHr > 1 ? "s" : ""} ago`;
  if (diffMin > 0) return `${diffMin} minute${diffMin > 1 ? "s" : ""} ago`;
  return "just now";
}

function CitationItem({ citation }: { citation: Citation }) {
  const config = sourceConfig[citation.source] ?? {
    displayName: citation.source,
    className: "bg-slate-500/20 text-slate-300",
  };

  return (
    <div className="flex flex-col gap-1 rounded-md bg-slate-700/30 px-3 py-2">
      <div className="flex items-center gap-2">
        <Badge className={config.className}>{config.displayName}</Badge>
        <a
          href={citation.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-slate-300 hover:text-white transition-colors truncate"
          title={citation.title ?? citation.url}
        >
          {citation.title ?? new URL(citation.url).hostname}
          <ExternalLink className="h-3 w-3 shrink-0" />
        </a>
      </div>
      <div className="flex items-center gap-3 text-xs text-slate-400">
        {citation.date && (
          <span>{getRelativeTime(citation.date)}</span>
        )}
        {citation.reply_count != null && citation.reply_count > 0 && (
          <span>{citation.reply_count} replies</span>
        )}
      </div>
      {citation.snippet && (
        <p className="text-xs text-slate-400 line-clamp-2">{citation.snippet}</p>
      )}
    </div>
  );
}

export function SourceCard({ claim, index = 0 }: SourceCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.1, duration: 0.3 }}
      className="rounded-lg border border-slate-700 bg-slate-800/50 p-4 space-y-3"
    >
      <p className="text-sm text-slate-200">{claim.claim}</p>

      {claim.citations.length > 0 && (
        <div className="space-y-2">
          {claim.citations.map((citation, i) => (
            <CitationItem key={`${citation.url}-${i}`} citation={citation} />
          ))}
        </div>
      )}

      {claim.confidence != null && (
        <ConfidenceMeter confidence={claim.confidence} />
      )}
    </motion.div>
  );
}
