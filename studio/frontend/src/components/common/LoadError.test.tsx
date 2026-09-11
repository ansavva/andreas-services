import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LoadError } from "./LoadError";

afterEach(cleanup);

/**
 * A failed read always offers the retry, and a page-level one also offers the
 * way off the page. The regression this pins: three of the five entity pages
 * rendered a bare alert with no button of any kind, so a dead link was a dead
 * end.
 */
describe("a load error", () => {
  it("names what failed and offers the retry", () => {
    const retry = vi.fn();
    render(<LoadError what="this run" message="504 from the gateway" onRetry={retry} />);

    expect(screen.getByRole("alert").textContent).toContain("Could not load this run");
    expect(screen.getByText("504 from the gateway")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("has no escape unless a page-level failure asks for one", () => {
    render(<LoadError what="scenes" message="offline" onRetry={() => {}} />);

    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("offers the escape beside the retry, and it goes where it says", () => {
    const leave = vi.fn();
    render(
      <LoadError
        what="this scene"
        message="offline"
        onRetry={() => {}}
        escape={{ label: "Back to home", onClick: leave }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Back to home" }));
    expect(leave).toHaveBeenCalledTimes(1);
  });
});
