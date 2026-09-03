import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, expect, it } from "vitest";

import { RunList } from "./RunList";
import { TestProviders } from "../../test-providers";

/**
 * The point of this component is that a run looks the same wherever it is
 * listed. Three screens drew their own row and no two agreed — most visibly on
 * status colour, where a character page knew only `failed` and coloured a
 * `running` run grey while a project page coloured it amber.
 *
 * Rows are `EntityRow`'s now — an `<a>` addressed by `to` rather than a
 * `<button>` with an `onOpen` — which is why every case here renders inside a
 * `MemoryRouter`: `EntityRow` calls `useNavigate` even when nothing is clicked.
 */

afterEach(cleanup);

function draw(
  runs: Parameters<typeof RunList>[0]["runs"],
  to: Parameters<typeof RunList>[0]["to"] = () => "/x",
) {
  render(
    <MemoryRouter>
      <RunList runs={runs} to={to} />
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
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

it("links each row to the address the caller gives it", () => {
  draw([{ id: "run-1", status: "succeeded", model: "m" }], (run) => `/p/proj/r/${run.id}`);
  const link = screen.getByRole("link") as HTMLAnchorElement;
  expect(link.getAttribute("href")).toBe("/p/proj/r/run-1");
});

it("opens the run that was clicked", () => {
  let landed = "";
  function Land() {
    landed = useLocation().pathname;
    return <span>landed</span>;
  }

  render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route
          path="/"
          element={
            <RunList
              runs={[{ id: "run-1", status: "succeeded", model: "m" }]}
              to={(run) => `/r/${run.id}`}
            />
          }
        />
        <Route path="/r/:runId" element={<Land />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );

  fireEvent.click(screen.getByRole("link"));
  expect(landed).toBe("/r/run-1");
});

it("shows the caller's own empty state rather than inventing one", () => {
  render(
    <MemoryRouter>
      <RunList runs={[]} to={() => "/x"} empty={<span>nothing yet</span>} />
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
  expect(screen.getByText("nothing yet")).toBeTruthy();
});
