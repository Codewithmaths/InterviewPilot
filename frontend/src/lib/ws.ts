import type { Role, WsMessage, WsEventType } from "@/types";

type Listener = (message: WsMessage) => void;

/**
 * Typed WebSocket client. Supports reconnection and per-event listeners.
 * Also used for WebRTC signaling (send SIGNAL messages).
 */
export class WsClient {
  private ws: WebSocket | null = null;
  private url: string;
  private role: Role;
  private listeners = new Map<string, Set<Listener>>();
  private shouldReconnect = true;
  private reconnectDelay = 1500;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(interviewId: number | string, role: Role) {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    this.url = `${protocol}://${window.location.host}/ws/${interviewId}?role=${role}`;
    this.role = role;
  }

  connect(): void {
    this.shouldReconnect = true;
    this.open();
  }

  private open(): void {
    const ws = new WebSocket(this.url);
    this.ws = ws;

    ws.onopen = () => {
      this.send("JOIN", { role: this.role });
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data as string) as WsMessage;
        this.dispatch(message);
      } catch {
        /* ignore malformed frames */
      }
    };

    ws.onclose = () => {
      if (this.shouldReconnect && this.reconnectDelay <= 15000) {
        this.reconnectTimer = setTimeout(() => this.open(), this.reconnectDelay);
        this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 15000);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  on(type: WsEventType | "ALL", listener: Listener): () => void {
    const key = type;
    if (!this.listeners.has(key)) this.listeners.set(key, new Set());
    this.listeners.get(key)!.add(listener);
    return () => this.listeners.get(key)?.delete(listener);
  }

  dispatch(message: WsMessage): void {
    this.listeners.get(message.type)?.forEach((l) => l(message));
    this.listeners.get("ALL")?.forEach((l) => l(message));
  }

  send(type: string, payload: Record<string, unknown> = {}): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, payload }));
    }
  }

  sendSignal(kind: "offer" | "answer" | "ice", data: Record<string, unknown>): void {
    this.send("SIGNAL", { kind, ...data });
  }

  sendMediaState(camera: string, mic: string): void {
    this.send("MEDIA_STATE", { camera, mic });
  }

  close(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }

  get isOpen(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
