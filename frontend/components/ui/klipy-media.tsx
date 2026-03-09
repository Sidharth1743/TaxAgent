"use client";

import { X } from "lucide-react";
import { type KlipyMedia } from "@/lib/klipy";

interface KlipyMediaCardProps {
  media: KlipyMedia;
  onDismiss: () => void;
}

export function KlipyMediaCard({ media, onDismiss }: KlipyMediaCardProps) {
  const isVideo = media.format === "mp4" || media.format === "webm";

  return (
    <div className="relative mt-2 max-w-[240px] rounded-lg overflow-hidden border border-border animate-fade-in">
      {/* Dismiss button */}
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        className="absolute top-1 right-1 z-10 size-5 rounded-full bg-black/50 flex items-center justify-center hover:bg-black/70 transition-colors"
      >
        <X className="size-3 text-white" />
      </button>

      {isVideo ? (
        <video
          src={media.url}
          autoPlay
          loop
          muted
          playsInline
          className="w-full h-auto block"
        />
      ) : (
        <img
          src={media.url}
          alt={media.alt}
          className="w-full h-auto block"
          loading="lazy"
        />
      )}

      {/* Caption */}
      <div className="px-2 py-1 bg-black/30">
        <p className="text-[9px] font-mono text-white/50 truncate">{media.alt}</p>
      </div>
    </div>
  );
}
