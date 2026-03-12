"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { Camera, FileText, MessageSquareText, Network, ShieldCheck, Waves } from "lucide-react";

import { ChatPanel } from "@/components/chat-panel";
import { DisclaimerModal } from "@/components/disclaimer-modal";
import { DocumentCard } from "@/components/document-card";
import { ErrorBanner } from "@/components/error-banner";
import { GraphPanel } from "@/components/graph-panel";
import { JurisdictionBadge } from "@/components/jurisdiction-badge";
import { SettingsDialog } from "@/components/settings-dialog";
import { SourcePanel } from "@/components/source-panel";
import { UploadDialog } from "@/components/upload-dialog";
import { VoiceOrb } from "@/components/voice-orb";
import { Button } from "@/components/ui/button";
import { useDisclaimer } from "@/hooks/use-disclaimer";
import { useUserId } from "@/hooks/use-user-id";
import { useVoiceSession } from "@/hooks/use-voice-session";

function StatusPill({
  icon,
  label,
  value,
  tone = "default",
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone?: "default" | "accent" | "warning";
}) {
  const toneClass =
    tone === "accent"
      ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-200"
      : tone === "warning"
        ? "border-amber-400/20 bg-amber-400/10 text-amber-200"
        : "border-white/10 bg-white/5 text-slate-200";

  return (
    <div className={`rounded-full border px-3 py-2 text-xs ${toneClass}`}>
      <div className="flex items-center gap-2">
        {icon}
        <span className="font-medium">{label}</span>
        <span className="text-slate-400">{value}</span>
      </div>
    </div>
  );
}

export default function VoiceShell() {
  const [volume, setVolume] = useState(0);
  const {
    volumeRef,
    extractedDocument,
    setExtractedDocument,
    clearDocument,
    handleDocumentConfirmed,
    graphRefreshKey,
    orbState,
    sessionState,
    error,
    transcript,
    handleOrbClick: handleSessionOrbClick,
    handleInterrupt,
    handleReconnect,
    handleDismissError,
    routingResult,
    voice,
    setVoice,
    modality,
    setModality,
    textAssistMode,
    showSources,
    setShowSources,
    sendTextTurn,
    messageDraft,
    setMessageDraft,
    videoRef,
    cameraActive,
    cameraError,
    transparencyGraph,
    transparencyHeadline,
    beginMemoryGraphLoad,
    applyMemoryGraph,
    failMemoryGraph,
  } = useVoiceSession();
  const { acknowledged, acknowledge } = useDisclaimer();
  const userId = useUserId();
  const [showGraph, setShowGraph] = useState(false);

  useEffect(() => {
    let rafId: number;
    const tick = () => {
      setVolume(volumeRef.current);
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [volumeRef]);

  const handleOrbClick = () => {
    if (!acknowledged) {
      return;
    }
    handleSessionOrbClick();
  };

  const statusText =
    orbState === "idle"
      ? textAssistMode
        ? "Assistant ready for keyboard questions"
        : "Tap the orb to start a live voice session"
      : orbState === "listening"
        ? "Listening for your voice and watching the camera feed"
        : orbState === "thinking"
          ? "Routing the question through live tax agents"
          : "Speaking the current answer";

  return (
    <div className="relative min-h-screen overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(16,185,129,0.16),_transparent_35%),radial-gradient(circle_at_bottom_right,_rgba(59,130,246,0.18),_transparent_30%),linear-gradient(180deg,_#050816_0%,_#07111f_40%,_#091321_100%)] text-white">
      <DisclaimerModal acknowledged={acknowledged} onAcknowledge={acknowledge} />

      <div className="pointer-events-none absolute inset-0 opacity-40 [background-image:linear-gradient(rgba(148,163,184,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.08)_1px,transparent_1px)] [background-size:64px_64px]" />

      <div className="relative z-10 flex min-h-screen flex-col">
        <header className="border-b border-white/10 bg-slate-950/65 backdrop-blur-xl">
          <div className="mx-auto flex w-full max-w-[1600px] items-center justify-between gap-4 px-4 py-4 lg:px-6">
            <div className="flex items-center gap-4">
              <div>
                <p className="text-[11px] uppercase tracking-[0.28em] text-emerald-300/80">TaxClarity</p>
                <h1 className="text-lg font-semibold text-slate-50">Live tax guidance with citations, memory, and documents</h1>
              </div>
              {routingResult?.jurisdiction && (
                <JurisdictionBadge jurisdiction={routingResult.jurisdiction} />
              )}
            </div>

            <div className="flex items-center gap-2">
              <UploadDialog onDocumentExtracted={setExtractedDocument} />
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setShowGraph((current) => !current)}
                className="rounded-full border border-white/10 bg-white/5 text-slate-200 hover:bg-white/10"
                title={showGraph ? "Close memory graph" : "Open memory graph"}
              >
                <Network className="size-5" />
              </Button>
              <SettingsDialog
                voice={voice}
                onVoiceChange={setVoice}
                modality={modality}
                onModalityChange={setModality}
              />
            </div>
          </div>
        </header>

        <div className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col gap-4 px-4 py-4 lg:px-6">
          <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr_1fr]">
            <StatusPill
              icon={<ShieldCheck className="size-3.5" />}
              label="Session"
              value={sessionState}
              tone={sessionState === "connected" ? "accent" : "default"}
            />
            <StatusPill
              icon={<Camera className="size-3.5" />}
              label="Camera"
              value={cameraActive ? "live vision feed" : cameraError ?? "waiting"}
              tone={cameraActive ? "accent" : "warning"}
            />
            <StatusPill
              icon={<MessageSquareText className="size-3.5" />}
              label="Mode"
              value={textAssistMode ? "keyboard assist" : "voice + camera"}
            />
          </div>

          <div className="grid flex-1 gap-4 lg:grid-cols-[360px_minmax(0,1fr)_360px]">
            <div className="hidden min-h-[780px] lg:block">
              <ChatPanel
                entries={transcript}
                draft={messageDraft}
                onDraftChange={setMessageDraft}
                onSubmit={() => sendTextTurn(messageDraft)}
                disabled={sessionState === "connecting"}
                className="h-full w-full rounded-[32px] border border-white/10 bg-slate-950/70 backdrop-blur-xl"
              />
            </div>

            <div className="relative min-h-[780px] overflow-hidden rounded-[36px] border border-white/10 bg-slate-950/60 shadow-[0_40px_140px_-70px_rgba(16,185,129,0.65)] backdrop-blur-xl">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(16,185,129,0.18),_transparent_35%),radial-gradient(circle_at_bottom,_rgba(59,130,246,0.14),_transparent_35%)]" />

              <div className="relative flex h-full flex-col px-4 py-4 sm:px-6">
                <ErrorBanner
                  error={error}
                  onReconnect={handleReconnect}
                  onDismiss={handleDismissError}
                />

                <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                  <div className="max-w-2xl">
                    <p className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Live advisory workspace</p>
                    <h2 className="mt-1 text-2xl font-semibold text-slate-50">
                      Ask by voice, show a document on camera, or upload for exact extraction
                    </h2>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
                      TaxClarity keeps the live voice session, source evidence, contradiction checks,
                      uploaded forms, and the memory graph in one place.
                    </p>
                  </div>
                  <div className="rounded-3xl border border-white/10 bg-white/5 px-4 py-3 text-right">
                    <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Current status</p>
                    <p className="mt-2 text-sm font-medium text-slate-100">{statusText}</p>
                  </div>
                </div>

                <div className="grid flex-1 gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
                  <div className="relative overflow-hidden rounded-[32px] border border-white/10 bg-slate-950/70">
                    {extractedDocument ? (
                      <div className="flex h-full items-center justify-center p-4">
                        <DocumentCard
                          document={extractedDocument}
                          userId={userId}
                          onConfirmed={handleDocumentConfirmed}
                          onDismiss={clearDocument}
                        />
                      </div>
                    ) : (
                      <div className="flex h-full flex-col items-center justify-center px-6 py-8">
                        <div className="relative flex flex-col items-center">
                          <div className="absolute inset-0 blur-3xl" />
                          <VoiceOrb
                            state={orbState}
                            volume={volume}
                            onClick={handleOrbClick}
                          />
                        </div>

                        <div className="mt-8 grid w-full max-w-3xl gap-3 sm:grid-cols-3">
                          <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
                            <div className="mb-2 flex items-center gap-2 text-emerald-300">
                              <Waves className="size-4" />
                              <span className="text-xs uppercase tracking-[0.22em]">Voice</span>
                            </div>
                            <p className="text-sm text-slate-200">
                              Start a live Gemini session with real audio responses and agent routing.
                            </p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
                            <div className="mb-2 flex items-center gap-2 text-cyan-300">
                              <Camera className="size-4" />
                              <span className="text-xs uppercase tracking-[0.22em]">Camera</span>
                            </div>
                            <p className="text-sm text-slate-200">
                              The session sends camera frames continuously so the assistant can react to what you show.
                            </p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
                            <div className="mb-2 flex items-center gap-2 text-amber-300">
                              <FileText className="size-4" />
                              <span className="text-xs uppercase tracking-[0.22em]">Documents</span>
                            </div>
                            <p className="text-sm text-slate-200">
                              Upload Form 16 or US forms to extract fields, persist them, and compute taxes.
                            </p>
                          </div>
                        </div>

                        {orbState !== "idle" && (
                          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={handleInterrupt}
                              className="border-white/10 bg-white/5 text-slate-100 hover:bg-white/10"
                            >
                              Interrupt
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setShowGraph((current) => !current)}
                              className="border-white/10 bg-white/5 text-slate-100 hover:bg-white/10"
                            >
                              {showGraph ? "Close memory graph" : "Open memory graph"}
                            </Button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="flex flex-col gap-4">
                    <div className="overflow-hidden rounded-[28px] border border-white/10 bg-slate-950/70">
                      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Camera feed</p>
                          <p className="text-sm text-slate-200">
                            {cameraActive
                              ? "Frames are being sent to the live session"
                              : cameraError ?? "Camera starts when the session connects"}
                          </p>
                        </div>
                        <Camera className="size-5 text-cyan-300" />
                      </div>
                      <div className="aspect-video bg-slate-950">
                        <video
                          ref={videoRef}
                          autoPlay
                          playsInline
                          muted
                          className={`h-full w-full scale-x-[-1] object-cover ${cameraActive ? "opacity-100" : "opacity-40"}`}
                        />
                      </div>
                    </div>

                    <div className="rounded-[28px] border border-white/10 bg-slate-950/70 p-4">
                      <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Quick actions</p>
                      <div className="mt-3 grid gap-2">
                        <Button
                          variant="outline"
                          className="justify-start border-white/10 bg-white/5 text-slate-100 hover:bg-white/10"
                          onClick={() => sendTextTurn("I work at TCS, what tax saving options do I have?")}
                        >
                          Ask a salary deduction question
                        </Button>
                        <Button
                          variant="outline"
                          className="justify-start border-white/10 bg-white/5 text-slate-100 hover:bg-white/10"
                          onClick={() => sendTextTurn("I'm moving to the US on H-1B. How does this affect my taxes?")}
                        >
                          Ask a cross-border question
                        </Button>
                        <Button
                          variant="outline"
                          className="justify-start border-white/10 bg-white/5 text-slate-100 hover:bg-white/10"
                          onClick={() => setShowGraph((current) => !current)}
                        >
                          {showGraph ? "Close the knowledge graph" : "Inspect the knowledge graph"}
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-4 lg:hidden">
                  <ChatPanel
                    entries={transcript}
                    draft={messageDraft}
                    onDraftChange={setMessageDraft}
                    onSubmit={() => sendTextTurn(messageDraft)}
                    disabled={sessionState === "connecting"}
                    className="w-full rounded-[28px] border border-white/10 bg-slate-950/70 backdrop-blur-xl"
                  />
                </div>
              </div>
            </div>

            <div className="hidden lg:block">
              <div className="flex h-full min-h-[780px] flex-col overflow-hidden rounded-[32px] border border-white/10 bg-slate-950/70 backdrop-blur-xl">
                <div className="border-b border-white/10 px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Evidence rail</p>
                  <h3 className="mt-1 text-lg font-semibold text-slate-50">Citations, conflicts, and jurisdiction</h3>
                </div>
                {routingResult ? (
                  <SourcePanel
                    claims={routingResult.claims}
                    jurisdiction={routingResult.jurisdiction}
                    contradictions={routingResult.contradictions}
                    sourceStatuses={routingResult.source_statuses}
                    visible
                    onClose={() => setShowSources(false)}
                    docked
                  />
                ) : (
                  <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-slate-400">
                    Ask a question to populate live evidence cards from the tax agents.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="lg:hidden">
          {routingResult && (
            <SourcePanel
              claims={routingResult.claims}
              jurisdiction={routingResult.jurisdiction}
              contradictions={routingResult.contradictions}
              sourceStatuses={routingResult.source_statuses}
              visible={showSources}
              onClose={() => setShowSources(false)}
            />
          )}
        </div>

        <GraphPanel
          userId={userId}
          visible={showGraph}
          onClose={() => setShowGraph(false)}
          refreshKey={graphRefreshKey}
          graphState={transparencyGraph}
          headline={transparencyHeadline}
          onMemoryLoadStart={beginMemoryGraphLoad}
          onMemoryLoaded={applyMemoryGraph}
          onMemoryLoadFailed={failMemoryGraph}
        />
      </div>
    </div>
  );
}
