"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useTransparencyGraph } from "@/hooks/use-transparency-graph";
import { useUserId, createSessionId } from "@/hooks/use-user-id";
import { AudioRecorder } from "@/lib/audio-recorder";
import { AudioStreamer } from "@/lib/audio-streamer";
import { audioContext, base64ToArrayBuffer } from "@/lib/utils";
import { VideoStreamer } from "@/lib/video-streamer";
import { WSClient } from "@/lib/ws-client";
import type {
  DocumentConfirmResponse,
  ExtractedDocument,
  ErrorType,
  OrbState,
  RoutingResult,
  SessionState,
  TranscriptEntry,
} from "@/types";

export function useVoiceSession() {
  const userId = useUserId();
  const transparencyGraphApi = useTransparencyGraph();
  const {
    startSession: startTransparencySession,
    setCameraActive: setTransparencyCameraActive,
    applyConversationMemory: applyTransparencyConversationMemory,
    applyRoutingResult: applyTransparencyRoutingResult,
    confirmDocument: confirmTransparencyDocument,
    beginMemoryLoad,
    applyMemoryGraph,
    failMemoryGraph,
    state: transparencyGraph,
    headline: transparencyHeadline,
  } = transparencyGraphApi;

  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [sessionState, setSessionState] = useState<SessionState>("disconnected");
  const [error, setError] = useState<ErrorType>(null);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [routingResult, setRoutingResult] = useState<RoutingResult | null>(null);
  const [voice, setVoice] = useState<string>("Puck");
  const [modality, setModality] = useState<string[]>(["AUDIO"]);
  const [showSources, setShowSources] = useState<boolean>(false);
  const [extractedDocument, setExtractedDocument] = useState<ExtractedDocument | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [messageDraft, setMessageDraft] = useState("");
  const [graphRefreshKey, setGraphRefreshKey] = useState(0);

  const volumeRef = useRef<number>(0);
  const wsClientRef = useRef<WSClient | null>(null);
  const recorderRef = useRef<AudioRecorder | null>(null);
  const streamerRef = useRef<AudioStreamer | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const videoStreamerRef = useRef<VideoStreamer | null>(null);
  const sessionIdRef = useRef<string>("");
  const intentionalStopRef = useRef(false);
  const startInFlightRef = useRef(false);

  const textAssistMode = useMemo(
    () => modality.length === 1 && modality[0] === "TEXT",
    [modality],
  );

  const appendTranscript = useCallback((entry: Omit<TranscriptEntry, "id" | "timestamp">) => {
    setTranscript((prev) => {
      const last = prev[prev.length - 1];
      if (
        last &&
        last.role === entry.role &&
        last.text.trim() === entry.text.trim()
      ) {
        return prev;
      }

      return [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: entry.role,
          text: entry.text,
          timestamp: new Date(),
        },
      ];
    });
  }, []);

  const resetRealtimeResources = useCallback(() => {
    if (recorderRef.current) {
      recorderRef.current.stop();
      recorderRef.current.removeAllListeners();
      recorderRef.current = null;
    }

    if (streamerRef.current) {
      streamerRef.current.stop();
      streamerRef.current = null;
    }

    if (videoStreamerRef.current) {
      videoStreamerRef.current.stop();
      videoStreamerRef.current = null;
    }

    setCameraActive(false);
    volumeRef.current = 0;
  }, []);

  const stopSession = useCallback(() => {
    intentionalStopRef.current = true;

    if (wsClientRef.current) {
      wsClientRef.current.stop();
      wsClientRef.current.disconnect();
      wsClientRef.current.removeAllListeners();
      wsClientRef.current = null;
    }

    resetRealtimeResources();
    setOrbState("idle");
    setSessionState("disconnected");
  }, [resetRealtimeResources]);

  const startSession = useCallback(async (options?: { captureAudio?: boolean }) => {
    if (startInFlightRef.current) {
      return;
    }

    const captureAudio = options?.captureAudio ?? !textAssistMode;

    startInFlightRef.current = true;
    intentionalStopRef.current = false;
    setSessionState("connecting");
    setError(null);
    setCameraError(null);
    setOrbState(captureAudio ? "listening" : "thinking");

    if (wsClientRef.current) {
      wsClientRef.current.disconnect();
      wsClientRef.current.removeAllListeners();
      wsClientRef.current = null;
    }

    try {
      const wsClient = new WSClient();
      wsClientRef.current = wsClient;

      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("Connection timeout")), 10000);

        wsClient.once("socketOpen", () => {
          clearTimeout(timeout);
          resolve();
        });

        wsClient.once("error", (data) => {
          clearTimeout(timeout);
          reject(new Error(data.message));
        });

        wsClient.connect();
      }).catch((err) => {
        setError("session-error");
        setSessionState("error");
        wsClient.disconnect();
        wsClientRef.current = null;
        throw err;
      });
      if (intentionalStopRef.current) {
        wsClient.disconnect();
        wsClient.removeAllListeners();
        wsClientRef.current = null;
        return;
      }

      sessionIdRef.current = createSessionId();
      startTransparencySession(sessionIdRef.current);
      wsClient.startSession(sessionIdRef.current, userId, {
        voice,
        response_modalities: modality,
      });

      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("Gemini session timeout")), 15000);

        wsClient.once("connected", () => {
          clearTimeout(timeout);
          resolve();
        });

        wsClient.once("error", (data) => {
          clearTimeout(timeout);
          reject(new Error(data.message));
        });
      }).catch((err) => {
        setError("session-error");
        setSessionState("error");
        wsClient.disconnect();
        wsClientRef.current = null;
        throw err;
      });
      if (intentionalStopRef.current) {
        wsClient.disconnect();
        wsClient.removeAllListeners();
        wsClientRef.current = null;
        return;
      }

      if (!textAssistMode) {
        const ctx = await audioContext({ id: "voice-playback", sampleRate: 24000 });
        streamerRef.current = new AudioStreamer(ctx);
      }

      wsClient.on("audio", (data) => {
        if (textAssistMode || !streamerRef.current) {
          return;
        }
        const buffer = base64ToArrayBuffer(data.data);
        streamerRef.current.addPCM16(new Uint8Array(buffer));
        setOrbState("speaking");
      });

      wsClient.on("user_text", (data) => {
        appendTranscript({ role: "user", text: data.text });
      });

      wsClient.on("memory_context", (data) => {
        applyTransparencyConversationMemory(data);
      });

      wsClient.on("text", (data) => {
        setTranscript((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.role === "agent") {
            const updated = [...prev];
            updated[updated.length - 1] = {
              ...last,
              text: `${last.text}${data.text}`,
            };
            return updated;
          }

          return [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "agent",
              text: data.text,
              timestamp: new Date(),
            },
          ];
        });
      });

      wsClient.on("thinking", () => {
        streamerRef.current?.stop();
        setOrbState("thinking");
      });

      wsClient.on("content", (data) => {
        setRoutingResult(data);
        setShowSources(true);
        applyTransparencyRoutingResult(data);
      });

      wsClient.on("turnComplete", () => {
        setOrbState(captureAudio ? "listening" : "idle");
        streamerRef.current?.stop();
      });

      wsClient.on("interrupted", () => {
        setOrbState(captureAudio ? "listening" : "idle");
        streamerRef.current?.stop();
      });

      wsClient.on("error", () => {
        streamerRef.current?.stop();
        setError("session-error");
        setSessionState("error");
      });

      wsClient.on("reconnected", () => {
        streamerRef.current?.stop();
        setSessionState("connected");
        setError(null);
        setOrbState(captureAudio ? "listening" : "idle");
      });

      wsClient.on("closed", () => {
        streamerRef.current?.stop();
        if (!intentionalStopRef.current) {
          setError("disconnected");
          setOrbState("idle");
          setSessionState("disconnected");
          resetRealtimeResources();
        }
      });

      if (videoRef.current) {
        try {
          const videoStreamer = new VideoStreamer();
          await videoStreamer.start(videoRef.current, (b64) => {
            wsClient.sendVideo(b64);
          });
          videoStreamerRef.current = videoStreamer;
          setCameraActive(true);
          setTransparencyCameraActive(true, "Frames are being sent to the live session");
        } catch (err) {
          const message = err instanceof Error ? err.message : "Camera unavailable";
          setCameraError(message);
          setTransparencyCameraActive(false, message);
        }
      }

      if (captureAudio) {
        try {
          const recorder = new AudioRecorder();
          await recorder.start();
          recorderRef.current = recorder;

          recorder.on("data", (base64Data: string) => {
            wsClient.sendAudio(base64Data);
          });

          recorder.on("volume", (vol: number) => {
            volumeRef.current = vol;
          });
        } catch (err) {
          const isDenied = err instanceof DOMException && err.name === "NotAllowedError";
          setError(isDenied ? "mic-denied" : "session-error");
          setSessionState("error");
          wsClient.disconnect();
          wsClientRef.current = null;
          resetRealtimeResources();
          return;
        }
      }
      if (intentionalStopRef.current) {
        wsClient.disconnect();
        wsClient.removeAllListeners();
        wsClientRef.current = null;
        return;
      }

      setRoutingResult(null);
      setShowSources(false);
      setSessionState("connected");
      setOrbState(captureAudio ? "listening" : "idle");
    } finally {
      startInFlightRef.current = false;
    }
  }, [
    appendTranscript,
    applyTransparencyConversationMemory,
    modality,
    resetRealtimeResources,
    textAssistMode,
    applyTransparencyRoutingResult,
    userId,
    setTransparencyCameraActive,
    startTransparencySession,
    voice,
  ]);

  const ensureConnected = useCallback(async (captureAudio: boolean) => {
    if (sessionState === "connected" && wsClientRef.current) {
      return;
    }
    await startSession({ captureAudio });
  }, [sessionState, startSession]);

  const sendTextTurn = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }

    appendTranscript({ role: "user", text: trimmed });
    setMessageDraft("");

    try {
      await ensureConnected(false);
      wsClientRef.current?.sendText(trimmed);
      setOrbState("thinking");
    } catch {
      setError("session-error");
    }
  }, [appendTranscript, ensureConnected]);

  const handleInterrupt = useCallback(() => {
    if (orbState === "speaking" || orbState === "thinking") {
      wsClientRef.current?.interrupt();
      streamerRef.current?.stop();
      setOrbState(textAssistMode ? "idle" : "listening");
    }
  }, [orbState, textAssistMode]);

  const handleOrbClick = useCallback(() => {
    if (orbState === "idle" && sessionState === "disconnected") {
      startSession({ captureAudio: !textAssistMode }).catch(() => {
        // startSession already sets error state
      });
      return;
    }

    if (orbState === "speaking") {
      handleInterrupt();
      return;
    }

    if (orbState === "listening" || orbState === "thinking") {
      stopSession();
    }
  }, [handleInterrupt, orbState, sessionState, startSession, stopSession, textAssistMode]);

  const handleReconnect = useCallback(() => {
    setError(null);
    stopSession();
    startSession({ captureAudio: !textAssistMode }).catch(() => {
      // Errors already handled
    });
  }, [startSession, stopSession, textAssistMode]);

  const handleDismissError = useCallback(() => {
    setError(null);
  }, []);

  const clearDocument = useCallback(() => {
    setExtractedDocument(null);
  }, []);

  const handleDocumentConfirmed = useCallback((response?: DocumentConfirmResponse) => {
    if (response) {
      confirmTransparencyDocument(response.doc_id, response.spanner_stored);
    }
    setGraphRefreshKey((prev) => prev + 1);
  }, [confirmTransparencyDocument]);

  useEffect(() => {
    return () => {
      stopSession();
    };
  }, [stopSession]);

  return {
    orbState,
    sessionState,
    error,
    transcript,
    volumeRef,
    handleOrbClick,
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
    extractedDocument,
    setExtractedDocument,
    clearDocument,
    sendTextTurn,
    messageDraft,
    setMessageDraft,
    videoRef,
    cameraActive,
    cameraError,
    graphRefreshKey,
    handleDocumentConfirmed,
    transparencyGraph,
    transparencyHeadline,
    beginMemoryGraphLoad: beginMemoryLoad,
    applyMemoryGraph,
    failMemoryGraph,
  };
}
