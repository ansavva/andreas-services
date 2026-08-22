/** Shapes returned by the studio API. Mirrors `studio_core.services`. */

export type MediaKind = "image" | "video" | "text" | "other";

/**
 * Mirrors `browse.SORTS`. `newest` is the default on both sides: this is a
 * library of generated output, so what you came to look at is almost always
 * what the pipeline produced most recently.
 */
export type SortOrder = "newest" | "oldest" | "name" | "name_desc";

export const SORT_LABELS: Record<SortOrder, string> = {
  newest: "Newest first",
  oldest: "Oldest first",
  name: "Name A–Z",
  name_desc: "Name Z–A",
};

export const DEFAULT_SORT: SortOrder = "newest";

export function isSortOrder(value: string | null): value is SortOrder {
  return value !== null && value in SORT_LABELS;
}

/**
 * What a node is, as `/api/nodes` and `/api/resolve` report it.
 *
 * Not `MediaKind`. That one is classified from the extension and answers "how do
 * I draw this"; this one is the catalog's own answer to "is this a folder", and
 * the two share a field name on different shapes. A listing entry carries the
 * first, a record the second.
 */
export type NodeKind = "folder" | "file";

/**
 * One node's record — the whole of what the catalog will say about it.
 *
 * No `blob_key` and no `path`, deliberately and permanently: see the header of
 * `backend/studio_core/routes/nodes.py`. Absent attributes are absent rather
 * than null, which is why every optional field here is `?` and not `| null`.
 */
export interface NodeRecord {
  id: string;
  lib: string;
  /** Absent on the library root, and that absence is what identifies it. */
  parent_id?: string;
  name: string;
  kind: NodeKind;
  size?: number;
  content_type?: string;
  created_at: string;
  updated_at?: string;
}

export interface FileEntry {
  /** The node id. This is what the URL names and what a selection holds. */
  id: string;
  /**
   * The slash-joined *name* path — never the S3 key it is stored under.
   *
   * Still here because the write routes are still key-addressed (#316 retires
   * them). It is also what `CopyKeyButton` puts on the clipboard, which is what
   * a `studio` command takes.
   */
  key: string;
  name: string;
  size: number;
  last_modified: string | null;
  kind: MediaKind;
  content_type: string | null;
  /** Presigned inline GET. Short-lived — re-sign through `getAsset` when it dies. */
  url: string;
  /** Highlighting hint, present on text files only. */
  language?: string;
}

export interface FolderEntry {
  id: string;
  prefix: string;
  name: string;
  last_modified: string | null;
}

export interface Crumb {
  /** The node the crumb names — a crumb is a navigation target, so it has one. */
  id: string;
  name: string;
  prefix: string;
}

export interface TreeResponse {
  prefix: string;
  sort: SortOrder;
  breadcrumbs: Crumb[];
  folders: FolderEntry[];
  files: FileEntry[];
  counts: { folders: number; files: number; media: number };
}

export interface ReelResponse {
  prefix: string;
  sort: SortOrder;
  items: FileEntry[];
  total: number;
  /** True when the recursive walk hit its cap — there is more than this shows. */
  truncated: boolean;
  /** An offset into the sorted result, not an S3 continuation token. */
  next_cursor: string | null;
}

export interface AssetResponse {
  key: string;
  name: string;
  kind: MediaKind;
  size: number;
  content_type: string | null;
  expires_in: number;
  url: string;
}

export interface TextResponse {
  key: string;
  name: string;
  language: string;
  truncated: boolean;
  content: string;
}

export interface CreatedFolder {
  prefix: string;
  name: string;
}

export interface RenamedObject {
  key: string;
  name: string;
  renamed: boolean;
}

export interface RenamedFolder {
  prefix: string;
  name: string;
  objects: number;
  renamed: boolean;
}

export interface MovedObjects {
  destination: string;
  moved: number;
  /** Objects already sitting in the destination — not an error, just nothing to do. */
  skipped: number;
  /** The objects' new keys. */
  keys: string[];
}

export interface MovedFolder {
  prefix: string;
  name: string;
  objects: number;
  moved: boolean;
}

export interface CopiedObjects {
  destination: string;
  copied: number;
  /** The new keys, numbered where the destination already held the name. */
  keys: string[];
}

export interface SavedText {
  key: string;
  name: string;
  language: string;
  bytes: number;
}

export interface DeletedObjects {
  deleted: number;
  keys: string[];
}

export interface DeletedFolder {
  prefix: string;
  deleted: number;
}
