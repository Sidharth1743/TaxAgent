"use client";

import { useCallback, useMemo, useReducer } from "react";

import type { ConversationMemoryContext, PersistedGraphData, RoutingResult } from "@/types";
import {
  buildTimelineHeadline,
  createInitialTransparencyGraphState,
  reduceGraphState,
} from "@/lib/transparency-graph";

export function useTransparencyGraph() {
  const [state, dispatch] = useReducer(
    reduceGraphState,
    undefined,
    createInitialTransparencyGraphState,
  );

  const startSession = useCallback((sessionId: string) => {
    dispatch({ type: "session_started", payload: { sessionId } });
  }, []);

  const setCameraActive = useCallback((active: boolean, message?: string) => {
    dispatch({ type: "camera_updated", payload: { active, message } });
  }, []);

  const applyConversationMemory = useCallback((payload: ConversationMemoryContext) => {
    dispatch({ type: "conversation_memory_loaded", payload });
  }, []);

  const applyRoutingResult = useCallback((payload: RoutingResult) => {
    dispatch({ type: "routing_result", payload });
  }, []);

  const beginMemoryLoad = useCallback(() => {
    dispatch({ type: "memory_loading" });
  }, []);

  const applyMemoryGraph = useCallback((payload: PersistedGraphData) => {
    dispatch({ type: "memory_loaded", payload });
  }, []);

  const failMemoryGraph = useCallback((error: string) => {
    dispatch({ type: "memory_load_failed", payload: { error } });
  }, []);

  const confirmDocument = useCallback((docId: string, stored: boolean) => {
    dispatch({ type: "document_confirmed", payload: { docId, stored } });
  }, []);

  return {
    state,
    headline: useMemo(() => buildTimelineHeadline(state), [state]),
    startSession,
    setCameraActive,
    applyConversationMemory,
    applyRoutingResult,
    beginMemoryLoad,
    applyMemoryGraph,
    failMemoryGraph,
    confirmDocument,
  };
}
