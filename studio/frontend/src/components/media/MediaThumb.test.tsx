import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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

/**
 * A clip previews on hover everywhere but the runs wall, where it plays on
 * its own — and only while it is on screen.
 *
 * The setup's `IntersectionObserver` reports nothing, so a tile is never near
 * and a `<video>` never gets its `src`. These cases install one whose
 * callbacks a test can fire: the first call says the tile is near (the
 * source mounts), the second is the autoplay observer's answer.
 */
describe("a clip playing on its own", () => {
  type Callback = (entries: Array<{ isIntersecting: boolean }>) => void;
  let callbacks: Callback[];
  const original = window.IntersectionObserver;

  const install = () => {
    callbacks = [];
    class FakeObserver {
      constructor(callback: Callback) {
        callbacks.push(callback);
      }
      observe(): void {}
      disconnect(): void {}
    }
    // The setup defined it writable and not configurable, so assigned rather
    // than `stubGlobal`, which redefines.
    window.IntersectionObserver = FakeObserver as unknown as typeof IntersectionObserver;
    const play = vi
      .spyOn(HTMLMediaElement.prototype, "play")
      .mockImplementation(() => Promise.resolve());
    const pause = vi
      .spyOn(HTMLMediaElement.prototype, "pause")
      .mockImplementation(() => undefined);
    return { play, pause };
  };
  const intersect = (on: boolean) =>
    act(() => callbacks.forEach((each) => each([{ isIntersecting: on }])));

  afterEach(() => {
    // Unmount while `pause` is still the mock: the effect's cleanup calls it,
    // and jsdom's own throws "not implemented".
    cleanup();
    window.IntersectionObserver = original;
    vi.restoreAllMocks();
  });

  it("does not play by itself, and a hover leaving pauses it", () => {
    const { play, pause } = install();
    render(<MediaThumb nodeId="node-1" url="https://example.invalid/a.mp4" isVideo />);
    intersect(true);
    expect(play).not.toHaveBeenCalled();
    const box = screen.getByRole("presentation").parentElement!;
    fireEvent.pointerOver(box, { pointerType: "mouse" });
    expect(play).toHaveBeenCalledTimes(1);
    fireEvent.pointerOut(box, { pointerType: "mouse" });
    expect(pause).toHaveBeenCalledTimes(1);
  });

  it("with `autoplay`, plays once on screen, pauses off it, and a hover changes nothing", () => {
    const { play, pause } = install();
    render(
      <MediaThumb nodeId="node-1" url="https://example.invalid/a.mp4" isVideo autoplay />,
    );
    // Near, and the autoplay observer is armed by the same act.
    intersect(true);
    expect(callbacks).toHaveLength(2);
    // The autoplay observer alone answers now: it is the second one.
    act(() => callbacks[1]!([{ isIntersecting: true }]));
    expect(play).toHaveBeenCalledTimes(1);

    const box = screen.getByRole("presentation").parentElement!;
    fireEvent.pointerOut(box, { pointerType: "mouse" });
    expect(pause).not.toHaveBeenCalled();

    act(() => callbacks[1]!([{ isIntersecting: false }]));
    expect(pause).toHaveBeenCalledTimes(1);
  });
});
