import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MediaPlayback } from "../../hooks/useMediaPlayback";
import { PlayerTransport } from "./PlayerTransport";

afterEach(cleanup);

function playback(overrides: Partial<MediaPlayback> = {}): MediaPlayback {
  return {
    muted: true,
    blocked: false,
    paused: true,
    time: 0,
    duration: 0,
    register: () => () => undefined,
    toggleMuted: vi.fn(),
    togglePaused: vi.fn(),
    seekTo: vi.fn(),
    seekBy: vi.fn(),
    ...overrides,
  };
}

function seek() {
  return screen.getByRole("slider", { name: "Seek" });
}

describe("the seek bar", () => {
  it("is disabled until the metadata says how long the clip is", () => {
    render(<PlayerTransport playback={playback()} />);

    // Not hidden: the bar appears in its final position rather than popping
    // into existence when the duration lands.
    expect((seek() as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("—:—")).toBeTruthy();
  });

  it("paints on movement and seeks only on release", () => {
    const seekTo = vi.fn();
    render(<PlayerTransport playback={playback({ duration: 60, time: 10, seekTo })} />);

    fireEvent.change(seek(), { target: { value: "42" } });
    // The decoder is not asked for a frame per pointer move — the thumb has
    // moved, the clip has not.
    expect(seekTo).not.toHaveBeenCalled();
    expect((seek() as HTMLInputElement).value).toBe("42");

    fireEvent.pointerUp(seek());
    expect(seekTo).toHaveBeenCalledWith(42);
  });

  it("announces where it is in words, not just as a number", () => {
    render(<PlayerTransport playback={playback({ duration: 90, time: 30 })} />);

    expect(seek().getAttribute("aria-valuetext")).toBe("0:30 of 1:30");
  });

  it("paints the buffered position where the caller tracks it", () => {
    render(<PlayerTransport playback={playback({ duration: 100, time: 10 })} buffered={40} />);

    // The gradient itself is one opaque string; `data-buffered` is the only
    // observable difference between a buffered bar and an unbuffered one.
    expect(seek().getAttribute("data-buffered")).toBe("40");
  });
});

describe("the skip buttons", () => {
  it("move five seconds each way", () => {
    const seekBy = vi.fn();
    render(<PlayerTransport playback={playback({ duration: 60, seekBy })} />);

    fireEvent.click(screen.getByRole("button", { name: "Back 5 seconds" }));
    fireEvent.click(screen.getByRole("button", { name: "Forward 5 seconds" }));

    expect(seekBy.mock.calls).toEqual([[-5], [5]]);
  });

  it("names play and pause by what the press will do", () => {
    const { rerender } = render(<PlayerTransport playback={playback({ paused: true })} />);
    expect(screen.getByRole("button", { name: "Play (space)" })).toBeTruthy();

    rerender(<PlayerTransport playback={playback({ paused: false })} />);
    expect(screen.getByRole("button", { name: "Pause (space)" })).toBeTruthy();
  });
});
