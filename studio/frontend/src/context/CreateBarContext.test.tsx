import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { TestProviders } from "../test-providers";
import { afterEach, beforeEach, expect, it } from "vitest";

import {
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
        overViewer: bar.overViewer,
        raised: bar.raised,
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
    // The provider reads a scene on `/s/<id>` through react-query, so it
    // needs a client even on routes that never ask.
    { wrapper: TestProviders },
  );
}

afterEach(cleanup);
beforeEach(() => {
  window.localStorage.removeItem(CREATE_PROJECT_STORAGE_KEY);
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

it("move puts one attachment at another's index, within the current kind", () => {
  mount();
  const second: AttachRef = { ...FACE, node: "node-2", name: "face-02.png" };
  const third: AttachRef = { ...FACE, node: "node-3", name: "face-03.png" };
  act(() => api.attach(FACE, "reference"));
  act(() => api.attach(second, "reference"));
  act(() => api.attach(third, "reference"));

  act(() => own.move(2, 0));
  expect(state().attachments.image.map((each: { ref: AttachRef }) => each.ref.node)).toEqual([
    "node-3",
    "node-face",
    "node-2",
  ]);
  act(() => own.move(0, 1));
  expect(state().attachments.image.map((each: { ref: AttachRef }) => each.ref.node)).toEqual([
    "node-face",
    "node-3",
    "node-2",
  ]);
  // Out of range, or nowhere: nothing happens.
  act(() => own.move(1, 1));
  act(() => own.move(0, 7));
  expect(state().attachments.image.map((each: { ref: AttachRef }) => each.ref.node)).toEqual([
    "node-face",
    "node-3",
    "node-2",
  ]);
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
 * On a page the sheet is always drawn and there is nothing to put away; on
 * the opened run it is drawn only once called up, and can be put away again.
 * `dismiss` on a page is a no-op rather than a hidden sheet with no handle.
 */
it("summon and dismiss are the opened run's; on a page the sheet is simply there", () => {
  mount();
  expect(state().shown).toBe(true);
  expect(state().overViewer).toBe(false);
  act(() => own.dismiss());
  expect(state().shown).toBe(true);
});

it("on the opened run, summon draws the sheet focused and dismiss puts it away", () => {
  mount("/p/proj-1/r/run-1");
  expect(state().shown).toBe(false);
  expect(state().overViewer).toBe(true);

  const focus = state().focus;
  act(() => own.summon());
  expect(state().shown).toBe(true);
  // Opened to type in, so the caret goes with it.
  expect(state().focus).toBe(focus + 1);

  act(() => own.dismiss());
  expect(state().shown).toBe(false);
});

/**
 * **The one outcome this must not have**: a picture attached to a sheet nobody
 * can see. Every route into the bar — a tile's `Use as reference`, a row's
 * Edit, Rerun — brings it up with what it filled. Only the ones that load
 * words say so through `raised`, which scrolls the page to the sheet: a
 * picture lands in the dock the sheet leaves behind when scrolled past, and
 * scrolling on its account would pull that dock out from under the drag.
 */
it("anything that fills the bar opens it; loading a run raises it, attaching does not", () => {
  mount("/p/proj-1/r/run-1");
  expect(state().shown).toBe(false);
  const raised = state().raised;

  act(() => api.attach(FACE, "reference"));
  expect(state().shown).toBe(true);
  expect(state().raised).toBe(raised);
  expect(state().attachments.image).toEqual([{ ref: FACE, role: "reference" }]);

  act(() => own.dismiss());
  act(() => api.loadRun({ project: "proj-1", kind: "image" }));
  expect(state().shown).toBe(true);
  expect(state().raised).toBe(raised + 1);
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
