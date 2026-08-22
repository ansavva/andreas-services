import type {
  AssetResponse,
  CopiedObjects,
  CreatedFolder,
  DeletedFolder,
  DeletedObjects,
  Library,
  MovedFolder,
  MovedObjects,
  NodeKind,
  NodeRecord,
  ReelResponse,
  RenamedFolder,
  RenamedObject,
  SavedText,
  SortOrder,
  TextResponse,
  TreeResponse,
  UploadGrant,
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
 * A fresh presigned URL for one node's bytes.
 *
 * Two callers: the download button (`attachment`, which is the only way a
 * cross-origin download actually downloads), and the media surfaces re-signing
 * a URL that expired while the tab sat idle.
 *
 * **By node id, and that is the fix rather than a tidy-up (#432).** The route
 * also takes a `key`, and there it means a raw *S3* key rather than the name
 * path everything else in this file sends — the pipeline reads shared material
 * that has no catalog node through it. So a name path handed to `key` signs
 * whatever object happens to sit at that string, which since #294 is nothing at
 * all for anything uploaded through the app: its bytes are at `blobs/<id>`.
 */
export function getAsset(node: string, disposition: "inline" | "attachment" = "inline") {
  return apiGet<AssetResponse>("/api/asset", { node, disposition });
}

/**
 * A JSON/markdown/text object's contents, for the text page.
 *
 * By node id for `getAsset`'s reason, minus the trap: `GET /api/text?key=` is a
 * *name path* and agrees with `saveText` exactly (#432). The id is simply the
 * cheaper address — a path costs the API a read per segment — and every row has
 * carried one since #313.
 */
export function getText(node: string) {
  return apiGet<TextResponse>("/api/text", { node });
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

// ---------------------------------------------------------------------------
// Upload
//
// Three calls here and one — the PUT — deliberately not here: it goes to S3
// rather than to the API, carries no token, and is the only request in this app
// that is not `fetch`. See `apis/upload.ts`, which sequences all four.
// ---------------------------------------------------------------------------

/**
 * Create a node under `parent`.
 *
 * `onConflict` is `"fail"` on the API's side when it is not sent, which is what
 * every other caller wants: a name already taken is a 409 that keeps a rename
 * field open. The uploader sends `"number"` — dropping `clip.mp4` into a folder
 * that already holds one means "this too", not "stop".
 *
 * **Read the `name` off the response rather than assuming the one you sent.**
 * That is where a numbering caller learns it landed as `clip (2).mp4`; the
 * numbering happens in `catalog.create_numbered` so that it agrees with copy's,
 * and it is not re-derivable here.
 */
export function createNode(
  parent: string,
  name: string,
  kind: NodeKind,
  { onConflict }: { onConflict?: "fail" | "number" } = {},
) {
  return apiSend<NodeRecord>("POST", "/api/nodes", {
    parent,
    name,
    kind,
    ...(onConflict ? { on_conflict: onConflict } : {}),
  });
}

/**
 * Sign a PUT for one node's blob.
 *
 * `size` and `contentType` are signed into the URL, so they are a declaration
 * rather than a hint: send `file.size` and `file.type` and then send exactly
 * that file. The grant is one key, one length, one type, once.
 */
export function getUploadUrl(id: string, size: number, contentType: string) {
  return apiSend<UploadGrant>("POST", `/api/nodes/${encodeURIComponent(id)}/upload-url`, {
    size,
    content_type: contentType,
  });
}

/**
 * Finalise a placeholder once its bytes have landed.
 *
 * The row learns its size here, from `HeadObject` rather than from anything this
 * client says — it already declared one when it asked for the URL, and checking
 * beats trusting the same claim twice. Until this runs the node is a placeholder
 * a folder listing draws as a tile that will not load.
 */
export function confirmUpload(id: string) {
  return apiSend<NodeRecord>("POST", `/api/nodes/${encodeURIComponent(id)}/confirm-upload`, {});
}

/**
 * Delete one node by id.
 *
 * Here for the uploader's cleanup only: a PUT that failed leaves a row naming a
 * key with nothing behind it, and that row is what the grid draws as a broken
 * tile. Everything a person deletes goes through `deleteObjects` /
 * `deleteFolder`, which are name-path-addressed and take a selection.
 */
export function deleteNode(id: string) {
  return apiSend<{ id: string; deleted: number }>(
    "DELETE",
    `/api/nodes/${encodeURIComponent(id)}`,
  );
}
