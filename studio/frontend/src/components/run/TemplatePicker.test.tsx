import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { TestProviders } from "../../test-providers";
import type { TemplateLibrary } from "../../types";

vi.mock("../../apis/studio", () => ({
  getTemplates: vi.fn(),
}));

import { getTemplates } from "../../apis/studio";
import { TemplatePicker } from "./TemplatePicker";

const read = vi.mocked(getTemplates);

function show() {
  return render(<TemplatePicker onPick={() => {}} cast={0} />, { wrapper: TestProviders });
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

/**
 * The same empty state the Templates page shows now that it exists, rather
 * than a paragraph of its own — a fresh dev stack seeds one character and no
 * templates, so this is the first thing a picker opened there shows.
 */
it("says there are no templates yet, the way the Templates page does", async () => {
  const empty: TemplateLibrary = { blocks: {}, templates: [] };
  read.mockResolvedValue(empty);

  show();
  fireEvent.click(screen.getByRole("button", { name: "Start from a template" }));

  expect(await screen.findByText(/No templates yet/i)).toBeTruthy();
  expect(screen.getByText(/templates push/)).toBeTruthy();
});
