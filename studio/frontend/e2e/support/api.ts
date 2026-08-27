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

const characterRoot = fixture<Array<{ id: string; name: string }>>("character-root");
const character = fixture<{ root: string }>("character");
const characters = fixture<Array<{ id: string }>>("characters");
const libraries = fixture<Array<{ id: string }>>("libraries");
const projects = fixture<unknown>("projects");
const seedFolder = fixture<unknown>("seed-folder");
const reel = fixture<unknown>("reel");

export const LIBRARY = libraries[0].id;
export const CHARACTER = characters[0].id;
export const CHARACTER_ROOT = character.root;
export const SEED_FOLDER = characterRoot.find((node) => node.name === "seed")!.id;

/** A 1x1 PNG, so an `<img>` that reaches a stub actually decodes. */
const PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
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
    if (path.endsWith("/api/reel")) return json(route, reel);
    if (path.endsWith("/api/nodes")) {
      if (parent === CHARACTER_ROOT) return json(route, characterRoot);
      if (parent === SEED_FOLDER) return json(route, seedFolder);
      return json(route, []);
    }
    // Signed reads: the app asks for a URL and then fetches it. Both are
    // answered here so no request leaves the browser.
    if (path.includes("/download-url") || path.includes("/asset")) {
      return json(route, { url: `${url.origin}/e2e-asset.png` });
    }
    return json(route, { error: `e2e: no fixture for ${path}` }, 501);
  });

  await page.route("**/e2e-asset.png", (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: PIXEL }),
  );
}
