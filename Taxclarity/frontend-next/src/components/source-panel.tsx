"use client";

import { X } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { JurisdictionBadge } from "@/components/jurisdiction-badge";
import { SourceCard } from "@/components/source-card";
import { ContradictionCard } from "@/components/contradiction-card";
import type { Claim, Contradiction, JurisdictionType, SourceStatus } from "@/types";

interface SourcePanelProps {
  claims: Claim[];
  jurisdiction: JurisdictionType;
  visible: boolean;
  onClose: () => void;
  contradictions?: Contradiction[];
  docked?: boolean;
  sourceStatuses?: SourceStatus[];
}

export function SourcePanel({
  claims,
  jurisdiction,
  visible,
  onClose,
  contradictions,
  docked = false,
  sourceStatuses,
}: SourcePanelProps) {
  const failedSources = (sourceStatuses ?? []).filter((status) => status.status === "error");

  return (
    <AnimatePresence>
      {visible && (
        <motion.aside
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ type: "spring", damping: 25, stiffness: 300 }}
          className={
            docked
              ? "flex h-full w-full flex-col bg-transparent"
              : "fixed right-0 top-0 z-40 h-full w-full border-l border-slate-700 bg-slate-900/95 backdrop-blur-sm lg:w-80"
          }
        >
          {/* Header */}
          <div className={`flex items-center justify-between border-b border-slate-700 px-4 py-3 ${docked ? "bg-transparent" : ""}`}>
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-semibold text-slate-200">Sources</h2>
              <JurisdictionBadge jurisdiction={jurisdiction} />
              <span className="text-xs text-slate-400">
                {claims.length} claim{claims.length !== 1 ? "s" : ""}
              </span>
            </div>
            {!docked && (
              <button
                onClick={onClose}
                className="rounded-md p-1 text-slate-400 hover:bg-slate-700 hover:text-slate-200 transition-colors"
                aria-label="Close sources panel"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          {/* Body */}
          <ScrollArea className={docked ? "h-full" : "h-[calc(100%-3.5rem)]"}>
            <div className="space-y-3 p-4">
              {contradictions && contradictions.length > 0 && (
                <div className="space-y-3 mb-4">
                  <h3 className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
                    Conflicting Views
                  </h3>
                  {contradictions.map((c, i) => (
                    <ContradictionCard
                      key={`contradiction-${i}`}
                      contradiction={c}
                      index={i}
                    />
                  ))}
                </div>
              )}
              {sourceStatuses && sourceStatuses.length > 0 && (
                <div className="space-y-3 mb-4">
                  <h3 className="text-xs font-semibold text-cyan-400 uppercase tracking-wider">
                    Source Status
                  </h3>
                  {sourceStatuses.map((status) => (
                    <div
                      key={`${status.region}-${status.source}`}
                      className="rounded-2xl border border-white/10 bg-white/5 p-3"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-slate-100">{status.label}</p>
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                            {status.region}
                          </p>
                        </div>
                        <span
                          className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${
                            status.status === "error"
                              ? "bg-rose-400/10 text-rose-300"
                              : status.evidence_count
                                ? "bg-emerald-400/10 text-emerald-300"
                                : "bg-amber-400/10 text-amber-300"
                          }`}
                        >
                          {status.status === "error"
                            ? "unreachable"
                            : status.evidence_count
                              ? `${status.evidence_count} hits`
                              : "no evidence"}
                        </span>
                      </div>
                      {status.error && (
                        <p className="mt-2 text-xs leading-5 text-slate-400">{status.error}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {claims.length === 0 ? (
                <p className="text-center text-sm text-slate-500 py-8">
                  {failedSources.length > 0
                    ? "No evidence loaded because one or more source agents are unreachable."
                    : "No sources yet"}
                </p>
              ) : (
                claims.map((claim, i) => (
                  <SourceCard
                    key={`${claim.claim.slice(0, 40)}-${i}`}
                    claim={claim}
                    index={i}
                  />
                ))
              )}
            </div>
          </ScrollArea>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
