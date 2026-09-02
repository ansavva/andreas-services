import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { CharacterRecord, ReferenceSpec } from "../../types";
import { TestProviders } from "../../test-providers";

vi.mock("../../apis/studio", () => ({
  draftTurnaround: vi.fn(),
  getProject: vi.fn(),
  getProjects: vi.fn(),
  getMedia: vi.fn(),
  getReferenceSpec: vi.fn(),
  getFolder: vi.fn(),
  resolvePath: vi.fn(),
  getAsset: vi.fn().mockResolvedValue({ url: "https://signed/plate.png" }),
}));

import {
  draftTurnaround,
  getProject,
  getProjects,
  getMedia,
  getReferenceSpec,
  getFolder,
  resolvePath,
} from "../../apis/studio";
import { TurnaroundPanel } from "./TurnaroundPanel";

const draft = vi.mocked(draftTurnaround);
const tree = vi.mocked(getFolder);
const reel = vi.mocked(getMedia);
const projects = vi.mocked(getProjects);
const projectRecord = vi.mocked(getProject);
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
  projectRecord.mockResolvedValue({ id: "proj-1", slug: "refs", root: "node-proj" } as never);
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

/**
 * Select an angle's card and click a photograph in the pool.
 *
 * **The card itself is the control.** It was a `Pick photographs` button inside
 * the card — a second thing to aim at for a decision the card already stands
 * for, reading as "open something" rather than "this one".
 */
async function pick(angleId: string, name: string) {
  fireEvent.click(
    await screen.findByRole("button", { name: `Pick photographs for ${angleId}` }),
  );
  fireEvent.click(await screen.findByLabelText(new RegExp(`${angleId}: ${name}`)));
}

/**
 * The call that DRAFTS.
 *
 * The panel also previews on its own, on a debounce, so the first call to this
 * mock is very often an assembly nobody asked for — asserting on `calls[0]`
 * would read the preview's body and pass or fail for the wrong reason.
 */
function drafting() {
  return draft.mock.calls.find((call) => !call[1].preview)!;
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

  await waitFor(() => expect(drafting()).toBeTruthy());
  expect(drafting()[1].identity_by_angle).toEqual({
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

  await waitFor(() => expect(drafting()).toBeTruthy());
  expect(drafting()[1].identity_by_angle!.face_front).toEqual([
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

  await waitFor(() => expect(drafting()).toBeTruthy());
  expect(drafting()[1].identity_by_angle).toEqual({
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

  await waitFor(() => expect(drafting()).toBeTruthy());
  expect(drafting()[1].identity).toEqual([]);
});

it("assembles the prompts WITHOUT being asked, and before a project is chosen", async () => {
  /**
   * **There was a Preview button and it was the wrong shape twice over.** What
   * an angle would say is the thing that tells you whether your choices are
   * right, so putting it behind a click meant deciding first and reading
   * afterwards — and the button was disabled until a project was chosen and all
   * fourteen angles had photographs, which is the point at which there is
   * nothing left to decide.
   */
  ready();
  draft.mockResolvedValue({
    preview: [{ angle: "face_front", model: "m",
                plan: { prompt: "A studio portrait.", params: {} }, sends: [] }],
    failed: [],
  });
  show();

  // No project, no photographs, no click.
  expect(await screen.findByText("A studio portrait.")).toBeTruthy();
  expect(draft.mock.calls[0]![1].preview).toBe(true);
  expect(draft.mock.calls[0]![1].project).toBeUndefined();
  expect(screen.queryByText("Preview")).toBeNull();
});

it("keeps showing the prompts when an assembly fails", async () => {
  /**
   * A preview runs on every change, so a network blip mid-click would otherwise
   * replace the panel with a red box for something nobody did.
   */
  ready();
  draft.mockRejectedValue(new Error("boom"));
  show();
  await screen.findAllByText(/face_front/);
  await waitFor(() => expect(draft).toHaveBeenCalled());
  expect(screen.queryByText(/The turnaround was refused/)).toBeNull();
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

it("removes one photograph from a card, where the mistake is visible", async () => {
  /**
   * It was only removable in the pool, by finding the same photograph among
   * fifty and clicking it again — so the place that shows you the wrong picture
   * was not the place you could take it off.
   */
  ready();
  draft.mockResolvedValue({ drafted: [], failed: [] });
  show();
  await chooseProject();
  await pick("face_front", "a.jpg");
  await pick("face_front", "b.jpg");
  // Every angle needs photographs before the panel will draft at all.
  await pick("face_profile_right", "a.jpg");

  fireEvent.click(screen.getByLabelText("Remove a.jpg from face_front"));
  fireEvent.click(screen.getByText(/Draft 2 angle\(s\)/));

  await waitFor(() => expect(drafting()).toBeTruthy());
  expect(drafting()[1].identity_by_angle!.face_front).toEqual(["node-b"]);
});

it("opens a photograph full size on a modified click instead of picking it", async () => {
  /**
   * These are thumbnails of the only pictures that will say who this person is,
   * and the decision is made by eye — so looking at one properly, without
   * leaving the screen you are choosing on, is part of the job.
   */
  ready();
  const open = vi.spyOn(window, "open").mockReturnValue(null);
  show();
  await chooseProject();
  fireEvent.click(
    await screen.findByRole("button", { name: "Pick photographs for face_front" }),
  );

  const thumb = await screen.findByLabelText(/face_front: a\.jpg/);
  fireEvent.click(thumb, { metaKey: true });

  expect(open).toHaveBeenCalledWith("https://x/node-a", "_blank", "noopener,noreferrer");
  // And it did NOT become a pick.
  expect(screen.getAllByText("No photographs yet.").length).toBeGreaterThan(0);
  open.mockRestore();
});

it("shoots the ANCHOR alone first, then chains the rest off its render", async () => {
  /**
   * **A turnaround is not N independent shoots.** Every hand-authored
   * production set was made as one anchor and then the rest chained off it,
   * each binding the anchor's render as `[Image1]` and each told to take the
   * wardrobe and the background from it. Shot independently the same prompts
   * produced a different shirt every time, because nothing in them held it.
   *
   * Phase one drafts the anchor ALONE: drafting all fourteen and shooting the
   * anchor out of that pile would leave thirteen payloads written against a
   * render that does not exist yet, and a payload is the thing a person
   * approves.
   */
  ready();
  draft.mockResolvedValue({ drafted: [], failed: [] });
  show();
  await chooseProject();
  await pick("face_front", "a.jpg");

  const anchors = await screen.findAllByText("Make anchor");
  fireEvent.click(anchors[0]!);
  fireEvent.click(await screen.findByText("Draft the anchor"));

  await waitFor(() => expect(drafting()).toBeTruthy());
  expect(drafting()[1].angles).toEqual(["face_front"]);
  expect(drafting()[1].anchor).toBeUndefined();
});

it("binds the chosen render for the REST once an anchor image is picked", async () => {
  ready();
  reel.mockResolvedValue({
    prefix: "", sort: "newest", total: 1,
    items: [file("node-render", "anchor.png")],
  } as never);
  draft.mockResolvedValue({ drafted: [], failed: [] });
  show();
  await chooseProject();

  fireEvent.click((await screen.findAllByText("Make anchor"))[0]!);
  fireEvent.click(await screen.findByLabelText("Anchor: anchor.png"));
  fireEvent.click(await screen.findByText(/Draft 1 angle\(s\)/));

  await waitFor(() => expect(drafting()).toBeTruthy());
  // The anchor angle is not reshot, and the rest carry the render.
  expect(drafting()[1].angles).toEqual(["face_profile_right"]);
  expect(drafting()[1].anchor).toBe("node-render");
});

it("an anchored pass needs no fresh picks, because the anchor IS the identity", async () => {
  ready();
  reel.mockResolvedValue({
    prefix: "", sort: "newest", total: 1,
    items: [file("node-render", "anchor.png")],
  } as never);
  show();
  await chooseProject();
  fireEvent.click((await screen.findAllByText("Make anchor"))[0]!);
  fireEvent.click(await screen.findByLabelText("Anchor: anchor.png"));

  const button = (await screen.findByText(/Draft 1 angle\(s\)/)) as HTMLButtonElement;
  expect(button.disabled).toBe(false);
});
