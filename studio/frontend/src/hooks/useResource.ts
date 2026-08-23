import { useCallback, useEffect, useState } from "react";

/**
 * One `GET` and the three states it can be in, with a `reload` for after a write.
 *
 * Every entity screen needs exactly this and the browse hooks already each wrote
 * it out — `useTree` and `useReel` both carry their own copy, and neither is
 * refactored onto this one because both do something extra with the answer
 * (a pin, a cursor, a drop). This is for the plain case, which is now most of
 * the app.
 *
 * **`load` must be memoised by the caller**, with `useCallback`, and that is the
 * whole interface: a loader rebuilt on every render is an infinite fetch loop,
 * and the alternative — a dependency array passed in — hides the same mistake
 * from the lint rule that would otherwise catch it.
 *
 * `null` is a legitimate loader and means "not yet": a run page knows its run id
 * from the URL but a scene's payload cannot be fetched before the record naming
 * it lands. Nothing is requested then, and `loading` stays true, because
 * "waiting on something upstream" and "waiting on this" look the same to a
 * spinner and should.
 */
export function useResource<T>(load: (() => Promise<T>) | null) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(() => {
    if (load === null) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    load()
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
  }, [load]);

  useEffect(run, [run]);

  return { data, loading, error, reload: run, setData };
}
