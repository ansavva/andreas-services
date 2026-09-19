import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { PromptText } from "./PromptText";

afterEach(cleanup);

it("draws every placeholder as a pill, in the editor's own clothes", () => {
  const { container } = render(
    <PromptText text={"{block.face_only}\n\n{character.1.top} at golden hour"} />,
  );
  // A block is solid, a computed value dashed — the two kinds the editor draws.
  expect(screen.getByText("{block.face_only}").dataset.kind).toBe("block");
  expect(screen.getByText("{character.1.top}").dataset.kind).toBe("computed");
  // The prose between them is verbatim, line breaks included: `pre-wrap`,
  // not a paragraph per line, so the string is the string.
  expect(container.textContent).toBe("{block.face_only}\n\n{character.1.top} at golden hour");
});

it("leaves a doubled brace and a bare word as text", () => {
  render(<PromptText text="{{not a citation}} and {Nope}" />);
  expect(document.querySelector("[data-token]")).toBeNull();
});
