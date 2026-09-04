import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { RunSummary } from "../../types";
import { TestProviders } from "../../test-providers";

vi.mock("../media/MediaThumb", () => ({ MediaThumb: () => <div>thumb</div> }));

vi.mock("../../apis/studio", () => ({ getRuns: vi.fn() }));

import { getRuns } from "../../apis/studio";
import { RunsTable } from "./RunsTable";

const list = vi.mocked(getRuns);

const PROJECT = "proj-0001";

function run(over: Partial<RunSummary> = {}): RunSummary {
  return {
    id: "run-0001",
    project: PROJECT,
    status: "succeeded",
    kind: "image",
    model: "openai/gpt-image-2",
    created: "2026-08-28T00:00:00Z",
    cost: null,
    thumb: null,
    ...over,
  };
}

/**
 * The mock answers the way the ROUTE does, which is the whole point of it.
 *
 * A listing naming no status and not asking for drafts gets none, so a mock that
 * returned the same rows however it was called would pass this file while the
 * real screen stayed empty — the bug being covered here.
 */
function library(rows: RunSummary[]) {
  list.mockImplementation((params: { status?: string; include?: string } = {}) => {
    let out = rows;
    if (params.status) out = rows.filter((each) => each.status === params.status);
    else if (params.include !== "drafts") out = rows.filter((each) => each.status !== "draft");
    return Promise.resolve({ runs: out, cursor: null });
  });
}

/** Reports `location.search`, so a test can assert a filter landed in the URL. */
function SearchProbe() {
  const location = useLocation();
  return <span data-testid="search">{location.search}</span>;
}

function open() {
  render(
    <TestProviders>
      <MemoryRouter>
        <RunsTable projectId={PROJECT} characters={[]} to={() => "/x"} />
        <SearchProbe />
      </MemoryRouter>
    </TestProviders>,
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

it("asks for drafts when no status is named, because the control says Any status", async () => {
  library([]);
  open();

  await waitFor(() =>
    expect(list).toHaveBeenCalledWith(expect.objectContaining({ include: "drafts" })),
  );
});

it("shows a project holding nothing but unsent payloads", async () => {
  library([run({ id: "run-waiting", status: "draft" })]);
  open();

  // Before the fix this drew "Nothing here matches that search" against a
  // project with a full queue in it.
  expect(await screen.findByText("draft")).toBeTruthy();
  expect(screen.queryByText(/Nothing here matches/i)).toBeNull();
});

it("still narrows to exactly one status when one is named", async () => {
  library([
    run({ id: "run-waiting", status: "draft" }),
    run({ id: "run-done", status: "succeeded" }),
  ]);
  open();

  await waitFor(() => expect(screen.getByText("draft")).toBeTruthy());
  expect(screen.getByText("succeeded")).toBeTruthy();

  // The package's Select is an ARIA combobox button over a listbox, not a
  // native <select>, so it is opened and its option clicked.
  fireEvent.click(screen.getByRole("combobox", { name: /status/i }));
  fireEvent.click(await screen.findByRole("option", { name: "succeeded" }));

  await waitFor(() =>
    expect(list).toHaveBeenCalledWith(expect.objectContaining({ status: "succeeded" })),
  );
  // A named status is a narrowing, so `include` has no business being sent too.
  expect(list).not.toHaveBeenCalledWith(
    expect.objectContaining({ status: "succeeded", include: "drafts" }),
  );
});

it("the filters are collapsed by default", () => {
  library([]);
  open();

  expect(
    screen.getByRole("button", { name: /^Filter runs/ }).getAttribute("aria-expanded"),
  ).toBe("false");
});

it("choosing a status is URL state, and Clear resets it", async () => {
  library([run({ id: "run-waiting", status: "draft" })]);
  open();

  await waitFor(() => expect(screen.getByText("draft")).toBeTruthy());
  expect(screen.getByTestId("search")).toHaveProperty("textContent", "");

  fireEvent.click(screen.getByRole("combobox", { name: /status/i }));
  fireEvent.click(await screen.findByRole("option", { name: "draft" }));

  await waitFor(() => expect(screen.getByTestId("search")).toHaveProperty(
    "textContent",
    "?status=draft",
  ));

  fireEvent.click(screen.getByRole("button", { name: "Clear" }));
  await waitFor(() =>
    expect(screen.getByTestId("search")).toHaveProperty("textContent", ""),
  );
  await waitFor(() =>
    expect(list).toHaveBeenCalledWith(expect.objectContaining({ include: "drafts" })),
  );
});
