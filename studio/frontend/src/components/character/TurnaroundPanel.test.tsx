import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { CharacterRecord, ReferenceSpec } from "../../types";
import { TestProviders } from "../../test-providers";

vi.mock("../../apis/studio", () => ({
  draftTurnaround: vi.fn(),
  getProjects: vi.fn(),
  getReel: vi.fn(),
  getReferenceSpec: vi.fn(),
  getTree: vi.fn(),
  resolvePath: vi.fn(),
  getAsset: vi.fn().mockResolvedValue({ url: "https://signed/plate.png" }),
}));

import {
  draftTurnaround,
  getProjects,
  getReel,
  getReferenceSpec,
  getTree,
  resolvePath,
} from "../../apis/studio";
import { TurnaroundPanel } from "./TurnaroundPanel";

const draft = vi.mocked(draftTurnaround);
const tree = vi.mocked(getTree);
const reel = vi.mocked(getReel);
const projects = vi.mocked(getProjects);
const spec = vi.mocked(getReferenceSpec);
const resolve = vi.mocked(resolvePath);

const RECORD = { id: "char-1", root: "node-root", slug: "subject-a" } as CharacterRecord;

const SPEC: ReferenceSpec = {
  blocks: {},
  angles: [
    {
      id: "face_front", group: "face", prompt: "Front.",
      description: "Head and shoulders, front on.", tags: ["face"],
      illustration: "config/angle/face/front.png",
    },
    {
      id: "face_profile_right", group: "face", prompt: "Profile.",
      description: "Full profile.", tags: ["face"],
      illustration: "config/angle/face/profile-right.png",
    },
  ],
};

function file(id: string, name: string) {
  return {
    id, name, key: `seed/${name}`, size: 10, last_modified: null,
    kind: "image" as const, content_type: "image/jpeg", url: `https://x/${id}`,
  };
}

function show() {
  return render(
    <TestProviders>
      <MemoryRouter>
        <TurnaroundPanel record={RECORD} />
      </MemoryRouter>
    </TestProviders>,
  );
}

function ready(files = [file("node-a", "a.jpg"), file("node-b", "b.jpg")]) {
  tree.mockResolvedValue({
    prefix: "", sort: "name", breadcrumbs: [],
    folders: [{ id: "node-seed", name: "seed" }],
    files: [], counts: { folders: 1, files: 0, media: 0 },
  } as never);
  reel.mockResolvedValue({ prefix: "", sort: "name", items: files, total: files.length } as never);
  projects.mockResolvedValue([{ id: "proj-1", slug: "refs" }] as never);
  spec.mockResolvedValue(SPEC);
  // **The REAL shape: a node view, with no presigned url.** This returned a
  // `file()` — a listing entry, which carries one — and the panel crashed on
  // first render against the live API while every test passed. A fake more
  // capable than the service is the trap `fake_api.py` documents on the other
  // side of this repo, and it caught nobody here either.
  resolve.mockResolvedValue({ id: "node-plate", name: "front.png", kind: "file" });
}

/**
 * The package's `Select` is an ARIA combobox over a listbox, not a native
 * `<select>`, so it is opened and its option clicked. `fireEvent.change` does
 * nothing at all and the failure then reads as "the button did not fire".
 */
async function chooseProject(label = "refs") {
  // `find`, not `get`: the panel resolves the character's folders before it
  // renders anything, so the combobox does not exist on the first tick.
  fireEvent.click(await screen.findByRole("combobox", { name: /project/i }));
  fireEvent.click(await screen.findByRole("option", { name: label }));
}

/** Open one angle's picker and click a photograph inside it. */
async function pick(angleId: string, name: string) {
  const openers = await screen.findAllByText(/Pick photographs|Change/);
  const card = openers
    .map((b) => b.closest("div")?.parentElement)
    .find((c) => c?.textContent?.includes(angleId));
  fireEvent.click(
    [...(card?.querySelectorAll("button") ?? [])].find((b) =>
      /Pick photographs|Change/.test(b.textContent ?? ""),
    ) as HTMLButtonElement,
  );
  fireEvent.click(await screen.findByLabelText(new RegExp(`${angleId}: ${name}`)));
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("reads the seed pool RECURSIVELY, so filed photographs are pickable", async () => {
  /**
   * A seed pool is a tree the moment anyone files it — `original/`, `restored/`,
   * a folder per age — and a listing one level deep shows only what was never
   * filed. That blindness kept thirteen restored photographs out of a shoot's
   * view on the CLI side, silently.
   */
  ready();
  show();
  await waitFor(() => expect(reel).toHaveBeenCalled());
  expect(reel.mock.calls[0]![0]).toEqual({ node: "node-seed" });
});

it("shows the PLATE for each angle, which is what the orientation means", async () => {
  /**
   * An angle id says `face_profile_right` and its prompt spends a paragraph
   * defining that in terms of what is visible in frame. The picture says it at
   * a glance — and these are the plates a face angle stopped SENDING, which is
   * why showing them is free: an illustration outside the payload cannot
   * influence a render.
   */
  ready();
  show();
  await waitFor(() => expect(resolve).toHaveBeenCalled());
  expect(resolve.mock.calls.map((c) => c[0])).toContain("config/angle/face/front.png");
});

it("will not shoot until EVERY angle has photographs", async () => {
  /**
   * A shoot that half-happens because the twelfth angle was the one nobody
   * picked for is the failure this guards. The route refuses it too; refusing
   * here makes it visible before the click rather than as an error after it.
   */
  ready();
  show();
  await chooseProject();
  await pick("face_front", "a.jpg");

  expect(await screen.findByText(/1 angle\(s\) still need photographs/)).toBeTruthy();
  const button = screen.getByText(/Draft 2 angle\(s\)/) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
});

it("sends a SEPARATE list per angle", async () => {
  /**
   * A profile angle wants the profile photographs and a front angle does not.
   * One selection for all fourteen made the commonest correction impossible to
   * express.
   */
  ready();
  draft.mockResolvedValue({ drafted: [], failed: [] });
  show();
  await chooseProject();
  await pick("face_front", "a.jpg");
  await pick("face_profile_right", "b.jpg");
  fireEvent.click(screen.getByText(/Draft 2 angle\(s\)/));

  await waitFor(() => expect(draft).toHaveBeenCalled());
  expect(draft.mock.calls[0]![1].identity_by_angle).toEqual({
    face_front: ["node-a"],
    face_profile_right: ["node-b"],
  });
});

it("keeps pick ORDER within an angle, because a citation depends on it", async () => {
  ready();
  draft.mockResolvedValue({ drafted: [], failed: [] });
  show();
  await chooseProject();
  await pick("face_front", "b.jpg");
  fireEvent.click(await screen.findByLabelText(/face_front: a\.jpg/));
  await pick("face_profile_right", "a.jpg");
  fireEvent.click(screen.getByText(/Draft 2 angle\(s\)/));

  await waitFor(() => expect(draft).toHaveBeenCalled());
  expect(draft.mock.calls[0]![1].identity_by_angle!.face_front).toEqual([
    "node-b",
    "node-a",
  ]);
});

it("copies one angle's picks onto every angle as an explicit list", async () => {
  /**
   * A bulk EDIT, not a default. A default is a thing angles inherit, which is
   * the shape that made "this angle needs different pictures" impossible to
   * say; this writes the same explicit list onto each, and each can then change.
   */
  ready();
  draft.mockResolvedValue({ drafted: [], failed: [] });
  show();
  await chooseProject();
  await pick("face_front", "a.jpg");
  fireEvent.click(screen.getByText("Use for every angle"));
  fireEvent.click(screen.getByText(/Draft 2 angle\(s\)/));

  await waitFor(() => expect(draft).toHaveBeenCalled());
  expect(draft.mock.calls[0]![1].identity_by_angle).toEqual({
    face_front: ["node-a"],
    face_profile_right: ["node-a"],
  });
});

it("sends no fallback identity, so an unpicked angle cannot shoot anyway", async () => {
  ready();
  draft.mockResolvedValue({ drafted: [], failed: [] });
  show();
  await chooseProject();
  await pick("face_front", "a.jpg");
  fireEvent.click(screen.getByText("Use for every angle"));
  fireEvent.click(screen.getByText(/Draft 2 angle\(s\)/));

  await waitFor(() => expect(draft).toHaveBeenCalled());
  expect(draft.mock.calls[0]![1].identity).toEqual([]);
});

it("previews without recording anything", async () => {
  ready();
  draft.mockResolvedValue({
    preview: [{ angle: "face_front", model: "m",
                plan: { prompt: "A studio portrait.", params: {} }, sends: [] }],
    failed: [],
  });
  show();
  await chooseProject();
  await pick("face_front", "a.jpg");
  fireEvent.click(screen.getByText("Use for every angle"));
  fireEvent.click(screen.getByText("Preview"));

  await waitFor(() => expect(draft).toHaveBeenCalled());
  expect(draft.mock.calls[0]![1].preview).toBe(true);
  expect(await screen.findByText("A studio portrait.")).toBeTruthy();
});

it("says so when the character has no seed pool at all", async () => {
  ready();
  tree.mockResolvedValue({
    prefix: "", sort: "name", breadcrumbs: [], folders: [], files: [],
    counts: { folders: 0, files: 0, media: 0 },
  } as never);
  show();
  expect(await screen.findByText(/no seed pool/i)).toBeTruthy();
  expect(reel).not.toHaveBeenCalled();
});
