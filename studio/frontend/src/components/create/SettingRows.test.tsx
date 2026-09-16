import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { TestProviders } from "../../test-providers";
import type { ModelSchema } from "../../types";
import { SettingRows } from "./CreateChips";

afterEach(cleanup);

const schema: ModelSchema = {
  model: "runpod/wan-2-6-t2v",
  props: {
    prompt: { type: "string" },
    negative_prompt: { type: "string", description: "What to keep out." },
    seed: { type: "integer", default: -1 },
    shot_type: { type: "string", enum: ["single", "multi"], default: "single" },
  },
  schemas: {},
};

function draw(params: Record<string, unknown> = {}) {
  const onParams = vi.fn();
  render(
    <TestProviders>
      <SettingRows schema={schema} skip={new Set()} params={params} onParams={onParams} />
    </TestProviders>,
  );
  return onParams;
}

it("a free string is a full-width textarea on its own line, not a chip", () => {
  draw();
  const field = screen.getByRole("textbox", { name: "Negative prompt" });
  expect(field.tagName).toBe("TEXTAREA");
  expect(field.closest("[data-setting-row]")?.hasAttribute("data-stacked")).toBe(true);
  // A listed value keeps the row shape: word left, chip right.
  const listed = screen.getByRole("button", { name: /Shot type/ });
  expect(listed.closest("[data-setting-row]")?.hasAttribute("data-stacked")).toBe(false);
});

it("typing into it writes the string", () => {
  const onParams = draw({ seed: 7 });
  const field = screen.getByRole("textbox", { name: "Negative prompt" });
  fireEvent.change(field, { target: { value: "watermark, text, jitter" } });
  expect(onParams).toHaveBeenLastCalledWith({ seed: 7, negative_prompt: "watermark, text, jitter" });
});

it("clearing it unsets the param rather than writing an empty string", () => {
  const onParams = draw({ seed: 7, negative_prompt: "watermark" });
  fireEvent.change(screen.getByRole("textbox", { name: "Negative prompt" }), {
    target: { value: "" },
  });
  expect(onParams).toHaveBeenLastCalledWith({ seed: 7 });
});

it("shows what is already set, in full", () => {
  const text = "static, still frame, blurry, low quality, distorted, watermark";
  draw({ negative_prompt: text });
  const field = screen.getByRole("textbox", { name: "Negative prompt" }) as HTMLTextAreaElement;
  expect(field.value).toBe(text);
});
