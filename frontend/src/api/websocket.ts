import type { ReconnectPolicy, RealtimeMessage } from "../types/observability";
import { getStoredAuthToken } from "./authToken";

type Listener = (message: RealtimeMessage) => void;
type StateListener = (state: "connecting" | "open" | "closed" | "error") => void;

export interface ObservabilityWebSocketOptions {
  url?: string;
  tokenProvider?: () => string | null;
  reconnectPolicy?: Partial<ReconnectPolicy>;
  WebSocketCtor?: typeof WebSocket;
}

const defaultPolicy: ReconnectPolicy = {
  initialDelayMs: 250,
  maxDelayMs: 10000,
  multiplier: 2,
  maxAttempts: Infinity
};

const defaultWsUrl = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws";

export class ObservabilityWebSocketClient {
  private readonly url: string;

  private readonly tokenProvider: () => string | null;

  private readonly reconnectPolicy: ReconnectPolicy;

  private readonly WebSocketCtor: typeof WebSocket;

  private socket: WebSocket | null = null;

  private closedByUser = false;

  private reconnectAttempts = 0;

  private readonly subscriptions = new Map<string, number | undefined>();

  private readonly listeners = new Set<Listener>();

  private readonly stateListeners = new Set<StateListener>();

  constructor(options: ObservabilityWebSocketOptions = {}) {
    this.url = options.url ?? defaultWsUrl;
    this.tokenProvider = options.tokenProvider ?? getStoredAuthToken;
    this.reconnectPolicy = { ...defaultPolicy, ...options.reconnectPolicy };
    this.WebSocketCtor = options.WebSocketCtor ?? WebSocket;
  }

  connect(): void {
    this.closedByUser = false;
    this.openSocket();
  }

  close(): void {
    this.closedByUser = true;
    this.socket?.close();
    this.socket = null;
    this.emitState("closed");
  }

  subscribe(sessionId: string, lastSequenceNumber?: number): void {
    this.subscriptions.set(sessionId, lastSequenceNumber);
    this.send({
      type: "subscribe",
      session_id: sessionId,
      last_sequence_number: lastSequenceNumber
    });
  }

  unsubscribe(sessionId: string): void {
    this.subscriptions.delete(sessionId);
    this.send({ type: "unsubscribe", session_id: sessionId });
  }

  onMessage(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onStateChange(listener: StateListener): () => void {
    this.stateListeners.add(listener);
    return () => this.stateListeners.delete(listener);
  }

  private openSocket(): void {
    const token = this.tokenProvider();
    const separator = this.url.includes("?") ? "&" : "?";
    const url = token ? `${this.url}${separator}token=${encodeURIComponent(token)}` : this.url;

    this.emitState("connecting");
    this.socket = new this.WebSocketCtor(url);

    this.socket.addEventListener("open", () => {
      this.reconnectAttempts = 0;
      this.emitState("open");
      for (const [sessionId, lastSequenceNumber] of this.subscriptions) {
        this.send({
          type: "subscribe",
          session_id: sessionId,
          last_sequence_number: lastSequenceNumber
        });
      }
    });

    this.socket.addEventListener("message", (event) => {
      const message = this.parseMessage(event.data);
      if (!message) {
        return;
      }

      if (message.type === "ping") {
        this.send({ type: "pong" });
        return;
      }

      if (message.type === "event") {
        this.subscriptions.set(message.session_id, message.event.sequence_number);
      }

      if (message.type === "events") {
        const latest = message.events.at(-1);
        if (latest) {
          this.subscriptions.set(message.session_id, latest.sequence_number);
        }
      }

      this.listeners.forEach((listener) => listener(message));
    });

    this.socket.addEventListener("close", () => {
      this.emitState("closed");
      this.scheduleReconnect();
    });

    this.socket.addEventListener("error", () => {
      this.emitState("error");
    });
  }

  private send(message: Record<string, unknown>): void {
    if (this.socket?.readyState === this.WebSocketCtor.OPEN) {
      this.socket.send(JSON.stringify(message));
    }
  }

  private scheduleReconnect(): void {
    if (this.closedByUser || this.reconnectAttempts >= this.reconnectPolicy.maxAttempts) {
      return;
    }

    const delay = Math.min(
      this.reconnectPolicy.initialDelayMs * this.reconnectPolicy.multiplier ** this.reconnectAttempts,
      this.reconnectPolicy.maxDelayMs
    );
    this.reconnectAttempts += 1;
    window.setTimeout(() => {
      if (!this.closedByUser) {
        this.openSocket();
      }
    }, delay);
  }

  private parseMessage(data: unknown): RealtimeMessage | null {
    if (typeof data !== "string") {
      return null;
    }
    try {
      return JSON.parse(data) as RealtimeMessage;
    } catch {
      return null;
    }
  }

  private emitState(state: "connecting" | "open" | "closed" | "error"): void {
    this.stateListeners.forEach((listener) => listener(state));
  }
}
