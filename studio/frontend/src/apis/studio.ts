import type {
  AssetResponse,
  CharacterRecord,
  CharacterProfile,
  CharacterSummary,
  CopiedNodes,
  CreateRunBody,
  CreatedRun,
  DeletedNodes,
  Library,
  ModelEntry,
  ModelSchema,
  MovedNodes,
  MovieRecord,
  MovieSummary,
  NodeKind,
  NodeOwner,
  NodeRecord,
  ProjectRecord,
  ProjectSummary,
  EntryKind,
  Depth,
  NodeListing,
  FolderListing,
  MediaListing,
  FileEntry,
  FolderEntry,
  RunFeedPage,
  RunPage,
  RunPlan,
  RunRecord,
  SelectionResponse,
  SavedText,
  SceneRecord,
  Shot,
  SceneSummary,
  SortOrder,
  TextResponse,
  UploadGrant,
  TemplateLibrary,
  TagInUse,
  TagScope,
  PromptTemplate,
  TemplateBody,
  SpecBlock,
} from "../types";
import { apiGet, apiSend } from "./client";

/**
 * Which folder a listing is about.
 *
 * A node id, or nothing at all for the library root — whose id is not knowable
 * before the first request answers. Never a name path: a listing is a query on
 * the parent id, so an id is the argument the query already wants, while a path
 * would cost a read per segment to walk down from the root first.
 */
type FolderRef = { node?: string };

/** What every listing filter can narrow on. Both readers below accept them. */
interface ListFilter {
  /** An entry must carry ALL of these. */
  tag?: string[];
  /** `folder`, `image`, `video`, `text`, `other`. Omit for everything. */
  kind?: EntryKind[];
}

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

/**
 * The one listing route: everything under a node, at a depth, filtered.
 *
 * **`GET /api/tree` and `GET /api/reel` were folded into it.** They were two of
 * three answers this API gave to "what is under this node" — the third being the
 * one the CLI used — and they differed in depth, in which kinds they admitted
 * and in whether they paged. Those are arguments, so there is one route and the
 * two readers below are conveniences over it rather than two endpoints.
 */
export function listNodes(
  where: FolderRef,
  opts: ListFilter & {
    depth?: Depth;
    sort?: SortOrder;
    cursor?: string;
    limit?: number;
  } = {},
) {
  return apiGet<NodeListing>("/api/nodes", {
    under: where.node,
    depth: opts.depth,
    sort: opts.sort,
    cursor: opts.cursor,
    kind: opts.kind?.length ? opts.kind.join(",") : undefined,
    tag: opts.tag?.length ? opts.tag.join(",") : undefined,
    // `apiGet` builds a query string, so the number goes over as one.
    limit: opts.limit === undefined ? undefined : String(opts.limit),
  });
}

/**
 * Immediate contents of one folder, split into folders and files.
 *
 * **The split is the client's job now**, which is what makes one array on the
 * wire the right shape: a caller wanting them apart does this, and a caller
 * wanting them in one order — every recursive listing — cannot put them back
 * together once the server has separated them.
 */
export async function getFolder(
  where: FolderRef,
  sort: SortOrder,
  filter: ListFilter = {},
): Promise<FolderListing> {
  // **Narrowing searches the BRANCH.** Not knowing which folder a tagged image
  // is in is the whole reason for asking by tag, so a filter that only looked in
  // the folder you happen to be standing in would answer the question nobody
  // has. A `kind` filter is the same question in the other vocabulary — "every
  // picture under this character" is not a request about one folder — so both
  // go deep, and an unfiltered listing stays the one-level readdir it was.
  const depth = filter.tag?.length || filter.kind?.length ? "all" : "1";
  const listing = await listNodes(where, { ...filter, sort, depth });
  return {
    prefix: listing.prefix,
    sort: listing.sort,
    depth: listing.depth,
    tags: listing.tags,
    breadcrumbs: listing.breadcrumbs,
    folders: listing.entries.filter((e): e is FolderEntry => e.kind === "folder"),
    files: listing.entries.filter((e): e is FileEntry => e.kind !== "folder"),
  };
}

/** One page of images and videos beneath a folder, recursively. */
export async function getMedia(
  where: FolderRef,
  sort: SortOrder,
  cursor?: string,
  filter: ListFilter = {},
): Promise<MediaListing> {
  const listing = await listNodes(where, {
    ...filter,
    sort,
    cursor,
    depth: "all",
    kind: filter.kind ?? ["image", "video"],
  });
  return {
    prefix: listing.prefix,
    sort: listing.sort,
    tags: listing.tags,
    items: listing.entries as FileEntry[],
    total: listing.total,
    truncated: listing.truncated,
    next_cursor: listing.next_cursor,
  };
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
 * **By node id, never by name path.** The route also takes a `key`, and there
 * it means a raw *S3* key — the pipeline reads shared material that has no
 * catalog node through it. A name path handed to `key` signs whatever object
 * happens to sit at that string, which is nothing at all for anything uploaded
 * through the app: its bytes are at `blobs/<id>`.
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
 * `saveNodeText`), so the read and the write address the same file through one
 * resolver that cannot disagree with itself.
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
// An id is an id, so `move`, `copy` and `delete` are one route each and take a
// mixed selection of folders and files.
//
// What that buys is the same thing ids buy the URL: a rename cannot strand
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
// * **Ids, and there is no other address.** The SPA always holds an id and
//   never sends a name, so a rename cannot invalidate anything it is holding.
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
  name: string;
  profile?: CharacterProfile;
}) {
  return apiSend<CharacterRecord>("POST", "/api/characters", body);
}

/**
 * Rename or re-hero a character.
 *
 * **A rename here moves nothing.** No object is copied, no run document is
 * rewritten, and every reference, binding and default-set entry keeps pointing
 * at the same node ids — the name is a label on one row and nothing else moves,
 * the root folder included, because it is named by the id.
 */
export function patchCharacter(
  id: string,
  body: { rev: number; name?: string; hero?: string },
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

/**
 * One tag vocabulary, by name, with how many things carry each tag.
 *
 * **Derived from what is in use rather than stored**, which is what makes the
 * deletion rule true by construction: a tag exists exactly while something
 * carries it, so there is no list that can fall out of step with the things.
 */
export function getTags(scope: TagScope) {
  return apiGet<{ scope: TagScope; tags: TagInUse[] }>("/api/tags", { scope });
}

/**
 * Rename one tag everywhere in its scope.
 *
 * A bulk write behind a single-item address, and that is the honest shape: the
 * name IS the identity — a filter passes it, the CLI passes it, a stored row
 * holds it — so renaming half the carriers would leave two tags where somebody
 * believes there is one.
 */
export function renameTag(scope: TagScope, name: string, next: string) {
  return apiSend<{ name: string; changed: number }>(
    "PATCH",
    `/api/tags/${encodeURIComponent(name)}?scope=${scope}`,
    { name: next },
  );
}

/** Take one tag off everything in its scope, which is what deleting it IS. */
export function deleteTag(scope: TagScope, name: string) {
  return apiSend<{ name: string; changed: number }>(
    "DELETE",
    `/api/tags/${encodeURIComponent(name)}?scope=${scope}`,
  );
}

export function getTemplates() {
  return apiGet<TemplateLibrary>("/api/templates");
}

export function saveBlock(name: string, text: string) {
  return apiSend<SpecBlock>("PATCH", `/api/templates/blocks/${encodeURIComponent(name)}`, {
    text,
  });
}

/**
 * Write one template, addressed by its id. A `name` in the body renames it.
 *
 * The id is minted here for a create, which is why there is no separate POST:
 * a create and an update are the same call with the same shape, and the caller
 * already knows which it is doing.
 */
export function saveTemplate(templateId: string, body: TemplateBody) {
  return apiSend<PromptTemplate>(
    "PATCH",
    `/api/templates/${encodeURIComponent(templateId)}`,
    body,
  );
}

/** A UUID for a template about to be created. */
export function newTemplateId() {
  return `template-${crypto.randomUUID()}`;
}

export function deleteBlock(name: string) {
  return apiSend<{ name: string }>("DELETE", `/api/templates/blocks/${encodeURIComponent(name)}`);
}

export function deleteTemplate(templateId: string) {
  return apiSend<{ id: string }>(
    "DELETE",
    `/api/templates/${encodeURIComponent(templateId)}`,
  );
}

/**
 * What a run plan's template would become, expanded against this run's cast.
 *
 * Writes nothing, so the editor can call it on every change — the save is the
 * write, and what a prompt will SAY is exactly the thing that tells you whether
 * it is right.
 */
export function previewPlanPrompt(runId: string, template: string) {
  return apiSend<{
    prompt: string;
    /** Where each `{character.N.field}` landed in `prompt`, so it can be marked. */
    spans: Array<{ name: string; start: number; end: number }>;
    characters: number;
  }>(
    "POST",
    `/api/runs/${encodeURIComponent(runId)}/plan/preview`,
    { template },
  );
}

/**
 * A write answers with LESS than a read does.
 *
 * adds the expanded `characters`. Every `PATCH` returns `jsonify(updated)` —
 * the record as stored, without any of it — and the wrappers here all claimed
 * the full type.
 *
 * It bit twice before being named. Feeding a default-set acknowledgement into
 * the page's record left a character with no name and no root folder;
 * feeding a `PATCH /characters` reply in crashed the project page on
 * `record.counts.runs`.
 *
 * So a write is typed as what it is — a patch — and every caller MERGES it into
 * what it already holds. Merging is correct whatever a route omits, which is
 * the property that makes this safe against the next route that omits
 * something new.
 */
type EntityPatch<T> = Partial<T> & { id: string; rev: number };

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

/**
 * The ordered images a model would actually be shown, and the cap they face.
 *
 * **A route rather than a function in each half of studio**, so the CLI and this
 * app cannot disagree about what slot 3 was. `pick` names files and `tag` names
 * tags, both comma-joined; `pick` wins, and neither given means the `default`
 * images. There is no `group` parameter because a group IS a tag.
 *
 * **One refusal a caller has to surface rather than work around**, a 409:
 * `over_cap`, when more images match than the model will take, carrying every
 * candidate so a person can choose. Never truncated, because a generation shown
 * seven of eighteen images silently is a result nobody can explain afterwards.
 * A stale selection is not a second refusal: a tag cannot outlive the file it
 * is written on.
 *
 * **`ApiError.message` is the CODE on that refusal, not the sentence.** The API's
 * ordinary errors put their prose in `error` and a structured one puts the code
 * there, so `apis/client` — which reads `error` first — surfaces `over_cap`
 * verbatim and drops the `index`. A caller that wants the candidates has to read
 * the response itself; a caller that only reports needs to say more than the
 * code word.
 */
export function getCharacterSelection(
  id: string,
  opts: { pick?: string; tag?: string; group?: string; limit?: number } = {},
) {
  return apiGet<SelectionResponse>(
    `/api/characters/${encodeURIComponent(id)}/selection`,
    {
      pick: opts.pick,
      tag: opts.tag,
      group: opts.group,
      limit: opts.limit === undefined ? undefined : String(opts.limit),
    },
  );
}

/** Runs that used this character — one query, not a walk. */
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
  name?: string;
  description?: string;
  characters?: string[];
}) {
  return apiSend<ProjectRecord>("POST", "/api/projects", body);
}

export function patchProject(
  id: string,
  body: {
    rev: number;
    name?: string;
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
 * Replace who a project is about. **The answer is mergeable**: the route
 * answers in the shape `GET` sends — `{id, name}` objects, not the id strings
 * it was handed — so the caller merges it into the record instead of
 * refetching. A route that echoed strings would put them where the record
 * holds objects, and `characters.map(c => c.id)` would read every chip as
 * unselected while the write had succeeded — a failure no type can catch.
 */
export function setProjectCharacters(id: string, characters: string[]) {
  return apiSend<{ id: string; characters: ProjectRecord["characters"] }>(
    "PATCH",
    `/api/projects/${encodeURIComponent(id)}/characters`,
    { characters },
  );
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
// A type alias rather than an interface: an alias carries the implicit index
// signature `apiGet`'s `Record<string, string | undefined>` asks for.
type RunsQuery = {
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
  /**
   * **The one filter that is not for a screen.** It answers "has this exact
   * payload already gone out here", which is a question about money rather
   * than about what to draw — pass `include: "drafts"` with it, or the draft
   * being asked about is itself hidden from the answer.
   */
  fingerprint?: string;
  since?: string;
  /**
   * A prompt search: case-insensitive substring over the plan's prompt, within
   * whatever scope and filters the rest of the query names. The catalog has no
   * text index, so one call scans a bounded number of rows — **a page may come
   * back short, or empty, with `cursor` still set, and that means keep
   * going**, not "nothing more". See `docs/WEB_APP.md#the-entity-routes`.
   */
  q?: string;
  limit?: string;
  cursor?: string;
};

/**
 * `GET /api/runs`, in either of its two shapes.
 *
 * Without `view` it is the listing — `RunSummary` rows, the projection the
 * grid, the duplicate-submission check and the CLI read, cheap because it
 * reads no envelope. `view: "feed"` asks for `RunFeedRow`s: the plan, every
 * send and every output signed, the cast by name, from one call and no fetch
 * per row. The feed page is clamped server-side (`STUDIO_MAX_FEED_ROWS`, 50)
 * and says so in `cursor`, so a caller pages rather than raising `limit`.
 */
export function getRuns(params: RunsQuery & { view: "feed" }): Promise<RunFeedPage>;
export function getRuns(params?: RunsQuery & { view?: undefined }): Promise<RunPage>;
export function getRuns(params: RunsQuery & { view?: "feed" } = {}) {
  return apiGet<RunPage | RunFeedPage>("/api/runs", params);
}

/**
 * Create a run as a **draft**. Nothing is submitted and nothing is billed.
 *
 * Only `project`, `kind` and `model` are required; a draft with no plan and no
 * sends is legal, and is what the composer strip makes before the editor fills
 * it in. The fingerprint is recomputed server-side from what actually landed
 * and comes back on the 201 — never derived here, because the hash under it has
 * had three implementations in this repository and one of them silently
 * disagreed.
 */
export function createRun(body: CreateRunBody) {
  return apiSend<CreatedRun>("POST", "/api/runs", body);
}

/**
 * Delete a run. `files` keeps its folder by default.
 *
 * **The route has no status gate** — it will delete a succeeded run and its
 * outputs as readily as an abandoned draft. The app offers this on unsubmitted
 * runs only, which is a decision about what to put a button on rather than
 * something this call enforces.
 */
/**
 * Replace which characters a run is about.
 *
 * **A run's cast could only be set at creation, and the app never set it.** The
 * characters are edges — `RUN#<id>` / `CHAR#<id>` — and `POST /api/runs` was
 * the only writer, so every run the app made bound nobody and could not cite
 * one: a prompt names its cast by position, and `{character.1.top}` had nothing
 * to fill from with no way to supply it.
 *
 * A replace, like every other edge set: a client that sent a difference and got
 * it wrong would accumulate links nothing removes.
 */
export function setRunCharacters(id: string, characters: string[]) {
  return apiSend<RunRecord>("PATCH", `/api/runs/${encodeURIComponent(id)}`, {
    characters,
  });
}

export function deleteRun(id: string, files: "keep" | "delete" = "keep") {
  return apiSend<{ id: string; files: string }>(
    "DELETE",
    `/api/runs/${encodeURIComponent(id)}?files=${files}`,
  );
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
 * The payload a DRAFT would send, rebuilt from the plan as it stands.
 *
 * Hard rule #2 asks a person to read the full payload, and a draft has no
 * `request.json` — that document records what was actually sent and is written
 * after dispatch. So the run whose payload most needs reading was the one whose
 * payload tab was empty, and an edit to the plan appeared to change nothing.
 *
 * Answered by the API rather than assembled here on purpose: `payload_of` is
 * the single allowlist of what reaches a provider, and a second copy in this
 * file is exactly how a field added to the plan later becomes part of a payload
 * somebody read as something else.
 */
export function getRunPayloadPreview(id: string) {
  return apiGet<{ request: Record<string, unknown>; prompt: unknown }>(
    `/api/runs/${encodeURIComponent(id)}/payload`,
  );
}

/**
 * Send a draft to the model. **This is the call that spends money, and calling
 * it is the decision.**
 *
 * **There is no approve step in front of it.** There was: `approveRun` sent a
 * digest of the payload on screen and the API refused a submit whose plan had
 * moved since. Decision 2026-09-04 removed it everywhere — a recorded yes was
 * never a stronger claim than the press that submits, and the payload is on the
 * page. Hard rule #2 is carried by who presses, not by a row.
 *
 * **The app could not do this at all until generation moved into the API.** The
 * spending lived in the CLI, holding the provider token, so a run planned on
 * this page then had to be sent from a terminal. It is one route now, and the
 * credential stays server-side where the SPA can never hold one. Refused with
 * 409 once the run has already gone out — the same route `runs submit` calls,
 * so the app and the CLI cannot come to disagree about what may be sent.
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
 * Rewrite a draft's authored half. The fingerprint moves with it.
 *
 * Refused outright once the run has been submitted: a plan edited afterwards
 * would sit beside `request.json` describing something that was never sent.
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

/** Replace the ordered images a draft binds. The fingerprint moves with it. */
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

// ---------------------------------------------------------------------------
// The model registry
//
// Read-only, and the same answer for every caller: which models exist is a
// property of the service rather than of a library. The API serves what shipped
// in `models.json`; `studio add-model` and `studio models refresh` write that
// file in a reviewed commit, and nothing here can change it.
// ---------------------------------------------------------------------------

/**
 * A model name as a path, encoded **per segment**.
 *
 * A registry key is a bare word but a Replicate id is `owner/name`, and the
 * routes take `<path:name>` precisely so both spellings resolve. Encoding the
 * whole string would turn that slash into `%2F` — which Werkzeug's path
 * converter does not match, so the request 404s on a model that exists.
 */
function modelPath(name: string): string {
  return name.split("/").map(encodeURIComponent).join("/");
}

/**
 * Every registry entry, keyed by registry name.
 *
 * **Unwrapped from `{models: {…}}`.** A map rather than an array because every
 * caller looks a model up by the key it was given, and each entry carries its
 * own `key`, so iterating loses nothing.
 */
export function getModels() {
  return apiGet<{ models: Record<string, ModelEntry> }>("/api/models").then(
    (body) => body.models ?? {},
  );
}

/** One entry, by registry key, alias, or the Replicate `owner/name`. */
export function getModel(name: string) {
  return apiGet<ModelEntry>(`/api/models/${modelPath(name)}`);
}

/**
 * The model's input schema, **fetched live from the provider on every call.**
 *
 * So: lazily, once, when an editor actually opens — never on a poll and never
 * per keystroke. It is a round trip to Replicate sitting inside a request
 * somebody is waiting on, and it is a different question from the entry's
 * `snapshot`, which `models refresh` recorded into the repo and may be months
 * old. This one is what the provider will accept today.
 *
 * A provider failure answers with empty maps rather than an error, so `props`
 * being empty means "could not ask", not "this model takes nothing".
 */
export function getModelSchema(name: string) {
  return apiGet<ModelSchema>(`/api/models/${modelPath(name)}/schema`);
}

export function getScene(id: string) {
  return apiGet<SceneRecord>(`/api/scenes/${encodeURIComponent(id)}`);
}

/**
 * Change a scene's own fields — its setting, its name, its status.
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

/**
 * Delete a scene and its shots. `files` keeps its folder by default.
 *
 * The route has been there since the entity model; the app had no wrapper for
 * it. Not wired to a page yet — the scene bar's Delete is placed separately.
 */
export function deleteScene(id: string, files: "keep" | "delete" = "keep") {
  return apiSend<{ id: string; files: string }>(
    "DELETE",
    `/api/scenes/${encodeURIComponent(id)}?files=${files}`,
  );
}

export function getMovie(id: string) {
  return apiGet<MovieRecord>(`/api/movies/${encodeURIComponent(id)}`);
}

/** Delete a movie. Same shape and same `files` default as `deleteScene`. */
export function deleteMovie(id: string, files: "keep" | "delete" = "keep") {
  return apiSend<{ id: string; files: string }>(
    "DELETE",
    `/api/movies/${encodeURIComponent(id)}?files=${files}`,
  );
}
