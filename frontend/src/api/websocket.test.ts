import { describe, expect, it, vi } from "vitest";
import { ObservabilityWebSocketClient } from "./websocket";

type Listener = (event: { data?: string }) => void;

class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  static instances: FakeWebSocket[] = [];

  readonly sent: string[] = [];

  readonly url: string;

  readyState = FakeWebSocket.CONNECTING;

  private readonly listeners = new Map<string, Set<Listener>>();

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  addEventListener(type: string, listener: Listener) {
    const listeners = this.listeners.get(type) ?? new Set<Listener>();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  send(message: string) {
    this.sent.push(message);
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.emit("close", {});
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.emit("open", {});
  }

  receive(data: unknown) {
    this.emit("message", { data: JSON.stringify(data) });
  }

  fail() {
    this.emit("error", {});
  }

  serverClose() {
    this.readyState = FakeWebSocket.CLOSED;
    this.emit("close", {});
  }

  private emit(type: string, event: { data?: string }) {
    this.listeners.get(type)?.forEach((listener) => listener(event));
  }
}

describe("ObservabilityWebSocketClient", () => {
  it("authenticates, subscribes, and responds to heartbeat pings", () => {
    FakeWebSocket.instances = [];
    const client = new ObservabilityWebSocketClient({
      url: "ws://server.test/ws",
      tokenProvider: () => "jwt-token",
      WebSocketCtor: FakeWebSocket as unknown as typeof WebSocket
    });

    client.connect();
    client.subscribe("session-1", 41);

    const socket = FakeWebSocket.instances[0];
    expect(socket.url).toBe("ws://server.test/ws?token=jwt-token");
    socket.open();

    expect(socket.sent.map((message) => JSON.parse(message))).toContainEqual({
      type: "subscribe",
      session_id: "session-1",
      last_sequence_number: 41
    });

    socket.receive({ type: "ping" });
    expect(JSON.parse(socket.sent.at(-1) ?? "{}")).toEqual({ type: "pong" });
  });

  it("dispatches events and resumes after reconnect", () => {
    vi.useFakeTimers();
    FakeWebSocket.instances = [];
    const seen: string[] = [];
    const client = new ObservabilityWebSocketClient({
      url: "ws://server.test/ws",
      tokenProvider: () => null,
      WebSocketCtor: FakeWebSocket as unknown as typeof WebSocket,
      reconnectPolicy: {
        initialDelayMs: 10,
        maxDelayMs: 10,
        maxAttempts: 1
      }
    });

    client.onMessage((message) => {
      if (message.type === "event") {
        seen.push(message.event.event_id);
      }
    });

    client.connect();
    const first = FakeWebSocket.instances[0];
    first.open();
    client.subscribe("session-1");
    first.receive({
      type: "event",
      session_id: "session-1",
      event: {
        event_id: "event-42",
        session_id: "session-1",
        event_type: "reasoning_step",
        timestamp: "2026-06-03T00:00:00Z",
        sequence_number: 42,
        event_data: {}
      }
    });
    expect(seen).toEqual(["event-42"]);

    first.serverClose();
    vi.advanceTimersByTime(10);
    const second = FakeWebSocket.instances[1];
    second.open();

    expect(second.sent.map((message) => JSON.parse(message))).toContainEqual({
      type: "subscribe",
      session_id: "session-1",
      last_sequence_number: 42
    });

    vi.useRealTimers();
  });
});
