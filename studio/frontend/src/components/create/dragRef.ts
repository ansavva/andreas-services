import type { DragEvent } from "react";

import type { AttachRef } from "../../context/CreateBarContext";

/**
 * Dragging a picture out of the library and onto the create sheet.
 *
 * **A private MIME type, and that is the whole design.** The payload is a node
 * — an id the API can resolve — not a file and not a URL, so it must not be
 * confused with either. `FolderBrowser` treats a drag carrying `Files` as an
 * upload and highlights the whole listing for it; a drag carrying this one is
 * an *existing* node going somewhere, and the two are told apart by the type
 * alone rather than by inspecting a payload neither handler is allowed to read
 * mid-drag.
 *
 * **`types` is readable during a drag and `getData` is not.** The protection
 * mode of a `DataTransfer` while `dragover` is firing hides every value, which
 * is deliberate on the browser's part — a page should not be able to read what
 * is being dragged across it. So the decision "may this land here" is made from
 * the type list, and the payload is not opened until the drop.
 *
 * A `text/plain` copy rides along so a drag that leaves the app lands as
 * something legible rather than as nothing.
 *
 * **Every still starts one of these, from wherever it is drawn.** `MediaThumb`
 * and `MediaPlayer` load the drag themselves — a grid tile, a run's output,
 * the picture on a viewer's stage, a strip thumb, a card's hero — so "can I
 * drag this into the sheet" has one answer everywhere rather than one per
 * surface. It was two grids for a while, and every other picture in the app
 * answered a drag with the browser's own image drag, which the sheet refused.
 */
export const NODE_MIME = "application/x-studio-node";

/**
 * What travels: the whole `AttachRef` — the node, enough to draw it before the
 * run exists, and its provenance (`kind`, `run`, `output`, `character`), so a
 * run's output dropped on the sheet is recorded as that run's output and not
 * as a bare file. A payload from before the provenance rode along carries no
 * `kind`; `readNodeDrag` reads that as an object.
 */
type NodePayload = Partial<AttachRef> & { node: string };

/**
 * Load the drag with a node.
 *
 * `effectAllowed = "copy"` because nothing is moved or removed — the picture
 * stays where it is and the sheet gets a pointer to it, which is also what
 * makes the cursor say `+` rather than the move arrow.
 */
export function startNodeDrag(event: DragEvent, ref: AttachRef): void {
  const payload: NodePayload = ref;
  event.dataTransfer.setData(NODE_MIME, JSON.stringify(payload));
  event.dataTransfer.setData("text/plain", ref.name ?? ref.node);
  event.dataTransfer.effectAllowed = "copy";
}

/** A picture with no provenance beyond being a node — what most surfaces drag. */
export function objectRef(node: string, url?: string | null, name?: string): AttachRef {
  return { node, url, name, kind: "object" };
}

/**
 * Whether this drag is one of ours — the only question answerable mid-drag.
 *
 * Takes a native event as well as React's: the shell listens on `window` for
 * the drag that should bring the sheet up, and React does not wrap those.
 */
export function isNodeDrag(event: { dataTransfer: DataTransfer | null }): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes(NODE_MIME);
}

/**
 * The node the drop carried, or null.
 *
 * Null for anything that is not ours and for a payload that will not parse —
 * a drop is a thing a person did once, so a refusal here has to be silent
 * rather than thrown into a screen that has no way to explain it.
 */
export function readNodeDrag(event: DragEvent): AttachRef | null {
  const raw = event.dataTransfer.getData(NODE_MIME);
  if (!raw) return null;
  try {
    const payload = JSON.parse(raw) as NodePayload;
    if (!payload?.node) return null;
    return { ...payload, kind: payload.kind ?? "object" };
  } catch {
    return null;
  }
}
