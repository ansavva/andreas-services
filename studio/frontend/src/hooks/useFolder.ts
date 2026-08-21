import { useEffect, useState } from "react";

import { getNode } from "../apis/studio";
import type { SortOrder } from "../types";
import type { FolderId, Target } from "../utils/location";
import { useTree } from "./useTree";

/** A folder held open regardless of what the URL says. See `pin` below. */
export type FolderPin = { id: FolderId } | null;

/**
 * The folder the page is showing, and its listing.
 *
 * A folder URL names it outright. An object URL does not — it names the file —
 * so the folder is that file's parent, and the parent has to be *asked for*.
 * That lookup is the one cost of id-addressed URLs over the key-addressed ones
 * #313 replaced, where `parentPrefix(key)` was string arithmetic and free.
 *
 * **The listing already in hand answers it whenever it can, and that is what
 * keeps the lookup to one request.** The reel rewrites the URL to every clip it
 * scrolls past, so asking per object URL would be a request per scroll for an
 * answer that had not changed. A listing holding the open file is proof of its
 * parent; a cold share link, which has no listing at all, asks once.
 *
 * Staleness is what rules out simply *keeping* the last folder instead. Going
 * back into an object URL after browsing elsewhere would keep a folder the file
 * is not in — so the listing has to confirm, not merely exist.
 *
 * The resolution and the listing live in one hook because each is the other's
 * input: the listing is fetched for a folder id, and the folder id is settled by
 * the listing. Split across two, that is a cycle with no order to write it in.
 *
 * `pin` overrides all of it, for the recursive reel — which walks across folders
 * and leaves the URL naming a clip in none of them.
 */
export function useFolder(target: Target, sort: SortOrder, pin: FolderPin) {
  // `undefined` is "not settled yet", and it is not `null`, which is the library
  // root. `useTree` fetches nothing on `undefined`: the request it would make is
  // for the root, and the answer would be discarded a moment later.
  const [resolved, setResolved] = useState<FolderId | undefined>(
    target.kind === "folder" ? target.id : undefined,
  );
  const [lookupError, setLookupError] = useState<string | null>(null);

  const folderId = pin ? pin.id : resolved;
  const tree = useTree(folderId, sort);
  const listing = tree.data;

  useEffect(() => {
    if (target.kind === "folder") {
      setResolved(target.id);
      setLookupError(null);
      return;
    }

    if (pin) return;

    // The listing came *from* the folder this hook last returned, so a listing
    // holding the open file settles it without naming the folder again — which
    // is why this leaves `resolved` alone rather than reading the last
    // breadcrumb. At the root the two would disagree on spelling (`null` against
    // the root node's real id) and re-fetch the same folder to learn nothing.
    if (listing?.files.some((file) => file.id === target.id)) {
      setLookupError(null);
      return;
    }

    let cancelled = false;
    getNode(target.id)
      .then((node) => {
        if (cancelled) return;
        setResolved(node.parent_id ?? null);
        setLookupError(null);
      })
      .catch((err: Error) => {
        if (!cancelled) setLookupError(err.message);
      });

    return () => {
      cancelled = true;
    };
  }, [listing, pin, target]);

  return {
    folderId,
    data: listing,
    loading: tree.loading,
    // A dead object link and an unreadable folder are the same thing to the
    // page: it has nothing to draw and should say why.
    error: tree.error ?? lookupError,
    reload: tree.reload,
  };
}
