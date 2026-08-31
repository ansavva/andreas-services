import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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

describe("maximize is absent where it cannot work", () => {
  it("renders no fullscreen button when the API is unavailable", () => {
    render(<MediaPlayer {...CLIP} />);
    fireEvent.click(play());

    // iOS Safari refuses `requestFullscreen` on anything but a <video>. The
    // correct outcome is a control that was never offered, not one that fails.
    expect(screen.queryByRole("button", { name: /fullscreen/i })).toBeNull();
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
