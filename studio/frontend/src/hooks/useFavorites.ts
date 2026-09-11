import { useCallback, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { addFavorite, getFavoriteIds, removeFavorite } from "../apis/studio";

/**
 * The query key the id set is cached under, and what a write invalidates.
 *
 * Exported because two other things name it: the favorites grid, whose page
 * goes stale the moment a heart is pressed anywhere, and the tests.
 */
export const FAVORITES_KEY = ["favorites", "ids"] as const;

/** What the grid is cached under. Any write invalidates both. */
export const FAVORITES_GRID_KEY = ["favorites", "grid"] as const;

/**
 * Which files this person has favorited, and the press that changes it.
 *
 * **One request for the whole app, not one per tile.** A heart is drawn in the
 * folder browser, on the open file and on a run's outputs, and every one of
 * those is a grid — so "is this favorited" has to be answerable from something
 * already in hand. It is: the id set is one small `GET`, React Query dedupes it
 * across every component that asks, and membership is a `Set.has`.
 *
 * **The press is optimistic, and that is not a nicety.** A heart that waits for
 * a round trip before filling reads as a press that did not register, and the
 * second press people then make would undo the first. The cache is patched
 * first, the request follows, and a failure puts the old set back — so the only
 * state a person can reach is one the server agreed to.
 *
 * **`POST` and `DELETE`, chosen from what the press MEANT** rather than a
 * toggle route: two tabs open on the same file would otherwise race to opposite
 * parities and land on whichever arrived last. Here the last press wins, which
 * is what it looks like it should do.
 */
export function useFavorites() {
  const client = useQueryClient();

  const query = useQuery({
    queryKey: FAVORITES_KEY,
    queryFn: async () => (await getFavoriteIds()).ids,
  });

  const mutation = useMutation<
    { node: string },
    Error,
    { id: string; favorite: boolean },
    { previous: string[] }
  >({
    // The two writes report different bodies — one carries `favorited_at` —
    // and nothing here reads either, so the mutation is typed by what the two
    // have in common rather than by a union no caller would branch on.
    mutationFn: ({ id, favorite }) =>
      favorite ? addFavorite(id) : removeFavorite(id),

    // Patch the set before the request goes, and hand back what it was so a
    // failure can put it back. React Query cancels in-flight reads first —
    // without that, a listing already on the wire would land after this and
    // overwrite the optimistic answer with the pre-press one.
    onMutate: async ({ id, favorite }) => {
      await client.cancelQueries({ queryKey: FAVORITES_KEY });
      const previous = client.getQueryData<string[]>(FAVORITES_KEY) ?? [];
      client.setQueryData<string[]>(
        FAVORITES_KEY,
        favorite ? [id, ...previous.filter((each) => each !== id)]
                 : previous.filter((each) => each !== id),
      );
      return { previous };
    },

    onError: (_error, _variables, context) => {
      if (context) client.setQueryData(FAVORITES_KEY, context.previous);
    },

    // The grid is a different read — hydrated, presigned, paged — so it cannot
    // be patched from an id and is refetched instead. Invalidated rather than
    // refetched directly: a screen that is not showing it does not need it.
    onSettled: () => {
      void client.invalidateQueries({ queryKey: FAVORITES_KEY });
      void client.invalidateQueries({ queryKey: FAVORITES_GRID_KEY });
    },
  });

  const ids = query.data;
  // A `Set`, because the caller is a grid: `includes` per tile is the array
  // walked once per thumbnail, and the browser draws two hundred of them.
  const set = useMemo(() => new Set(ids ?? []), [ids]);

  const isFavorite = useCallback((id: string) => set.has(id), [set]);

  const setFavorite = useCallback(
    (id: string, favorite: boolean) => mutation.mutate({ id, favorite }),
    [mutation],
  );

  return {
    /** Newest pick first, or `undefined` until the first read lands. */
    ids,
    /**
     * Undefined until the set is known — which is why callers draw an empty
     * heart rather than nothing: a control that appears late is a control
     * people press twice.
     */
    loading: query.isPending,
    isFavorite,
    setFavorite,
    toggle: useCallback(
      (id: string) => mutation.mutate({ id, favorite: !set.has(id) }),
      [mutation, set],
    ),
  };
}
