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

it("draws the cuts under the prompt, in the boxes the create panel writes them in", () => {
  render(
    <TestProviders>
      <RunPrompt
        row={row({
          version: 1,
          origin: "authored",
          prompt: "a coach's office, late afternoon",
          params: {
            duration: 8,
            multi_prompt: JSON.stringify([
              { prompt: "Wide shot, static. He kneads his shoulder.", duration: 5 },
              { prompt: "Medium shot, static. The other man stops at the desk.", duration: 3 },
            ]),
          },
        })}
      />
    </TestProviders>,
  );
  // The same `ShotCard` the editor draws, so a run reads back as it was written.
  expect(document.querySelectorAll("[data-shot-card]").length).toBe(2);
  expect(screen.getByText("Shot 1")).toBeTruthy();
  expect(screen.getByText("5s")).toBeTruthy();
  expect(screen.getByText("Wide shot, static. He kneads his shoulder.")).toBeTruthy();
  // And never the escaped JSON it is stored as.
  expect(screen.queryByText(/\{"prompt"/)).toBeNull();
});

it("says nothing about cuts on a run that has none", () => {
  render(
    <TestProviders>
      <RunPrompt row={row({ version: 1, origin: "authored", prompt: "a mug", params: { seed: 7 } })} />
    </TestProviders>,
  );
  expect(document.querySelector("[data-shots-read]")).toBeNull();
});
