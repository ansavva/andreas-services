import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  RAIL_WIDTH_DEFAULT,
  RAIL_WIDTH_MAX,
  RAIL_WIDTH_MIN,
  RAIL_WIDTH_STORAGE_KEY,
  ViewerRail,
} from "./ViewerRail";

function railWidth(): string {
  return screen.getByRole("complementary", { name: "Rail" }).style.getPropertyValue("--rail-w");
}

describe("ViewerRail", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(cleanup);

  it("opens at the default width and publishes it as a custom property", () => {
    render(<ViewerRail aria-label="Rail">body</ViewerRail>);
    expect(railWidth()).toBe(`${RAIL_WIDTH_DEFAULT}px`);
    const handle = screen.getByRole("separator", { name: "Resize panel" });
    expect(handle.getAttribute("aria-valuenow")).toBe(String(RAIL_WIDTH_DEFAULT));
  });

  it("follows the pointer from its own right edge, clamped, and remembers", () => {
    render(<ViewerRail aria-label="Rail">body</ViewerRail>);
    const aside = screen.getByRole("complementary", { name: "Rail" });
    aside.getBoundingClientRect = () =>
      ({ right: 1000, left: 640, top: 0, bottom: 0, width: 360, height: 0 }) as DOMRect;
    const handle = screen.getByRole("separator", { name: "Resize panel" });
    handle.setPointerCapture = () => undefined;
    handle.releasePointerCapture = () => undefined;

    fireEvent.pointerDown(handle, { button: 0, clientX: 640, pointerId: 1 });
    fireEvent.pointerMove(handle, { clientX: 500, pointerId: 1 });
    expect(railWidth()).toBe("500px");
    expect(window.localStorage.getItem(RAIL_WIDTH_STORAGE_KEY)).toBe("500");

    // Past the floor: the rail stops there.
    fireEvent.pointerMove(handle, { clientX: 950, pointerId: 1 });
    expect(railWidth()).toBe(`${RAIL_WIDTH_MIN}px`);
    fireEvent.pointerUp(handle, { pointerId: 1 });

    // Released: further movement changes nothing.
    fireEvent.pointerMove(handle, { clientX: 400, pointerId: 1 });
    expect(railWidth()).toBe(`${RAIL_WIDTH_MIN}px`);
  });

  it("starts from the remembered width", () => {
    window.localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, "480");
    render(<ViewerRail aria-label="Rail">body</ViewerRail>);
    expect(railWidth()).toBe("480px");
  });

  it("ignores a remembered width it cannot use", () => {
    window.localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, "wide");
    render(<ViewerRail aria-label="Rail">body</ViewerRail>);
    expect(railWidth()).toBe(`${RAIL_WIDTH_DEFAULT}px`);
  });

  it("nudges from the keyboard and resets on a double-click", () => {
    render(<ViewerRail aria-label="Rail">body</ViewerRail>);
    const handle = screen.getByRole("separator", { name: "Resize panel" });
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(railWidth()).toBe(`${RAIL_WIDTH_DEFAULT + 16}px`);
    fireEvent.keyDown(handle, { key: "ArrowRight" });
    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(railWidth()).toBe(`${RAIL_WIDTH_DEFAULT - 16}px`);
    // Home asks for the ceiling; jsdom's 1024px window is narrower than
    // the ceiling plus the room the stage keeps, so the window wins.
    fireEvent.keyDown(handle, { key: "Home" });
    expect(Number(handle.getAttribute("aria-valuenow"))).toBeLessThanOrEqual(RAIL_WIDTH_MAX);
    expect(Number(handle.getAttribute("aria-valuenow"))).toBe(window.innerWidth - 320);
    fireEvent.doubleClick(handle);
    expect(railWidth()).toBe(`${RAIL_WIDTH_DEFAULT}px`);
    // Back at the default, nothing is remembered.
    expect(window.localStorage.getItem(RAIL_WIDTH_STORAGE_KEY)).toBeNull();
  });
});
