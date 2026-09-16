import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MediaPlayer } from "./MediaPlayer";

/**
 * What is asserted here is the cycle the reel never had — poster, play in
 * place, close back to the poster — and the one piece of chrome that must be
 * ABSENT rather than merely inert.
 *
 * jsdom implements neither `play` nor `pause` on `HTMLMediaElement`: the real
 * methods log "Not implemented" and return `undefined`, which `useMediaPlayback`
 * then calls `.catch` on. Stubbing them is the environment's gap, not the
 * component's.
 */
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  setFullscreenEnabled(false);
});

afterEach(() => {
  cleanup();
  setFullscreenEnabled(false);
});

/**
 * `document.fullscreenEnabled` is what `useFullscreen` reads to decide whether
 * the API exists at all, and jsdom reports it false — which is the same answer
 * an iPhone gives, and the case worth pinning.
 */
function setFullscreenEnabled(value: boolean) {
  Object.defineProperty(document, "fullscreenEnabled", { value, configurable: true });
}

const CLIP = {
  nodeId: "node-1",
  url: "https://example.invalid/clip.mp4?sig=1",
  name: "cut_03.mp4",
  isVideo: true,
};

function play() {
  return screen.getByRole("button", { name: "Play cut_03.mp4" });
}

function transport() {
  return screen.queryByRole("slider", { name: "Seek" });
}

describe("poster, play in place, close back to the poster", () => {
  it("starts as a poster with no transport and nothing to close", () => {
    render(<MediaPlayer {...CLIP} />);

    expect(play()).toBeTruthy();
    expect(transport()).toBeNull();
    expect(screen.queryByRole("button", { name: /^Close/ })).toBeNull();
  });

  it("mounts playback in the same box on the first press", () => {
    render(<MediaPlayer {...CLIP} />);

    fireEvent.click(play());

    expect(transport()).toBeTruthy();
    expect(screen.getByRole("button", { name: "Back 5 seconds" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Forward 5 seconds" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Play cut_03.mp4" })).toBeNull();
  });

  it("offers sound only once something is playing, and starts silent", () => {
    render(<MediaPlayer {...CLIP} />);
    expect(screen.queryByRole("button", { name: /mute/i })).toBeNull();

    fireEvent.click(play());

    // Muted, so the button offers the opposite. See the header of MediaPlayer
    // for why sound cannot be granted by the press that mounts the element.
    expect(screen.getByRole("button", { name: "Unmute (m)" })).toBeTruthy();
  });

  it("closes back to the poster without navigating", () => {
    const onClose = vi.fn();
    render(<MediaPlayer {...CLIP} onClose={onClose} />);

    fireEvent.click(play());
    fireEvent.click(screen.getByRole("button", { name: "Close cut_03.mp4" }));

    expect(play()).toBeTruthy();
    expect(transport()).toBeNull();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("pauses and rewinds the element it hands back", () => {
    render(<MediaPlayer {...CLIP} />);

    fireEvent.click(play());
    const video = document.querySelector("video");
    expect(video).toBeTruthy();
    video!.currentTime = 7;

    fireEvent.click(screen.getByRole("button", { name: "Close cut_03.mp4" }));

    // `useMediaPlayback` pauses and rewinds everything that is not current, and
    // closing is exactly "nothing is current" — which is what makes the poster
    // the first frame again rather than wherever the clip stopped.
    expect(video!.currentTime).toBe(0);
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
  });

  it("skips the poster when the caller asked for autoplay", () => {
    render(<MediaPlayer {...CLIP} autoPlay />);

    expect(transport()).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Play cut_03.mp4" })).toBeNull();
  });
});

/**
 * **Maximize is offered everywhere now, and answered two ways.**
 *
 * It used to be drawn only where `requestFullscreen` works — which is never on
 * an iPhone, since Safari refuses it on anything but a `<video>` — so the one
 * device where a picture is smallest was the one with no way to enlarge it.
 * `useFullscreen` falls back to an in-app expansion there, and jsdom is that
 * case: it defines no `fullscreenEnabled`.
 */
describe("maximize", () => {
  it("is offered where the API is unavailable, and expands in the app instead", () => {
    render(<MediaPlayer {...CLIP} />);
    fireEvent.click(play());

    fireEvent.click(screen.getByRole("button", { name: "Fullscreen (f)" }));

    // The app positions the box itself, because the browser has not: the same
    // state the native path reaches, drawn by us.
    const exit = screen.getByRole("button", { name: "Exit fullscreen (f)" });
    const box = exit.closest(".fixed");
    expect(box).toBeTruthy();
    // And nothing else positioning it: Tailwind emits `relative` after
    // `fixed`, so a box wearing both stays put and this whole state is a
    // screen-sized box hanging off the page's corner.
    expect(box!.classList.contains("relative")).toBe(false);
    expect(box!.getAttribute("data-fullscreen")).toBe("app");
  });

  it("leaves the app's own fullscreen on Escape, and nothing else hears it", () => {
    const onClose = vi.fn();
    render(<MediaPlayer {...CLIP} onClose={onClose} />);
    fireEvent.click(play());
    fireEvent.click(screen.getByRole("button", { name: "Fullscreen (f)" }));

    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.getByRole("button", { name: "Fullscreen (f)" })).toBeTruthy();
    // One press leaves the picture, not the screen behind it.
    expect(onClose).not.toHaveBeenCalled();
  });

  it("renders it where the API is available", () => {
    setFullscreenEnabled(true);
    render(<MediaPlayer {...CLIP} />);
    fireEvent.click(play());

    expect(screen.getByRole("button", { name: "Fullscreen (f)" })).toBeTruthy();
  });
});

describe("a still", () => {
  it("draws the image with no poster, no play and no transport", () => {
    render(<MediaPlayer nodeId="node-2" url="https://example.invalid/a.png" name="a.png" />);

    expect(screen.getByRole("img", { name: "a.png" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Play/ })).toBeNull();
    expect(transport()).toBeNull();
  });

  /**
   * Every still drags its node to the create sheet — the picture on a
   * viewer's stage included — and a clip drags nothing. The `<img>` itself is
   * not draggable, so the browser's own image drag (a URL, which the sheet
   * refuses) never starts.
   */
  it("drags its node as a ref, and a clip does not", () => {
    render(<MediaPlayer nodeId="node-2" url="https://example.invalid/a.png" name="a.png" />);
    const img = screen.getByRole("img", { name: "a.png" });
    expect(img.getAttribute("draggable")).toBe("false");
    const box = img.parentElement!;
    expect(box.getAttribute("draggable")).toBe("true");

    const data = new Map<string, string>();
    fireEvent.dragStart(box, {
      dataTransfer: { setData: (type: string, value: string) => data.set(type, value), types: [] },
    });
    expect(JSON.parse(data.get("application/x-studio-node")!)).toEqual({
      node: "node-2",
      url: "https://example.invalid/a.png",
      name: "a.png",
      kind: "object",
    });

    cleanup();
    render(<MediaPlayer {...CLIP} />);
    expect(screen.getByLabelText(/^Play/).parentElement!.getAttribute("draggable")).toBeNull();
  });

  it("drags what it was told to — a run's output keeps its provenance", () => {
    render(
      <MediaPlayer
        nodeId="node-2"
        url="https://example.invalid/a.png"
        name="a.png"
        drag={{ node: "node-2", kind: "run", run: "run-1", output: 2 }}
      />,
    );
    const data = new Map<string, string>();
    fireEvent.dragStart(screen.getByRole("img", { name: "a.png" }).parentElement!, {
      dataTransfer: { setData: (type: string, value: string) => data.set(type, value), types: [] },
    });
    expect(JSON.parse(data.get("application/x-studio-node")!)).toEqual({
      node: "node-2",
      kind: "run",
      run: "run-1",
      output: 2,
    });
  });
});

describe("the fullscreen container is exposed", () => {
  it("reports its own element, which is what a dialog portals into", () => {
    const seen: (HTMLElement | null)[] = [];
    const { unmount } = render(
      <MediaPlayer {...CLIP} onContainerChange={(element) => seen.push(element)} />,
    );

    // Reported from the ref callback, so the first thing the caller hears is the
    // element itself rather than a null it has to render around.
    expect(seen).toHaveLength(1);
    expect(seen[0]).toBeInstanceOf(HTMLElement);
    expect(seen[0]!.querySelector("video")).toBeTruthy();

    unmount();
    expect(seen.at(-1)).toBeNull();
  });

  it("reports fullscreen by the app's route as well as the browser's", () => {
    const seen: boolean[] = [];
    render(<MediaPlayer {...CLIP} onFullscreenChange={(on) => seen.push(on)} />);
    fireEvent.click(play());
    expect(seen).toEqual([false]);

    // No API here (jsdom, and an iPhone), so this is the in-app expansion —
    // the one `document.fullscreenElement` never reports.
    fireEvent.click(screen.getByRole("button", { name: "Fullscreen (f)" }));
    expect(seen).toEqual([false, true]);

    fireEvent.click(screen.getByRole("button", { name: "Exit fullscreen (f)" }));
    expect(seen).toEqual([false, true, false]);
  });

  it("renders an overlay inside that element, so fullscreen paints it", () => {
    let container: HTMLElement | null = null;
    render(
      <MediaPlayer
        {...CLIP}
        onContainerChange={(element) => (container = element)}
        overlay={<span data-testid="sheet">details</span>}
      />,
    );

    // A descendant of the fullscreen element, not a sibling of it: that is the
    // whole difference between an overlay that paints in fullscreen and one
    // that does not.
    expect((container as HTMLElement | null)?.contains(screen.getByTestId("sheet"))).toBe(true);
  });
});

/**
 * **The chrome goes away while a clip runs untouched.**
 *
 * jsdom has no `PointerEvent`, so the events below are plain `Event`s with a
 * `pointerType` set on them — which is the property React's synthetic event
 * reads, and the one the hook decides by. It also reports every element as
 * `paused`, so "running" is faked the same way the hook learns it in a
 * browser: the getter says false and a `play` event says so.
 */
describe("the chrome hides while a clip runs", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(HTMLMediaElement.prototype, "paused", {
      get: () => false,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    delete (HTMLMediaElement.prototype as { paused?: unknown }).paused;
  });

  function pointer(
    target: Element,
    type: string,
    pointerType: "mouse" | "touch",
    at: { clientX: number; clientY: number } = { clientX: 100, clientY: 100 },
  ) {
    const event = new Event(type, { bubbles: true });
    Object.assign(event, { pointerType, ...at });
    fireEvent(target, event);
  }

  /** A finger down and up in the same place — what iOS never turns into `click`. */
  function tap(target: Element) {
    pointer(target, "pointerdown", "touch");
    pointer(target, "pointerup", "touch");
  }

  function chrome() {
    return screen.getByRole("slider", { name: "Seek" }).closest(".transition-\\[opacity\\,visibility\\]")!;
  }

  function running() {
    render(<MediaPlayer {...CLIP} />);
    fireEvent.click(play());
    const video = document.querySelector("video")!;
    fireEvent(video, new Event("play"));
    return video;
  }

  it("is drawn on play, gone after the idle time, and back when a mouse moves", () => {
    const video = running();
    expect(chrome().className).not.toContain("invisible");

    act(() => vi.advanceTimersByTime(3000));
    expect(chrome().className).toContain("invisible");

    pointer(video, "pointermove", "mouse");
    expect(chrome().className).not.toContain("invisible");

    // Leaving hides at once — the bar is only wanted under a cursor. React
    // derives `onPointerLeave` from `pointerout`, so that is what is fired.
    pointer(video.parentElement!, "pointerout", "mouse");
    expect(chrome().className).toContain("invisible");
  });

  it("stays up while the clip is paused", () => {
    const video = running();
    fireEvent(video, new Event("pause"));

    act(() => vi.advanceTimersByTime(3000));
    expect(chrome().className).not.toContain("invisible");
  });

  it("is a switch under a finger: one tap brings it back, the next puts it away", () => {
    const video = running();
    act(() => vi.advanceTimersByTime(3000));
    expect(chrome().className).toContain("invisible");

    tap(video);
    expect(chrome().className).not.toContain("invisible");

    tap(video);
    expect(chrome().className).toContain("invisible");
  });

  it("a finger that travels is a scroll, not a tap", () => {
    const video = running();
    act(() => vi.advanceTimersByTime(3000));

    pointer(video, "pointerdown", "touch", { clientX: 100, clientY: 100 });
    pointer(video, "pointermove", "touch", { clientX: 100, clientY: 160 });
    pointer(video, "pointerup", "touch", { clientX: 100, clientY: 160 });
    expect(chrome().className).toContain("invisible");
  });

  it("ignores a mouse press on the picture — hover already owns it", () => {
    const video = running();
    act(() => vi.advanceTimersByTime(3000));
    expect(chrome().className).toContain("invisible");

    // Reveals — as any mouse activity over the box does — and the press
    // itself is not a switch: a second one does not put it away.
    pointer(video, "pointerdown", "mouse");
    pointer(video, "pointerup", "mouse");
    expect(chrome().className).not.toContain("invisible");
    pointer(video, "pointerdown", "mouse");
    pointer(video, "pointerup", "mouse");
    expect(chrome().className).not.toContain("invisible");
  });

  it("does not vanish under a finger on the seek bar", () => {
    running();
    act(() => vi.advanceTimersByTime(2000));
    pointer(screen.getByRole("slider", { name: "Seek" }), "pointerdown", "touch");

    act(() => vi.advanceTimersByTime(2000));
    expect(chrome().className).not.toContain("invisible");
  });
});
