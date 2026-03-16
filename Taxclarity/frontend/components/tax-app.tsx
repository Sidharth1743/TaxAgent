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
import { extractEmotion, selectContent, fetchKlipyContent, type KlipyMedia, type ContentRequest } from "@/lib/klipy";
import { KlipyMediaCard } from "@/components/ui/klipy-media";
import {
  NetworkIcon,
  FileTextIcon,
  PanelRightIcon,
  MicIcon,
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
  meta?: {
    kind?: "query_builder" | "dispatch_agents" | "agent_status";
    data?: any;
  };
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
  const env = process.env.NEXT_PUBLIC_API_URL;
  if (env) return env;
  if (typeof window === "undefined") return "http://localhost:8006";
  return `${window.location.protocol}//${window.location.hostname}:8006`;
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

function extractCitationUrl(citation: any): string | null {
  if (!citation) return null;
  if (typeof citation === "string") return citation;
  if (typeof citation === "object") {
    return (
      citation.url ||
      citation.link ||
      citation.href ||
      null
    );
  }
  return null;
}

type KlipyPayload = {
  content_type?: "gif" | "meme" | "sticker" | "clip" | "none";
  query?: string;
  intensity?: "low" | "medium" | "high";
  moment?: string;
};

function parseKlipyBlock(text: string): { cleanText: string; klipy: KlipyPayload | null } {
  if (!text) return { cleanText: text, klipy: null };
  const match = text.match(/<klipy>\s*([\s\S]*?)(?:<\/klipy>|<\/kl_y>|$)/i);
  if (!match) return { cleanText: text, klipy: null };
  const raw = match[1];
  let parsed: KlipyPayload | null = null;
  try {
    parsed = JSON.parse(raw);
  } catch {
    parsed = null;
  }
  const cleanText = text.replace(match[0], "").trim();
  return { cleanText, klipy: parsed };
}

function stripKlipyNoise(text: string, klipy: KlipyPayload | null): string {
  if (!text) return text;
  const noisy = new Set<string>([
    "welcome wave hi",
    "welcome back hi",
    "loading thinking",
    "processing thinking",
    "thinking face loading",
    "trophy winner champion celebration",
    "don't worry got you",
    "price amount toast",
  ]);
  if (klipy?.query) noisy.add(klipy.query.toLowerCase());
  return text
    .split("\n")
    .filter((line) => {
      const clean = line.trim();
      if (!clean) return false;
      const lower = clean.toLowerCase();
      if (noisy.has(lower)) return false;
      if (lower.startsWith("[klipy")) return false;
      if (lower.includes("<klipy>")) return false;
      if (lower.startsWith("saul goodman:")) return false;
      if (lower.startsWith("user:")) return false;
      if (lower.startsWith("[session")) return false;
      return true;
    })
    .join("\n")
    .trim();
}

function stripKlipyBlocks(text: string): string {
  if (!text) return text;
  return text.replace(/<klipy>[\s\S]*?(?:<\/klipy>|<\/kl_y>|$)/gi, "").trim();
}

function getTranscriptionText(msg: any, kind: "input" | "output"): string {
  if (!msg) return "";
  const direct = msg.content ?? msg.text ?? msg.transcript;
  if (typeof direct === "string") return direct;
  if (direct && typeof direct === "object") {
    const inner = (direct as any).text ?? (direct as any).content;
    if (typeof inner === "string") return inner;
  }
  const snake = msg?.[`${kind}_transcription`]?.text;
  if (typeof snake === "string") return snake;
  const serverSnake = msg?.server_content?.[`${kind}_transcription`]?.text;
  if (typeof serverSnake === "string") return serverSnake;
  const camelKey = kind === "input" ? "inputTranscription" : "outputTranscription";
  const camel = msg?.serverContent?.[camelKey]?.text;
  if (typeof camel === "string") return camel;
  const nested = msg?.transcription?.text;
  if (typeof nested === "string") return nested;
  return "";
}

function mapKlipyRequest(payload: KlipyPayload | null): ContentRequest | null {
  if (!payload) return null;
  if (!payload.content_type || payload.content_type === "none") return null;
  const query = (payload.query || "").trim();
  if (!query) return null;
  switch (payload.content_type) {
    case "gif":
      return { api: "gifs", query };
    case "meme":
      return { api: "static-memes", query };
    case "sticker":
      return { api: "stickers", query };
    case "clip":
      // Klipy doesn't support clips directly; fall back to GIFs.
      return { api: "gifs", query };
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function SaulGoodmanApp() {
  // State
  const [connected, setConnected] = useState(false);
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [messages, setMessages] = useState<Message[]>([]);
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [input, setInput] = useState("");
  const [voiceLevel, setVoiceLevel] = useState(0);
  const [micLevel, setMicLevel] = useState(0);
  const [isListening, setIsListening] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [rightOpen, setRightOpen] = useState(true);
  const [liveUserText, setLiveUserText] = useState("");
  const [liveAgentText, setLiveAgentText] = useState("");
  const [wsUrl] = useState(() => getWsUrl());
  const [demoMode, setDemoMode] = useState(false);
  const [demoReady, setDemoReady] = useState(false);

  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const micCtxRef = useRef<AudioContext | null>(null);
  const micProcRef = useRef<ScriptProcessorNode | null>(null);
  const playQueueRef = useRef<ArrayBuffer[]>([]);
  const isPlayingRef = useRef(false);
  const currentAgentMsgIdRef = useRef<string | null>(null);
  const currentAgentTextRef = useRef<string>("");        // accumulates text for KLIPY (text + output_transcription)
  const lastKlipyAtRef = useRef(0);
  const micFrameCountRef = useRef(0);
  const lastWsDropLogRef = useRef(0);
  const userVoiceMsgIdRef = useRef<string | null>(null);
  const userVoiceBufferRef = useRef<string>("");
  const agentVoiceBufferRef = useRef<string>("");
  const userVoiceDebounceRef = useRef<number | null>(null);
  const inputTxLogRef = useRef(0);
  const outputTxLogRef = useRef(0);
  const rawTxLogRef = useRef(0);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const demoRecRef = useRef<any>(null);
  const demoTranscriptRef = useRef<string>("");
  const demoSilenceTimerRef = useRef<number | null>(null);
  const demoLastCommitRef = useRef<string>("");
  const userId = useRef<string>("");
  const sessionId = useRef<string>("");
  const msgSeqRef = useRef(0);
  const turnSeqRef = useRef(0);
  const currentTurnRef = useRef<string | null>(null);
  const turnUserCommittedRef = useRef(false);
  const turnAgentCommittedRef = useRef(false);
  const currentAgentMsgAddedRef = useRef(false);
  const lastCompletedTurnRef = useRef(0);
  const connectedBannerShownRef = useRef(false);
  const connectTimerRef = useRef<number | null>(null);
  const handleServerMessageRef = useRef<(msg: any) => void>(() => {});

  useEffect(() => {
    if (userId.current) return;
    const stored = typeof window !== "undefined" ? window.localStorage.getItem("taxclarity_user_id") : null;
    if (stored) {
      userId.current = stored;
    } else {
      const fresh = "user_" + Math.random().toString(36).slice(2, 10);
      userId.current = fresh;
      if (typeof window !== "undefined") {
        window.localStorage.setItem("taxclarity_user_id", fresh);
      }
    }
    if (!sessionId.current) {
      sessionId.current = "session_" + Math.random().toString(36).slice(2, 10);
    }
  }, []);

  const nextMsgId = useCallback((prefix: string) => {
    msgSeqRef.current += 1;
    return `${prefix}_${Date.now()}_${msgSeqRef.current}`;
  }, []);

  const ensureTurn = useCallback(() => {
    if (!currentTurnRef.current) {
      turnSeqRef.current += 1;
      currentTurnRef.current = `turn_${turnSeqRef.current}`;
      turnUserCommittedRef.current = false;
      turnAgentCommittedRef.current = false;
      currentAgentMsgAddedRef.current = false;
      // user voice is live-only, no persistent message until turnComplete
      currentAgentMsgIdRef.current = null;
      userVoiceMsgIdRef.current = null;
      currentAgentTextRef.current = "";
    }
  }, []);

  // Scroll to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (messages.length > 0) {
      const ids = messages.map((m) => m.id);
      const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
      if (dupes.length) {
        console.warn("[CHAT] duplicate ids", dupes);
      }
      console.log("[CHAT] messages", messages.length, ids);
    }
  }, [messages]);

  // ---------------------------------------------------------------------------
  // WebSocket
  // ---------------------------------------------------------------------------

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
        const newId = nextMsgId("agent");
        currentAgentMsgIdRef.current = newId;
        return [...prev, { id: newId, role: "agent", content: text }];
      }
      return prev.map((m) => m.id === id ? { ...m, content: m.content + text } : m);
    });
  }, []);

  const setAgentLiveText = useCallback((text: string) => {
    const cleaned = stripKlipyBlocks(text);
    currentAgentTextRef.current = cleaned;
    setLiveAgentText(cleaned);
  }, []);

  const setUserVoiceText = useCallback((text: string) => {
    setLiveUserText(text);
  }, []);

  const finalizeUserVoice = useCallback(() => {
    if (userVoiceDebounceRef.current) {
      window.clearTimeout(userVoiceDebounceRef.current);
      userVoiceDebounceRef.current = null;
    }
    const text = userVoiceBufferRef.current.trim();
    if (text) {
      setUserVoiceText(text);
    }
    userVoiceBufferRef.current = "";
    userVoiceMsgIdRef.current = null;
  }, [setUserVoiceText]);

  const scheduleDemoCommit = useCallback(() => {
    if (demoSilenceTimerRef.current) {
      window.clearTimeout(demoSilenceTimerRef.current);
    }
    demoSilenceTimerRef.current = window.setTimeout(() => {
      if (isLoading) {
        scheduleDemoCommit();
        return;
      }
      const text = demoTranscriptRef.current.trim();
      if (!text || text === demoLastCommitRef.current) return;
      demoLastCommitRef.current = text;
      addMsg({ id: nextMsgId("user"), role: "user", content: text });
      demoTranscriptRef.current = "";
      setUserVoiceText("");
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "text", text }));
        setOrbState("thinking");
        setIsLoading(true);
      }
    }, 2000);
  }, [addMsg, isLoading, setUserVoiceText]);

  const startDemoRecognition = useCallback(() => {
    if (demoRecRef.current) return;
    const SpeechRecognition: any =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn("[DEMO] SpeechRecognition not available");
      return;
    }
    const rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.onresult = (event: any) => {
      let finalText = "";
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const transcript = result[0]?.transcript || "";
        if (result.isFinal) finalText += transcript;
        else interimText += transcript;
      }
      if (finalText) {
        demoTranscriptRef.current = (demoTranscriptRef.current + " " + finalText).trim();
      }
      const live = (demoTranscriptRef.current + " " + interimText).trim();
      if (live) {
        setUserVoiceText(live);
        scheduleDemoCommit();
      }
    };
    rec.onend = () => {
      if (demoMode && isListening) {
        try { rec.start(); } catch {}
      }
    };
    rec.onerror = (e: any) => {
      console.warn("[DEMO] speech recognition error", e?.error || e);
    };
    demoRecRef.current = rec;
    try { rec.start(); } catch {}
  }, [demoMode, isListening, scheduleDemoCommit, setUserVoiceText]);

  const stopDemoRecognition = useCallback(() => {
    const rec = demoRecRef.current;
    if (rec) {
      try { rec.onresult = null; rec.onend = null; rec.stop(); } catch {}
    }
    demoRecRef.current = null;
    demoTranscriptRef.current = "";
    if (demoSilenceTimerRef.current) {
      window.clearTimeout(demoSilenceTimerRef.current);
      demoSilenceTimerRef.current = null;
    }
    setUserVoiceText("");
  }, []);

  const handleServerMessage = useCallback((msg: any) => {
    switch (msg.type) {
      case "connected":
        if (!connectedBannerShownRef.current) {
          connectedBannerShownRef.current = true;
          addMsg({
            id: nextMsgId("sys"),
            role: "system",
            content: "Connected. Click the orb to enable the microphone.",
          });
        }
        break;

      case "demo_mode":
        setDemoMode(Boolean(msg.enabled));
        setDemoReady(Boolean(msg.enabled));
        break;

      case "transcript": // partial streaming text — show immediately, don't wait
      case "text": {
        setOrbState("speaking");
        setIsLoading(true);
        setUserVoiceText("");
        const chunk = msg.text || msg.content || "";
        appendToAgent(chunk);
        break;
      }

      case "output_transcription":
        // Voice mode: agent spoke → transcription arrives here, not via "text"
        {
          if (demoMode) {
            break;
          }
          ensureTurn();
          const text = getTranscriptionText(msg, "output");
          if (!text) {
            if (outputTxLogRef.current < 3) {
              outputTxLogRef.current += 1;
              console.warn("[WS] output_transcription missing text", msg);
            }
            break;
          }
          if (outputTxLogRef.current < 3) {
            outputTxLogRef.current += 1;
            console.debug("[WS] output_transcription text", text);
          }
          // Accumulate chunks and commit on turnComplete.
          agentVoiceBufferRef.current = (agentVoiceBufferRef.current + text).trimStart();
          currentAgentTextRef.current = agentVoiceBufferRef.current;
          setAgentLiveText(agentVoiceBufferRef.current);
        }
        break;

      case "input_transcription":
        // Voice mode: show what the user actually said
        {
          if (demoMode) {
            userVoiceBufferRef.current = "";
            break;
          }
          ensureTurn();
          const text = getTranscriptionText(msg, "input");
          if (!text || !text.trim()) {
            if (inputTxLogRef.current < 3) {
              inputTxLogRef.current += 1;
              console.warn("[WS] input_transcription missing text", msg);
            }
            break;
          }
          if (inputTxLogRef.current < 3) {
            inputTxLogRef.current += 1;
            console.debug("[WS] input_transcription text", text);
          }
          userVoiceBufferRef.current = (userVoiceBufferRef.current + text).trimStart();
          setUserVoiceText(userVoiceBufferRef.current);
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
        if (msg.name === "query_builder") {
          addMsg({
            id: nextMsgId("sys"),
            role: "system",
            content: "Query Builder → UserTaxContext",
            meta: { kind: "query_builder", data: msg.args || {} },
          });
          break;
        }
        if (msg.name === "dispatch_agents") {
          addMsg({
            id: nextMsgId("sys"),
            role: "system",
            content: "Dispatching agents…",
            meta: { kind: "dispatch_agents", data: msg.args || {} },
          });
          break;
        }
        if (msg.name === "agent_status") {
          addMsg({
            id: nextMsgId("sys"),
            role: "system",
            content: "Agent status",
            meta: { kind: "agent_status", data: msg.args || {} },
          });
          break;
        }
        addMsg({
          id: nextMsgId("tool"),
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
            const urls = (msg.content.claims as any[])
              .flatMap((c: any) => c.citations || [])
              .map((c: any) => extractCitationUrl(c))
              .filter((u): u is string => typeof u === "string" && u.startsWith("http"));
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
        // Guard: sometimes backend emits duplicate turnComplete events.
        if (turnSeqRef.current && lastCompletedTurnRef.current === turnSeqRef.current) {
          break;
        }
        if (turnSeqRef.current) {
          lastCompletedTurnRef.current = turnSeqRef.current;
        }
        const completedMsgId = currentAgentMsgIdRef.current;
        const completedText = currentAgentTextRef.current || agentVoiceBufferRef.current;
        const { cleanText, klipy } = parseKlipyBlock(completedText);
        const sanitizedText = stripKlipyNoise(cleanText, klipy);
        agentVoiceBufferRef.current = "";
        const finalUserText = demoMode ? "" : userVoiceBufferRef.current.trim();
        if (finalUserText && !turnUserCommittedRef.current) {
          turnUserCommittedRef.current = true;
          addMsg({ id: nextMsgId("user"), role: "user", content: finalUserText });
        }
        finalizeUserVoice();
        setLiveAgentText("");
        setLiveUserText("");
        // Reset refs before async work
        currentAgentMsgIdRef.current = null;
        currentAgentTextRef.current = "";
        currentTurnRef.current = null;
        setIsLoading(false);
        setOrbState(isListening ? "listening" : "idle");

        if (completedText.trim()) {
          const ensuredMsgId = completedMsgId || ((): string => {
            const newId = nextMsgId("agent");
            currentAgentMsgIdRef.current = newId;
            currentAgentMsgAddedRef.current = true;
            setMessages((prev) => [...prev, { id: newId, role: "agent", content: completedText }]);
            return newId;
          })();
          turnAgentCommittedRef.current = true;
          if (!currentAgentMsgAddedRef.current) {
            currentAgentMsgAddedRef.current = true;
            setMessages((prev) => {
              const exists = prev.some((m) => m.id === ensuredMsgId);
              return exists ? prev : [...prev, { id: ensuredMsgId, role: "agent", content: completedText }];
            });
          }
          // Strip <klipy> block from the displayed message.
          if (sanitizedText && sanitizedText !== completedText) {
            setMessages((msgs) =>
              msgs.map((m) =>
                m.id === ensuredMsgId ? { ...m, content: sanitizedText } : m,
              ),
            );
          }

          // Prefer explicit klipy payload if present.
          const klipyReq = mapKlipyRequest(klipy);
          if (klipyReq) {
            fetchKlipyContent(klipyReq.api, klipyReq.query, klipyReq.locale, userId.current)
              .then((media) => {
                if (!media) return;
                lastKlipyAtRef.current = Date.now();
                setMessages((msgs) =>
                  msgs.map((m) =>
                    m.id === ensuredMsgId ? { ...m, media } : m,
                  ),
                );
              });
          } else {
            // Fallback to emotion-based selection if no klipy block.
            const { emotion, jurisdiction } = extractEmotion(completedText);
            const now = Date.now();
            const timeSinceLast = now - lastKlipyAtRef.current;
            const longEnough = completedText.length >= 120;
            const hasQuestion = completedText.includes("?");
            const shouldConsider = emotion !== "neutral" && (longEnough || hasQuestion);
            if (shouldConsider && timeSinceLast > 90_000) {
              const probability = emotion === "celebration" ? 0.6
                : emotion === "confusion" ? 0.45
                : emotion === "urgency" ? 0.35
                : emotion === "resolved" ? 0.25
                : 0.0;
              if (Math.random() < probability) {
                const req = selectContent(emotion, jurisdiction, completedText);
                if (req) {
                  fetchKlipyContent(req.api, req.query, req.locale, userId.current)
                    .then((media) => {
                      if (!media) return;
                      lastKlipyAtRef.current = Date.now();
                      setMessages((msgs) =>
                        msgs.map((m) =>
                          m.id === ensuredMsgId ? { ...m, media } : m,
                        ),
                      );
                    });
                }
              }
            }
          }
        }
        currentAgentMsgAddedRef.current = false;
        break;
      }

      case "interrupted":
        setIsLoading(false);
        stopPlayback();
        userVoiceBufferRef.current = "";
        agentVoiceBufferRef.current = "";
        userVoiceMsgIdRef.current = null;
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
        addMsg({ id: nextMsgId("err"), role: "system", content: `Error: ${msg.message}` });
        break;
    }
  }, [addMsg, appendToAgent, demoMode, ensureTurn, finalizeUserVoice, isListening, nextMsgId, setAgentLiveText, setUserVoiceText]);

  useEffect(() => {
    handleServerMessageRef.current = handleServerMessage;
  }, [handleServerMessage]);

  // ---------------------------------------------------------------------------
  // WebSocket
  // ---------------------------------------------------------------------------

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;

    console.log("[WS] connecting", getWsUrl());
    const ws = new WebSocket(getWsUrl());
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[WS] open");
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
        const parsed = JSON.parse(event.data);
        if (parsed?.type) {
          console.log("[WS] message", parsed.type);
          if ((parsed.type === "input_transcription" || parsed.type === "output_transcription") && rawTxLogRef.current < 4) {
            rawTxLogRef.current += 1;
            console.log("[WS] raw transcription payload", parsed);
          }
        }
        handleServerMessageRef.current(parsed);
        return;
      } catch {}
      try {
        handleServerMessageRef.current(JSON.parse(event.data));
      } catch {}
    };

    ws.onclose = () => {
      console.warn("[WS] closed");
      setConnected(false);
      setDemoReady(false);
      setOrbState("idle");
      wsRef.current = null;
      if (connectTimerRef.current) {
        window.clearTimeout(connectTimerRef.current);
      }
      connectTimerRef.current = window.setTimeout(connect, 3000);
    };

    ws.onerror = (e) => {
      console.error("[WS] error", e);
      setOrbState("error");
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (connectTimerRef.current) {
        window.clearTimeout(connectTimerRef.current);
      }
      wsRef.current?.close();
    };
  }, [connect]);

  useEffect(() => {
    if (demoMode && demoReady && isListening && !isLoading) {
      startDemoRecognition();
      return;
    }
    stopDemoRecognition();
  }, [demoMode, demoReady, isListening, isLoading, startDemoRecognition, stopDemoRecognition]);

  // ---------------------------------------------------------------------------
  // Audio
  // ---------------------------------------------------------------------------

  const startMic = useCallback(async () => {
    if (micStreamRef.current) return;
    try {
      console.log("[MIC] requesting permission");
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      console.log("[MIC] permission granted");
      const ctx = new AudioContext({ sampleRate: 16000 });
      const source = ctx.createMediaStreamSource(stream);
      const proc = ctx.createScriptProcessor(4096, 1, 1);

      proc.onaudioprocess = (e) => {
        const ws = wsRef.current;
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          const now = Date.now();
          if (now - lastWsDropLogRef.current > 2000) {
            lastWsDropLogRef.current = now;
            console.warn("[MIC] audio dropped: ws not open");
          }
          return;
        }
        const f32 = e.inputBuffer.getChannelData(0);
        const i16 = new Int16Array(f32.length);
        let sum = 0;
        for (let i = 0; i < f32.length; i++) {
          i16[i] = Math.max(-32768, Math.min(32767, Math.floor(f32[i] * 32767)));
          sum += f32[i] * f32[i];
        }
        const payload = demoMode ? new Int16Array(i16.length) : i16;
        ws.send(JSON.stringify({ type: "audio", data: arrayBufferToBase64(payload.buffer) }));
        const level = Math.min(1, Math.sqrt(sum / f32.length) * 5);
        setVoiceLevel(level);
        setMicLevel(level);
        micFrameCountRef.current += 1;
        if (micFrameCountRef.current % 50 === 0) {
          console.log("[MIC] frames", micFrameCountRef.current, "level", level.toFixed(2));
        }
      };

      source.connect(proc);
      proc.connect(ctx.destination);
      micStreamRef.current = stream;
      micCtxRef.current = ctx;
      micProcRef.current = proc;
      setIsListening(true);
      setOrbState("listening");
      if (demoMode && demoReady) startDemoRecognition();
    } catch (err) {
      console.error("[MIC] start failed", err);
      setOrbState("error");
      addMsg({ id: "mic_err_" + Date.now(), role: "system", content: "Microphone denied. Use text input." });
    }
  }, [addMsg, demoMode, demoReady, startDemoRecognition]);

  const stopMic = useCallback(() => {
    console.log("[MIC] stop");
    micProcRef.current?.disconnect();
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micCtxRef.current?.close();
    micStreamRef.current = null;
    micCtxRef.current = null;
    micProcRef.current = null;
    setIsListening(false);
    setMicLevel(0);
    setOrbState("idle");
    stopDemoRecognition();
  }, [stopDemoRecognition]);

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
    addMsg({ id: nextMsgId("user"), role: "user", content: text });
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
    if (!connected) {
      // Prompt mic permission only on explicit user action.
      startMic();
      connect();
      return;
    }
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
      addMsg({ id: nextMsgId("user"), role: "user", content: `[Uploaded ${file.name}]` });
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
      {/* ── Left Sidebar: Live Knowledge Graph ── */}
      <Sidebar side="left" variant="sidebar" collapsible="offcanvas">
        <SidebarHeader className="border-b border-sidebar-border">
          <div className="flex items-center gap-2 px-1">
            <NetworkIcon className="size-4 text-muted-foreground" />
            <span className="text-sm font-medium">Live Knowledge Graph</span>
          </div>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup className="p-0 flex-1">
            <SidebarGroupContent className="h-full">
              <GraphPanel
                userId={userId.current}
                sessionId={sessionId.current}
                apiUrl={getApiUrl()}
                refreshToken={messages.length}
              />
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
                <h1 className="text-sm font-semibold tracking-tight">Saul Goodman</h1>
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

            {/* Mic toggle */}
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => (isListening ? stopMic() : startMic())}
              className={cn(isListening && "bg-emerald-500/10 text-emerald-400")}
              title={isListening ? "Turn mic off" : "Turn mic on"}
            >
              <MicIcon className="size-4" />
              <span className="sr-only">Toggle Microphone</span>
            </Button>

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
              <div className="flex flex-col items-center gap-2">
                <VoiceOrb state={orbState} voiceLevel={voiceLevel} onClick={handleOrbClick} />
                {isListening ? (
                  <div className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground">
                    <span>Mic</span>
                    <div className="h-1.5 w-24 rounded-full bg-muted">
                      <div
                        className="h-1.5 rounded-full bg-emerald-400 transition-[width]"
                        style={{ width: `${Math.min(100, Math.round(micLevel * 100))}%` }}
                      />
                    </div>
                  </div>
                ) : connected ? (
                  <div className="text-[10px] font-mono text-muted-foreground">
                    Mic off — click orb to enable
                  </div>
                ) : null}
              </div>
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
                  {(!demoMode && (liveUserText || liveAgentText)) && (
                    <div className="space-y-2">
                      {liveUserText && (
                        <div className="flex justify-end">
                          <div className="max-w-[80%] px-3.5 py-2.5 text-sm leading-relaxed bg-secondary rounded-2xl rounded-br-md text-secondary-foreground opacity-90">
                            <div className="whitespace-pre-wrap">{liveUserText}</div>
                          </div>
                        </div>
                      )}
                      {liveAgentText && (
                        <div className="flex justify-start">
                          <div className="max-w-[80%] px-3.5 py-2.5 text-sm leading-relaxed bg-card border border-border rounded-2xl rounded-bl-md text-card-foreground opacity-90">
                            <div className="whitespace-pre-wrap">{liveAgentText}</div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
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
            <span>Saul Goodman</span>
            <span className="size-0.5 rounded-full bg-muted-foreground/50" />
            <span>Live tax intelligence</span>
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
    if (message.meta?.kind === "query_builder") {
      const ctx = message.meta.data || {};
      return (
        <div className="max-w-2xl mx-auto animate-fade-in">
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3">
            <div className="text-xs font-mono text-emerald-300/90">Query Builder → UserTaxContext</div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
              {Object.entries(ctx).map(([k, v]) => (
                <div key={k} className="rounded-lg bg-black/20 px-2 py-1">
                  <div className="text-[10px] uppercase tracking-wide text-emerald-200/60">{k}</div>
                  <div className="text-emerald-100/90">{String(v)}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }
    if (message.meta?.kind === "dispatch_agents") {
      const agents = message.meta.data || {};
      return (
        <div className="max-w-2xl mx-auto animate-fade-in">
          <div className="rounded-xl border border-sky-500/30 bg-sky-500/5 p-3">
            <div className="text-xs font-mono text-sky-300/90">Dispatching simultaneously</div>
            <div className="mt-2 space-y-1 text-[11px]">
              {Object.entries(agents).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between rounded-lg bg-black/20 px-2 py-1">
                  <span className="font-mono text-sky-100/90">{k}</span>
                  <span className="text-sky-200/70 truncate max-w-[70%]">{String(v)}</span>
                </div>
              ))}
            </div>
            <div className="mt-2 text-[10px] font-mono text-sky-200/60">Gemini aggregating… synthesizing… citing…</div>
          </div>
        </div>
      );
    }
    if (message.meta?.kind === "agent_status") {
      const statuses = (message.meta.data?.statuses || []) as any[];
      return (
        <div className="max-w-2xl mx-auto animate-fade-in">
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3">
            <div className="text-xs font-mono text-amber-300/90">Agent results</div>
            <div className="mt-2 space-y-1 text-[11px]">
              {statuses.map((s, idx) => (
                <div key={`${s.source || s.label || "agent"}-${idx}`} className="flex items-center justify-between rounded-lg bg-black/20 px-2 py-1">
                  <span className="font-mono text-amber-100/90">{s.label || s.source}</span>
                  <span className="text-amber-200/70">
                    {s.status}{typeof s.evidence_count === "number" ? ` · ${s.evidence_count} hits` : ""}
                  </span>
                </div>
              ))}
              {!statuses.length && (
                <div className="text-amber-200/60">No agent results reported.</div>
              )}
            </div>
          </div>
        </div>
      );
    }
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
