import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FIT, useZoom } from "./useZoom";

/**
 * A 1000×800 box holding a 600×1200 picture — portrait in a landscape box, so
 * `object-contain` fits it by height: 400×800 at the fit, centred with 300px
 * of black either side. Every clamp figure below is derived from those.
 */
function stage() {
  const container = document.createElement("div");
  Object.defineProperty(container, "clientWidth", { value: 1000 });
  Object.defineProperty(container, "clientHeight", { value: 800 });
  container.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 1000, height: 800, right: 1000, bottom: 800, x: 0, y: 0, toJSON() {} }) as DOMRect;
  const img = document.createElement("img");
  Object.defineProperty(img, "naturalWidth", { value: 600 });
  Object.defineProperty(img, "naturalHeight", { value: 1200 });
  document.body.appendChild(container);
  return { container: { current: container }, media: { current: img } };
}

function mount(over: Partial<Parameters<typeof useZoom>[0]> = {}) {
  const refs = stage();
  const hook = renderHook((props: Partial<Parameters<typeof useZoom>[0]>) =>
    useZoom({ ...refs, enabled: true, ...over, ...props }),
  );
  return { ...hook, ...refs };
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("the fit and the steps", () => {
  it("starts at the fit, steps in by half and out by the same, and never past the fit", () => {
    const { result } = mount();
    expect(result.current.zoom).toEqual(FIT);
    expect(result.current.zoomed).toBe(false);
    expect(result.current.canZoomOut).toBe(false);

    act(() => result.current.zoomIn());
    expect(result.current.zoom).toEqual({ scale: 1.5, x: 0, y: 0 });
    expect(result.current.zoomed).toBe(true);
    expect(result.current.style.transform).toBe("translate(0px, 0px) scale(1.5)");

    act(() => result.current.zoomOut());
    expect(result.current.zoom).toEqual(FIT);
    // The transform goes with it: nothing is drawn differently at the fit.
    expect(result.current.style.transform).toBeUndefined();

    act(() => result.current.zoomOut());
    expect(result.current.zoom).toEqual(FIT);
  });

  it("stops at eight times", () => {
    const { result } = mount();
    for (let i = 0; i < 10; i += 1) act(() => result.current.zoomIn());
    expect(result.current.zoom.scale).toBe(8);
    expect(result.current.canZoomIn).toBe(false);
  });

  it("resets to the fit, and resets when the picture changes", () => {
    const { result, rerender } = mount({ resetKey: "node-a" });
    act(() => result.current.zoomIn());
    act(() => result.current.reset());
    expect(result.current.zoom).toEqual(FIT);

    act(() => result.current.zoomIn());
    rerender({ resetKey: "node-b" });
    expect(result.current.zoom).toEqual(FIT);
  });
});

describe("the pan", () => {
  it("is clamped to the picture's edge, and centred on an axis the picture does not fill", () => {
    const { result, container } = mount();
    // ×2.25: the picture is 900×1800 in a 1000×800 box. It does not fill the
    // width, so x stays 0; it overflows the height by 1000, so y reaches ±500.
    act(() => result.current.zoomIn());
    act(() => result.current.zoomIn());
    expect(result.current.zoom.scale).toBe(2.25);

    act(() => {
      result.current.handlers.onPointerDown?.(
        pointer(container.current, { pointerId: 1, clientX: 500, clientY: 400 }),
      );
      result.current.handlers.onPointerMove?.(
        pointer(container.current, { pointerId: 1, clientX: 900, clientY: 2400 }),
      );
    });
    // 400×2.25 = 900 wide: 0 either side. 800×2.25 = 1800 tall: (1800−800)/2.
    expect(result.current.zoom.x).toBe(0);
    expect(result.current.zoom.y).toBe(500);
  });

  it("does nothing at the fit — a press on a picture nobody has zoomed is a click", () => {
    const { result, container } = mount();
    act(() => {
      result.current.handlers.onPointerDown?.(
        pointer(container.current, { pointerId: 1, clientX: 500, clientY: 400 }),
      );
      result.current.handlers.onPointerMove?.(
        pointer(container.current, { pointerId: 1, clientX: 600, clientY: 500 }),
      );
    });
    expect(result.current.zoom).toEqual(FIT);
  });
});

describe("zooming about a point", () => {
  it("keeps the picture point under a double-click where it was", () => {
    const { result, container } = mount();
    // Double-click at the box's right-hand quarter, 250px right of the middle.
    act(() =>
      result.current.handlers.onDoubleClick?.({
        clientX: 750,
        clientY: 400,
        currentTarget: container.current,
      } as never),
    );
    // Going in ×2.5 about p=250: t' = p − k·(p − t) = 250 − 2.5·250 = −375,
    // then clamped to the picture's edge, (400×2.5 − 1000)/2 = 0 — the picture
    // at ×2.5 is exactly the box's width, so x is 0 either way; y is untouched.
    expect(result.current.zoom.scale).toBe(2.5);
    expect(result.current.zoom.x).toBeCloseTo(0);
    expect(result.current.zoom.y).toBeCloseTo(0);

    // And back out from anywhere.
    act(() =>
      result.current.handlers.onDoubleClick?.({
        clientX: 10,
        clientY: 10,
        currentTarget: container.current,
      } as never),
    );
    expect(result.current.zoom).toEqual(FIT);
  });

  it("a pinch on a trackpad zooms about the pointer, and a plain wheel at the fit is the page's below md", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    const { result, container } = mount();

    const plain = new WheelEvent("wheel", { deltaY: -100, cancelable: true, clientX: 500, clientY: 400 });
    act(() => void container.current.dispatchEvent(plain));
    expect(result.current.zoom).toEqual(FIT);
    expect(plain.defaultPrevented).toBe(false);

    const pinch = new WheelEvent("wheel", {
      deltaY: -100,
      ctrlKey: true,
      cancelable: true,
      clientX: 500,
      clientY: 400,
    });
    act(() => void container.current.dispatchEvent(pinch));
    expect(result.current.zoom.scale).toBeGreaterThan(1);
    // Prevented, or the browser zooms the whole page under the picture.
    expect(pinch.defaultPrevented).toBe(true);

    // Zoomed now, so a plain wheel is the picture's.
    const more = new WheelEvent("wheel", { deltaY: -100, cancelable: true, clientX: 500, clientY: 400 });
    const before = result.current.zoom.scale;
    act(() => void container.current.dispatchEvent(more));
    expect(result.current.zoom.scale).toBeGreaterThan(before);
    expect(more.defaultPrevented).toBe(true);
  });

  it("a plain wheel zooms from md, where the viewer does not scroll", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    const { result, container } = mount();
    const plain = new WheelEvent("wheel", { deltaY: -100, cancelable: true, clientX: 500, clientY: 400 });
    act(() => void container.current.dispatchEvent(plain));
    expect(result.current.zoom.scale).toBeGreaterThan(1);
  });
});

describe("controlled", () => {
  it("reports through onChange and draws the value it is given", () => {
    const onChange = vi.fn();
    const { result } = mount({ value: FIT, onChange });
    act(() => result.current.zoomIn());
    expect(onChange).toHaveBeenCalledWith({ scale: 1.5, x: 0, y: 0 });
    // Still the fit until the owner hands the new value back.
    expect(result.current.zoom).toEqual(FIT);
  });
});

describe("disabled", () => {
  it("hands out no handlers, no cursor and no touch-action", () => {
    const { result } = mount({ enabled: false });
    expect(result.current.handlers).toEqual({});
    expect(result.current.stage).toEqual({ touchAction: undefined, cursor: undefined });
    expect(result.current.canZoomIn).toBe(false);
  });
});

/** A pointer event the handlers accept, with capture stubbed for jsdom. */
function pointer(
  target: HTMLElement,
  init: { pointerId: number; clientX: number; clientY: number },
) {
  target.setPointerCapture ??= () => undefined;
  target.releasePointerCapture ??= () => undefined;
  target.hasPointerCapture ??= () => false;
  return {
    ...init,
    pointerType: "touch",
    button: 0,
    target,
    currentTarget: target,
  } as never;
}
