import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CreateBarProvider,
  useCreateBarState,
} from "../../context/CreateBarContext";
import { TestProviders } from "../../test-providers";
import type { RunFeedRow } from "../../types";

vi.mock("../../apis/studio", () => ({
  getRuns: vi.fn(),
  submitRun: vi.fn(),
  createRun: vi.fn(),
  deleteRun: vi.fn().mockResolvedValue({ id: "run-1", files: "keep" }),
  getAsset: vi.fn(),
  getModels: vi.fn().mockResolvedValue({
    "image-upscale": {
      key: "image-upscale",
      model: "topazlabs/image-upscale",
      kind: "image",
    },
  }),
}));

import { createRun, deleteRun, getRuns, submitRun } from "../../apis/studio";
import { RunFeed, expectedOutputs } from "./RunFeed";

const list = vi.mocked(getRuns);

const NOW = Date.now();
const ago = (seconds: number) => new Date(NOW - seconds * 1_000).toISOString();

function row(over: Partial<RunFeedRow> = {}): RunFeedRow {
  return {
    id: "run-1",
    lib: "lib-1",
    project: "proj-1",
    status: "succeeded",
    kind: "image",
    engine: "studio-media-gpt-image-2",
    model: "openai/gpt-image-2",
    created: ago(120),
    updated: null,
    submitted: ago(110),
    completed: ago(60),
    error: null,
    cost: { currency: "USD", amount: 0.14, predict_time: 38 },
    thumb: null,
    plan: {
      version: 1,
      origin: "authored",
      prompt: "a portrait, 85mm",
      params: { aspect_ratio: "3:4", outputs: 2, weights: [1, 2] },
    },
    characters: ["char-1"],
    cast: [{ id: "char-1", name: "jason" }],
    sends: [
      {
        node: "node-s1",
        name: "seed-01.jpg",
        url: "/seed-01.jpg",
        content_type: "image/jpeg",
        order: 1,
        field: "input_images",
        role: "reference",
        source: { kind: "character", character: "char-1" },
      },
    ],
    outputs: [
      {
        node: "node-o1",
        name: "out-1.png",
        url: "/out-1.png",
        content_type: "image/png",
      },
      {
        node: "node-o2",
        name: "out-2.png",
        url: "/out-2.png",
        content_type: "image/png",
      },
    ],
    ...over,
  };
}

/** What the create bar now holds for its current kind — the real provider, read back. */
function Probe() {
  const state = useCreateBarState();
  const kind = state.kind;
  const held = state.attachments[kind];
  return (
    <output data-testid="bar">
      {JSON.stringify({
        kind,
        seed: {
          model: state.model[kind],
          prompt: state.prompt,
          kind,
          attachments: held.length,
        },
        attachments: held.map((a) => `${a.role}:${a.ref.node}`),
      })}
    </output>
  );
}

const bar = () => JSON.parse(screen.getByTestId("bar").textContent ?? "{}");

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
});

const onOpen = vi.fn();

async function draw(rows: RunFeedRow[], path = "/p/proj-1?tab=runs") {
  list.mockResolvedValue({ runs: rows, cursor: null });
  render(
    <MemoryRouter initialEntries={[path]}>
      <CreateBarProvider>
        <RunFeed
          projectId="proj-1"
          characters={[{ id: "char-1", name: "jason" }]}
          heroes={{}}
          onOpen={onOpen}
        />
        <Probe />
      </CreateBarProvider>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
  await waitFor(() => expect(list).toHaveBeenCalled());
}

describe("the feed", () => {
  it("asks for the feed shape, drafts included, and groups the rows by day", async () => {
    await draw([
      row({ id: "run-a", created: ago(60) }),
      row({ id: "run-b", created: ago(60 * 60 * 26) }),
      row({ id: "run-c", created: ago(60 * 60 * 24 * 6) }),
    ]);

    expect(list).toHaveBeenCalledWith(
      expect.objectContaining({
        project: "proj-1",
        view: "feed",
        include: "drafts",
      }),
    );
    const today = await screen.findByRole("region", { name: "Today" });
    expect(within(today).getAllByRole("article")).toHaveLength(1);
    expect(
      within(screen.getByRole("region", { name: "Yesterday" })).getAllByRole(
        "article",
      ),
    ).toHaveLength(1);
    // The third group is a date, and it is the third heading.
    // The filter panel is a region too; the groups are the sections.
    const regions = screen
      .getAllByRole("region")
      .filter((each) => each.tagName === "SECTION");
    expect(regions).toHaveLength(3);
    expect(regions[2]!.getAttribute("aria-label")).not.toMatch(
      /Today|Yesterday/,
    );
  });

  it("draws the plan beside the outputs: status, kind, prompt, scalar params, the model, the cast", async () => {
    await draw([row()]);

    const article = await screen.findByRole("article");
    expect(within(article).getByText("succeeded")).toBeTruthy();
    expect(within(article).getByText("image")).toBeTruthy();
    expect(within(article).getByText("a portrait, 85mm")).toBeTruthy();
    expect(within(article).getByText("aspect_ratio")).toBeTruthy();
    expect(within(article).getByText("3:4")).toBeTruthy();
    // A list is not a chip.
    expect(within(article).queryByText("weights")).toBeNull();
    expect(within(article).getByText("openai/gpt-image-2")).toBeTruthy();
    expect(
      within(article).getByRole("link", { name: /jason/ }).getAttribute("href"),
    ).toBe("/c/char-1");
    // Two outputs, two tiles, each opening the run at its own position.
    fireEvent.click(
      within(article).getByRole("button", { name: "Open Output 2 of 2" }),
    );
    expect(onOpen).toHaveBeenCalledWith(
      expect.objectContaining({ id: "run-1" }),
      1,
    );
  });

  it("searches prompts on Enter and sends the words as q", async () => {
    await draw([row()]);

    const box = screen.getByRole("textbox", { name: "Search prompts" });
    fireEvent.change(box, { target: { value: "portrait" } });
    fireEvent.keyDown(box, { key: "Enter" });

    await waitFor(() =>
      expect(list).toHaveBeenCalledWith(
        expect.objectContaining({ q: "portrait", view: "feed" }),
      ),
    );
  });
});

describe("a run in flight", () => {
  it("fills its row with shimmering tiles, the spinner and the seconds since it went out", async () => {
    await draw([
      row({
        id: "run-flying",
        status: "running",
        submitted: ago(12),
        completed: null,
        outputs: [],
        cost: null,
      }),
    ]);

    const article = await screen.findByRole("article");
    // As many tiles as the plan asked for.
    expect(within(article).getAllByTestId("in-flight-tile")).toHaveLength(2);
    expect(
      within(article).getAllByTestId("in-flight-tile")[0]!.className,
    ).toContain("studio-shimmer");
    expect(within(article).getByText("Running…")).toBeTruthy();
    expect(within(article).getByText(/^1[23]s$/)).toBeTruthy();
    expect(within(article).getByText(/sent 1[23]s ago/)).toBeTruthy();
    // The spinner is on the badge too.
    expect(
      within(article).getAllByRole("progressbar", { name: "Run running" })
        .length,
    ).toBeGreaterThanOrEqual(2);
    // Nothing spends or destroys while it is out.
    expect(within(article).queryByRole("button", { name: "Rerun" })).toBeNull();
    expect(
      within(article).queryByRole("button", { name: /Delete/ }),
    ).toBeNull();
  });

  it("counts the tiles off the plan, one when it says nothing", () => {
    expect(expectedOutputs(row({ plan: null }))).toBe(1);
    expect(
      expectedOutputs(
        row({
          plan: {
            version: 1,
            origin: "authored",
            prompt: "",
            params: { num_outputs: 4 },
          },
        }),
      ),
    ).toBe(4);
  });
});

describe("the actions", () => {
  it("Edit loads the run into the create bar", async () => {
    await draw([row()]);

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));

    expect(bar().seed).toEqual({
      model: "openai/gpt-image-2",
      prompt: "a portrait, 85mm",
      kind: "image",
      attachments: 1,
    });
  });

  it("Use in prompt attaches the output as a reference; Animate switches to video with it as the start", async () => {
    await draw([row()]);
    await screen.findByRole("article");

    fireEvent.click(
      screen.getAllByRole("button", { name: "Use in prompt" })[1]!,
    );
    expect(bar().attachments).toEqual(["reference:node-o2"]);

    fireEvent.click(screen.getAllByRole("button", { name: "Animate" })[0]!);
    expect(bar().kind).toBe("video");
    expect(bar().attachments).toEqual(["start:node-o1"]);
    expect(bar().seed.kind).toBe("video");
  });

  it("Upscale loads an image run on the upscaler with the output attached", async () => {
    await draw([row()]);
    await screen.findByRole("article");

    // The registry has to have answered first — the button reads it.
    await waitFor(() => {
      fireEvent.click(screen.getAllByRole("button", { name: "Upscale" })[0]!);
      expect(bar().seed?.model).toBe("topazlabs/image-upscale");
    });
    expect(bar().attachments).toEqual(["start:node-o1"]);
  });

  it("Rerun arms on the first press and creates then submits on the second", async () => {
    vi.mocked(createRun).mockResolvedValue({
      id: "run-new",
      fingerprint: "sha256:x",
    } as never);
    vi.mocked(submitRun).mockResolvedValue({} as never);
    await draw([row()]);

    const rerun = await screen.findByRole("button", { name: "Rerun" });
    fireEvent.click(rerun);
    expect(createRun).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Press again/ })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Press again/ }));
    await waitFor(() => expect(submitRun).toHaveBeenCalledWith("run-new"));
    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({
        project: "proj-1",
        model: "openai/gpt-image-2",
        sends: [{ field: "input_images", role: "reference", node: "node-s1" }],
      }),
    );
  });

  it("a draft offers Run, which arms first and submits second", async () => {
    vi.mocked(submitRun).mockResolvedValue({} as never);
    await draw([
      row({
        status: "draft",
        submitted: null,
        completed: null,
        outputs: [],
        cost: null,
      }),
    ]);

    const run = await screen.findByRole("button", { name: "Run" });
    fireEvent.click(run);
    expect(submitRun).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Press again/ }));
    await waitFor(() => expect(submitRun).toHaveBeenCalledWith("run-1"));
  });

  it("Delete arms, then deletes the run", async () => {
    await draw([row()]);

    const trash = await screen.findByRole("button", {
      name: "Delete this run",
    });
    fireEvent.click(trash);
    expect(deleteRun).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: /Confirm — delete this run/ }),
    );
    await waitFor(() => expect(deleteRun).toHaveBeenCalledWith("run-1"));
  });
});

describe("the shape of the frames", () => {
  it("a draft draws dashed frames the size and number its plan asks for", async () => {
    await draw([
      row({
        status: "draft",
        kind: "image",
        outputs: [],
        plan: {
          version: 1,
          origin: "authored",
          prompt: "x",
          params: { aspect_ratio: "2:3", number_of_images: 3 },
        },
      }),
    ]);
    await screen.findByRole("article");
    const frames = screen.getAllByTestId("draft-tile");
    expect(frames).toHaveLength(3);
    expect(frames[0]!.style.aspectRatio).toBe("2 / 3");
    expect(screen.getByText("Not run yet.")).toBeTruthy();
  });

  it("an output tile takes the plan's aspect ratio, not the kind's", async () => {
    await draw([
      row({
        kind: "video",
        plan: {
          version: 1,
          origin: "authored",
          prompt: "x",
          params: { aspect_ratio: "9:16", duration: 5 },
        },
      }),
    ]);
    await screen.findByRole("article");
    const tile = screen.getAllByRole("button", { name: /^Open Output/ })[0]!;
    const box = tile.querySelector("span[style]") as HTMLElement;
    expect(box.style.aspectRatio).toBe("9 / 16");
  });
});
