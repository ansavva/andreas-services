import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { TestProviders } from "../../test-providers";
import type { RunFeedRow } from "../../types";
import { RunPrompt } from "./RunFeed";

afterEach(cleanup);

function row(plan: RunFeedRow["plan"]): RunFeedRow {
  return { plan } as RunFeedRow;
}

it("draws the negative prompt under the prompt, as prose under a word saying which it is", () => {
  render(
    <TestProviders>
      <RunPrompt
        row={row({
          version: 1,
          origin: "authored",
          prompt: "a lighthouse at golden hour",
          params: { negative_prompt: "static, blurry, watermark", seed: 7 },
        })}
      />
    </TestProviders>,
  );
  expect(screen.getByText("a lighthouse at golden hour")).toBeTruthy();
  expect(screen.getByText("Negative")).toBeTruthy();
  expect(screen.getByText("static, blurry, watermark")).toBeTruthy();
});

it("says nothing about a negative prompt that is absent or blank", () => {
  render(
    <TestProviders>
      <RunPrompt
        row={row({ version: 1, origin: "authored", prompt: "a mug", params: { negative_prompt: "  " } })}
      />
    </TestProviders>,
  );
  expect(screen.queryByText("Negative")).toBeNull();
});
