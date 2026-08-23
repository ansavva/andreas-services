import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CharacterRecord } from "../types";

// The header pulls in auth and the library context and says nothing this file
// asserts on. Everything else is the real component.
vi.mock("../components/common/AppHeader", () => ({ AppHeader: () => <div /> }));
vi.mock("../components/browse/FolderBrowser", () => ({
  FolderTab: ({ rootId }: { rootId: string }) => <div>files of {rootId}</div>,
}));
vi.mock("../components/character/ReferencesGrid", () => ({
  ReferencesGrid: () => <div>references</div>,
}));

vi.mock("../apis/studio", () => ({
  deleteCharacter: vi.fn(),
  getCharacter: vi.fn(),
  patchCharacter: vi.fn(),
  putCharacterProfile: vi.fn(),
}));

import { getCharacter, patchCharacter, putCharacterProfile } from "../apis/studio";
import { CharacterPage } from "./CharacterPage";

const read = vi.mocked(getCharacter);
const patch = vi.mocked(patchCharacter);
const putProfile = vi.mocked(putCharacterProfile);

const ID = "char-0001";

function record(over: Partial<CharacterRecord> = {}): CharacterRecord {
  return {
    id: ID,
    lib: "lib-0001",
    slug: "<slug>",
    display_name: "<name>",
    fictional: true,
    rev: 7,
    created: "2026-08-01T00:00:00Z",
    updated: "2026-08-01T00:00:00Z",
    root: "node-root",
    hero: null,
    default_set: [],
    profile: { appearance: { hair: "short" }, voice: { accent: "flat" } },
    ...over,
  };
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  read.mockResolvedValue(record());
});

async function open() {
  render(
    <MemoryRouter initialEntries={[`/c/${ID}`]}>
      <Routes>
        <Route path="/c/:characterId" element={<CharacterPage />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("tab", { name: "Profile" });
}

describe("the tab strip", () => {
  it("is three tabs, and none of them is a folder", async () => {
    await open();

    const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    expect(tabs).toEqual(["Profile", "References", "Files"]);
  });

  it("puts the whole character root behind Files, not one folder per tab", async () => {
    await open();

    fireEvent.click(screen.getByRole("tab", { name: "Files" }));
    expect(await screen.findByText("files of node-root")).toBeTruthy();
  });
});

describe("saving identity and the bible together", () => {
  /** Type into a field that is already on screen, then hit the one Save. */
  async function editAndSave(label: string, value: string) {
    const field = screen.getByLabelText(label);
    fireEvent.change(field, { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
  }

  it("chains the two writes, so the profile carries the rev the rename produced", async () => {
    // The trap this exists to catch: both routes are compare-and-swap on the
    // same row, so sending them the same `rev` makes the second one 409 against
    // a change the page itself just made.
    patch.mockResolvedValue(record({ slug: "<other>", rev: 8 }));
    putProfile.mockResolvedValue(record({ slug: "<other>", rev: 9 }));

    await open();
    await editAndSave("Slug", "<other>");
    // Identity alone is dirty here, so only the one write goes.
    await waitFor(() => expect(patch).toHaveBeenCalledWith(ID, expect.objectContaining({ rev: 7 })));
    expect(putProfile).not.toHaveBeenCalled();

    cleanup();
    vi.clearAllMocks();
    read.mockResolvedValue(record());
    patch.mockResolvedValue(record({ rev: 8 }));
    putProfile.mockResolvedValue(record({ rev: 9 }));

    await open();
    // Both halves dirty: the slug, and a leaf inside the first bible section.
    fireEvent.change(screen.getByLabelText("Slug"), { target: { value: "<other>" } });
    fireEvent.change(screen.getByLabelText("Hair"), { target: { value: "long" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(putProfile).toHaveBeenCalled());
    expect(patch).toHaveBeenCalledWith(ID, expect.objectContaining({ rev: 7 }));
    expect(putProfile).toHaveBeenCalledWith(ID, expect.anything(), 8);
  });

  it("sends only the bible when only the bible moved", async () => {
    putProfile.mockResolvedValue(record({ rev: 8 }));

    await open();
    await editAndSave("Hair", "long");

    await waitFor(() => expect(putProfile).toHaveBeenCalledWith(ID, expect.anything(), 7));
    expect(patch).not.toHaveBeenCalled();
  });

  it("has one save bar and one revision label, not one per section", async () => {
    await open();

    expect(screen.getAllByRole("button", { name: "Saved" })).toHaveLength(1);
    expect(screen.getAllByText(/revision 7/)).toHaveLength(1);
  });
});

describe("the sections", () => {
  /** A section's own trigger — the only button with the name that carries `aria-expanded`. */
  const section = (name: RegExp) =>
    screen
      .getAllByRole("button", { name })
      .find((each) => each.hasAttribute("aria-expanded")) as HTMLElement;

  it("opens identity and the first of the bible, and leaves the rest closed", async () => {
    await open();

    const expanded = screen
      .getAllByRole("button", { expanded: true })
      .map((each) => each.textContent);

    expect(expanded).toContain("Identity");
    expect(expanded).toContain("Appearance");
    expect(expanded).not.toContain("Voice");
  });

  it("keeps a draft when its section is collapsed", async () => {
    // The panel stays mounted and goes `inert`, which is why an edit survives a
    // collapse. A section that unmounted would drop the edit on the floor and
    // the save bar would still say there was one.
    await open();

    fireEvent.change(screen.getByLabelText("Hair"), { target: { value: "long" } });

    // By `expanded`, because the desktop rail carries the same names: it is
    // `hidden` below `lg` and jsdom applies no CSS, so both are in this tree.
    // Only the section trigger has `aria-expanded`.
    const trigger = section(/Appearance/);
    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");

    expect((screen.getByLabelText("Hair") as HTMLInputElement).value).toBe("long");
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
  });

  it("marks the section that moved, and only that one", async () => {
    await open();

    fireEvent.change(screen.getByLabelText("Hair"), { target: { value: "long" } });

    expect(within(section(/Appearance/)).queryByLabelText("unsaved changes")).toBeTruthy();
    expect(within(section(/Voice/)).queryByLabelText("unsaved changes")).toBeNull();
  });
});
