import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MediaPlayer, type MediaPlayerControls } from "./MediaPlayer";

/**
 * A clip is Video.js's packaged skin, so what is asserted about it is the seam
 * around the player rather than the player: that the skin is drawn as shipped
 * and our controls sit beside it, that the container and the controls reach
 * the page, and the two routes fullscreen takes — the container where the
 * API exists, the phone's own player where it does not. A still is ours, and
 * its tests are the old ones.
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

describe("a clip is the packaged skin, with nothing of ours over the picture", () => {
  it("draws Video.js's own controls, and the app's actions outside the player", async () => {
    let container: HTMLElement | null = null;
    render(
      <MediaPlayer
        {...CLIP}
        actions={<button type="button">Frame</button>}
        onContainerChange={(element) => (container = element)}
      />,
    );
    await settle();

    // The skin's, by the skin's names: nothing here is a label we wrote.
    expect(screen.getByRole("button", { name: "Play" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Unmute" })).toBeTruthy();
    expect(screen.getByRole("slider", { name: "Seek" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Settings" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /\(space\)|\(m\)|\(f\)/ })).toBeNull();

    // The Frame menu is beside the player, not on it — and so not in the
    // element that goes fullscreen.
    const frame = screen.getByRole("button", { name: "Frame" });
    expect(container).toBeInstanceOf(HTMLElement);
    expect((container as HTMLElement | null)?.contains(frame)).toBe(false);
    expect((container as HTMLElement | null)?.querySelector("video")).toBeTruthy();
  });

  it("starts silent, which is the autoplay policy rather than a taste", async () => {
    render(<MediaPlayer {...CLIP} autoPlay />);
    await settle();

    expect(document.querySelector("video")!.muted).toBe(true);
    expect(screen.getByRole("button", { name: "Unmute" })).toBeTruthy();
  });

  it("hands the page's keys a way in: play, pause, mute, where the clip is", async () => {
    let controls: MediaPlayerControls | null = null;
    const { unmount } = render(<MediaPlayer {...CLIP} onControlsChange={(next) => (controls = next)} />);
    await settle();
    expect(controls).not.toBeNull();

    act(() => controls!.togglePlay());
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();

    const video = document.querySelector("video")!;
    video.currentTime = 7;
    expect(controls!.currentTime()).toBe(7);

    act(() => controls!.toggleMuted());
    await settle();
    expect(video.muted).toBe(false);

    // Nothing to zoom on a clip, and nothing thrown for asking.
    controls!.zoomIn();

    unmount();
    expect(controls).toBeNull();
  });
});

/**
 * **Fullscreen is the package's, and it takes two routes.**
 *
 * Where the element API exists the skin's CONTAINER goes fullscreen, so its
 * controls are painted inside it. Where it does not — an iPhone without one
 * — the `<video>` is handed to the phone's own player. The old in-app
 * fallback for a clip is gone: it was a box under Safari's bar.
 */
describe("maximize", () => {
  it("is not drawn where nothing can answer it", async () => {
    render(<MediaPlayer {...CLIP} />);
    await settle();

    expect(screen.queryByRole("button", { name: /fullscreen/i })).toBeNull();
  });

  it("fullscreens the skin's container where the API exists, and says so", async () => {
    stubElementFullscreen();
    let container: HTMLElement | null = null;
    const seen: boolean[] = [];
    render(
      <MediaPlayer
        {...CLIP}
        onContainerChange={(element) => (container = element)}
        onFullscreenChange={(on) => seen.push(on)}
      />,
    );
    await settle();
    expect(seen).toEqual([false]);

    fireEvent.click(screen.getByRole("button", { name: "Enter fullscreen" }));
    await settle();

    expect(Element.prototype.requestFullscreen).toHaveBeenCalledTimes(1);
    expect(document.fullscreenElement).toBe(container);
    expect(screen.getByRole("button", { name: "Exit fullscreen" })).toBeTruthy();
    expect(seen).toEqual([false, true]);

    fireEvent.click(screen.getByRole("button", { name: "Exit fullscreen" }));
    await settle();
    expect(seen).toEqual([false, true, false]);
  });

  it("hands the clip to the phone's own player where there is no element API", async () => {
    const restore = stubWebKitPresentation();
    try {
      render(<MediaPlayer {...CLIP} />);
      await settle();

      fireEvent.click(screen.getByRole("button", { name: "Enter fullscreen" }));
      await settle();

      const video = document.querySelector("video")!;
      const proto = HTMLVideoElement.prototype as unknown as {
        webkitSetPresentationMode: (mode: string) => void;
      };
      expect(proto.webkitSetPresentationMode).toHaveBeenCalledWith("fullscreen");
      expect((video as unknown as { webkitPresentationMode: string }).webkitPresentationMode).toBe(
        "fullscreen",
      );
      expect(screen.getByRole("button", { name: "Exit fullscreen" })).toBeTruthy();
    } finally {
      restore();
    }
  });

  it("reaches the same fullscreen from the page's key", async () => {
    stubElementFullscreen();
    let controls: MediaPlayerControls | null = null;
    render(<MediaPlayer {...CLIP} onControlsChange={(next) => (controls = next)} />);
    await settle();

    act(() => controls!.toggleFullscreen());
    await settle();
    expect(document.fullscreenElement).not.toBeNull();
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
