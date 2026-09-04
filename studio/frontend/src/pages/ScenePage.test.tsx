import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { SceneRecord, Shot } from "../types";

// The header pulls in auth and the library context and says nothing this file
// asserts on. Everything else is the real component.

// `getProject` is here for the breadcrumb, which reads the project's name so
// the trail says where the scene sits rather than just "Project".
vi.mock("../apis/studio", () => ({
  getScene: vi.fn(),
  patchScene: vi.fn(),
  patchShot: vi.fn(),
  deleteScene: vi.fn(),
  getProject: vi.fn(),
}));

import { deleteScene, getProject, getScene, patchScene, patchShot } from "../apis/studio";
import { ScenePage } from "./ScenePage";
import { TestProviders } from "../test-providers";

const read = vi.mocked(getScene);
const save = vi.mocked(patchShot);
const project = vi.mocked(getProject);
const destroy = vi.mocked(deleteScene);

const ID = "scene-0001";

function shot(over: Partial<Shot> = {}): Shot {
  return {
    id: "shot-01",
    order: 10,
    prompt: "",
    run: null,
    panel: null,
    beat: "The whistle comes off",
    status: "planned",
    continues: false,
    panels: [],
    motion: {
      prompt: "he lifts the lanyard over his head",
      duration: 6,
      model: "kling",
    },
    ...over,
  };
}

function record(over: Partial<SceneRecord> = {}): SceneRecord {
  return {
    id: ID,
    project: "proj-0001",
    name: "Light flex",
    status: "planned",
    movies: [],
    created: "2026-08-25T00:00:00Z",
    folder: "node-folder",
    output: null,
    shots: [shot()],
    ...over,
  };
}

/** Where the router ended up, so a navigation can be asserted on. */
let landed = "";

function Land() {
  const location = useLocation();
  landed = `${location.pathname}${location.search}`;
  return <div>landed</div>;
}

function draw(scene: SceneRecord) {
  read.mockResolvedValue(scene);
  project.mockResolvedValue({
    id: "proj-0001",
    name: "A project",
  } as never);
  landed = "";
  return render(
    <MemoryRouter initialEntries={[`/s/${ID}`]}>
      <Routes>
        <Route path="/s/:sceneId" element={<ScenePage />} />
        {/* The board opens frames in the viewer now rather than in a drawer of
            its own, so what a click does is *navigate* — this stands in for the
            screen it navigates to. */}
        <Route path="/o/:nodeId" element={<Land />} />
        {/* Opening a RUN is a different navigation from opening an object, and
            the board now does both — every tile links to the run behind it. */}
        <Route path="/p/:projectId/r/:runId" element={<Land />} />
        {/* Where deleting the scene lands — the project it belongs to. */}
        <Route path="/p/:projectId" element={<Land />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("draws a shot by its beat rather than its prompt", async () => {
  // The beat is the board caption — one line a person can scan a scene by. The
  // page showed `prompt`, which on a storyboarded scene is empty, so every shot
  // rendered as a blank row.
  draw(record());

  expect(await screen.findByText("The whistle comes off")).toBeTruthy();
  expect(screen.getByText("6s")).toBeTruthy();
  expect(screen.getAllByText("kling").length).toBeGreaterThan(0);
});

it("draws a boarded panel as its image and an unboarded one as a placeholder", async () => {
  // **A placeholder is the normal state of a board**, not an error: a panel is
  // planned before it is rendered, and the gap is what a person is looking for
  // when they ask what still needs shooting.
  draw(
    record({
      shots: [
        shot({
          panels: [
            {
              n: 1,
              role: "start",
              prompt: "square to camera",
              node: "node-a",
              image: {
                node: "node-a",
                name: "panel-01.png",
                url: "https://example/panel-01.png",
              },
            },
            { n: 2, role: "sample", prompt: "the peak of the move" },
          ],
        }),
      ],
    }),
  );

  await screen.findByText("The whistle comes off");
  const boarded = screen.getAllByRole("button", {
    name: /square to camera/i,
  })[0]!;
  expect(
    within(boarded).getByRole("presentation", { hidden: true }),
  ).toBeTruthy();
  // The unboarded one carries its prompt instead of a picture, and is not a
  // link to a node that does not exist.
  expect(screen.getAllByText("the peak of the move").length).toBeGreaterThan(0);
  expect(
    screen.queryByRole("button", { name: /the peak of the move/i }),
  ).toBeNull();
});

it("labels a sample as a sample, because it is the one panel that binds to nothing", async () => {
  draw(
    record({
      shots: [
        shot({
          panels: [
            { n: 1, role: "sample", prompt: "what the shot should look like" },
          ],
        }),
      ],
    }),
  );

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("Samples")).toBeTruthy();
  expect(screen.getByText("not sent")).toBeTruthy();
  expect(screen.getByText("what the shot should look like")).toBeTruthy();
});

it("leads the strip with the frame the shot opens on", async () => {
  // The handoff outranks any panel composed for the same moment — a cut is only
  // seamless from the literal last frame of the shot before it — so the board
  // has to show which image actually opens the shot.
  draw(
    record({
      shots: [
        shot({
          continues: true,
          opens_on: {
            node: "node-handoff",
            frame: {
              node: "node-handoff",
              name: "last.png",
              url: "https://example/last.png",
            },
          },
        }),
      ],
    }),
  );

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("Start")).toBeTruthy();
  expect(screen.getByText("handoff")).toBeTruthy();
});

it("flags a panel whose prompt moved on after the image was rendered", async () => {
  draw(
    record({
      shots: [
        shot({
          panels: [
            {
              n: 1,
              role: "start",
              prompt: "reworded since",
              node: "node-a",
              stale: true,
              image: {
                node: "node-a",
                name: "panel-01.png",
                url: "https://example/panel-01.png",
              },
            },
          ],
        }),
      ],
    }),
  );

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("stale")).toBeTruthy();
});

it("gives one answer to whether a shot has been shot, not two", async () => {
  // `status` is computed from the plan and `not rendered` was drawn from `run`
  // being null, so a shot could carry `rendered` and `not rendered` side by side.
  draw(record({ shots: [shot({ status: "rendered", run: null })] }));

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("rendered")).toBeTruthy();
  expect(screen.queryByText("not rendered")).toBeNull();
});

it("still says a shot is unrendered when it has no status to say it", async () => {
  // The pre-storyboard shape: assembled from bare runs, no plan behind it.
  draw(record({ shots: [shot({ status: undefined, run: null })] }));

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("not rendered")).toBeTruthy();
});

it("shows the motion prompt without making anyone click for it", async () => {
  // Reading the prompts is what this page is for — a storyboard is judged on its
  // wording before any shot is bought. It was behind a `Collapsible`, whose
  // panel reveals with a `grid-rows-[0fr]`-to-`[1fr]` transition that never
  // progresses: the trigger flipped `aria-expanded` and the panel opened to a
  // zero-height row, so the prompt read as blank.
  draw(
    record({
      shots: [
        shot({ motion: { prompt: '{ "subject": "the man, unchanged" }' } }),
      ],
    }),
  );

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("the man, unchanged")).toBeTruthy();
  // Nothing to press, so nothing to be stuck closed.
  expect(screen.queryByRole("button", { name: /motion prompt/i })).toBeNull();
});

const PROMPT = JSON.stringify(
  {
    subject: "The man from the source image, unchanged",
    action: "He lifts the lanyard over his head",
    camera: {
      shot: "wide",
      movement: "static/hold",
      lens_mm: 50,
      speed: "locked off",
    },
    style: "Photorealistic live-action",
    avoid: "changing face, cuts",
    dialogue: ["a key this form does not show"],
  },
  null,
  2,
);

it("reads the motion prompt as fields, not as JSON", async () => {
  // **Back to where it started, and now the run screen agrees.** It reached the
  // page as 1.4 kB of escaped JSON, which is not showing anyone their prompt.
  // This is studio's OWN document with a schema `studio prompt` validates — the
  // run page's "never parsed" rule is about the PROVIDER's payload, whose shape
  // studio does not own, and applying it here was wrong.
  //
  // It was briefly drawn as the document to match the run screen; the
  // convergence went the other way in the end, and `RunPlan` renders these same
  // fields. Both screens, one rendering.
  draw(record({ shots: [shot({ motion: { prompt: PROMPT, duration: 6 } })] }));

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("Subject")).toBeTruthy();
  expect(
    screen.getByText("The man from the source image, unchanged"),
  ).toBeTruthy();
  expect(
    screen.getByText("wide · static/hold · 50mm · locked off"),
  ).toBeTruthy();
  expect(screen.queryByText(/^\{$/)).toBeNull();
});

it("falls back to the raw text when the prompt is prose rather than JSON", async () => {
  // A plain prose prompt is legal on every engine here.
  draw(
    record({
      shots: [shot({ motion: { prompt: "he lifts the lanyard, slowly" } })],
    }),
  );

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("he lifts the lanyard, slowly")).toBeTruthy();
});

it("saves an edit as both the document and the string the model is given", async () => {
  save.mockResolvedValue({} as Shot);
  draw(record({ shots: [shot({ motion: { prompt: PROMPT, duration: 6 } })] }));
  await screen.findByText("The whistle comes off");

  fireEvent.click(screen.getByRole("button", { name: /^edit the prompt$/i }));
  fireEvent.change(screen.getByLabelText("Action"), {
    target: { value: "He ducks through it" },
  });
  fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

  await waitFor(() => expect(save).toHaveBeenCalled());
  const call = save.mock.calls[0];
  if (!call) throw new Error("patchShot was not called");
  const [, shotId, body] = call;
  expect(shotId).toBe("shot-01");
  const sent = JSON.parse((body.motion as { prompt: string }).prompt);
  expect(sent.action).toBe("He ducks through it");
  // Everything else survives, including a key this form never renders.
  expect(sent.subject).toBe("The man from the source image, unchanged");
  expect(sent.camera.lens_mm).toBe(50);
  expect(sent.dialogue).toEqual(["a key this form does not show"]);
  // Order is the document's, not the form's.
  expect(Object.keys(sent)).toEqual([
    "subject",
    "action",
    "camera",
    "style",
    "avoid",
    "dialogue",
  ]);
  // The parsed document travels alongside the string the model receives.
  expect((body.motion as { prompt_json: unknown }).prompt_json).toEqual(sent);
});

it("keeps the edit open and says why when the save fails", async () => {
  save.mockRejectedValue(new Error("shot-01 is gone"));
  draw(record({ shots: [shot({ motion: { prompt: PROMPT } })] }));
  await screen.findByText("The whistle comes off");

  fireEvent.click(screen.getByRole("button", { name: /^edit the prompt$/i }));
  fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

  expect(await screen.findByText("shot-01 is gone")).toBeTruthy();
  expect(screen.getByRole("button", { name: /^save$/i })).toBeTruthy();
});

it("says what the shot will send, and what it will not", async () => {
  // The two lists were both invisible: what the video engine receives, and what
  // a panel pulls to render the still. Conflating them is what made "why aren't
  // you showing me the images you intend to send" a fair question.
  draw(
    record({
      shots: [
        shot({
          continues: true,
          opens_on: {
            node: "node-tail",
            frame: {
              node: "node-tail",
              name: "tail.png",
              url: "https://example/tail.png",
            },
          },
          panels: [
            {
              n: 1,
              role: "start",
              prompt: "the opening",
              references: { characters: ["subject-a"] },
            },
            { n: 2, role: "sample", prompt: "the peak" },
          ],
        }),
      ],
    }),
  );

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("Start")).toBeTruthy();
  expect(screen.getByText("References")).toBeTruthy();
  // The handoff takes the start slot and the panel composed for it is demoted.
  expect(screen.getByText("handoff")).toBeTruthy();
  expect(screen.getByText("demoted")).toBeTruthy();
  // A sample is shown and labelled as never reaching the model.
  expect(screen.getByText("not sent")).toBeTruthy();
  // Not bracketed, so it says so rather than leaving the row blank.
  // Chained, so there is no End row at all — the mode is stated once at the top.
  expect(screen.queryByText("End")).toBeNull();
  expect(screen.getByText("chained")).toBeTruthy();
  // Every slot is drawn as a tile, and the sample says it never reaches the model.
  expect(screen.getByText("Samples")).toBeTruthy();
});

it("says a start frame is pending rather than showing an empty slot", async () => {
  draw(
    record({ shots: [shot({ continues: true, opens_on: null, panels: [] })] }),
  );

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("awaits previous shot")).toBeTruthy();
});

it("shows the setting once, not once per panel", async () => {
  draw(record({ setting: "A plain mid-grey seamless studio cyclorama." }));

  expect(
    await screen.findByText("A plain mid-grey seamless studio cyclorama."),
  ).toBeTruthy();
});

it("totals the planned runtime, which is what the scene will cost to shoot", async () => {
  draw(
    record({
      shots: [
        shot({
          id: "shot-01",
          order: 10,
          motion: { prompt: "a", duration: 6 },
        }),
        shot({
          id: "shot-02",
          order: 20,
          motion: { prompt: "b", duration: 12 },
        }),
      ],
    }),
  );

  expect(await screen.findByText(/18s planned/)).toBeTruthy();
});

it("still draws a scene assembled from bare runs, which has no storyboard at all", async () => {
  // `scenes assemble --shot <runref>` appends runs directly and a board stays
  // optional, so the pre-storyboard shape has to keep rendering.
  draw(
    record({
      shots: [
        {
          id: "shot-01",
          order: 10,
          prompt: "wide on the touchline",
          run: "run-abc",
          panel: null,
        },
      ],
    }),
  );

  expect(await screen.findByText("wide on the touchline")).toBeTruthy();
  // **`Open its run` is gone, and this shot is why it could not just be
  // deleted.** A scene cut from bare runs has a `run` per shot and no
  // storyboard, so nothing expands `runs` — the shot synthesises one row so the
  // single remaining route to a run still reaches it here.
  const tab = await screen.findByRole("tab", { name: /^Runs/ });
  expect(tab.textContent).toContain("1");
  fireEvent.click(tab);
  // The role is what the synthesised row carries, and it is what proves the row
  // rendered at all rather than the tab merely existing.
  await waitFor(() => expect(screen.getByText("clip")).toBeTruthy());
});

it("shows an End row only when the scene brackets its shots", async () => {
  // A chained scene has no end frames anywhere, so a row reading "none" on every
  // card is a column of nothing. The mode belongs at the top, once.
  draw(
    record({
      shots: [
        shot({
          panels: [
            { n: 1, role: "start", prompt: "opens here" },
            { n: 2, role: "end", prompt: "lands here" },
          ],
        }),
      ],
    }),
  );

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("bracketed")).toBeTruthy();
  expect(screen.getByText("End")).toBeTruthy();
});

it("draws a reference the plan names as a thumbnail, not as a filename", async () => {
  // "plus <name>" said nothing about which pictures are going, and which pictures
  // are going is the whole question. The API resolves the block to images.
  draw(
    record({
      shots: [
        shot({
          motion: {
            prompt: "x",
            references: { characters: ["subject-a"], pick: "front.png" },
            reference_assets: [
              {
                node: "node-ref",
                name: "front.png",
                url: "https://example/front.png",
              },
            ],
          },
        }),
      ],
    }),
  );

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("reference")).toBeTruthy();
  expect(screen.getByRole("button", { name: /front\.png/i })).toBeTruthy();
});

it("opens a frame in the viewer, in the scene's own context", async () => {
  // A tile is 80px because a scene holds twenty-odd of them; judging a pose
  // needs the picture at a size you can read.
  //
  // This used to open a drawer, on the reasoning that navigating away "would
  // lose your place on the board". The viewer is a real screen now: `?in=scene`
  // makes its neighbours the storyboard rather than some folder, back returns
  // to the board, and unlike a drawer the frame can be linked to and made
  // fullscreen.
  draw(
    record({
      shots: [
        shot({
          panels: [
            {
              n: 1,
              role: "start",
              prompt: "square to camera",
              node: "node-a",
              image: {
                node: "node-a",
                name: "shot-01-p1.jpeg",
                url: "https://example/a.jpeg",
              },
            },
          ],
        }),
      ],
    }),
  );
  await screen.findByText("The whistle comes off");

  fireEvent.click(screen.getByRole("button", { name: /square to camera/i }));

  await screen.findByText("landed");
  expect(landed).toBe(`/o/node-a?in=${encodeURIComponent(`scene:${ID}`)}`);
});

it("does not offer a viewer for a frame that has not been rendered", async () => {
  draw(
    record({
      shots: [shot({ panels: [{ n: 1, role: "start", prompt: "not yet" }] })],
    }),
  );

  await screen.findByText("The whistle comes off");
  expect(screen.queryByRole("button", { name: /not yet/i })).toBeNull();
});

/**
 * The way back up. A scene knew nothing of the movie that cut it, because a
 * movie held its scenes in a JSON list and no index addresses into one.
 */
it("names the movie that cut this scene", async () => {
  draw(
    record({ movies: [{ id: "movie-3", name: "The cut" }] }),
  );

  expect(await screen.findByText("Cut into")).toBeTruthy();
  expect(screen.getByRole("button", { name: "The cut" })).toBeTruthy();
});

it("says nothing when the scene has not been cut into anything", async () => {
  draw(record());

  await screen.findByText("The whistle comes off");
  expect(screen.queryByText("Cut into")).toBeNull();
});

// ─────────────── the links out, and the takes kept ───────────────
//
// Every picture on this board came from a run and none of them said which. A
// sample that came out wrong was a dead end: the run holds the prompt, the
// payload and the approval that produced it, and there was no way to reach it.

it("links a sample panel to the run that rendered it", async () => {
  draw(
    record({
      shots: [
        shot({
          panels: [
            {
              n: 1,
              role: "sample",
              prompt: "the peak of this beat",
              run: "run-sample",
              node: "node-s",
              image: { node: "node-s", name: "s.png", url: "https://x/s.png" },
            },
          ],
        }),
      ],
    }),
  );

  const samples = await screen.findByText("Samples");
  const row = samples.parentElement as HTMLElement;
  fireEvent.click(within(row).getByRole("button", { name: "Run" }));
  await waitFor(() => expect(landed).toContain("run-sample"));
});

it("links the handoff frame to the run it came out of", async () => {
  draw(
    record({
      shots: [
        shot({
          continues: true,
          opens_on: {
            node: "node-h",
            from_run: "run-previous",
            frame: { node: "node-h", name: "h.png", url: "https://x/h.png" },
          },
        }),
      ],
    }),
  );

  const start = await screen.findByText("Start");
  const row = start.parentElement as HTMLElement;
  fireEvent.click(within(row).getByRole("button", { name: "Run" }));
  await waitFor(() => expect(landed).toContain("run-previous"));
});

it("draws an earlier take beside the clip it was replaced by", async () => {
  // A shot holds one `run`, so a retry used to erase the only pointer to what
  // it replaced. Comparing the two is the reason for re-rendering at all.
  draw(
    record({
      shots: [
        shot({
          run: "run-current",
          node: "node-now",
          clip: { node: "node-now", name: "now.mp4", url: "https://x/now.mp4" },
          takes: [
            {
              run: "run-earlier",
              node: "node-was",
              clip: {
                node: "node-was",
                name: "was.mp4",
                url: "https://x/was.mp4",
              },
            },
          ],
        }),
      ],
    }),
  );

  // `earlier` is a badge on the take's own output panel now — the small
  // `Frame` that carried a `superseded` hint is gone, because a shot's outputs
  // are drawn by the same panel the run screen uses.
  expect(await screen.findByText("earlier")).toBeTruthy();
  expect(screen.getByText("was.mp4")).toBeTruthy();
  expect(screen.getByText("now.mp4")).toBeTruthy();
});

it("draws every cut of the scene, newest first, marking the older ones", async () => {
  draw(
    record({
      output: {
        node: "node-2",
        name: "light-flex-2.mp4",
        url: "https://x/2.mp4",
      },
      cuts: [
        { node: "node-1", name: "light-flex.mp4", url: "https://x/1.mp4" },
      ],
    }),
  );

  expect(await screen.findByText("Cuts")).toBeTruthy();
  expect(screen.getByText("light-flex-2.mp4")).toBeTruthy();
  expect(screen.getByText("light-flex.mp4")).toBeTruthy();
  expect(screen.getByText("earlier")).toBeTruthy();
});

it("still says 'The cut' when there is only one", async () => {
  // The plural is a signal that there is history to look at; a scene cut once
  // should not imply there is.
  draw(
    record({
      output: {
        node: "node-1",
        name: "light-flex.mp4",
        url: "https://x/1.mp4",
      },
    }),
  );
  expect(await screen.findByText("The cut")).toBeTruthy();
});

it("lists the runs behind a shot, using the shared run list", async () => {
  // A link per tile answers "what made this picture" one picture at a time.
  // Read together the runs answer a different question — what has been spent on
  // this shot, what is still a draft, what failed.
  draw(
    record({
      shots: [
        shot({
          run: "run-clip",
          runs: [
            {
              id: "run-clip",
              project: "proj-0001",
              role: "clip",
              status: "succeeded",
              model: "kling",
            },
            {
              id: "run-old",
              project: "proj-0001",
              role: "earlier take",
              status: "succeeded",
              model: "kling",
            },
          ],
        }),
      ],
    }),
  );

  // The runs moved behind a tab on the shot, so reaching them is a click now —
  // and the tab is labelled with its count, which is what makes it worth
  // opening. Asserting the count too, because a tab that says `Runs · 2` and
  // opens on one run is the failure this test would otherwise miss.
  const tab = await screen.findByRole("tab", { name: /^Runs/ });
  expect(tab.textContent).toContain("2");
  fireEvent.click(tab);

  expect(await screen.findByText("clip")).toBeTruthy();
  expect(screen.getByText("earlier take")).toBeTruthy();

  fireEvent.click(screen.getByText("run-old"));
  await waitFor(() => expect(landed).toContain("run-old"));
});

it("edits the scene's setting in place, and keeps the board's URLs alive", async () => {
  // The setting was readable and not editable, and it is the one field a person
  // actually revises: it is prepended byte-identically to every panel prompt,
  // so it is the lever that keeps separately rendered panels agreeing on one
  // room. `PATCH /scenes/<id>` has accepted it all along; the frontend simply
  // never asked.
  const patch = vi.mocked(patchScene);
  patch.mockResolvedValue({ setting: "A garage at night" } as SceneRecord);
  draw(record({ setting: "A bare studio wall" }));

  expect(await screen.findByText("A bare studio wall")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /^edit the setting$/i }));

  fireEvent.change(screen.getByLabelText("Setting"), {
    target: { value: "A garage at night" },
  });
  fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

  await waitFor(() =>
    expect(patch).toHaveBeenCalledWith(ID, { setting: "A garage at night" }),
  );
  // Merged, not refetched: a re-GET would re-sign every panel URL on the board
  // to show one changed sentence.
  expect(await screen.findByText("A garage at night")).toBeTruthy();
  expect(vi.mocked(getScene).mock.calls.length).toBe(1);
});

/**
 * Delete lives behind the page bar's `⋯` now — never wired to a page before
 * this, per `apis/studio.ts`'s own note on `deleteScene`.
 */
it("types the name before deleting the scene, then lands on its project", async () => {
  destroy.mockResolvedValue({ id: ID, files: "delete" });
  draw(record());
  await screen.findByText("Light flex");

  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));

  const dialog = await screen.findByRole("alertdialog");
  const action = within(dialog).getByRole("button", { name: "Delete" }) as HTMLButtonElement;
  expect(action.disabled).toBe(true);
  expect(destroy).not.toHaveBeenCalled();

  fireEvent.change(within(dialog).getByLabelText("Confirm"), {
    target: { value: "Light flex" },
  });
  await waitFor(() => expect(action.disabled).toBe(false));
  fireEvent.click(action);

  await waitFor(() => expect(destroy).toHaveBeenCalledWith(ID, "delete"));
  await waitFor(() => expect(landed).toBe("/p/proj-0001"));
});
