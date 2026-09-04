import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CharacterRecord } from "../types";

// The header pulls in auth and the library context and says nothing this file
// asserts on. Everything else is the real component.
// `FolderTab` moved to its own file: it and the standalone browser are two
// screens sharing one listing, and only one of them can spend the address bar.
vi.mock("../components/browse/FolderTab", () => ({
  FolderTab: ({ rootId }: { rootId: string }) => <div>files of {rootId}</div>,
}));

vi.mock("../apis/studio", () => ({
  deleteCharacter: vi.fn(),
  getCharacter: vi.fn(),
  patchCharacter: vi.fn(),
  setCharacterProfile: vi.fn(),
}));

import { getCharacter, patchCharacter, setCharacterProfile } from "../apis/studio";
import { CharacterPage } from "./CharacterPage";
import { TestProviders } from "../test-providers";

const read = vi.mocked(getCharacter);
const patch = vi.mocked(patchCharacter);
const setProfile = vi.mocked(setCharacterProfile);

const ID = "char-0001";

function record(over: Partial<CharacterRecord> = {}): CharacterRecord {
  return {
    id: ID,
    lib: "lib-0001",
    name: "<name>",
    rev: 7,
    created: "2026-08-01T00:00:00Z",
    updated: "2026-08-01T00:00:00Z",
    root: "node-root",
    hero: null,
    profile: {
      // `hair` is short and stays a line. `build` is 63 characters — over the
      // old 100-char threshold it was a single-line input you had to scroll
      // sideways through on a phone, which shows about 40.
      // Real section names, because the form orders and annotates by them now: a
      // made-up key renders after the schema's own and carries the off-schema
      // warning, which is not what this fixture is here to exercise.
      face: { hair: "short", build: "a" .repeat(63) },
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
  { wrapper: TestProviders },
  );
  await screen.findByRole("tab", { name: "Profile" });
}

describe("the tab strip", () => {
  it("is a FIXED list, and none of it is a folder", async () => {
    // The count is not the point and has changed twice now — Runs and Projects
    // joined when the character stopped being a dead end, and Shoot joined when
    // a reference set could be made without a terminal. What must not come back
    // is a strip built from the folder listing: it grew and shrank as folders
    // came and went, every folder tab showed what Files already held, and at
    // 390px seven of them wrapped into three rows of underline. The character's
    // root children are `reference`, `corpus`, `seed` and `archive`, and none of
    // those may appear here — `seed` in particular, which Shoot now reads from
    // and which is exactly the kind of tab this test exists to keep out.
    await open();

    const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    // No `Identity`, and that is the point of this assertion as much as the
    // folder names below it: it was Files with `default` pre-filled, which is a
    // preset of the tab beside it rather than a place of its own. `Shoot` went
    // with the turnaround — it rendered fourteen angles at once, and a template
    // is picked for one run from the plan editor.
    expect(tabs).toEqual(["Profile", "Files", "Runs", "Projects"]);
    expect(tabs).not.toContain("Identity");
    expect(tabs).not.toContain("reference");
    expect(tabs).not.toContain("seed");
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
    patch.mockResolvedValue(record({ rev: 8 }));
    setProfile.mockResolvedValue(record({ rev: 9 }));

    await open();
    await editAndSave("Name", "<other>");
    // The record fields alone are dirty here, so only the one write goes.
    await waitFor(() => expect(patch).toHaveBeenCalledWith(ID, expect.objectContaining({ rev: 7 })));
    expect(setProfile).not.toHaveBeenCalled();

    cleanup();
    vi.clearAllMocks();
    read.mockResolvedValue(record());
    patch.mockResolvedValue(record({ rev: 8 }));
    setProfile.mockResolvedValue(record({ rev: 9 }));

    await open();
    // Both halves dirty: the name, and a leaf inside the first bible section.
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "<other>" } });
    fireEvent.change(screen.getByLabelText("Hair"), { target: { value: "long" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(setProfile).toHaveBeenCalled());
    expect(patch).toHaveBeenCalledWith(ID, expect.objectContaining({ rev: 7 }));
    expect(setProfile).toHaveBeenCalledWith(ID, expect.anything(), 8);
  });

  it("sends only the bible when only the bible moved", async () => {
    setProfile.mockResolvedValue(record({ rev: 8 }));

    await open();
    await editAndSave("Hair", "long");

    await waitFor(() => expect(setProfile).toHaveBeenCalledWith(ID, expect.anything(), 7));
    expect(patch).not.toHaveBeenCalled();
  });

  it("has one save bar and one revision label, not one per section", async () => {
    await open();

    expect(screen.getAllByRole("button", { name: "Save" })).toHaveLength(1);
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
    expect(expanded).toContain("Face");
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
    const trigger = section(/Face/);
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
    // `Card.Root` carries `p-lg`, and this resets it. It used to have to be an
    // inline style: the package merged caller classes with a `tailwind-merge`
    // that did not recognise this design system's t-shirt spacing keys, so
    // `twMerge('… p-lg …', 'p-0')` returned BOTH and `.p-lg` — emitted after
    // `.p-0` — won. The card kept 24px and the panel added 24px more: 48px a
    // side on a 390px screen.
    //
    // design-system 0.17.0 teaches the merge the scale, so the reset is a
    // className again and the assertion follows it. What is asserted is that
    // `p-lg` is GONE, not merely that `p-0` is present — the whole failure was
    // that both survived, and a bare `toContain("p-0")` would have passed
    // throughout.
    await open();

    const card = document.querySelector<HTMLElement>('[data-section=" record"]');
    expect(card).toBeTruthy();
    expect(card!.className).toContain("p-0");
    expect(card!.className).toContain("gap-0");
    expect(card!.className).not.toContain("p-lg");
    expect(card!.className).not.toContain("gap-sm");
  });

  it("marks the section that moved, and only that one", async () => {
    await open();

    fireEvent.change(screen.getByLabelText("Hair"), { target: { value: "long" } });

    expect(within(section(/Face/)).queryByLabelText("unsaved changes")).toBeTruthy();
    expect(within(section(/Voice/)).queryByLabelText("unsaved changes")).toBeNull();
  });

  it("orders sections by the schema, not by the order the record arrived in", async () => {
    // A DynamoDB map has no order worth relying on: these two came back with
    // `voice` first, which put the accent above the face on the screen.
    read.mockResolvedValue(
      record({ profile: { voice: { accent: "flat" }, face: { hair: "short" } } }),
    );
    await open();

    const rendered = [...document.querySelectorAll("[data-section]")].map((each) =>
      each.getAttribute("data-section"),
    );
    expect(rendered).toEqual([" record", "face", "voice"]);
  });

  it("warns on a section the API does not know, and puts it last", async () => {
    // `corpus` is the real one: a key the pre-catalog migration carried across
    // verbatim, which sat in this form looking like part of the schema while
    // every save that included it was refused whole.
    read.mockResolvedValue(
      record({
        profile: {
          corpus: [{ file: "<name>_in_7.png", description: "<…>" }],
          face: { hair: "short" },
        },
      }),
    );
    await open();

    const rendered = [...document.querySelectorAll("[data-section]")].map((each) =>
      each.getAttribute("data-section"),
    );
    expect(rendered).toEqual([" record", "face", "corpus"]);
    expect(within(section(/Corpus/)).getByText("Not in the schema")).toBeTruthy();
    expect(within(section(/Face/)).queryByText("Not in the schema")).toBeNull();
  });

  it("groups the sections, and drops a group the record has nothing for", async () => {
    // Only appearance keys here, so Direction and Summary have nothing to draw.
    // A group rendered empty reads as a form with a hole in it.
    read.mockResolvedValue(
      record({ profile: { face: { hair: "short" }, identity: { apparent_age: "40s" } } }),
    );
    await open();

    // Twice each when present — the rail names a group and so does the column.
    expect(screen.getAllByText("Appearance")).toHaveLength(2);
    expect(screen.queryAllByText("Direction")).toHaveLength(0);
    expect(screen.queryAllByText("Summary")).toHaveLength(0);
  });

  it("puts an off-schema key in its own group, after every real one", async () => {
    read.mockResolvedValue(
      record({ profile: { corpus: [{ file: "<name>_in_7.png" }], voice: { accent: "flat" } } }),
    );
    await open();

    const headings = [...document.querySelectorAll("[data-section]")].map((each) =>
      each.getAttribute("data-section"),
    );
    expect(headings).toEqual([" record", "voice", "corpus"]);
    // The group heading, the rail's copy of it, and the badge on the trigger.
    expect(screen.getAllByText("Not in the schema")).toHaveLength(3);
  });

  it("tells you to reread the summary when what it summarises moves", async () => {
    read.mockResolvedValue(
      record({
        profile: { face: { hair: "short" }, text_identity_block: "A tall figure." },
      }),
    );
    await open();

    // Nothing edited yet: the paragraph still matches what it was written from.
    expect(screen.queryByText(/sections this summarises have changed/)).toBeNull();

    fireEvent.change(screen.getByLabelText("Hair"), { target: { value: "long" } });

    expect(screen.getByText(/sections this summarises have changed/)).toBeTruthy();
  });

  it("gives the summary no way to regenerate itself", async () => {
    // There is nothing to regenerate it WITH — the paragraph is written by
    // Claude and studio's API calls no model. A button here would be a lie.
    read.mockResolvedValue(record({ profile: { text_identity_block: "A tall figure." } }));
    await open();

    expect(screen.queryByRole("button", { name: /regenerate/i })).toBeNull();
    // Editable, and not marked read-only: it is the source of truth for what a
    // start-frame engine is handed, not a cache of the sections above it.
    const box = screen.getByDisplayValue("A tall figure.");
    expect(box).toBeTruthy();
    expect(box.hasAttribute("readonly")).toBe(false);
  });

  it("says what each schema section is for", async () => {
    await open();

    // The complaint this answers: nine characters of `rendering.default_style`
    // that every shoot depends on looked exactly as important as three thousand
    // characters of `face` that no code reads.
    expect(screen.getByText(/what a prompt gets written from/)).toBeTruthy();
  });
});
