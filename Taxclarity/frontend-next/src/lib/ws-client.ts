import EventEmitter from "eventemitter3";
import type {
  StartMessage,
  AudioMessage,
  TextMessage,
  ControlMessage,
  ServerMessage,
  RoutingResult,
  ConversationMemoryContext,
} from "@/types";

export interface WSClientEventTypes {
  socketOpen: () => void;        // raw WS transport is open — send "start" now
  connected: () => void;         // Gemini session is ready (server sent {type:"connected"})
  audio: (data: { data: string }) => void;
  text: (data: { text: string }) => void;
  user_text: (data: { text: string }) => void;
  memory_context: (data: ConversationMemoryContext) => void;
  thinking: () => void;
  turnComplete: () => void;
  interrupted: () => void;
  error: (data: { message: string }) => void;
  reconnected: () => void;
  content: (data: RoutingResult) => void;
  closed: (data: { wasClean: boolean }) => void;
}

export class WSClient extends EventEmitter<WSClientEventTypes> {
  private ws: WebSocket | null = null;
  private url: string;
  private intentionalClose = false;

  constructor(url?: string) {
    super();
    this.url = url ?? process.env.NEXT_PUBLIC_WS_URL ?? WSClient.defaultUrl();
  }

  private static defaultUrl(): string {
    if (typeof window === "undefined") {
      return "ws://localhost:8003/ws";
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/ws`;
  }

  get isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  connect(): void {
    if (this.ws) {
      this.disconnect();
    }

    this.intentionalClose = false;
    this.ws = new WebSocket(this.url);

    // Emit as soon as the transport handshake completes so callers
    // can immediately send the "start" message without waiting for
    // the Gemini-level "connected" ack (which only arrives AFTER "start").
    this.ws.onopen = () => {
      this.emit("socketOpen");
    };

    this.ws.onmessage = (event: MessageEvent) => {
      let msg: ServerMessage;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }

      switch (msg.type) {
        case "connected":
          this.emit("connected");
          break;
        case "audio":
          if (msg.data) {
            this.emit("audio", { data: msg.data });
          }
          break;
        case "text":
          if (msg.text) {
            this.emit("text", { text: msg.text });
          }
          break;
        case "user_text":
          if (msg.text) {
            this.emit("user_text", { text: msg.text });
          }
          break;
        case "memory_context":
          if (msg.memory_context) {
            this.emit("memory_context", msg.memory_context);
          }
          break;
        case "thinking":
          this.emit("thinking");
          break;
        case "turnComplete":
          this.emit("turnComplete");
          break;
        case "interrupted":
          this.emit("interrupted");
          break;
        case "error":
          this.emit("error", { message: msg.message ?? msg.text ?? "Unknown error" });
          break;
        case "reconnected":
          this.emit("reconnected");
          break;
        case "content":
          if (msg.content) {
            this.emit("content", msg.content as RoutingResult);
          }
          break;
        case "stopped":
          // Server acknowledged stop, no specific event needed
          break;
      }
    };

    this.ws.onclose = (event: CloseEvent) => {
      this.ws = null;
      if (!this.intentionalClose) {
        this.emit("closed", { wasClean: event.wasClean });
      }
    };

    this.ws.onerror = () => {
      this.emit("error", { message: "WebSocket connection error" });
    };
  }

  startSession(sessionId: string, userId: string, options?: { voice?: string; response_modalities?: string[] }): void {
    if (!this.isConnected) return;

    const msg: StartMessage = {
      type: "start",
      session_id: sessionId,
      user_id: userId,
      voice: options?.voice,
      response_modalities: options?.response_modalities,
    };
    this.ws!.send(JSON.stringify(msg));
  }

  sendVideo(base64Data: string): void {
    if (!this.isConnected) return;

    const msg = {
      type: "video",
      data: base64Data,
    };
    this.ws!.send(JSON.stringify(msg));
  }

  sendAudio(base64Data: string): void {
    if (!this.isConnected) return;

    const msg: AudioMessage = {
      type: "audio",
      data: base64Data,
    };
    this.ws!.send(JSON.stringify(msg));
  }

  sendText(text: string): void {
    if (!this.isConnected) return;

    const msg: TextMessage = {
      type: "text",
      text,
    };
    this.ws!.send(JSON.stringify(msg));
  }

  interrupt(): void {
    if (!this.isConnected) return;

    const msg: ControlMessage = {
      type: "interrupt",
    };
    this.ws!.send(JSON.stringify(msg));
  }

  stop(): void {
    if (!this.isConnected) return;

    const msg: ControlMessage = {
      type: "stop",
    };
    this.ws!.send(JSON.stringify(msg));
  }

  disconnect(): void {
    this.intentionalClose = true;
    if (this.ws) {
      try {
        this.stop();
      } catch {
        // WebSocket might already be closing
      }
      this.ws.close();
      this.ws = null;
    }
  }
}
