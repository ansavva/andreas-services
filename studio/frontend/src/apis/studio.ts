import type {
  AssetResponse,
  CharacterRecord,
  CharacterProfile,
  CharacterSummary,
  CopiedNodes,
  DeletedNodes,
  Library,
  MovedNodes,
  MovieRecord,
  MovieSummary,
  NodeKind,
  NodeOwner,
  NodeRecord,
  ProjectInput,
  ProjectRecord,
  ProjectSummary,
  ReferenceEntry,
  ReferenceIndex,
  ReelResponse,
  RunPage,
  RunPlan,
  RunRecord,
  SavedText,
  SceneRecord,
  Shot,
  SceneSummary,
  SortOrder,
  TextResponse,
  TreeResponse,
  UploadGrant,
} from "../types";
import { apiGet, apiSend } from "./client";

/**
 * Which folder a listing is about.
 *
 * A node id, or nothing at all for the library root — whose id is not knowable
 * before the first request answers. **`prefix=` is gone**, and with it the last
 * read route that took a name path: a listing is a query on the parent id, so an
 * id is the argument the query already wants, while a path cost a read per
 * segment to walk down from the root first.
 */
export type FolderRef = { node?: string };

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
export function getReel(
  where: FolderRef,
  sort: SortOrder,
  cursor?: string,
  pageSize?: number,
) {
  return apiGet<ReelResponse>("/api/reel", {
    ...where,
    sort,
    cursor,
    // `apiGet` builds a query string, so the number goes over as one.
    page_size: pageSize === undefined ? undefined : String(pageSize),
  });
}

/** One node's record, by id. The SPA reads it for `parent_id`. */
export function getNode(id: string) {
  return apiGet<NodeRecord>(`/api/nodes/${encodeURIComponent(id)}`);
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
export function getAsset(
  node: string,
  disposition: "inline" | "attachment" = "inline",
) {
  return apiGet<AssetResponse>("/api/asset", { node, disposition });
}

/**
 * A JSON/markdown/text object's contents, for the text page.
 *
 * On the node's own route in both directions (`GET` here, `PATCH` in
 * `saveNodeText`), which is what closed the last gap #432 left open: the read
 * took a node id and the write took a name path, so the two addressed the same
 * file through two resolvers that could disagree. One address, one resolver.
 */
export function getNodeText(id: string) {
  return apiGet<TextResponse>(`/api/nodes/${encodeURIComponent(id)}/text`);
}

/**
 * Which entity a node belongs to, walked up its ancestry.
 *
 * The listing routes already carry `owner` on every row, so this is for the one
 * caller that has a node and no listing around it.
 */
export function getNodeOwner(id: string) {
  return apiGet<NodeOwner | null>(`/api/nodes/${encodeURIComponent(id)}/owner`);
}

// ---------------------------------------------------------------------------
// File-layer writes — node ids, and nothing else
//
// Every one of these used to take a slash-joined *name* path, and there were
// nine of them because a folder's address and a file's address were different
// strings that counted different things. An id is an id, so `move`, `copy` and
// `delete` are one route each and take a mixed selection.
//
// What that bought is the same thing ids bought the URL: a rename cannot strand
// a request in flight, and nothing has to translate between an address and a
// key. See ENTITY_MODEL.md, "one addressing scheme: the node id".
// ---------------------------------------------------------------------------

/**
 * Rename one node in place.
 *
 * `{name}` and `{parent}` are both accepted by this route and sending both is a
 * 400 — a rename changes the name and keeps the folder, a move changes the
 * folder and keeps the name, and the API refuses to guess which was meant. The
 * app therefore never sends `{parent}` here; a move goes through `moveNodes`,
 * which takes a selection.
 */
/**
 * What a file shows, and how it is selected.
 *
 * A third operation on the node address, alongside rename and move, and the API
 * refuses more than one per request — `description` and `tags` count as one,
 * because a caption editor usually sends both and neither can reorder against
 * the other.
 *
 * Both are optional here and neither is `undefined` on the wire when sent:
 * omitting a field leaves what is stored, sending `null` clears it. That is why
 * this takes an object rather than two positional arguments.
 */
export function describeNode(
  id: string,
  changes: { description?: string | null; tags?: string[] | null },
) {
  return apiSend<NodeRecord>(
    "PATCH",
    `/api/nodes/${encodeURIComponent(id)}`,
    changes,
  );
}

export function renameNode(id: string, name: string) {
  return apiSend<NodeRecord>("PATCH", `/api/nodes/${encodeURIComponent(id)}`, {
    name,
  });
}

/**
 * Move nodes into another folder, keeping their names.
 *
 * Folders and files in one call, and a folder brings its subtree. The one
 * refusal worth knowing about before the round trip is a folder into itself or
 * into its own descendant, which the destination picker greys out rather than
 * letting the request come back with.
 */
export function moveNodes(ids: string[], destination: string) {
  return apiSend<MovedNodes>("POST", "/api/nodes/move", { ids, destination });
}

/**
 * Copy nodes into another folder, leaving the sources where they are.
 *
 * Same arguments as `moveNodes`, differing in the two ways a caller feels:
 * nothing is deleted, and a name the destination already holds is numbered
 * rather than refused.
 */
export function copyNodes(ids: string[], destination: string) {
  return apiSend<CopiedNodes>("POST", "/api/nodes/copy", { ids, destination });
}

/**
 * Delete nodes — one, many, files, folders, the same call either way.
 *
 * A JSON body on a `DELETE` is unusual and deliberate: a grid selection is a few
 * hundred ids, which as repeated query parameters is a URL-length limit waiting
 * to be hit on exactly the case bulk delete exists for.
 *
 * **A folder that is some entity's `root` is refused**, and the message names
 * the entity to delete instead. That is the one hard rule the "layout is
 * convention" model leaves: every other folder in the library, including the
 * four a character starts with, is ordinary and may go.
 */
export function deleteNodes(ids: string[]) {
  return apiSend<DeletedNodes>("DELETE", "/api/nodes", { ids });
}

/**
 * Overwrite a text file's contents.
 *
 * `PATCH` rather than `PUT` on purpose: the browser's preflight is answered by
 * API Gateway rather than by Flask, so the allowed-method list lives in four
 * places that have to agree, and PATCH is already in all four.
 */
export function saveNodeText(id: string, content: string) {
  return apiSend<SavedText>(
    "PATCH",
    `/api/nodes/${encodeURIComponent(id)}/text`,
    { content },
  );
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
  return apiSend<UploadGrant>(
    "POST",
    `/api/nodes/${encodeURIComponent(id)}/upload-url`,
    {
      size,
      content_type: contentType,
    },
  );
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
  return apiSend<NodeRecord>(
    "POST",
    `/api/nodes/${encodeURIComponent(id)}/confirm-upload`,
    {},
  );
}

/**
 * Delete one node by id.
 *
 * Here for the uploader's cleanup only: a PUT that failed leaves a row naming a
 * key with nothing behind it, and that row is what the grid draws as a broken
 * tile. Everything a person deletes goes through `deleteNodes`, which takes a
 * selection — and which this is the one-id case of, kept separate because the
 * uploader is undoing its own half-finished write rather than acting on a choice
 * somebody made.
 */
export function deleteNode(id: string) {
  return apiSend<{ id: string; deleted: number }>(
    "DELETE",
    `/api/nodes/${encodeURIComponent(id)}`,
  );
}

// ---------------------------------------------------------------------------
// Entities
//
// Characters, projects, runs, scenes and movies — rows with ids, queried rather
// than walked. Three things hold for every call below:
//
// * **Ids, never slugs.** The API accepts `slug:<slug>` on the read routes for
//   the CLI, where a person types a name; the SPA always holds an id and never
//   sends one, so a rename cannot invalidate anything it is holding.
// * **`rev` on every record write.** The caller sends the `rev` it read and a
//   stale one comes back 409. That is a compare-and-swap, not a check followed
//   by a write with a window in it.
// * **Library scope is the header.** `X-Studio-Library` is set once in
//   `apis/client`; nothing here threads a library through.
// ---------------------------------------------------------------------------

/** Every character in the library, with a signed hero URL per card. */
export function getCharacters(q?: string) {
  return apiGet<CharacterSummary[]>("/api/characters", { q });
}

/** One character's whole record, `profile` inline. */
export function getCharacter(id: string) {
  return apiGet<CharacterRecord>(`/api/characters/${encodeURIComponent(id)}`);
}

export function createCharacter(body: {
  slug: string;
  display_name: string;
  profile?: CharacterProfile;
}) {
  return apiSend<CharacterRecord>("POST", "/api/characters", body);
}

/**
 * Rename, retitle, or re-hero a character.
 *
 * **A rename here moves nothing.** No object is copied, no run document is
 * rewritten, and every reference, binding and default-set entry keeps pointing
 * at the same node ids — the slug is a label on one row and the root folder's
 * name changes in the same transaction. It used to be a `PATCH` per slugged
 * basename across four pools plus a rewrite pass over every run that cited the
 * old path.
 */
export function patchCharacter(
  id: string,
  body: { rev: number; slug?: string; display_name?: string; hero?: string },
) {
  return apiSend<EntityPatch<CharacterRecord>>(
    "PATCH",
    `/api/characters/${encodeURIComponent(id)}`,
    body,
  );
}

/**
 * Replace the whole bible.
 *
 * A whole-document write rather than a merge because that is what the profile
 * editor produces: it renders every section it was given and hands the same
 * shape back, so a field it removed was removed on purpose.
 *
 * **The route also merges, and this app has no wrapper for that.** `{patch}`
 * updates the sections it names and leaves the rest; the wrapper for it was
 * written, never called, and is deleted rather than kept as a promise nothing
 * behind it is exercising. Add it back the day a caller wants one section.
 *
 * **`PATCH`, despite replacing.** The two operations share one address and are
 * told apart by which key the body carries, so they cannot use different verbs:
 * `{profile}` replaces and `{patch}` merges. This sent `PUT` from the day the
 * route was written, and `PUT` is neither registered on it nor in the API's
 * `CORS_METHODS` — so every profile save from this app failed the preflight,
 * and nothing caught it because the backend tests call the route directly.
 *
 * **Which is why these are named `set*` and not `put*`.** The verb was fixed
 * and the name was not, so three wrappers went on advertising a method none of
 * them sends. It is not a cosmetic mismatch: a reader who trusts the name
 * writes `PUT` into the next route, the preflight fails in the browser and
 * nowhere else, and the same afternoon gets spent twice.
 */
export function setCharacterProfile(
  id: string,
  profile: CharacterProfile,
  rev: number,
) {
  return apiSend<EntityPatch<CharacterRecord>>(
    "PATCH",
    `/api/characters/${encodeURIComponent(id)}/profile`,
    { profile, rev },
  );
}

/**
 * Delete a character.
 *
 * `files` defaults to keeping them — the folder is orphaned into the library
 * root rather than destroyed. The reverse default loses media to a typo, and
 * these are the only copies.
 */
/**
 * Delete a character. `force` drops the links projects and runs hold on it.
 *
 * **The links are the reason this refuses by default.** They are what makes
 * "every run of this subject" answerable, so dropping them is a real loss and
 * has to be asked for. A run itself is untouched either way: it really did use
 * this character, and deleting the character is not a reason to delete the work
 * — which is exactly why a project deletes with `cascade` and a character does
 * not have one.
 */
export function deleteCharacter(
  id: string,
  files: "keep" | "delete" = "keep",
  force = false,
) {
  return apiSend<{ id: string; deleted: number }>(
    "DELETE",
    `/api/characters/${encodeURIComponent(id)}?files=${files}` +
      (force ? "&force=1" : ""),
  );
}

/** The reference index, grouped and in `order` within each group. */
export function getReferences(id: string, group?: string) {
  return apiGet<ReferenceIndex>(
    `/api/characters/${encodeURIComponent(id)}/references`,
    { group },
  );
}

/**
 * Attach an existing node as a reference.
 *
 * Two steps, and always has been: the bytes arrive, then a person decides the
 * image is identity. `after` places the entry between two existing ones by
 * taking the midpoint of their `order` values — one write, neither neighbour
 * touched.
 */
export function addReference(
  id: string,
  body: {
    node: string;
    group: string;
    description?: string;
    tags?: string[];
    after?: string;
  },
) {
  return apiSend<ReferenceEntry>(
    "POST",
    `/api/characters/${encodeURIComponent(id)}/references`,
    body,
  );
}

/**
 * Change one entry's group, description, tags or position.
 *
 * Each of those used to be something else entirely: the group was the folder the
 * file sat in, the position was a number in its filename, and the description
 * was a key in the bible that every write rewrote whole. All three are one row's
 * write now, so two people describing two references stop fighting over one
 * document.
 */
export function patchReference(
  id: string,
  node: string,
  body: {
    group?: string;
    description?: string;
    tags?: string[];
    after?: string;
  },
) {
  return apiSend<ReferenceEntry>(
    "PATCH",
    `/api/characters/${encodeURIComponent(id)}/references/${encodeURIComponent(node)}`,
    body,
  );
}

/** Detach an entry. The file stays exactly where it is. */
export function deleteReference(id: string, node: string) {
  return apiSend<{ node: string }>(
    "DELETE",
    `/api/characters/${encodeURIComponent(id)}/references/${encodeURIComponent(node)}`,
  );
}

/**
 * The ordered handful a generation reaches for when nothing else is asked.
 *
 * **`rev` is required**, and this did not send it — the route compare-and-swaps
 * the record like every other write on it. Nothing in the app calls this yet, so
 * the omission had no symptom; the CLI's copy of the same mistake failed with
 * `rev is required` the moment #479 let the request reach the API at all.
 *
 * Every member must already be a reference. The API refuses a node with no
 * `REF#` row rather than accepting a set that names an image a shoot cannot send.
 */
/**
 * The acknowledgement this route answers with — **not** a character record.
 *
 * It used to be typed `CharacterRecord`, which was simply false: the route
 * returns `{id, default_set, rev}` and nothing else. Nothing read the result
 * until the grid learned to write the set, and the first caller to trust the
 * type fed three fields into the page's record — so the character lost its
 * name, its slug and its root folder. The data was never touched; only the
 * screen was wrong, which is the worst way for a type to be a lie.
 */
/**
 * What a WRITE to an entity answers with — never as much as a `GET`.
 *
 * **This is a whole class of bug, not one route.** `GET /characters/<id>` adds
 * `hero_url` and `counts` on top of the stored record; `GET /projects/<id>`
 * adds the expanded `characters`. Every `PATCH` returns `jsonify(updated)` —
 * the record as stored, without any of it — and the wrappers here all claimed
 * the full type.
 *
 * It bit twice before being named. Feeding a default-set acknowledgement into
 * the page's record left a character with no name, no slug and no root folder;
 * feeding a `PATCH /characters` reply in crashed the project page on
 * `record.counts.runs`.
 *
 * So a write is typed as what it is — a patch — and every caller MERGES it into
 * what it already holds. Merging is correct whatever a route omits, which is
 * the property that makes this safe against the next route that omits
 * something new.
 */
export type EntityPatch<T> = Partial<T> & { id: string; rev: number };

export interface DefaultSetAck {
  id: string;
  default_set: string[];
  rev: number;
}

export function setDefaultSet(id: string, nodes: string[], rev: number) {
  return apiSend<DefaultSetAck>(
    "PATCH",
    `/api/characters/${encodeURIComponent(id)}/default-set`,
    {
      nodes,
      rev,
    },
  );
}

/**
 * Revise one shot of a storyboard.
 *
 * The route merges per-field onto what a render already put there, so sending a
 * reworded beat cannot discard the panel underneath it. Scenes carry no `rev`
 * and that is deliberate — a scene is driven by the machine rendering it, in
 * sequence, so demanding one would make every write re-read the record first.
 */
export function patchShot(
  sceneId: string,
  shotId: string,
  body: Partial<Shot>,
) {
  return apiSend<Shot>(
    "PATCH",
    `/api/scenes/${encodeURIComponent(sceneId)}/shots/${encodeURIComponent(shotId)}`,
    body,
  );
}

/** Runs that used this character — one query, where it used to be a full walk. */
export function getCharacterRuns(id: string, cursor?: string) {
  return apiGet<RunPage>(`/api/characters/${encodeURIComponent(id)}/runs`, {
    cursor,
  });
}

/** Projects this character is involved in — a question with no answer before. */
export function getCharacterProjects(id: string) {
  return apiGet<ProjectSummary[]>(
    `/api/characters/${encodeURIComponent(id)}/projects`,
  );
}

export function getProjects() {
  return apiGet<ProjectSummary[]>("/api/projects");
}

export function getProject(id: string) {
  return apiGet<ProjectRecord>(`/api/projects/${encodeURIComponent(id)}`);
}

export function createProject(body: {
  slug: string;
  title?: string;
  description?: string;
  characters?: string[];
}) {
  return apiSend<ProjectRecord>("POST", "/api/projects", body);
}

export function patchProject(
  id: string,
  body: {
    rev: number;
    slug?: string;
    title?: string;
    description?: string;
    hero?: string;
  },
) {
  return apiSend<EntityPatch<ProjectRecord>>(
    "PATCH",
    `/api/projects/${encodeURIComponent(id)}`,
    body,
  );
}

/**
 * Delete a project. `cascade` takes its runs, scenes and movies with it.
 *
 * **Without `cascade` this refuses while the project holds anything**, because
 * a run's envelope names its project and deleting the project alone leaves
 * every one of them pointing at nothing. The API also has `?force=1`, which
 * does precisely that; it is not exposed here on purpose.
 */
export function deleteProject(
  id: string,
  files: "keep" | "delete" = "keep",
  cascade = false,
) {
  return apiSend<{
    id: string;
    files: string;
    removed: Record<string, number>;
  }>(
    "DELETE",
    `/api/projects/${encodeURIComponent(id)}?files=${files}` +
      (cascade ? "&cascade=1" : ""),
  );
}

/** Replace the involvement links wholesale — this is `projects link` / `unlink`. */
/**
 * Replace who a project is about. **The answer is mergeable.**
 *
 * It was not, and the asymmetry cost three bugs: the route answered with the id
 * strings it had been handed while a `GET` expands the same field into
 * `{id, slug, display_name}` objects. Merging replaced objects with strings, so
 * `characters.map(c => c.id)` became a list of `undefined` and every chip read
 * unselected while the write itself had succeeded — a failure no type could
 * catch, because the type was an assertion about a shape nobody had checked.
 *
 * The route now answers in the shape `GET` sends. The refetch this used to
 * require is gone, and `ProjectPage` lost the `onReload` prop that existed for
 * nothing else.
 */
export function setProjectCharacters(id: string, characters: string[]) {
  return apiSend<{ id: string; characters: ProjectRecord["characters"] }>(
    "PATCH",
    `/api/projects/${encodeURIComponent(id)}/characters`,
    { characters },
  );
}

/**
 * The working pool, name-ascending. Position in this list is `--input N`.
 *
 * **Unwrapped from `{folder, inputs}`.** This was typed as a bare array and is
 * not one, so the Inputs tab did `data.map` on an object and threw — the whole
 * tab was the error boundary. The type said otherwise, and a type on an
 * `apiGet` is an assertion about a shape nobody checked, not a check.
 *
 * `folder` is dropped rather than returned: nothing here uploads into the pool,
 * and a caller that needs it can ask for it when there is one.
 */
export function getProjectInputs(id: string) {
  return apiGet<{ folder: string; inputs: ProjectInput[] }>(
    `/api/projects/${encodeURIComponent(id)}/inputs`,
  ).then((page) => page.inputs ?? []);
}

/**
 * A project's scenes, unwrapped from the page the route answers with.
 *
 * **`/api/projects/<id>/{runs,scenes,movies}` all answer `{ "<kind>s": [...],
 * "cursor": null }`**, never a bare array — one `_listing` builds all three.
 * These two were typed as the array and handed the object straight to a caller
 * that did `data.length === 0` and then `data.map(...)`: `undefined === 0` is
 * false, so the empty-state branch was skipped and the map threw. The Scenes and
 * Movies tabs of a project crashed, and the Scenes tab is the only route to a
 * scene in the app — so a storyboard was unreachable from the UI.
 *
 * `RunsTable` reads `page.runs` and was always fine, which is why this survived:
 * the one listing anybody had opened was the one that unwrapped.
 */
export function getProjectScenes(id: string) {
  return apiGet<{ scenes: SceneSummary[]; cursor: string | null }>(
    `/api/projects/${encodeURIComponent(id)}/scenes`,
  ).then((page) => page.scenes ?? []);
}

export function getProjectMovies(id: string) {
  return apiGet<{ movies: MovieSummary[]; cursor: string | null }>(
    `/api/projects/${encodeURIComponent(id)}/movies`,
  ).then((page) => page.movies ?? []);
}

/**
 * The runs query — the route that replaced a walk over every project's every run
 * folder reading three JSON documents each.
 *
 * Every filter is a field on the row, so combining them costs nothing. `cursor`
 * is real pagination: the listing rows are ranged on the creation timestamp
 * under the project's partition, so a page is a query rather than an offset into
 * a result that had to be built first.
 */
export function getRuns(
  params: {
    project?: string;
    character?: string;
    model?: string;
    status?: string;
    /**
     * `"drafts"` un-hides drafts, which the route otherwise keeps out of a
     * listing that names no status. Pass it whenever the caller means EVERY
     * run — a screen offering "Any status" and then quietly dropping one is
     * worse than a screen that never offered the choice.
     */
    include?: string;
    since?: string;
    limit?: string;
    cursor?: string;
  } = {},
) {
  return apiGet<RunPage>("/api/runs", params);
}

/**
 * One run's envelope, with `outputs` and `bindings` expanded to nodes and signed
 * URLs — and `payload` left as three node ids.
 *
 * That last part is the rule surviving its move: studio stores the request and
 * response bodies and decodes neither. Read them with `getNodeText` and show
 * them as text.
 */
export function getRun(id: string) {
  return apiGet<RunRecord>(`/api/runs/${encodeURIComponent(id)}`);
}

/**
 * Approve a draft — record that somebody read THIS payload and said yes to it.
 *
 * **The digest is the whole of it.** It is sent, not stored: the API recomputes
 * the digest of what is actually on the row and answers 409 `stale_digest` if
 * the two disagree, so an approval cannot outlive the payload it was given for.
 * Approve-then-edit is the failure hard rule #2 names and that nothing checked
 * until this existed.
 */
export function approveRun(id: string, digest: string) {
  return apiSend<RunRecord>(
    "POST",
    `/api/runs/${encodeURIComponent(id)}/approve`,
    {
      digest,
    },
  );
}

/** Take an approval back. The run returns to `draft` and cannot be submitted. */
export function revokeRunApproval(id: string) {
  return apiSend<RunRecord>(
    "DELETE",
    `/api/runs/${encodeURIComponent(id)}/approve`,
  );
}

/**
 * Send an approved run to the model. **This is the call that spends money.**
 *
 * **The app could not do this at all until generation moved into the API.** The
 * spending lived in the CLI, holding the provider token, so a run approved on
 * this page then had to be sent from a terminal — the page could show the
 * payload, record the yes, and not act on it. It is one route now, and the
 * credential stays server-side where the SPA can never hold one.
 *
 * Refused with 409 unless the run is approved and the approval still matches the
 * payload. That is the same gate `runs submit` passes through, called from the
 * same place, so the app and the CLI cannot come to disagree about what may be
 * sent.
 *
 * It returns as soon as the provider has accepted the prediction — the run comes
 * back `running`, not `succeeded`. What closes it is a callback, minutes later,
 * which is why `RunPage` polls while a run is not terminal.
 */
export function submitRun(id: string) {
  return apiSend<RunRecord>(
    "POST",
    `/api/runs/${encodeURIComponent(id)}/submit`,
  );
}

/**
 * Ask the provider what happened to a run that went out and never came back.
 *
 * A generation is closed by a callback, and a callback can be lost — a deploy
 * landing mid-flight, a signature the API refused, a queue nobody drained. The
 * run sits at `running` with a prediction id: legible, and never resolving.
 *
 * Safe to repeat and safe to press on a run that is merely still working: it
 * asks, and a prediction that has not finished leaves the row alone.
 */
export function reconcileRun(id: string) {
  return apiSend<RunRecord>(
    "POST",
    `/api/runs/${encodeURIComponent(id)}/reconcile`,
  );
}

/**
 * Rewrite a draft's authored half. **Clears the approval, every time.**
 *
 * That is not this function's doing — the route does it — but a caller needs to
 * know, because finding out at submit time is finding out too late. Refused
 * outright once the run has been submitted: a plan edited afterwards would sit
 * beside `request.json` describing something that was never sent.
 */
export function patchRunPlan(id: string, plan: RunPlan) {
  return apiSend<RunRecord>(
    "PATCH",
    `/api/runs/${encodeURIComponent(id)}/plan`,
    {
      plan,
    },
  );
}

/** Replace the ordered images a draft binds. Clears the approval, every time. */
export function patchRunSends(
  id: string,
  sends: { field: string; role: string | null; node: string }[],
) {
  return apiSend<RunRecord>(
    "PATCH",
    `/api/runs/${encodeURIComponent(id)}/sends`,
    {
      sends,
    },
  );
}

export function getScene(id: string) {
  return apiGet<SceneRecord>(`/api/scenes/${encodeURIComponent(id)}`);
}

/**
 * Change a scene's own fields — its setting, its title, its status.
 *
 * `setting` is the one a person edits: it is prepended byte-identically to
 * every panel prompt, so it is the single lever that keeps separately rendered
 * panels agreeing on one room, and it was readable on the scene screen with no
 * way to change it. `PATCH /scenes/<id>` has accepted it all along —
 * `SCENE_PLAN` on the route — so this is the wrapper that was missing, not the
 * capability.
 */
export function patchScene(id: string, body: Partial<SceneRecord>) {
  return apiSend<SceneRecord>(
    "PATCH",
    `/api/scenes/${encodeURIComponent(id)}`,
    body,
  );
}

export function getMovie(id: string) {
  return apiGet<MovieRecord>(`/api/movies/${encodeURIComponent(id)}`);
}
