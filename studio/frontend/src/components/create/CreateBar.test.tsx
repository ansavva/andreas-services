import {
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
  getProject: vi.fn(),
  getProjects: vi.fn().mockResolvedValue([]),
  getTemplates: vi.fn(),
  expandTemplate: vi.fn(),
  createRun: vi.fn(),
  submitRun: vi.fn(),
  patchRunPlan: vi.fn(),
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
  createRun,
  expandTemplate,
  getModels,
  getProject,
  getRuns,
  getTemplates,
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
  vi.mocked(createRun).mockResolvedValue(created());
  vi.mocked(submitRun).mockResolvedValue({
    id: "run-0001",
    status: "pending",
  } as never);
  vi.mocked(getRuns).mockResolvedValue({ runs: [], cursor: null });
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

it("Enter creates the draft and then submits it, in that order; Shift+Enter does not", async () => {
  await open();
  fill("A portrait.");
  await waitFor(() => expect(editor().textContent).toContain("A portrait."));

  fireEvent.keyDown(editor(), { key: "Enter", shiftKey: true });
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(createRun).not.toHaveBeenCalled();

  fireEvent.keyDown(editor(), { key: "Enter" });
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
        prompt: "A face, front on. {block.scale} {character.1.top}",
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
  wake();
  fill("draft");
  fireEvent.click(await screen.findByRole("button", { name: "Template" }));
  fireEvent.click(await screen.findByRole("button", { name: /Face front/ }));

  await waitFor(() =>
    expect(editor().textContent).toContain("Wearing a plain grey T-shirt"),
  );
  // The citations are gone from the box: what is in it is what goes out.
  expect(editor().textContent).not.toContain("{block.scale}");
  expect(vi.mocked(expandTemplate).mock.calls[0]![0]).toBe(
    "A face, front on. {block.scale} {character.1.top}",
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
  fireEvent.click(await screen.findByRole("button", { name: /Face front/ }));

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
        prompt: "{character.2.top}",
        description: "",
        tags: [],
      },
    ],
  });
  vi.mocked(expandTemplate).mockRejectedValue(
    new Error("this prompt cites {character.2.top}, and this run binds 0."),
  );
  await open();
  wake();
  fill("draft");
  fireEvent.click(await screen.findByRole("button", { name: "Template" }));
  fireEvent.click(await screen.findByRole("button", { name: /Two up/ }));

  expect(
    await screen.findByText(/this run binds 0/),
  ).toBeTruthy();
  expect(editor().textContent).toContain("{character.2.top}");
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
