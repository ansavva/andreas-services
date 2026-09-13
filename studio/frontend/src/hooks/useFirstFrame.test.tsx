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
import { firstFrameName, useFirstFrame } from "./useFirstFrame";

const inputs = vi.mocked(getProjectInputs);
const grab = vi.mocked(grabFrame);
const asset = vi.mocked(getAsset);

afterEach(cleanup);

/** One button that asks for the clip's first frame as a reference, and the bar read back. */
function Harness() {
  const { take, busy } = useFirstFrame();
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
          .map((held) => `${held.role}:${held.ref.node}:${held.ref.name}`)
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

  it("goes into the route's project's input pool and lands on the bar as the role", async () => {
    mount("/p/proj-1");
    fireEvent.click(screen.getByRole("button", { name: "First frame as reference" }));

    await waitFor(() =>
      expect(screen.getByTestId("bar").textContent).toBe("reference:node-frame:dance-first.png"),
    );
    expect(inputs).toHaveBeenCalledWith("proj-1");
    expect(grab).toHaveBeenCalledWith({
      node: "node-clip",
      at: 0,
      dest: "node-pool",
      name: "dance-first.png",
    });
    expect(asset).toHaveBeenCalledWith("node-frame");
    // Said once it is there, and the toast names the clip it came from.
    const region = await screen.findByRole("region", { name: "Notifications" });
    expect(region.textContent).toContain("First frame of dance.mp4");
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

  it("reports the worker's own failure and attaches nothing", async () => {
    grab.mockRejectedValue(new Error("ffmpeg: moov atom not found"));
    mount("/p/proj-1");
    fireEvent.click(screen.getByRole("button", { name: "First frame as reference" }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("moov atom not found"),
    );
    expect(screen.getByTestId("bar").textContent).toBe("");
  });

  it("names the still for the clip", () => {
    expect(firstFrameName("dance.mp4")).toBe("dance-first.png");
    expect(firstFrameName("a.b.mov")).toBe("a.b-first.png");
    expect(firstFrameName(undefined)).toBe("clip-first.png");
  });
});
