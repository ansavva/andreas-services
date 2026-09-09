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

import { createRun, deleteRun, getAsset, getRuns, submitRun } from "../../apis/studio";
import { RunFeed, expectedOutputs } from "./RunFeed";

const list = vi.mocked(getRuns);

/**
 * A fixed instant, and the clock the components read is set to it.
 *
 * **"26 hours ago" is not always yesterday.** Between midnight and 02:00 it
 * lands two days back, so the grouping case below failed for two hours a day
 * and passed in CI, which runs in UTC. The offsets are what these tests are
 * about; when they are measured from is not — so it is midday, fixed.
 */
const NOW = new Date("2026-09-09T12:00:00").getTime();
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

/**
 * Open one output tile's `⋮`, where every action on an output now lives.
 *
 * **Two triggers per tile, and the first is the one to press.** `ActionMenu`
 * draws the pointer's `Dropdown` and the phone's `Drawer` and hides one of them
 * in CSS, which jsdom does not apply — so both are found, and the dropdown is
 * the one whose items are `menuitem`s.
 */
function openTileMenu(tile: number) {
  const triggers = screen.getAllByRole("button", { name: /^Actions for Output/ });
  fireEvent.click(triggers[tile * 2]!);
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

beforeEach(() => {
  // `shouldAdvanceTime` so the query client's own timers still run — the
  // clock is fixed for what the rows are dated against, not stopped.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(NOW);
});
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

  it("Use as reference attaches the output; Start frame switches to video with it as the start", async () => {
    await draw([row()]);
    await screen.findByRole("article");

    openTileMenu(1);
    fireEvent.click(screen.getByRole("menuitem", { name: "Use as reference" }));
    expect(bar().attachments).toEqual(["reference:node-o2"]);

    openTileMenu(0);
    fireEvent.click(screen.getByRole("menuitem", { name: "Start frame" }));
    expect(bar().kind).toBe("video");
    expect(bar().attachments).toEqual(["start:node-o1"]);
    expect(bar().seed.kind).toBe("video");
  });

  it("Upscale loads an image run on the upscaler with the output attached", async () => {
    await draw([row()]);
    await screen.findByRole("article");

    // The registry has to have answered first — the item reads it.
    await waitFor(() => {
      openTileMenu(0);
      fireEvent.click(screen.getByRole("menuitem", { name: "Upscale" }));
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
    // A clip is not a reference — a reference is a picture — so the tile's
    // menu offers no way to attach it as one. It did, and the send was refused.
    openTileMenu(0);
    expect(screen.queryByRole("menuitem", { name: "Use as reference" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "Start frame" })).toBeNull();
    expect(screen.getByRole("menuitem", { name: "Run again with this" })).toBeTruthy();
  });
});

describe("a pointer at a node that is gone", () => {
  /**
   * The whole feed used to die on this, and it took two production projects
   * with it: `GET /api/runs?view=feed` reports a send whose node the catalog
   * cannot find as the bare `{node}` it honestly is — no `name`, no `url` —
   * and `MediaThumb` did `new URL(undefined)`, caught the throw, and then did
   * `undefined.split("?")` in the fallback. `Cannot read properties of
   * undefined (reading 'split')`, and nothing on the page rendered.
   */
  it("draws the row, with the send marked unavailable rather than crashing it", async () => {
    await draw([
      row({
        sends: [
          // Exactly what `GET /api/runs?view=feed` answers for a send whose
          // node the catalog cannot find: the pointer, its role, and the
          // `{kind: "object"}` fallback `_source_for` supplies. No name, no url.
          {
            node: "node-gone",
            order: 1,
            field: "input_images",
            role: "reference",
            source: { kind: "object" },
          },
        ],
      }),
    ]);

    const article = await screen.findByRole("article");
    // The row is there, and so is everything after the sends.
    expect(within(article).getByText("a portrait, 85mm")).toBeTruthy();
    expect(within(article).getAllByRole("button", { name: /^Open Output/ })).toHaveLength(2);

    const sent = within(article).getByLabelText("Sent");
    expect(within(sent).getByText("Unavailable")).toBeTruthy();
    // Not `Image 1 · undefined`. The role is drawn under the thumb as well,
    // so a send whose node is gone still says what it was for.
    expect(sent.querySelector("[title]")?.getAttribute("title")).toBe(
      "Image 1 · deleted file",
    );
    expect(within(sent).getByText("Image 1")).toBeTruthy();
    // **And it is not a link.** The object behind it is gone, so the only
    // place a link could lead is an error page — see `SendThumbs`.
    expect(within(sent).queryByRole("link")).toBeNull();
  });

  /**
   * **A send opens, and ⌘-click opens it in a tab.** They were pictures and
   * nothing else: a press did nothing at all, on the feed row and in the
   * opened run alike, while everything around them opened. A real `<a href>`
   * is what gives the browser its own gestures back — see `SendThumbs`.
   */
  /**
   * **Which one was the start frame** — the question a video run is opened
   * with, and the one thing a flat row of identical squares could not answer.
   * The role was a `title` and nothing else: invisible on a touch screen, and
   * on a pointer only if you knew to hover.
   */
  it("says what each picture was sent as, frames first and references numbered", async () => {
    await draw([
      row({
        sends: [
          // Out of order on purpose: `order` is what the model was handed, and
          // the reading order is not it.
          { node: "node-r2", name: "b.jpg", url: "/b.jpg", order: 4, field: "input_images", role: "reference", source: { kind: "object" } },
          { node: "node-end", name: "end.png", url: "/end.png", order: 2, field: "end_image", role: "end", source: { kind: "object" } },
          { node: "node-r1", name: "a.jpg", url: "/a.jpg", order: 3, field: "input_images", role: "reference", source: { kind: "object" } },
          { node: "node-start", name: "start.png", url: "/start.png", order: 1, field: "start_image", role: "start", source: { kind: "object" } },
        ],
      }),
    ]);
    const sent = within(await screen.findByRole("article")).getByLabelText("Sent");

    expect(
      within(sent)
        .getAllByRole("link")
        .map((link) => link.getAttribute("title")),
    ).toEqual([
      "Start frame · start.png",
      "End frame · end.png",
      // Numbered by their place among the REFERENCES, in send order — which is
      // what `Image 2` means in a prompt.
      "Image 1 · a.jpg",
      "Image 2 · b.jpg",
    ]);
  });

  it("links each sent picture to the file, with no sequence around it", async () => {
    await draw([row()]);
    const article = await screen.findByRole("article");

    const link = within(within(article).getByLabelText("Sent")).getByRole("link");
    // `/o/<node>` and no `?in=`: a send comes from somewhere else, so there is
    // no feed here to walk.
    expect(link.getAttribute("href")).toBe("/o/node-s1");
  });

  it("draws an output the same way, and asks for no re-sign", async () => {
    await draw([
      row({ outputs: [{ node: "node-gone" }], thumb: null }),
    ]);

    const article = await screen.findByRole("article");
    expect(within(article).getByText("Unavailable")).toBeTruthy();
    expect(vi.mocked(getAsset)).not.toHaveBeenCalled();
  });
});
