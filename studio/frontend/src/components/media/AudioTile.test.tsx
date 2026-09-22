import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AudioTile } from "./AudioTile";

vi.mock("../../apis/studio", () => ({ getAsset: vi.fn() }));

/**
 * jsdom implements no media playback at all — `play()` throws "Not
 * implemented" — so both sides are stubbed to flip `paused` and fire the
 * events a real element would. What is under test is the tile's decisions,
 * not the browser's decoder.
 */
beforeEach(() => {
  const media = window.HTMLMediaElement.prototype;
  vi.spyOn(media, "play").mockImplementation(function (this: HTMLMediaElement) {
    Object.defineProperty(this, "paused", { value: false, configurable: true });
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  });
  vi.spyOn(media, "pause").mockImplementation(function (this: HTMLMediaElement) {
    Object.defineProperty(this, "paused", { value: true, configurable: true });
    this.dispatchEvent(new Event("pause"));
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const tile = (node: string, name: string) => (
  <AudioTile nodeId={node} url={`https://example.invalid/${name}`} name={name} />
);

describe("a voice sample as a tile", () => {
  it("plays on a press and stops on the next one", () => {
    render(tile("node-1", "take.mp3"));

    fireEvent.click(screen.getByLabelText("Play take.mp3"));
    const pause = screen.getByLabelText("Pause take.mp3");

    fireEvent.click(pause);
    expect(screen.getByLabelText("Play take.mp3")).toBeTruthy();
  });

  it("stops whatever else was playing — two samples at once is noise", () => {
    render(
      <>
        {tile("node-1", "first.mp3")}
        {tile("node-2", "second.mp3")}
      </>,
    );

    fireEvent.click(screen.getByLabelText("Play first.mp3"));
    fireEvent.click(screen.getByLabelText("Play second.mp3"));

    expect(screen.getByLabelText("Play first.mp3")).toBeTruthy();
    expect(screen.getByLabelText("Pause second.mp3")).toBeTruthy();
  });

  it("does not let a press on the play button reach the control around it", () => {
    /**
     * The tile sits inside the picker's own button. Without this, listening to
     * a sample would attach it — the one gesture that must not be the same
     * gesture.
     */
    const outer = vi.fn();
    render(
      <button type="button" onClick={outer}>
        {tile("node-1", "take.mp3")}
      </button>,
    );

    fireEvent.click(screen.getByLabelText("Play take.mp3"));
    expect(outer).not.toHaveBeenCalled();
  });

  it("drags its node to the create sheet like every other tile", () => {
    render(tile("node-1", "take.mp3"));
    const box = screen.getByLabelText("Play take.mp3").closest("[data-audio-tile]")!;
    const data = new Map<string, string>();
    fireEvent.dragStart(box, {
      dataTransfer: { setData: (type: string, value: string) => data.set(type, value), types: [] },
    });
    expect(JSON.parse(data.get("application/x-studio-node")!)).toEqual({
      node: "node-1",
      url: "https://example.invalid/take.mp3",
      name: "take.mp3",
      kind: "object",
    });
  });

  it("says Unavailable rather than drawing a dead control", () => {
    render(<AudioTile nodeId="node-1" url={null} name="gone.mp3" />);
    expect(screen.getByText("Unavailable")).toBeTruthy();
  });
});
