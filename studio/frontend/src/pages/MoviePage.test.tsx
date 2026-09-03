import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { MovieRecord } from "../types";
import { TestProviders } from "../test-providers";

vi.mock("../apis/studio", () => ({
  getMovie: vi.fn(),
  deleteMovie: vi.fn(),
  getProject: vi.fn().mockResolvedValue({ id: "proj-1", name: "A project" }),
}));

import { deleteMovie, getMovie } from "../apis/studio";
import { MoviePage } from "./MoviePage";

const read = vi.mocked(getMovie);
const destroy = vi.mocked(deleteMovie);
const ID = "movie-1";

let landed = "";

function Land() {
  landed = useLocation().pathname;
  return <div>landed</div>;
}

function record(over: Partial<MovieRecord> = {}): MovieRecord {
  return {
    id: ID,
    project: "proj-1",
    name: "A movie",
    status: "planned",
    created: "2026-08-20T00:00:00Z",
    output: null,
    scenes: [],
    ...over,
  } as MovieRecord;
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  landed = "";
});

async function open() {
  render(
    <MemoryRouter initialEntries={[`/m/${ID}`]}>
      <Routes>
        <Route path="/m/:movieId" element={<MoviePage />} />
        <Route path="/s/:sceneId" element={<Land />} />
        {/* Where deleting the movie lands — the project it belongs to. */}
        <Route path="/p/:projectId" element={<Land />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
  await screen.findByText("Scenes");
}

it("names the project in the trail", async () => {
  read.mockResolvedValue(record());
  await open();

  await waitFor(() => expect(screen.getByText("A project")).toBeTruthy());
});

/**
 * A movie's scenes are listed rather than embedded, because a scene is an
 * entity with its own page — so each row has to actually go there.
 */
it("opens a scene from its row", async () => {
  read.mockResolvedValue(
    record({
      scenes: [
        { id: "scene-7", name: "A scene", status: "assembled", thumb: null },
      ],
    } as Partial<MovieRecord>),
  );
  await open();

  // A row is `EntityRow`'s `<a>` now, not a `<button>` — see `EntityRow.to`.
  fireEvent.click(await screen.findByRole("link", { name: /A scene/ }));

  await screen.findByText("landed");
  expect(landed).toBe("/s/scene-7");
});

/**
 * The numbering is the cut order, and it is the one thing this page adds over
 * the project's own Scenes tab.
 */
it("numbers the scenes in cut order", async () => {
  read.mockResolvedValue(
    record({
      scenes: [
        { id: "s1", name: "First", status: "assembled", thumb: null },
        { id: "s2", name: "Second", status: "planned", thumb: null },
      ],
    } as Partial<MovieRecord>),
  );
  await open();

  const rows = await screen.findAllByRole("link", { name: /First|Second/ });
  expect(rows[0]?.textContent).toMatch(/^1/);
  expect(rows[1]?.textContent).toMatch(/^2/);
});

/** Delete lives behind the page bar's `⋯`, typing the name like Scene's does. */
it("types the name before deleting the movie, then lands on its project", async () => {
  destroy.mockResolvedValue({ id: ID, files: "delete" });
  read.mockResolvedValue(record());
  await open();

  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));

  const dialog = await screen.findByRole("alertdialog");
  const action = screen.getByRole("button", { name: "Delete" }) as HTMLButtonElement;
  expect(action.disabled).toBe(true);
  expect(destroy).not.toHaveBeenCalled();

  fireEvent.change(within(dialog).getByLabelText("Confirm"), { target: { value: "A movie" } });
  await waitFor(() => expect(action.disabled).toBe(false));
  fireEvent.click(action);

  await waitFor(() => expect(destroy).toHaveBeenCalledWith(ID, "delete"));
  await screen.findByText("landed");
  expect(landed).toBe("/p/proj-1");
});
