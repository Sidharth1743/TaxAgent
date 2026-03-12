"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/utils";
import type { OrbState } from "@/types";

interface VoiceOrbProps {
  state: OrbState;
  volume: number;
  onClick: () => void;
}

const stateStyles: Record<OrbState, string> = {
  idle: "shadow-cyan-500/30 shadow-[0_0_60px_6px] animate-pulse-slow",
  listening: "shadow-emerald-500/50 shadow-[0_0_70px_12px]",
  thinking: "shadow-amber-400/50 shadow-[0_0_70px_12px] animate-spin-slow",
  speaking: "shadow-sky-400/50 shadow-[0_0_80px_14px]",
};

export function VoiceOrb({ state, volume, onClick }: VoiceOrbProps) {
  const isVolumeReactive = state === "listening" || state === "speaking";
  const scale = isVolumeReactive ? 1 + volume * 0.15 : 1;

  return (
    <motion.button
      onClick={onClick}
      animate={{ scale }}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
      className={cn(
        "relative h-36 w-36 cursor-pointer rounded-full border border-white/15 bg-[radial-gradient(circle_at_30%_30%,rgba(255,255,255,0.9),rgba(255,255,255,0.12)_18%,rgba(8,47,73,0.1)_28%),conic-gradient(from_180deg_at_50%_50%,#0f766e,#10b981,#38bdf8,#0f172a,#0f766e)] transition-shadow duration-300 md:h-44 md:w-44",
        stateStyles[state]
      )}
      aria-label={state === "idle" ? "Start voice session" : "Stop voice session"}
    >
      <span className="absolute inset-[18%] rounded-full border border-white/10 bg-slate-950/75" />
      <span className="absolute inset-[30%] rounded-full bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.4),rgba(255,255,255,0.06),rgba(8,15,26,0.95))]" />
    </motion.button>
  );
}
