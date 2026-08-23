import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmDeleteButton } from "./ConfirmDeleteButton";

afterEach(cleanup);

const NOUN = "character <slug> and its reference library";

function button() {
  return screen.getByRole("button");
}

describe("a page-level destroy, which renders as text in every phase", () => {
  /**
   * The regression this pins: the visible span read `Confirm — delete …` in
   * *every* phase, so a page loaded with its delete button already looking
   * armed. `aria-label` was correct the whole time, which is what made it easy
   * to miss — the accessible name and the visible text simply disagreed.
   */
  it("says the bare word at rest, not the confirmation", () => {
    render(<ConfirmDeleteButton tone="page" noun={NOUN} onConfirm={() => Promise.resolve()} />);

    expect(button().textContent).toContain("Delete");
    expect(button().textContent).not.toContain("Confirm");
  });

  it("spells out what goes, once armed", () => {
    render(<ConfirmDeleteButton tone="page" noun={NOUN} onConfirm={() => Promise.resolve()} />);

    fireEvent.click(button());

    expect(button().textContent).toContain(`Confirm — delete ${NOUN}`);
  });

  it("names the whole thing to a screen reader in both phases", () => {
    // The visible word is short at rest; the accessible name is not, and it has
    // to contain the visible label either way (WCAG 2.5.3).
    render(<ConfirmDeleteButton tone="page" noun={NOUN} onConfirm={() => Promise.resolve()} />);

    expect(button().getAttribute("aria-label")).toBe(`Delete ${NOUN}`);

    fireEvent.click(button());
    expect(button().getAttribute("aria-label")).toBe(`Confirm — delete ${NOUN}`);
  });

  it("lets the armed sentence wrap, so a long noun cannot push the page sideways", () => {
    render(<ConfirmDeleteButton tone="page" noun={NOUN} onConfirm={() => Promise.resolve()} />);

    fireEvent.click(button());

    // Inline, because `buttonClass` is `whitespace-nowrap` at a fixed `h-8` and
    // which of two conflicting utilities wins is a stylesheet-order question.
    expect(button().style.whiteSpace).toBe("normal");
    expect(button().style.height).toBe("auto");
  });

  it("deletes only on the second press", async () => {
    const confirm = vi.fn(() => Promise.resolve());
    render(<ConfirmDeleteButton tone="page" noun={NOUN} onConfirm={confirm} />);

    fireEvent.click(button());
    expect(confirm).not.toHaveBeenCalled();

    fireEvent.click(button());
    await waitFor(() => expect(confirm).toHaveBeenCalledOnce());
  });

  it("disarms when focus leaves, so a half-press is never left live", () => {
    render(<ConfirmDeleteButton tone="page" noun={NOUN} onConfirm={() => Promise.resolve()} />);

    fireEvent.click(button());
    expect(button().textContent).toContain("Confirm");

    fireEvent.blur(button());
    expect(button().textContent).not.toContain("Confirm");
  });
});

describe("the tones that are an icon at rest", () => {
  it.each(["row", "bar"] as const)("shows no text for %s until it is armed", (tone) => {
    render(<ConfirmDeleteButton tone={tone} noun={NOUN} onConfirm={() => Promise.resolve()} />);

    expect(button().textContent).not.toContain("Delete");

    if (tone === "bar") {
      // `bar` is the one that grows into a sentence — it sits in a selection bar
      // that already says "3 selected", so the count is not restated at rest.
      fireEvent.click(button());
      expect(button().textContent).toContain(`Confirm — delete ${NOUN}`);
    }
  });
});
