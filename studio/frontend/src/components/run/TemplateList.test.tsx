import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { TestProviders } from "../../test-providers";
import type { TemplateLibrary } from "../../types";

vi.mock("../../apis/studio", () => ({
  getTemplates: vi.fn(),
}));

import { getTemplates } from "../../apis/studio";
import { TemplateList } from "./TemplateList";

const read = vi.mocked(getTemplates);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

/**
 * The same empty state the Templates page shows, rather than a paragraph of
 * its own — a fresh dev stack seeds one character and no templates, so this
 * is the first thing the dropdown shows there.
 */
it("says there are no templates yet, the way the Templates page does", async () => {
  const empty: TemplateLibrary = { blocks: {}, templates: [] };
  read.mockResolvedValue(empty);

  render(<TemplateList onPick={() => {}} cast={0} />, {
    wrapper: TestProviders,
  });

  expect(await screen.findByText(/No templates yet/i)).toBeTruthy();
  expect(screen.getByText(/templates push/)).toBeTruthy();
});

it("a pick hands over the prompt, and says when it cites more cast than the run binds", async () => {
  read.mockResolvedValue({
    blocks: {},
    templates: [
      {
        id: "t1",
        name: "Two up",
        prompt: "{character.1.profile} and {character.2.profile}\nmore",
        description: "",
        tags: [],
      },
    ],
  });
  const onPick = vi.fn();
  render(<TemplateList onPick={onPick} cast={1} />, { wrapper: TestProviders });

  const row = await screen.findByRole("button", { name: /Two up/ });
  expect(row.textContent).toContain("Cites character 2; this run binds 1");
  fireEvent.click(row);
  expect(onPick).toHaveBeenCalledWith(
    "{character.1.profile} and {character.2.profile}\nmore",
  );
});
