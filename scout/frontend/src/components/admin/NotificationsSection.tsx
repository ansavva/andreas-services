import { useCallback, useEffect, useState } from "react";
import { useApi } from "@/api";
import { Badge, Button, ErrorBanner, Spinner } from "@/components/ui";
import type { Notification } from "@/types";

export function NotificationsSection() {
  const api = useApi();
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listNotifications();
      setItems(data.notifications);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const markRead = async (id: string) => {
    try {
      await api.markNotificationRead(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  };

  if (loading) return <div className="flex justify-center py-16"><Spinner /></div>;

  return (
    <div className="flex flex-col gap-2">
      {error && <ErrorBanner message={error} />}
      {items.length === 0 ? (
        <p className="py-12 text-center text-sm text-[var(--color-text-muted)]">No notifications.</p>
      ) : (
        <div className="border-t border-[var(--color-rule)]">
          {items.map((n) => (
            <div
              key={n.notification_id}
              className={`flex flex-col gap-3 border-b border-[var(--color-border)] py-4 sm:flex-row sm:items-center sm:justify-between ${
                n.read ? "opacity-50" : ""
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge value={n.type} />
                <span className="text-sm text-[var(--color-text-primary)]">{n.message}</span>
              </div>
              {!n.read && <Button onClick={() => void markRead(n.notification_id)}>Mark read</Button>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
