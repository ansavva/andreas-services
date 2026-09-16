import type { MediaKind } from "../types";

/**
 * What a file IS, decided the way the API decides it — by extension first.
 *
 * `services/keys.py::kind` on the API classifies a name into image, video,
 * text or other, and `GET /api/nodes/<id>/text` refuses anything that is not
 * `text`. The viewer used to decide from the content type alone — image,
 * video, and everything else "other" — and then treated "other" as text. That
 * agreed with the API by accident for `prompt.json` (whose type is
 * `application/json`) and disagreed for the first non-media, non-text file
 * anyone opened: a `.safetensors`, `application/octet-stream`, which the page
 * sent to the text route, got a 400 for, and drew as a spinner forever.
 *
 * So the same four sets, spelled here once. The content type is the fallback
 * for a name with no telling extension, not the first word.
 */
const IMAGE = new Set([".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp"]);
const VIDEO = new Set([".mp4", ".webm", ".mov", ".m4v"]);
const TEXT = new Set([".json", ".md", ".txt", ".yaml", ".yml", ".csv", ".log"]);

export function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

export function kindOfFile(name: string, contentType?: string | null): MediaKind {
  const ext = extensionOf(name);
  if (IMAGE.has(ext)) return "image";
  if (VIDEO.has(ext)) return "video";
  if (TEXT.has(ext)) return "text";
  const type = contentType ?? "";
  if (type.startsWith("image/")) return "image";
  if (type.startsWith("video/")) return "video";
  if (type.startsWith("text/") || type === "application/json") return "text";
  return "other";
}

/** A word for a binary file the viewer cannot draw — what the page calls it. */
export function describeBinary(name: string): string {
  const ext = extensionOf(name);
  if (ext === ".safetensors") return "LoRA / model weights";
  if (ext === ".zip") return "Archive";
  if (ext === ".pdf") return "PDF document";
  return "File";
}
