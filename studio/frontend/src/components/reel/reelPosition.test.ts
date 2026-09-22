import { beforeEach, expect, it } from "vitest";

import { forgetPosition, recallPosition, rememberPosition } from "./reelPosition";

beforeEach(() => window.localStorage.clear());

it("starts from the top when nothing was remembered", () => {
  expect(recallPosition("proj-1")).toBeNull();
});

it("recalls the node it was left on, per project", () => {
  rememberPosition("proj-1", "node-a");
  rememberPosition("proj-2", "node-b");
  expect(recallPosition("proj-1")).toBe("node-a");
  expect(recallPosition("proj-2")).toBe("node-b");
});

it("forgets a project's place without touching another's", () => {
  rememberPosition("proj-1", "node-a");
  rememberPosition("proj-2", "node-b");
  forgetPosition("proj-1");
  expect(recallPosition("proj-1")).toBeNull();
  expect(recallPosition("proj-2")).toBe("node-b");
});
