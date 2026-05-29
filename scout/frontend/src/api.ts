import { useCallback, useMemo } from "react";
import { useAuth } from "@/context/AuthContext";
import type {
  AdminEvent,
  ArtifactChunk,
  DeletedItem,
  Facets,
  Feed,
  Label,
  LabelTaxonomy,
  Location,
  Notification,
  PublicEvent,
  PublicFilters,
  ReviewGroup,
  Settings,
  Source,
  SourceRun,
  SubEvent,
} from "@/types";

const API_BASE = import.meta.env.VITE_API_URL as string;

function buildQuery(params: Record<string, string | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v as string)}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

/**
 * Typed Scout API client. Admin calls carry the Cognito bearer token; public
 * calls are unauthenticated. JSON bodies are sent and parsed automatically.
 */
export function useApi() {
  const { idToken } = useAuth();

  const request = useCallback(
    async <T>(path: string, init?: RequestInit): Promise<T> => {
      const headers: Record<string, string> = {
        ...(init?.headers as Record<string, string> | undefined),
      };
      if (idToken) headers["Authorization"] = `Bearer ${idToken}`;
      if (init?.body) headers["Content-Type"] = "application/json";

      const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const body = (await res.json()) as { error?: string };
          if (body.error) detail = body.error;
        } catch {
          /* ignore non-JSON error bodies */
        }
        throw new Error(detail);
      }
      const text = await res.text();
      return (text ? JSON.parse(text) : {}) as T;
    },
    [idToken]
  );

  return useMemo(() => {
    const post = (path: string, body?: unknown) =>
      request(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
    const put = (path: string, body: unknown) =>
      request(path, { method: "PUT", body: JSON.stringify(body) });
    const del = (path: string) => request(path, { method: "DELETE" });

    return {
      request,

      // --- public ---
      feed: (filters: PublicFilters, cursor?: string, sort?: string) =>
        request<Feed>(
          `/public/events${buildQuery({
            location_id: filters.location_id,
            event_labels: filters.event_labels.join(",") || undefined,
            location_labels: filters.location_labels.join(",") || undefined,
            q: filters.q,
            sort,
            cursor,
          })}`
        ),
      eventDetail: (id: string) =>
        request<PublicEvent>(`/public/events/${encodeURIComponent(id)}`),
      facets: () => request<Facets>(`/public/facets`),

      // --- sources ---
      listSources: (archived?: boolean, cursor?: string, pageSize?: number) =>
        request<{ sources: Source[]; next_cursor: string | null }>(
          `/admin/sources${buildQuery({
            archived: archived ? "true" : undefined,
            cursor,
            page_size: pageSize ? String(pageSize) : undefined,
          })}`
        ),
      sourcesRunning: () =>
        request<{ running: string[] }>(`/admin/sources/running`),
      createSource: (body: unknown) => post(`/admin/sources`, body) as Promise<Source>,
      scanInbox: () => post(`/admin/sources/scan-inbox`, {}),
      updateSource: (id: string, body: unknown) =>
        put(`/admin/sources/${id}`, body) as Promise<Source>,
      archiveSource: (id: string, archived: boolean) =>
        post(`/admin/sources/${id}/archive`, { archived }) as Promise<Source>,
      runSource: (id: string) => post(`/admin/sources/${id}/run`),
      previewSource: (id: string) => post(`/admin/sources/${id}/preview`),
      listRuns: (id: string, cursor?: string, pageSize?: number) =>
        request<{ runs: SourceRun[]; next_cursor: string | null }>(
          `/admin/sources/${id}/runs${buildQuery({
            cursor,
            page_size: pageSize ? String(pageSize) : undefined,
          })}`
        ),
      // Fetches one byte-range chunk of a run artifact from an absolute URL the
      // server emitted alongside the run. Looped by the UI until next_offset is
      // null so any file size renders inline without hitting the response cap.
      fetchArtifactChunk: async (url: string, offset: number): Promise<ArtifactChunk> => {
        const sep = url.includes("?") ? "&" : "?";
        const full = `${url}${sep}offset=${offset}`;
        const headers: Record<string, string> = {};
        if (idToken) headers["Authorization"] = `Bearer ${idToken}`;
        const res = await fetch(full, { headers });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as ArtifactChunk;
      },
      sourceHealth: () =>
        request<{ errored: Source[]; stale: Source[]; overdue: Source[] }>(
          `/admin/sources/health`
        ),
      deleteSourcePreview: (id: string) =>
        request<{ events: number; subevents: number; runs: number }>(
          `/admin/sources/${id}/delete-preview`
        ),
      deleteSource: (id: string, cascade: boolean) =>
        del(`/admin/sources/${id}${buildQuery({ cascade: cascade ? "true" : "false" })}`),

      // --- events ---
      listEvents: (review: string, cursor?: string, pageSize?: number) =>
        request<{ groups: ReviewGroup[]; next_cursor: string | null }>(
          `/admin/events${buildQuery({
            review,
            cursor,
            page_size: pageSize ? String(pageSize) : undefined,
          })}`
        ),
      getEvent: (id: string) =>
        request<{ event: AdminEvent; subevents: SubEvent[] }>(`/admin/events/${id}`),
      previewEvent: (id: string) =>
        request<PublicEvent>(`/admin/events/${encodeURIComponent(id)}/preview`),
      reviewEvent: (id: string, status: string) =>
        post(`/admin/events/${id}/review`, { status }),
      // Swipe decision: approve (publish event + all occurrences) or reject
      // (unpublish them), with an optional feedback note. Returns the refreshed
      // parent + occurrences.
      decideEvent: (id: string, decision: "approved" | "rejected", feedback?: string) =>
        post(`/admin/events/${id}/decide`, { decision, feedback }) as Promise<{
          event: AdminEvent;
          subevents: SubEvent[];
        }>,
      bulkReview: (ids: string[], status: string) =>
        post(`/admin/events/review`, { ids, status }),
      publishEvent: (id: string, published: boolean) =>
        post(`/admin/events/${id}/publish`, { published }),
      cancelEvent: (id: string) => post(`/admin/events/${id}/cancel`),
      updateEvent: (id: string, body: unknown) => put(`/admin/events/${id}`, body),
      updateSubevent: (eventId: string, subId: string, body: unknown) =>
        put(`/admin/events/${eventId}/subevents/${subId}`, body),
      deleteEvent: (id: string, cascade: boolean) =>
        del(`/admin/events/${id}${buildQuery({ cascade: cascade ? "true" : "false" })}`),
      reviewSub: (eventId: string, subId: string, status: string) =>
        post(`/admin/events/${eventId}/subevents/${subId}/review`, { status }),
      publishSub: (eventId: string, subId: string, published: boolean) =>
        post(`/admin/events/${eventId}/subevents/${subId}/publish`, { published }),
      cancelSub: (eventId: string, subId: string) =>
        post(`/admin/events/${eventId}/subevents/${subId}/cancel`),
      deleteSub: (eventId: string, subId: string) =>
        del(`/admin/events/${eventId}/subevents/${subId}`),

      // --- locations ---
      listLocations: () => request<{ locations: Location[] }>(`/admin/locations`),
      createLocation: (body: unknown) =>
        post(`/admin/locations`, body) as Promise<Location>,
      updateLocation: (id: string, body: unknown) =>
        put(`/admin/locations/${id}`, body) as Promise<Location>,
      deleteLocation: (id: string, cascade: boolean) =>
        del(`/admin/locations/${id}${buildQuery({ cascade: cascade ? "true" : "false" })}`),
      mergeLocations: (targetId: string, sourceIds: string[]) =>
        post(`/admin/locations/merge`, { target_id: targetId, source_ids: sourceIds }),

      // --- labels ---
      listLabels: (taxonomy: LabelTaxonomy) =>
        request<{ labels: Label[] }>(`/admin/labels/${taxonomy}`),
      createLabel: (taxonomy: LabelTaxonomy, name: string) =>
        post(`/admin/labels/${taxonomy}`, { name }) as Promise<Label>,
      renameLabel: (taxonomy: LabelTaxonomy, id: string, name: string) =>
        put(`/admin/labels/${taxonomy}/${id}`, { name }) as Promise<Label>,
      deleteLabel: (taxonomy: LabelTaxonomy, id: string) =>
        del(`/admin/labels/${taxonomy}/${id}`),

      // --- settings / notifications / deleted ---
      getSettings: () => request<Settings>(`/admin/settings`),
      updateSettings: (body: Settings) => put(`/admin/settings`, body) as Promise<Settings>,
      listNotifications: (unreadOnly?: boolean) =>
        request<{ notifications: Notification[] }>(
          `/admin/notifications${buildQuery({ unread: unreadOnly ? "true" : undefined })}`
        ),
      markNotificationRead: (id: string) => post(`/admin/notifications/${id}/read`),
      listDeleted: (entityType: string) =>
        request<{ items: DeletedItem[] }>(`/admin/deleted/${entityType}`),
      restore: (pk: string, sk: string) => post(`/admin/restore`, { pk, sk }),
    };
  }, [request, idToken]);
}

export type ScoutApi = ReturnType<typeof useApi>;
