"use client";

interface ConfidenceMeterProps {
  confidence: number; // 0 to 1
}

function getConfidenceLabel(confidence: number): string {
  if (confidence >= 0.7) return "High confidence";
  if (confidence >= 0.4) return "Medium confidence";
  return "Low confidence";
}

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.7) return "bg-green-500";
  if (confidence >= 0.4) return "bg-yellow-500";
  return "bg-red-500";
}

export function ConfidenceMeter({ confidence }: ConfidenceMeterProps) {
  const label = getConfidenceLabel(confidence);
  const color = getConfidenceColor(confidence);
  const widthPercent = Math.round(confidence * 100);

  return (
    <div className="group relative flex items-center gap-2">
      <div className="h-2 w-24 rounded-full bg-slate-700">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${widthPercent}%` }}
        />
      </div>
      <span className="text-xs text-slate-400">{widthPercent}%</span>
      <span className="pointer-events-none absolute -top-7 left-0 rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-200 opacity-0 transition-opacity group-hover:opacity-100">
        {label}
      </span>
    </div>
  );
}
