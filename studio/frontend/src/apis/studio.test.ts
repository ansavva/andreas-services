import { afterEach, describe, expect, it, vi } from "vitest";

// Same stub `client.test.ts` uses, and for the same reason: what is under test
// is the URL a wrapper builds, not the token on it.
vi.mock("../amplify", () => ({ isAuthConfigured: false }));

import { getAsset, getText, saveText } from "./studio";

function stubFetch() {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

function urlOf(fetcher: ReturnType<typeof stubFetch>): URL {
  return new URL(String(fetcher.mock.calls[0]?.[0]));
}

function bodyOf(fetcher: ReturnType<typeof stubFetch>): Record<string, unknown> {
  return JSON.parse(String((fetcher.mock.calls[0]?.[1] as { body: string }).body));
}

afterEach(() => vi.unstubAllGlobals());

/**
 * The two reads address a node, and this file is what stops them drifting back.
 *
 * `?key=` on `/api/asset` is a **raw S3 key** — the one parameter in the API
 * that is not a name path, kept because the pipeline reads shared material with
 * no catalog node through it. A row's `key` is a name path, so sending it there
 * signs whatever object happens to sit at that string: nothing at all for
 * anything uploaded through the app, whose bytes are at `blobs/<id>` (#432).
 * The mistake is invisible in types — both are strings — so it is asserted here.
 */
describe("the reads that take a node id", () => {
  it("asks for an asset by node, never by key", async () => {
    const fetcher = stubFetch();

    await getAsset("node-0001", "attachment");

    const url = urlOf(fetcher);
    expect(url.pathname).toBe("/api/asset");
    expect(url.searchParams.get("node")).toBe("node-0001");
    expect(url.searchParams.get("key")).toBeNull();
    expect(url.searchParams.get("disposition")).toBe("attachment");
  });

  it("signs inline unless a download asked otherwise", async () => {
    // The default matters: `attachment` is what makes a cross-origin download
    // download, and applying it to every re-signed tile would download them.
    const fetcher = stubFetch();

    await getAsset("node-0001");

    expect(urlOf(fetcher).searchParams.get("disposition")).toBe("inline");
  });

  it("asks for text by node, never by key", async () => {
    const fetcher = stubFetch();

    await getText("node-0002");

    const url = urlOf(fetcher);
    expect(url.pathname).toBe("/api/text");
    expect(url.searchParams.get("node")).toBe("node-0002");
    expect(url.searchParams.get("key")).toBeNull();
  });
});

/**
 * The write half still sends a name path, and that is not an oversight.
 *
 * `PATCH /api/text` takes one, `GET /api/text?key=` takes the same one, and the
 * two resolve to the same node — which is the whole of #432. The SPA sends the
 * id on the read because it is the cheaper address, not because the path is
 * wrong.
 */
describe("saving text", () => {
  it("sends the name path", async () => {
    const fetcher = stubFetch();

    await saveText("characters/subject-a/profile.yaml", "name: x\n");

    expect(urlOf(fetcher).pathname).toBe("/api/text");
    expect(bodyOf(fetcher)).toEqual({
      key: "characters/subject-a/profile.yaml",
      content: "name: x\n",
    });
  });
});
