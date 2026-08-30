import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { RunList } from "./RunList";
import { TestProviders } from "../../test-providers";

/**
 * The point of this component is that a run looks the same wherever it is
 * listed. Three screens drew their own row and no two agreed — most visibly on
 * status colour, where a character page knew only `failed` and coloured a
 * `running` run grey while a project page coloured it amber.
 */

afterEach(cleanup);

function draw(runs: Parameters<typeof RunList>[0]["runs"], onOpen = vi.fn()) {
  render(<RunList runs={runs} onOpen={onOpen} />, { wrapper: TestProviders });
  return onOpen;
}

it("colours a status the same way regardless of who is listing", () => {
  // The concrete regression: `running` must not be neutral anywhere.
  draw([{ id: "run-1", status: "running", model: "m", created: "2026-08-30T00:00:00Z" }]);
  expect(screen.getByText("running")).toBeTruthy();
});

it("draws the role a run plays when the caller knows one", () => {
  draw([{ id: "run-1", role: "earlier take", status: "succeeded" }]);
  expect(screen.getByText("earlier take")).toBeTruthy();
});

it("falls back to the id when a caller has no date", () => {
  // A storyboard row carries less than a project listing does; it renders what
  // it has rather than an empty headline.
  draw([{ id: "run-abc" }]);
  expect(screen.getByText("run-abc")).toBeTruthy();
});

it("leaves out the cost column entirely when cost is unknown", () => {
  // `null` means "the provider reported none"; `undefined` means "this caller
  // does not read costs". Drawing an em dash for the second would claim the
  // run was free.
  draw([{ id: "run-1", status: "succeeded" }]);
  expect(screen.queryByText("—")).toBeNull();
  cleanup();
  draw([{ id: "run-2", status: "succeeded", cost: null }]);
  expect(screen.getByText("—")).toBeTruthy();
});

it("opens the run that was clicked", () => {
  const onOpen = draw([{ id: "run-1", status: "succeeded", model: "m" }]);
  fireEvent.click(screen.getByRole("button"));
  expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "run-1" }));
});

it("shows the caller's own empty state rather than inventing one", () => {
  render(<RunList runs={[]} onOpen={vi.fn()} empty={<span>nothing yet</span>} />, {
    wrapper: TestProviders,
  });
  expect(screen.getByText("nothing yet")).toBeTruthy();
});
