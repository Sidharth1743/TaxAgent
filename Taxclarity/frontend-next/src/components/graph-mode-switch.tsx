"use client";

import type { TransparencyGraphMode } from "@/types";

export function getGraphModeLabel(mode: TransparencyGraphMode): string {
  switch (mode) {
    case "live":
      return "Live Flow";
    case "memory":
      return "Memory";
    default:
      return "Combined";
  }
}

interface GraphModeSwitchProps {
  value: TransparencyGraphMode;
  onChange: (mode: TransparencyGraphMode) => void;
}

const MODES: TransparencyGraphMode[] = ["live", "memory", "combined"];

export function GraphModeSwitch({ value, onChange }: GraphModeSwitchProps) {
  return (
    <div className="inline-flex rounded-full border border-white/10 bg-white/5 p-1">
      {MODES.map((mode) => {
        const active = mode === value;
        return (
          <button
            key={mode}
            type="button"
            onClick={() => onChange(mode)}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
              active
                ? "bg-cyan-400/15 text-cyan-100 shadow-[0_0_22px_rgba(34,211,238,0.18)]"
                : "text-slate-400 hover:text-slate-100"
            }`}
          >
            {getGraphModeLabel(mode)}
          </button>
        );
      })}
    </div>
  );
}
