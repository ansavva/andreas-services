import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LocationRecord } from "../types";

// `CharacterPage.test.tsx` pins the form's behaviour — collapsing, grouping,
// adding fields, the chained save. A location is the same page with a room's
// bible, so what this file pins is the difference: the location routes are
// the ones called, and the sections are a location's, grouped and annotated
// as a location's rather than a character's.
vi.mock("../components/browse/FolderTab", () => ({
  FolderTab: ({ rootId }: { rootId: string }) => <div>files of {rootId}</div>,
}));

vi.mock("../apis/studio", () => ({
  deleteLocation: vi.fn(),
  getLocation: vi.fn(),
  getLocationProfileTemplate: vi.fn(),
  patchLocation: vi.fn(),
  setLocationProfile: vi.fn(),
}));

import {
  getLocation,
  getLocationProfileTemplate,
  patchLocation,
  setLocationProfile,
} from "../apis/studio";
import { LocationPage } from "./LocationPage";
import { TestProviders } from "../test-providers";

const read = vi.mocked(getLocation);
const patch = vi.mocked(patchLocation);
const setProfile = vi.mocked(setLocationProfile);
const template = vi.mocked(getLocationProfileTemplate);

const ID = "loc-0001";

function record(over: Partial<LocationRecord> = {}): LocationRecord {
  return {
    id: ID,
    lib: "lib-0001",
    name: "dev-kitchen",
    rev: 3,
    created: "2026-09-01T00:00:00Z",
    updated: "2026-09-01T00:00:00Z",
    root: "node-root",
    hero: null,
    profile: {
      space: { layout: "an L, the door on the short leg", floor: "terrazzo" },
      lighting: { sources: "one window, north" },
      rendering: { lens: "24mm" },
    },
    ...over,
  };
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  read.mockResolvedValue(record());
  template.mockResolvedValue({
    profile: {
      identity: { kind: "", scale: "" },
      space: { layout: "", floor: "" },
      lighting: { sources: "" },
      text_identity_block: "",
    },
    hints: { "space.layout": "the plan — where the walls, doors and windows are" },
  });
});

async function open() {
  render(
    <MemoryRouter initialEntries={[`/l/${ID}`]}>
      <Routes>
        <Route path="/l/:locationId" element={<LocationPage />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
  await screen.findByRole("tab", { name: "Profile" });
}

describe("the page", () => {
  it("reads the location routes, and draws the same two tabs a character has", async () => {
    await open();

    expect(read).toHaveBeenCalledWith(ID);
    expect(template).toHaveBeenCalled();
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Profile",
      "Files",
    ]);
    expect(screen.getByRole("link", { name: "Locations" })).toBeTruthy();
  });

  it("chains the rename and the bible through the location routes", async () => {
    patch.mockResolvedValue(record({ rev: 4 }));
    setProfile.mockResolvedValue(record({ rev: 5 }));

    await open();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "the kitchen" } });
    fireEvent.change(screen.getByLabelText("Layout"), { target: { value: "a square" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(setProfile).toHaveBeenCalled());
    expect(patch).toHaveBeenCalledWith(ID, expect.objectContaining({ rev: 3, name: "the kitchen" }));
    expect(setProfile).toHaveBeenCalledWith(ID, expect.anything(), 4);
  });
});

describe("a location's bible", () => {
  it("groups the sections as a place, not as a person", async () => {
    await open();

    // The rail names a group and so does the column — twice each when present.
    expect(screen.getAllByText("The place")).toHaveLength(2);
    expect(screen.getAllByText("Direction")).toHaveLength(2);
    expect(screen.queryAllByText("Appearance")).toHaveLength(0);
  });

  it("annotates the sections with what a room's sections are for", async () => {
    await open();
    expect(screen.getByText(/What is FIXED and cannot move between renders/)).toBeTruthy();
    expect(screen.queryByText(/what a prompt gets written from/)).toBeNull();
  });

  it("offers the missing sections of the LOCATION template, and names the noun", async () => {
    await open();
    expect(screen.getByText(/this location does not have yet/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Identity/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Face$/ })).toBeNull();
  });

  it("marks the summary stale when the space moves, and points at the location CLI", async () => {
    read.mockResolvedValue(
      record({
        profile: {
          space: { layout: "an L" },
          text_identity_block: "An L-shaped kitchen lit from one north window.",
        },
      }),
    );
    await open();

    fireEvent.change(screen.getByLabelText("Layout"), { target: { value: "a square" } });

    expect(screen.getByText(/studio location textblock/)).toBeTruthy();
  });
});
