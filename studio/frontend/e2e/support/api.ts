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

interface Reel {
  prefix: string;
  sort: string;
  items: Item[];
  total: number;
  truncated: boolean;
  next_cursor: string | null;
}

const characterRoot = fixture<Node[]>("character-root");
const character = fixture<{ root: string }>("character");
const characters = fixture<Array<{ id: string }>>("characters");
const libraries = fixture<Array<{ id: string }>>("libraries");
const projects = fixture<unknown>("projects");
const seedFolder = fixture<Node[]>("seed-folder");
const reel = fixture<Reel>("reel");

export const LIBRARY = libraries[0].id;
export const CHARACTER = characters[0].id;
export const CHARACTER_ROOT = character.root;
export const SEED_FOLDER = characterRoot.find(
  (node) => node.name === "seed",
)!.id;

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
const STILL_ITEM = reel.items[0]!;

/** The captured node the cold-link specs open, owner and all. */
export const STILL = seedFolder[0]!;

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
  [...characterRoot, ...seedFolder, TEXT_NODE].map((node) => [node.id, node]),
);

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
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
    const url = new URL(route.request().url());
    const path = url.pathname;
    const parent = url.searchParams.get("parent");

    if (path.endsWith("/api/libraries")) return json(route, libraries);
    if (path.endsWith("/api/characters")) return json(route, characters);
    if (path.includes("/api/characters/")) return json(route, character);
    if (path.endsWith("/api/projects")) return json(route, projects);
    if (path.includes("/api/runs/")) return json(route, RUN);
    // The clip leads the walk, so `/o?in=recursive` opens on it. The seed
    // carries no video and a library does, so a reel that is stills all the way
    // down is the less faithful answer of the two.
    if (path.endsWith("/api/reel")) {
      return json(route, {
        ...reel,
        items: [CLIP_ITEM, ...reel.items],
        total: reel.total + 1,
      });
    }
    if (path.endsWith("/api/nodes")) {
      if (parent === CHARACTER_ROOT) return json(route, characterRoot);
      if (parent === SEED_FOLDER) return json(route, seedFolder);
      return json(route, []);
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
