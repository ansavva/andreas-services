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

export interface FileEntry {
  key: string;
  name: string;
  size: number;
  last_modified: string | null;
  kind: MediaKind;
  /** Presigned inline GET. Short-lived — re-sign through `getAsset` when it dies. */
  url: string;
  /** Highlighting hint, present on text files only. */
  language?: string;
  /**
   * Where a favourite of this file would be copied, or null if it cannot be one.
   *
   * Derived by the API from the key — `projects/<subject>/…` favourites into
   * `projects/<subject>/favorites/`, and nothing in `characters/` favourites at
   * all, because that tree holds who a subject is rather than what was generated
   * of them. It arrives per file rather than being worked out here on purpose:
   * the reel walks across subjects, so two items on screen can belong to
   * different projects, and the bucket's layout is the backend's to know.
   */
  favorites_prefix: string | null;
  /** True when this file is already in its project's favourites. */
  favorited: boolean;
}

export interface FolderEntry {
  prefix: string;
  name: string;
}

export interface Crumb {
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

export interface Favorited {
  favorited: number;
  /** Files that were already there — a second press is a no-op, not an error. */
  skipped: number;
  /** The new keys, which may be numbered if the flat folder held the name. */
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
