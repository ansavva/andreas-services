import type { MouseEvent } from "react";
import type { NavigateFunction } from "react-router-dom";

import { isModifiedPress } from "../entity/EntityRow";

/**
 * The press handler every in-app `<a href>` needs.
 *
 * **A bare `<a href="/f/…">` is a full page load**, and the app it reloads is
 * a single-page one: the whole bundle re-runs, every query starts empty and
 * every picture on the screen is fetched again. Two controls had one — the
 * Folder button in a feed row and the Folder cell in an opened run — so the
 * one gesture that says "show me where this lives" was also the one gesture
 * that threw the session away.
 *
 * The href stays, because it is what makes the control a link at all:
 * middle-click, ⌘-click and Copy address are the browser's, and
 * `isModifiedPress` is what hands those back to it. Everything else is the
 * router's.
 */
export function pressInApp(navigate: NavigateFunction, to: string) {
  return (event: MouseEvent) => {
    if (isModifiedPress(event) || event.shiftKey) return;
    event.preventDefault();
    navigate(to);
  };
}
