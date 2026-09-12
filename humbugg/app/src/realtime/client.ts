// The realtime channel's client half (#691): one socket per session, a nudge in, a refetch out.
//
// The server never pushes content. What arrives is `{ type, group_id, side }` — "your view of this
// thread changed" — and the listener answers with the ordinary authorized GET, so the socket carries
// nothing that needs protecting and the access token never leaves the Authorization header. The
// socket itself is opened with a one-time ticket the API mints on request: sixty seconds, spent on
// first use, the only credential that ever appears in a URL.
//
// A broken socket degrades to today's polling, not to silence: `connected` is false and the thread
// hook polls faster; the client keeps trying with backoff and reconnects the moment the app comes
// back to the foreground. API Gateway closes an idle socket after ten minutes and any socket after
// two hours, so a ping goes out every five minutes and a close is simply a reconnect.
import { AppState, type AppStateStatus } from 'react-native';

export interface RealtimeNudge {
  type: string;
  group_id: string;
  side: 'giver' | 'recipient';
}

export type RealtimeListener = (nudge: RealtimeNudge) => void;

/** The subset of the WebSocket API the client uses, so a test can hand in a fake. */
export interface SocketLike {
  readyState: number;
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: unknown) => void) | null;
  onerror: ((event: unknown) => void) | null;
  send(data: string): void;
  close(): void;
}

export interface RealtimeClientOptions {
  /** `wss://ws.humbugg.com` in production, `ws://127.0.0.1:5001/ws` on a dev stack. */
  url: string;
  /** Mints a fresh one-time ticket; called on every connect. */
  ticket(): Promise<string>;
  /** `(url) => new WebSocket(url)` outside tests. */
  open(url: string): SocketLike;
  /** Backoff bounds, in ms. */
  minDelay?: number;
  maxDelay?: number;
  pingEvery?: number;
  /** Deterministic in tests; `Math.random` otherwise. */
  random?: () => number;
}

const OPEN = 1;

export class RealtimeClient {
  private socket: SocketLike | null = null;
  private listeners = new Set<RealtimeListener>();
  private statusListeners = new Set<(connected: boolean) => void>();
  private attempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private stopped = true;
  private appState: { remove(): void } | null = null;
  private readonly minDelay: number;
  private readonly maxDelay: number;
  private readonly pingEvery: number;
  private readonly random: () => number;

  connected = false;

  constructor(private readonly options: RealtimeClientOptions) {
    this.minDelay = options.minDelay ?? 1_000;
    this.maxDelay = options.maxDelay ?? 30_000;
    this.pingEvery = options.pingEvery ?? 5 * 60_000;
    this.random = options.random ?? Math.random;
  }

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.attempt = 0;
    // Coming back to the foreground is the one moment a closed socket should not wait its turn.
    this.appState = AppState.addEventListener('change', (state: AppStateStatus) => {
      if (state === 'active' && !this.connected && !this.stopped) this.connectNow();
    });
    void this.connect();
  }

  stop(): void {
    this.stopped = true;
    this.appState?.remove();
    this.appState = null;
    this.clearTimers();
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      socket.onclose = null;
      socket.onerror = null;
      socket.close();
    }
    this.setConnected(false);
  }

  subscribe(listener: RealtimeListener): () => void {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }

  onStatus(listener: (connected: boolean) => void): () => void {
    this.statusListeners.add(listener);
    return () => { this.statusListeners.delete(listener); };
  }

  private async connect(): Promise<void> {
    if (this.stopped) return;
    let ticket: string;
    try {
      ticket = await this.options.ticket();
    } catch {
      this.scheduleReconnect();
      return;
    }
    if (this.stopped) return;
    const separator = this.options.url.includes('?') ? '&' : '?';
    const socket = this.options.open(`${this.options.url}${separator}ticket=${encodeURIComponent(ticket)}`);
    this.socket = socket;
    socket.onopen = () => {
      if (this.socket !== socket) return;
      this.attempt = 0;
      this.setConnected(true);
      this.pingTimer = setInterval(() => {
        if (socket.readyState === OPEN) socket.send(JSON.stringify({ action: 'ping' }));
      }, this.pingEvery);
    };
    socket.onmessage = (event) => {
      if (this.socket !== socket) return;
      const nudge = parse(event.data);
      if (nudge) for (const listener of this.listeners) listener(nudge);
    };
    socket.onerror = () => { /* the close that follows is what we act on */ };
    socket.onclose = () => {
      if (this.socket !== socket) return;
      this.socket = null;
      this.clearTimers();
      this.setConnected(false);
      this.scheduleReconnect();
    };
  }

  private connectNow(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    if (this.socket) return;
    this.attempt = 0;
    void this.connect();
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.reconnectTimer) return;
    // Exponential with full jitter: 1 s, 2 s, 4 s … capped, and never a thundering herd.
    const ceiling = Math.min(this.maxDelay, this.minDelay * 2 ** this.attempt);
    this.attempt += 1;
    const delay = Math.round(ceiling / 2 + (ceiling / 2) * this.random());
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      void this.connect();
    }, delay);
  }

  private clearTimers(): void {
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = null;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
  }

  private setConnected(next: boolean): void {
    if (this.connected === next) return;
    this.connected = next;
    for (const listener of this.statusListeners) listener(next);
  }
}

function parse(data: unknown): RealtimeNudge | null {
  if (typeof data !== 'string') return null;
  try {
    const value = JSON.parse(data) as Partial<RealtimeNudge>;
    if (typeof value.type !== 'string' || typeof value.group_id !== 'string') return null;
    if (value.side !== 'giver' && value.side !== 'recipient') return null;
    return { type: value.type, group_id: value.group_id, side: value.side };
  } catch {
    return null;
  }
}
