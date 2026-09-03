import { useCallback, useEffect, useRef, useState } from "react";

import { useToast } from "@ansavva/design-system";

import { uploadFile, type UploadProgress } from "../apis/upload";

export type UploadStatus = "waiting" | "sending" | "done" | "failed";

export interface UploadItem {
  /** A client-side key for the row. Not a node id — a waiting file has no node. */
  key: string;
  /** The name the file arrived with. `landedAs` is what the catalog gave it. */
  name: string;
  status: UploadStatus;
  loaded: number;
  total: number;
  /** Set once the node exists and the catalog has settled its name. */
  landedAs?: string;
  error?: string;
}

let sequence = 0;

/**
 * Files into the folder on screen, one at a time, with a bar each.
 *
 * ## One at a time, on purpose
 *
 * The obvious alternative is `Promise.all`. It is worse here for two reasons and
 * neither is about the server. A phone on mobile data running four 200 MB PUTs
 * finishes all four later than it would have finished the first, and shows four
 * bars crawling instead of one moving — which is the difference between "this is
 * working" and "this is stuck". And sequencing makes the numbering deterministic:
 * three files called `clip.mp4` become `clip.mp4`, `clip (2).mp4`, `clip (3).mp4`
 * in the order they were picked, rather than in whichever order three racing
 * writes reached the table.
 *
 * ## One refresh, at the end
 *
 * `onSettled` fires once the queue drains rather than per file. A listing refetch
 * per file would be a request per upload for a folder nobody is reading while a
 * progress bar is over it — and `useSelection` is keyed by node id, so a refetch
 * mid-queue is safe but pointless.
 *
 * A failure does not stop the queue. Ten photos where the third is a HEIC should
 * leave nine uploaded and one legible message, not one message and seven files
 * never attempted.
 */
export function useUploads(parentId: string | null, onSettled: () => void) {
  const [items, setItems] = useState<readonly UploadItem[]>([]);
  const [active, setActive] = useState(false);
  const toast = useToast();

  // Set on unmount so a resolving upload cannot write state into a page that is
  // gone — the same guard `ConfirmDeleteButton` keeps, and reached the same way:
  // navigating away mid-request.
  const gone = useRef(false);
  useEffect(() => {
    gone.current = false;
    return () => {
      gone.current = true;
    };
  }, []);

  const patch = useCallback((key: string, change: Partial<UploadItem>) => {
    if (gone.current) return;
    setItems((current) =>
      current.map((item) => (item.key === key ? { ...item, ...change } : item)),
    );
  }, []);

  const start = useCallback(
    async (files: readonly File[]) => {
      // The **last breadcrumb's** id, which is a real node even at the library
      // root — `folderId` is `null` there, and `POST /api/nodes` needs a parent.
      // `null` here therefore means "the listing has not landed", the same state
      // `prefix` uses to disable every control that writes. The button is
      // disabled then; this refuses as well, because a drop target cannot be.
      if (parentId === null || files.length === 0) return;

      const queued: UploadItem[] = files.map((file) => ({
        key: `upload-${(sequence += 1)}`,
        name: file.name,
        status: "waiting",
        loaded: 0,
        total: file.size,
      }));
      setItems((current) => [...current, ...queued]);
      setActive(true);

      const landed: string[] = [];
      for (const [index, file] of files.entries()) {
        const item = queued[index];
        if (!item) continue;
        patch(item.key, { status: "sending" });
        try {
          const node = await uploadFile(parentId, file, {
            onProgress: (progress: UploadProgress) => patch(item.key, progress),
          });
          patch(item.key, { status: "done", landedAs: node.name, loaded: file.size });
          landed.push(node.name);
        } catch (err) {
          patch(item.key, { status: "failed", error: (err as Error).message });
        }
      }

      // Said once the queue drains, not per file, for the same reason the
      // refresh is. The rows above the grid carry the detail — which name
      // each file landed under, and which failed — and stay until cleared;
      // the toast is the one line for a person who has scrolled on.
      if (landed.length > 0)
        toast.add({
          intent: "success",
          title: landed.length === 1 ? `Uploaded ${landed[0]}` : `Uploaded ${landed.length} files`,
        });

      if (gone.current) return;
      setActive(false);
      onSettled();
    },
    [onSettled, parentId, patch, toast],
  );

  /**
   * Drop the finished rows, keeping anything still going.
   *
   * Not automatic on a timer. A failure is the whole reason this list is on
   * screen, and a message that removes itself is one nobody reads; the successes
   * go with it because "clip.mp4 landed as clip (2).mp4" has been read by then
   * and the file itself is now in the grid underneath.
   */
  const clearFinished = useCallback(() => {
    setItems((current) => current.filter((item) => item.status !== "done"));
  }, []);

  return { items, active, start, clearFinished };
}
