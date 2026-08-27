import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { SceneRecord, Shot } from "../types";

// The header pulls in auth and the library context and says nothing this file
// asserts on. Everything else is the real component.

// `getProject` is here for the breadcrumb, which reads the project's name so
// the trail says where the scene sits rather than just "Project".
vi.mock("../apis/studio", () => ({
  getScene: vi.fn(),
  patchShot: vi.fn(),
  getProject: vi.fn(),
}));

import { getProject, getScene, patchShot } from "../apis/studio";
import { ScenePage } from "./ScenePage";
import { TestProviders } from "../test-providers";

const read = vi.mocked(getScene);
const save = vi.mocked(patchShot);
const project = vi.mocked(getProject);

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
    motion: { prompt: "he lifts the lanyard over his head", duration: 6, model: "kling" },
    ...over,
  };
}

function record(over: Partial<SceneRecord> = {}): SceneRecord {
  return {
    id: ID,
    project: "proj-0001",
    slug: "light-flex",
    title: "Light flex",
    status: "planned",
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
  project.mockResolvedValue({ id: "proj-0001", slug: "a-project", title: "A project" } as never);
  landed = "";
  return render(
    <MemoryRouter initialEntries={[`/s/${ID}`]}>
      <Routes>
        <Route path="/s/:sceneId" element={<ScenePage />} />
        {/* The board opens frames in the viewer now rather than in a drawer of
            its own, so what a click does is *navigate* — this stands in for the
            screen it navigates to. */}
        <Route path="/o/:nodeId" element={<Land />} />
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
              image: { node: "node-a", name: "panel-01.png", url: "https://example/panel-01.png" },
            },
            { n: 2, role: "sample", prompt: "the peak of the move" },
          ],
        }),
      ],
    }),
  );

  await screen.findByText("The whistle comes off");
  const boarded = screen.getAllByRole("button", { name: /square to camera/i })[0]!;
  expect(within(boarded).getByRole("presentation", { hidden: true })).toBeTruthy();
  // The unboarded one carries its prompt instead of a picture, and is not a
  // link to a node that does not exist.
  expect(screen.getAllByText("the peak of the move").length).toBeGreaterThan(0);
  expect(screen.queryByRole("button", { name: /the peak of the move/i })).toBeNull();
});

it("labels a sample as a sample, because it is the one panel that binds to nothing", async () => {
  draw(
    record({
      shots: [
        shot({ panels: [{ n: 1, role: "sample", prompt: "what the shot should look like" }] }),
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
            frame: { node: "node-handoff", name: "last.png", url: "https://example/last.png" },
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
              image: { node: "node-a", name: "panel-01.png", url: "https://example/panel-01.png" },
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
  draw(record({ shots: [shot({ motion: { prompt: '{ "subject": "the man, unchanged" }' } })] }));

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("the man, unchanged")).toBeTruthy();
  // Nothing to press, so nothing to be stuck closed.
  expect(screen.queryByRole("button", { name: /motion prompt/i })).toBeNull();
});

const PROMPT = JSON.stringify(
  {
    subject: "The man from the source image, unchanged",
    action: "He lifts the lanyard over his head",
    camera: { shot: "wide", movement: "static/hold", lens_mm: 50, speed: "locked off" },
    style: "Photorealistic live-action",
    avoid: "changing face, cuts",
    dialogue: ["a key this form does not show"],
  },
  null,
  2,
);

it("reads the motion prompt as prose, not as JSON", async () => {
  // It reached the page as 1.4 kB of escaped JSON, which is not showing anyone
  // their prompt. This is studio's OWN document with a schema `studio prompt`
  // validates — the run page's "never parsed" rule is about the PROVIDER's
  // payload, whose shape studio does not own, and applying it here was wrong.
  draw(record({ shots: [shot({ motion: { prompt: PROMPT, duration: 6 } })] }));

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("Subject")).toBeTruthy();
  expect(screen.getByText("The man from the source image, unchanged")).toBeTruthy();
  expect(screen.getByText("wide · static/hold · 50mm · locked off")).toBeTruthy();
  expect(screen.queryByText(/^\{$/)).toBeNull();
});

it("falls back to the raw text when the prompt is prose rather than JSON", async () => {
  // A plain prose prompt is legal on every engine here.
  draw(record({ shots: [shot({ motion: { prompt: "he lifts the lanyard, slowly" } })] }));

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("he lifts the lanyard, slowly")).toBeTruthy();
});

it("saves an edit as both the document and the string the model is given", async () => {
  save.mockResolvedValue({} as Shot);
  draw(record({ shots: [shot({ motion: { prompt: PROMPT, duration: 6 } })] }));
  await screen.findByText("The whistle comes off");

  fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
  fireEvent.change(screen.getByLabelText("Action"), { target: { value: "He ducks through it" } });
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
  expect(Object.keys(sent)).toEqual(["subject", "action", "camera", "style", "avoid", "dialogue"]);
  // The parsed document travels alongside the string the model receives.
  expect((body.motion as { prompt_json: unknown }).prompt_json).toEqual(sent);
});

it("keeps the edit open and says why when the save fails", async () => {
  save.mockRejectedValue(new Error("shot-01 is gone"));
  draw(record({ shots: [shot({ motion: { prompt: PROMPT } })] }));
  await screen.findByText("The whistle comes off");

  fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
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
            frame: { node: "node-tail", name: "tail.png", url: "https://example/tail.png" },
          },
          panels: [
            { n: 1, role: "start", prompt: "the opening", references: { characters: ["subject-a"] } },
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
  draw(record({ shots: [shot({ continues: true, opens_on: null, panels: [] })] }));

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("awaits previous shot")).toBeTruthy();
});

it("shows the setting once, not once per panel", async () => {
  draw(record({ setting: "A plain mid-grey seamless studio cyclorama." }));

  expect(await screen.findByText("A plain mid-grey seamless studio cyclorama.")).toBeTruthy();
});

it("totals the planned runtime, which is what the scene will cost to shoot", async () => {
  draw(
    record({
      shots: [
        shot({ id: "shot-01", order: 10, motion: { prompt: "a", duration: 6 } }),
        shot({ id: "shot-02", order: 20, motion: { prompt: "b", duration: 12 } }),
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
  await waitFor(() => expect(screen.getByRole("button", { name: /open its run/i })).toBeTruthy());
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

it("draws a plate the plan names as a thumbnail, not as a filename", async () => {
  // "plus peter" said nothing about which pictures are going, and which pictures
  // are going is the whole question. The API resolves the block to images.
  draw(
    record({
      shots: [
        shot({
          motion: {
            prompt: "x",
            references: { characters: ["subject-a"], pick: "front.png" },
            reference_assets: [
              { node: "node-plate", name: "front.png", url: "https://example/front.png" },
            ],
          },
        }),
      ],
    }),
  );

  await screen.findByText("The whistle comes off");
  expect(screen.getByText("plate")).toBeTruthy();
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
              image: { node: "node-a", name: "shot-01-p1.jpeg", url: "https://example/a.jpeg" },
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
  draw(record({ shots: [shot({ panels: [{ n: 1, role: "start", prompt: "not yet" }] })] }));

  await screen.findByText("The whistle comes off");
  expect(screen.queryByRole("button", { name: /not yet/i })).toBeNull();
});
