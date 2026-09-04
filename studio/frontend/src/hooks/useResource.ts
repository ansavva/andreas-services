import { useCallback } from "react";
import {
  useQuery,
  useQueryClient,
  type QueryKey,
  type UseQueryOptions,
} from "@tanstack/react-query";

/**
 * One `GET`, the three states it can be in, and a `reload` for after a write.
 *
 * **The shape of a `useState` + `useEffect` pair; a cache underneath.** A bare
 * pair per caller means every navigation refetches everything — going back to
 * home refires the character list, the project list and a walk of the whole
 * library, each answer re-signing every URL in it — and two components wanting
 * the same list make two requests: the header search and the home page both
 * read `/api/characters`.
 *
 * The interface keeps the plain shape on purpose: twenty-one callers use this.
 *
 * ## The key is the one thing callers had to gain
 *
 * A cache needs to know what it is caching. `load` alone cannot say — two
 * closures over different ids are different functions with nothing to compare —
 * so the key is passed and it is what dedupes, what a write invalidates, and
 * what `setData` writes through.
 *
 * `null` for either argument means "not yet", which is unchanged: a payload
 * cannot be fetched before the record naming it lands. Nothing is requested,
 * and `loading` stays true — because "waiting on something upstream" and
 * "waiting on this" look the same to a spinner and should.
 *
 * **`load` must still be memoised by the caller.** React Query would tolerate a
 * fresh closure, but the callers pass `useCallback` already and the lint rule
 * that catches a missing dependency is worth keeping pointed at them.
 */
export function useResource<T>(
  key: QueryKey | null,
  load: (() => Promise<T>) | null,
  /**
   * Passed straight through, for the one screen that needs more than a fetch.
   *
   * A run page polls while its run can still change — see `isTerminal`. Kept as
   * a pass-through rather than a `poll?: number` of this hook's own, because
   * the interval has to be decided from the answer already in hand, which is
   * exactly the shape React Query's callback form has.
   */
  options?: Pick<UseQueryOptions<T>, "refetchInterval">,
) {
  const client = useQueryClient();
  const enabled = key !== null && load !== null;

  const query = useQuery({
    // A disabled query still needs a key; this one is never fetched under it.
    queryKey: key ?? ["idle"],
    queryFn: () => (load as () => Promise<T>)(),
    enabled,
    ...options,
  });

  /**
   * Patch what is cached, rather than what this component happens to hold.
   *
   * The old version set local state, so a page that saved a record and a
   * sibling reading the same record disagreed until one of them refetched.
   * Writing through the cache means there is one answer.
   */
  const setData = useCallback(
    (next: T | null | ((current: T | null) => T | null)) => {
      if (key === null) return;
      client.setQueryData<T | null>(key, (current) =>
        typeof next === "function"
          ? (next as (c: T | null) => T | null)(current ?? null)
          : next,
      );
    },
    [client, key],
  );

  const reload = useCallback(() => {
    void query.refetch();
  }, [query]);

  return {
    data: (query.data ?? null) as T | null,
    // `isPending` is true while disabled too, which is the "waiting upstream"
    // state this hook has always reported as loading.
    loading: enabled ? query.isPending : true,
    error: query.error ? (query.error as Error).message : null,
    reload,
    setData,
  };
}
