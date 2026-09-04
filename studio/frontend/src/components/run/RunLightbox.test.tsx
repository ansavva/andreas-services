import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CreateBarProvider,
  useCreateBarState,
} from "../../context/CreateBarContext";
import { SidebarProvider, useShellSidebar } from "../../context/SidebarContext";
import { TestProviders } from "../../test-providers";
import type { RunFeedRow, RunRecord } from "../../types";

vi.mock("../../apis/studio", () => ({
  getRuns: vi.fn(),
  getRun: vi.fn(),
  getNodeText: vi.fn(),
  getRunPayloadPreview: vi.fn(),
  submitRun: vi.fn(),
  createRun: vi.fn(),
  deleteRun: vi.fn(),
  getAsset: vi.fn(),
  getModels: vi.fn().mockResolvedValue({}),
}));
// The player is its own suite; here the stage only has to name what it shows.
vi.mock("../media/MediaPlayer", () => ({
  MediaPlayer: ({ name, isVideo }: { name: string; isVideo?: boolean }) => (
    <div data-testid="stage">
      {isVideo ? "video" : "image"}: {name}
    </div>
  ),
}));

import { deleteRun, getNodeText, getRun, getRuns } from "../../apis/studio";
import { RunLightbox } from "./RunLightbox";

const list = vi.mocked(getRuns);
const read = vi.mocked(getRun);
const text = vi.mocked(getNodeText);

const NOW = Date.now();
const ago = (seconds: number) => new Date(NOW - seconds * 1_000).toISOString();

function row(over: Partial<RunFeedRow> = {}): RunFeedRow {
  return {
    id: "run-2",
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
    thumb: { node: "node-o1", url: "/out-1.png" },
    plan: {
      version: 1,
      origin: "authored",
      prompt: "a portrait, 85mm",
      params: { aspect_ratio: "3:4" },
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
        size: 2048,
      },
      {
        node: "node-o2",
        name: "out-2.png",
        url: "/out-2.png",
        content_type: "image/png",
        size: 4096,
      },
    ],
    ...over,
  };
}

function record(over: Partial<RunRecord> = {}): RunRecord {
  const base = row();
  return {
    id: base.id,
    lib: base.lib,
    project: base.project,
    status: base.status,
    kind: base.kind,
    engine: base.engine ?? "",
    model: base.model,
    prediction_id: "9c1e2f3a4b5c",
    created: base.created,
    submitted: base.submitted ?? null,
    completed: base.completed ?? null,
    bindings: {},
    sends: base.sends,
    plan: base.plan,
    characters: base.characters,
    folder: "node-folder",
    outputs: base.outputs,
    scenes: [],
    cost: base.cost,
    error: null,
    payload: {
      prompt: "node-prompt",
      request: "node-request",
      response: "node-response",
    },
    ...over,
  };
}

/** Where the router is, and whether the rail is collapsed — read back. */
function Probe() {
  const location = useLocation();
  const { collapsed } = useShellSidebar();
  const bar = useCreateBarState();
  return (
    <>
      <output data-testid="address">
        {location.pathname + location.search}
      </output>
      <output data-testid="collapsed">{String(collapsed)}</output>
      <output data-testid="attachments">
        {bar.attachments[bar.kind]
          .map((a) => `${a.role}:${a.ref.node}`)
          .join(",")}
      </output>
    </>
  );
}

// The route element reads the run id off the address the way `ProjectPage`
// reads it off its params.
function At({ runId }: { runId: string }) {
  return (
    <>
      <RunLightbox
        projectId="proj-1"
        runId={runId}
        characters={[{ id: "char-1", name: "jason" }]}
        heroes={{}}
      />
      <Probe />
    </>
  );
}

function RouteElement() {
  const location = useLocation();
  const runId = location.pathname.split("/r/")[1] ?? "";
  return <At runId={runId} />;
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  list.mockResolvedValue({
    runs: [row({ id: "run-2" }), row({ id: "run-1", created: ago(400) })],
    cursor: null,
  });
  read.mockResolvedValue(record());
  text.mockResolvedValue({
    id: "node-request",
    name: "request.json",
    language: "json",
    truncated: false,
    content: '{"input":{"prompt":"a portrait"}}',
  } as never);
});

async function draw(path = "/p/proj-1/r/run-2?tab=runs") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <SidebarProvider>
        <CreateBarProvider>
          <Routes>
            <Route path="/p/:projectId" element={<Probe />} />
            <Route path="/p/:projectId/r/:runId" element={<RouteElement />} />
          </Routes>
        </CreateBarProvider>
      </SidebarProvider>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
  await screen.findByRole("dialog", { name: "Run" });
}

const address = () => screen.getByTestId("address").textContent;
const collapsed = () => screen.getByTestId("collapsed").textContent;

describe("the opened run", () => {
  it("opens on the route, collapses the rail, and puts it back on close", async () => {
    await draw();

    expect(collapsed()).toBe("true");
    await screen.findByTestId("stage");
    expect(screen.getByTestId("stage").textContent).toBe("image: out-1.png");

    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(address()).toBe("/p/proj-1?tab=runs"));
    expect(collapsed()).toBe("false");
    expect(screen.queryByRole("dialog", { name: "Run" })).toBeNull();
  });

  it("draws the run's plan in the rail and fetches the record for the rest", async () => {
    await draw();
    const rail = await screen.findByRole("complementary", {
      name: "Run details",
    });

    expect(within(rail).getByText("succeeded")).toBeTruthy();
    expect(within(rail).getByText("a portrait, 85mm")).toBeTruthy();
    expect(within(rail).getByText("aspect_ratio")).toBeTruthy();
    expect(within(rail).getByText("openai/gpt-image-2")).toBeTruthy();
    expect(
      within(rail).getByRole("link", { name: /jason/ }).getAttribute("href"),
    ).toBe("/c/char-1");
    expect(within(rail).getByTitle("reference · seed-01.jpg")).toBeTruthy();
    await waitFor(() =>
      expect(within(rail).getByText(/prediction 9c1e2f3a…/)).toBeTruthy(),
    );
    expect(read).toHaveBeenCalledWith("run-2");
    // The rail's Folder is the run's own folder, off the record.
    expect(
      within(rail).getByRole("link", { name: "Folder" }).getAttribute("href"),
    ).toBe("/f/node-folder");
  });

  it("steps between the project's runs on the arrow keys and the strip, replacing the address", async () => {
    await draw();
    await screen
      .findByRole("region", { name: "Runs in this project" })
      .catch(() => null);

    fireEvent.keyDown(window, { key: "ArrowRight" });
    await waitFor(() => expect(address()).toBe("/p/proj-1/r/run-1?tab=runs"));

    fireEvent.keyDown(window, { key: "ArrowLeft" });
    await waitFor(() => expect(address()).toBe("/p/proj-1/r/run-2?tab=runs"));

    // The strip: one tile per run, the open one marked, the other a press.
    const strip = screen.getByLabelText("Runs in this project");
    const tiles = within(strip).getAllByRole("button", { name: /^Run / });
    expect(tiles).toHaveLength(2);
    expect(tiles[0]!.getAttribute("aria-current")).toBe("true");
    fireEvent.click(tiles[1]!);
    await waitFor(() => expect(address()).toBe("/p/proj-1/r/run-1?tab=runs"));
  });

  it("switches the stage between the run's outputs", async () => {
    await draw();
    await screen.findByTestId("stage");

    fireEvent.click(screen.getByRole("button", { name: "Output 2 of 2" }));
    expect(screen.getByTestId("stage").textContent).toBe("image: out-2.png");
    expect(screen.getByText(/out-2\.png · 4\.0 KB/)).toBeTruthy();
  });

  it("loads a document only when the Request row is opened and the document pressed", async () => {
    await draw();
    await screen.findByRole("complementary", { name: "Run details" });
    await waitFor(() => expect(read).toHaveBeenCalled());

    expect(text).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Request/ }));
    await screen.findByRole("button", { name: "request.json" });
    expect(text).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "request.json" }));
    await waitFor(() => expect(text).toHaveBeenCalledWith("node-request"));
    await screen.findByText(/"prompt": "a portrait"/);
  });

  it("draws a run the feed has not loaded off its record, naming the cast", async () => {
    list.mockResolvedValue({ runs: [], cursor: null });
    await draw();

    const rail = await screen.findByRole("complementary", {
      name: "Run details",
    });
    expect(within(rail).getByText("a portrait, 85mm")).toBeTruthy();
    expect(within(rail).getByRole("link", { name: /jason/ })).toBeTruthy();
    // One run is no strip.
    expect(screen.queryByLabelText("Runs in this project")).toBeNull();
  });

  it("Use as reference hands the output on the stage to the create bar", async () => {
    await draw();
    await screen.findByTestId("stage");

    fireEvent.click(screen.getByRole("button", { name: "Output 2 of 2" }));
    fireEvent.click(screen.getByRole("button", { name: "Use as reference" }));
    expect(screen.getByTestId("attachments").textContent).toBe(
      "reference:node-o2",
    );
  });

  it("Trash arms, then deletes and returns to the project", async () => {
    vi.mocked(deleteRun).mockResolvedValue({ id: "run-2", files: "keep" });
    await draw();
    await screen.findByTestId("stage");

    fireEvent.click(screen.getByRole("button", { name: "Trash" }));
    expect(deleteRun).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm — delete this run" }),
    );
    await waitFor(() => expect(deleteRun).toHaveBeenCalledWith("run-2"));
  });

  it("shows the shimmer and the counter for a run in flight, and offers nothing that spends", async () => {
    list.mockResolvedValue({
      runs: [
        row({
          id: "run-2",
          status: "running",
          submitted: ago(12),
          completed: null,
          outputs: [],
          thumb: null,
          cost: null,
        }),
      ],
      cursor: null,
    });
    read.mockResolvedValue(record({ status: "running", outputs: [] }));
    await draw();

    expect(await screen.findByTestId("in-flight-stage")).toBeTruthy();
    expect(screen.getByText("Running…")).toBeTruthy();
    expect(screen.getByText(/^1[23]s$/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Rerun" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Trash" })).toBeNull();
    expect(screen.getByRole("button", { name: "Edit" })).toBeTruthy();
  });
});

it("the strip and the arrows skip runs with nothing to show", async () => {
  list.mockResolvedValue({
    runs: [
      row({ id: "run-a" }),
      row({ id: "run-draft", status: "draft", outputs: [], created: ago(100) }),
      row({
        id: "run-failed",
        status: "failed",
        outputs: [],
        created: ago(200),
      }),
      row({ id: "run-b", created: ago(300) }),
    ],
    cursor: null,
  });
  await draw("/p/proj-1/r/run-a?tab=runs");

  const strip = await screen.findByLabelText("Runs in this project");
  // Two runs have outputs (the open one and run-b); the draft and the
  // failure are not offered.
  expect(within(strip).getAllByRole("button", { name: /^Run / })).toHaveLength(
    2,
  );

  fireEvent.keyDown(document, { key: "ArrowRight" });
  await waitFor(() => expect(address()).toContain("/r/run-b"));
});
