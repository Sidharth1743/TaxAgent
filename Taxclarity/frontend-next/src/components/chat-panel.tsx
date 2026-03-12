"use client";

import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { TranscriptEntry } from "@/types";

interface ChatPanelProps {
  entries: TranscriptEntry[];
  className?: string;
  draft?: string;
  onDraftChange?: (value: string) => void;
  onSubmit?: () => void;
  disabled?: boolean;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function ChatPanel({
  entries,
  className,
  draft = "",
  onDraftChange,
  onSubmit,
  disabled = false,
}: ChatPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries]);

  return (
    <div
      className={cn(
        "flex flex-col h-full w-80 bg-slate-900/95 border-r border-slate-700",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
        <h2 className="text-sm font-semibold text-slate-200">Conversation</h2>
        {entries.length > 0 && (
          <span className="text-xs text-slate-500">
            {entries.length} message{entries.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 px-3 py-3">
        {entries.length === 0 ? (
          <p className="text-sm text-slate-500 text-center mt-16">
            Start a conversation...
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {entries.map((entry) => (
              <div
                key={entry.id}
                className={cn(
                  "flex flex-col max-w-[85%]",
                  entry.role === "user"
                    ? "self-end items-end"
                    : "self-start items-start"
                )}
              >
                <span className="text-[10px] text-slate-500 mb-0.5 px-1">
                  {entry.role === "user" ? "You" : "Tax Advisor"}
                </span>
                <p
                  className={cn(
                    "text-sm rounded-lg px-3 py-2 leading-relaxed",
                    entry.role === "user"
                      ? "bg-blue-600/20 text-blue-100"
                      : "bg-slate-700/50 text-slate-100"
                  )}
                >
                  {entry.text}
                </p>
                <span className="text-[10px] text-slate-600 mt-0.5 px-1">
                  {formatTime(entry.timestamp)}
                </span>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </ScrollArea>

      {(onDraftChange || onSubmit) && (
        <div className="border-t border-slate-700 px-3 py-3 space-y-2 bg-slate-950/90">
          <textarea
            value={draft}
            onChange={(event) => onDraftChange?.(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSubmit?.();
              }
            }}
            disabled={disabled}
            placeholder="Ask about salary, deductions, Form 16, or a cross-border move..."
            className="min-h-24 w-full resize-none rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-emerald-500 focus:outline-none disabled:opacity-60"
          />
          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] text-slate-500">
              Enter to send. Shift+Enter for a new line.
            </p>
            <button
              onClick={onSubmit}
              disabled={disabled || draft.trim().length === 0}
              className="rounded-full bg-emerald-500 px-4 py-2 text-xs font-semibold text-slate-950 transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            >
              Send
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
