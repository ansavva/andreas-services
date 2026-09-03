import { act, renderHook } from "@testing-library/react";
import type { KeyboardEvent } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ARMED_MS, useArmed } from "./useArmed";

function escape() {
  return { key: "Escape", stopPropagation: vi.fn() } as unknown as KeyboardEvent & {
    stopPropagation: ReturnType<typeof vi.fn>;
  };
}

describe("an armed control", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("arms on the first press and fires on the second, once", async () => {
    const onFire = vi.fn(() => Promise.resolve());
    const { result } = renderHook(() => useArmed({ onFire }));

    act(() => result.current.press());
    expect(result.current.armed).toBe(true);
    expect(onFire).not.toHaveBeenCalled();

    await act(async () => result.current.press());
    expect(onFire).toHaveBeenCalledOnce();
    expect(result.current.phase).toBe("idle");
  });

  it("expires, so a half-press left on screen is never still live", () => {
    /**
     * The arming is not a formality. A control armed and walked away from has
     * to be at rest when the next person reaches it.
     */
    const { result } = renderHook(() => useArmed({ onFire: () => Promise.resolve() }));

    act(() => result.current.arm());
    act(() => vi.advanceTimersByTime(ARMED_MS - 1));
    expect(result.current.armed).toBe(true);

    act(() => vi.advanceTimersByTime(1));
    expect(result.current.armed).toBe(false);
  });

  it("disarms when focus leaves", () => {
    const { result } = renderHook(() => useArmed({ onFire: () => Promise.resolve() }));

    act(() => result.current.arm());
    act(() => result.current.handlers.onBlur());

    expect(result.current.armed).toBe(false);
  });

  it("takes Escape only while armed, so the overlay around it keeps its own", () => {
    const { result } = renderHook(() => useArmed({ onFire: () => Promise.resolve() }));

    const idle = escape();
    act(() => result.current.handlers.onKeyDown(idle));
    expect(idle.stopPropagation).not.toHaveBeenCalled();

    act(() => result.current.arm());
    const armed = escape();
    act(() => result.current.handlers.onKeyDown(armed));
    expect(armed.stopPropagation).toHaveBeenCalledOnce();
    expect(result.current.armed).toBe(false);
  });

  it("hands a rejection to onError and returns to rest", async () => {
    const problem = new Error("refused");
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useArmed({ onFire: () => Promise.reject(problem), onError }),
    );

    act(() => result.current.arm());
    await act(async () => result.current.fire());

    expect(onError).toHaveBeenCalledWith(problem);
    expect(result.current.phase).toBe("idle");
  });

  it("ignores presses while busy, so a slow delete cannot be sent twice", async () => {
    let settle: () => void = () => undefined;
    const onFire = vi.fn(() => new Promise<void>((resolve) => (settle = resolve)));
    const { result } = renderHook(() => useArmed({ onFire }));

    act(() => result.current.press());
    act(() => result.current.press());
    expect(result.current.busy).toBe(true);

    act(() => result.current.press());
    act(() => result.current.arm());
    expect(onFire).toHaveBeenCalledOnce();
    expect(result.current.busy).toBe(true);

    await act(async () => settle());
    expect(result.current.phase).toBe("idle");
  });
});
