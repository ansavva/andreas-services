import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../apis/studio", () => ({
  getProjectInputs: vi.fn(),
  grabFrame: vi.fn(),
  getAsset: vi.fn(),
  getModels: vi.fn().mockResolvedValue({ models: {} }),
}));

import { getAsset, getProjectInputs, grabFrame } from "../apis/studio";
import { CreateBarProvider, useCreateBarState } from "../context/CreateBarContext";
import { TestProviders } from "../test-providers";
import { formatMoment, frameName, useFrameGrab } from "./useFrameGrab";

const inputs = vi.mocked(getProjectInputs);
const grab = vi.mocked(grabFrame);
const asset = vi.mocked(getAsset);

afterEach(cleanup);

/** One button that asks for the clip's first frame as a reference, and the bar read back. */
function Harness() {
  const { take, busy } = useFrameGrab();
  const state = useCreateBarState();
  return (
    <>
      <button
        onClick={() => void take({ node: "node-clip", name: "dance.mp4", kind: "object" }, "reference")}
      >
        First frame as reference
      </button>
      <output data-testid="busy">{busy ?? ""}</output>
      <output data-testid="bar">
        {state.attachments[state.kind]
          .map((held) => `${held.role}:${held.ref.pending ? "pending" : held.ref.node}:${held.ref.name}`)
          .join(",")}
      </output>
    </>
  );
}

/** The same, at a moment mid-clip, with the pending sentence read back too. */
function AtHarness() {
  const { take } = useFrameGrab();
  const state = useCreateBarState();
  return (
    <>
      <button
        onClick={() =>
          void take({ node: "node-clip", name: "dance.mp4", kind: "object" }, "start", 4.24)
        }
      >
        Frame at 4.24s as start
      </button>
      <output data-testid="bar">
        {state.attachments[state.kind]
          .map((held) =>
            held.ref.pending
              ? `${held.role}:pending:${held.ref.name}:${held.ref.pending}`
              : `${held.role}:${held.ref.node}:${held.ref.name}`,
          )
          .join(",")}
      </output>
    </>
  );
}

function mount(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <CreateBarProvider>
        <Harness />
      </CreateBarProvider>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
}

/**
 * The first frame of a clip, made by the worker and attached by the bar.
 *
 * The frame is a render job: `POST /api/renders` with `at: 0` into the
 * project's input pool, polled until it lands, then signed and attached in
 * the role asked for. What this checks is the order and the addresses — the
 * pool folder is the project's, the still is named for the clip, and what
 * reaches the bar is the FRAME's node, never the clip's.
 */
describe("the first frame of a clip", () => {
  beforeEach(() => {
    inputs.mockResolvedValue({ folder: "node-pool", inputs: [] });
    grab.mockResolvedValue({
      node: "node-frame",
      name: "dance-first.png",
      size: 1,
      content_type: "image/png",
    });
    asset.mockResolvedValue({ url: "https://signed/frame.png", kind: "image" } as never);
  });

  it("is on the bar at once as a placeholder, then becomes the frame when it lands", async () => {
    // The grab is held open so the placeholder can be seen before it resolves.
    let land!: (frame: Awaited<ReturnType<typeof grabFrame>>) => void;
    grab.mockReturnValue(new Promise((resolve) => (land = resolve)));
    mount("/p/proj-1");
    fireEvent.click(screen.getByRole("button", { name: "First frame as reference" }));

    // Before the worker has answered: the tile is there, waiting, named for
    // the frame it will become.
    await waitFor(() =>
      expect(screen.getByTestId("bar").textContent).toBe("reference:pending:dance-first.png"),
    );
    expect(inputs).toHaveBeenCalledWith("proj-1");

    land({ node: "node-frame", name: "dance-first.png", size: 1, content_type: "image/png" });
    await waitFor(() =>
      expect(screen.getByTestId("bar").textContent).toBe("reference:node-frame:dance-first.png"),
    );
    expect(grab).toHaveBeenCalledWith({
      node: "node-clip",
      at: 0,
      dest: "node-pool",
      name: "dance-first.png",
    });
    expect(asset).toHaveBeenCalledWith("node-frame");
    // No toast on success: the tile turning into the picture is the news.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("refuses without a project, before asking the worker for anything", async () => {
    window.localStorage.clear();
    mount("/favorites");
    fireEvent.click(screen.getByRole("button", { name: "First frame as reference" }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("Choose a project first"),
    );
    expect(grab).not.toHaveBeenCalled();
    expect(screen.getByTestId("bar").textContent).toBe("");
  });

  it("reports the worker's own failure and takes the placeholder back off", async () => {
    grab.mockRejectedValue(new Error("ffmpeg: moov atom not found"));
    mount("/p/proj-1");
    fireEvent.click(screen.getByRole("button", { name: "First frame as reference" }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("moov atom not found"),
    );
    expect(screen.getByTestId("bar").textContent).toBe("");
  });

  it("takes the frame at a moment, named and captioned for it", async () => {
    let land!: (frame: Awaited<ReturnType<typeof grabFrame>>) => void;
    grab.mockReturnValue(new Promise((resolve) => (land = resolve)));
    render(
      <MemoryRouter initialEntries={["/p/proj-1"]}>
        <CreateBarProvider>
          <AtHarness />
        </CreateBarProvider>
      </MemoryRouter>,
      { wrapper: TestProviders },
    );
    fireEvent.click(screen.getByRole("button", { name: "Frame at 4.24s as start" }));
    await waitFor(() =>
      expect(screen.getByTestId("bar").textContent).toBe(
        "start:pending:dance-at-0m04.2s.png:Taking the frame at 0:04.2 of dance.mp4…",
      ),
    );
    land({ node: "node-frame", name: "dance-at-0m04.2s.png", size: 1, content_type: "image/png" });
    await waitFor(() => expect(screen.getByTestId("bar").textContent).toContain("node-frame"));
    // Rounded to the tenth the transport shows; ffmpeg seeks to the nearest frame.
    expect(grab).toHaveBeenCalledWith({
      node: "node-clip",
      at: 4.2,
      dest: "node-pool",
      name: "dance-at-0m04.2s.png",
    });
  });

  it("names the still for the clip and the moment", () => {
    expect(frameName("dance.mp4", 0)).toBe("dance-first.png");
    expect(frameName("a.b.mov", 0)).toBe("a.b-first.png");
    expect(frameName(undefined, 0)).toBe("clip-first.png");
    expect(frameName("dance.mp4", 4.2)).toBe("dance-at-0m04.2s.png");
    expect(frameName("dance.mp4", 75)).toBe("dance-at-1m15.0s.png");
    expect(formatMoment(4.24)).toBe("0:04.2");
    expect(formatMoment(75)).toBe("1:15.0");
  });
});
