/** Shapes returned by the studio API. Mirrors `studio_core.services.browse`. */

export type MediaKind = "image" | "video" | "text" | "other";

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
  breadcrumbs: Crumb[];
  folders: FolderEntry[];
  files: FileEntry[];
  counts: { folders: number; files: number; media: number };
}

export interface ReelResponse {
  prefix: string;
  items: FileEntry[];
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
