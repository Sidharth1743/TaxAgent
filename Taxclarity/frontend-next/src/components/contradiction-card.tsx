"use client";

import { AlertTriangle, ExternalLink } from "lucide-react";
import { motion } from "motion/react";

import { Badge } from "@/components/ui/badge";
import { sourceConfig } from "@/components/source-card";
import type { Contradiction, SourceName } from "@/types";

interface ContradictionCardProps {
  contradiction: Contradiction;
  index?: number;
}

export function ContradictionCard({
  contradiction,
  index = 0,
}: ContradictionCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.1, duration: 0.3 }}
      className="rounded-lg border border-amber-700/50 bg-slate-800/50 p-4 space-y-3"
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
        <span className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
          Conflicting Views
        </span>
      </div>

      {/* Topic */}
      <p className="text-sm font-medium text-slate-200">{contradiction.topic}</p>

      {/* Positions */}
      <div className="space-y-2">
        {contradiction.positions.map((position, i) => {
          const config =
            sourceConfig[position.source as SourceName] ?? {
              displayName: position.source,
              className: "bg-slate-500/20 text-slate-300",
            };

          return (
            <div
              key={`position-${i}`}
              className="flex flex-col gap-1 rounded-md bg-slate-700/30 px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <Badge className={config.className}>
                  {config.displayName}
                </Badge>
                {position.citations.length > 0 && (
                  <a
                    href={position.citations[0]}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-slate-300 hover:text-white transition-colors truncate"
                  >
                    View source
                    <ExternalLink className="h-3 w-3 shrink-0" />
                  </a>
                )}
              </div>
              <p className="text-xs text-slate-300">{position.claim}</p>
            </div>
          );
        })}
      </div>

      {/* Analysis */}
      {contradiction.analysis && (
        <p className="text-xs text-slate-400 italic">{contradiction.analysis}</p>
      )}
    </motion.div>
  );
}
