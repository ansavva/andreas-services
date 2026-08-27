import { afterEach, describe, expect, it, vi } from "vitest";

// Same stub `client.test.ts` uses, and for the same reason: what is under test
// is the URL a wrapper builds, not the token on it.
vi.mock("../amplify", () => ({ isAuthConfigured: false }));

import {
  copyNodes,
  getProjectMovies,
  getProjectInputs,
  getProjectScenes,
  deleteNodes,
  getAsset,
  getNodeText,
  moveNodes,
  setCharacterProfile,
  renameNode,
  saveNodeText,
} from "./studio";

function stubFetch() {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

function urlOf(fetcher: ReturnType<typeof stubFetch>): URL {
  return new URL(String(fetcher.mock.calls[0]?.[0]));
}

function initOf(fetcher: ReturnType<typeof stubFetch>): { method: string; body: string } {
  return fetcher.mock.calls[0]?.[1] as { method: string; body: string };
}

function bodyOf(fetcher: ReturnType<typeof stubFetch>): Record<string, unknown> {
  return JSON.parse(String(initOf(fetcher).body));
}

afterEach(() => vi.unstubAllGlobals());

/**
 * There is one addressing scheme now, and this file is what stops a second one
 * growing back.
 *
 * Every write here used to take a slash-joined *name path* under a parameter
 * called `key` or `prefix`, and the mistake that made was invisible in types: a
 * row carries an `id` and a `key`, both are `string`, and sending the wrong one
 * compiles, renders and fails only against material uploaded through the app —
 * whose bytes live under an entity-prefixed key that the name path does not
 * resemble at all. So the *argument* is asserted here, not just the parameter.
 */
describe("the file layer addresses nodes by id", () => {
  it("reads text on the node's own route", async () => {
    const fetcher = stubFetch();

    await getNodeText("node-0002");

    expect(urlOf(fetcher).pathname).toBe("/api/nodes/node-0002/text");
    expect(urlOf(fetcher).searchParams.get("key")).toBeNull();
  });

  it("writes text back to the same route it read from", async () => {
    // The read and the write used to resolve through two different addresses,
    // which is the half of #432 that survived it. One route, both directions.
    const fetcher = stubFetch();

    await saveNodeText("node-0002", "name: x\n");

    expect(urlOf(fetcher).pathname).toBe("/api/nodes/node-0002/text");
    expect(initOf(fetcher).method).toBe("PATCH");
    expect(bodyOf(fetcher)).toEqual({ content: "name: x\n" });
  });

  it("renames by id, and sends no parent — both together is a 400", async () => {
    const fetcher = stubFetch();

    await renameNode("node-0003", "three-quarter-left-v2.png");

    expect(urlOf(fetcher).pathname).toBe("/api/nodes/node-0003");
    expect(bodyOf(fetcher)).toEqual({ name: "three-quarter-left-v2.png" });
  });

  it("moves and copies a mixed selection through one route each", async () => {
    // A folder and a file in one call is the whole of what ids bought here:
    // there used to be an endpoint per address shape.
    const move = stubFetch();
    await moveNodes(["node-0004", "node-0005"], "node-0006");
    expect(urlOf(move).pathname).toBe("/api/nodes/move");
    expect(bodyOf(move)).toEqual({ ids: ["node-0004", "node-0005"], destination: "node-0006" });

    vi.unstubAllGlobals();
    const copy = stubFetch();
    await copyNodes(["node-0004"], "node-0006");
    expect(urlOf(copy).pathname).toBe("/api/nodes/copy");
    expect(bodyOf(copy)).toEqual({ ids: ["node-0004"], destination: "node-0006" });
  });

  it("deletes with a body rather than a few hundred query parameters", async () => {
    const fetcher = stubFetch();

    await deleteNodes(["node-0007", "node-0008"]);

    expect(urlOf(fetcher).pathname).toBe("/api/nodes");
    expect(initOf(fetcher).method).toBe("DELETE");
    expect(bodyOf(fetcher)).toEqual({ ids: ["node-0007", "node-0008"] });
  });

  it("still signs an asset by node, never by key", async () => {
    // `?key=` on `/api/asset` was a raw *S3* key, which is the one address in
    // this API that never was a name path. Sending a row's `key` there signed
    // whatever happened to sit at that string.
    const fetcher = stubFetch();

    await getAsset("node-0009", "attachment");

    const url = urlOf(fetcher);
    expect(url.pathname).toBe("/api/asset");
    expect(url.searchParams.get("node")).toBe("node-0009");
    expect(url.searchParams.get("key")).toBeNull();
    expect(url.searchParams.get("disposition")).toBe("attachment");
  });

  it("signs inline unless a download asked otherwise", async () => {
    // The default matters: `attachment` is what makes a cross-origin download
    // download, and applying it to every re-signed tile would download them.
    const fetcher = stubFetch();

    await getAsset("node-0009");

    expect(urlOf(fetcher).searchParams.get("disposition")).toBe("inline");
  });
});

/**
 * The entity writes carry the revision they read at.
 *
 * That is a compare-and-swap, and it is the only thing between two people
 * editing one bible and one of them silently losing their work. A write that
 * forgot to send `rev` would not fail loudly — it would be *accepted*, which is
 * exactly the shape of bug worth an assertion.
 */
describe("record writes send `rev`", () => {
  it("replaces a profile at the revision it was read at", async () => {
    const fetcher = stubFetch();

    await setCharacterProfile("char-0001", { identity: { register: "…" } }, 4);

    expect(urlOf(fetcher).pathname).toBe("/api/characters/char-0001/profile");
    // PATCH, not PUT: replace and merge share one address and are told apart by
    // the body's key. This asserted PUT, which the API neither routes nor allows
    // through CORS — the assertion agreed with the client and both were wrong.
    expect(initOf(fetcher).method).toBe("PATCH");
    expect(bodyOf(fetcher)).toEqual({ profile: { identity: { register: "…" } }, rev: 4 });
  });
});

describe("project listings", () => {
  // `/api/projects/<id>/{runs,scenes,movies}` all answer `{ "<kind>s": [...],
  // "cursor": null }` — one `_listing` builds all three, and none is a bare
  // array. Scenes and movies were typed as the array and handed the object to a
  // caller doing `data.length === 0` then `data.map(...)`: the empty check
  // silently passed on `undefined` and the map threw, so both tabs crashed. The
  // Scenes tab is the only route to a scene in the app.
  it("unwraps the scenes page into the rows", async () => {
    const rows = [{ id: "scene-1", slug: "light-flex" }];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ scenes: rows, cursor: null }) }),
    );

    await expect(getProjectScenes("proj-1")).resolves.toEqual(rows);
  });

  it("unwraps the movies page into the rows", async () => {
    const rows = [{ id: "movie-1", slug: "the-cut" }];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ movies: rows, cursor: null }) }),
    );

    await expect(getProjectMovies("proj-1")).resolves.toEqual(rows);
  });

  it("reads a project with no scenes as none, not as a crash", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ scenes: [], cursor: null }) }),
    );

    await expect(getProjectScenes("proj-1")).resolves.toEqual([]);
  });

  // The THIRD of these, found the same way and fixed after the other two.
  // `/inputs` answers `{folder, inputs}` — a different envelope again, which is
  // why fixing scenes and movies did not fix it — and it was typed as the bare
  // array, so the Inputs tab called `.map` on an object and threw.
  it("unwraps the input pool out of its folder envelope", async () => {
    const rows = [{ id: "node-1", name: "plate.png", url: "https://x/1" }];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ folder: "node-f", inputs: rows }) }),
    );

    await expect(getProjectInputs("proj-1")).resolves.toEqual(rows);
  });

  it("reads an empty input pool as none, not as a crash", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ folder: "node-f", inputs: [] }) }),
    );

    await expect(getProjectInputs("proj-1")).resolves.toEqual([]);
  });
});
