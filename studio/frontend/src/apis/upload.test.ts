import { afterEach, describe, expect, it, vi } from "vitest";

// Same stub the other two API suites use: what is under test is the sequence of
// requests, not the token on them.
vi.mock("../amplify", () => ({ isAuthConfigured: false }));

import { contentTypeOf, putSigned, rejectionFor, uploadFile } from "./upload";
import type { UploadGrant } from "../types";

const GRANT: UploadGrant = {
  id: "node-0001",
  url: "https://bucket.s3.amazonaws.com/blobs/node-0001?X-Amz-SignedHeaders=content-length%3Bcontent-type",
  expires_in: 300,
  headers: { "Content-Length": "9", "Content-Type": "video/mp4" },
};

function file(name = "clip.mp4", type = "video/mp4", bytes = "mp4-bytes") {
  return new File([bytes], name, { type });
}

/**
 * A fake `XMLHttpRequest` that records what was opened and set, and that fires
 * whatever outcome the test asked for.
 *
 * **The network is never reached and must never be.** These tests are about the
 * order of four calls and the headers on one of them; an actual PUT would be an
 * S3 write from a unit suite.
 */
interface FakeXhr {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: unknown;
}

function stubXhr({
  status = 200,
  transportError = false,
  progress = [] as Array<{ loaded: number; total: number; lengthComputable: boolean }>,
} = {}) {
  const sent: FakeXhr[] = [];

  class Fake {
    method = "";
    url = "";
    status = 0;
    headers: Record<string, string> = {};
    upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onabort: (() => void) | null = null;
    ontimeout: (() => void) | null = null;

    open(method: string, url: string) {
      this.method = method;
      this.url = url;
    }

    setRequestHeader(name: string, value: string) {
      this.headers[name] = value;
    }

    send(body: unknown) {
      sent.push({ method: this.method, url: this.url, headers: this.headers, body });
      // Asynchronously, as a real one is: a handler assigned after `send` in the
      // implementation would still be attached in time, and a synchronous fake
      // would hide that mistake.
      setTimeout(() => {
        for (const event of progress) {
          this.upload.onprogress?.(event as unknown as ProgressEvent);
        }
        if (transportError) {
          this.onerror?.();
          return;
        }
        this.status = status;
        this.onload?.();
      }, 0);
    }

    abort() {
      this.onabort?.();
    }
  }

  vi.stubGlobal("XMLHttpRequest", Fake);
  return sent;
}

/** Records every `fetch` and answers each with the JSON the API would send. */
function stubApi(answers: unknown[]) {
  let call = 0;
  const fetcher = vi.fn().mockImplementation(() => {
    const body = answers[call] ?? {};
    call += 1;
    return Promise.resolve({ ok: true, json: async () => body });
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

function callsOf(fetcher: ReturnType<typeof stubApi>) {
  return fetcher.mock.calls.map(([url, init]) => ({
    method: (init as { method: string }).method,
    path: new URL(String(url)).pathname,
    body: (init as { body?: string }).body ? JSON.parse((init as { body: string }).body) : null,
  }));
}

afterEach(() => vi.unstubAllGlobals());

/**
 * The order is the contract, and every step of it depends on the one before.
 *
 * The node names the key, the key is what gets signed, and the confirm reads the
 * size off the object that PUT put there. Reordered, each step signs or confirms
 * something that does not exist yet — and the failure would be a 404 from S3
 * that reads like an infrastructure problem.
 */
describe("one file, four calls", () => {
  it("creates, signs, PUTs, then confirms", async () => {
    const fetcher = stubApi([
      { id: "node-0001", name: "clip.mp4", kind: "file" },
      GRANT,
      { id: "node-0001", name: "clip.mp4", kind: "file", size: 9 },
    ]);
    const sent = stubXhr();

    await uploadFile("node-parent", file());

    expect(callsOf(fetcher)).toEqual([
      {
        method: "POST",
        path: "/api/nodes",
        body: { parent: "node-parent", name: "clip.mp4", kind: "file", on_conflict: "number" },
      },
      {
        method: "POST",
        path: "/api/nodes/node-0001/upload-url",
        body: { size: 9, content_type: "video/mp4" },
      },
      { method: "POST", path: "/api/nodes/node-0001/confirm-upload", body: {} },
    ]);
    expect(sent).toHaveLength(1);
    expect(sent[0]?.method).toBe("PUT");
    expect(sent[0]?.url).toBe(GRANT.url);
  });

  it("declares the size the file actually is", async () => {
    // The size is a *signed* header, so a declaration that disagrees with the
    // body fails validation at S3 and writes nothing. It has to come off the
    // file rather than from anywhere else.
    const fetcher = stubApi([{ id: "node-0001", name: "big.mp4" }, GRANT, {}]);
    stubXhr();

    await uploadFile("node-parent", file("big.mp4", "video/mp4", "x".repeat(4096)));

    expect(callsOf(fetcher)[1]?.body).toEqual({ size: 4096, content_type: "video/mp4" });
  });
});

/**
 * The headers are the grant. `upload-url` signs `content-length` and
 * `content-type`, so what goes on the PUT is not this client's choice.
 */
describe("the signed headers", () => {
  it("sends back exactly what the API returned, minus the one it cannot", async () => {
    stubApi([{ id: "node-0001", name: "clip.mp4" }, GRANT, {}]);
    const sent = stubXhr();

    await uploadFile("node-parent", file());

    expect(sent[0]?.headers).toEqual({ "Content-Type": "video/mp4" });
  });

  it("does not try to set Content-Length", async () => {
    // A forbidden header name: `setRequestHeader` for it is a silent no-op and
    // the browser supplies the value itself. Calling it anyway would read as a
    // working line and would be doing nothing — the signature validates because
    // the browser's own value is `file.size`, not because this sent one.
    stubApi([{ id: "node-0001", name: "clip.mp4" }, GRANT, {}]);
    const sent = stubXhr();

    await uploadFile("node-parent", file());

    expect(Object.keys(sent[0]?.headers ?? {})).not.toContain("Content-Length");
  });

  it("sends whatever else a future grant signs", async () => {
    // The list is read off the response rather than hard-coded, so adding a
    // signed header to `presign_put` needs no change here.
    stubApi([
      { id: "node-0001", name: "clip.mp4" },
      { ...GRANT, headers: { ...GRANT.headers, "x-amz-meta-run": "abc" } },
      {},
    ]);
    const sent = stubXhr();

    await uploadFile("node-parent", file());

    expect(sent[0]?.headers["x-amz-meta-run"]).toBe("abc");
  });
});

/**
 * A failure before the confirm must not confirm, and must not leave a row
 * pointing at bytes that never arrived.
 *
 * `browse._file_entry` presigns any row carrying a `blob_key`, so an abandoned
 * placeholder is a tile the grid draws and cannot load — not, as #294 assumed, a
 * row nobody sees. `studio catalog gc` does not collect it either: that command
 * deletes blobs no row names, which is the other direction.
 */
describe("a PUT that fails", () => {
  it("does not confirm", async () => {
    const fetcher = stubApi([{ id: "node-0001", name: "clip.mp4" }, GRANT, {}, {}]);
    stubXhr({ status: 403 });

    await expect(uploadFile("node-parent", file())).rejects.toThrow(/403/);

    expect(callsOf(fetcher).map((call) => call.path)).not.toContain(
      "/api/nodes/node-0001/confirm-upload",
    );
  });

  it("deletes the placeholder it created", async () => {
    const fetcher = stubApi([{ id: "node-0001", name: "clip.mp4" }, GRANT, {}]);
    stubXhr({ transportError: true });

    await expect(uploadFile("node-parent", file())).rejects.toThrow(/connection/);

    // Awaited out of the microtask queue: the cleanup is deliberately not
    // awaited by the failure path, so that the message the caller sees is why
    // the upload failed rather than why the tidy-up did.
    await Promise.resolve();
    expect(callsOf(fetcher)).toContainEqual({
      method: "DELETE",
      path: "/api/nodes/node-0001",
      body: null,
    });
  });

  it("reports the transport failure, not the cleanup's", async () => {
    stubApi([{ id: "node-0001", name: "clip.mp4" }, GRANT]);
    stubXhr({ status: 500 });

    await expect(uploadFile("node-parent", file())).rejects.toThrow(
      "Upload refused by storage (500)",
    );
  });
});

/**
 * Each file is its own node, and that is what makes numbering work: the catalog
 * decides each name against the folder as it stands at that moment.
 */
describe("more than one file", () => {
  it("mints a node per file", async () => {
    const fetcher = stubApi([
      { id: "node-a", name: "clip.mp4" },
      { ...GRANT, id: "node-a" },
      { id: "node-a", name: "clip.mp4" },
      { id: "node-b", name: "clip (2).mp4" },
      { ...GRANT, id: "node-b" },
      { id: "node-b", name: "clip (2).mp4" },
    ]);
    stubXhr();

    await uploadFile("node-parent", file());
    await uploadFile("node-parent", file());

    const paths = callsOf(fetcher).map((call) => call.path);
    expect(paths.filter((path) => path === "/api/nodes")).toHaveLength(2);
    expect(paths).toContain("/api/nodes/node-a/upload-url");
    expect(paths).toContain("/api/nodes/node-b/upload-url");
  });

  it("reports the name the catalog gave the second one", async () => {
    // The `(2)` is minted server-side (`catalog.create_numbered`), so this
    // asserts the client *reads* it back rather than composing one of its own —
    // a client-side copy of the convention would be a second implementation
    // that only disagrees in a folder that has been through copy as well.
    stubApi([
      { id: "node-b", name: "clip (2).mp4", kind: "file" },
      { ...GRANT, id: "node-b" },
      { id: "node-b", name: "clip (2).mp4", kind: "file", size: 9 },
    ]);
    stubXhr();

    const node = await uploadFile("node-parent", file());

    expect(node.name).toBe("clip (2).mp4");
  });

  it("asks the catalog to number rather than sending a name it made up", async () => {
    const fetcher = stubApi([{ id: "node-0001", name: "clip.mp4" }, GRANT, {}]);
    stubXhr();

    await uploadFile("node-parent", file());

    expect(callsOf(fetcher)[0]?.body).toMatchObject({
      name: "clip.mp4",
      on_conflict: "number",
    });
  });
});

describe("progress", () => {
  it("reports bytes as they go out", async () => {
    // The one thing `fetch` cannot do, and the whole reason this module reaches
    // for `XMLHttpRequest`: a `fetch` upload can only ever draw an indeterminate
    // bar, which over ten minutes of a large clip is indistinguishable from a
    // hang.
    stubXhr({
      progress: [
        { loaded: 4, total: 9, lengthComputable: true },
        { loaded: 9, total: 9, lengthComputable: true },
      ],
    });
    const seen: Array<{ loaded: number; total: number }> = [];

    await putSigned(GRANT, file(), { onProgress: (p) => seen.push(p) });

    expect(seen).toEqual([
      { loaded: 4, total: 9 },
      { loaded: 9, total: 9 },
    ]);
  });

  it("ignores an event that cannot say how big the body is", async () => {
    // `lengthComputable: false` carries a zero total; reporting it would make
    // the bar jump backwards to empty part-way through.
    stubXhr({ progress: [{ loaded: 0, total: 0, lengthComputable: false }] });
    const seen: Array<{ loaded: number; total: number }> = [];

    await putSigned(GRANT, file(), { onProgress: (p) => seen.push(p) });

    expect(seen).toEqual([]);
  });

  it("rejects when aborted", async () => {
    stubXhr();
    const controller = new AbortController();
    const pending = putSigned(GRANT, file(), { signal: controller.signal });
    controller.abort();

    await expect(pending).rejects.toThrow(/cancelled/);
  });
});

describe("what is refused before anything is created", () => {
  it("refuses a HEIC by extension, naming the fix", () => {
    const refusal = rejectionFor(file("IMG_0001.HEIC", ""));

    expect(refusal).toMatch(/HEIC/);
    expect(refusal).toMatch(/Most Compatible/);
  });

  it("refuses a HEIC by type when the name does not say so", () => {
    expect(rejectionFor(file("photo", "image/heic"))).not.toBeNull();
  });

  it("lets an ordinary clip through", () => {
    expect(rejectionFor(file())).toBeNull();
  });

  it("creates no node for a refused file", async () => {
    const fetcher = stubApi([]);
    stubXhr();

    await expect(uploadFile("node-parent", file("IMG_0001.HEIC", ""))).rejects.toThrow(/HEIC/);

    expect(fetcher).not.toHaveBeenCalled();
  });

  it("substitutes a type for a file that has none", () => {
    // The API requires a non-empty `content_type` — it is a signed header, so
    // there is nothing to sign without one.
    expect(contentTypeOf(file("notes", ""))).toBe("application/octet-stream");
    expect(contentTypeOf(file())).toBe("video/mp4");
  });
});
