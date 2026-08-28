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
  /** What the file shows, and how it is selected. See `FileEntry` below. */
  description?: string;
  tags?: string[];
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
  /**
   * What the file SHOWS, and how it is selected — both on the node.
   *
   * Absent, not empty, when nothing has been written: the API drops null
   * attributes, and "there is no description" is one state rather than two.
   * These used to live on the `REF#` row that made a file one character's
   * reference, so the same picture had words inside a reference grid and none
   * anywhere else. `group` and `order` stayed on that row, because they are
   * facts about the set rather than about the picture.
   */
  description?: string;
  tags?: string[];
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
/**
 * One file in the pool.
 *
 * **`id`, not `node`.** `support.assets` draws the line: a pointer a record
 * holds says `node`, and a node reported by its own id says `id`. The pool is
 * a listing of the `input/` folder's children, so it is the second — and this
 * said `node`, which is `undefined` against the route and left every thumbnail
 * in the tab blank. The same divergence cost every tile on the run page once,
 * in the other direction.
 */
export interface ProjectInput {
  id: string;
  name: string;
  size?: number;
  content_type?: string | null;
  url: string;
}

export type RunStatus =
  // Before anything is submitted. A run is created when it is PLANNED now, so
  // the row no longer says that anything happened — see `RunRecord.plan`.
  | "draft"
  | "approved"
  | "discarded"
  // After. `adopted` is a synthetic run wrapping an artifact that already
  // existed; nothing was submitted and nothing billed.
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "adopted";

/** The states that come before a submission, mirrored from `catalog.py`. */
export const UNSUBMITTED_RUN_STATUSES: readonly RunStatus[] = [
  "draft",
  "approved",
  "discarded",
];

export const isUnsubmitted = (status: RunStatus): boolean =>
  UNSUBMITTED_RUN_STATUSES.includes(status);

/**
 * The three a run does not come back from — mirrored from `catalog.py`'s
 * `TERMINAL_RUN_STATUSES`, which owns the word.
 *
 * The app polls a run while it can still change and stops when it cannot. The
 * set is duplicated here rather than fetched because it is part of the API's
 * shape, like the union above it: a status the backend added and this did not
 * know about would be *non*-terminal here, which errs toward asking again
 * rather than toward showing a stale answer for ever.
 */
export const TERMINAL_RUN_STATUSES: readonly RunStatus[] = [
  "succeeded",
  "failed",
  "cancelled",
  // A discarded draft is gone. A draft is NOT here — it can still be approved
  // and submitted, so the run page has to keep watching one.
  "discarded",
  "adopted",
];

export const isTerminal = (status: RunStatus): boolean =>
  TERMINAL_RUN_STATUSES.includes(status);

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
  /**
   * Role → the nodes bound to it, e.g. `image_input`.
   *
   * **Derived from `sends` by the API**, and answered from the old stored
   * attribute for runs that predate them. Kept because it is the shape that
   * groups by model input, which is what the payload actually looks like;
   * `sends` is the shape that says why each image is there.
   */
  bindings: Record<string, RunAsset[]>;
  /**
   * Every image this run sends, IN ORDER, each with its role and provenance.
   *
   * The order is not presentational: a model is handed a list and prompts cite
   * positions in it ("the first image is an existing plate"), so this is the
   * order the model sees.
   */
  sends: RunSend[];
  /**
   * The AUTHORED half — what a person decided, as studio's own data.
   *
   * `null` on a run that predates the plan and could not be reconstructed.
   * `plan.origin` says whether a person wrote it or `catalog backfill-plans`
   * rebuilt it from the recorded request.
   */
  plan: RunPlan | null;
  /** A hash over the plan AND the ordered sends — what an approval names. */
  plan_digest: string | null;
  /** Who said yes, when, and to which payload. `null` until somebody has. */
  approval: RunApproval | null;
  /**
   * Whether the payload moved after it was approved.
   *
   * Computed by the API on every read rather than stored — a gate that trusted
   * a cached answer would pass the exact case it exists to catch.
   */
  stale: boolean;
  characters: string[];
  folder: string;
  outputs: RunAsset[];
  lineage: RunLineage;
  /** Which scenes bound this run into a shot. */
  scenes: Backlink[];
  /** What was chained off it — `lineage.from_run` read the other way. */
  derived: Backlink[];
  cost: RunCost | null;
  error: string | null;
  payload: { request: string | null; response: string | null; prompt: string | null };
}

/**
 * What one image a run sends is FOR, and where it came from.
 *
 * `role` is read off the model registry — which field of the model's input this
 * binds to decides it — and `source` is derived by the API from where the node
 * sits, so a run submitted today and a run reconstructed from history describe
 * their images in the same words.
 */
export interface RunSend extends RunAsset {
  order: number;
  /** The model input this binds to, e.g. `image_input`, `start_image`. */
  field: string;
  /** `null` on a run backfilled from a model no longer in the registry. */
  role: "start" | "end" | "reference" | "input" | null;
  source: RunSendSource;
}

export interface RunSendSource {
  kind: "character" | "run" | "input-pool" | "project" | "object";
  character?: string;
  /** The reference group a character's image was filed under, e.g. `face`. */
  group?: string;
  order?: number;
  run?: string;
  /** 1-based, matching what a runref's `#2` means. */
  output?: number;
  project?: string;
  /** 1-based position in the project's input pool — what `--input N` means. */
  position?: number;
}

export interface RunPlan {
  version: number;
  /** `authored` if a person wrote it; `backfilled` if it was reconstructed. */
  origin: "authored" | "backfilled";
  /** A structured prompt document, or plain prose. Never decoded by studio. */
  prompt: unknown;
  /** Everything else the model was given — aspect ratio, quality, duration. */
  params: Record<string, unknown>;
  note?: string | null;
}

export interface RunApproval {
  /**
   * The Cognito sub of whoever approved it — or the literal `backfill`, for a
   * run approved before approvals were recorded. Naming the mechanism rather
   * than a person is deliberate: nobody consented in a browser to a run made
   * last August, and a row implying they had would be undetectable later.
   */
  by: string;
  at: string;
  digest: string;
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
/**
 * What a panel is FOR, which is the same question as whether it binds.
 *
 * `start` and `end` are frames the model is given, `reference` steers the look
 * without fixing a frame, and a **`sample` binds to nothing** — it is a still
 * that shows a person what the shot should look like, so a fifteen-second render
 * can be judged before it is bought rather than after.
 *
 * It is `null` when the author left it to position. Resolving that is the
 * pipeline's job (`storyboard.panel_roles`) and deliberately not this page's:
 * a shot that opens on a handoff frame has its start panel demoted to a
 * reference, and a UI that recomputed the rule would be a second copy of it.
 */
export type PanelRole = "start" | "end" | "reference" | "sample";

/** One panel of a shot: a prompt, and the image it rendered into once boarded. */
export interface Panel {
  n: number;
  role: PanelRole | null;
  prompt: string;
  model?: string | null;
  aspect_ratio?: string | null;
  /**
   * Where this panel's own reference images come from when it renders — a
   * character's plates, by default set or by name, plus any explicit nodes.
   *
   * **Not the same list as the shot's.** These steer the STILL; what the video
   * engine is sent is the shot's own `motion.references` plus the scene's frames.
   * Conflating the two is the mistake this field being invisible encouraged.
   */
  references?: { characters?: string[]; pick?: string; pick_tag?: string; keys?: string[] };
  /** The run that rendered it, and the node that run produced. */
  run?: string | null;
  node?: string | null;
  boarded?: string | null;
  /** The prompt changed after the image was rendered — the picture is behind the words. */
  stale?: boolean;
  /** Expanded by the API from `node`, so a board can be drawn without a second call. */
  image?: RunAsset;
  /** The plates this panel renders FROM, resolved to images by the API. */
  reference_assets?: RunAsset[];
}

/**
 * The motion prompt as the thing it actually is — a document studio authored.
 *
 * `motion.prompt` is this object serialized, and it is what the model receives:
 * every engine's prompt field is a plain string, so "JSON prompting" means
 * writing a structured object INTO that string. Reading it back apart to show a
 * person is therefore not parsing somebody else's payload — the run page's rule
 * about `request.json` is about the PROVIDER's document, whose shape studio does
 * not own. This one has a schema `studio prompt` validates against.
 *
 * Every field is optional because the schema is additive and a prose prompt is
 * legal too; anything unrecognised is preserved on the way back out.
 */
export interface MotionPrompt {
  subject?: string;
  action?: string;
  scene?: string;
  lighting?: string;
  style?: string;
  audio?: string;
  /** Folded in as `avoid` by the compiler — no engine here has a negative param. */
  avoid?: string;
  camera?: {
    shot?: string;
    movement?: string;
    lens_mm?: number;
    speed?: string;
  };
  [key: string]: unknown;
}

/** The clip half of a shot: what moves, for how long, on which engine. */
export interface Motion {
  prompt: string;
  /** The same document unserialized, when the plan carried one. */
  prompt_json?: MotionPrompt | null;
  duration?: number | null;
  model?: string | null;
  aspect_ratio?: string | null;
  extra?: Record<string, unknown> | null;
  references?: { characters?: string[]; pick?: string; pick_tag?: string; keys?: string[] } | null;
  /**
   * The reference block resolved into drawable images, by the API.
   *
   * A stored plan NAMES its plates ("this character, these files"); a board has
   * to draw them. Expanded server-side because resolving which pictures a pick
   * means is the character module's job, not a second copy in the browser.
   */
  reference_assets?: RunAsset[];
}

/**
 * One planned shot.
 *
 * `run` is how a shot knows what rendered it, and it is a run id rather than a
 * path — which is what lets a plan be revised without stranding the work already
 * done against it.
 *
 * `prompt` and `panel` are the pre-storyboard shape and still arrive on scenes
 * assembled from bare runs, which is why they are kept alongside `beat`,
 * `panels` and `motion` rather than replaced by them.
 */
export interface Shot {
  id: string;
  order: number;
  prompt: string;
  run: string | null;
  panel: string | number | null;

  /** One line, for the board caption. */
  beat?: string;
  status?: string;
  /** Whether this shot picks up the movement of the one before it. */
  continues?: boolean;
  panels?: Panel[];
  motion?: Motion | null;
  /**
   * The previous shot's literal last frame — the only image that makes the join
   * invisible, which is why it outranks a panel composed for the same moment.
   */
  opens_on?: { node?: string | null; from_run?: string | null; frame?: RunAsset } | null;

  runref?: string | null;
  /** The rendered clip, and its expansion. */
  node?: string | null;
  clip?: RunAsset;
  duration?: number | null;
  rendered?: string | null;
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

/**
 * A link back UP the tree — which scene used this run, which movie cut this
 * scene. Thin on purpose: id, slug and title are what a link needs to be drawn.
 *
 * These are answered off `by-sk` edge rows, and until those existed the
 * questions had no answer at any price: a run lived in a shot's attribute and a
 * movie's scenes in a JSON list, and no index can see into either.
 */
export interface Backlink {
  id: string;
  slug: string | null;
  title: string | null;
}

export interface SceneRecord extends SceneSummary {
  folder: string;
  shots: Shot[];
  /** The stitched take, once `assemble` has uploaded it. */
  output: RunAsset | null;
  /** Which movies cut this scene. */
  movies: Backlink[];

  /** Prepended byte-identically to every panel prompt — one look, stated once. */
  setting?: string;
  logline?: string;
  /** Model, panel model, duration and technical block every shot inherits. */
  defaults?: Record<string, unknown> | null;
  characters?: string[];
  version?: number;
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
