import { afterEach, describe, expect, it, vi } from "vitest";

// Same stub `client.test.ts` uses, and for the same reason: what is under test
// is the URL a wrapper builds, not the token on it.
vi.mock("../amplify", () => ({ isAuthConfigured: false }));

import {
  copyNodes,
  deleteNodes,
  getAsset,
  getNodeText,
  moveNodes,
  putCharacterProfile,
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

    await putCharacterProfile("char-0001", { identity: { register: "…" } }, 4);

    expect(urlOf(fetcher).pathname).toBe("/api/characters/char-0001/profile");
    expect(initOf(fetcher).method).toBe("PUT");
    expect(bodyOf(fetcher)).toEqual({ profile: { identity: { register: "…" } }, rev: 4 });
  });
});
