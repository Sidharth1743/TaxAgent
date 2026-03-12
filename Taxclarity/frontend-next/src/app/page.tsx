"use client";

import dynamic from "next/dynamic";

const VoiceShell = dynamic(() => import("@/components/voice-shell"), { ssr: false });

export default function Home() {
  return <VoiceShell />;
}
