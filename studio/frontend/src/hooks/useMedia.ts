import { useCallback, useEffect, useRef, useState } from "react";

import { getMedia } from "../apis/studio";
import type { FolderId } from "../utils/location";
import type { FileEntry, SortOrder } from "../types";

/**
 * Every image and video beneath a folder, recursively, paged in as the reel is
 * scrolled. The first page arrives immediately so the reel opens on real media
 * rather than a spinner; the rest is fetched when `loadMore` is called near the
 * end of what is already mounted.
 *
 * The cursor is an offset into the server's sorted result rather than a
 * DynamoDB `LastEvaluatedKey` — sorting by date means the whole branch has to be
 * known before any page can be cut from it. See `browse.reel_items`.
 */
export function useMedia(
  folderId: FolderId,
  sort: SortOrder,
  enabled: boolean,
  /**
   * How many per page. The API's own default is 200.
   *
   * Home shows twelve and never pages, so it asks for twelve: the response and
   * the presigning shrink with it. What does NOT shrink is the enumeration —
   * the endpoint reads the branch, sorts it and slices, because `total` and the
   * cursor are defined against the whole of it. See the note in `HomePage`.
   */
  pageSize?: number,
) {
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
  // one.
  const query = useRef({ id: 0, folderId, sort });

  const fetchPage = useCallback(async (id: number, next: string | null) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    setError(null);

    const { folderId: forFolder, sort: forSort } = query.current;

    try {
      const page = await getMedia(
        forFolder === null ? {} : { node: forFolder },
        forSort,
        next ?? undefined,
        pageSize,
      );
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
  }, [pageSize]);

  useEffect(() => {
    const id = query.current.id + 1;
    query.current = { id, folderId, sort };
    cursor.current = null;
    // **A new query supersedes whatever is in flight, so the flag is cleared
    // rather than waited on.** It guards `loadMore` against appending the same
    // page twice; it must not make a *different* query a no-op, because the
    // response it is holding the door for is one the id check below is about to
    // discard anyway — so nothing would ever arrive.
    //
    // StrictMode is what made this bite. It runs an effect twice on mount, so
    // the second run bumped the id and then hit `if (inFlight.current) return`
    // and did nothing, while the first run's page came back stale against the
    // new id and was dropped. `items` stayed empty for good — and only
    // sometimes, since a request that resolved before the second run beat the
    // race. That is the whole of "Recent is empty on this reload and full on
    // the last one".
    inFlight.current = false;
    setItems([]);
    setExhausted(false);
    setTruncated(false);

    if (!enabled) return;
    void fetchPage(id, null);
  }, [enabled, fetchPage, folderId, sort]);

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
   * A *renamed* item is dropped too, not patched. Its id survives the rename —
   * that is what makes its URL a durable share link — but its name, its key and
   * its position under the current sort do not, and a pane carrying the old ones
   * is a pane that cannot load. Reopening the reel picks it up again.
   */
  const dropItem = useCallback((id: string) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  /**
   * Patch one item in place, rather than dropping it.
   *
   * **The counterpart to `dropItem`, and the difference is which fields moved.**
   * A rename invalidates the name, the key and the presigned URL, so the pane
   * cannot be repaired and is dropped. A description and a set of tags invalidate
   * none of them — the pane stays exactly as it is, with different words on the
   * chrome — and dropping it would scroll the reel out from under somebody
   * mid-sentence.
   */
  const refreshItem = useCallback((id: string, changes: Partial<FileEntry>) => {
    setItems((current) =>
      current.map((item) => (item.id === id ? { ...item, ...changes } : item)),
    );
  }, []);

  return { items, loading, error, exhausted, truncated, loadMore, dropItem, refreshItem };
}
