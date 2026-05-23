import { useCallback, useEffect, useState } from "react";
import type { Event } from "@/types";

const API_BASE = import.meta.env.VITE_API_URL as string;

interface UseEventsOptions {
  region?: string;
  category?: string;
  upcoming?: boolean;
}

interface UseEventsResult {
  events: Event[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useEvents({ region, category, upcoming }: UseEventsOptions): UseEventsResult {
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (region) params.set("region", region);
      if (category) params.set("category", category);
      if (upcoming) params.set("upcoming", "true");
      const qs = params.toString();
      const url = qs ? `${API_BASE}/events?${qs}` : `${API_BASE}/events`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const data = (await res.json()) as { events: Event[] };
      setEvents(data.events ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [region, category, upcoming]);

  useEffect(() => {
    void fetchEvents();
  }, [fetchEvents]);

  return { events, loading, error, refetch: fetchEvents };
}
