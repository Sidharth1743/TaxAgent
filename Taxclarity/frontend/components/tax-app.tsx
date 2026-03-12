"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { VoiceOrb, type OrbState } from "./voice-orb";
import { GraphPanel } from "./graph-panel";
import { SourcePanel, extractSources, type SourceItem } from "./source-cards";
import { ChatInput, ChatInputTextArea, ChatInputSubmit, ChatInputCamera } from "./chat-input";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Item, ItemContent, ItemMedia, ItemTitle, ItemDescription } from "@/components/ui/item";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";
import { extractEmotion, selectContent, fetchKlipyContent, type KlipyMedia } from "@/lib/klipy";
import { KlipyMediaCard } from "@/components/ui/klipy-media";
import {
  NetworkIcon,
  FileTextIcon,
  PanelRightIcon,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Message {
  id: string;
  role: "user" | "agent" | "system" | "tool";
  content: string;
  citations?: string[];
  media?: KlipyMedia;
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

function getWsUrl(): string {
  const env = process.env.NEXT_PUBLIC_WS_URL;
  if (env) return env;
  if (typeof window === "undefined") return "ws://localhost:8003/ws";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.hostname}:8003/ws`;
}

function getApiUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL || "";
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function TaxClarityApp() {
  // State
  const [connected, setConnected] = useState(false);
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [messages, setMessages] = useState<Message[]>([]);
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [input, setInput] = useState("");
  const [voiceLevel, setVoiceLevel] = useState(0);
  const [isListening, setIsListening] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [rightOpen, setRightOpen] = useState(true);

  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const micCtxRef = useRef<AudioContext | null>(null);
  const micProcRef = useRef<ScriptProcessorNode | null>(null);
  const playQueueRef = useRef<ArrayBuffer[]>([]);
  const isPlayingRef = useRef(false);
  const currentAgentMsgIdRef = useRef<string | null>(null);
  const currentAgentTextRef = useRef<string>("");        // accumulates text for KLIPY (text + output_transcription)
  const chatEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const userId = useRef("user_" + Math.random().toString(36).slice(2, 8));
  const sessionId = useRef("session_" + Math.random().toString(36).slice(2, 10));

  // Scroll to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ---------------------------------------------------------------------------
  // WebSocket
  // ---------------------------------------------------------------------------

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;

    const ws = new WebSocket(getWsUrl());
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setOrbState("idle");
      ws.send(JSON.stringify({
        type: "start",
        session_id: sessionId.current,
        user_id: userId.current,
        voice: "Aoede",
        response_modalities: ["AUDIO"],
      }));
    };

    ws.onmessage = (event) => {
      try {
        handleServerMessage(JSON.parse(event.data));
      } catch {}
    };

    ws.onclose = () => {
      setConnected(false);
      setOrbState("idle");
      wsRef.current = null;
      setTimeout(connect, 3000);
    };

    ws.onerror = () => setOrbState("error");
  }, []);

  useEffect(() => {
    connect();
    return () => { wsRef.current?.close(); };
  }, [connect]);

  // ---------------------------------------------------------------------------
  // Server Message Handler
  // ---------------------------------------------------------------------------

  const addMsg = useCallback((msg: Message) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const appendToAgent = useCallback((text: string) => {
    currentAgentTextRef.current += text;
    setMessages((prev) => {
      const id = currentAgentMsgIdRef.current;
      if (!id) {
        const newId = "agent_" + Date.now();
        currentAgentMsgIdRef.current = newId;
        return [...prev, { id: newId, role: "agent", content: text }];
      }
      return prev.map((m) => m.id === id ? { ...m, content: m.content + text } : m);
    });
  }, []);

  const handleServerMessage = useCallback((msg: any) => {
    switch (msg.type) {
      case "connected":
        addMsg({ id: "sys_" + Date.now(), role: "system", content: `Connected to ${msg.model || "Gemini Live"}` });
        break;

      case "transcript": // partial streaming text — show immediately, don't wait
      case "text": {
        setOrbState("speaking");
        setIsLoading(true);
        appendToAgent(msg.text || msg.content || "");
        break;
      }

      case "output_transcription":
        // Voice mode: agent spoke → transcription arrives here, not via "text"
        // Only use the finished transcription to avoid duplicating partial chunks
        if (msg.finished !== false) {
          appendToAgent(msg.content);
        }
        break;

      case "input_transcription":
        // Voice mode: show what the user actually said
        if (msg.finished !== false && msg.content?.trim()) {
          addMsg({ id: "user_voice_" + Date.now(), role: "user", content: msg.content });
        }
        break;

      case "user_text":
        if (msg.text?.trim()) {
          addMsg({ id: "user_" + Date.now(), role: "user", content: msg.text });
        }
        break;

      case "thinking":
        setOrbState("thinking");
        setIsLoading(true);
        break;

      case "tool_call":
        setOrbState("thinking");
        setIsLoading(true);
        addMsg({
          id: "tool_" + Date.now(),
          role: "tool",
          content: `${msg.name}(${JSON.stringify(msg.args || {}).slice(0, 50)})`,
        });
        break;

      case "content":
        if (msg.content) {
          const newSources = extractSources(msg.content);
          if (newSources.length) {
            setSources((prev) => [...prev, ...newSources]);
          }
          if (msg.content.claims && currentAgentMsgIdRef.current) {
            const urls = (msg.content.claims as any[]).flatMap((c: any) => c.citations || []);
            if (urls.length) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === currentAgentMsgIdRef.current
                    ? { ...m, citations: [...new Set([...(m.citations || []), ...urls])] }
                    : m,
                ),
              );
            }
          }
        }
        break;

      case "turnComplete":
      case "turn_complete": {
        const completedMsgId = currentAgentMsgIdRef.current;
        const completedText = currentAgentTextRef.current;
        // Reset refs before async work
        currentAgentMsgIdRef.current = null;
        currentAgentTextRef.current = "";
        setIsLoading(false);
        setOrbState(isListening ? "listening" : "idle");

        // Fire-and-forget KLIPY fetch — never blocks the chat
        // Uses accumulated text (covers both text + output_transcription paths)
        if (completedMsgId && completedText.trim()) {
          const { emotion, jurisdiction } = extractEmotion(completedText);
          const req = selectContent(emotion, jurisdiction);
          if (req) {
            fetchKlipyContent(req.api, req.query, req.locale, userId.current)
              .then((media) => {
                if (!media) return;
                setMessages((msgs) =>
                  msgs.map((m) =>
                    m.id === completedMsgId ? { ...m, media } : m,
                  ),
                );
              });
          }
        }
        break;
      }

      case "interrupted":
        currentAgentMsgIdRef.current = null;
        currentAgentTextRef.current = "";
        setIsLoading(false);
        stopPlayback();
        setOrbState("listening");
        break;

      case "audio":
        if (msg.data) {
          handleAudioOutput(base64ToArrayBuffer(msg.data));
        }
        break;

      case "audio_level":
        setVoiceLevel(msg.level || 0);
        break;

      case "error":
        setOrbState("error");
        setIsLoading(false);
        addMsg({ id: "err_" + Date.now(), role: "system", content: `Error: ${msg.message}` });
        break;
    }
  }, [addMsg, appendToAgent, isListening]);

  // ---------------------------------------------------------------------------
  // Audio
  // ---------------------------------------------------------------------------

  const startMic = useCallback(async () => {
    if (micStreamRef.current) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      const ctx = new AudioContext({ sampleRate: 16000 });
      const source = ctx.createMediaStreamSource(stream);
      const proc = ctx.createScriptProcessor(4096, 1, 1);

      proc.onaudioprocess = (e) => {
        const ws = wsRef.current;
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const f32 = e.inputBuffer.getChannelData(0);
        const i16 = new Int16Array(f32.length);
        let sum = 0;
        for (let i = 0; i < f32.length; i++) {
          i16[i] = Math.max(-32768, Math.min(32767, Math.floor(f32[i] * 32767)));
          sum += f32[i] * f32[i];
        }
        ws.send(JSON.stringify({ type: "audio", data: arrayBufferToBase64(i16.buffer) }));
        setVoiceLevel(Math.min(1, Math.sqrt(sum / f32.length) * 5));
      };

      source.connect(proc);
      proc.connect(ctx.destination);
      micStreamRef.current = stream;
      micCtxRef.current = ctx;
      micProcRef.current = proc;
      setIsListening(true);
      setOrbState("listening");
    } catch {
      setOrbState("error");
      addMsg({ id: "mic_err_" + Date.now(), role: "system", content: "Microphone denied. Use text input." });
    }
  }, [addMsg]);

  const stopMic = useCallback(() => {
    micProcRef.current?.disconnect();
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micCtxRef.current?.close();
    micStreamRef.current = null;
    micCtxRef.current = null;
    micProcRef.current = null;
    setIsListening(false);
    setOrbState("idle");
  }, []);

  const handleAudioOutput = useCallback((buf: ArrayBuffer) => {
    playQueueRef.current.push(buf);
    if (!isPlayingRef.current) playNext();
  }, []);

  const playNext = useCallback(() => {
    if (!playQueueRef.current.length) { isPlayingRef.current = false; return; }
    isPlayingRef.current = true;
    setOrbState("speaking");
    const buf = playQueueRef.current.shift()!;
    try {
      const ctx = new AudioContext({ sampleRate: 24000 });
      const i16 = new Int16Array(buf);
      const f32 = new Float32Array(i16.length);
      for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768.0;
      const ab = ctx.createBuffer(1, f32.length, 24000);
      ab.getChannelData(0).set(f32);
      const src = ctx.createBufferSource();
      src.buffer = ab;
      src.connect(ctx.destination);
      src.onended = () => { ctx.close(); playNext(); };
      src.start();
    } catch {
      isPlayingRef.current = false;
      playNext();
    }
  }, []);

  const stopPlayback = useCallback(() => {
    playQueueRef.current = [];
    isPlayingRef.current = false;
  }, []);

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  const sendText = useCallback((text: string) => {
    if (!text.trim()) return;
    addMsg({ id: "user_" + Date.now(), role: "user", content: text });
    currentAgentMsgIdRef.current = null;

    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connect();
      const poll = setInterval(() => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          clearInterval(poll);
          wsRef.current.send(JSON.stringify({ type: "text", text }));
          setOrbState("thinking");
          setIsLoading(true);
        }
      }, 200);
      return;
    }
    ws.send(JSON.stringify({ type: "text", text }));
    setOrbState("thinking");
    setIsLoading(true);
  }, [connect, addMsg]);

  const handleSubmit = useCallback(() => {
    sendText(input);
    setInput("");
  }, [input, sendText]);

  const handleDismissMedia = useCallback((id: string) => {
    setMessages((prev) =>
      prev.map((m) => m.id === id ? { ...m, media: undefined } : m),
    );
  }, []);

  const handleStop = useCallback(() => {
    stopPlayback();
    setIsLoading(false);
    setOrbState("idle");
  }, [stopPlayback]);

  const handleOrbClick = useCallback(() => {
    if (!connected) { connect(); return; }
    if (isListening) stopMic(); else startMic();
  }, [connected, connect, isListening, startMic, stopMic]);

  const handleCamera = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const b64 = (ev.target?.result as string).split(",")[1];
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({ type: "video", data: b64, mime_type: file.type || "image/jpeg" }));
      ws.send(JSON.stringify({ type: "text", text: `I've uploaded a document (${file.name}). Please analyze it.` }));
      addMsg({ id: "user_" + Date.now(), role: "user", content: `[Uploaded ${file.name}]` });
      setOrbState("thinking");
      setIsLoading(true);
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  }, [addMsg]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <SidebarProvider
      defaultOpen={true}
      style={{ "--sidebar-width": "280px" } as React.CSSProperties}
    >
      {/* ── Left Sidebar: Knowledge Graph ── */}
      <Sidebar side="left" variant="sidebar" collapsible="offcanvas">
        <SidebarHeader className="border-b border-sidebar-border">
          <div className="flex items-center gap-2 px-1">
            <NetworkIcon className="size-4 text-muted-foreground" />
            <span className="text-sm font-medium">Knowledge Graph</span>
          </div>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup className="p-0 flex-1">
            <SidebarGroupContent className="h-full">
              <GraphPanel userId={userId.current} apiUrl={getApiUrl()} />
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarRail />
      </Sidebar>

      {/* ── Main Content ── */}
      <SidebarInset className="flex flex-col h-screen">
        {/* Header */}
        <header className="flex items-center justify-between h-12 px-3 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <SidebarTrigger />
            <div className="h-4 w-px bg-border" />
            <div className="flex items-center gap-2">
              <div className="size-6 rounded-md bg-primary/10 flex items-center justify-center">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
                  <path d="M12 2L2 7l10 5 10-5-10-5z" fill="currentColor" className="text-primary" opacity="0.8"/>
                  <path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" className="text-primary" strokeWidth="1.5" fill="none" strokeLinecap="round"/>
                </svg>
              </div>
              <div>
                <h1 className="text-sm font-semibold tracking-tight">TaxClarity</h1>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Connection status */}
            <div className={cn(
              "flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-mono",
              connected
                ? "text-emerald-400"
                : "text-muted-foreground",
            )}>
              <span className={cn(
                "size-1.5 rounded-full",
                connected ? "bg-emerald-400" : "bg-muted-foreground",
              )} />
              {connected ? "Live" : "Offline"}
            </div>

            <div className="h-4 w-px bg-border" />

            {/* Toggle right panel */}
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setRightOpen(!rightOpen)}
              className={cn(rightOpen && "bg-accent")}
            >
              <PanelRightIcon className="size-4" />
              <span className="sr-only">Toggle Sources</span>
            </Button>
          </div>
        </header>

        {/* Body: Center + optional right panel */}
        <div className="flex flex-1 min-h-0">
          {/* Center: Orb + Chat + Input */}
          <section className="flex-1 min-w-0 flex flex-col">
            {/* Orb */}
            <div className="flex justify-center py-5 shrink-0">
              <VoiceOrb state={orbState} voiceLevel={voiceLevel} onClick={handleOrbClick} />
            </div>

            {/* Chat */}
            <div className="flex-1 overflow-y-auto px-4 pb-2 min-h-0">
              {messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center">
                  <p className="text-sm font-medium text-muted-foreground">Ask anything about taxes</p>
                  <p className="text-xs text-muted-foreground/60 mt-1">Voice or text &middot; India &amp; US &middot; Expert sources</p>
                </div>
              ) : (
                <div className="max-w-2xl mx-auto space-y-3">
                  {messages.map((m) => (
                    <MessageBubble key={m.id} message={m} onDismissMedia={handleDismissMedia} />
                  ))}
                  <div ref={chatEndRef} />
                </div>
              )}
            </div>

            {/* Input */}
            <div className="px-4 pb-4 pt-2 shrink-0">
              <div className="max-w-2xl mx-auto">
                <ChatInput
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onSubmit={handleSubmit}
                  loading={isLoading}
                  onStop={handleStop}
                >
                  <div className="flex items-end gap-1 w-full">
                    <ChatInputCamera onCamera={handleCamera} />
                    <ChatInputTextArea placeholder="Ask a tax question..." />
                    <ChatInputSubmit />
                  </div>
                </ChatInput>
                <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleFileSelect} />
              </div>
            </div>
          </section>

          {/* Right Panel: Sources (not a shadcn sidebar — just a collapsible aside) */}
          {rightOpen && (
            <aside className="w-[280px] shrink-0 border-l border-border hidden lg:flex">
              <SourcePanel sources={sources} />
            </aside>
          )}
        </div>

        {/* Footer */}
        <footer className="flex items-center justify-between h-8 px-3 border-t border-border shrink-0">
          <div className="flex gap-1">
            {[
              { key: "india", label: "India", flag: "IN" },
              { key: "us", label: "USA", flag: "US" },
              { key: "cross", label: "Cross-border", flag: "CB" },
            ].map((j, i) => (
              <Button
                key={j.key}
                variant="ghost"
                size="xs"
                className={cn(
                  "rounded-full font-mono gap-1",
                  i === 0 && "text-emerald-400",
                )}
              >
                <span className="text-[8px] font-semibold opacity-60">{j.flag}</span>
                {j.label}
              </Button>
            ))}
          </div>
          <div className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground">
            <span>Gemini Live</span>
            <span className="size-0.5 rounded-full bg-muted-foreground/50" />
            <span>ADK</span>
            <span className="size-0.5 rounded-full bg-muted-foreground/50" />
            <span>Spanner</span>
          </div>
        </footer>
      </SidebarInset>
    </SidebarProvider>
  );
}

// ---------------------------------------------------------------------------
// Message Bubble
// ---------------------------------------------------------------------------

function MessageBubble({ message, onDismissMedia }: { message: Message; onDismissMedia?: (id: string) => void }) {
  if (message.role === "system") {
    const isError = message.content.startsWith("Error:");
    return (
      <div className="max-w-md mx-auto animate-fade-in">
        <Item variant="muted">
          <ItemMedia>
            <div className={cn(
              "size-4 rounded-full flex items-center justify-center text-[8px]",
              isError ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary",
            )}>
              {isError ? "!" : "•"}
            </div>
          </ItemMedia>
          <ItemContent>
            <ItemTitle className={cn(
              "line-clamp-2 font-mono",
              isError ? "text-destructive" : "text-muted-foreground",
            )}>
              {message.content}
            </ItemTitle>
          </ItemContent>
        </Item>
      </div>
    );
  }

  if (message.role === "tool") {
    const match = message.content.match(/^(\w+)\((.*)?\)$/);
    const toolName = match ? match[1] : message.content;
    const toolArgs = match?.[2] || "";

    const TOOL_LABELS: Record<string, string> = {
      search_tax_knowledge: "Searching tax sources",
      get_legal_context: "Fetching legal context",
      get_user_memory: "Loading your profile",
      save_to_memory: "Saving to memory",
      analyze_document: "Analyzing document",
    };

    return (
      <div className="max-w-md mx-auto animate-fade-in">
        <Item variant="muted">
          <ItemMedia>
            <Spinner className="text-amber-400" />
          </ItemMedia>
          <ItemContent>
            <ItemTitle className="line-clamp-1 text-amber-300/80">
              {TOOL_LABELS[toolName] || toolName}
            </ItemTitle>
            {toolArgs && (
              <ItemDescription className="line-clamp-1 font-mono">
                {toolArgs}
              </ItemDescription>
            )}
          </ItemContent>
        </Item>
      </div>
    );
  }

  const isUser = message.role === "user";

  return (
    <div className={cn("animate-fade-in", isUser ? "flex justify-end" : "flex justify-start")}>
      <div
        className={cn(
          "max-w-[80%] px-3.5 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-secondary rounded-2xl rounded-br-md text-secondary-foreground"
            : "bg-card border border-border rounded-2xl rounded-bl-md text-card-foreground",
        )}
      >
        <div className="whitespace-pre-wrap">{message.content}</div>

        {/* KLIPY media */}
        {!isUser && message.media && onDismissMedia && (
          <KlipyMediaCard
            media={message.media}
            onDismiss={() => onDismissMedia(message.id)}
          />
        )}

        {/* Citations */}
        {message.citations && message.citations.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2 pt-2 border-t border-border">
            {[...new Set(message.citations)].map((url) => {
              let label = url;
              try { label = new URL(url).hostname.replace("www.", "").split(".")[0]; } catch {}
              return (
                <a
                  key={url}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono text-primary/70 bg-primary/5 border border-primary/10 hover:bg-primary/10 transition-colors"
                >
                  <span className="size-1 rounded-full bg-primary/60" />
                  {label}
                </a>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
