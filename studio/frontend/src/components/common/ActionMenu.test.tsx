import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ActionMenu, type MenuAction } from "./ActionMenu";
import { CopyIcon, TrashIcon } from "./icons";

const ACTIONS: readonly MenuAction[] = [
  { key: "copy", label: "Copy link", icon: <CopyIcon />, onSelect: vi.fn() },
  { key: "delete", label: "Delete", icon: <TrashIcon />, danger: true, onSelect: vi.fn() },
];

/** A box, the way `getBoundingClientRect` reports one. */
function rect(top: number, bottom: number, left = 600, right = 632): DOMRect {
  return {
    top,
    bottom,
    left,
    right,
    x: left,
    y: top,
    width: right - left,
    height: bottom - top,
    toJSON: () => ({}),
  };
}

/**
 * jsdom lays nothing out, so the boxes are handed to it: the trigger's
 * anchor, `<main>`, and the create sheet when one is on the page.
 */
function draw({
  anchor,
  sheet,
}: {
  anchor: DOMRect;
  sheet?: DOMRect;
}) {
  window.innerHeight = 768;
  render(
    <>
      {sheet && <div data-create-bar="" data-testid="sheet" />}
      <main data-testid="main">
        <ActionMenu label="a file" actions={ACTIONS} />
      </main>
    </>,
  );
  const trigger = screen.getAllByRole("button", { name: "Actions for a file" })[0]!;
  const main = screen.getByTestId("main");
  // The menu's own root — the box the placement measures — is `<main>`'s
  // one child; the trigger sits two wrappers down inside it.
  vi.spyOn(main.firstElementChild!, "getBoundingClientRect").mockReturnValue(anchor);
  vi.spyOn(main, "getBoundingClientRect").mockReturnValue(rect(0, 768, 64, 1280));
  if (sheet) {
    vi.spyOn(screen.getByTestId("sheet"), "getBoundingClientRect").mockReturnValue(sheet);
  }
  fireEvent.click(trigger);
  return screen.getByRole("menu");
}

afterEach(cleanup);

/**
 * The floor used to be the create sheet's top edge, from when the sheet was
 * docked at the foot of the column. It is a card at the head of the page
 * now, so its top was above every trigger and every menu opened upward —
 * over the tab strip, with the whole page free below it.
 */
it("opens downward under a sheet that sits above the trigger", () => {
  const menu = draw({ anchor: rect(300, 332), sheet: rect(80, 240) });
  expect(menu.className).not.toContain("bottom-full");
});

it("opens downward with the page free below and no sheet at all", () => {
  const menu = draw({ anchor: rect(300, 332) });
  expect(menu.className).not.toContain("bottom-full");
});

it("opens upward from a trigger at the foot of the viewport", () => {
  const menu = draw({ anchor: rect(700, 732) });
  expect(menu.className).toContain("bottom-full");
});

it("still opens upward when the sheet sits below the trigger, with no room between", () => {
  const menu = draw({ anchor: rect(168, 200), sheet: rect(240, 600) });
  expect(menu.className).toContain("bottom-full");
});
