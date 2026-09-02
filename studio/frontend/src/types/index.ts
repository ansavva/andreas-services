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

/**
 * A node as `GET /api/resolve` and `GET /api/nodes/<id>` report it.
 *
 * Deliberately NOT a `FileEntry`. That is what a listing hands out — it carries
 * a presigned `url` because the route that builds it expands a POINTER to a
 * node into what a page can draw. A node addressed by its own id reports its
 * own fields and nothing signed, so anything wanting to display one asks
 * `MediaThumb` to sign from the id.
 */
export interface NodeView {
  id: string;
  name: string;
  kind: "file" | "folder";
  size?: number;
  content_type?: string | null;
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
  kind: "folder";
  prefix: string;
  name: string;
  last_modified: string | null;
  parent_id?: string;
  /** The entity whose root this is, when it is one. Draws a card, not an icon. */
  entity?: string;
  owner?: NodeOwner | null;
}

export interface Crumb {
  /** The node the crumb names — a crumb is a navigation target, so it has one. */
  id: string;
  name: string;
  prefix: string;
}

/**
 * One folder's contents, split — what `getFolder` makes of a listing.
 *
 * Not a wire shape. `GET /api/nodes` answers with one array; splitting it is the
 * client's job, and this is the result of doing it.
 */
export interface FolderListing {
  prefix: string;
  sort: SortOrder;
  /** `all` when a tag filter is on — a tag search is a search of the branch. */
  depth: Depth;
  breadcrumbs: Crumb[];
  folders: FolderEntry[];
  files: FileEntry[];
  tags: Record<string, number>;
}

/** One page of media beneath a folder — what `getMedia` makes of a listing. */
export interface MediaListing {
  prefix: string;
  sort: SortOrder;
  tags: Record<string, number>;
  items: FileEntry[];
  total: number;
  truncated: boolean;
  next_cursor: string | null;
}

/** `PROPFIND`'s `Depth`, minus the `0` — one node is `GET /api/nodes/<id>`. */
export type Depth = "1" | "all";

/** What `?kind=` filters on, and what an entry reports. */
export type EntryKind = "folder" | MediaKind;

/**
 * `GET /api/nodes` — the one listing route.
 *
 * **One array, discriminated by `kind`**, where `/api/tree` handed back folders
 * and files in separate fields. A caller wanting them apart splits in a line
 * (`getFolder` does); a caller wanting them in one order — anything recursive —
 * could not have put them back together.
 */
export interface NodeListing {
  prefix: string;
  sort: SortOrder;
  depth: Depth;
  breadcrumbs: Crumb[];
  entries: (FileEntry | FolderEntry)[];
  /** Keyed by kind, over everything the filters admitted — not over the page. */
  counts: Partial<Record<EntryKind, number>>;
  /**
   * The tags present in this result and how many entries carry each, commonest
   * first. A facet over what was listed — **not a vocabulary of the library**,
   * which nothing stores. Computed after the filters, so narrowing by one tag
   * leaves exactly the tags worth narrowing by next.
   */
  tags: Record<string, number>;
  total: number;
  /** True when the enumeration hit its cap — there is more than this shows. */
  truncated: boolean;
  /** An offset into the sorted result, not a DynamoDB continuation token. */
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
  /**
   * The new nodes, in the order the ids were sent.
   *
   * **This said `ids: string[]` and the route has never sent one.** It answers
   * `{destination, copied, nodes}` — whole records, because the numbering is
   * decided at the destination and a caller cannot re-derive the name it got.
   * Nothing read the field until promote-to-reference needed the copy's id, so
   * a type that was an assertion nobody had checked went three routes' worth of
   * time without a symptom. Read the id off `nodes`, and never assume the name
   * you sent.
   */
  nodes: NodeRecord[];
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
  /**
   * `default` is how many of its images a generation is shown — what
   * `counts.references` was, counted off the tag rather than off a row class
   * that no longer exists. Both come out of one branch walk.
   */
  counts: { default: number; files: number };
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
}

export interface CharacterRecord {
  id: string;
  lib: string;
  slug: string;
  display_name: string;
  rev: number;
  created: string;
  updated: string;
  root: string;
  /** A node id, not a signed URL — see `HeroImage`. */
  hero: string | null;
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
/**
 * One shared block of the reference spec — prose an angle template cites by name.
 *
 * A row rather than a key in one document, so a bad edit breaks one block and
 * two people editing different blocks do not overwrite each other. That is the
 * shape the phrasebook was moved to for the same reasons.
 */
export interface SpecBlock {
  name: string;
  text: string;
  updated?: string;
}

/**
 * A prompt somebody wrote, picked for a run.
 *
 * **This was a reference ANGLE.** It held one orientation of one character's
 * standard set, carried a `group` that had to be `face` or `body`, and only a
 * turnaround could use one. `group` chose which prose `build` and `must`
 * produced, and a template names that itself now —
 * `{character.1.build.face}` — so the column was a second place to say
 * something the prompt already says. `order` was the shooting order, and
 * nothing shoots a set.
 */
export interface PromptTemplate {
  id: string;
  /** What a person picks it by. */
  name?: string;
  prompt: string;
  /** What a promotion starts from when this image becomes identity. Never sent. */
  description: string;
  tags: string[];
  /**
   * A picture of what this template MAKES, shown to a person and never sent.
   *
   * **All that is left of the pose plates.** A template could bind one as a
   * first image, and it distorted the very thing it existed to record — the
   * face angles stopped sending theirs, and the body angles followed once
   * eleven hand-authored production renders were compared and not one had
   * bound a plate. The picture is still the clearest statement of what a
   * template produces, so it survives on a field that cannot reach a payload.
   */
  illustration?: string | null;
}

export type TemplateBody = Omit<PromptTemplate, "id">;

/** `GET /api/templates` — blocks keyed by name, templates by name. */
export interface TemplateLibrary {
  blocks: Record<string, string>;
  templates: PromptTemplate[];
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
/**
 * One image of a resolved selection, in the position the model will see it in.
 *
 * **Everything but `slot` and `node` is nullable, and this used to declare none
 * of it.** `name` was missing entirely — the route sends it because a person
 * reviewing a payload has to know which picture is `[Image3]` — and `url` is
 * null for a reference whose node carries no blob.
 */
export interface SelectionEntry {
  /** 1-based position in the resolved list. What `[Image3]` counts. */
  slot: number;
  node: string;
  name: string | null;
  group: string | null;
  description: string | null;
  url: string | null;
}

export interface SelectionResponse {
  selection: SelectionEntry[];
  /** The ceiling this was measured against — `null` when the caller named none. */
  cap: number | null;
  /** Which of `tag`, `pick`, `group`, `default` or `all` chose these. */
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
/**
 * What a run cost, as far as the provider will say — **which is not a price.**
 *
 * Replicate's prediction body carries no money in it: billing is per second of
 * the model's hardware and the rate lives on the account, not on the response.
 * So `amount` is null on everything the callback closes, and `predict_time` is
 * the real number — what a price would be derived from.
 *
 * **Both halves are nullable and that is load-bearing.** They were `number` and
 * `string`, which was true only of runs that predate the callback: a `cost`
 * object with a null `amount` crashed the run page on `amount.toFixed(3)`, live,
 * on the first real generation. `formatCost` is the one place this is rendered
 * for exactly that reason.
 */
export interface RunCost {
  currency: string | null;
  amount: number | null;
  /** Seconds of model time. What the provider actually reports. */
  predict_time?: number | null;
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
  characters?: string[];
  /** Projected onto the row so `?fingerprint=` is one query — see `RunRecord`. */
  fingerprint?: string;
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
  /**
   * Who the run is ABOUT, which `characters` alone does not answer.
   *
   * `characters` is written at creation and nowhere else, so a run built by
   * adding a character's references in the editor binds that character's
   * photographs and records nobody. This is derived from the bindings when the
   * record is silent, and it is what `{character.N}` counts.
   */
  cast?: string[];
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
   * positions in it ("the first image is an existing reference"), so this is the
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
  /**
   * What makes two submissions the same one — `plan_digest` plus the model.
   *
   * Answers "has this exact payload already gone out here" through
   * `GET /api/runs?fingerprint=`, which is why it is on the listing row too.
   * Absent on runs written before it existed.
   */
  fingerprint?: string | null;
  /**
   * What the output file is called. **A filename, not an identity.**
   *
   * Outside `plan` on purpose: `plan_digest` hashes the plan, so a rename would
   * otherwise void an approval over something the provider is never sent.
   */
  output_name?: string | null;
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
  /** Which scenes bound this run into a shot. */
  scenes: Backlink[];
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
  /**
   * What was TYPED, when the prompt was written as a template.
   *
   * Kept beside the expanded `prompt` rather than instead of it. The expansion
   * happens at save so `plan_digest` covers exactly what reaches the model — a
   * template expanded at submit would mean the payload somebody approved is not
   * the payload sent — and the template is kept so the prompt stays editable
   * instead of becoming a wall of finished prose with no way back.
   */
  template?: string;
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
   * than a person is deliberate: nobody approved a run made last August in a
   * browser, and a row implying they had would be undetectable later.
   */
  by: string;
  at: string;
  digest: string;
  /**
   * How the yes arrived. `interactive` is a person at the control — the app's
   * approve button, or a terminal confirm. `relayed` is somebody saying yes
   * where studio cannot see it, passed on by an agent with `--relayed`.
   *
   * It is a WEAKER claim and the app says so rather than drawing both the same.
   * Absent on rows recorded before the field existed, which is why it is
   * optional and why a missing value is not read as `interactive`.
   */
  via?: "interactive" | "relayed";
}

/** A page of runs. `cursor` is `null` when there is nothing after this page. */
export interface RunPage {
  runs: RunSummary[];
  cursor: string | null;
}

/**
 * What `POST /api/runs` takes. Three fields are required and the rest are not.
 *
 * **No provider `input` here, deliberately.** The route accepts one and writes
 * it to `request.json`; submit rebuilds the body it actually sends from
 * `plan.prompt + plan.params + sends` (`generate.payload_of`), which is the one
 * allowlist of what reaches a provider. An `input` authored in the browser would
 * be a second answer to that, recorded as if it were the first.
 *
 * `sends` and `bindings` are the same argument twice: send `sends` when the
 * roles are known, `bindings` when only the fields are. Sending both is not an
 * error — the API reads `sends` and ignores the map.
 */
export interface CreateRunBody {
  project: string;
  kind: RunKind;
  model: string;
  engine?: string;
  /** The output filename. Lands on the record as `output_name`. */
  name?: string;
  characters?: string[];
  sends?: RunSendInput[];
  /** The older spelling: `{field: [nodeId, …]}`, read as sends with a null role. */
  bindings?: Record<string, string[]>;
  plan?: RunPlan | null;
}

/**
 * A send as a caller AUTHORS it — the three fields the digest hashes.
 *
 * `order` is the position in the list and `source` is derived by the API from
 * where the node sits, so neither is sent. See `RunSend` for what comes back.
 */
export interface RunSendInput {
  field: string;
  role: RunSend["role"];
  node: string;
}

/**
 * The 201 body of `POST /api/runs`. **Not a `RunRecord`** — it carries the
 * handful of fields whose values the caller could not have known, and nothing
 * else: no status history, no outputs, no expanded assets.
 *
 * `plan_digest` is here so the next call can be `approveRun(id, plan_digest)`
 * without a read in between, and `fingerprint` so a duplicate check is one query.
 */
export interface CreatedRun {
  id: string;
  project: string;
  status: RunStatus;
  folder: string;
  payload: { request: string | null; response: string | null; prompt: string | null };
  plan_digest: string;
  fingerprint: string;
  /** The rows as written, renumbered from 1. `source` is null on every one. */
  sends: Array<RunSendInput & { order: number; source: RunSendSource | null }>;
  created: string;
}

// ---------------------------------------------------------------------------
// The model registry, as the API serves it
//
// `models.json` ships inside the API image and `GET /api/models` hands it back,
// so there is one copy at runtime as well as one in the repo. Nothing below is
// per-library: two accounts get byte-identical answers.
// ---------------------------------------------------------------------------

/**
 * One prop of a recorded schema snapshot — an enum, a default, a range.
 *
 * Deliberately partial: which keys a prop has depends on the provider's own
 * schema, and `models refresh` records what it found.
 */
export interface SnapshotProp {
  enum?: unknown[];
  default?: unknown;
  minimum?: number;
  maximum?: number;
}

/**
 * The snapshot map: one entry per input, plus `refreshed`.
 *
 * **`refreshed` is a date string sitting among the props**, which is why the
 * index signature is a union and why anything walking this has to skip that key
 * rather than trust every value to be an object.
 */
export interface ModelSnapshot {
  [prop: string]: SnapshotProp | string | undefined;
  refreshed?: string;
}

/**
 * One registry entry, as `GET /api/models` and `/api/models/<name>` return it.
 *
 * `key` is the registry name and is attached by the API to every entry,
 * including the ones inside the map, so a caller that iterates does not lose it.
 * `model` is the Replicate `owner/name` — which is what `POST /api/runs` wants,
 * and `key` is not.
 */
export interface ModelEntry {
  key: string;
  model: string;
  kind: RunKind;
  /** The `studio-media-*` skill that documents this model. */
  skill: string;
  /**
   * Which inputs take images, by field name. `null` where a model has no such
   * field — a still model has no start frame — so a null is "not offered"
   * rather than "unknown".
   */
  images?: {
    refs?: string | null;
    start?: string | null;
    end?: string | null;
    /** `null` means no cap, which is not the same as absent. */
    max_refs?: number | null;
    accepts_ext?: string[];
    start_counts_toward_max_refs?: boolean;
    start_excludes_refs?: boolean;
    end_excludes_refs?: boolean;
  };
  prompt?: { max_chars?: number | null; recommended_words?: number | null };
  note?: string;
  /** Params the pipeline always sends unless something overrides them. */
  defaults?: Record<string, unknown>;
  /** Values the schema still advertises that this model will not honour. */
  denied?: Record<string, Record<string, string>>;
  /** Video-only wiring: where the negative prompt and technical block go. */
  video?: Record<string, unknown>;
  snapshot?: ModelSnapshot;
  aliases?: string[];
}

/**
 * One property of a LIVE provider schema. **Deliberately loose.**
 *
 * `GET /api/models/<name>/schema` proxies Replicate and distils nothing, so this
 * is the provider's own OpenAPI fragment: `type`, `enum`, `default`, `minimum`,
 * `x-order`, an `allOf` naming a `$ref` into `schemas`. Declaring those leaves
 * would be a copy of a schema studio does not own — the condensed form lives in
 * `ModelEntry.snapshot`, which studio does own.
 */
export type SchemaProp = Record<string, unknown>;

export interface ModelSchema {
  /** The Replicate `owner/name` this resolved to, which may not be what was asked. */
  model: string;
  props: Record<string, SchemaProp>;
  /** The sibling components an enum may hide behind a `$ref`. */
  schemas?: Record<string, SchemaProp>;
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
   * character's references, by default set or by name, plus any explicit nodes.
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
  /** The references this panel renders FROM, resolved to images by the API. */
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
   * A stored plan NAMES its references ("this character, these files"); a board has
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
  /**
   * The runs this shot was rendered by BEFORE the current one, newest first.
   *
   * A shot holds one `run`, so a retry — a reworded beat, a take that came out
   * wrong — used to erase the only pointer to what it replaced. The run itself
   * survived in the project and was reachable by nobody. Written by the API on
   * every shot write, never by a client.
   */
  takes?: Take[];
  /**
   * Every run behind this shot, as the same summary a runs listing carries.
   *
   * A board is made of run output — the clip, each boarded panel, the handoff
   * frame, every superseded take — and could only say so in ids. Expanded by
   * the API in one batched read for the whole scene, with the `role` each run
   * plays in this shot, which is the one thing only the scene knows.
   */
  runs?: ShotRun[];
}

/** A run row on a shot: the listing fields, plus what it is TO this shot. */
export interface ShotRun {
  id: string;
  project?: string;
  status?: RunStatus;
  kind?: RunKind;
  model?: string;
  created?: string;
  /** `clip`, `handoff`, `sample`, `start`, `reference`, `earlier take`. */
  role?: string;
}

/** A run that used to be a shot's, kept so it can still be opened and watched. */
export interface Take {
  run: string | null;
  runref?: string | null;
  node?: string | null;
  rendered?: string | null;
  /** Expanded by the API from `node`, so the board can draw it. */
  clip?: RunAsset;
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
  /**
   * Earlier cuts of this scene, newest first.
   *
   * Each assemble writes its own node now, so re-cutting after re-rendering a
   * shot leaves both takes side by side. It used to overwrite one node and rely
   * on S3 object versioning, which is recoverable but not *visible* — a version
   * has no node, so nothing lists it, draws it or links to it.
   */
  cuts?: RunAsset[];
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
