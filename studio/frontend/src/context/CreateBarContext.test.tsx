import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it } from "vitest";

import {
  CREATE_COLLAPSED_STORAGE_KEY,
  CREATE_PROJECT_STORAGE_KEY,
  CreateBarProvider,
  useCreateBar,
  useCreateBarState,
  type AttachRef,
  type CreateBarApi,
} from "./CreateBarContext";

const FACE: AttachRef = {
  node: "node-face",
  url: "https://example.invalid/face.png",
  name: "face-01.png",
  kind: "character",
  character: "char-1",
};
const FRAME: AttachRef = {
  node: "node-frame",
  url: "https://example.invalid/frame.png",
  name: "out-2.png",
  kind: "run",
  run: "run-1",
  output: 2,
};

let api: CreateBarApi;
/** The state half — what the bar itself reads, and what puts it away. */
let own: ReturnType<typeof useCreateBarState>;

/** The provider's state, as JSON, and the api handed out for the test to drive. */
function Probe() {
  api = useCreateBar();
  const bar = useCreateBarState();
  own = bar;
  return (
    <pre data-testid="state">
      {JSON.stringify({
        kind: bar.kind,
        model: bar.model,
        prompt: bar.prompt,
        params: bar.params,
        attachments: bar.attachments,
        project: bar.project,
        target: bar.target,
        onProject: bar.onProject,
        role: bar.role,
        focus: bar.focus,
        shown: bar.shown,
      })}
    </pre>
  );
}

function state() {
  return JSON.parse(screen.getByTestId("state").textContent ?? "{}");
}

function mount(path = "/") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <CreateBarProvider>
        <Probe />
      </CreateBarProvider>
    </MemoryRouter>,
  );
}

afterEach(cleanup);
beforeEach(() => {
  window.localStorage.removeItem(CREATE_PROJECT_STORAGE_KEY);
  window.localStorage.removeItem(CREATE_COLLAPSED_STORAGE_KEY);
});

it("loadRun fills the bar whole and asks for focus", () => {
  mount();
  expect(state().focus).toBe(0);

  act(() =>
    api.loadRun({
      project: "proj-1",
      kind: "video",
      model: "vendor/motion-model",
      prompt: "Slow push-in.",
      params: { duration: 8 },
      attachments: [{ ref: FRAME, role: "start" }],
    }),
  );

  const after = state();
  expect(after.kind).toBe("video");
  expect(after.model.video).toBe("vendor/motion-model");
  expect(after.prompt).toBe("Slow push-in.");
  // Params are kept PER MODEL, so switching models never carries one model's
  // knobs into another.
  expect(after.params["vendor/motion-model"]).toEqual({ duration: 8 });
  expect(after.attachments.video).toEqual([{ ref: FRAME, role: "start" }]);
  expect(after.project).toBe("proj-1");
  expect(after.target).toBe("proj-1");
  expect(after.focus).toBe(1);
});

it("attach: reference accumulates without duplicates; a frame replaces and switches to video", () => {
  mount();
  act(() => api.attach(FACE, "reference"));
  act(() => api.attach(FACE, "reference"));
  expect(state().attachments.image).toEqual([{ ref: FACE, role: "reference" }]);
  expect(state().kind).toBe("image");

  // A start frame is a VIDEO's, so attaching one switches the bar.
  act(() => api.attach(FRAME, "start"));
  expect(state().kind).toBe("video");
  expect(state().attachments.video).toEqual([{ ref: FRAME, role: "start" }]);
  // The image side kept its own images.
  expect(state().attachments.image).toEqual([{ ref: FACE, role: "reference" }]);

  // One start frame at a time: a second replaces the first.
  act(() => api.attach(FACE, "start"));
  expect(state().attachments.video).toEqual([{ ref: FACE, role: "start" }]);
});

it("setKind switches and drops the highlighted role", () => {
  mount();
  act(() => api.setKind("video"));
  expect(state().kind).toBe("video");
  expect(state().role).toBeNull();
  act(() => api.setKind("image"));
  expect(state().kind).toBe("image");
});

it("the route's project is the target and is remembered; off a project the last one stands", () => {
  mount("/p/proj-9/r/run-1");
  expect(state().target).toBe("proj-9");
  expect(state().onProject).toBe(true);
  expect(window.localStorage.getItem(CREATE_PROJECT_STORAGE_KEY)).toBe("proj-9");
  cleanup();

  mount("/");
  expect(state().target).toBe("proj-9");
  expect(state().onProject).toBe(false);
});

/**
 * Collapsing the sheet — a decision about every screen, and a remembered one.
 *
 * It used to be answerable on the opened run alone, where the sheet is not
 * drawn until something calls it up. The sheet covers whatever you are looking
 * at everywhere else too, and "I want the feed to myself" is the same sentence
 * there.
 */
it("collapse drops the sheet, remembers it, and expand brings it back focused", () => {
  mount();
  expect(state().shown).toBe(true);

  act(() => own.collapse());
  expect(state().shown).toBe(false);
  // Remembered, because the point of collapsing it is to browse without it.
  expect(window.localStorage.getItem(CREATE_COLLAPSED_STORAGE_KEY)).toBe("1");

  const focus = state().focus;
  act(() => own.expand());
  expect(state().shown).toBe(true);
  // Opened to type in, so the caret goes with it.
  expect(state().focus).toBe(focus + 1);
  expect(window.localStorage.getItem(CREATE_COLLAPSED_STORAGE_KEY)).toBeNull();
});

it("a collapsed sheet stays collapsed across a reload", () => {
  window.localStorage.setItem(CREATE_COLLAPSED_STORAGE_KEY, "1");
  mount();
  expect(state().shown).toBe(false);
});

/**
 * **The one outcome this must not have**: a picture attached to a sheet nobody
 * can see. Every route into the bar — a tile's `Use as reference`, a row's
 * Edit, Rerun — brings it back with what it filled.
 */
it("anything that fills the bar opens it", () => {
  mount();
  act(() => own.collapse());
  expect(state().shown).toBe(false);

  act(() => api.attach(FACE, "reference"));
  expect(state().shown).toBe(true);
  expect(state().attachments.image).toEqual([{ ref: FACE, role: "reference" }]);

  act(() => own.collapse());
  act(() => api.loadRun({ project: "proj-1", kind: "image" }));
  expect(state().shown).toBe(true);
});

/**
 * The open file is the opened run's viewer now — `ViewerFrame`, sized to the
 * window — so the sheet stays away from it the same way, until something
 * calls it up.
 */
it("the open file keeps the sheet away until something fills it, like the opened run", () => {
  mount("/o/node-1");
  expect(state().shown).toBe(false);

  act(() => api.attach(FACE, "reference"));
  expect(state().shown).toBe(true);
});
