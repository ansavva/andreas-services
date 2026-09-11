import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { EntityRow } from "./EntityRow";
import { TestProviders } from "../../test-providers";

/**
 * The one row every list in the app draws through now. What is worth pinning
 * here is what a bespoke row could not offer at all: that it is a real link.
 */

afterEach(cleanup);

/** Where the router actually landed, read by whichever test wants it. */
let landed = "";

function Land() {
  landed = useLocation().pathname;
  return <span>landed</span>;
}

function draw(ui: React.ReactElement, path = "/") {
  landed = "";
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={path} element={ui} />
        <Route path="/elsewhere/:id" element={<Land />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
}

it("renders as a link when it has somewhere to go", () => {
  draw(<EntityRow title="A scene" to="/elsewhere/1" />);
  const link = screen.getByRole("link", { name: "A scene" }) as HTMLAnchorElement;
  expect(link.getAttribute("href")).toBe("/elsewhere/1");
});

it("a plain click is the router's", () => {
  draw(<EntityRow title="A scene" to="/elsewhere/1" />);
  fireEvent.click(screen.getByRole("link", { name: "A scene" }));
  expect(landed).toBe("/elsewhere/1");
});

it("does not intercept a modified click — that one is the browser's", () => {
  draw(<EntityRow title="A scene" to="/elsewhere/1" />);
  fireEvent.click(screen.getByRole("link", { name: "A scene" }), { metaKey: true });
  // jsdom does not open a new tab on a modified click, so the only observable
  // fact is that this component did not navigate itself — `preventDefault`
  // was never called, which `EntityRow.press` guards on `isModifiedPress`.
  expect(landed).toBe("");
});

it("a row with no address and no onOpen is a plain, disabled button", () => {
  draw(<EntityRow title="Not viewable" />);
  const button = screen.getByRole("button", { name: "Not viewable" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
});

it("falls back to onOpen when there is no address", () => {
  const onOpen = vi.fn();
  draw(<EntityRow title="A file" onOpen={onOpen} />);
  fireEvent.click(screen.getByRole("button", { name: "A file" }));
  expect(onOpen).toHaveBeenCalled();
});

it("draws a placeholder thumb carrying the kind, when there is no picture", () => {
  draw(<EntityRow title="A run" thumb={{ placeholder: "video" }} onOpen={vi.fn()} />);
  expect(screen.getByText("video")).toBeTruthy();
});

it("draws a supplied icon in place of a thumb, for a file or a folder", () => {
  draw(<EntityRow title="clip.mp4" thumb={{ icon: <svg data-testid="file-icon" /> }} onOpen={vi.fn()} />);
  expect(screen.getByTestId("file-icon")).toBeTruthy();
});

it("marks the selected row without touching the unselected default", () => {
  draw(<EntityRow title="A row" to="/elsewhere/1" selected />);
  const wrapper = screen.getByRole("link", { name: "A row" }).parentElement;
  expect(wrapper?.className).toMatch(/border-primary/);
  expect(wrapper?.className).toMatch(/ring-primary/);

  cleanup();
  draw(<EntityRow title="A row" to="/elsewhere/1" />);
  const plain = screen.getByRole("link", { name: "A row" }).parentElement;
  expect(plain?.className).not.toMatch(/ring-primary/);
});
