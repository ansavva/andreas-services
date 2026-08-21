import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { NodeRecord } from "../types";

// The whole API module, because `routes.tsx` pulls in `BrowsePage`, which
// imports the write half of it. Nothing here calls those; they only have to
// exist.
vi.mock("../apis/studio", () => ({ resolvePath: vi.fn() }));

// `BrowsePage` is the destination, not the subject: what these cases assert is
// which component a URL reaches and what the resolver does on the way. Stubbing
// it keeps the auth context, Amplify and a listing fetch out of a routing test.
vi.mock("./BrowsePage", () => ({
  BrowsePage: () => <div data-testid="browse" />,
}));

import { resolvePath } from "../apis/studio";
import { StudioRoutes } from "../routes";

const resolve = vi.mocked(resolvePath);

const NODE = "0f2a1c9e-4b7d-4c11-9a3e-2d5b6f8c0a41";
const PARENT = "3c8d5e21-77aa-4f0b-8e19-1b4c9d0e6f22";

// Testing Library only registers its own cleanup when Vitest globals are on,
// and they are not — so an unmounted tree would otherwise stay in the document
// and the next case would find two of everything.
afterEach(cleanup);

function record(kind: NodeRecord["kind"]): NodeRecord {
  return {
    id: NODE,
    lib: "lib-1",
    parent_id: "3c8d5e21-77aa-4f0b-8e19-1b4c9d0e6f22",
    name: "clip.mp4",
    kind,
    created_at: "2026-08-14T16:32:11.000123",
  };
}

/** Reports the URL the router is on, and offers a back press to walk history. */
function Harness() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <span data-testid="address">{`${location.pathname}${location.search}`}</span>
      <button type="button" data-testid="back" onClick={() => navigate(-1)} />
    </>
  );
}

function address() {
  return screen.getByTestId("address").textContent;
}

function renderAt(...entries: string[]) {
  return render(
    <MemoryRouter initialEntries={entries} initialIndex={entries.length - 1}>
      <StudioRoutes />
      <Harness />
    </MemoryRouter>,
  );
}

describe("an old share link", () => {
  it("resolves once and redirects to the id URL, keeping the query", async () => {
    resolve.mockResolvedValue(record("file"));

    renderAt("/projects/a%20b/runs/x/output/clip%20%232.mp4?sort=name");

    await waitFor(() => {
      expect(address()).toBe(`/o/${NODE}?sort=name`);
    });
    // Once: the redirect `replace`s, so the legacy URL is not left in history
    // for back to re-enter and resolve again.
    expect(resolve).toHaveBeenCalledTimes(1);
    expect(resolve).toHaveBeenCalledWith("projects/a b/runs/x/output/clip #2.mp4");
  });

  it("does not stay in history, where back would walk into it again", async () => {
    // `replace` rather than a push. Without it, back re-enters the resolver,
    // which resolves and pushes forward again — a back button that cannot
    // escape the link somebody arrived on.
    resolve.mockResolvedValue(record("file"));

    renderAt(`/f/${PARENT}`, "/projects/a/runs/x/output/clip.mp4");
    await waitFor(() => {
      expect(address()).toBe(`/o/${NODE}`);
    });

    fireEvent.click(screen.getByTestId("back"));

    expect(address()).toBe(`/f/${PARENT}`);
    expect(resolve).toHaveBeenCalledTimes(1);
  });

  it("sends a folder to /f/ and a file to /o/, on the node's kind", async () => {
    resolve.mockResolvedValue(record("folder"));

    renderAt("/projects/a/runs/");

    await waitFor(() => {
      expect(address()).toBe(`/f/${NODE}`);
    });
  });

  it("says so when it resolves to nothing, instead of landing on the root", async () => {
    resolve.mockRejectedValue(new Error("projects/a/runs"));

    renderAt("/projects/a/runs/gone.mp4");

    expect(await screen.findByText(/does not lead anywhere/i)).toBeTruthy();
    expect(address()).toBe("/projects/a/runs/gone.mp4");
  });
});

describe("an id URL", () => {
  it("is left alone — no resolve, straight to the browser", async () => {
    renderAt(`/o/${NODE}`);

    expect(await screen.findByTestId("browse")).toBeTruthy();
    expect(resolve).not.toHaveBeenCalled();
    expect(address()).toBe(`/o/${NODE}`);
  });

  it("routes /f/ and the root to the browser too", async () => {
    renderAt(`/f/${NODE}`);
    expect(await screen.findByTestId("browse")).toBeTruthy();

    renderAt("/");
    expect(resolve).not.toHaveBeenCalled();
  });
});
