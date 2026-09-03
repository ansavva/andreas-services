import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmDeleteButton } from "./ConfirmDeleteButton";
import { ARMED_MS } from "../../hooks/useArmed";
import { TestProviders } from "../../test-providers";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const NOUN = "character <slug> and its reference library";

function button() {
  return screen.getByRole("button");
}

function show(tone: "text" | "icon", onConfirm = () => Promise.resolve()) {
  render(<ConfirmDeleteButton tone={tone} noun={NOUN} onConfirm={onConfirm} />, {
    wrapper: TestProviders,
  });
}

describe("the text tone, which is a word at rest and a sentence armed", () => {
  /**
   * The regression this pins: the visible span read `Confirm — delete …` in
   * *every* phase, so a page loaded with its delete button already looking
   * armed. `aria-label` was correct the whole time, which is what made it easy
   * to miss — the accessible name and the visible text simply disagreed.
   */
  it("says the bare word at rest, not the confirmation", () => {
    show("text");

    expect(button().textContent).toContain("Delete");
    expect(button().textContent).not.toContain("Confirm");
  });

  it("spells out what goes, once armed", () => {
    show("text");

    fireEvent.click(button());

    expect(button().textContent).toContain(`Confirm — delete ${NOUN}`);
  });

  it("names the whole thing to a screen reader in both phases", () => {
    // The visible word is short at rest; the accessible name is not, and it has
    // to contain the visible label either way (WCAG 2.5.3).
    show("text");

    expect(button().getAttribute("aria-label")).toBe(`Delete ${NOUN}`);

    fireEvent.click(button());
    expect(button().getAttribute("aria-label")).toBe(`Confirm — delete ${NOUN}`);
  });

  it("wears the danger fill and wraps once armed, so a long noun cannot push the page sideways", () => {
    show("text");

    expect(button().className).not.toContain("bg-danger");

    fireEvent.click(button());

    // Classes, not an inline style: `buttonClass` merges through tailwind-merge,
    // which drops the intent's own fill and the `nowrap`/`h-8` these override.
    expect(button().className).toContain("bg-danger");
    expect(button().className).toContain("whitespace-normal");
    expect(button().className).toContain("h-auto");
    expect(button().className).not.toContain("whitespace-nowrap");
  });

  it("deletes only on the second press", async () => {
    const confirm = vi.fn(() => Promise.resolve());
    show("text", confirm);

    fireEvent.click(button());
    expect(confirm).not.toHaveBeenCalled();

    fireEvent.click(button());
    await waitFor(() => expect(confirm).toHaveBeenCalledOnce());
  });

  it("disarms when focus leaves, so a half-press is never left live", () => {
    show("text");

    fireEvent.click(button());
    expect(button().textContent).toContain("Confirm");

    fireEvent.blur(button());
    expect(button().textContent).not.toContain("Confirm");
  });

  it("disarms on Escape without letting it reach the page", () => {
    show("text");
    const reached = vi.fn();
    document.addEventListener("keydown", reached);

    fireEvent.click(button());
    fireEvent.keyDown(button(), { key: "Escape" });

    expect(button().textContent).not.toContain("Confirm");
    expect(reached).not.toHaveBeenCalled();
    document.removeEventListener("keydown", reached);
  });

  it("expires", () => {
    vi.useFakeTimers();
    show("text");

    fireEvent.click(button());
    act(() => vi.advanceTimersByTime(ARMED_MS));

    expect(button().textContent).not.toContain("Confirm");
  });
});

describe("the icon tone, which is a trash can at rest", () => {
  it("shows no text, and carries the same accessible name", () => {
    show("icon");

    expect(button().textContent).not.toContain("Delete");
    expect(button().getAttribute("aria-label")).toBe(`Delete ${NOUN}`);
  });

  it("turns into a danger square that says what the next press does", () => {
    show("icon");

    fireEvent.click(button());

    expect(button().getAttribute("aria-label")).toBe(`Confirm — delete ${NOUN}`);
    expect(button().className).toContain("bg-danger");
    // Still no visible text: the icon changed, and the sentence is for the
    // accessibility tree.
    expect(button().textContent).not.toContain("Delete");
  });

  it("expires the same way the text tone does", () => {
    vi.useFakeTimers();
    show("icon");

    fireEvent.click(button());
    act(() => vi.advanceTimersByTime(ARMED_MS));

    expect(button().getAttribute("aria-label")).toBe(`Delete ${NOUN}`);
    expect(button().className).not.toContain("bg-danger");
  });

  it("deletes only on the second press", async () => {
    const confirm = vi.fn(() => Promise.resolve());
    show("icon", confirm);

    fireEvent.click(button());
    fireEvent.click(button());

    await waitFor(() => expect(confirm).toHaveBeenCalledOnce());
  });
});
