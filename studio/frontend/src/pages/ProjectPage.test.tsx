import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { ProjectRecord } from "../types";
import { TestProviders } from "../test-providers";

vi.mock("../components/browse/FolderBrowser", () => ({
  FolderTab: () => <div>files</div>,
}));
vi.mock("../components/project/RunsTable", () => ({ RunsTable: () => <div>runs table</div> }));

vi.mock("../apis/studio", () => ({
  getProject: vi.fn(),
  getProjectScenes: vi.fn().mockResolvedValue([]),
  getProjectMovies: vi.fn().mockResolvedValue([]),
  getProjectInputs: vi.fn().mockResolvedValue([]),
  getCharacters: vi.fn().mockResolvedValue([]),
  deleteProject: vi.fn(),
  patchProject: vi.fn(),
  putProjectCharacters: vi.fn(),
}));

import { deleteProject, getProject, putProjectCharacters } from "../apis/studio";
import { ProjectPage } from "./ProjectPage";

const read = vi.mocked(getProject);
const destroy = vi.mocked(deleteProject);
const setCharacters = vi.mocked(putProjectCharacters);

const ID = "proj-0001";

function record(over: Partial<ProjectRecord> = {}): ProjectRecord {
  return {
    id: ID,
    lib: "lib-0001",
    slug: "a-project",
    title: "A project",
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
 * not what back went to — on a page with six of them.
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
 * The delete gate.
 *
 * A project takes its runs, scenes and movies with it, and the armed-button
 * shape — press twice in the same spot — is exactly the gesture a mis-click
 * produces. So the slug has to be typed, and the sentence above it says what
 * goes.
 */
it("will not delete until the slug is typed, and says what goes with it", async () => {
  await open();

  fireEvent.click(screen.getByRole("button", { name: "Delete" }));

  // Scoped to the dialog: the trigger and the dialog's action share a label,
  // which is correct — both say what pressing them does.
  const dialog = await screen.findByRole("alertdialog");
  const action = within(dialog).getByRole("button", { name: "Delete" }) as HTMLButtonElement;

  expect(action.disabled).toBe(true);
  expect(within(dialog).getByText(/29 run\(s\), 3 scene\(s\) and 1 movie\(s\)/)).toBeTruthy();
  expect(destroy).not.toHaveBeenCalled();

  fireEvent.change(within(dialog).getByLabelText("Confirm"), { target: { value: "a-project" } });
  await waitFor(() => expect(action.disabled).toBe(false));
});

/**
 * Involvement is a set replace, and its answer cannot be merged.
 *
 * The route reports the links as ids where the record holds expanded objects,
 * so the page refetches instead — merging replaced objects with strings and
 * every chip silently read unselected while the write had succeeded.
 */
it("refetches the project after changing who is involved", async () => {
  const { getCharacters } = await import("../apis/studio");
  vi.mocked(getCharacters).mockResolvedValue([
    { id: "char-1", slug: "someone", display_name: "Someone", hero: null, counts: { references: 0, files: 0 } },
  ] as never);
  setCharacters.mockResolvedValue({ id: ID, characters: ["char-1"] });

  await open();
  await waitFor(() => expect(screen.getByRole("button", { name: "Someone" })).toBeTruthy());

  read.mockClear();
  fireEvent.click(screen.getByRole("button", { name: "Someone" }));

  await waitFor(() => expect(setCharacters).toHaveBeenCalledWith(ID, ["char-1"]));
  // The refetch is the assertion: without it the page holds ids in a field that
  // is meant to hold objects.
  await waitFor(() => expect(read).toHaveBeenCalled());
});
