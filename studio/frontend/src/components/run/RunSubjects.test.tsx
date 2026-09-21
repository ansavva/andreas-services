import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("../../apis/studio", () => ({
  getProject: vi.fn(),
  getLocations: vi.fn(),
  getRun: vi.fn(),
  setRunCharacters: vi.fn(),
  setRunLocations: vi.fn(),
}));

import {
  getLocations,
  getProject,
  getRun,
  setRunCharacters,
  setRunLocations,
} from "../../apis/studio";
import { TestProviders } from "../../test-providers";
import type { RunFeedRow } from "../../types";
import { RunSubjects } from "./RunSubjects";

/**
 * Who a run is about and where it was shot, edited from the rail.
 *
 * What these pin: the write is a whole-set replace of what the run NAMES,
 * not of its derived cast; the chips come from the project; and a press
 * re-reads the run rather than merging, because `cast` is derived.
 *
 * Placeholder slugs only (hard rule #1).
 */

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getProject).mockResolvedValue({
    id: "proj-1",
    characters: [
      { id: "char-1", name: "jason" },
      { id: "char-2", name: "mira" },
    ],
    locations: [{ id: "loc-1", name: "kitchen" }],
  } as never);
  vi.mocked(getLocations).mockResolvedValue([
    { id: "loc-1", name: "kitchen", hero: null },
  ] as never);
  vi.mocked(getRun).mockResolvedValue({ id: "run-1" } as never);
  vi.mocked(setRunCharacters).mockResolvedValue({} as never);
  vi.mocked(setRunLocations).mockResolvedValue({} as never);
});

function row(over: Partial<RunFeedRow> = {}): RunFeedRow {
  return {
    id: "run-1",
    lib: "lib-1",
    project: "proj-1",
    status: "succeeded",
    kind: "image",
    engine: null,
    model: "m",
    created: "2026-09-01T00:00:00Z",
    updated: null,
    submitted: null,
    completed: null,
    error: null,
    cost: null,
    thumb: null,
    plan: null,
    characters: [],
    cast: [{ id: "char-1", name: "jason" }],
    locations: [],
    sends: [],
    outputs: [],
    ...over,
  };
}

function mount(over: Partial<RunFeedRow> = {}) {
  return render(
    <TestProviders>
      <MemoryRouter>
        <dl>
          <RunSubjects row={row(over)} heroes={{}} />
        </dl>
      </MemoryRouter>
    </TestProviders>,
  );
}

it("reads the derived cast, and says nowhere when the run names no location", () => {
  mount();
  expect(screen.getByText("jason")).toBeTruthy();
  expect(screen.getByText("nowhere named")).toBeTruthy();
});

it("a press on a location chip replaces the set and re-reads the run", async () => {
  mount();
  fireEvent.click(screen.getByLabelText("Edit locations"));
  const chip = await screen.findByRole("button", { name: /kitchen/ });
  fireEvent.click(chip);
  await waitFor(() => expect(setRunLocations).toHaveBeenCalledWith("run-1", ["loc-1"]));
  await waitFor(() => expect(getRun).toHaveBeenCalledWith("run-1"));
});

it("the cast chips toggle what the run NAMES, appended in order, not the derived cast", async () => {
  mount();
  fireEvent.click(screen.getByLabelText("Edit characters"));
  // Names nobody: the derived cast lights no chip, and the row says why.
  expect(await screen.findByText(/Names nobody/)).toBeTruthy();
  fireEvent.click(await screen.findByRole("button", { name: /mira/ }));
  await waitFor(() => expect(setRunCharacters).toHaveBeenCalledWith("run-1", ["char-2"]));
});

it("a name the run carries that the project no longer lists is still offered, so it can come off", async () => {
  mount({ characters: ["char-9"], cast: [{ id: "char-9", name: null }] });
  fireEvent.click(screen.getByLabelText("Edit characters"));
  fireEvent.click(await screen.findByRole("button", { name: /deleted character/ }));
  await waitFor(() => expect(setRunCharacters).toHaveBeenCalledWith("run-1", []));
});

it("a refused write is reported on the row and the chips stay pressable", async () => {
  vi.mocked(setRunLocations).mockRejectedValueOnce(new Error("no such location"));
  mount();
  fireEvent.click(screen.getByLabelText("Edit locations"));
  fireEvent.click(await screen.findByRole("button", { name: /kitchen/ }));
  expect(await screen.findByText("no such location")).toBeTruthy();
  expect((screen.getByRole("button", { name: /kitchen/ }) as HTMLButtonElement).disabled).toBe(false);
});
