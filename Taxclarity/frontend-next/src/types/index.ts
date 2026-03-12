export type OrbState = "idle" | "listening" | "thinking" | "speaking";

export interface TranscriptEntry {
  id: string;
  role: "user" | "agent";
  text: string;
  timestamp: Date;
}

// Client-to-server messages
export type ClientMessageType = "start" | "audio" | "video" | "text" | "stop" | "interrupt";

export interface StartMessage {
  type: "start";
  session_id: string;
  user_id: string;
  voice?: string;
  response_modalities?: string[];
}

export interface AudioMessage {
  type: "audio";
  data: string; // base64 PCM16
}

export interface TextMessage {
  type: "text";
  text: string;
}

export interface ControlMessage {
  type: "stop" | "interrupt";
}

export type ClientMessage = StartMessage | AudioMessage | TextMessage | ControlMessage;

// Server-to-client messages
export type ServerMessageType =
  | "connected"
  | "audio"
  | "text"
  | "user_text"
  | "memory_context"
  | "thinking"
  | "turnComplete"
  | "interrupted"
  | "error"
  | "reconnected"
  | "stopped"
  | "content";

export interface ServerMessage {
  type: ServerMessageType;
  data?: string;   // base64 audio for type="audio"
  text?: string;   // text content for type="text" or "error"
  message?: string; // error message for type="error"
  content?: RoutingResult; // structured citation data for type="content"
  memory_context?: ConversationMemoryContext;
}

export type SessionState = "disconnected" | "connecting" | "connected" | "error" | "reconnecting";

export type ErrorType = "mic-denied" | "disconnected" | "session-error" | null;

// Source/citation types for trust features
export type SourceName = "caclub" | "taxtmi" | "turbotax" | "taxprofblog";
export type JurisdictionType = "india" | "usa" | "both";

export interface Citation {
  url: string;
  title?: string;
  snippet?: string;
  date?: string;        // ISO date string
  reply_count?: number;
  source: SourceName;
}

export interface Claim {
  claim: string;
  citations: Citation[];
  confidence?: number;  // 0-1, derived from corroboration
}

export interface ContradictionPosition {
  source: string;
  claim: string;
  citations: string[];
}

export interface Contradiction {
  topic: string;
  positions: ContradictionPosition[];
  analysis: string;
}

export interface SourceStatus {
  source: string;
  label: string;
  region: string;
  status: string;
  error?: string;
  evidence_count?: number;
}

export interface GraphEvent {
  id: string;
  kind: string;
  label: string;
  status?: string;
  region?: string;
  parentId?: string;
  sourceId?: string;
  confidence?: number;
  evidenceCount?: number;
  priorCount?: number;
  unresolvedCount?: number;
  url?: string;
  error?: string;
}

export interface GraphSummary {
  session_id: string;
  active_sources: number;
  claim_count: number;
  contradiction_count: number;
  memory_loaded: boolean;
  remembered_turns?: number;
  remembered_topics?: number;
}

export interface ConversationTurn {
  role: "user" | "agent";
  text: string;
  created_at: string;
}

export interface ConversationMemoryContext {
  summary: string;
  recent_turns: ConversationTurn[];
  prior_topics: string[];
  loaded: boolean;
}

export interface PersistedGraphNode {
  id: string;
  label: string;
  type: string;
  color: string;
}

export interface PersistedGraphLink {
  source: string;
  target: string;
  type: string;
}

export interface PersistedGraphData {
  nodes: PersistedGraphNode[];
  links: PersistedGraphLink[];
}

export type TransparencyGraphMode = "live" | "memory" | "combined";

export interface TransparencyGraphNode {
  id: string;
  label: string;
  type: string;
  color: string;
  layer: "live" | "memory";
  x?: number;
  y?: number;
  status?: string;
  region?: string;
  confidence?: number;
  emphasis?: number;
  meta?: Record<string, string | number | boolean>;
}

export interface TransparencyGraphLink {
  source: string;
  target: string;
  type: string;
  layer: "live" | "memory";
  color?: string;
}

export interface TransparencyTimelineEvent {
  id: string;
  label: string;
  detail?: string;
  tone: "info" | "success" | "warning" | "critical";
  createdAt: string;
}

export interface TransparencyGraphDataset {
  nodes: TransparencyGraphNode[];
  links: TransparencyGraphLink[];
}

export interface TransparencyGraphState {
  live: TransparencyGraphDataset;
  memory: TransparencyGraphDataset;
  combined: TransparencyGraphDataset;
  timeline: TransparencyTimelineEvent[];
  memoryStatus: "idle" | "loading" | "ready" | "error";
  memoryError?: string | null;
}

export interface RoutingResult {
  query: string;
  jurisdiction: JurisdictionType;
  sources: string[];
  claims: Claim[];
  contradictions?: Contradiction[];
  source_statuses?: SourceStatus[];
  graph_events?: GraphEvent[];
  graph_summary?: GraphSummary;
  synthesized_response?: string;
  memory_context?: {
    prior_resolutions: Array<{ query: string; status: string; created_at: string }>;
    unresolved_queries: Array<{ query: string; status: string; created_at: string }>;
  };
}

// Document processing types
export interface FormField {
  name: string;
  value: string;
  confidence: number;
}

export interface ExtractedDocument {
  doc_id: string;
  form_type: string;     // "w2" | "1099" | "form16" | "unknown"
  jurisdiction: string;  // "usa" | "india"
  fields: FormField[];
  raw_text: string;
  pageindex_doc_id?: string | null;
}

export interface DocumentConfirmResponse {
  doc_id: string;
  form_id?: string | null;
  entity_ids?: string[] | null;
  spanner_stored: boolean;
  jurisdiction_id?: string | null;
}

export interface TaxComputationResult {
  old_regime_tax?: number;
  new_regime_tax?: number;
  recommended?: string;
  savings?: number;
  federal_tax?: number;
  effective_rate?: number;
  marginal_bracket?: number;
  optimizations?: string[];
  error?: string;
}

export interface DocumentComputeResponse {
  doc_id: string;
  form_type: string;
  jurisdiction: string;
  computation: TaxComputationResult;
}
