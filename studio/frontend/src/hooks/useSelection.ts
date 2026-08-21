import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { FileEntry } from "../types";

/**
 * Which items in one grid are picked, for an action taken over all of them.
 *
 * Keyed by node id rather than by index, because a listing can be re-fetched
 * under a selection — a presigned URL healing itself, a folder polled again —
 * and an index-keyed selection would silently come to mean different files. It
 * held the object key until #313 and holds the id for the same reason one press
 * further on: an id survives the rename that changes a key.
 *
 * The anchor is what makes shift-click a *range*: an extending press adds
 * everything between the last press and this one rather than toggling, which is
 * the whole reason to select in bulk instead of clicking forty tiles.
 */
export function useSelection(items: readonly FileEntry[], resetToken: string | null) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  const anchor = useRef<number | null>(null);

  // Changing folder empties the selection. This watches the folder rather than
  // living in the click handler that navigates, so that browser back/forward —
  // which changes the folder without going through it — clears it too.
  useEffect(() => {
    setSelected(new Set());
    anchor.current = null;
  }, [resetToken]);

  const toggleAt = useCallback(
    (index: number, extend: boolean) => {
      const item = items[index];
      if (!item) return;

      setSelected((current) => {
        const next = new Set(current);
        const from = anchor.current;

        if (extend && from !== null && items[from]) {
          const [lo, hi] = from <= index ? [from, index] : [index, from];
          // A range press only ever adds. Making it toggle would mean dragging
          // across a partly-selected run deselects half of what you crossed.
          for (let i = lo; i <= hi; i += 1) {
            const between = items[i];
            if (between) next.add(between.id);
          }
        } else if (next.has(item.id)) {
          next.delete(item.id);
        } else {
          next.add(item.id);
        }

        return next;
      });

      anchor.current = index;
    },
    [items],
  );

  const selectAll = useCallback(() => {
    setSelected(new Set(items.map((item) => item.id)));
    anchor.current = null;
  }, [items]);

  const clear = useCallback(() => {
    setSelected(new Set());
    anchor.current = null;
  }, []);

  /** In grid order, not the order they were picked — this is what gets pasted. */
  const selectedItems = useMemo(
    () => items.filter((item) => selected.has(item.id)),
    [items, selected],
  );

  return {
    selected,
    selectedItems,
    count: selectedItems.length,
    allSelected: items.length > 0 && selectedItems.length === items.length,
    toggleAt,
    selectAll,
    clear,
  };
}
