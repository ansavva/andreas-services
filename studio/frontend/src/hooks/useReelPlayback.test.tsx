import { act, render } from "@testing-library/react";
import { beforeAll, expect, it, vi } from "vitest";

import { useReelPlayback } from "./useReelPlayback";

/**
 * The map this hook keeps IS a pane's identity for playback. Two panes sharing
 * one string means one of them silently loses its element — which is what a
 * scene board did, because every Kling run names its output `video.mp4` and the
 * reel was registering on the file name.
 */

beforeAll(() => {
  // jsdom implements no media pipeline: `play()` returns undefined where a
  // browser returns a promise, and the hook chains `.catch` off it.
  Object.defineProperty(HTMLMediaElement.prototype, "play", {
    configurable: true,
    value: () => Promise.resolve(),
  });
});

function Harness({ keys, current }: { keys: string[]; current: string }) {
  const playback = useReelPlayback(current);
  return (
    <>
      {keys.map((key) => (
        <video key={key} data-testid={key} ref={playback.register(key)} />
      ))}
    </>
  );
}

it("keeps one element per distinct key", () => {
  const { getByTestId } = render(<Harness keys={["a", "b"]} current="a" />);
  // Distinct keys: both elements are real and different.
  expect(getByTestId("a")).not.toBe(getByTestId("b"));
});

it("hands the same registrar back for a repeated key", () => {
  // The memoisation this hook documents: a fresh arrow per render would detach
  // and re-attach every pane's ref on every tick of the scrub bar.
  const seen: Array<(el: HTMLVideoElement | null) => void> = [];
  function Probe() {
    const playback = useReelPlayback("a");
    seen.push(playback.register("a"));
    return null;
  }
  const { rerender } = render(<Probe />);
  rerender(<Probe />);
  expect(seen[0]).toBe(seen[1]);
});

it("collapses two panes that share a key onto one element", () => {
  // The failure, asserted directly. Both panes register under "video.mp4"; the
  // map can only hold one, so the pane on screen and the element the hook would
  // play are not the same object. This is why the reel must be given ids.
  const registrar = vi.fn();
  function Probe() {
    const playback = useReelPlayback("video.mp4");
    // The same string from two panes returns the SAME callback, so whichever
    // element mounts last wins the slot.
    registrar(playback.register("video.mp4") === playback.register("video.mp4"));
    return null;
  }
  act(() => {
    render(<Probe />);
  });
  expect(registrar).toHaveBeenCalledWith(true);
});
