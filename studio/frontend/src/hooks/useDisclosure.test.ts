import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useDisclosure } from "./useDisclosure";

function escape() {
  act(() => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  });
}

describe("a disclosed panel", () => {
  it("opens on the control that owns it and closes on the same one", () => {
    const { result } = renderHook(() => useDisclosure());

    act(() => result.current.toggle("node-1"));
    expect(result.current.isOpen("node-1")).toBe(true);

    act(() => result.current.toggle("node-1"));
    expect(result.current.isOpen("node-1")).toBe(false);
  });

  it("holds one at a time, so a second control takes the panel over", () => {
    // A panel left open beside the one just asked for would be a form pointing
    // at an item nobody is looking at any more.
    const { result } = renderHook(() => useDisclosure());

    act(() => result.current.toggle("node-1"));
    act(() => result.current.toggle("node-2"));

    expect(result.current.isOpen("node-1")).toBe(false);
    expect(result.current.isOpen("node-2")).toBe(true);
  });

  it("closes on Escape", () => {
    const { result } = renderHook(() => useDisclosure());
    act(() => result.current.toggle("node-1"));

    escape();

    expect(result.current.open).toBeNull();
  });

  it("declines Escape while the form has something in it", () => {
    // The whole reason the guard exists: a panel carrying typed words that
    // vanishes on a stray keypress loses them, and there is no undo.
    let dirty = true;
    const { result } = renderHook(() => useDisclosure(() => !dirty));
    act(() => result.current.toggle("node-1"));

    escape();
    expect(result.current.isOpen("node-1")).toBe(true);

    dirty = false;
    escape();
    expect(result.current.open).toBeNull();
  });

  it("listens for Escape only while something is open", () => {
    // Nothing open is the state this page spends most of its life in.
    const { result } = renderHook(() => useDisclosure());

    escape();

    expect(result.current.open).toBeNull();
  });
});
