import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import type { Category, Event, ProcessedEmail, Sender } from "@/types";

const API_BASE = import.meta.env.VITE_API_URL as string;

export type EventEditFields = Partial<
  Pick<
    Event,
    | "event_name"
    | "date"
    | "time"
    | "venue"
    | "price"
    | "description"
    | "links"
    | "categories"
    | "regions"
  >
>;

/**
 * Returns a set of admin API action helpers, each automatically carrying the
 * `Authorization: Bearer <idToken>` header and parsing JSON responses.
 */
export function useAdminApi() {
  const { idToken } = useAuth();

  const request = useCallback(
    async <T>(path: string, init?: RequestInit): Promise<T> => {
      const headers: Record<string, string> = {
        ...(init?.headers as Record<string, string> | undefined),
      };
      if (idToken) headers["Authorization"] = `Bearer ${idToken}`;
      if (init?.body) headers["Content-Type"] = "application/json";

      const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const text = await res.text();
      return (text ? JSON.parse(text) : {}) as T;
    },
    [idToken]
  );

  return useMemo(
    () => ({
      request,
      listAdminEvents: (status: string) =>
        request<{ events: Event[]; count: number }>(
          `/admin/events?status=${encodeURIComponent(status)}`
        ),
      approveEvent: (id: string) =>
        request<Event>(`/admin/events/${encodeURIComponent(id)}/approve`, {
          method: "POST",
        }),
      rejectEvent: (id: string) =>
        request<Event>(`/admin/events/${encodeURIComponent(id)}/reject`, {
          method: "POST",
        }),
      unpublishEvent: (id: string) =>
        request<Event>(`/admin/events/${encodeURIComponent(id)}/unpublish`, {
          method: "POST",
        }),
      updateEvent: (id: string, fields: EventEditFields) =>
        request<Event>(`/admin/events/${encodeURIComponent(id)}`, {
          method: "PUT",
          body: JSON.stringify(fields),
        }),
      bulkApprove: (ids: string[]) =>
        request<unknown>(`/admin/events/approve`, {
          method: "POST",
          body: JSON.stringify({ ids }),
        }),
      listAdminEmails: () =>
        request<{ emails: ProcessedEmail[]; count: number }>(`/admin/emails`),
      listSenders: (status: string) =>
        request<{ senders: Sender[]; count: number }>(
          `/admin/senders?status=${encodeURIComponent(status)}`
        ),
      classifySender: (senderKey: string, regions: string[]) =>
        request<Sender>(`/admin/senders/${encodeURIComponent(senderKey)}`, {
          method: "PUT",
          body: JSON.stringify({ regions }),
        }),
      listAdminCategories: (status: string) =>
        request<{ categories: Category[]; count: number }>(
          `/admin/categories?status=${encodeURIComponent(status)}`
        ),
      approveCategory: (body: { slug?: string; name?: string }) =>
        request<Category>(`/admin/categories`, {
          method: "POST",
          body: JSON.stringify(body),
        }),
      rejectCategory: (slug: string) =>
        request<unknown>(`/admin/categories/${encodeURIComponent(slug)}`, {
          method: "DELETE",
        }),
    }),
    [request]
  );
}

interface UseAdminEventsResult {
  events: Event[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useAdminEvents(status: string): UseAdminEventsResult {
  const { listAdminEvents } = useAdminApi();
  const { idToken } = useAuth();
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEvents = useCallback(async () => {
    if (!idToken) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listAdminEvents(status);
      setEvents(data.events ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [listAdminEvents, status, idToken]);

  useEffect(() => {
    void fetchEvents();
  }, [fetchEvents]);

  return { events, loading, error, refetch: fetchEvents };
}
