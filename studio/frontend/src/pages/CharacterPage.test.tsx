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
    profile: {
      // `hair` is short and stays a line. `build` is 63 characters — over the
      // old 100-char threshold it was a single-line input you had to scroll
      // sideways through on a phone, which shows about 40.
      appearance: { hair: "short", build: "a" .repeat(63) },
      voice: { accent: "flat" },
    },
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
    // The record fields alone are dirty here, so only the one write goes.
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

  it("opens the record card and the first of the bible, and leaves the rest closed", async () => {
    await open();

    const expanded = screen
      .getAllByRole("button", { expanded: true })
      .map((each) => each.textContent);

    // "Record", not "Identity": the bible has its own `identity:` section and
    // the two cards used to carry the same heading.
    expect(expanded).toContain("Record");
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

  it("gives a value that wraps a box, not a one-line input", async () => {
    // The threshold used to be 100 characters, which is a desktop answer: a
    // single-line input shows about 40 on a phone, so everything between was
    // read by scrolling sideways through a one-line box.
    await open();

    expect(screen.getByLabelText("Build").tagName).toBe("TEXTAREA");
    expect(screen.getByLabelText("Hair").tagName).toBe("INPUT");
  });

  it("resets the card's own padding, which a class cannot be trusted to do", async () => {
    // `Card.Root` carries `p-lg`, and the package merges caller classes with
    // `tailwind-merge`, which does not recognise this design system's t-shirt
    // spacing keys — `twMerge('… p-lg …', 'p-0')` returns BOTH, and `.p-lg` is
    // emitted after `.p-0` in the stylesheet, so the reset lost. The card kept
    // 24px and the panel added 24px more: 48px a side on a 390px screen.
    //
    // Asserting the inline style is the point. A className assertion would have
    // passed the whole time this was broken.
    await open();

    const card = document.querySelector<HTMLElement>('[data-section=" record"]');
    expect(card).toBeTruthy();
    // Parsed, not string-compared: jsdom serialises these two zeroes
    // differently — `padding` as "0px" and `gap` as "0".
    expect(parseFloat(card!.style.padding)).toBe(0);
    expect(parseFloat(card!.style.gap)).toBe(0);
  });

  it("marks the section that moved, and only that one", async () => {
    await open();

    fireEvent.change(screen.getByLabelText("Hair"), { target: { value: "long" } });

    expect(within(section(/Appearance/)).queryByLabelText("unsaved changes")).toBeTruthy();
    expect(within(section(/Voice/)).queryByLabelText("unsaved changes")).toBeNull();
  });
});
