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
  /**
   * Which entity this node sits inside, or `null` for loose material under the
   * library root.
   *
   * **Derived from the node's ancestry on every read, never stored on the row.**
   * That is what makes it correct after a move: the blob key stamped at creation
   * still carries the old owner's prefix — it is a pointer and stays valid — but
   * the ownership a person is shown follows the tree. See
   * `GET /api/nodes/<id>/owner`, which is this same walk asked for on its own.
   */
  owner?: NodeOwner | null;
}

/**
 * The entity a node belongs to: what the app renders as "in <slug>".
 *
 * A `slug` and not a display name, because the slug is the address a person
 * types at the CLI and the two must read as the same thing. It is mutable — a
 * rename moves it — which is exactly why nothing here stores it: it is re-read
 * with the node every time.
 *
 * **The owner is the DEEPEST entity, which is often a run**, and a run has no
 * slug — so `slug` is null there and the id is all there is to show. This
 * declared only `character | project` while the API has always answered with
 * whichever entity is nearest; the union now says what is actually returned.
 */
export interface NodeOwner {
  kind: "character" | "project" | "run" | "scene" | "movie";
  id: string;
  slug: string | null;
}

export interface FileEntry {
  /** The node id. This is what the URL names and what a selection holds. */
  id: string;
  /**
   * The slash-joined *name* path — never the S3 key it is stored under, which
   * carries the owning entity's id and this node's (`characters/<char_id>/
   * <node_id>.png`) and is a string nothing outside the API may split.
   *
   * **Nothing addresses a write with it any more.** Every write route takes node
   * ids, so what survives here is the one job a path was always better at: it is
   * an *address a person types*, and it is what `CopyKeyButton` puts on the
   * clipboard for a `studio` command to resolve through `GET /api/resolve`.
   * Still called `key` because that is the word the listing route answers with.
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
  id: string;
  name: string;
  language: string;
  truncated: boolean;
  content: string;
}

/**
 * What a bulk move reports.
 *
 * One shape for folders and files alike, which is the whole of what
 * `POST /api/nodes/move` bought: a folder used to have its own endpoint because
 * its address was a prefix and a file's was a key, and the two counted different
 * things. An id is an id, so a mixed selection is one call.
 *
 * `skipped` is not an error — a node already sitting in the destination is
 * nothing to do, and refusing the whole request over one would make a
 * re-submitted move fail where the first one half-succeeded.
 */
export interface MovedNodes {
  destination: string;
  moved: number;
  skipped: number;
  ids: string[];
}

/**
 * What a bulk copy reports.
 *
 * Differs from a move in the one way that matters to the caller: a name the
 * destination already holds is *numbered* — `clip.mp4` lands as `clip (2).mp4` —
 * rather than refusing, because copying a file next to one of the same name is
 * ordinary rather than a mistake.
 */
export interface CopiedNodes {
  destination: string;
  copied: number;
  /** The new nodes, in the order the ids were sent. */
  ids: string[];
}

export interface DeletedNodes {
  /** Rows removed, which for a folder is its whole subtree rather than one. */
  deleted: number;
  ids: string[];
}

export interface SavedText {
  id: string;
  name: string;
  language: string;
  bytes: number;
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

// ---------------------------------------------------------------------------
// Entities
//
// A character, a project, a run, a scene and a movie are rows with ids now, not
// a folder name plus a document inside it. Two consequences shape every type
// below and neither is cosmetic:
//
// * **The id is the identity and the slug is a label.** Nothing here is keyed
//   on a slug, so a rename is one write and no link, binding or reference goes
//   stale. `slug` is present because it is what a person types at the CLI.
// * **Studio owns the envelope; the provider owns the payload.** A run's status,
//   model, bindings and outputs are fields because studio validates them. The
//   request and response bodies are *node ids* — the app fetches them as text
//   and shows them verbatim. See `RunRecord.payload`.
// ---------------------------------------------------------------------------

/**
 * A hero image as a listing hands it back: the node, and a URL already signed.
 *
 * Expanded on the *list* responses and left as a bare node id on the full
 * record, which is the asymmetry a caller has to know about. A list is drawing
 * forty cards and would otherwise need forty follow-up signings; a record is
 * being edited, and what an edit sets is the id.
 */
export interface HeroImage {
  node: string;
  url: string;
}

/** One row of `GET /api/characters`. */
export interface CharacterSummary {
  id: string;
  slug: string;
  display_name: string;
  hero: HeroImage | null;
  counts: { references: number; files: number };
  updated: string;
}

/**
 * The bible, as studio now owns it.
 *
 * **Deliberately not a closed schema in this app.** The sections the API
 * validates — `identity`, `face`, `body`, `wardrobe`, `voice`, `rendering`,
 * `consistency`, `text_identity_block` — are the pipeline's to change, and a
 * frontend that spelled every leaf out would have to be redeployed to show a
 * field somebody added. So the editor walks the value it is given and renders a
 * control per leaf type, and an unknown section appears the moment the API
 * returns one.
 *
 * `ProfileValue` is what a leaf can be; anything the walker does not recognise
 * is shown read-only rather than dropped, because dropping it would delete it on
 * the next save.
 */
export type ProfileValue =
  | string
  | number
  | boolean
  | null
  | ProfileValue[]
  | { [key: string]: ProfileValue };

export type CharacterProfile = Record<string, ProfileValue>;

/**
 * One character's whole record.
 *
 * `rev` is the reason an edit here is safe. Every write that changes the record
 * sends the `rev` it read, and the API refuses a stale one with a 409 — a
 * compare-and-swap rather than the read-then-write the old `profile.yaml` path
 * did, which had a window between the check and the write.
 *
 * `root` is the **one** pointer into the file tree. There is no map of
 * `reference/`, `corpus/`, `seed/` and `archive/`: those are children of `root`,
 * found by listing it, and a person may rename or delete any of them without
 * breaking anything. See ENTITY_MODEL.md, "the folder layout is convention, not
 * schema" — it is why this app builds the character's folder tabs from the
 * listing rather than from a constant.
 */
/**
 * The three fields promoted out of the bible onto the record.
 *
 * Grouped as a type because they are saved as a unit and by a different route
 * from the bible — `PATCH /api/characters/<id>` against
 * `PATCH /api/characters/<id>/profile`, which are told apart by the path and by
 * the body's key rather than by the verb. One form edits both; see `ProfileForm`.
 */
export interface CharacterIdentity {
  slug: string;
  display_name: string;
  fictional: boolean;
}

export interface CharacterRecord {
  id: string;
  lib: string;
  slug: string;
  display_name: string;
  fictional: boolean;
  rev: number;
  created: string;
  updated: string;
  root: string;
  /** A node id, not a signed URL — see `HeroImage`. */
  hero: string | null;
  default_set: string[];
  profile: CharacterProfile;
  schema_version?: number;
}

/**
 * One reference image's entry — the row that replaced filename magic.
 *
 * `order` is an attribute gapped by 1000, so inserting between two entries is
 * one write and touches neither neighbour. `group` is an attribute, so
 * regrouping copies no bytes. Both used to be encoded in the filename
 * (`<slug>_<group>_<n>.png`), which is why the file this names can now be called
 * anything and renamed freely: the row names its **node id**.
 */
export interface ReferenceEntry {
  node: string;
  /** Absent inside a grouped listing, where the key already says it. */
  group?: string;
  order: number;
  description: string;
  tags: string[];
  /** True when the node is in the character's `default_set`. */
  default?: boolean;
  file: {
    name: string;
    size?: number;
    content_type?: string | null;
    /** Presigned inline GET, short-lived like every other URL in this app. */
    url: string;
  };
}

/** `GET /api/characters/<id>/references`, grouped and in `order` within a group. */
export interface ReferenceIndex {
  groups: Record<string, ReferenceEntry[]>;
  counts: Record<string, number>;
}

/**
 * What a model would actually be shown, resolved by the API rather than by each
 * caller.
 *
 * It is a route and not a function in each half of studio for one reason: the
 * CLI and the app must not be able to disagree about what slot 3 was. Over-cap
 * is a 409 carrying the index rather than a silent truncation, so the refusal
 * arrives before the money is spent.
 */
export interface SelectionResponse {
  selection: Array<{
    slot: number;
    node: string;
    group: string;
    description: string;
    url: string;
  }>;
  cap: number;
  source: string;
}

/**
 * How many reference images each engine will accept.
 *
 * Held here rather than fetched because it is the *refusal* that has to be
 * authoritative and that lives in the API — this is only what lets the
 * References grid say "18 of 14" before a shoot is attempted. If an engine's cap
 * moves, the worst this does is warn slightly early or slightly late; it can
 * never let an over-cap set through, because it is not the check.
 */
export const ENGINE_CAPS: ReadonlyArray<{ engine: string; cap: number }> = [
  { engine: "Kling", cap: 7 },
  { engine: "Seedance", cap: 9 },
  { engine: "Nano Banana", cap: 14 },
];

/** One row of `GET /api/projects`. */
export interface ProjectSummary {
  id: string;
  slug: string;
  title: string;
  hero: HeroImage | null;
  counts: ProjectCounts;
  updated: string;
}

/** Maintained on the record as runs land — never a scan over the runs folder. */
export interface ProjectCounts {
  runs: number;
  scenes: number;
  movies: number;
}

/**
 * One project's record.
 *
 * `characters` is expanded from the `PROJ#…/CHAR#…` involvement rows rather than
 * being a list on the record, which is what makes the reverse question — "which
 * projects involve this character" — answerable at all.
 */
export interface ProjectRecord {
  id: string;
  lib: string;
  slug: string;
  title: string;
  description: string;
  rev: number;
  created: string;
  updated: string;
  root: string;
  hero: string | null;
  counts: ProjectCounts;
  characters: Array<{ id: string; slug: string; display_name: string }>;
}

/**
 * One file in a project's input pool.
 *
 * **Position in this list is what `--input N` means**, which is why the app
 * numbers the rows: the pool is sorted name-ascending by the API and the number
 * a person passes on the command line is an index into that order, not anything
 * stored. Renaming a file therefore renumbers the pool, and showing the numbers
 * is how that stops being a surprise.
 */
export interface ProjectInput {
  node: string;
  name: string;
  size?: number;
  content_type?: string | null;
  url: string;
}

export type RunStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled";

export type RunKind = "image" | "video";

/** What a model charged, when the provider reported it. Never computed here. */
export interface RunCost {
  currency: string;
  amount: number;
}

/**
 * One row of the runs list — the projection the listing row carries.
 *
 * A projection rather than the envelope because a run is immutable once it
 * completes, so there is nothing to keep in step, and drawing a grid from
 * envelopes would be a batch read over hundreds of payloads.
 *
 * **Every field here must be one the API actually writes into the listing row.**
 * This declared `slug` and the row never carried one — the CLI's equivalent
 * formatter crashed on it and this table rendered an empty column. A run has no
 * slug at all now: it is a machine event, addressed by its id or by `latest`.
 */
export interface RunSummary {
  id: string;
  project: string;
  status: RunStatus;
  kind: RunKind;
  model: string;
  created: string;
  cost: RunCost | null;
  thumb: HeroImage | null;
  /** Present when the run was chained off another's output. */
  lineage?: RunLineage;
  characters?: string[];
}

export interface RunLineage {
  from_run: string | null;
  from_output: string | null;
}

/**
 * A node a run points at, expanded with a signed URL so the page can draw it.
 *
 * Used for outputs and for bindings alike, which is the point: a binding names a
 * **node**, never a URL and never a path. A URL-shaped binding is refused by the
 * API — that is hard rule #3, enforced for both halves of studio rather than
 * only for the CLI.
 */
export interface RunAsset {
  node: string;
  name: string;
  size?: number;
  content_type?: string | null;
  url: string;
}

/**
 * One run's envelope.
 *
 * **`payload` names three nodes and studio decodes none of them.** The rule that
 * `request.json` is never parsed has not gone away; it has moved to where it is
 * actually true. The provider owns the exact body sent and the exact body
 * returned, the pipeline changes their shape freely, and this app shows them as
 * text. Everything above `payload` is studio's own and is validated.
 */
export interface RunRecord {
  id: string;
  lib: string;
  project: string;
  status: RunStatus;
  kind: RunKind;
  engine: string;
  model: string;
  prediction_id: string | null;
  created: string;
  submitted: string | null;
  completed: string | null;
  /** Role → the nodes bound to it, e.g. `image_input`. */
  bindings: Record<string, RunAsset[]>;
  characters: string[];
  folder: string;
  outputs: RunAsset[];
  lineage: RunLineage;
  cost: RunCost | null;
  error: string | null;
  payload: { request: string | null; response: string | null; prompt: string | null };
}

/** A page of runs. `cursor` is `null` when there is nothing after this page. */
export interface RunPage {
  runs: RunSummary[];
  cursor: string | null;
}

/**
 * One planned shot inside a scene.
 *
 * `run` is how a shot knows what rendered it, and it is a run id rather than a
 * path — which is what lets a plan be revised without stranding the work already
 * done against it.
 */
export interface Shot {
  id: string;
  order: number;
  prompt: string;
  run: string | null;
  panel: string | null;
}

export interface SceneSummary {
  id: string;
  project: string;
  slug: string;
  title: string;
  status: string;
  created: string;
  thumb?: HeroImage | null;
}

export interface SceneRecord extends SceneSummary {
  folder: string;
  shots: Shot[];
  /** The stitched take, once `assemble` has uploaded it. */
  output: RunAsset | null;
}

export interface MovieSummary {
  id: string;
  project: string;
  slug: string;
  title: string;
  status: string;
  created: string;
  thumb?: HeroImage | null;
}

export interface MovieRecord extends MovieSummary {
  folder: string;
  scenes: SceneSummary[];
  output: RunAsset | null;
}
