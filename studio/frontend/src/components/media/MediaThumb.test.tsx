import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MediaThumb } from "./MediaThumb";

afterEach(cleanup);

/** What a drag started on the box put into the transfer, by type. */
function drag(box: Element) {
  const data = new Map<string, string>();
  fireEvent.dragStart(box, {
    dataTransfer: { setData: (type: string, value: string) => data.set(type, value), types: [] },
  });
  return data;
}

/**
 * Every still is draggable to the create sheet, from wherever it is drawn —
 * this is the one place media is drawn, so this is where the drag starts. The
 * `<img>` inside is told not to drag, or the browser's own image drag (a URL)
 * would be the payload and the sheet would refuse it.
 */
describe("dragging a picture to the sheet", () => {
  it("a still drags its node as an object by default", () => {
    render(<MediaThumb nodeId="node-1" url="https://example.invalid/a.png" name="a.png" />);
    const img = screen.getByRole("presentation");
    expect(img.getAttribute("draggable")).toBe("false");
    const box = img.parentElement!;
    expect(box.getAttribute("draggable")).toBe("true");
    expect(JSON.parse(drag(box).get("application/x-studio-node")!)).toEqual({
      node: "node-1",
      url: "https://example.invalid/a.png",
      name: "a.png",
      kind: "object",
    });
  });

  it("drags the ref it was given instead — a run's output keeps its provenance", () => {
    render(
      <MediaThumb
        nodeId="node-1"
        url="https://example.invalid/a.png"
        name="a.png"
        drag={{ node: "node-1", name: "a.png", kind: "run", run: "run-1", output: 1 }}
      />,
    );
    const box = screen.getByRole("presentation").parentElement!;
    expect(JSON.parse(drag(box).get("application/x-studio-node")!)).toMatchObject({
      kind: "run",
      run: "run-1",
      output: 1,
    });
  });

  it("a clip drags nothing, and neither does a still told not to", () => {
    const { container, unmount } = render(
      <MediaThumb nodeId="node-2" url="https://example.invalid/a.mp4" name="a.mp4" isVideo />,
    );
    expect(container.querySelector("[draggable]")).toBeNull();
    unmount();

    const still = render(
      <MediaThumb nodeId="node-1" url="https://example.invalid/a.png" name="a.png" drag={false} />,
    );
    expect(still.container.querySelector("[draggable=true]")).toBeNull();
  });
});
