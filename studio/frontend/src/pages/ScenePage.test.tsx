import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { RunAsset, SceneCut, SceneRecord } from "../types";

// The feed is the project's own component, tested there; here it is a stub
// that says which project and which scene it was asked for.
vi.mock("../components/project/RunFeed", () => ({
  RunFeed: ({ projectId }: { projectId: string }) => {
    const location = useLocation();
    return <div>feed for {projectId} {new URLSearchParams(location.search).get("scene")}</div>;
  },
}));

// `getProject` and `getCharacters` are here for the project's bar, which the
// page draws above its own trail — the name, the counts, the chips.
vi.mock("../apis/studio", () => ({
  getScene: vi.fn(),
  setSceneRuns: vi.fn(),
  deleteScene: vi.fn(),
  deleteProject: vi.fn(),
  getProject: vi.fn(),
  getCharacters: vi.fn().mockResolvedValue([]),
}));

import { deleteScene, getProject, getScene, setSceneRuns } from "../apis/studio";
import { ScenePage } from "./ScenePage";
import { TestProviders } from "../test-providers";

const read = vi.mocked(getScene);
const write = vi.mocked(setSceneRuns);
const project = vi.mocked(getProject);
const destroy = vi.mocked(deleteScene);

const ID = "scene-0001";

function asset(node: string): RunAsset {
  return { node, name: `${node}.mp4`, url: `https://signed/${node}`, content_type: "video/mp4" };
}

function cut(id: string, output: RunAsset | null = null): SceneCut {
  return { id, project: "proj-0001", status: output ? "succeeded" : "draft", kind: "video",
           model: "kwaivgi/kling", created: "2026-08-25T00:00:00Z", scene: ID, output,
           thumb: output };
}

function record(over: Partial<SceneRecord> = {}): SceneRecord {
  return {
    id: ID,
    project: "proj-0001",
    name: "Light flex",
    status: "planned",
    movies: [],
    created: "2026-08-25T00:00:00Z",
    folder: "node-folder",
    output: null,
    runs: [],
    frames: [],
    ...over,
  };
}

/** Where the router ended up, so a navigation can be asserted on. */
let landed = "";

function Land() {
  const location = useLocation();
  landed = `${location.pathname}${location.search}`;
  return <div>landed</div>;
}

function draw(scene: SceneRecord) {
  read.mockResolvedValue(scene);
  project.mockResolvedValue({
    id: "proj-0001",
    name: "A project",
    counts: { runs: 3, scenes: 1, movies: 0 },
    characters: [],
    locations: [],
  } as never);
  landed = "";
  return render(
    <MemoryRouter initialEntries={[`/s/${ID}`]}>
      <Routes>
        <Route path="/s/:sceneId" element={<ScenePage />} />
        <Route path="/o/:nodeId" element={<Land />} />
        <Route path="/p/:projectId/r/:runId" element={<Land />} />
        <Route path="/p/:projectId" element={<Land />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("draws the cut in order, with a row for a run that has not rendered", async () => {
  draw(record({ runs: [cut("run-a", asset("node-a")), cut("run-b")] }));

  const rows = await screen.findAllByRole("link", { name: /kwaivgi\/kling/ });
  expect(rows).toHaveLength(2);
  expect(screen.getByText("not rendered")).toBeTruthy();
  expect(screen.getByText(/1 not rendered yet/)).toBeTruthy();
});

it("narrows the feed to this scene and keeps it narrowed", async () => {
  draw(record());
  expect(await screen.findByText(`feed for proj-0001 ${ID}`)).toBeTruthy();
});

it("moves a run down by writing the whole cut back, and merges the answer in", async () => {
  draw(record({ runs: [cut("run-a", asset("node-a")), cut("run-b", asset("node-b"))] }));
  write.mockResolvedValue({ id: ID, runs: [cut("run-b", asset("node-b")), cut("run-a", asset("node-a"))] });

  const buttons = await screen.findAllByRole("button", { name: "Move down" });
  fireEvent.click(buttons[0]!);

  await waitFor(() => expect(write).toHaveBeenCalledWith(ID, ["run-b", "run-a"]));
  // One GET only: the page swapped the rows the route answered with.
  await waitFor(() => {
    const links = screen.getAllByRole("link", { name: /kwaivgi\/kling/ });
    expect((links[0] as HTMLAnchorElement).getAttribute("href")).toContain("run-b");
  });
  expect(read).toHaveBeenCalledTimes(1);
});

it("removes a run from the cut without refetching", async () => {
  draw(record({ runs: [cut("run-a", asset("node-a"))] }));
  write.mockResolvedValue({ id: ID, runs: [] });

  fireEvent.click(await screen.findByRole("button", { name: "Remove from the cut" }));

  await waitFor(() => expect(write).toHaveBeenCalledWith(ID, []));
  expect(await screen.findByText("Nothing in the cut yet.")).toBeTruthy();
});

it("leads with the latest take, one at a time, and a tab per earlier one", async () => {
  draw(record({ output: asset("node-take"), cuts: [asset("node-earlier")], status: "assembled" }));

  expect(await screen.findByText("Takes")).toBeTruthy();
  // Newest first, numbered from the total; the latest is the one drawn.
  // Scoped to the takes' own strip: the project's tabs sit above it.
  const tabs = within(screen.getByRole("tablist", { name: "Takes" })).getAllByRole("tab");
  expect(tabs.map((tab) => tab.textContent)).toEqual(["Take 2latest", "Take 1"]);
  expect(screen.queryByText("earlier")).toBeNull();
  // The tile opens the viewer over the scene's takes, as a real link.
  const open = screen.getByRole("link", { name: "Open node-take.mp4" }) as HTMLAnchorElement;
  expect(open.getAttribute("href")).toBe(`/o/node-take?in=scene%3A${ID}`);

  // An earlier take is picked from the strip and marked as earlier.
  fireEvent.click(tabs[1]!);
  expect(await screen.findByText("earlier")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Open node-earlier.mp4" })).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Open node-take.mp4" })).toBeNull();
});

it("draws a single take with no strip", async () => {
  draw(record({ output: asset("node-take"), status: "assembled" }));

  expect(await screen.findByText("The take")).toBeTruthy();
  expect(screen.queryByRole("tablist", { name: "Takes" })).toBeNull();
});

/**
 * The scene was opened from the project's Scenes tab, and the page used to
 * drop the bar — a different title, no strip — so it read as leaving the
 * project. Now it is the project's bar with Scenes selected, and the scene
 * is a trail under the tabs, the way the Files tab draws a folder.
 */
it("draws the project's bar on Scenes, and the scene as a trail under it", async () => {
  draw(record());

  await screen.findByRole("heading", { name: "A project" });
  expect(screen.getByRole("tab", { name: "Scenes" }).getAttribute("aria-selected")).toBe("true");
  expect(screen.getByRole("tab", { name: "Runs" }).getAttribute("aria-selected")).toBe("false");

  const crumb = screen.getByRole("link", { name: "A project" }) as HTMLAnchorElement;
  expect(crumb.getAttribute("href")).toBe("/p/proj-0001?tab=scenes");
  expect(screen.getByText("Light flex").getAttribute("aria-current")).toBe("page");
});

/** The other tabs are the project's own, so picking one goes there. */
it("leaves for the project on the tab picked", async () => {
  draw(record());

  fireEvent.click(await screen.findByRole("tab", { name: "Movies" }));

  await screen.findByText("landed");
  expect(landed).toBe("/p/proj-0001?tab=movies");
});

it("deletes from the page bar and lands on the project", async () => {
  draw(record());
  destroy.mockResolvedValue({ id: ID, files: "delete" } as never);

  await screen.findByText("Light flex");
  fireEvent.click(screen.getAllByRole("button", { name: "Actions for Light flex" })[0]!);
  fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
  const dialog = await screen.findByRole("alertdialog");
  const action = within(dialog).getByRole("button", { name: "Delete" }) as HTMLButtonElement;
  fireEvent.change(within(dialog).getByLabelText("Confirm"), { target: { value: "Light flex" } });
  await waitFor(() => expect(action.disabled).toBe(false));
  fireEvent.click(action);

  await waitFor(() => expect(destroy).toHaveBeenCalledWith(ID, "delete"));
  await waitFor(() => expect(landed).toBe("/p/proj-0001"));
});
