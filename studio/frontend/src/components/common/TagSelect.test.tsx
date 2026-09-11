import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/studio", () => ({
  getTags: vi.fn(),
  deleteTag: vi.fn(),
  renameTag: vi.fn(),
}));

import { deleteTag, getTags, renameTag } from "../../apis/studio";
import { TagSelect } from "./TagSelect";

const vocabulary = vi.mocked(getTags);
const remove = vi.mocked(deleteTag);
const rename = vi.mocked(renameTag);

beforeEach(() => {
  vocabulary.mockResolvedValue({ scope: "file", tags: [{ name: "studio", count: 43 }] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

/** Render with management on, and open the list. */
async function open() {
  const onChange = vi.fn();
  render(<TagSelect scope="file" value={[]} onChange={onChange} manage />);
  fireEvent.focus(screen.getByLabelText("Add a tag"));
  await screen.findByText("studio");
  return onChange;
}

describe("deleting a tag, which rewrites every file carrying it", () => {
  it("opens the typed-name dialog and says how many files it comes off", async () => {
    /**
     * This used to fire on one un-confirmed click, with the count on a sibling
     * span. A tag is an entity with children — forty-three of them here — so it
     * takes the same gate a project does.
     */
    await open();

    fireEvent.click(screen.getByLabelText("Delete tag studio"));

    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Delete tag studio?");
    expect(dialog.textContent).toContain("43 files");
    expect(remove).not.toHaveBeenCalled();
  });

  it("deletes once the name is typed", async () => {
    remove.mockResolvedValue({ name: "studio", changed: 43 });
    await open();

    fireEvent.click(screen.getByLabelText("Delete tag studio"));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.change(within(dialog).getByLabelText("Confirm"), {
      target: { value: "studio" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(remove).toHaveBeenCalledWith("file", "studio"));
  });

  it("reports a delete that did not land, under the box", async () => {
    remove.mockRejectedValue(new Error("the library is read-only"));
    await open();

    fireEvent.click(screen.getByLabelText("Delete tag studio"));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.change(within(dialog).getByLabelText("Confirm"), {
      target: { value: "studio" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    expect(await screen.findByText("Could not delete the tag")).toBeTruthy();
    expect(screen.getByText("the library is read-only")).toBeTruthy();
  });
});

describe("renaming a tag", () => {
  it("reports a rename that did not land, which used to report nothing", async () => {
    rename.mockRejectedValue(new Error("that name is taken"));
    await open();

    fireEvent.click(screen.getByLabelText("Rename tag studio"));
    fireEvent.change(screen.getByLabelText("Rename studio"), {
      target: { value: "workshop" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Could not rename the tag")).toBeTruthy();
    expect(screen.getByText("that name is taken")).toBeTruthy();
  });
});
