import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { FormBar } from "./FormBar";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const save = () => screen.getByRole("button", { name: /^Sav/ });
const revert = () => screen.getByRole("button", { name: "Revert" });

it("keeps both buttons dead until something changed", () => {
  const onSave = vi.fn();
  const onRevert = vi.fn();
  const { rerender } = render(
    <FormBar dirty={false} saving={false} onSave={onSave} onRevert={onRevert} />,
  );

  expect(save().textContent).toBe("Save");
  expect(save().hasAttribute("disabled")).toBe(true);
  expect(revert().hasAttribute("disabled")).toBe(true);

  rerender(<FormBar dirty saving={false} onSave={onSave} onRevert={onRevert} />);
  fireEvent.click(save());
  fireEvent.click(revert());
  expect(onSave).toHaveBeenCalledTimes(1);
  expect(onRevert).toHaveBeenCalledTimes(1);
});

it("says Saving… while a write is out, then Saved for two seconds", () => {
  vi.useFakeTimers();
  const noop = () => {};
  const { rerender } = render(<FormBar dirty saving onSave={noop} onRevert={noop} />);

  expect(save().textContent).toBe("Saving…");
  expect(save().hasAttribute("disabled")).toBe(true);

  // The write landed: the caller re-baselined, so the form is clean.
  rerender(<FormBar dirty={false} saving={false} onSave={noop} onRevert={noop} />);
  expect(save().textContent).toBe("Saved");

  act(() => vi.advanceTimersByTime(1999));
  expect(save().textContent).toBe("Saved");
  act(() => vi.advanceTimersByTime(1));
  expect(save().textContent).toBe("Save");
});

it("does not claim Saved when the write was refused", () => {
  vi.useFakeTimers();
  const noop = () => {};
  const { rerender } = render(<FormBar dirty saving onSave={noop} onRevert={noop} />);

  // A refusal keeps the draft, so the form is still dirty and carries the reason.
  rerender(<FormBar dirty saving={false} error="rev moved" onSave={noop} onRevert={noop} />);
  expect(save().textContent).toBe("Save");
  expect(screen.getByText("Could not save")).toBeTruthy();
  expect(screen.getByText("rev moved")).toBeTruthy();
});

it("typing during the flash puts Save back", () => {
  vi.useFakeTimers();
  const noop = () => {};
  const { rerender } = render(<FormBar dirty saving onSave={noop} onRevert={noop} />);
  rerender(<FormBar dirty={false} saving={false} onSave={noop} onRevert={noop} />);
  expect(save().textContent).toBe("Saved");

  rerender(<FormBar dirty saving={false} onSave={noop} onRevert={noop} />);
  expect(save().textContent).toBe("Save");
  expect(save().hasAttribute("disabled")).toBe(false);
});

it("sticks to the bottom only when asked, and never to the top", () => {
  const noop = () => {};
  const { container, rerender } = render(
    <FormBar dirty={false} saving={false} onSave={noop} onRevert={noop} />,
  );
  const bar = () => container.querySelector("[data-form-bar]")!;
  expect(bar().className).not.toContain("sticky");

  rerender(<FormBar dirty={false} saving={false} onSave={noop} onRevert={noop} sticky />);
  expect(bar().className).toContain("sticky");
  expect(bar().className).toContain("bottom-0");
  expect(bar().className).not.toContain("top-0");
});

it("carries the caption on the left in mono", () => {
  const noop = () => {};
  render(
    <FormBar dirty={false} saving={false} onSave={noop} onRevert={noop} meta="revision 5" />,
  );
  expect(screen.getByText("revision 5").className).toContain("font-mono");
});
