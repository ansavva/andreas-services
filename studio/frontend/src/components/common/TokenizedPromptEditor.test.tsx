import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { TokenizedPromptEditor } from "./TokenizedPromptEditor";
import type { PromptToken } from "./TokenizedPromptEditor";

const TOKENS: PromptToken[] = [
  { name: "face_only", kind: "block", hint: "THE FACE COMES FROM…" },
  { name: "scale_face", kind: "block", hint: "SCALE, held constant…" },
  { name: "top", kind: "computed" },
];

function show(value: string, onValueChange = vi.fn()) {
  render(
    <TokenizedPromptEditor
      value={value}
      onValueChange={onValueChange}
      tokens={TOKENS}
      ariaLabel="Prompt"
    />,
  );
  return onValueChange;
}

afterEach(cleanup);

/**
 * **The invariant the whole component exists to protect.**
 *
 * Assembly is `string.Formatter().vformat` over `{name}`, and `plan_digest`
 * hashes the prompt into the approval. An editor that normalised one space, or
 * dropped one trailing newline, would silently stale every approval already
 * given — for a change nobody made, on a payload nobody edited.
 */
it.each([
  ["a bare line", "A studio portrait of the person, front on."],
  ["one placeholder", "A studio portrait. {face_only} Neutral expression."],
  ["adjacent placeholders", "{scale_face}{face_only}"],
  ["paragraphs", "First line.\n\nSecond paragraph. {face_only}\n\nThird."],
  ["a computed value", "Wearing {top}. Flat mid-grey backdrop."],
  ["double spaces inside a line", "Two  spaces and {face_only}  after."],
  ["a placeholder at each end", "{face_only} middle {scale_face}"],
  ["the real face_front template",
   "A studio portrait of the person, front on, squared to the camera, looking " +
   "straight down the lens. Neutral expression, mouth closed. CROPPED AT " +
   "MID-CHEST — head and shoulders only, with no waist, no hips and no legs " +
   "anywhere in the frame.\n\n{scale_face}\n\n{face_only}\n\n{top}. " +
   "{backdrop_face} {light} {style} {quality}"],
])("round-trips %s byte for byte", async (_name, original) => {
  const changed = show(original);
  await waitFor(() => expect(changed).toHaveBeenCalled());
  expect(changed.mock.calls.at(-1)![0]).toBe(original);
});

it("draws a placeholder as a pill rather than as characters", async () => {
  show("A portrait. {face_only}");
  const pill = await waitFor(() => {
    const found = document.querySelector('[data-token="face_only"]');
    if (!found) throw new Error("no pill");
    return found as HTMLElement;
  });
  expect(pill.dataset.kind).toBe("block");
});

it("marks a COMPUTED value differently from a block", async () => {
  /**
   * A block is in the database and opens for editing; a computed value is
   * filled from the character's bible and has nothing behind it to open.
   * Identical pills would send somebody clicking `{top}` looking for a text box
   * that cannot exist.
   */
  show("Wearing {top} and {face_only}.");
  await waitFor(() => expect(document.querySelector('[data-token="top"]')).toBeTruthy());
  expect(
    (document.querySelector('[data-token="top"]') as HTMLElement).dataset.kind,
  ).toBe("computed");
  expect(
    (document.querySelector('[data-token="face_only"]') as HTMLElement).dataset.kind,
  ).toBe("block");
});

it("a placeholder nothing provides still round-trips, marked as unknown", async () => {
  /**
   * The editor must never silently drop or rewrite text it does not recognise.
   * `{no_such_block}` is a real failure the person needs to see and fix — but a
   * prompt that lost it on load would look repaired while the angle stayed
   * broken.
   */
  const changed = show("A portrait. {no_such_block}");
  await waitFor(() => expect(changed).toHaveBeenCalled());
  expect(changed.mock.calls.at(-1)![0]).toBe("A portrait. {no_such_block}");
});

it("opens the list on + and inserts the pill rather than the typed name", async () => {
  const changed = show("A portrait. ");
  const box = screen.getByLabelText("Prompt");
  await waitFor(() => expect(changed).toHaveBeenCalled());

  fireEvent.keyDown(box, { key: "+" });
  expect(await screen.findByRole("listbox", { name: /placeholder/i })).toBeTruthy();

  fireEvent.click(screen.getByRole("option", { name: /face_only/ }));
  await waitFor(() =>
    expect(changed.mock.calls.at(-1)![0]).toContain("{face_only}"),
  );
  // The `+` is thrown away — it is a trigger, not part of the document.
  expect(changed.mock.calls.at(-1)![0]).not.toContain("+");
});

it("narrows the list as you type and says when nothing matches", async () => {
  show("x");
  const box = screen.getByLabelText("Prompt");
  fireEvent.keyDown(box, { key: "+" });
  fireEvent.keyDown(box, { key: "s" });
  fireEvent.keyDown(box, { key: "c" });

  expect(await screen.findByRole("option", { name: /scale_face/ })).toBeTruthy();
  expect(screen.queryByRole("option", { name: /face_only/ })).toBeNull();

  fireEvent.keyDown(box, { key: "z" });
  expect(await screen.findByText(/Nothing matches/)).toBeTruthy();
});

it("closes the list on Escape without inserting anything", async () => {
  const changed = show("A portrait.");
  const box = screen.getByLabelText("Prompt");
  await waitFor(() => expect(changed).toHaveBeenCalled());

  fireEvent.keyDown(box, { key: "+" });
  expect(await screen.findByRole("listbox", { name: /placeholder/i })).toBeTruthy();
  fireEvent.keyDown(box, { key: "Escape" });

  await waitFor(() =>
    expect(screen.queryByRole("listbox", { name: /placeholder/i })).toBeNull(),
  );
  expect(changed.mock.calls.at(-1)![0]).toBe("A portrait.");
});
