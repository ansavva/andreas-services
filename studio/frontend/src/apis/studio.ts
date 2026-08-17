import type {
  AssetResponse,
  CreatedFolder,
  DeletedFolder,
  DeletedObjects,
  ReelResponse,
  RenamedFolder,
  RenamedObject,
  SortOrder,
  TextResponse,
  TreeResponse,
} from "../types";
import { apiGet, apiSend } from "./client";

/** Immediate contents of one folder. */
export function getTree(prefix: string, sort: SortOrder) {
  return apiGet<TreeResponse>("/api/tree", { prefix, sort });
}

/** One page of images and videos beneath a prefix, recursively. */
export function getReel(prefix: string, sort: SortOrder, cursor?: string) {
  return apiGet<ReelResponse>("/api/reel", { prefix, sort, cursor });
}

/**
 * A fresh presigned URL for one object.
 *
 * Two callers: the download button (`attachment`, which is the only way a
 * cross-origin download actually downloads), and the media surfaces re-signing
 * a URL that expired while the tab sat idle.
 */
export function getAsset(key: string, disposition: "inline" | "attachment" = "inline") {
  return apiGet<AssetResponse>("/api/asset", { key, disposition });
}

/** A JSON/markdown/text object's contents, for the read-only viewer. */
export function getText(key: string) {
  return apiGet<TextResponse>("/api/text", { key });
}

// ---------------------------------------------------------------------------
// Writes
//
// Studio spent most of its life unable to do any of this. See the header of
// `backend/studio_core/clients/aws/s3.py` for why that changed and what still
// bounds it.
// ---------------------------------------------------------------------------

/** Create an empty folder inside `prefix`. */
export function createFolder(prefix: string, name: string) {
  return apiSend<CreatedFolder>("POST", "/api/folder", { prefix, name });
}

/** Rename one object in place. Returns its new key. */
export function renameObject(key: string, name: string) {
  return apiSend<RenamedObject>("PATCH", "/api/object", { key, name });
}

/** Rename a folder and everything beneath it. */
export function renameFolder(prefix: string, name: string) {
  return apiSend<RenamedFolder>("PATCH", "/api/folder", { prefix, name });
}

/** Delete one or many objects — the same call either way. */
export function deleteObjects(keys: string[]) {
  return apiSend<DeletedObjects>("DELETE", "/api/objects", { keys });
}

/** Delete a folder and everything beneath it. */
export function deleteFolder(prefix: string) {
  return apiSend<DeletedFolder>("DELETE", "/api/folder", { prefix });
}
