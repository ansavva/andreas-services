import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CreatedRun, ModelEntry } from "../../types";
import { TestProviders } from "../../test-providers";

vi.mock("../../apis/studio", () => ({
  getModels: vi.fn(),
  createRun: vi.fn(),
}));

import { createRun, getModels } from "../../apis/studio";
import { NewRunStrip } from "./NewRunStrip";

const models = vi.mocked(getModels);
const create = vi.mocked(createRun);

const PROJECT = "proj-0001";

/**
 * Two invented entries rather than two real ones.
 *
 * The registry is data that gets refreshed against the providers, so a test
 * pinned to what `models.json` says today fails the next time somebody runs
 * `models refresh` — for a reason that has nothing to do with this strip. What
 * matters here is the SHAPE: a snapshot holding `refreshed` among the props, an
 * image field that is a send rather than a param, and a non-scalar default.
 */
const STILL: ModelEntry = {
  key: "still-model",
  model: "vendor/still-model",
  kind: "image",
  skill: "studio-media-still-model",
  images: { refs: "image_input", start: null, end: null, max_refs: 4 },
  snapshot: {
    resolution: { enum: ["1K", "2K"], default: "2K" },
    output_format: { enum: ["jpg", "png"], default: "jpg" },
    number_of_images: { default: 1, minimum: 1, maximum: 4 },
    // Dropped: an image field is a send, never a param (hard rule #3).
    image_input: { default: [] },
    // Dropped: the plan carries the prompt beside the params.
    prompt: { default: "" },
    // Dropped: metadata sitting among the props.
    refreshed: "2026-08-15",
  },
};

const MOTION: ModelEntry = {
  key: "motion-model",
  model: "vendor/motion-model",
  kind: "video",
  skill: "studio-media-motion-model",
  images: { refs: "reference_images", start: "start_image", end: "end_image", max_refs: 6 },
  snapshot: {
    duration: { default: 5, minimum: 3, maximum: 15 },
    generate_audio: { default: false },
    reference_images: { default: [] },
    start_image: { default: null },
    refreshed: "2026-08-15",
  },
};

function created(over: Partial<CreatedRun> = {}): CreatedRun {
  return {
    id: "run-0001",
    project: PROJECT,
    status: "draft",
    folder: "node-run",
    payload: { request: null, response: null, prompt: null },
    fingerprint: "f1",
    sends: [],
    created: "2026-08-31T00:00:00Z",
    ...over,
  };
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  models.mockResolvedValue({ "still-model": STILL, "motion-model": MOTION });
  create.mockResolvedValue(created());
});

/** Reports where a create navigated, and what it carried there. */
function Address() {
  const location = useLocation();
  return (
    <span data-testid="address">
      {location.pathname} {JSON.stringify(location.state)}
    </span>
  );
}

async function open() {
  render(
    <MemoryRouter initialEntries={[`/p/${PROJECT}`]}>
      <NewRunStrip projectId={PROJECT} />
      <Address />
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
  // **The strip is disclosed, not permanent.** It opens where its button
  // stood — the pattern the plan editor and the promote panel also follow —
  // so every case here starts by asking for it.
  fireEvent.click(screen.getByRole("button", { name: "New run" }));
  // The picker is disabled until the registry lands, so waiting on the request
  // alone would click a control that is not yet offering anything.
  await waitFor(() => expect(picker().disabled).toBe(false));
}

function picker(): HTMLButtonElement {
  return screen.getByRole("combobox", { name: "Model" }) as HTMLButtonElement;
}

/** The model list, as the picker offers it. */
function options(): string[] {
  fireEvent.click(picker());
  const labels = screen.getAllByRole("option").map((each) => each.textContent);
  fireEvent.keyDown(picker(), { key: "Escape" });
  return labels.filter((label): label is string => label !== null);
}

function choose(label: string) {
  fireEvent.click(picker());
  fireEvent.click(screen.getByRole("option", { name: label }));
}

/**
 * The kind is what decides which models are even askable.
 *
 * A still model has no start frame and a video model produces no still, so
 * offering both lists at once would put a run one mis-click from a model that
 * cannot do what was asked — which the API would refuse, after the draft.
 */
it("filters the models by the kind that is pressed", async () => {
  await open();

  expect(options()).toEqual(["still-model"]);

  fireEvent.click(screen.getByRole("button", { name: "Video" }));
  expect(options()).toEqual(["motion-model"]);
});

it("will not create until a model is chosen", async () => {
  await open();

  // Re-queried after each change rather than held: the form lives inside a
  // portalled drawer, so the element is a different node after a re-render.
  const create = () =>
    screen.getByRole("button", { name: "Create run" }) as HTMLButtonElement;
  expect(create().disabled).toBe(true);

  choose("still-model");
  await waitFor(() => expect(create().disabled).toBe(false));
});

describe("what the draft is created with", () => {
  it("pins the model, the engine and the seeded params", async () => {
    await open();
    choose("still-model");

    fireEvent.click(screen.getByRole("button", { name: "Create run" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create).toHaveBeenCalledWith({
      project: PROJECT,
      kind: "image",
      // The Replicate id, never the registry key — and `engine` is the skill.
      model: "vendor/still-model",
      engine: "studio-media-still-model",
      plan: {
        version: 1,
        origin: "authored",
        prompt: "",
        // `refreshed`, `prompt` and the entry's image field are all absent,
        // and so is the non-scalar default behind `image_input`.
        params: { resolution: "2K", output_format: "jpg", number_of_images: 1 },
      },
    });
  });

  it("drops the video entry's start and reference fields too", async () => {
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Video" }));
    choose("motion-model");

    fireEvent.click(screen.getByRole("button", { name: "Create run" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0]?.[0].plan?.params).toEqual({
      duration: 5,
      generate_audio: false,
    });
  });

  it("sends the output name as the API will store it, and omits an empty one", async () => {
    await open();
    choose("still-model");
    fireEvent.change(screen.getByLabelText("Output name"), { target: { value: "Wide Shot" } });

    fireEvent.click(screen.getByRole("button", { name: "Create run" }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0]?.[0].name).toBe("wide-shot");
  });
});

/**
 * The strip creates the record and the editor does the rest, so landing in the
 * editor is half the feature: a draft that opens read-only is a form somebody
 * has to find the "edit" button on before they can write the prompt.
 */
it("opens the new draft with its editor already open", async () => {
  create.mockResolvedValue(created({ id: "run-0042" }));

  await open();
  choose("still-model");
  fireEvent.click(screen.getByRole("button", { name: "Create run" }));

  await waitFor(() =>
    expect(screen.getByTestId("address").textContent).toBe(
      `/p/${PROJECT}/r/run-0042 {"editing":true}`,
    ),
  );
});

it("says what went wrong where the choice was made, and stays there", async () => {
  create.mockRejectedValue(new Error("project is not yours"));

  await open();
  choose("still-model");
  fireEvent.click(screen.getByRole("button", { name: "Create run" }));

  /**
   * **This used to assert there was no `dialog` on screen**, back when the form
   * was an inline strip: a failure reported by opening a second thing over the
   * top of the first is a failure you have to dismiss before you can fix it.
   * The form is a drawer now, so the drawer IS the dialog — what still has to
   * hold is that nothing NEW opened to deliver the news, the panel is still
   * there, and the choice that produced the failure is still in it.
   */
  const panel = screen.getByRole("dialog");
  expect(await screen.findByText("project is not yours")).toBeTruthy();
  expect(panel.contains(screen.getByText("project is not yours"))).toBe(true);
  expect(screen.getByRole("button", { name: "Create run" })).toBeTruthy();
  expect(screen.getByTestId("address").textContent).toContain(`/p/${PROJECT}`);
  expect(screen.getByTestId("address").textContent).not.toContain("/r/");
});
