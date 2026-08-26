import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";

function Boom(): never {
  throw new Error("panel 3 has no node");
}

beforeEach(() => {
  // React logs the caught error itself, which is noise here and not the subject.
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("shows what broke instead of a blank page", async () => {
  // **This is the behaviour, not a nicety.** With nothing catching a render
  // throw React unmounts the whole tree, and the app becomes an empty document —
  // no message, no way to tell it apart from a stalled request or a dead
  // session, and nothing to put in a report.
  render(
    <ErrorBoundary>
      <Boom />
    </ErrorBoundary>,
  );

  expect(screen.getByText("This page could not be drawn")).toBeTruthy();
  expect(screen.getByText("panel 3 has no node")).toBeTruthy();
  expect(screen.getByRole("button", { name: /reload/i })).toBeTruthy();
});

it("names the address that failed, because that is what identifies the record", () => {
  window.history.pushState({}, "", "/o/node-441cbc02");

  render(
    <ErrorBoundary>
      <Boom />
    </ErrorBoundary>,
  );

  expect(screen.getByText("/o/node-441cbc02")).toBeTruthy();
});

it("stays out of the way when nothing throws", () => {
  render(
    <ErrorBoundary>
      <p>the board</p>
    </ErrorBoundary>,
  );

  expect(screen.getByText("the board")).toBeTruthy();
  expect(screen.queryByText("This page could not be drawn")).toBeNull();
});

it("still puts the error on the console for whoever is debugging", () => {
  const logged = vi.mocked(console.error);

  render(
    <ErrorBoundary>
      <Boom />
    </ErrorBoundary>,
  );

  expect(logged.mock.calls.some((c) => c[0] === "A page failed to render")).toBe(true);
});
