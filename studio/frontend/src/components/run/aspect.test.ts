import { describe, expect, it } from "vitest";

import { ratioOf } from "./aspect";

const plan = (params: Record<string, unknown>) => ({
  version: 1,
  origin: "authored" as const,
  prompt: "",
  params,
});

describe("ratioOf", () => {
  it("reads W:H off the plan", () => {
    expect(ratioOf({ kind: "video", plan: plan({ aspect_ratio: "9:16" }) })).toBe("9 / 16");
    expect(ratioOf({ kind: "image", plan: plan({ aspect_ratio: "2:3" }) })).toBe("2 / 3");
    expect(ratioOf({ kind: "image", plan: plan({ aspect_ratio: " 1:1 " }) })).toBe("1 / 1");
  });

  it("falls back to the kind when the plan does not say", () => {
    expect(ratioOf({ kind: "video", plan: plan({}) })).toBe("16 / 9");
    expect(ratioOf({ kind: "image", plan: plan({ aspect_ratio: "auto" }) })).toBe("3 / 4");
    expect(ratioOf({ kind: "image", plan: plan({ aspect_ratio: "match_input_image" }) })).toBe(
      "3 / 4",
    );
    expect(ratioOf({ kind: "image", plan: plan({ aspect_ratio: "0:4" }) })).toBe("3 / 4");
  });
});

it("reads a Runpod `size` of W*H pixels when there is no aspect_ratio", () => {
  expect(ratioOf({ kind: "video", plan: { params: { size: "720*1280" } } } as never)).toBe("720 / 1280");
  expect(ratioOf({ kind: "image", plan: { params: { size: "1280*720" } } } as never)).toBe("1280 / 720");
  // aspect_ratio still wins when both are present.
  expect(
    ratioOf({ kind: "video", plan: { params: { aspect_ratio: "9:16", size: "1280*720" } } } as never),
  ).toBe("9 / 16");
});
