import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { useSearchParamState } from "../../hooks/useSearchParamState";
import { FilterBar } from "./FilterBar";

afterEach(cleanup);

/**
 * One URL-backed field, standing in for the real callers' several — proves the
 * contract this component makes: it draws the disclosure and the badge, and
 * everything a field holds is the caller's own `useSearchParamState`.
 */
function Harness() {
  const [q, setQ] = useSearchParamState("q", "");
  return (
    <FilterBar activeCount={q ? 1 : 0} onClear={() => setQ("")}>
      <input aria-label="Query" value={q} onChange={(event) => setQ(event.target.value)} />
    </FilterBar>
  );
}

function open(initial = "/") {
  render(
    <MemoryRouter initialEntries={[initial]}>
      <Harness />
    </MemoryRouter>,
  );
}

it("is collapsed by default", () => {
  open();
  expect(
    screen.getByRole("button", { name: /^Filter/ }).getAttribute("aria-expanded"),
  ).toBe("false");
  // `inert` rather than absent — the field is real DOM, just not reachable.
  // jsdom does not reflect the IDL property, so the attribute is what is
  // checked, exactly as `Collapsible.Panel` sets it.
  expect(
    screen.getByLabelText("Query").closest('[role="region"]')?.getAttribute("inert"),
  ).toBe("");
});

it("shows a mono count badge only once a field is active", () => {
  open();
  expect(screen.queryByText("1")).toBeNull();

  open("/?q=jason");
  expect(screen.getByText("1")).toBeTruthy();
});

it("Clear resets the field it holds, which is URL state", () => {
  open("/?q=jason");
  fireEvent.click(screen.getByRole("button", { name: /^Filter/ }));
  expect((screen.getByLabelText("Query") as HTMLInputElement).value).toBe("jason");

  fireEvent.click(screen.getByRole("button", { name: "Clear" }));
  expect((screen.getByLabelText("Query") as HTMLInputElement).value).toBe("");
  // The badge reflects the caller's own count, not a value FilterBar tracks.
  expect(screen.queryByText("1")).toBeNull();
});

/**
 * The panel's clip is what hid every dropdown a field in here opens — the tag
 * picker's list, the Runs table's Status and Character surfaces. It is real
 * CSS, which jsdom does not compute, so what is held up is the class that
 * carries it and the timing: on only once the open animation is over, off the
 * moment a close starts.
 */
it("un-clips the panel once it has finished opening, and re-clips on close", () => {
  vi.useFakeTimers();
  try {
    open();
    const wrapper = () => screen.getByLabelText("Query").closest('[role="region"]')!.parentElement!;
    const unclipped = () => wrapper().className.includes("overflow-visible");

    expect(unclipped()).toBe(false);

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /^Filter/ }));
    });
    // Still clipped while the package's grid-rows transition runs.
    expect(unclipped()).toBe(false);
    act(() => {
      vi.advanceTimersByTime(250);
    });
    expect(unclipped()).toBe(true);

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /^Filter/ }));
    });
    expect(unclipped()).toBe(false);
  } finally {
    vi.useRealTimers();
  }
});
