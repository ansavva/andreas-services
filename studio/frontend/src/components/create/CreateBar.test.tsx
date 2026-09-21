import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";

import {
  CreateBarProvider,
  useCreateBar,
  type AttachRef,
  type CreateBarApi,
} from "../../context/CreateBarContext";
import { TestProviders } from "../../test-providers";
import type { CreatedRun, ModelEntry } from "../../types";

vi.mock("../../apis/studio", () => ({
  getModels: vi.fn(),
  getModelDefaults: vi.fn(),
  setModelDefaults: vi.fn(),
  clearModelDefaults: vi.fn(),
  getProject: vi.fn(),
  getProjects: vi.fn().mockResolvedValue([]),
  getTemplates: vi.fn(),
  expandTemplate: vi.fn(),
  createRun: vi.fn(),
  submitRun: vi.fn(),
  patchRunPlan: vi.fn(),
  patchRunSends: vi.fn(),
  setRunCharacters: vi.fn(),
  setRunLocations: vi.fn(),
  setRunModel: vi.fn(),
  deleteRun: vi.fn(),
  getRuns: vi.fn(),
  // The settings rows and the picker, when they open.
  getModelSchema: vi.fn().mockRejectedValue(new Error("no registry in tests")),
  getFolder: vi.fn().mockResolvedValue({
    prefix: "",
    sort: "name",
    depth: "1",
    tags: [],
    breadcrumbs: [],
    folders: [],
    files: [],
  }),
}));

import {
  clearModelDefaults,
  createRun,
  expandTemplate,
  getFolder,
  getModelDefaults,
  getModels,
  getProject,
  getRuns,
  getTemplates,
  patchRunPlan,
  patchRunSends,
  setModelDefaults,
  setRunCharacters,
  setRunLocations,
  setRunModel,
  submitRun,
} from "../../apis/studio";
import { CreateBar } from "./CreateBar";

const PROJECT = "proj-0001";

const STILL: ModelEntry = {
  key: "still-model",
  model: "vendor/still-model",
  kind: "image",
  skill: "studio-media-still-model",
  images: { refs: "input_images", start: null, end: null, max_refs: 4 },
  snapshot: {
    resolution: { enum: ["1K", "2K"], default: "2K" },
    input_images: { default: [] },
    prompt: { default: "" },
    refreshed: "2026-08-15",
  },
};

const MOTION: ModelEntry = {
  key: "motion-model",
  model: "vendor/motion-model",
  kind: "video",
  skill: "studio-media-motion-model",
  images: {
    refs: "reference_images",
    start: "start_image",
    end: "end_image",
    max_refs: 6,
  },
  snapshot: {
    duration: { default: 5, enum: [5, 10] },
    start_image: { default: null },
    refreshed: "2026-08-15",
  },
};

const FACE: AttachRef = {
  node: "node-face",
  url: "https://example.invalid/face.png",
  name: "face-01.png",
  kind: "character",
  character: "char-1",
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

let api: CreateBarApi;

function Driver() {
  api = useCreateBar();
  return <span data-testid="address">{useLocation().pathname}</span>;
}

// Focusing the editor makes Lexical measure the caret, and jsdom's `Range`
// cannot be measured. The rect is never read here; it only has to exist.
beforeAll(() => {
  const rect = () => new DOMRect(0, 0, 0, 0);
  Range.prototype.getBoundingClientRect = rect;
  Range.prototype.getClientRects = () => [] as unknown as DOMRectList;
});

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getModels).mockResolvedValue({
    "still-model": STILL,
    "motion-model": MOTION,
  });
  vi.mocked(getProject).mockResolvedValue({
    id: PROJECT,
    name: "A project",
    characters: [],
  } as never);
  vi.mocked(getTemplates).mockResolvedValue({ blocks: {}, templates: [] });
  vi.mocked(getModelDefaults).mockResolvedValue({ defaults: {} });
  vi.mocked(setModelDefaults).mockImplementation(async (model, params) => ({
    model,
    params,
    set_at: "2026-09-13T00:00:00Z",
  }));
  vi.mocked(clearModelDefaults).mockImplementation(async (model) => ({ model, cleared: true }));
  vi.mocked(createRun).mockResolvedValue(created());
  vi.mocked(submitRun).mockResolvedValue({
    id: "run-0001",
    status: "pending",
  } as never);
  vi.mocked(getRuns).mockResolvedValue({ runs: [], cursor: null });
  vi.mocked(patchRunPlan).mockResolvedValue({ ...created(), fingerprint: "f-plan" } as never);
  vi.mocked(patchRunSends).mockResolvedValue({ ...created(), fingerprint: "f-sends" } as never);
  vi.mocked(setRunCharacters).mockResolvedValue(created() as never);
  vi.mocked(setRunLocations).mockResolvedValue(created() as never);
  vi.mocked(setRunModel).mockResolvedValue({ ...created(), fingerprint: "f-model" } as never);
});

async function open(path = `/p/${PROJECT}`) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <CreateBarProvider>
        <CreateBar />
        <Driver />
      </CreateBarProvider>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
  // The registry has landed once the placeholder names the project.
  await screen.findByText("Describe what to make in A project…");
}

const editor = () => screen.getByRole("textbox", { name: "Prompt" });

/** Focus leaves for somewhere outside the bar. */
const leave = () => fireEvent.focusOut(editor(), { relatedTarget: null });
const strip = () => document.querySelector("[data-mode-strip]") as HTMLElement;

/** The prompt, put into the bar the way a feed row would. */
function fill(prompt: string) {
  api.loadRun({ project: PROJECT, kind: "image", prompt });
}

it("the kind switch changes the tiles, the chips and the model", async () => {
  await open();
  fill("A portrait.");
  await waitFor(() => expect(strip()).toBeTruthy());

  const labels = () =>
    Array.from(strip().querySelectorAll("[data-role-cell]")).map((cell) =>
      cell.getAttribute("aria-label"),
    );
  expect(labels()).toEqual(["Image refs"]);
  // The still model's snapshot has a resolution and no duration.
  expect(screen.getByRole("button", { name: "Resolution: 2K" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: /^Duration/ })).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "Video" }));
  expect(labels()).toEqual(["Start frame", "End frame", "Image refs"]);
  // The duration is the snapshot's enum, as a chip reading the default.
  expect(screen.getByRole("button", { name: "Duration: 5s" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: /^Resolution/ })).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(createRun).toHaveBeenCalled());
  expect(vi.mocked(createRun).mock.calls[0]![0]).toMatchObject({
    kind: "video",
    model: "vendor/motion-model",
    engine: "studio-media-motion-model",
    plan: { prompt: "A portrait.", params: { duration: 5 } },
  });
});

/**
 * A person's own defaults for a model lie over the registry's, and the
 * settings panel is where they are set and unset — on the popover and the
 * phone sheet alike, since both draw the same panel.
 */
it("saved defaults seed the params; Set as default writes them, Reset goes back to the model's", async () => {
  vi.mocked(getModelDefaults).mockResolvedValue({
    defaults: { "vendor/still-model": { resolution: "1K" } },
  });
  await open();
  // The saved 1K over the snapshot's 2K.
  expect(await screen.findByRole("button", { name: "Resolution: 1K" })).toBeTruthy();

  // Two gears — the popover's and the phone sheet's, one hidden by CSS jsdom
  // does not apply. The popover's is first.
  fireEvent.click(screen.getAllByRole("button", { name: "Settings" })[0]!);
  const panel = await screen.findByRole("dialog", { name: "Settings" });
  expect(within(panel).getByText("Starts from your defaults.")).toBeTruthy();

  // Back to the model's own: the row goes, and so does the 1K.
  fireEvent.click(within(panel).getByRole("button", { name: "Reset" }));
  await waitFor(() => expect(clearModelDefaults).toHaveBeenCalledWith("vendor/still-model"));
  // The chip in the row and its row in the panel both read 2K now.
  await waitFor(() =>
    expect(screen.getAllByRole("button", { name: "Resolution: 2K" }).length).toBeGreaterThan(0),
  );
  expect(screen.queryByRole("button", { name: "Resolution: 1K" })).toBeNull();
  await waitFor(() =>
    expect(within(panel).getByText("Starts from the model's defaults.")).toBeTruthy(),
  );

  // Set as default keeps what the sheet holds now, whole.
  fireEvent.click(within(panel).getByRole("button", { name: "Set as default" }));
  await waitFor(() =>
    expect(setModelDefaults).toHaveBeenCalledWith("vendor/still-model", { resolution: "2K" }),
  );
  await waitFor(() => expect(within(panel).getByText("Starts from your defaults.")).toBeTruthy());
  expect(await screen.findByText(/Saved as your default for still-model/)).toBeTruthy();
});

it("⌘/Ctrl+Enter creates the draft and then submits it, in that order; plain Enter does not", async () => {
  await open();
  fill("A portrait.");
  await waitFor(() => expect(editor().textContent).toContain("A portrait."));

  // Enter is a line break, not a send — a prompt is paragraphs.
  fireEvent.keyDown(editor(), { key: "Enter" });
  fireEvent.keyDown(editor(), { key: "Enter", shiftKey: true });
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(createRun).not.toHaveBeenCalled();

  fireEvent.keyDown(editor(), { key: "Enter", metaKey: true });
  await waitFor(() => expect(submitRun).toHaveBeenCalledWith("run-0001"));

  expect(vi.mocked(createRun).mock.calls[0]![0]).toMatchObject({
    project: PROJECT,
    kind: "image",
    model: "vendor/still-model",
    engine: "studio-media-still-model",
    // The snapshot's defaults; the image field and `prompt` are not params.
    plan: {
      version: 1,
      origin: "authored",
      prompt: "A portrait.",
      params: { resolution: "2K" },
    },
    sends: [],
  });
  const order = [
    vi.mocked(createRun).mock.invocationCallOrder[0]!,
    vi.mocked(getRuns).mock.invocationCallOrder[0]!,
    vi.mocked(submitRun).mock.invocationCallOrder[0]!,
  ];
  expect([...order].sort((a, b) => a - b)).toEqual(order);
  // The duplicate question is one cheap read on the listing row.
  expect(getRuns).toHaveBeenCalledWith({
    project: PROJECT,
    fingerprint: "f1",
    include: "drafts",
  });

  // Sent: the prompt goes, the toast says so.
  expect(await screen.findByText("Sent")).toBeTruthy();
  await waitFor(() => expect(editor().textContent).toBe(""));
});

it("sends a JSON prompt as words, and a cited one as a template", async () => {
  /**
   * **The bug this pins.** The test for "does this prompt need expanding" was
   * `prompt.includes("{")`, and `studio prompt` writes a prompt as a serialised
   * JSON object — so every structured prompt went out through `PATCH /plan` as
   * a template and came back refused for citing `{ "subject"}`. There was no
   * way to send one from the app.
   *
   * A brace is not a citation. `@block.…`, `@character.N.…` and `@slot.…`
   * are; a JSON document is the words themselves.
   */
  vi.mocked(patchRunPlan).mockResolvedValue({ ...created(), fingerprint: "f2" } as never);
  await open();

  const json = '{"subject": "a person", "camera": {"move": "push in"}}';
  fill(json);
  await waitFor(() => expect(editor().textContent).toContain('"subject"'));
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(submitRun).toHaveBeenCalledWith("run-0001"));

  expect(patchRunPlan).not.toHaveBeenCalled();
  expect(vi.mocked(createRun).mock.calls[0]![0]).toMatchObject({
    plan: { prompt: json },
  });

  // The same bar, a prompt that really does cite something: the template goes.
  fill("A portrait. @block.scale");
  await waitFor(() => expect(editor().textContent).toContain("@block.scale"));
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(patchRunPlan).toHaveBeenCalled());
  expect(vi.mocked(patchRunPlan).mock.calls[0]![1]).toMatchObject({
    template: "A portrait. @block.scale",
  });
});

/** A draft's row, loaded the way Edit on it does — as itself, not as a copy. */
function editDraft(prompt: string, over: Partial<{ model: string }> = {}) {
  api.loadRun({
    project: PROJECT,
    kind: "image",
    model: over.model ?? "vendor/still-model",
    prompt,
    params: { resolution: "1K" },
    editing: {
      run: "run-draft",
      project: PROJECT,
      kind: "image",
      model: "vendor/still-model",
      plan: { version: 1, origin: "backfilled", prompt, params: { resolution: "1K" }, note: "keep me" },
    },
  });
}

it("Edit on a draft writes the draft in place and Send submits THAT run — no second draft", async () => {
  /**
   * A draft has not gone out, so it is still the thing being decided about.
   * Edit used to load a copy, and the send made a run beside the draft it
   * was opened from — the row a person had just edited never changed, and
   * the feed gained a twin. Editing writes back through the three routes the
   * API offers a draft, then submits the same id.
   */
  await open();
  editDraft("A portrait.");
  await waitFor(() => expect(editor().textContent).toContain("A portrait."));
  expect(screen.getByText("Editing draft")).toBeTruthy();

  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(submitRun).toHaveBeenCalledWith("run-draft"));

  expect(createRun).not.toHaveBeenCalled();
  // The model did not move, so it is not written.
  expect(setRunModel).not.toHaveBeenCalled();
  expect(setRunCharacters).toHaveBeenCalledWith("run-draft", []);
  expect(setRunLocations).toHaveBeenCalledWith("run-draft", []);
  // The plan as loaded survives a save: `origin` and `note` are carried,
  // the prompt and params are what the sheet holds.
  expect(vi.mocked(patchRunPlan).mock.calls[0]).toEqual([
    "run-draft",
    {
      version: 1,
      origin: "backfilled",
      note: "keep me",
      prompt: "A portrait.",
      params: { resolution: "1K" },
    },
  ]);
  expect(patchRunSends).toHaveBeenCalledWith("run-draft", []);
  // The duplicate question reads the fingerprint the LAST write answered.
  expect(getRuns).toHaveBeenCalledWith({ project: PROJECT, fingerprint: "f-sends", include: "drafts" });
  const order = [
    vi.mocked(setRunCharacters).mock.invocationCallOrder[0]!,
    vi.mocked(patchRunPlan).mock.invocationCallOrder[0]!,
    vi.mocked(patchRunSends).mock.invocationCallOrder[0]!,
    vi.mocked(submitRun).mock.invocationCallOrder[0]!,
  ];
  expect([...order].sort((a, b) => a - b)).toEqual(order);

  // Sent: the sheet is making new runs again.
  expect(await screen.findByText("Sent")).toBeTruthy();
  await waitFor(() => expect(screen.queryByText("Editing draft")).toBeNull());
});

it("Save keeps the draft a draft, and writes the model only when it moved", async () => {
  vi.mocked(getModels).mockResolvedValue({
    "still-model": STILL,
    "other-still": { ...STILL, key: "other-still", model: "vendor/other-still", skill: "studio-media-other" },
    "motion-model": MOTION,
  });
  await open();
  editDraft("A portrait.");
  await waitFor(() => expect(editor().textContent).toContain("A portrait."));

  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(patchRunSends).toHaveBeenCalledWith("run-draft", []));
  expect(submitRun).not.toHaveBeenCalled();
  expect(createRun).not.toHaveBeenCalled();
  expect(setRunModel).not.toHaveBeenCalled();
  expect(await screen.findByText("Saved")).toBeTruthy();
  // Still editing: a save is a checkpoint, not a way out.
  expect(screen.getByText("Editing draft")).toBeTruthy();
  expect(editor().textContent).toContain("A portrait.");

  // Switching the model in the sheet writes it — drafts only, the API's rule.
  editDraft("A portrait.", { model: "vendor/other-still" });
  await waitFor(() => expect(screen.getByText(/other-still/)).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(setRunModel).toHaveBeenCalledWith("run-draft", "vendor/other-still", "studio-media-other"),
  );
  expect(submitRun).not.toHaveBeenCalled();
});

it("a draft that is gone by the time Save or Send reaches it lets the edit go and says so", async () => {
  const { ApiError } = await import("../../apis/client");
  await open();
  editDraft("A portrait.");
  await waitFor(() => expect(editor().textContent).toContain("A portrait."));

  vi.mocked(setRunCharacters).mockRejectedValueOnce(
    new ApiError("No such object: run-draft", 404, "not_found"),
  );
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Could not save the draft")).toBeTruthy();
  expect(screen.getByText(/That draft no longer exists/)).toBeTruthy();
  // Not editing any more; the words stay; the next Send makes a new run.
  expect(screen.queryByText("Editing draft")).toBeNull();
  expect(editor().textContent).toContain("A portrait.");
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(submitRun).toHaveBeenCalledWith("run-0001"));
  expect(createRun).toHaveBeenCalledTimes(1);
});

it("× on the strip leaves the draft alone; the next Send makes a new run", async () => {
  await open();
  editDraft("A portrait.");
  await waitFor(() => expect(editor().textContent).toContain("A portrait."));

  fireEvent.click(screen.getByRole("button", { name: "Stop editing this draft" }));
  expect(screen.queryByText("Editing draft")).toBeNull();
  expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  // The words stay — what changes is where they go.
  expect(editor().textContent).toContain("A portrait.");

  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(submitRun).toHaveBeenCalledWith("run-0001"));
  expect(createRun).toHaveBeenCalledTimes(1);
  expect(patchRunPlan).not.toHaveBeenCalled();
});

it("a kind switch drops the edit — the other kind's tiles are not the draft's pictures", async () => {
  await open();
  editDraft("A portrait.");
  await waitFor(() => expect(screen.getByText("Editing draft")).toBeTruthy());

  fireEvent.click(screen.getByRole("button", { name: "Video" }));
  expect(screen.queryByText("Editing draft")).toBeNull();
  expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
});

it("holds a draft whose payload already went out here, and Send anyway submits it", async () => {
  vi.mocked(getRuns).mockResolvedValue({
    runs: [
      {
        id: "run-earlier",
        project: PROJECT,
        status: "succeeded",
        kind: "image",
        model: "vendor/still-model",
        created: "2026-08-30T00:00:00Z",
        cost: null,
        thumb: null,
        fingerprint: "f1",
      },
    ],
    cursor: null,
  });
  await open();
  fill("A portrait.");
  await waitFor(() => expect(editor().textContent).toContain("A portrait."));

  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(
    await screen.findByText("This request has been run here before"),
  ).toBeTruthy();
  expect(submitRun).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "Send anyway" }));
  await waitFor(() => expect(submitRun).toHaveBeenCalledWith("run-0001"));
  // The held draft is what goes out — no second draft.
  expect(createRun).toHaveBeenCalledTimes(1);
});

it("a template pick lands filled, not as the citations it was written with", async () => {
  vi.mocked(getTemplates).mockResolvedValue({
    blocks: { scale: "Shot at eye level." },
    templates: [
      {
        id: "tpl-1",
        name: "Face front",
        prompt: "A face, front on. @block.scale @character.1.top",
        description: "",
        tags: [],
      },
    ],
  });
  vi.mocked(expandTemplate).mockResolvedValue({
    prompt: "A face, front on. Shot at eye level. Wearing a plain grey T-shirt",
    characters: 1,
  });
  await open();
  fill("draft");
  fireEvent.click(await screen.findByRole("button", { name: "Template" }));
  fireEvent.click(await screen.findByRole("option", { name: /Face front/ }));

  await waitFor(() =>
    expect(editor().textContent).toContain("Wearing a plain grey T-shirt"),
  );
  // The citations are gone from the box: what is in it is what goes out.
  expect(editor().textContent).not.toContain("@block.scale");
  expect(vi.mocked(expandTemplate).mock.calls[0]![0]).toBe(
    "A face, front on. @block.scale @character.1.top",
  );
});

it("a template with nothing to cite is not sent to the API to be filled", async () => {
  vi.mocked(getTemplates).mockResolvedValue({
    blocks: {},
    templates: [
      {
        id: "tpl-1",
        name: "Face front",
        prompt: "A face, front on.",
        description: "",
        tags: [],
      },
    ],
  });
  await open();
  fill("draft");
  fireEvent.click(await screen.findByRole("button", { name: "Template" }));
  fireEvent.click(await screen.findByRole("option", { name: /Face front/ }));

  await waitFor(() =>
    expect(editor().textContent).toContain("A face, front on."),
  );
  expect(expandTemplate).not.toHaveBeenCalled();
});

it("a fill the API refuses leaves the template in the box and says why", async () => {
  vi.mocked(getTemplates).mockResolvedValue({
    blocks: {},
    templates: [
      {
        id: "tpl-1",
        name: "Two up",
        prompt: "@character.2.top",
        description: "",
        tags: [],
      },
    ],
  });
  vi.mocked(expandTemplate).mockRejectedValue(
    new Error("this prompt cites @character.2.top, and this run binds 0."),
  );
  await open();
  fill("draft");
  fireEvent.click(await screen.findByRole("button", { name: "Template" }));
  fireEvent.click(await screen.findByRole("option", { name: /Two up/ }));

  expect(
    await screen.findByText(/this run binds 0/),
  ).toBeTruthy();
  expect(editor().textContent).toContain("@character.2.top");
});

it("attachments show as thumbs in their role cell with a way off; a frame switches to video", async () => {
  await open();
  api.attach(FACE, "reference");
  await waitFor(() => expect(strip()).toBeTruthy());

  const reference = within(strip()).getByRole("group", { name: "Image refs" });
  expect(within(reference).getByTitle(/^Image refs · /)).toBeTruthy();
  expect(
    within(reference).getByRole("button", { name: "Remove face-01.png" }),
  ).toBeTruthy();

  api.attach({ ...FACE, node: "node-frame", name: "out-2.png" }, "start");
  await waitFor(() =>
    expect(
      within(strip()).getByRole("group", { name: "Start frame" }),
    ).toBeTruthy(),
  );
  expect(
    within(within(strip()).getByRole("group", { name: "Start frame" })).getByRole(
      "button",
      {
        name: "Remove out-2.png",
      },
    ),
  ).toBeTruthy();

  // Back on image, the reference is still there, and × takes it off.
  fireEvent.click(screen.getByRole("button", { name: "Image" }));
  fireEvent.click(
    within(strip()).getByRole("button", { name: "Remove face-01.png" }),
  );
  expect(
    screen.queryByRole("button", { name: "Remove face-01.png" }),
  ).toBeNull();
});

/**
 * The order of the references is the order they are sent in and the number
 * the prompt cites, so it can be changed in place: an arrow key on a focused
 * tile, or a drag along the row. jsdom lays nothing out, so the drag is
 * driven with tiles told where they are.
 */
it("a reference moves along the row by arrow key and by drag, and its caption follows", async () => {
  await open();
  api.attach(FACE, "reference");
  api.attach({ ...FACE, node: "node-2", name: "face-02.png" }, "reference");
  api.attach({ ...FACE, node: "node-3", name: "face-03.png" }, "reference");
  await waitFor(() =>
    expect(within(strip()).getAllByTitle(/^Image refs · /)).toHaveLength(3),
  );
  const captions = () =>
    within(strip())
      .getAllByRole("button", { name: /^Image \d — / })
      .map((each) => each.getAttribute("aria-label"));
  expect(captions()).toEqual([
    "Image 1 — face-01.png",
    "Image 2 — face-02.png",
    "Image 3 — face-03.png",
  ]);

  // ← on the third puts it second; → on the first would put it second too.
  fireEvent.keyDown(within(strip()).getByRole("button", { name: /^Image \d — face-03/ }), { key: "ArrowLeft" });
  expect(captions()).toEqual([
    "Image 1 — face-01.png",
    "Image 2 — face-03.png",
    "Image 3 — face-02.png",
  ]);
  // ← on the first goes nowhere.
  fireEvent.keyDown(within(strip()).getByRole("button", { name: /^Image \d — face-01/ }), { key: "ArrowLeft" });
  expect(captions()[0]).toBe("Image 1 — face-01.png");

  // A mouse drag: tiles 72px wide at x = 0, 80, 160. Take the first, move it
  // past the middle of the third.
  const tiles = Array.from(strip().querySelectorAll<HTMLElement>("[data-ref-position]"));
  tiles.forEach((tile, at) => {
    tile.getBoundingClientRect = () =>
      ({ left: at * 80, right: at * 80 + 72, width: 72, top: 0, bottom: 72, height: 72 }) as DOMRect;
  });
  const first = tiles[0]!;
  // The grip is the strip at the tile's foot; the picture is a press.
  fireEvent.pointerDown(first.querySelector("button")!, { pointerId: 1, pointerType: "mouse", button: 0, clientX: 10, clientY: 10 });
  expect(first.hasAttribute("data-dragging")).toBe(false);
  const grip = first.querySelector("[data-ref-grip]")!;
  fireEvent.pointerDown(grip, { pointerId: 1, pointerType: "mouse", button: 0, clientX: 10, clientY: 60 });
  expect(first.hasAttribute("data-dragging")).toBe(true);
  fireEvent.pointerMove(grip, { pointerId: 1, pointerType: "mouse", clientX: 210, clientY: 60 });
  fireEvent.pointerUp(grip, { pointerId: 1, pointerType: "mouse", clientX: 210, clientY: 60 });
  expect(first.hasAttribute("data-dragging")).toBe(false);
  expect(captions()).toEqual([
    "Image 1 — face-03.png",
    "Image 2 — face-02.png",
    "Image 3 — face-01.png",
  ]);
  // The release is not a press: no preview opened.
  expect(screen.queryByRole("dialog")).toBeNull();
});

/**
 * A picture dropped on the sheet but on no tile still lands, as a reference —
 * a drag from a viewer brings the sheet up under the pointer, and a drop an
 * inch from the tile must not be a drop into nothing. A drop that is not a
 * node (a file from the desktop) is refused.
 */
it("a node dropped anywhere on the sheet attaches as a reference", async () => {
  await open();
  const sheet = document.querySelector("[data-create-bar]")!;
  const carrying = (types: string[], payload?: string) => ({
    dataTransfer: {
      types,
      getData: () => payload ?? "",
      dropEffect: "none",
    },
  });

  fireEvent.drop(sheet, carrying(["Files"]));
  expect(screen.queryByTitle(/^Image refs · /)).toBeNull();

  const over = fireEvent.dragOver(sheet, carrying(["application/x-studio-node"]));
  // `preventDefault` on dragover is what lets the drop happen at all.
  expect(over).toBe(false);
  fireEvent.drop(
    sheet,
    carrying(["application/x-studio-node"], JSON.stringify(FACE)),
  );
  await waitFor(() => expect(strip()).toBeTruthy());
  const reference = within(strip()).getByRole("group", { name: "Image refs" });
  expect(within(reference).getByTitle(/^Image refs · face-01\.png/)).toBeTruthy();
});

it("a picture out of a location's tree records where the run is shot, after who is in it", async () => {
  // A room's wide dropped beside a face: the draft names the character AND
  // the location, each as its own edge, so "every run in this room" is one
  // query — and the project's own location follows the attached one, the
  // same order `castOf` gives the cast.
  vi.mocked(getProject).mockResolvedValue({
    id: PROJECT,
    name: "A project",
    characters: [],
    locations: [{ id: "loc-project", name: "the porch" }],
  } as never);
  await open();
  const sheet = document.querySelector("[data-create-bar]")!;
  const carrying = (payload: AttachRef) => ({
    dataTransfer: {
      types: ["application/x-studio-node"],
      getData: () => JSON.stringify(payload),
      dropEffect: "none",
    },
  });
  const drop = (payload: AttachRef) => {
    fireEvent.dragOver(sheet, carrying(payload));
    fireEvent.drop(sheet, carrying(payload));
  };
  // The prompt first: `fill` seeds the bar the way a feed row does, and a
  // seed replaces whatever was attached.
  fill("At the counter.");
  await waitFor(() => expect(editor().textContent).toContain("At the counter."));
  drop(FACE);
  drop({
    node: "node-wide",
    url: "https://example.invalid/wide.png",
    name: "wide-from-door.png",
    kind: "location",
    location: "loc-kitchen",
  });
  await waitFor(() =>
    expect(within(strip()).getByTitle(/^Image refs · wide-from-door\.png/)).toBeTruthy(),
  );

  fireEvent.keyDown(editor(), { key: "Enter", metaKey: true });
  await waitFor(() => expect(createRun).toHaveBeenCalled());

  expect(vi.mocked(createRun).mock.calls[0]![0]).toMatchObject({
    characters: ["char-1"],
    locations: ["loc-kitchen", "loc-project"],
  });
});

it("off a project page, the bar asks which project and lands there after sending", async () => {
  await open("/");
  fill("A portrait.");
  await waitFor(() => expect(editor().textContent).toContain("A portrait."));

  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(submitRun).toHaveBeenCalled());
  expect(screen.getByTestId("address").textContent).toBe(`/p/${PROJECT}`);
});

it("the sheet is always drawn, and a press elsewhere folds nothing", async () => {
  await open();
  fill("A portrait.");
  api.attach(FACE, "reference");
  await waitFor(() => expect(strip()).toBeTruthy());

  leave();
  fireEvent.pointerDown(document.body);
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(strip()).toBeTruthy();
  expect(editor().textContent).toContain("A portrait.");
  expect(screen.getByRole("button", { name: "Remove face-01.png" })).toBeTruthy();
});

it("on the opened run the sheet stays away until something calls it up, and closes again", async () => {
  // Not `open()`: that waits for the placeholder, and there is no sheet to
  // hold one yet — its absence is the point.
  render(
    <MemoryRouter initialEntries={[`/p/${PROJECT}/r/run-0001`]}>
      <CreateBarProvider>
        <CreateBar />
        <Driver />
      </CreateBarProvider>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
  await screen.findByTestId("address");
  expect(document.querySelector("[data-create-bar]")).toBeNull();

  act(() => api.loadRun({ project: PROJECT, kind: "image", prompt: "Again, but warmer." }));
  await waitFor(() => expect(document.querySelector("[data-create-bar]")).toBeTruthy());
  expect(screen.getByRole("textbox", { name: "Prompt" }).textContent).toContain("Again, but warmer.");

  // The close is drawn over the viewer only: on a page the sheet is part of
  // the page, and there is nothing to close.
  fireEvent.click(screen.getByRole("button", { name: "Close the create panel" }));
  await waitFor(() => expect(document.querySelector("[data-create-bar]")).toBeNull());
});

/**
 * Pressing a picture opens it large, with the row's gestures as lines under
 * it: the moves reorder, Remove takes it off. On every screen — the drawer
 * is a side panel on a desk and a bottom sheet on a phone, the same lines.
 */
it("a picture opens a preview whose lines move it and remove it", async () => {
  await open();
  api.attach(FACE, "reference");
  api.attach({ ...FACE, node: "node-2", name: "face-02.png" }, "reference");
  await waitFor(() => expect(strip()).toBeTruthy());

  fireEvent.click(within(strip()).getByRole("button", { name: "Image 1 — face-01.png" }));
  const drawer = await screen.findByRole("dialog", { name: "Image 1 — face-01.png" });
  expect(within(drawer).getByRole("button", { name: "Move earlier" })).toHaveProperty("disabled", true);
  fireEvent.click(within(drawer).getByRole("button", { name: "Move later" }));

  // The caption follows the position: what was first is now `Image 2`, and
  // the line closed the drawer.
  await waitFor(() =>
    expect(within(strip()).getByRole("button", { name: "Image 2 — face-01.png" })).toBeTruthy(),
  );
  expect(screen.queryByRole("dialog")).toBeNull();

  fireEvent.click(within(strip()).getByRole("button", { name: "Image 1 — face-02.png" }));
  fireEvent.click(
    within(await screen.findByRole("dialog", { name: "Image 1 — face-02.png" })).getByRole("button", {
      name: "Remove",
    }),
  );
  await waitFor(() =>
    expect(within(strip()).queryByRole("button", { name: /face-02\.png/ })).toBeNull(),
  );
  expect(within(strip()).getByRole("button", { name: "Image 1 — face-01.png" })).toBeTruthy();

  // Choose… is the picker on the tile's role, where a press used to go.
  fireEvent.click(within(strip()).getByRole("button", { name: "Image 1 — face-01.png" }));
  fireEvent.click(
    within(await screen.findByRole("dialog")).getByRole("button", { name: "Choose image refs…" }),
  );
  expect(await screen.findByRole("region", { name: "Choose image refs" })).toBeTruthy();
});

/**
 * The `Image refs` tile retires once `max_refs` is met, but a picker already
 * open on it kept taking pictures past the cap — twelve reached a model that
 * takes ten, and the run failed at the provider. The picker now reads the same
 * rule: at the cap, the pictures not on the sheet are disabled and say why,
 * the title counts against the cap, and the ones on the sheet stay pressable
 * so a person can make room.
 */
it("the picker stops at the model's reference cap and says so", async () => {
  window.localStorage.clear();
  const file = (n: number) => ({
    id: `node-pick-${n}`,
    key: `pick-${n}.png`,
    name: `pick-${n}.png`,
    size: 1,
    last_modified: null,
    kind: "image" as const,
    content_type: "image/png",
    url: `https://example.invalid/pick-${n}.png`,
  });
  vi.mocked(getFolder).mockResolvedValue({
    prefix: "",
    sort: "name",
    depth: "1",
    tags: [],
    breadcrumbs: [],
    folders: [],
    files: [file(1), file(2)],
  } as never);
  await open();
  // STILL takes 4; three are already on the sheet.
  for (const n of [1, 2, 3]) api.attach({ ...FACE, node: `node-${n}`, name: `face-0${n}.png` }, "reference");
  await waitFor(() => expect(strip()).toBeTruthy());

  fireEvent.click(within(strip()).getByRole("button", { name: "Image refs" }));
  const first = await screen.findByRole("button", { name: "Attach pick-1.png" });
  expect(screen.getByText("· 3 / 4")).toBeTruthy();
  expect(first).toHaveProperty("disabled", false);

  fireEvent.click(first);

  // The fourth met the cap: the title says so, the other picture is closed
  // with the reason, and the one just attached can still come off.
  await screen.findByText("· 4 / 4");
  const second = screen.getByRole("button", { name: "Attach pick-2.png" });
  expect(second).toHaveProperty("disabled", true);
  expect(second.getAttribute("title")).toBe("This model takes at most 4 reference images.");
  // Two `Remove pick-1.png`: the strip's tile and the picker's mark. The
  // picker's is the one whose disabling would matter.
  const picker = second.closest("[data-attach-picker]") as HTMLElement;
  expect(within(picker).getByRole("button", { name: "Remove pick-1.png" })).toHaveProperty("disabled", false);
});
