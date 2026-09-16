import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AUTOPLAY_BUDGET, MediaThumb } from "./MediaThumb";

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

  it("plays at most the budget at once, and a clip leaving hands its slot to the next", () => {
    const { play } = install();
    const n = AUTOPLAY_BUDGET + 1;
    render(
      <>
        {Array.from({ length: n }, (_, i) => (
          <MediaThumb
            key={i}
            nodeId={`node-${i}`}
            url={`https://example.invalid/${i}.mp4`}
            isVideo
            autoplay
          />
        ))}
      </>,
    );
    // Every tile near: the first n callbacks are the `near` observers, and
    // the n autoplay observers are armed by that same act.
    intersect(true);
    expect(callbacks).toHaveLength(2 * n);
    const autoplayObservers = callbacks.slice(n);
    act(() => autoplayObservers.forEach((each) => each([{ isIntersecting: true }])));
    expect(play).toHaveBeenCalledTimes(AUTOPLAY_BUDGET);

    // The first clip scrolls off; the one that was waiting starts.
    act(() => autoplayObservers[0]!([{ isIntersecting: false }]));
    expect(play).toHaveBeenCalledTimes(AUTOPLAY_BUDGET + 1);
  });
});

/**
 * With a poster the clip costs nothing until it plays: the still is the
 * picture, the video is `preload="none"`, and the badge reads the recorded
 * length. Without one — a clip stored before the worker made stills — the
 * tile is what it always was.
 */
describe("a clip with a poster", () => {
  it("draws the still, loads no metadata, and badges the recorded length", () => {
    render(
      <MediaThumb
        nodeId="node-1"
        url="https://example.invalid/a.mp4"
        isVideo
        poster={{ node: "node-p", url: "https://example.invalid/a.poster.jpg" }}
        duration={5.2}
      />,
    );
    const still = screen.getByTestId("poster") as HTMLImageElement;
    expect(still.src).toBe("https://example.invalid/a.poster.jpg");
    const video = document.querySelector("video")!;
    expect(video.getAttribute("preload")).toBe("none");
    expect(screen.getByText("0:05")).toBeTruthy();
  });

  it("without one, the clip's own metadata is the poster, as before", () => {
    render(<MediaThumb nodeId="node-1" url="https://example.invalid/a.mp4" isVideo />);
    expect(screen.queryByTestId("poster")).toBeNull();
    expect(document.querySelector("video")!.getAttribute("preload")).toBe("metadata");
    expect(screen.getByText("video")).toBeTruthy();
  });
});
