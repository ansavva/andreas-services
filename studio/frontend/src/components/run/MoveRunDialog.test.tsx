import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/studio", () => ({
  getProjects: vi.fn(),
  moveRun: vi.fn(),
}));

import { getProjects, moveRun } from "../../apis/studio";
import type { ProjectSummary, RunFeedRow } from "../../types";
import { TestProviders } from "../../test-providers";
import { MoveRunDialog } from "./MoveRunDialog";

/**
 * Moving a run to another project, from its `⋯` menu.
 *
 * What these pin: the current project is not on offer, nothing is sent until
 * a project is chosen and Move is pressed, and a lightbox open on the run
 * follows it. Placeholder names only (hard rule #1).
 */

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

const projects = vi.mocked(getProjects);
const move = vi.mocked(moveRun);

function project(id: string, name: string): ProjectSummary {
  return {
    id,
    name,
    hero: null,
    counts: { runs: 0, scenes: 0, movies: 0 },
    updated: "",
  };
}

function row(over: Partial<RunFeedRow> = {}): RunFeedRow {
  return {
    id: "run-1",
    project: "proj-1",
    status: "succeeded",
    kind: "image",
    model: "a-model",
    created: "2026-08-20T00:00:00Z",
    scene: null,
    lib: "lib-1",
    engine: null,
    updated: null,
    submitted: null,
    completed: null,
    error: null,
    plan: null,
    characters: [],
    cast: [],
    sends: [],
    outputs: [],
    thumb: null,
    ...over,
  } as RunFeedRow;
}

function Address() {
  const location = useLocation();
  return <div>at {location.pathname}</div>;
}

function open(at = "/p/proj-1", over: Partial<RunFeedRow> = {}, onClose = vi.fn()) {
  render(
    <TestProviders>
      <MemoryRouter initialEntries={[at]}>
        <MoveRunDialog row={row(over)} onClose={onClose} />
        <Address />
      </MemoryRouter>
    </TestProviders>,
  );
  return onClose;
}

const picker = () => screen.getByRole("combobox", { name: "Project" });
const moveButton = () => screen.getByRole("button", { name: /^Mov/ });

describe("MoveRunDialog", () => {
  it("offers every project but the one the run is in", async () => {
    projects.mockResolvedValue([project("proj-1", "here"), project("proj-2", "there")]);
    open();

    await waitFor(() => expect(picker().hasAttribute("disabled")).toBe(false));
    fireEvent.click(picker());

    expect(screen.getAllByRole("option").map((each) => each.textContent)).toEqual(["there"]);
    expect(moveButton().hasAttribute("disabled")).toBe(true);
    expect(move).not.toHaveBeenCalled();
  });

  it("moves on Move, reports it, and follows the run when it is open", async () => {
    projects.mockResolvedValue([project("proj-1", "here"), project("proj-2", "there")]);
    move.mockResolvedValue({ moved: true } as never);
    const onClose = open("/p/proj-1/r/run-1");

    await waitFor(() => expect(picker().hasAttribute("disabled")).toBe(false));
    fireEvent.click(picker());
    fireEvent.click(screen.getByRole("option", { name: "there" }));
    fireEvent.click(moveButton());

    await waitFor(() => expect(move).toHaveBeenCalledWith("run-1", "proj-2"));
    expect(await screen.findByText("Moved the run")).toBeTruthy();
    expect(await screen.findByText("at /p/proj-2/r/run-1")).toBeTruthy();
    expect(onClose).toHaveBeenCalled();
  });

  it("stays on the feed when the run was not open", async () => {
    projects.mockResolvedValue([project("proj-1", "here"), project("proj-2", "there")]);
    move.mockResolvedValue({ moved: true } as never);
    open("/p/proj-1");

    await waitFor(() => expect(picker().hasAttribute("disabled")).toBe(false));
    fireEvent.click(picker());
    fireEvent.click(screen.getByRole("option", { name: "there" }));
    fireEvent.click(moveButton());

    await waitFor(() => expect(move).toHaveBeenCalled());
    expect(await screen.findByText("at /p/proj-1")).toBeTruthy();
  });

  it("shows the refusal and keeps the dialog open", async () => {
    projects.mockResolvedValue([project("proj-1", "here"), project("proj-2", "there")]);
    move.mockRejectedValue(new Error("a run cannot be moved into another library"));
    const onClose = open();

    await waitFor(() => expect(picker().hasAttribute("disabled")).toBe(false));
    fireEvent.click(picker());
    fireEvent.click(screen.getByRole("option", { name: "there" }));
    fireEvent.click(moveButton());

    expect(await screen.findByText("Could not move the run")).toBeTruthy();
    expect(screen.getByText("a run cannot be moved into another library")).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("says the run will leave its scene, when it is in one", async () => {
    projects.mockResolvedValue([project("proj-2", "there")]);
    open("/p/proj-1", { scene: "scene-1" });

    expect(await screen.findByText(/leaves its scene/)).toBeTruthy();
  });
});
