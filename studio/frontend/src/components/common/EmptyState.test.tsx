import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { EmptyState } from "./EmptyState";

afterEach(cleanup);

/**
 * An empty list says one sentence, and only carries a hint or a control when
 * it was given one. What these pin is the absence: no border, no alert role,
 * nothing that reads as an event — an empty list is a fact, not a failure.
 */
describe("an empty state", () => {
  it("is the title alone when that is all it was given", () => {
    render(<EmptyState title="No scenes yet." />);

    expect(screen.getByText("No scenes yet.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("puts the hint under the title", () => {
    render(
      <EmptyState
        title="No scenes yet."
        hint="A scene is shots stitched into one continuous take."
      />,
    );

    const title = screen.getByText("No scenes yet.");
    const hint = screen.getByText(/one continuous take/);
    // DOCUMENT_POSITION_FOLLOWING: the hint comes after the title.
    expect(title.compareDocumentPosition(hint) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders the action it is handed, so a page's own create control can sit here", () => {
    render(
      <EmptyState
        title="No projects yet."
        action={<button type="button">New project</button>}
      />,
    );

    expect(screen.getByRole("button", { name: "New project" })).toBeTruthy();
  });
});
