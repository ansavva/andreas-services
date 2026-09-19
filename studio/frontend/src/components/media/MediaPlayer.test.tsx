import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MediaPlayer } from "./MediaPlayer";

/**
 * What is asserted here is the cycle the reel never had — poster, play in
 * place, close back to the poster — the chrome that must be ABSENT rather than
 * merely inert, and the two routes fullscreen takes now that a clip is
 * Video.js: the container where the API exists, the phone's own player where
 * it does not.
 *
 * jsdom implements neither `play` nor `pause` on `HTMLMediaElement`: the real
 * methods log "Not implemented" and return `undefined`. Stubbing them is the
 * environment's gap, not the component's.
 */
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  setFullscreenEnabled(false);
});

afterEach(() => {
  cleanup();
  setFullscreenEnabled(false);
  vi.restoreAllMocks();
});

/**
 * `document.fullscreenEnabled` is what Video.js reads to decide whether the
 * element API exists at all, and jsdom reports it undefined — which is the
 * same answer an iPhone gives, and the case worth pinning.
 */
function setFullscreenEnabled(value: boolean) {
  Object.defineProperty(document, "fullscreenEnabled", { value, configurable: true });
}

/**
 * The element Fullscreen API, as far as a test needs it: a request records the
 * element and says so, an exit clears it and says so. Video.js listens to
 * `fullscreenchange` on the document rather than trusting its own call, so
 * both halves have to fire.
 */
function stubElementFullscreen() {
  setFullscreenEnabled(true);
  let current: Element | null = null;
  Object.defineProperty(document, "fullscreenElement", {
    get: () => current,
    configurable: true,
  });
  Element.prototype.requestFullscreen = vi.fn(async function (this: Element) {
    current = this; // eslint-disable-line @typescript-eslint/no-this-alias -- the element the request was made on IS the fullscreen element.
    document.dispatchEvent(new Event("fullscreenchange"));
  });
  document.exitFullscreen = vi.fn(async () => {
    current = null;
    document.dispatchEvent(new Event("fullscreenchange"));
  });
}

/**
 * The iPhone: no element API, and a `<video>` that can be handed to the
 * system player. `webkitSetPresentationMode` is what Video.js falls back to,
 * and `webkitpresentationmodechanged` is how it hears the answer.
 */
function stubWebKitPresentation() {
  setFullscreenEnabled(false);
  const proto = HTMLVideoElement.prototype as unknown as {
    webkitPresentationMode?: string;
    webkitSetPresentationMode?: (mode: string) => void;
  };
  proto.webkitPresentationMode = "inline";
  proto.webkitSetPresentationMode = vi.fn(function (this: HTMLVideoElement, mode: string) {
    (this as unknown as { webkitPresentationMode: string }).webkitPresentationMode = mode;
    this.dispatchEvent(new Event("webkitpresentationmodechanged"));
  });
  return () => {
    delete proto.webkitPresentationMode;
    delete proto.webkitSetPresentationMode;
  };
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

/**
 * The package's store batches its notifications on a microtask, so anything a
 * press changes lands one tick after the press. Awaited after every store
 * change; `act` is what makes React commit the result.
 */
async function settle() {
  await act(async () => {});
}

function transport() {
  return screen.queryByRole("slider", { name: "Seek" });
}

describe("poster, play in place, close back to the poster", () => {
  it("starts as a poster with no transport and nothing to close", async () => {
    render(<MediaPlayer {...CLIP} />);

    expect(play()).toBeTruthy();
    expect(transport()).toBeNull();
    expect(screen.queryByRole("button", { name: /^Close/ })).toBeNull();
  });

  it("mounts playback in the same box on the first press, inside the gesture", async () => {
    render(<MediaPlayer {...CLIP} />);

    fireEvent.click(play());

    await settle();

    expect(transport()).toBeTruthy();
    expect(screen.getByRole("button", { name: "Back 5 seconds" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Forward 5 seconds" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Play cut_03.mp4" })).toBeNull();
    // The element is under the poster already, so the press is a real `play()`
    // on a real element inside a real click — the only place sound is granted.
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it("offers sound only once something is playing, and starts silent", async () => {
    render(<MediaPlayer {...CLIP} />);
    expect(screen.queryByRole("button", { name: /mute/i })).toBeNull();

    fireEvent.click(play());

    await settle();

    expect(screen.getByRole("button", { name: "Unmute (m)" })).toBeTruthy();
  });

  it("closes back to the poster without navigating", async () => {
    const onClose = vi.fn();
    render(<MediaPlayer {...CLIP} onClose={onClose} />);

    fireEvent.click(play());

    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Close cut_03.mp4" }));
    await settle();

    expect(play()).toBeTruthy();
    expect(transport()).toBeNull();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("pauses and rewinds the element it hands back", async () => {
    render(<MediaPlayer {...CLIP} />);

    fireEvent.click(play());

    await settle();
    const video = document.querySelector("video");
    expect(video).toBeTruthy();
    video!.currentTime = 7;

    fireEvent.click(screen.getByRole("button", { name: "Close cut_03.mp4" }));

    await settle();

    // Closing is a return to the first frame, not to wherever the clip stopped.
    expect(video!.currentTime).toBe(0);
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
  });

  it("skips the poster when the caller asked for autoplay", async () => {
    render(<MediaPlayer {...CLIP} autoPlay />);

    expect(transport()).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Play cut_03.mp4" })).toBeNull();
  });
});

/**
 * **Fullscreen is the package's, and it takes two routes.**
 *
 * Where the element API exists the CONTAINER goes fullscreen, so our chrome
 * is painted inside it. Where it does not — an iPhone, on any browser, since
 * every one of them is WebKit — the `<video>` is handed to the phone's own
 * player. The old in-app fallback for a clip is gone: it was a box under
 * Safari's bar, which was the worst of both.
 */
describe("maximize", () => {
  it("is not drawn where nothing can answer it", async () => {
    render(<MediaPlayer {...CLIP} />);
    fireEvent.click(play());
    await settle();

    expect(screen.queryByRole("button", { name: /ullscreen/ })).toBeNull();
  });

  it("fullscreens the container where the API exists, so the chrome is painted in it", async () => {
    stubElementFullscreen();
    let container: HTMLElement | null = null;
    render(<MediaPlayer {...CLIP} onContainerChange={(element) => (container = element)} />);
    fireEvent.click(play());
    await settle();

    fireEvent.click(screen.getByRole("button", { name: "Fullscreen (f)" }));

    await settle();

    expect(Element.prototype.requestFullscreen).toHaveBeenCalledTimes(1);
    expect(document.fullscreenElement).toBe(container);
    expect((container as HTMLElement | null)?.getAttribute("data-fullscreen")).toBe("native");
    expect(screen.getByRole("button", { name: "Exit fullscreen (f)" })).toBeTruthy();
  });

  it("hands the clip to the phone's own player where there is no element API", async () => {
    const restore = stubWebKitPresentation();
    try {
      render(<MediaPlayer {...CLIP} />);
      fireEvent.click(play());
      await settle();

      fireEvent.click(screen.getByRole("button", { name: "Fullscreen (f)" }));

      await settle();

      const video = document.querySelector("video")!;
      const proto = HTMLVideoElement.prototype as unknown as {
        webkitSetPresentationMode: (mode: string) => void;
      };
      expect(proto.webkitSetPresentationMode).toHaveBeenCalledWith("fullscreen");
      expect((video as unknown as { webkitPresentationMode: string }).webkitPresentationMode).toBe(
        "fullscreen",
      );
      expect(screen.getByRole("button", { name: "Exit fullscreen (f)" })).toBeTruthy();
    } finally {
      restore();
    }
  });

  it("is for viewing: transport, sound and the way out — no actions, no Close", async () => {
    stubElementFullscreen();
    const onClose = vi.fn();
    render(<MediaPlayer {...CLIP} onClose={onClose} actions={<button type="button">Frame</button>} />);
    fireEvent.click(play());
    await settle();
    expect(screen.getByRole("button", { name: "Frame" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Close cut_03.mp4" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Fullscreen (f)" }));

    await settle();

    expect(screen.queryByRole("button", { name: "Frame" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Close/ })).toBeNull();
    expect(transport()).toBeTruthy();
    // jsdom reports every element paused, so the transport offers Play here.
    expect(screen.getByRole("button", { name: /^(Play|Pause) \(space\)$/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Unmute (m)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Exit fullscreen (f)" })).toBeTruthy();

    // Out again, and the file's chrome is back.
    fireEvent.click(screen.getByRole("button", { name: "Exit fullscreen (f)" }));
    await settle();
    expect(screen.getByRole("button", { name: "Frame" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Close cut_03.mp4" })).toBeTruthy();
  });

  it("leaves fullscreen on Close, on the way back to the poster", async () => {
    stubElementFullscreen();
    render(<MediaPlayer {...CLIP} autoPlay />);
    fireEvent.click(screen.getByRole("button", { name: "Fullscreen (f)" }));
    await settle();
    // Close is not drawn in fullscreen; the page's own keys reach it through
    // the controls handed up, which is what `close` answers.
    fireEvent.click(screen.getByRole("button", { name: "Exit fullscreen (f)" }));
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Close cut_03.mp4" }));
    await settle();

    expect(document.fullscreenElement).toBeNull();
    expect(play()).toBeTruthy();
  });
});

describe("a still", () => {
  it("draws the image with no poster, no play and no transport", async () => {
    render(<MediaPlayer nodeId="node-2" url="https://example.invalid/a.png" name="a.png" />);

    expect(screen.getByRole("img", { name: "a.png" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Play/ })).toBeNull();
    expect(transport()).toBeNull();
  });

  /**
   * A still keeps the in-app fullscreen fallback a clip no longer needs: an
   * iPhone refuses `requestFullscreen` on anything but a `<video>`, and a
   * picture has no `<video>` to hand the phone.
   */
  it("expands in the app where the API is unavailable", async () => {
    render(<MediaPlayer nodeId="node-2" url="https://example.invalid/a.png" name="a.png" />);

    fireEvent.click(screen.getByRole("button", { name: "Fullscreen (f)" }));

    await settle();

    const exit = screen.getByRole("button", { name: "Exit fullscreen (f)" });
    const box = exit.closest(".fixed");
    expect(box).toBeTruthy();
    // And nothing else positioning it: Tailwind emits `relative` after
    // `fixed`, so a box wearing both stays put and this whole state is a
    // screen-sized box hanging off the page's corner.
    expect(box!.classList.contains("relative")).toBe(false);
    expect(box!.getAttribute("data-fullscreen")).toBe("app");
  });

  it("leaves the app's own fullscreen on Escape, and nothing else hears it", async () => {
    const onClose = vi.fn();
    render(
      <MediaPlayer nodeId="node-2" url="https://example.invalid/a.png" name="a.png" onClose={onClose} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Fullscreen (f)" }));
    await settle();

    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.getByRole("button", { name: "Fullscreen (f)" })).toBeTruthy();
    // One press leaves the picture, not the screen behind it.
    expect(onClose).not.toHaveBeenCalled();
  });

  /**
   * Every still drags its node to the create sheet — the picture on a
   * viewer's stage included — and a clip drags nothing. The `<img>` itself is
   * not draggable, so the browser's own image drag (a URL, which the sheet
   * refuses) never starts.
   */
  it("drags its node as a ref, and a clip does not", async () => {
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

  it("drags what it was told to — a run's output keeps its provenance", async () => {
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
  it("reports its own element, which is what a dialog portals into", async () => {
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

  it("reports fullscreen as the package sees it, by either route", async () => {
    stubElementFullscreen();
    const seen: boolean[] = [];
    render(<MediaPlayer {...CLIP} onFullscreenChange={(on) => seen.push(on)} />);
    fireEvent.click(play());
    await settle();
    expect(seen).toEqual([false]);

    fireEvent.click(screen.getByRole("button", { name: "Fullscreen (f)" }));

    await settle();
    expect(seen).toEqual([false, true]);

    fireEvent.click(screen.getByRole("button", { name: "Exit fullscreen (f)" }));

    await settle();
    expect(seen).toEqual([false, true, false]);
  });

  it("renders an overlay inside that element, so fullscreen paints it", async () => {
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
 * **The chrome goes away while a clip runs untouched.** The idle model is the
 * package's now; what is pinned here is that its state reaches our surface
 * as `invisible` — which is what takes the buttons out of the tab order and
 * out from under a finger — and the three behaviours a person would notice
 * if it stopped: gone after the idle time, back under a mouse, up while
 * paused.
 *
 * jsdom reports every element as `paused`, so "running" is faked the same
 * way the package learns it in a browser: the getter says false and a `play`
 * event says so.
 */
describe("the chrome hides while a clip runs", () => {
  // jsdom's own getter, put back rather than deleted: `paused` lives on the
  // prototype, and deleting the override would delete it too.
  const paused = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, "paused")!;
  const setRunning = (running: boolean) =>
    Object.defineProperty(
      HTMLMediaElement.prototype,
      "paused",
      running ? { get: () => false, configurable: true } : paused,
    );

  beforeEach(() => {
    vi.useFakeTimers();
    setRunning(true);
  });

  afterEach(() => {
    vi.useRealTimers();
    setRunning(false);
  });

  function chrome() {
    return document.querySelector("[data-clip-controls]")!;
  }

  async function running() {
    render(<MediaPlayer {...CLIP} />);
    fireEvent.click(play());
    await settle();
    const video = document.querySelector("video")!;
    fireEvent(video, new Event("play"));
    await settle();
    return video;
  }

  it("is drawn on play, gone after the idle time, and back when a mouse moves", async () => {
    const video = await running();
    expect(chrome().className).not.toContain("invisible");

    act(() => vi.advanceTimersByTime(2500));

    await settle();
    expect(chrome().className).toContain("invisible");

    fireEvent.pointerMove(video, { pointerType: "mouse", clientX: 100, clientY: 100 });

    await settle();
    expect(chrome().className).not.toContain("invisible");
  });

  it("stays up while the clip is paused", async () => {
    const video = await running();
    setRunning(false);
    fireEvent(video, new Event("pause"));
    await settle();

    act(() => vi.advanceTimersByTime(2500));

    await settle();
    expect(chrome().className).not.toContain("invisible");
  });
});
