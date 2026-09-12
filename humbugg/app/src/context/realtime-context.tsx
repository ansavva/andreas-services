// The realtime channel for the session (#691): one client, started when signed in, stopped when
// not, and reachable from any thread hook through `useRealtime()`.
//
// `EXPO_PUBLIC_REALTIME_URL` is read here and nowhere else. Unset — the stubbed browser suite, or
// an environment that has no channel — there is no client at all, and the hooks poll as they always
// did. `useRealtime()` outside the provider answers the same way, so a component test needs no
// provider to render a thread.
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { api } from '../api/client';
import { RealtimeClient, type RealtimeListener, type SocketLike } from '../realtime/client';
import { useAuth } from './auth-context';

/** Metro inlines `EXPO_PUBLIC_*`; the lookup cannot be hoisted into a helper or a variable key. */
export const REALTIME_URL: string | null = process.env.EXPO_PUBLIC_REALTIME_URL || null;

interface RealtimeContextValue {
  /** A socket is open. Off, the thread hooks poll faster to make up for it. */
  connected: boolean;
  subscribe(listener: RealtimeListener): () => void;
}

const disconnected: RealtimeContextValue = { connected: false, subscribe: () => () => {} };

const RealtimeContext = createContext<RealtimeContextValue>(disconnected);

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const [connected, setConnected] = useState(false);
  const client = useMemo(
    () =>
      REALTIME_URL
        ? new RealtimeClient({
            url: REALTIME_URL,
            ticket: async () => (await api.createRealtimeTicket(await auth.accessToken())).ticket,
            // The DOM's handler types bind `this`; the client only ever assigns plain closures.
            open: (url) => new WebSocket(url) as unknown as SocketLike,
          })
        : null,
    // The client outlives any one token: it asks for a fresh one on every connect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  useEffect(() => {
    if (!client || !auth.authenticated) return undefined;
    const unsubscribe = client.onStatus(setConnected);
    client.start();
    return () => {
      unsubscribe();
      client.stop();
    };
  }, [client, auth.authenticated]);

  const value = useMemo<RealtimeContextValue>(
    () => (client ? { connected, subscribe: (listener) => client.subscribe(listener) } : disconnected),
    [client, connected],
  );
  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtime(): RealtimeContextValue {
  return useContext(RealtimeContext);
}
