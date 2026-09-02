import { useCallback, useEffect, useState } from "react";

import { getFolder } from "../apis/studio";
import type { FolderId } from "../utils/location";
import type { SortOrder, FolderListing } from "../types";

/**
 * One folder's listing, by node id.
 *
 * `null` is the library root, whose id is not knowable before the first request
 * — `GET /api/tree` with no address is already that folder. `undefined` is
 * "which folder is not settled yet", which is what an object URL looks like
 * until its parent has been asked for; nothing is fetched then, because the
 * alternative is a request for the root that the answer immediately discards.
 */
export function useFolder(folderId: FolderId | undefined, sort: SortOrder) {
  const [data, setData] = useState<FolderListing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    if (folderId === undefined) return;

    setLoading(true);
    setError(null);

    getFolder(folderId === null ? {} : { node: folderId }, sort)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [folderId, sort]);

  useEffect(load, [load]);

  // `reload` is what every write calls when it succeeds. The listing is the
  // source of truth for what is in the library, and a rename or a delete is far
  // cheaper to re-fetch than to replay into local state correctly — a renamed
  // object also changes its position under the current sort, which patching in
  // place would get wrong.
  return { data, loading, error, reload: load };
}
