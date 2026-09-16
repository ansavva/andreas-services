import { describe, expect, it } from "vitest";

import { describeBinary, kindOfFile } from "./media";

describe("kindOfFile", () => {
  it("classifies by extension the way the API does", () => {
    expect(kindOfFile("frame.PNG")).toBe("image");
    expect(kindOfFile("clip.mp4", "video/mp4")).toBe("video");
    expect(kindOfFile("prompt.json", "application/json")).toBe("text");
    expect(kindOfFile("notes.md")).toBe("text");
    expect(kindOfFile("orbit_high.safetensors", "application/octet-stream")).toBe("other");
  });

  it("falls back to the content type for a name that does not say", () => {
    expect(kindOfFile("blob", "image/webp")).toBe("image");
    expect(kindOfFile("blob", "text/plain")).toBe("text");
    expect(kindOfFile("blob", "application/octet-stream")).toBe("other");
    expect(kindOfFile("blob")).toBe("other");
  });
});

it("names a binary file for the page that cannot draw it", () => {
  expect(describeBinary("wan22_high.safetensors")).toBe("LoRA / model weights");
  expect(describeBinary("thing.bin")).toBe("File");
});
