import { useCallback, useEffect, useState } from "react";

import { getTree } from "../apis/studio";
import type { TreeResponse } from "../types";

export function useTree(prefix: string) {
  const [data, setData] = useState<TreeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getTree(prefix)
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
  }, [prefix]);

  useEffect(load, [load]);

  return { data, loading, error, reload: load };
}
