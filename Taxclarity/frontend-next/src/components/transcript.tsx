"use client";

import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { TranscriptEntry } from "@/types";

interface TranscriptProps {
  entries: TranscriptEntry[];
}

export function Transcript({ entries }: TranscriptProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries]);

  return (
    <ScrollArea className="h-64 w-full max-w-lg rounded-md border bg-white/5 p-4">
      {entries.length === 0 ? (
        <p className="text-sm text-slate-500 text-center mt-8">
          Start speaking to begin...
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {entries.map((entry) => (
            <div
              key={entry.id}
              className={cn(
                "flex flex-col max-w-[80%]",
                entry.role === "user" ? "self-end items-end" : "self-start items-start"
              )}
            >
              <span className="text-xs text-slate-400 mb-0.5">
                {entry.role === "user" ? "You" : "Tax Advisor"}
              </span>
              <p
                className={cn(
                  "text-sm rounded-lg px-3 py-2",
                  entry.role === "user"
                    ? "bg-blue-600/20 text-blue-100"
                    : "bg-slate-700/50 text-slate-100"
                )}
              >
                {entry.text}
              </p>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </ScrollArea>
  );
}
