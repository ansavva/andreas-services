import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { PromptText } from "./PromptText";

afterEach(cleanup);

it("draws every citation as a pill, in the editor's own clothes", () => {
  const { container } = render(
    <PromptText text={"@block.face_only\n\n@character.1.top at golden hour"} />,
  );
  // A block at full weight, a computed value stepped back — the two the editor draws.
  expect(screen.getByText("@block.face_only").dataset.namespace).toBe("block");
  expect(screen.getByText("@character.1.top").dataset.namespace).toBe("character");
  // The prose between them is verbatim, line breaks included: `pre-wrap`,
  // not a paragraph per line, so the string is the string.
  expect(container.textContent).toBe("@block.face_only\n\n@character.1.top at golden hour");
});

it("leaves an address, shorthand and a bare word as text", () => {
  render(<PromptText text="me@block.example, shot @ f/2.8 and @Nope" />);
  expect(document.querySelector("[data-token]")).toBeNull();
});
