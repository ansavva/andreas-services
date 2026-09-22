import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { DOUBLE_TAP_MS, useTaps } from "./useTaps";

function Surface({ onTap, onDoubleTap }: { onTap: () => void; onDoubleTap: () => void }) {
  const taps = useTaps({ onTap, onDoubleTap });
  return <div data-testid="surface" {...taps} />;
}

afterEach(cleanup);
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

/** A press at (x, y) whose `pointerup` reports 0,0 — what an iPhone sends. */
function tap(target: HTMLElement, x = 100, y = 200) {
  fireEvent.pointerDown(target, { pointerId: 1, isPrimary: true, clientX: x, clientY: y });
  fireEvent.pointerUp(target, { pointerId: 1, isPrimary: true, clientX: 0, clientY: 0 });
}

it("reports one tap only after a second one has had its chance", () => {
  const onTap = vi.fn();
  const onDoubleTap = vi.fn();
  render(<Surface onTap={onTap} onDoubleTap={onDoubleTap} />);
  const surface = screen.getByTestId("surface");

  tap(surface);
  expect(onTap).not.toHaveBeenCalled();
  vi.advanceTimersByTime(DOUBLE_TAP_MS + 1);
  expect(onTap).toHaveBeenCalledTimes(1);
  expect(onDoubleTap).not.toHaveBeenCalled();
});

it("two taps inside the window are one double tap at the first finger-down", () => {
  const onTap = vi.fn();
  const onDoubleTap = vi.fn();
  render(<Surface onTap={onTap} onDoubleTap={onDoubleTap} />);
  const surface = screen.getByTestId("surface");

  tap(surface, 40, 60);
  vi.advanceTimersByTime(DOUBLE_TAP_MS - 50);
  tap(surface, 44, 63);
  vi.advanceTimersByTime(DOUBLE_TAP_MS * 2);

  expect(onDoubleTap).toHaveBeenCalledWith({ x: 40, y: 60 });
  expect(onTap).not.toHaveBeenCalled();
});

it("a swipe is neither", () => {
  const onTap = vi.fn();
  const onDoubleTap = vi.fn();
  render(<Surface onTap={onTap} onDoubleTap={onDoubleTap} />);
  const surface = screen.getByTestId("surface");

  fireEvent.pointerDown(surface, { pointerId: 1, isPrimary: true, clientX: 100, clientY: 400 });
  fireEvent.pointerMove(surface, { pointerId: 1, clientX: 100, clientY: 370 });
  fireEvent.pointerMove(surface, { pointerId: 1, clientX: 100, clientY: 340 });
  fireEvent.pointerUp(surface, { pointerId: 1, isPrimary: true, clientX: 0, clientY: 0 });
  vi.advanceTimersByTime(DOUBLE_TAP_MS * 2);

  expect(onTap).not.toHaveBeenCalled();
  expect(onDoubleTap).not.toHaveBeenCalled();
});
