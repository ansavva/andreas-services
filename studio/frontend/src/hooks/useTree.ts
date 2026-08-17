import { useCallback, useEffect, useState } from "react";

import { getTree } from "../apis/studio";
import type { SortOrder, TreeResponse } from "../types";

export function useTree(prefix: string, sort: SortOrder) {
  const [data, setData] = useState<TreeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getTree(prefix, sort)
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
  }, [prefix, sort]);

  useEffect(load, [load]);

  // `reload` is what every write calls when it succeeds. The listing is the
  // source of truth for what is in the bucket, and a rename or a delete is far
  // cheaper to re-fetch than to replay into local state correctly — a renamed
  // object also changes its position under the current sort, which patching in
  // place would get wrong.
  return { data, loading, error, reload: load };
}
