import { useCallback, useEffect, useRef, useState } from "react";

import { getReel } from "../apis/studio";
import type { FileEntry, SortOrder } from "../types";

/**
 * Every image and video beneath a prefix, recursively, paged in as the reel is
 * scrolled. The first page arrives immediately so the reel opens on real media
 * rather than a spinner; the rest is fetched when `loadMore` is called near the
 * end of what is already mounted.
 *
 * The cursor is an offset into the server's sorted result rather than an S3
 * continuation token — sorting by date means the whole subtree has to be known
 * before any page can be cut from it. See `browse.reel_items`.
 */
export function useReel(prefix: string, sort: SortOrder, enabled: boolean) {
  const [items, setItems] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exhausted, setExhausted] = useState(false);
  const [truncated, setTruncated] = useState(false);

  const cursor = useRef<string | null>(null);
  // Guards against a scroll handler firing `loadMore` again while a page is
  // still in flight, which would append the same page twice.
  const inFlight = useRef(false);
  // What the in-flight request is *for*. A page that arrives after the folder or
  // the sort changed belongs to a listing nobody is looking at any more, so each
  // query carries a number and a late page compares its own against the current
  // one. A number rather than a `prefix + sort` string because S3 keys can
  // contain spaces and punctuation — there is no separator that could not also
  // appear inside the prefix.
  const query = useRef({ id: 0, prefix, sort });

  const fetchPage = useCallback(async (id: number, next: string | null) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    setError(null);

    const { prefix: forPrefix, sort: forSort } = query.current;

    try {
      const page = await getReel(forPrefix, forSort, next ?? undefined);
      if (query.current.id !== id) return;

      setItems((current) => (next === null ? page.items : [...current, ...page.items]));
      cursor.current = page.next_cursor;
      setExhausted(page.next_cursor === null);
      setTruncated(page.truncated);
    } catch (err) {
      if (query.current.id === id) setError((err as Error).message);
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const id = query.current.id + 1;
    query.current = { id, prefix, sort };
    cursor.current = null;
    setItems([]);
    setExhausted(false);
    setTruncated(false);

    if (!enabled) return;
    void fetchPage(id, null);
  }, [enabled, fetchPage, prefix, sort]);

  const loadMore = useCallback(() => {
    if (!enabled || exhausted || inFlight.current || cursor.current === null) return;
    void fetchPage(query.current.id, cursor.current);
  }, [enabled, exhausted, fetchPage]);

  /**
   * Forget one item without re-walking the bucket.
   *
   * The reel is a snapshot of a recursive walk, and re-taking that walk after
   * every write would re-page the whole subtree to fix one pane — while the
   * cursor is an offset, so the pages already loaded would shift underneath the
   * scroll position. Dropping the item locally is both cheaper and steadier.
   *
   * A *renamed* item is dropped too, not patched. Its key changed, which means
   * its presigned URL is dead and its position under the current sort may have
   * moved; carrying it along would show a pane that cannot load. Reopening the
   * reel picks it up again under its new name.
   */
  const dropItem = useCallback((key: string) => {
    setItems((current) => current.filter((item) => item.key !== key));
  }, []);

  return { items, loading, error, exhausted, truncated, loadMore, dropItem };
}
