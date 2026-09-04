import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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

/** The provider's state, as JSON, and the api handed out for the test to drive. */
function Probe() {
  api = useCreateBar();
  const bar = useCreateBarState();
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
