import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { AttachRef, Attachment } from "../../context/CreateBarContext";
import { TestProviders } from "../../test-providers";
import type { ModelEntry } from "../../types";

vi.mock("../../apis/studio", () => ({
  getCharacters: vi.fn(),
  getCharacterSelection: vi.fn(),
  getProjectInputs: vi.fn(),
  getRuns: vi.fn(),
}));

import { getCharacterSelection, getCharacters, getProjectInputs, getRuns } from "../../apis/studio";
import { CreateDrawer } from "./CreateDrawer";
import { sendsOf } from "./roles";

const PROJECT = "proj-0001";
const CHARACTER = "char-0001";

const STILL: ModelEntry = {
  key: "still-model",
  model: "vendor/still-model",
  kind: "image",
  skill: "studio-media-still-model",
  images: { refs: "input_images", start: null, end: null },
};
const MOTION: ModelEntry = {
  key: "motion-model",
  model: "vendor/motion-model",
  kind: "video",
  skill: "studio-media-motion-model",
  images: { refs: "reference_images", start: "start_image", end: "end_image" },
};

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getCharacters).mockResolvedValue([
    { id: CHARACTER, name: "jason", hero: null, counts: { default: 1, files: 1 }, updated: "" },
  ]);
  vi.mocked(getCharacterSelection).mockResolvedValue({
    selection: [
      {
        slot: 1,
        node: "node-seed",
        name: "seed-01.jpg",
        group: "face",
        description: null,
        url: "https://example.invalid/seed.jpg",
      },
    ],
    cap: null,
    source: "default",
  });
  vi.mocked(getProjectInputs).mockResolvedValue({
    folder: "node-input",
    inputs: [
      {
        position: 1,
        id: "node-coat",
        name: "coat-ref.jpg",
        size: 1,
        content_type: "image/jpeg",
        url: "https://example.invalid/coat.jpg",
      },
    ],
  });
  vi.mocked(getRuns).mockResolvedValue({
    runs: [
      {
        id: "run-7f3a0000",
        lib: "lib-1",
        project: PROJECT,
        status: "succeeded",
        kind: "image",
        engine: null,
        model: "vendor/still-model",
        created: "2026-09-01T00:00:00Z",
        updated: null,
        submitted: null,
        completed: null,
        cost: null,
        error: null,
        plan: null,
        characters: [],
        cast: [],
        sends: [],
        outputs: [
          { node: "node-out-1", name: "out-1.png", content_type: "image/png", url: "https://example.invalid/1.png" },
          { node: "node-out-2", name: "out-2.mp4", content_type: "video/mp4", url: "https://example.invalid/2.mp4" },
        ],
        thumb: null,
      },
    ],
    cursor: null,
  } as never);
});

function open(attached: string[] = []) {
  const onAttach = vi.fn<(ref: AttachRef) => void>();
  render(
    <CreateDrawer
      projectId={PROJECT}
      cast={[{ id: CHARACTER, name: "jason" }]}
      attached={new Set(attached)}
      onAttach={onAttach}
      onClose={vi.fn()}
    />,
    { wrapper: TestProviders },
  );
  return onAttach;
}

it("opens on the cast, draws a dashed placeholder for a character with no picture, and attaches an identity image as a reference send", async () => {
  const onAttach = open();

  const tab = screen.getByRole("tab", { name: /jason · identity/ });
  expect(tab.getAttribute("aria-selected")).toBe("true");
  expect(tab.querySelector("img")).toBeNull();
  expect(tab.querySelector(".border-dashed")).toBeTruthy();

  fireEvent.click(await screen.findByRole("button", { name: "Attach seed-01.jpg" }));
  const ref = onAttach.mock.calls[0]![0];
  expect(ref).toEqual({
    node: "node-seed",
    url: "https://example.invalid/seed.jpg",
    name: "seed-01.jpg",
    kind: "character",
    character: CHARACTER,
  });
  const sends = sendsOf([{ ref, role: "reference" }] as Attachment[], STILL);
  expect(sends).toEqual([{ field: "input_images", role: "reference", node: "node-seed" }]);
});

it("the input pool attaches as the image an edit starts from", async () => {
  const onAttach = open();
  fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
  fireEvent.click(await screen.findByRole("button", { name: "Attach coat-ref.jpg" }));

  const ref = onAttach.mock.calls[0]![0];
  expect(ref).toMatchObject({ node: "node-coat", kind: "input-pool" });
  // A still model has no single-image field, so an edit lands on its reference list.
  expect(sendsOf([{ ref, role: "input" }] as Attachment[], STILL)).toEqual([
    { field: "input_images", role: "input", node: "node-coat" },
  ]);
});

it("the project's outputs offer only pictures, numbered by output, and animate onto the start frame", async () => {
  const onAttach = open(["node-out-1"]);
  fireEvent.click(screen.getByRole("tab", { name: "This project's outputs" }));

  const tile = await screen.findByRole("button", { name: "Attach out-1.png" });
  // Already on the bar: pressed, not offered twice.
  expect(tile.getAttribute("aria-pressed")).toBe("true");
  expect(screen.queryByRole("button", { name: "Attach out-2.mp4" })).toBeNull();
  expect(screen.getByText("run 7f3a · out-1.png")).toBeTruthy();

  fireEvent.click(tile);
  const ref = onAttach.mock.calls[0]![0];
  expect(ref).toMatchObject({ node: "node-out-1", kind: "run", run: "run-7f3a0000", output: 1 });
  expect(sendsOf([{ ref, role: "start" }] as Attachment[], MOTION)).toEqual([
    { field: "start_image", role: "start", node: "node-out-1" },
  ]);
  // A role the model has no field for is dropped rather than sent somewhere.
  expect(sendsOf([{ ref, role: "start" }] as Attachment[], STILL)).toEqual([]);
});
