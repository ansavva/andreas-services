import type {
  AssetResponse,
  CreatedFolder,
  DeletedFolder,
  DeletedObjects,
  Favorited,
  MovedFolder,
  MovedObjects,
  ReelResponse,
  RenamedFolder,
  RenamedObject,
  SavedText,
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

/** A JSON/markdown/text object's contents, for the text page. */
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

/**
 * Move objects into another folder, keeping their names.
 *
 * The other half of the pair `renameObject` starts: rename changes the name and
 * keeps the folder, move changes the folder and keeps the name. `destination`
 * is a prefix, never a key — a name in it would be read as a folder to create,
 * not as a rename, which is what keeps the two operations from blurring.
 */
export function moveObjects(keys: string[], destination: string) {
  return apiSend<MovedObjects>("POST", "/api/objects/move", { keys, destination });
}

/** Move a folder and everything beneath it under a different parent. */
export function moveFolder(prefix: string, destination: string) {
  return apiSend<MovedFolder>("POST", "/api/folder/move", { prefix, destination });
}

/**
 * Copy files into their own project's favourites folder.
 *
 * The one write with no destination argument, and it is missing deliberately:
 * the server derives the folder from each key, so a favourite has exactly one
 * place it can land and this call cannot be pointed anywhere else. That is what
 * lets a selection spanning two subjects be favourited in one request — each
 * file goes to its own project.
 *
 * Files already there come back as `skipped` rather than as an error, so
 * pressing the star twice is a no-op instead of a duplicate.
 */
export function addFavorites(keys: string[]) {
  return apiSend<Favorited>("POST", "/api/favorites", { keys });
}

/**
 * Overwrite a text file's contents.
 *
 * `PATCH` rather than `PUT` on purpose: the browser's preflight is answered by
 * API Gateway rather than by Flask, so the allowed-method list lives in four
 * places that have to agree, and PATCH is already in all four. See the header of
 * `backend/studio_core/routes/manage.py`.
 */
export function saveText(key: string, content: string) {
  return apiSend<SavedText>("PATCH", "/api/text", { key, content });
}

/** Delete one or many objects — the same call either way. */
export function deleteObjects(keys: string[]) {
  return apiSend<DeletedObjects>("DELETE", "/api/objects", { keys });
}

/** Delete a folder and everything beneath it. */
export function deleteFolder(prefix: string) {
  return apiSend<DeletedFolder>("DELETE", "/api/folder", { prefix });
}
