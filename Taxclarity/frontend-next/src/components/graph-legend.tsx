"use client";

const LEGEND = [
  { label: "Query", color: "bg-sky-300" },
  { label: "Source Agent", color: "bg-emerald-300" },
  { label: "Claim / Citation", color: "bg-amber-300" },
  { label: "Contradiction", color: "bg-rose-300" },
  { label: "Memory", color: "bg-violet-300" },
];

export function GraphLegend() {
  return (
    <div className="flex flex-wrap gap-2">
      {LEGEND.map((item) => (
        <div
          key={item.label}
          className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5"
        >
          <span className={`h-2.5 w-2.5 rounded-full ${item.color}`} />
          <span className="text-[11px] uppercase tracking-[0.18em] text-slate-300">{item.label}</span>
        </div>
      ))}
    </div>
  );
}
