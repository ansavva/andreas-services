import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FileEntry } from "../../types";
import { FileDetailsPanel } from "./FileDetailsPanel";
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

function show(
  over: Partial<FileEntry> = {},
  onSave = vi.fn().mockResolvedValue({}),
  onRename = vi.fn().mockResolvedValue({}),
) {
  render(
    <FileDetailsPanel
      file={file(over)}
      onSave={onSave}
      onRename={onRename}
      onClose={vi.fn()}
    />,
    { wrapper: TestProviders },
  );
  return { onSave, onRename };
}

/** The two writes are separate routes, so every case asserts BOTH mocks. */
describe("the name", () => {
  it("saves through rename, and issues no describe write", async () => {
    const { onSave, onRename } = show();

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "wave-porch.webp" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onRename).toHaveBeenCalledWith("wave-porch.webp"));
    // Renaming a file is not a statement about what it shows. A describe write
    // here would re-send a description nobody touched.
    expect(onSave).not.toHaveBeenCalled();
  });

  it("offers no save while the name is unchanged", () => {
    show();

    expect(screen.getByRole("button", { name: "Save" }).hasAttribute("disabled")).toBe(
      true,
    );
  });

  it("writes both halves when both moved", async () => {
    const { onSave, onRename } = show();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "porch.webp" } });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "On the porch." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onRename).toHaveBeenCalledWith("porch.webp"));
    expect(onSave).toHaveBeenCalledWith({ description: "On the porch." });
  });

  it("keeps the panel open with the reason when the name is taken", async () => {
    // 409 is a name you fix by typing another one. Closing to say so would throw
    // away what was typed — which is the whole reason the API distinguishes it
    // from a 400.
    const { onSave, onRename } = show(
      {},
      vi.fn().mockResolvedValue({}),
      vi.fn().mockRejectedValue(new Error("that name is taken")),
    );

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "taken.webp" } });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "On the porch." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.getByText("that name is taken")).toBeTruthy());
    // The name goes first, so a rejection there leaves the description unsaved
    // and still in the field rather than committed behind an error about
    // something else.
    expect(onSave).not.toHaveBeenCalled();
    expect((screen.getByLabelText("Description") as HTMLTextAreaElement).value).toBe(
      "On the porch.",
    );
    expect(onRename).toHaveBeenCalledTimes(1);
  });
});

describe("the description", () => {
  it("saves on an explicit press, never on blur, and renames nothing", async () => {
    // Blur-to-save in an overlay that also closes on Escape is how an edit gets
    // committed by the gesture meant to abandon it.
    const { onSave, onRename } = show();

    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Shirtless at the pool." },
    });
    fireEvent.blur(screen.getByLabelText("Description"));
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({ description: "Shirtless at the pool." }),
    );
    expect(onRename).not.toHaveBeenCalled();
  });

  it("clears with null rather than an empty string", async () => {
    // `None` is a REMOVE server-side — an empty string would be a second way to
    // say "no description", which the row does not have.
    const { onSave } = show({ description: "something" });

    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ description: null }));
  });

  it("offers no save until something actually changed", () => {
    show({ description: "unchanged" });

    expect(screen.getByRole("button", { name: "Save" }).hasAttribute("disabled")).toBe(
      true,
    );
  });
});

describe("the dismissal guard", () => {
  function guarded() {
    const dirty = vi.fn();
    const view = render(
      <FileDetailsPanel
        file={file()}
        onSave={vi.fn().mockResolvedValue({})}
        onRename={vi.fn().mockResolvedValue({})}
        onClose={vi.fn()}
        onDirtyChange={dirty}
        unsavedWarning={false}
        onDiscard={vi.fn()}
        onKeepEditing={vi.fn()}
      />,
      { wrapper: TestProviders },
    );
    return { dirty, view };
  }

  it("reports a dirty form up, so the drawer can decline the dismissal", () => {
    const { dirty } = guarded();

    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Poolside." },
    });

    expect(dirty).toHaveBeenLastCalledWith(true);
  });

  it("reports a pristine one, so a dismissal is simply taken", () => {
    const { dirty } = guarded();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "other.webp" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "plate.webp" } });

    expect(dirty).toHaveBeenLastCalledWith(false);
  });

  it("keeps what was typed while the refused dismissal is on screen", () => {
    // The bug this exists for: reporting dirtiness through an effect that
    // depends on the CALLBACK re-runs it every render, and its cleanup says
    // "nothing typed here" — which put the warning away one render after it was
    // raised, so clicking outside a filled form appeared to do nothing at all.
    const { view } = guarded();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "porch.webp" } });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "On the porch." },
    });

    view.rerender(
      <FileDetailsPanel
        file={file()}
        onSave={vi.fn().mockResolvedValue({})}
        onRename={vi.fn().mockResolvedValue({})}
        onClose={vi.fn()}
        // Inline arrows, deliberately: a new identity on every render is what
        // the caller really passes.
        onDirtyChange={() => {}}
        unsavedWarning
        onDiscard={() => {}}
        onKeepEditing={() => {}}
      />,
    );

    expect(screen.getByText("Leave without saving?")).toBeTruthy();
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("porch.webp");
    expect((screen.getByLabelText("Description") as HTMLTextAreaElement).value).toBe(
      "On the porch.",
    );
    expect(screen.getByRole("button", { name: "Keep editing" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Discard" })).toBeTruthy();
  });
});

describe("the tags", () => {
  it("adds one that has never been used before", async () => {
    // Free-form is the whole point: there is no vocabulary to pick from, so the
    // input is the only way a tag is ever created.
    const { onSave, onRename } = show({ tags: ["poolside"] });

    fireEvent.change(screen.getByLabelText("Add a tag"), { target: { value: "whistle" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({ tags: ["poolside", "whistle"] }),
    );
    expect(onRename).not.toHaveBeenCalled();
  });

  it("adds on Enter without submitting anything behind it", async () => {
    const { onSave } = show();

    fireEvent.change(screen.getByLabelText("Add a tag"), { target: { value: "bleachers" } });
    fireEvent.keyDown(screen.getByLabelText("Add a tag"), { key: "Enter" });

    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ tags: ["bleachers"] }));
  });

  it("removes one, and names which in the label", async () => {
    const { onSave } = show({ tags: ["poolside", "shirtless"] });

    fireEvent.click(screen.getByRole("button", { name: "Remove poolside" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ tags: ["shirtless"] }));
  });

  it("leaves the case to the API rather than folding it here", async () => {
    // Whitespace is trimmed on the way out because the empty check needs it
    // anyway. Case is not: folding in two places is two implementations of one
    // rule, and the one that drifts is the one `--pick-tag` does not consult.
    const { onSave } = show();

    fireEvent.change(screen.getByLabelText("Add a tag"), { target: { value: " Poolside " } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ tags: ["Poolside"] }));
  });

  it("does nothing on an empty add", () => {
    const { onSave } = show();

    fireEvent.keyDown(screen.getByLabelText("Add a tag"), { key: "Enter" });

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Add" }).hasAttribute("disabled")).toBe(true);
  });
});
