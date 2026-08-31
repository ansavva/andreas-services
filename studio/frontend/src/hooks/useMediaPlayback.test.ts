import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useMediaPlayback } from "./useMediaPlayback";

/**
 * The three bugs this hook's header documents, pinned.
 *
 * It shipped with none of its own tests and Phase B moved the file, so these
 * exist to make the move provable rather than to raise a coverage number. Each
 * case below is one of the numbered failures in `useMediaPlayback.ts`:
 *
 * 1. the mute is set on the ELEMENT, synchronously, inside the click;
 * 2. a `NotAllowedError` is not swallowed — playback falls back to muted and
 *    `blocked` is raised;
 * 3. `volume === 0` is corrected, because unmuting a zero-volume element is
 *    still silence.
 *
 * A hand-built stub rather than a real `<video>`: jsdom's `HTMLMediaElement`
 * implements neither `play` nor `pause`, so a real element could only be tested
 * by monkeypatching the same two methods this object already is.
 */
interface FakeVideo extends HTMLVideoElement {
  playCalls: { muted: boolean; volume: number }[];
}

function fakeVideo(
  play: (video: FakeVideo) => Promise<void> = () => Promise.resolve(),
): FakeVideo {
  const video = {
    muted: true,
    volume: 1,
    paused: true,
    currentTime: 0,
    duration: 12,
    playCalls: [] as { muted: boolean; volume: number }[],
    pause: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  } as unknown as FakeVideo;

  video.play = vi.fn(() => {
    // Recorded at the moment of the call, which is the only way to assert that
    // the element was already in the right state when playback was asked for.
    video.playCalls.push({ muted: video.muted, volume: video.volume });
    return play(video);
  });

  return video;
}

/** A hook with one registered element, current, ready to be toggled. */
function mounted(video: FakeVideo) {
  const hook = renderHook(() => useMediaPlayback("node-1"));
  act(() => {
    hook.result.current.register("node-1")(video);
  });
  return hook;
}

function refuse(name: string) {
  return (video: FakeVideo) => {
    if (!video.muted) return Promise.reject(new DOMException("refused", name));
    return Promise.resolve();
  };
}

describe("the mute toggle happens inside the gesture", () => {
  it("sets `muted` on the element before React has re-rendered", () => {
    const video = fakeVideo();
    const { result } = mounted(video);

    // Deliberately NOT wrapped in `act`: the assertion is that the element was
    // already unmuted before any effect or re-render could run. An
    // implementation that set `video.muted` from an effect — the bug — leaves it
    // `true` here and passes only after the flush below.
    result.current.toggleMuted();
    expect(video.muted).toBe(false);
  });

  it("asks for playback with the element already in the state it wants", () => {
    const video = fakeVideo();
    const { result } = mounted(video);

    act(() => {
      result.current.toggleMuted();
    });

    expect(video.playCalls).toEqual([{ muted: false, volume: 1 }]);
    // React state follows to DESCRIBE what happened; it did not cause it.
    expect(result.current.muted).toBe(false);
  });

  it("corrects a zero volume, which unmuting alone leaves silent", () => {
    const video = fakeVideo();
    video.volume = 0;
    const { result } = mounted(video);

    act(() => {
      result.current.toggleMuted();
    });

    expect(video.volume).toBe(1);
    expect(video.playCalls[0]).toEqual({ muted: false, volume: 1 });
  });

  it("leaves the volume alone on the way back to muted", () => {
    const video = fakeVideo();
    const { result } = mounted(video);

    act(() => {
      result.current.toggleMuted();
    });
    video.volume = 0.3;
    act(() => {
      result.current.toggleMuted();
    });

    expect(video.volume).toBe(0.3);
  });
});

describe("a refusal is reported rather than swallowed", () => {
  it("falls back to muted playback and raises `blocked`", async () => {
    const video = fakeVideo(refuse("NotAllowedError"));
    const { result } = mounted(video);

    await act(async () => {
      result.current.toggleMuted();
    });

    // Silent beats stopped: the second call is the retry, muted.
    expect(video.playCalls).toEqual([
      { muted: false, volume: 1 },
      { muted: true, volume: 1 },
    ]);
    expect(video.muted).toBe(true);
    expect(result.current.muted).toBe(true);
    expect(result.current.blocked).toBe(true);
  });

  it("clears `blocked` on the next press, so the button stops accusing", async () => {
    const video = fakeVideo(refuse("NotAllowedError"));
    const { result } = mounted(video);

    await act(async () => {
      result.current.toggleMuted();
    });
    expect(result.current.blocked).toBe(true);

    video.play = vi.fn(() => Promise.resolve());
    await act(async () => {
      result.current.toggleMuted();
    });

    expect(result.current.blocked).toBe(false);
  });

  it("says nothing about an AbortError, which is the ordinary case", async () => {
    // A `play()` interrupted by the next `pause()`. It means nothing at all, and
    // treating it as a refusal would put a sound warning on screen for a scroll.
    const video = fakeVideo(refuse("AbortError"));
    const { result } = mounted(video);

    await act(async () => {
      result.current.toggleMuted();
    });

    expect(result.current.blocked).toBe(false);
    expect(result.current.muted).toBe(false);
    expect(video.playCalls).toHaveLength(1);
  });
});

describe("seeking", () => {
  it("clamps into the clip rather than past either end", () => {
    const video = fakeVideo();
    const { result } = mounted(video);

    act(() => {
      result.current.seekTo(-5);
    });
    expect(video.currentTime).toBe(0);

    act(() => {
      result.current.seekTo(99);
    });
    expect(video.currentTime).toBe(12);
  });

  it("does nothing at all when the duration has not landed", () => {
    const video = fakeVideo();
    (video as { duration: number }).duration = Number.NaN;
    const { result } = mounted(video);

    act(() => {
      result.current.seekBy(5);
    });

    expect(video.currentTime).toBe(0);
  });
});
