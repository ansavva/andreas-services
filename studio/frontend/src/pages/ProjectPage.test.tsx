import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { ProjectRecord } from "../types";
import { TestProviders } from "../test-providers";

vi.mock("../components/browse/FolderTab", () => ({ FolderTab: () => <div>files</div> }));
vi.mock("../components/project/RunsTable", () => ({ RunsTable: () => <div>runs table</div> }));

vi.mock("../apis/studio", () => ({
  getProject: vi.fn(),
  getProjectScenes: vi.fn().mockResolvedValue([]),
  getProjectMovies: vi.fn().mockResolvedValue([]),
  getCharacters: vi.fn().mockResolvedValue([]),
  // The Runs tab's composer strip reads the registry. Answering with nothing
  // keeps this file about the page: the strip has its own suite.
  getModels: vi.fn().mockResolvedValue({}),
  createRun: vi.fn(),
  deleteProject: vi.fn(),
  patchProject: vi.fn(),
  setProjectCharacters: vi.fn(),
}));

import { deleteProject, getProject, setProjectCharacters } from "../apis/studio";
import { ProjectPage } from "./ProjectPage";

const read = vi.mocked(getProject);
const destroy = vi.mocked(deleteProject);
const setCharacters = vi.mocked(setProjectCharacters);

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
});

async function open(path = `/p/${ID}`) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/p/:projectId" element={<ProjectPage />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
  await screen.findByRole("tab", { name: "Overview" });
}

/**
 * The tab is in the address.
 *
 * Uncontrolled tabs could not be linked to, did not survive a refresh, and were
 * not what back went to — on a page with five of them.
 */
it("opens the tab the address names", async () => {
  await open(`/p/${ID}?tab=scenes`);

  expect(screen.getByRole("tab", { name: "Scenes" }).getAttribute("aria-selected")).toBe("true");
  expect(screen.getByRole("tab", { name: "Overview" }).getAttribute("aria-selected")).toBe("false");
});

it("opens Overview when the address names no tab", async () => {
  await open();
  expect(screen.getByRole("tab", { name: "Overview" }).getAttribute("aria-selected")).toBe("true");
});

/**
 * Five tabs, and Inputs is not one of them.
 *
 * It was: `input/` had a tab drawing the same nodes Files draws one tab over,
 * numbered. Asserted by name because the removal is the point — a strip built
 * from a listing is what the character page already undid, and this is the same
 * mistake in the one place it survived.
 */
it("names its tabs, and offers no Inputs tab", async () => {
  await open();

  const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
  expect(tabs).toEqual(["Overview", "Runs", "Scenes", "Movies", "Files"]);
  expect(tabs).not.toContain("Inputs");
});

/**
 * Authoring a run starts where the runs are.
 *
 * Not in the page bar: its one action deletes the project, and what this makes
 * belongs to the project rather than being another thing done *to* it.
 */
it("offers the run composer on the Runs tab and nowhere else", async () => {
  await open(`/p/${ID}?tab=runs`);
  // Disclosed rather than permanent: the tab offers the control, and the form
  // opens in its place. A form standing open across a tab that is mostly read
  // is what this replaced.
  fireEvent.click(screen.getByRole("button", { name: "New run" }));
  expect(screen.getByRole("button", { name: "Create draft" })).toBeTruthy();

  fireEvent.click(screen.getByRole("tab", { name: "Overview" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "New run" })).toBeNull());
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

  fireEvent.click(screen.getByRole("button", { name: "Delete" }));

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
  const { getCharacters } = await import("../apis/studio");
  vi.mocked(getCharacters).mockResolvedValue([
    { id: "char-1", name: "Someone", hero: null, counts: { references: 0, files: 0 } },
  ] as never);
  setCharacters.mockResolvedValue({
    id: ID,
    characters: [{ id: "char-1", name: "Someone" }],
  });

  await open();
  await waitFor(() => expect(screen.getByRole("button", { name: "Someone" })).toBeTruthy());

  read.mockClear();
  fireEvent.click(screen.getByRole("button", { name: "Someone" }));

  await waitFor(() => expect(setCharacters).toHaveBeenCalledWith(ID, ["char-1"]));
  expect(read).not.toHaveBeenCalled();
});
