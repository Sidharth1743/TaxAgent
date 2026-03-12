"use client";

import { Badge } from "@/components/ui/badge";
import type { JurisdictionType } from "@/types";

interface JurisdictionBadgeProps {
  jurisdiction: JurisdictionType;
}

const config: Record<
  JurisdictionType,
  { emoji: string; label: string; className: string }
> = {
  india: {
    emoji: "\u{1F1EE}\u{1F1F3}",
    label: "India",
    className: "bg-orange-500/20 text-orange-300 border-orange-500/30",
  },
  usa: {
    emoji: "\u{1F1FA}\u{1F1F8}",
    label: "USA",
    className: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  },
  both: {
    emoji: "\u{1F1EE}\u{1F1F3}\u{1F1FA}\u{1F1F8}",
    label: "Cross-border",
    className: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  },
};

export function JurisdictionBadge({ jurisdiction }: JurisdictionBadgeProps) {
  const { emoji, label, className } = config[jurisdiction];

  return (
    <Badge className={className}>
      <span aria-hidden="true">{emoji}</span> {label}
    </Badge>
  );
}
