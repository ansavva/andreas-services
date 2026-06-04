import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { useApi } from "@/api";
import { ConfirmDeleteButton } from "@/components/admin/ConfirmDeleteButton";
import { Badge, Button, ErrorBanner, Spinner } from "@/components/ui";
import type { AdminImage } from "@/types";

/**
 * Per-image curation for one event. Agent-extracted images arrive unapproved and
 * the public site serves only approved ones, so this is where an admin decides
 * which images go live: approve (publish), reject (hide but keep), or delete.
 * Lives in the review flow alongside the event preview.
 */
export function EventImagesPanel({ eventId }: { eventId: string }) {
  const api = useApi();
  const [items, setItems] = useState<AdminImage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Per-image in-flight action ("<image_id>:<action>"); disables that card.
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await api.listEventImages(eventId);
      setItems(data.images);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load images");
    }
  }, [api, eventId]);

  useEffect(() => {
    setItems(null);
    void load();
  }, [load]);

  const run = async (
    key: string,
    call: () => Promise<unknown>,
    apply: () => void
  ) => {
    setBusy(key);
    setError(null);
    try {
      await call();
      apply();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(null);
    }
  };

  const setApproved = (id: string, approved: boolean) =>
    run(
      `${id}:${approved ? "approve" : "reject"}`,
      () => (approved ? api.approveImage(eventId, id) : api.rejectImage(eventId, id)),
      () =>
        setItems((prev) =>
          (prev ?? []).map((i) => (i.image_id === id ? { ...i, approved } : i))
        )
    );

  const remove = (id: string) =>
    run(
      `${id}:delete`,
      () => api.deleteImage(eventId, id),
      () => setItems((prev) => (prev ?? []).filter((i) => i.image_id !== id))
    );

  if (items === null && !error) {
    return (
      <div className="flex justify-center py-6">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="eyebrow text-[var(--color-text-muted)]">
        Images{items && items.length > 0 ? ` (${items.length})` : ""}
      </h3>
      {error && <ErrorBanner message={error} />}
      {items && items.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)]">
          No images extracted for this event.
        </p>
      ) : (
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {(items ?? []).map((img) => {
            const locked = busy?.startsWith(`${img.image_id}:`) ?? false;
            const spin = (action: string) =>
              busy === `${img.image_id}:${action}` ? (
                <Loader2 size={14} className="animate-spin" />
              ) : null;
            return (
              <li key={img.image_id} className="flex flex-col gap-2">
                <div className="relative">
                  <img
                    src={img.url}
                    alt=""
                    className={`aspect-[4/3] w-full object-cover grayscale ${
                      img.approved ? "" : "opacity-60"
                    }`}
                  />
                  <span className="absolute left-1.5 top-1.5">
                    <Badge value={img.approved ? "approved" : "pending"} />
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {img.approved ? (
                    <Button disabled={locked} onClick={() => void setApproved(img.image_id, false)}>
                      {spin("reject")}
                      Reject
                    </Button>
                  ) : (
                    <Button
                      variant="primary"
                      disabled={locked}
                      onClick={() => void setApproved(img.image_id, true)}
                    >
                      {spin("approve")}
                      Approve
                    </Button>
                  )}
                  <ConfirmDeleteButton
                    disabled={locked}
                    busy={busy === `${img.image_id}:delete`}
                    onConfirm={() => void remove(img.image_id)}
                    title="Delete image"
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
