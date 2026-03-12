"use client";

import { motion } from "motion/react";

import type { TransparencyTimelineEvent } from "@/types";

interface GraphTimelineProps {
  events: TransparencyTimelineEvent[];
}

const TONE_STYLES = {
  info: "bg-cyan-400/12 text-cyan-100 border-cyan-400/20",
  success: "bg-emerald-400/12 text-emerald-100 border-emerald-400/20",
  warning: "bg-amber-400/12 text-amber-100 border-amber-400/20",
  critical: "bg-rose-400/12 text-rose-100 border-rose-400/20",
};

export function GraphTimeline({ events }: GraphTimelineProps) {
  if (events.length === 0) {
    return (
      <div className="rounded-[28px] border border-dashed border-white/10 bg-white/[0.03] p-4 text-sm text-slate-400">
        Workflow events appear here as TaxClarity routes, verifies, and stores evidence.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {events.map((event, index) => (
        <motion.div
          key={event.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: Math.min(index * 0.03, 0.18) }}
          className={`rounded-[24px] border p-4 ${TONE_STYLES[event.tone]}`}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold">{event.label}</p>
              {event.detail && (
                <p className="mt-1 text-xs leading-5 text-slate-300/90">{event.detail}</p>
              )}
            </div>
            <span className="text-[10px] uppercase tracking-[0.24em] text-slate-400">
              {new Date(event.createdAt).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
