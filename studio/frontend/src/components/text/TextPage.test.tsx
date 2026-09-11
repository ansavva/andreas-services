import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { TestProviders } from "../../test-providers";
import type { FileEntry } from "../../types";

vi.mock("../../apis/studio", () => ({
  getNodeText: vi.fn().mockResolvedValue({
    content: "hello",
    language: "text",
    truncated: false,
    id: "node-1",
    name: "notes.txt",
  }),
  saveNodeText: vi.fn(),
}));

import { TextPage } from "./TextPage";

const FILE: FileEntry = {
  id: "node-1",
  key: "characters/subject/notes.txt",
  name: "notes.txt",
  size: 5,
  last_modified: null,
  kind: "image",
  content_type: "text/plain",
  url: "https://signed.example/stale",
};

function show() {
  return render(
    <MemoryRouter>
      <TextPage file={FILE} onClose={() => {}} />
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

/**
 * The last full-screen takeover, gone. `TextPage` used to be `fixed inset-0
 * z-50` over a black backdrop with its own `role="dialog"` — the last screen
 * in the app that was not an ordinary page inside `AppLayout`. It is one now,
 * with its own `PageBar` like every other screen, so this asserts the escape
 * hatch is actually closed rather than trusting the diff that closed it.
 */
it("renders as an ordinary page, not a fixed-position takeover", async () => {
  const { container } = show();
  await screen.findByText("hello");

  expect(container.querySelector(".fixed")).toBeNull();
  expect(container.querySelector('[role="dialog"]')).toBeNull();
});

/**
 * The body-scroll lock went with the takeover. Both existed for the same
 * reason — the old page had no scrollable container of its own to sit inside,
 * `AppLayout`'s `<main>` does, so freezing `<body>` behind it would now freeze
 * the wrong element.
 */
it("never touches the document body's own style", async () => {
  const before = document.body.style.overflow;
  const { unmount } = show();
  await screen.findByText("hello");

  expect(document.body.style.overflow).toBe(before);
  unmount();
  expect(document.body.style.overflow).toBe(before);
});
