/**
 * `/api/**` answered from fixtures captured off the REAL API.
 *
 * **The fixtures are not hand-written, and that is the point.** They were taken
 * from `http://localhost:8000` against the published dev-seed fixture — the
 * same 54-object character every developer's stack loads — with
 * `e2e/fixtures/README.md` recording how to retake them. A hand-written stub
 * drifts from the API silently and then asserts its own imagination; one
 * captured from the thing it is standing in for cannot drift without somebody
 * re-capturing it.
 *
 * Nothing here is about money. The web app has no HTTP client for any model
 * provider — its production dependencies are boto3, Flask, Werkzeug, mangum,
 * asgiref and PyJWT — so an e2e run could not bill whatever it did. Stubbing
 * buys determinism and a run that needs no AWS, no credentials and no stack.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { Page, Route } from "@playwright/test";

// Read off disk rather than `import ... from "*.json"`: under Node ESM that
// needs an import attribute, and these are captured artefacts rather than
// modules. `fixture()` is also what the live mode does NOT use, which keeps the
// difference between the two modes in one place.
const HERE = dirname(fileURLToPath(import.meta.url));

export function fixture<T>(name: string): T {
  return JSON.parse(
    readFileSync(join(HERE, "..", "fixtures", `${name}.json`), "utf8"),
  ) as T;
}

/** A row in a node listing, and what `GET /api/nodes/<id>` answers with. */
interface Node {
  id: string;
  lib: string;
  parent_id?: string;
  name: string;
  kind: string;
  size?: number;
  content_type?: string;
  created_at: string;
  updated_at?: string;
  owner?: { kind: string; id: string; slug: string | null } | null;
}

/** A pane in the recursive walk — a different shape from a node row. */
interface Item {
  id: string;
  key: string;
  name: string;
  size: number;
  last_modified: string;
  kind: string;
  content_type: string;
  url: string;
}

/**
 * A listing, as `GET /api/nodes` answers it — at any depth, filtered or not.
 *
 * **One shape where there were three.** `/api/tree` split folders from files,
 * `/api/reel` returned `items`, and the CLI-shaped `/api/nodes?parent=` returned
 * a bare array. They were the same question at different depths, so they are one
 * route with `depth`, `kind` and `tag` arguments, and one shape comes back.
 */
interface Listing<T> {
  prefix: string;
  sort: string;
  depth: string;
  breadcrumbs: unknown[];
  entries: T[];
  counts: Record<string, number>;
  total: number;
  truncated: boolean;
  next_cursor: string | null;
}

/** A run envelope. Left as a bag: this file dispatches on it, never reads it. */
type Run = Record<string, unknown> & { id: string };

const characterRoot = fixture<Listing<Node>>("character-root");
const character = fixture<{ root: string }>("character");
const characters = fixture<Array<{ id: string }>>("characters");
const libraries = fixture<Array<{ id: string }>>("libraries");
const projects = fixture<unknown>("projects");
const seedFolder = fixture<Listing<Node>>("seed-folder");
const reel = fixture<Listing<Item>>("reel");
const referenceSpec = fixture<unknown>("reference-spec");

export const LIBRARY = libraries[0].id;
export const CHARACTER = characters[0].id;
export const CHARACTER_ROOT = character.root;
export const SEED_FOLDER = characterRoot.entries.find(
  (node) => node.name === "seed",
)!.id;

/**
 * The authoring fixtures — **captured off a stack that has been WORKED IN**,
 * which the seed fixtures above are not.
 *
 * The published dev seed is one character and 54 stills: no project, no runs,
 * nothing ever submitted. So the three screens the run specs are about — a
 * project's Runs tab, a draft in the editor, a finished run with an output to
 * promote — have nothing in the seed to be captured from. `capture.py` takes
 * them as a second group, and its header says why the two groups cannot come
 * off one stack.
 */
const project = fixture<{ id: string; root: string }>("project");
const projectRuns = fixture<{
  runs: Array<{ id: string; status: string; fingerprint?: string }>;
  cursor: string | null;
}>("project-runs");
const draftRun = fixture<Run>("run-draft");
const imageRun = fixture<
  Run & {
    outputs: Array<{
      node: string;
      name: string;
      size?: number;
      content_type?: string | null;
      url: string;
    }>;
  }
>("run-image");
/** The 201 of `POST /api/runs` — not an envelope. See `CreatedRun`. */
const createdRun = fixture<{ id: string; plan_digest: string }>("created-run");
/** `GET /api/runs/<id>` on that same draft, which is what the app reads next. */
const createdRunRecord = fixture<Run>("created-run-record");
const models = fixture<{
  models: Record<string, { key: string; model: string; kind: string }>;
}>("models");
const modelSchema = fixture<{ model: string }>("model-schema");
const references = fixture<{
  counts: Record<string, number>;
  groups: Record<string, Array<Record<string, unknown>>>;
}>("references");
const characterTree = fixture<Listing<Node>>("character-tree");
const referenceTree = fixture<Listing<Node>>("reference-tree");

export const PROJECT = project.id;
/** An unsubmitted run — the one the editor and the run bar are exercised on. */
export const DRAFT_RUN = draftRun.id;
/** A succeeded IMAGE run: what "Run again" re-sends and what promote copies. */
export const IMAGE_RUN = imageRun.id;
/** The draft `POST /api/runs` answers with — where both create flows land. */
export const CREATED_RUN = createdRun.id;
/** The output tile the promote panel is opened from. */
export const OUTPUT = imageRun.outputs[0]!;
/** The character's `reference/` pool, which a promotion finds rather than makes. */
export const REFERENCE_POOL = characterTree.entries.find(
  (folder) => folder.name === "reference",
)!.id;

/**
 * The two nodes a promotion CREATES, which is why they are synthesised.
 *
 * Everything else here was captured; these cannot be, because they do not exist
 * until the run under test makes them. The group folder is `unsorted` — absent
 * from the captured `reference/` listing on purpose, so the spec walks the
 * branch that creates one rather than the branch that finds one.
 */
export const GROUP_FOLDER = "node-e2e00000-0000-0000-0000-000000009rup";
export const COPY = "node-e2e00000-0000-0000-0000-0000000000c0";

/** A 1x1 PNG, so an `<img>` that reaches a stub actually decodes. */
const PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

/**
 * A real MP4, so a `<video>` that reaches a stub actually plays.
 *
 * Every asset here used to be the pixel above, which is why no spec had ever
 * opened `/o`: a `<video>` handed PNG bytes fires `error` and the player shows
 * "this file could not be loaded" — a screen that proves nothing about
 * playback. Five seconds of one colour at 64x36, 1,741 bytes, H.264 so
 * Playwright's bundled Chromium decodes it.
 *
 * **It is generated rather than captured, and that is not a hole in the rule
 * this file is built on.** There is nothing to capture: the published dev seed
 * is 54 stills, because runs, scenes and movies are model output and cost money
 * to make. `capture.py --video` makes it, deterministically, with ffmpeg and no
 * network — see that file's header.
 */
const CLIP = readFileSync(join(HERE, "..", "fixtures", "e2e-asset.mp4"));

const PIXEL_PATH = "/e2e-asset.png";
const CLIP_PATH = "/e2e-asset.mp4";

/**
 * The two things the seed does not hold, built out of two things it does.
 *
 * The seed is images and folders: no clip, and no `prompt.json` either. Both
 * screens the object page can be — the player and the text page — therefore
 * need one node that cannot come off the API. So these are captured rows with
 * a few fields overridden, rather than objects typed out from memory: the
 * SHAPE is still the API's, and a field the API stops sending disappears from
 * here on the next capture the same way it disappears everywhere else.
 */
const STILL_ITEM = reel.entries[0]!;

/** The captured node the cold-link specs open, owner and all. */
export const STILL = seedFolder.entries[0]!;

export const CLIP_ITEM: Item = {
  ...STILL_ITEM,
  id: "node-e2e00000-0000-0000-0000-00000000c11p",
  key: "e2e/e2e-clip.mp4",
  name: "e2e-clip.mp4",
  kind: "video",
  content_type: "video/mp4",
  size: CLIP.byteLength,
  url: CLIP_PATH,
};

export const TEXT_NODE: Node = {
  ...STILL,
  id: "node-e2e00000-0000-0000-0000-0000000073x7",
  name: "e2e-prompt.json",
  content_type: "application/json",
  size: 42,
};

/**
 * One finished run, synthesised rather than captured.
 *
 * A real run's JSON is presigned — `X-Amz-Credential` carries an access key id —
 * and `e2e/README.md` exists because a hand capture once put one in git. The
 * shape here is the API's; the values are the two fixtures this suite already
 * serves, so the output is the same MP4 the player specs use. That makes this
 * the end-to-end check on video previews too: a run whose output renders as a
 * broken image is a run whose thumbnail forgot it was a video.
 */
export const RUN_PROJECT = "proj-e2e0-0000-0000-0000-00000000proj";
export const RUN_ID = "run-e2e00000-0000-0000-0000-000000000run";

/**
 * One assembled scene, synthesised like `RUN` and for the same reason.
 *
 * Its cut is the MP4 this suite already serves, so the scene screen's right-hand
 * column is exercised with real playable bytes rather than a poster that could
 * be anything.
 */
export const SCENE_ID = "scene-e2e0-0000-0000-0000-0000000scene";

export const SCENE: Record<string, unknown> = {
  id: SCENE_ID,
  project: RUN_PROJECT,
  slug: "e2e-scene",
  title: "An end-to-end scene",
  status: "assembled",
  movies: [],
  created: "2026-08-31T12:00:00+00:00",
  folder: "node-e2e-scene-folder",
  setting: "A bare studio wall, one hard key from the left.",
  output: {
    node: CLIP_ITEM.id,
    name: CLIP_ITEM.name,
    url: CLIP_PATH,
    size: CLIP.byteLength,
    content_type: "video/mp4",
  },
  cuts: [],
  shots: [
    {
      id: "shot-e2e-01",
      order: 10,
      prompt: "",
      run: null,
      panel: null,
      beat: "He raises both arms",
      status: "rendered",
      continues: false,
      panels: [],
      motion: {
        prompt: "a steady double-bicep flex",
        duration: 5,
        model: "kling",
      },
      // A rendered shot, so the shot's own right-hand column has something in
      // it — the per-shot split is what this page is really about.
      run: "run-e2e-shot-01",
      node: CLIP_ITEM.id,
      rendered: "2026-08-31T12:20:00+00:00",
      clip: {
        node: CLIP_ITEM.id,
        name: CLIP_ITEM.name,
        url: CLIP_PATH,
        size: CLIP.byteLength,
        content_type: "video/mp4",
      },
      runs: [
        {
          id: "run-e2e-shot-01",
          project: RUN_PROJECT,
          role: "clip",
          status: "succeeded",
          kind: "video",
          model: "kwaivgi/kling-v3-omni-video",
          created: "2026-08-31T12:15:00+00:00",
        },
      ],
    },
  ],
};

export const RUN: Record<string, unknown> = {
  id: RUN_ID,
  lib: LIBRARY,
  project: RUN_PROJECT,
  status: "succeeded",
  kind: "video",
  engine: "kling-replicate",
  model: "kwaivgi/kling-v3-omni-video",
  prediction_id: "e2epredict0000",
  created: "2026-08-31T12:29:00+00:00",
  submitted: "2026-08-31T12:33:30+00:00",
  completed: "2026-08-31T12:35:38+00:00",
  cost: 0.84,
  bindings: {},
  sends: [],
  plan: null,
  approval: null,
  scenes: [],
  characters: [],
  outputs: [
    {
      node: CLIP_ITEM.id,
      name: CLIP_ITEM.name,
      url: CLIP_PATH,
      size: CLIP.byteLength,
      content_type: "video/mp4",
    },
  ],
  // `prompt` points at the text node this suite already serves, so the payload
  // pane has something to render and the wrapping can be measured rather than
  // asserted from the class list.
  payload: { prompt: TEXT_NODE.id, request: null, response: null },
};

/** What a `prompt.json` in this folder would look like. */

export const TEXT_BODY = '{\n  "shot": "e2e",\n  "seconds": 5\n}\n';

/** Every node `GET /api/nodes/<id>` can answer for. */
const NODES = new Map<string, Node>(
  [...characterRoot.entries, ...seedFolder.entries, TEXT_NODE].map((node) => [node.id, node]),
);

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

/** Every run `GET /api/runs/<id>` can answer for. */
const RUNS = new Map<string, Record<string, unknown>>([
  [RUN_ID, RUN],
  [draftRun.id, draftRun],
  [imageRun.id, imageRun],
  [createdRunRecord.id, createdRunRecord],
]);

/**
 * The run behind an id — **falling back to `RUN`, which is not laziness.**
 *
 * Every run this suite reaches by id is in the map. The fallback is what keeps
 * the scene screen's per-shot runs answering as they did before there were any
 * captured runs at all, so adding them changed nothing for the specs that
 * predate them.
 */
function runFor(id: string): Record<string, unknown> {
  return RUNS.get(decodeURIComponent(id)) ?? RUN;
}

/** The run id in a `/api/runs/<id>/...` path. */
function runIdIn(path: string): string {
  return /\/api\/runs\/([^/]+)/.exec(path)?.[1] ?? "";
}

/**
 * The writes, answered — **and dispatched on the METHOD as well as the path.**
 *
 * Every flow this suite covers POSTs to a path that also has a GET: `/api/runs`
 * is the listing and the create, `/api/nodes` is the browse and the mkdir,
 * `/api/characters/<id>/references` is the library and the attach. Dispatching
 * on the path alone answered each of those with the other one's body — a create
 * that returned a listing, an attach that returned a character — which is a
 * green test against a stub doing the opposite of the thing under test.
 *
 * Returns `false` for a write this does not know, so the caller can 501 it. A
 * stub that invented a `{}` for an unrecognised write would turn a missing
 * fixture into a flow that appears to succeed.
 */
async function written(
  route: Route,
  method: string,
  path: string,
  body: Record<string, unknown>,
): Promise<boolean> {
  // A new draft. The 201 is not an envelope — it carries the id, the digest the
  // next call approves against, and little else.
  if (method === "POST" && path.endsWith("/api/runs")) {
    await json(route, createdRun, 201);
    return true;
  }

  // The two halves of the one armed press. Both answer with the run, moved on:
  // `RunBar` swaps what submit returns straight into the page.
  if (method === "POST" && path.endsWith("/approve")) {
    await json(route, { ...runFor(runIdIn(path)), status: "approved" });
    return true;
  }
  if (method === "POST" && path.endsWith("/submit")) {
    await json(route, {
      ...runFor(runIdIn(path)),
      status: "pending",
      submitted: "2026-08-31T12:33:30+00:00",
      prediction_id: "e2epredict0000",
    });
    return true;
  }

  // A promotion ensures two folders, copies, then attaches — see
  // `PromotePanel`. The folder and the copy are the only nodes in this file
  // that could not be captured: they do not exist until the run makes them.
  if (method === "POST" && path.endsWith("/api/nodes")) {
    await json(
      route,
      {
        ...STILL,
        id: GROUP_FOLDER,
        parent_id: String(body.parent ?? ""),
        name: String(body.name ?? ""),
        kind: "folder",
        size: undefined,
        content_type: undefined,
      },
      201,
    );
    return true;
  }
  if (method === "POST" && path.endsWith("/api/nodes/copy")) {
    await json(route, {
      destination: body.destination,
      copied: 1,
      // A whole record, because the destination decides the name — which is why
      // `CopiedNodes` answers with nodes and not with ids.
      nodes: [{ ...STILL, id: COPY, parent_id: body.destination, name: OUTPUT.name }],
    });
    return true;
  }
  if (method === "POST" && path.endsWith("/references")) {
    // The captured row for this character, pointed at whatever was attached.
    const row = Object.values(references.groups)[0]?.[0] ?? {};
    await json(route, { ...row, node: body.node, group: body.group }, 201);
    return true;
  }

  return false;
}

/**
 * Route every API call, and FAIL LOUDLY on one this does not know.
 *
 * A stub that quietly returns `{}` for an unrecognised path turns a missing
 * fixture into an empty screen and an assertion about nothing. A 501 with the
 * path in it says which fixture to capture.
 */
export async function stubApi(page: Page): Promise<void> {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());
    const path = url.pathname;
    const parent = url.searchParams.get("parent");

    // **Writes first, and that ordering is the whole of the method branching.**
    // Below this line every branch may assume a GET, which is what it always
    // assumed and never said.
    if (method !== "GET") {
      let body: Record<string, unknown> = {};
      try {
        body = (request.postDataJSON() ?? {}) as Record<string, unknown>;
      } catch {
        /* a write with no JSON body — DELETE, mostly */
      }
      if (await written(route, method, path, body)) return;
      return json(
        route,
        { error: `e2e: no fixture for ${method} ${path}` },
        501,
      );
    }

    if (path.endsWith("/api/libraries")) return json(route, libraries);
    // Before `/api/characters`, which does not match it, but keeping the spec
    // next to the listings it is a sibling of.
    if (path.endsWith("/api/reference-spec")) return json(route, referenceSpec);
    if (path.endsWith("/api/characters")) return json(route, characters);
    // Before the character itself, which would otherwise swallow it — the old
    // dispatch answered a reference library with a character record.
    if (path.endsWith("/references")) return json(route, references);
    if (path.includes("/api/characters/")) return json(route, character);
    if (path.endsWith("/api/projects")) return json(route, projects);
    // The record only. `/api/projects/<id>/scenes` and its siblings keep
    // falling through to the 501 — a project record standing in for a scenes
    // listing is exactly the silent wrong answer this file exists to refuse.
    if (/\/api\/projects\/[^/]+$/.test(path)) return json(route, project);
    // The registry: the map, one entry, or one entry's LIVE schema. A model
    // name is `owner/name`, so the id is the rest of the path rather than one
    // segment.
    if (path.endsWith("/api/models")) return json(route, models);
    const model = /\/api\/models\/(.+?)(\/schema)?$/.exec(path);
    if (model) {
      if (model[2]) return json(route, modelSchema);
      const name = decodeURIComponent(model[1]!);
      const entry = Object.values(models.models).find(
        (each) => each.model === name || each.key === name,
      );
      return entry
        ? json(route, entry)
        : json(route, { error: `e2e: no fixture for model ${name}` }, 501);
    }
    // The listing. `fingerprint` is filtered rather than ignored: it is the
    // duplicate-payload question, and a stub that answered it with the whole
    // project would put a "this has been run before" banner on every draft.
    if (path.endsWith("/api/runs")) {
      const fingerprint = url.searchParams.get("fingerprint");
      return json(route, {
        runs: fingerprint
          ? projectRuns.runs.filter((run) => run.fingerprint === fingerprint)
          : projectRuns.runs,
        cursor: null,
      });
    }
    // The draft payload preview, before the more general run route so it is not
    // swallowed by it.
    if (path.includes("/api/runs/") && path.endsWith("/payload")) {
      return json(route, { request: RUN.payload ?? {}, prompt: null });
    }
    if (path.includes("/api/runs/")) return json(route, runFor(runIdIn(path)));
    if (path.includes("/api/scenes/")) return json(route, SCENE);
    // **The one listing.** `/api/tree`, `/api/reel` and the CLI-shaped
    // `/api/nodes?parent=` were folded into it, so this stub dispatches on the
    // arguments that told them apart rather than on three paths.
    if (path.endsWith("/api/nodes")) {
      const under = url.searchParams.get("under");
      // Recursive: the clip leads the walk, so `/o?in=recursive` opens on it.
      // The seed carries no video and a library does, so a reel that is stills
      // all the way down is the less faithful answer of the two.
      if (url.searchParams.get("depth") === "all") {
        return json(route, {
          ...reel,
          entries: [CLIP_ITEM, ...reel.entries],
          total: reel.total + 1,
        });
      }
      if (under === CHARACTER_ROOT) return json(route, characterTree);
      if (under === REFERENCE_POOL) return json(route, referenceTree);
      if (under === SEED_FOLDER) return json(route, seedFolder);
      return json(route, { ...referenceTree, entries: [], counts: {}, total: 0 });
    }

    // One node, its words, or what owns it — the three routes a `/o/<id>` link
    // with no `?in=` makes, and the only ones the browse specs never reached.
    const node = /\/api\/nodes\/([^/]+)(?:\/(text|owner))?$/.exec(path);
    if (node) {
      const record = NODES.get(decodeURIComponent(node[1]!));
      if (!record)
        return json(
          route,
          { error: `e2e: no fixture for node ${node[1]}` },
          501,
        );
      if (node[2] === "owner") return json(route, record.owner ?? null);
      if (node[2] === "text") {
        return json(route, {
          id: record.id,
          name: record.name,
          language: "json",
          truncated: false,
          content: TEXT_BODY,
        });
      }
      return json(route, record);
    }

    // Signed reads: the app asks for a URL and then fetches it. Both are
    // answered here so no request leaves the browser. Which body comes back is
    // decided by the node, because a re-sign of a clip that answers with a PNG
    // is exactly the failure this suite is here to notice.
    if (path.includes("/download-url") || path.includes("/asset")) {
      const asset =
        url.searchParams.get("node") === CLIP_ITEM.id ? CLIP_PATH : PIXEL_PATH;
      return json(route, { url: `${url.origin}${asset}` });
    }
    return json(route, { error: `e2e: no fixture for ${path}` }, 501);
  });

  await page.route(`**${PIXEL_PATH}`, (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: PIXEL }),
  );

  await page.route(`**${CLIP_PATH}`, (route) =>
    route.fulfill({ status: 200, contentType: "video/mp4", body: CLIP }),
  );
}
