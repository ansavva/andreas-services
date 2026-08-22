import type {
  AssetResponse,
  CopiedObjects,
  CreatedFolder,
  DeletedFolder,
  DeletedObjects,
  Library,
  MovedFolder,
  MovedObjects,
  NodeRecord,
  ReelResponse,
  RenamedFolder,
  RenamedObject,
  SavedText,
  SortOrder,
  TextResponse,
  TreeResponse,
} from "../types";
import { apiGet, apiSend } from "./client";

/**
 * Which folder a listing is about — one address or the other, never both.
 *
 * `node` is the cheap one and the one the SPA routes on: a listing is a query on
 * the parent id, so an id is the argument the query already wants, while a path
 * costs a read per segment to walk down from the library root first. `prefix`
 * stays because the destination picker is choosing a *prefix* for a write route
 * that takes one, and because every share link ever handed out is a path.
 *
 * Neither is the library root, which is why both are optional. Sending both is a
 * 400 — the API refuses to guess which one meant it.
 */
export type FolderRef = { node?: string; prefix?: string };

/**
 * The libraries the signed-in caller is in.
 *
 * **The one call that is authenticated and not about a library**, which is what
 * makes it the first one the app makes: every other route resolves a library
 * before it runs, and the id it resolves against comes from here. Called once,
 * by `context/LibraryContext`, before anything is rendered that could fetch.
 */
export function getLibraries() {
  return apiGet<Library[]>("/api/libraries");
}

/** Immediate contents of one folder. */
export function getTree(where: FolderRef, sort: SortOrder) {
  return apiGet<TreeResponse>("/api/tree", { ...where, sort });
}

/** One page of images and videos beneath a folder, recursively. */
export function getReel(where: FolderRef, sort: SortOrder, cursor?: string) {
  return apiGet<ReelResponse>("/api/reel", { ...where, sort, cursor });
}

/** One node's record, by id. The SPA reads it for `parent_id`. */
export function getNode(id: string) {
  return apiGet<NodeRecord>(`/api/nodes/${encodeURIComponent(id)}`);
}

/**
 * The node a slash-joined name path names, walked from the library root.
 *
 * The one call the legacy-URL resolver makes, and the reason old `/projects/…`
 * share links keep working: it turns the address they carry into the id the app
 * now routes on. An empty path is the root.
 */
export function resolvePath(path: string) {
  return apiGet<NodeRecord>("/api/resolve", { path });
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
 * Copy objects into another folder, leaving the sources where they are.
 *
 * Same arguments as `moveObjects`, and it differs in two ways that both matter
 * to the caller. Nothing is deleted. And a name the destination already holds is
 * *numbered* — `clip.mp4` lands as `clip (2).mp4` — rather than refusing the
 * whole request the way a move does, because copying a file into a folder that
 * already has one by that name is ordinary rather than a mistake.
 */
export function copyObjects(keys: string[], destination: string) {
  return apiSend<CopiedObjects>("POST", "/api/objects/copy", { keys, destination });
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
