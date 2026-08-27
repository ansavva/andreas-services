import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FileEntry } from "../../types";
import { DescribePanel } from "./DescribePanel";
import { TestProviders } from "../../test-providers";

afterEach(cleanup);

function file(over: Partial<FileEntry> = {}): FileEntry {
  return {
    id: "node-0001",
    key: "<character>/reference/face/plate.webp",
    name: "plate.webp",
    size: 1024,
    last_modified: null,
    kind: "image",
    content_type: "image/webp",
    url: "https://example.invalid/plate.webp",
    ...over,
  };
}

function show(over: Partial<FileEntry> = {}, onSave = vi.fn().mockResolvedValue({})) {
  render(<DescribePanel file={file(over)} onSave={onSave} onClose={vi.fn()} />, { wrapper: TestProviders });
  return onSave;
}

describe("the description", () => {
  it("saves on an explicit press, never on blur", async () => {
    // Blur-to-save in an overlay that also closes on Escape is how an edit gets
    // committed by the gesture meant to abandon it.
    const save = show();

    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Shirtless at the pool." },
    });
    fireEvent.blur(screen.getByLabelText("Description"));
    expect(save).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Save description" }));
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith({ description: "Shirtless at the pool." }),
    );
  });

  it("clears with null rather than an empty string", async () => {
    // `None` is a REMOVE server-side — an empty string would be a second way to
    // say "no description", which the row does not have.
    const save = show({ description: "something" });

    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save description" }));

    await waitFor(() => expect(save).toHaveBeenCalledWith({ description: null }));
  });

  it("offers no save until something actually changed", () => {
    show({ description: "unchanged" });

    expect(
      screen.getByRole("button", { name: "Save description" }).hasAttribute("disabled"),
    ).toBe(true);
  });
});

describe("the tags", () => {
  it("adds one that has never been used before", async () => {
    // Free-form is the whole point: there is no vocabulary to pick from, so the
    // input is the only way a tag is ever created.
    const save = show({ tags: ["poolside"] });

    fireEvent.change(screen.getByLabelText("Add a tag"), { target: { value: "whistle" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(save).toHaveBeenCalledWith({ tags: ["poolside", "whistle"] }));
  });

  it("adds on Enter without submitting anything behind it", async () => {
    const save = show();

    fireEvent.change(screen.getByLabelText("Add a tag"), { target: { value: "bleachers" } });
    fireEvent.keyDown(screen.getByLabelText("Add a tag"), { key: "Enter" });

    await waitFor(() => expect(save).toHaveBeenCalledWith({ tags: ["bleachers"] }));
  });

  it("removes one, and names which in the label", async () => {
    const save = show({ tags: ["poolside", "shirtless"] });

    fireEvent.click(screen.getByRole("button", { name: "Remove poolside" }));

    await waitFor(() => expect(save).toHaveBeenCalledWith({ tags: ["shirtless"] }));
  });

  it("leaves the case to the API rather than folding it here", async () => {
    // Whitespace is trimmed on the way out because the empty check needs it
    // anyway. Case is not: folding in two places is two implementations of one
    // rule, and the one that drifts is the one `--pick-tag` does not consult.
    const save = show();

    fireEvent.change(screen.getByLabelText("Add a tag"), { target: { value: " Poolside " } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(save).toHaveBeenCalledWith({ tags: ["Poolside"] }));
  });

  it("does nothing on an empty add", () => {
    const save = show();

    fireEvent.keyDown(screen.getByLabelText("Add a tag"), { key: "Enter" });

    expect(save).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Add" }).hasAttribute("disabled")).toBe(true);
  });
});
