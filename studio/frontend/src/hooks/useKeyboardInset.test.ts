import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useKeyboardInset } from "./useKeyboardInset";

/**
 * jsdom has no `visualViewport`; a stand-in with the three fields the hook
 * reads and the two events it listens to is enough to say what it computes.
 */
class FakeViewport extends EventTarget {
  offsetTop = 0;
  height = 800;
}

function install(viewport: FakeViewport | undefined) {
  Object.defineProperty(window, "visualViewport", { value: viewport, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: 800, configurable: true });
}

afterEach(() => install(undefined));

describe("useKeyboardInset", () => {
  it("is zero without a visual viewport, and zero while nothing covers the foot", () => {
    install(undefined);
    expect(renderHook(() => useKeyboardInset()).result.current).toBe(0);

    install(new FakeViewport());
    expect(renderHook(() => useKeyboardInset()).result.current).toBe(0);
  });

  it("is the strip between the visual viewport's foot and the window's", () => {
    const viewport = new FakeViewport();
    install(viewport);
    const { result } = renderHook(() => useKeyboardInset());

    // The keyboard takes 300px: the visual viewport is 500 tall at the top.
    viewport.height = 500;
    act(() => void viewport.dispatchEvent(new Event("resize")));
    expect(result.current).toBe(300);

    // Then the page scrolls under it by 100: the visual viewport moves down
    // within the layout one, and 200 of the foot is still covered.
    viewport.offsetTop = 100;
    act(() => void viewport.dispatchEvent(new Event("scroll")));
    expect(result.current).toBe(200);

    // Keyboard down.
    viewport.height = 800;
    viewport.offsetTop = 0;
    act(() => void viewport.dispatchEvent(new Event("resize")));
    expect(result.current).toBe(0);
  });
});
