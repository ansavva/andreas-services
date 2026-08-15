import { useCallback, useEffect, useRef, useState } from "react";

import { getReel } from "../apis/studio";
import type { FileEntry } from "../types";

/**
 * Every image and video beneath a prefix, recursively, paged in as the reel is
 * scrolled. The first page arrives immediately so the reel opens on real media
 * rather than a spinner; the rest is fetched when `loadMore` is called near the
 * end of what is already mounted.
 */
export function useReel(prefix: string, enabled: boolean) {
  const [items, setItems] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exhausted, setExhausted] = useState(false);

  const cursor = useRef<string | null>(null);
  // Guards against a scroll handler firing `loadMore` again while a page is
  // still in flight, which would append the same page twice.
  const inFlight = useRef(false);
  const activePrefix = useRef(prefix);

  const fetchPage = useCallback(
    async (forPrefix: string, next: string | null) => {
      if (inFlight.current) return;
      inFlight.current = true;
      setLoading(true);
      setError(null);

      try {
        const page = await getReel(forPrefix, next ?? undefined);
        // A prefix change mid-flight makes this page the wrong folder's.
        if (activePrefix.current !== forPrefix) return;

        setItems((current) => (next === null ? page.items : [...current, ...page.items]));
        cursor.current = page.next_cursor;
        setExhausted(page.next_cursor === null);
      } catch (err) {
        if (activePrefix.current === forPrefix) setError((err as Error).message);
      } finally {
        inFlight.current = false;
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    activePrefix.current = prefix;
    cursor.current = null;
    setItems([]);
    setExhausted(false);

    if (!enabled) return;
    void fetchPage(prefix, null);
  }, [enabled, fetchPage, prefix]);

  const loadMore = useCallback(() => {
    if (!enabled || exhausted || inFlight.current || cursor.current === null) return;
    void fetchPage(activePrefix.current, cursor.current);
  }, [enabled, exhausted, fetchPage]);

  return { items, loading, error, exhausted, loadMore };
}
