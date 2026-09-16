import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { TestProviders } from "../../test-providers";
import { ParamChips } from "./ParamChips";

afterEach(cleanup);

it("a long value wraps inside its pill rather than running the pill out of its column", () => {
  const long = "a very long free-text style note that no single line of a feed row can hold at any width";
  render(
    <TestProviders>
      <ParamChips params={{ seed: 990001, style_note: long }} model="runpod/wan-2-6-t2v" />
    </TestProviders>,
  );
  const value = screen.getByText(long);
  expect(value.className).toContain("break-words");
  const pill = value.parentElement as HTMLElement;
  expect(pill.className).toContain("max-w-full");
  expect(pill.className).not.toContain("whitespace-nowrap");
  // The key beside it stays on one line, so `style_note` never breaks mid-word.
  expect(screen.getByText("style_note").className).toContain("whitespace-nowrap");
});

it("the negative prompt is not a pill — RunPrompt draws it as prose", () => {
  render(
    <TestProviders>
      <ParamChips params={{ seed: 1, negative_prompt: "watermark, text" }} />
    </TestProviders>,
  );
  expect(screen.queryByText("negative_prompt")).toBeNull();
  expect(screen.getByText("seed")).toBeTruthy();
});

it("draws nothing for a plan with no scalar params and no model", () => {
  const { container } = render(
    <TestProviders>
      <ParamChips params={{ loras: [{ path: "x" }] }} />
    </TestProviders>,
  );
  expect(container.innerHTML).toBe("");
});
