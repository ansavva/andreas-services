import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../apis/studio", () => ({ getAsset: vi.fn() }));

import { getAsset } from "../apis/studio";
import { useSignedSrc } from "./useSignedSrc";

const signed = vi.mocked(getAsset);

/**
 * The bytes behind a node never change; only the signature on the URL does.
 * So a re-signed listing must not become a reload of every picture on it.
 */
describe("a fresh signature for the same node", () => {
  it("keeps the URL already loaded, and takes a different node's outright", () => {
    const { result, rerender } = renderHook(
      ({ node, url }: { node: string; url: string }) => useSignedSrc(node, url),
      { initialProps: { node: "node-1", url: "/a.png?sig=1" } },
    );
    expect(result.current.src).toBe("/a.png?sig=1");

    rerender({ node: "node-1", url: "/a.png?sig=2" });
    expect(result.current.src).toBe("/a.png?sig=1");

    rerender({ node: "node-2", url: "/b.png?sig=1" });
    expect(result.current.src).toBe("/b.png?sig=1");
  });

  it("re-arms the one retry, so a second expiry re-signs rather than fails", async () => {
    signed.mockResolvedValue({ url: "/a.png?sig=fresh" } as never);
    const { result, rerender } = renderHook(
      ({ url }: { url: string }) => useSignedSrc("node-1", url),
      { initialProps: { url: "/a.png?sig=1" } },
    );

    await act(async () => result.current.onError());
    expect(result.current.src).toBe("/a.png?sig=fresh");
    expect(signed).toHaveBeenCalledTimes(1);

    // Without a fresh signature in between, the second error is final.
    await act(async () => result.current.onError());
    expect(result.current.failed).toBe(true);

    // A listing re-read since is what says "try once more".
    rerender({ url: "/a.png?sig=2" });
    expect(result.current.failed).toBe(false);
    await act(async () => result.current.onError());
    expect(signed).toHaveBeenCalledTimes(2);
    expect(result.current.failed).toBe(false);
  });

  it("adopts a URL where it had none — a record repaired under an open tab", () => {
    const { result, rerender } = renderHook(
      ({ url }: { url: string | null }) => useSignedSrc("node-1", url),
      { initialProps: { url: null as string | null } },
    );
    expect(result.current.failed).toBe(true);
    rerender({ url: "/a.png?sig=1" });
    expect(result.current.src).toBe("/a.png?sig=1");
    expect(result.current.failed).toBe(false);
  });
});
