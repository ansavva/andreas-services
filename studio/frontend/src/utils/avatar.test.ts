import { describe, expect, it } from "vitest";

import { AVATAR_MAX_BYTES, initials, validateAvatarFile } from "./avatar";

describe("initials", () => {
  it("takes the first and last name's first letters, uppercased", () => {
    expect(initials("Ada Lovelace")).toBe("AL");
    expect(initials("ada byron king lovelace")).toBe("AL");
    expect(initials("  Ada  ")).toBe("A");
  });

  it("falls back to the address, then to a neutral mark", () => {
    expect(initials(null, "person@example.com")).toBe("P");
    expect(initials("", "person@example.com")).toBe("P");
    expect(initials("   ", "  ")).toBe("?");
    expect(initials()).toBe("?");
  });
});

describe("validateAvatarFile", () => {
  it("accepts the three types a browser makes, under the cap", () => {
    expect(validateAvatarFile({ type: "image/png", size: 10 })).toBeNull();
    expect(validateAvatarFile({ type: "image/jpeg", size: AVATAR_MAX_BYTES })).toBeNull();
    expect(validateAvatarFile({ type: "image/webp", size: 10 })).toBeNull();
  });

  it("refuses anything else, with the sentence to show", () => {
    expect(validateAvatarFile({ type: "image/gif", size: 10 })).toMatch(/PNG, JPEG or WebP/);
    expect(validateAvatarFile({ type: "text/plain", size: 10 })).toMatch(/PNG, JPEG or WebP/);
    expect(validateAvatarFile({ type: "image/png", size: AVATAR_MAX_BYTES + 1 })).toMatch(/3 MB/);
  });
});
