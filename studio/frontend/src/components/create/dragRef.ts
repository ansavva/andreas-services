import type { DragEvent } from "react";

import type { AttachRef } from "../../context/CreateBarContext";
import type { FileEntry } from "../../types";

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
 */
export const NODE_MIME = "application/x-studio-node";

/** What travels: enough to attach the node and to draw it before the run exists. */
interface NodePayload {
  node: string;
  url?: string | null;
  name?: string;
}

/**
 * Load the drag with a node.
 *
 * `effectAllowed = "copy"` because nothing is moved or removed — the picture
 * stays where it is and the sheet gets a pointer to it, which is also what
 * makes the cursor say `+` rather than the move arrow.
 */
export function startNodeDrag(event: DragEvent, file: FileEntry): void {
  const payload: NodePayload = { node: file.id, url: file.url, name: file.name };
  event.dataTransfer.setData(NODE_MIME, JSON.stringify(payload));
  event.dataTransfer.setData("text/plain", file.name);
  event.dataTransfer.effectAllowed = "copy";
}

/** Whether this drag is one of ours — the only question answerable mid-drag. */
export function isNodeDrag(event: DragEvent): boolean {
  return Array.from(event.dataTransfer.types).includes(NODE_MIME);
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
    return { node: payload.node, url: payload.url, name: payload.name, kind: "object" };
  } catch {
    return null;
  }
}
