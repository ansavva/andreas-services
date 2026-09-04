import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { ProjectRecord } from "../types";
import { TestProviders } from "../test-providers";

vi.mock("../components/browse/FolderTab", () => ({ FolderTab: () => <div>files</div> }));
// The feed and the lightbox have suites of their own; what this file is about
// is the page around them — the tabs, the header, the delete gate.
vi.mock("../components/project/RunFeed", () => ({
  RunFeed: ({ projectId }: { projectId: string }) => <div>feed for {projectId}</div>,
}));
vi.mock("../components/run/RunLightbox", () => ({
  RunLightbox: ({ runId }: { runId: string }) => <div>lightbox {runId}</div>,
}));
vi.mock("../hooks/useInFlightRuns", () => ({ useInFlightRuns: vi.fn(() => ({})) }));

vi.mock("../apis/studio", () => ({
  getProject: vi.fn(),
  getProjectScenes: vi.fn().mockResolvedValue([]),
  getProjectMovies: vi.fn().mockResolvedValue([]),
  getCharacters: vi.fn().mockResolvedValue([]),
  deleteProject: vi.fn(),
  patchProject: vi.fn(),
  setProjectCharacters: vi.fn(),
}));

import { deleteProject, getCharacters, getProject, setProjectCharacters } from "../apis/studio";
import { useInFlightRuns } from "../hooks/useInFlightRuns";
import { ProjectPage } from "./ProjectPage";

const read = vi.mocked(getProject);
const destroy = vi.mocked(deleteProject);
const setCharacters = vi.mocked(setProjectCharacters);
const inFlight = vi.mocked(useInFlightRuns);

const ID = "proj-0001";

function record(over: Partial<ProjectRecord> = {}): ProjectRecord {
  return {
    id: ID,
    lib: "lib-0001",
    name: "A project",
    description: "",
    rev: 3,
    created: "2026-08-01T00:00:00Z",
    updated: "2026-08-01T00:00:00Z",
    root: "node-root",
    hero: null,
    characters: [],
    counts: { runs: 29, scenes: 3, movies: 1 },
    ...over,
  } as ProjectRecord;
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  read.mockResolvedValue(record());
  inFlight.mockReturnValue({});
});

async function open(path = `/p/${ID}`) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/p/:projectId" element={<ProjectPage />} />
        <Route path="/p/:projectId/r/:runId" element={<ProjectPage />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
  await screen.findByRole("tab", { name: "Runs" });
}

const selected = (name: string) =>
  screen.getByRole("tab", { name }).getAttribute("aria-selected") === "true";

/**
 * The tab is in the address.
 *
 * Uncontrolled tabs could not be linked to, did not survive a refresh, and were
 * not what back went to — on a page with five of them.
 */
it("opens the tab the address names", async () => {
  await open(`/p/${ID}?tab=scenes`);

  expect(selected("Scenes")).toBe(true);
  expect(selected("Runs")).toBe(false);
});

it("opens Runs — the feed — when the address names no tab", async () => {
  await open();
  expect(selected("Runs")).toBe(true);
  expect(screen.getByText(`feed for ${ID}`)).toBeTruthy();
});

/**
 * Overview became Settings, and an old `?tab=overview` link still lands on it
 * rather than on a tab that no longer exists.
 */
it("maps the old overview tab to Settings", async () => {
  await open(`/p/${ID}?tab=overview`);
  expect(selected("Settings")).toBe(true);
  expect(screen.getByRole("textbox", { name: "Name" })).toBeTruthy();
});

/**
 * Five tabs, Runs first and Settings last, and Inputs is not one of them.
 *
 * It was: `input/` had a tab drawing the same nodes Files draws one tab over,
 * numbered. Asserted by name because the removal is the point.
 */
it("names its tabs, Runs first, and offers no Inputs tab", async () => {
  await open();

  const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
  expect(tabs).toEqual(["Runs", "Scenes", "Movies", "Files", "Settings"]);
  expect(tabs).not.toContain("Inputs");
  expect(tabs).not.toContain("Overview");
});

/**
 * **Nothing on the page makes a run.** The create bar in the top bar is where
 * a run is authored; the strip that used to open from a `New run` button here
 * is gone with the approve step it led to.
 */
it("offers no New run control of its own", async () => {
  await open();
  expect(screen.queryByRole("button", { name: "New run" })).toBeNull();
});

/**
 * The header: the run count, the running badge with its spinner while a run
 * is out, and the characters as chips that open the character.
 */
it("counts the runs, says how many are running, and draws the cast as chips", async () => {
  read.mockResolvedValue(record({ characters: [{ id: "char-1", name: "jason" }] }));
  vi.mocked(getCharacters).mockResolvedValue([
    { id: "char-1", name: "jason", hero: { node: "node-h", url: "/hero.png" }, updated: "2026-08-01T00:00:00Z", counts: { default: 1, files: 1 } },
  ]);
  inFlight.mockReturnValue({ [ID]: 2 });
  await open();

  expect(screen.getByText("29 runs")).toBeTruthy();
  expect(screen.getByText("2 running")).toBeTruthy();
  expect(screen.getByRole("progressbar", { name: "2 running" })).toBeTruthy();

  const chip = screen.getByRole("link", { name: /jason/ });
  expect(chip.getAttribute("href")).toBe("/c/char-1");
  // The avatar is the character's card image, drawn decoratively — the chip's
  // own text is its name.
  await waitFor(() => expect(chip.querySelector("img")?.getAttribute("src")).toBe("/hero.png"));
});

it("says nothing about running when nothing is", async () => {
  await open();
  expect(screen.queryByText(/running/)).toBeNull();
});

/**
 * The opened run is this page with the lightbox over it — the feed stays
 * mounted underneath, so closing the run is not a second load of the feed.
 */
it("draws the lightbox over the feed when the address names a run", async () => {
  await open(`/p/${ID}/r/run-0001?tab=runs`);
  expect(screen.getByText("lightbox run-0001")).toBeTruthy();
  expect(screen.getByText(`feed for ${ID}`)).toBeTruthy();
});

/**
 * The delete gate.
 *
 * A project takes its runs, scenes and movies with it, and the armed-button
 * shape — press twice in the same spot — is exactly the gesture a mis-click
 * produces. So the name has to be typed, and the sentence above it says what
 * goes.
 */
it("will not delete until the name is typed, and says what goes with it", async () => {
  await open();

  // Delete lives behind the page bar's `⋯`, not loose beside the title.
  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));

  // Scoped to the dialog: the trigger and the dialog's action share a label,
  // which is correct — both say what pressing them does.
  const dialog = await screen.findByRole("alertdialog");
  const action = within(dialog).getByRole("button", { name: "Delete" }) as HTMLButtonElement;

  expect(action.disabled).toBe(true);
  expect(within(dialog).getByText(/29 run\(s\), 3 scene\(s\) and 1 movie\(s\)/)).toBeTruthy();
  expect(destroy).not.toHaveBeenCalled();

  fireEvent.change(within(dialog).getByLabelText("Confirm"), { target: { value: "A project" } });
  await waitFor(() => expect(action.disabled).toBe(false));
});

/**
 * Involvement is a set replace, and its answer is now mergeable.
 *
 * It was not: the route echoed the ids it was handed where the record holds
 * expanded objects, so merging put strings in a field of objects and every chip
 * read unselected while the write had succeeded. The page refetched the whole
 * project to work around it. The route answers in its `GET` shape now, so the
 * merge is the assertion — and the refetch is asserted NOT to happen, because a
 * refetch that quietly came back would hide the shape regressing again.
 */
it("merges the involvement answer without refetching the project", async () => {
  vi.mocked(getCharacters).mockResolvedValue([
    { id: "char-1", name: "Someone", hero: null, updated: "2026-08-01T00:00:00Z", counts: { default: 0, files: 0 } },
  ]);
  setCharacters.mockResolvedValue({
    id: ID,
    characters: [{ id: "char-1", name: "Someone" }],
  });

  await open(`/p/${ID}?tab=settings`);
  await waitFor(() => expect(screen.getByRole("button", { name: "Someone" })).toBeTruthy());

  read.mockClear();
  fireEvent.click(screen.getByRole("button", { name: "Someone" }));

  await waitFor(() => expect(setCharacters).toHaveBeenCalledWith(ID, ["char-1"]));
  expect(read).not.toHaveBeenCalled();
});
