import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { SceneRecord, Shot } from "../types";

// The header pulls in auth and the library context and says nothing this file
// asserts on. Everything else is the real component.
vi.mock("../components/common/AppHeader", () => ({ AppHeader: () => <div /> }));

vi.mock("../apis/studio", () => ({ getScene: vi.fn() }));

import { getScene } from "../apis/studio";
import { ScenePage } from "./ScenePage";

const read = vi.mocked(getScene);

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

function draw(scene: SceneRecord) {
  read.mockResolvedValue(scene);
  return render(
    <MemoryRouter initialEntries={[`/s/${ID}`]}>
      <Routes>
        <Route path="/s/:sceneId" element={<ScenePage />} />
      </Routes>
    </MemoryRouter>,
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
  expect(screen.getByText("kling")).toBeTruthy();
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
  const boarded = screen.getByRole("button", { name: /square to camera/i });
  expect(within(boarded).getByRole("presentation", { hidden: true })).toBeTruthy();
  // The unboarded one carries its prompt instead of a picture, and is not a
  // link to a node that does not exist.
  expect(screen.getByText("the peak of the move")).toBeTruthy();
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
  expect(screen.getByText("sample")).toBeTruthy();
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
  expect(screen.getByText("opens on")).toBeTruthy();
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
