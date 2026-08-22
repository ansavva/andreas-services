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
 * One entry of `GET /api/libraries` — a library the signed-in caller is in.
 *
 * `role` is `owner` or `member` and the app reads it for exactly one thing:
 * transferring a subtree between libraries needs `owner` in both. Everything
 * else in this API is authorised by membership alone, so it is typed as the two
 * words rather than as a permission model there is no more of.
 */
export interface Library {
  id: string;
  name: string;
  role: "owner" | "member";
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
   * The slash-joined *name* path — never the S3 key it is stored under. For
   * anything uploaded through the app the two do not resemble each other at
   * all: the blob sits at `blobs/<node-id>`.
   *
   * Still called `key` because the write routes still call their address that.
   * #316 is closed and did not retire them — it made them catalog writes, which
   * take a name path under the old parameter name. It is also what
   * `CopyKeyButton` puts on the clipboard, which is what a `studio` command
   * takes.
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
  moved: boolean;
  /**
   * Rows whose `path` the move rewrote. Not an object count — a move copies no
   * bytes since #316, so a folder rename reports nothing at all and this reports
   * how much of the tree came along.
   */
  descendants: number;
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

/**
 * What `POST /api/nodes/<id>/upload-url` hands back.
 *
 * `headers` is not advisory and not a suggestion of good practice: both entries
 * are in the URL's `X-Amz-SignedHeaders`, so a PUT carrying a different length
 * or a different type fails signature validation at S3 and writes nothing. They
 * are echoed by the API rather than rebuilt by the client for exactly that
 * reason — a client that composed its own would be guessing at what was signed.
 *
 * `Content-Length` is the odd one, and the oddity is the browser's rather than
 * this API's: it is a forbidden header name, so script cannot set it and the
 * browser supplies it from the body. See `apis/upload.ts`.
 */
export interface UploadGrant {
  id: string;
  url: string;
  expires_in: number;
  headers: Record<string, string>;
}
