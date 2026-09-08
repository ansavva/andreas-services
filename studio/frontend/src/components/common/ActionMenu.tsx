import { useCallback, useRef, useState, type ReactElement, type ReactNode } from "react";

import { Drawer, Dropdown, Text, iconButtonClass } from "@ansavva/design-system";

import { useArmed } from "../../hooks/useArmed";
import { DotsIcon, DotsVerticalIcon } from "./icons";
import { SheetHandle } from "./SheetHandle";

/**
 * Roughly how big the panel is, in pixels — what "is there room" is asked
 * against on each axis.
 *
 * Estimated rather than measured, because the panel does not exist to be
 * measured until it is open and the placement has to be decided before that.
 * The height is per menu (a line plus the panel's own padding), so a menu of
 * three lines is not sent upward on a screen that had room for it; the width
 * is one number because every one of these panels is the same width.
 */
const PANEL_LINE = 36;
const PANEL_PAD = 16;
const PANEL_W = 208;

/** One line of the menu: a glyph, a word, and what pressing it does. */
export interface MenuAction {
  /** Stable across renders — React's key. */
  key: string;
  /** The word, or the live one an item like Copy keeps changing. */
  label: ReactNode;
  icon: ReactElement;
  onSelect: () => void | Promise<unknown>;
  /** Red, because it destroys something. Says nothing about how it is confirmed. */
  danger?: boolean;
  /**
   * Arms instead of firing: the line restates what it will destroy, and the
   * second press does it. At most one per menu.
   *
   * **Separate from `danger`, because the confirmation is not always here.** A
   * page's Delete is red and opens a `ConfirmDestroyDialog` that makes you type
   * the name — arming in the menu as well would be two confirmations for one
   * decision. A row's or a tile's Delete has no dialog, so the menu is where
   * the second press has to live.
   *
   * Give `armedLabel` when the restatement is not just the label — "Confirm —
   * delete this folder" for a line that reads "Delete folder".
   */
  arm?: boolean;
  armedLabel?: string;
  /**
   * Leaves the menu open, for the one item whose entire feedback is its own
   * label changing — Copy, which says "Copied" where it stands.
   */
  keepOpen?: boolean;
  /** Drawn, and refused, with the reason as its title. */
  disabled?: boolean;
  reason?: string;
  /** On the line itself — the one use is `sm:hidden`, for an item a wider toolbar draws as a button. */
  className?: string;
}

/**
 * Every menu in this app: a trigger, and a list of things that can be done.
 *
 * **One component, because there were four and they disagreed.** The page bar's
 * `⋯`, a folder toolbar's, a file row's and a tile's were each a hand-written
 * `Dropdown` with its own arming, its own alignment fix, its own copy-keeps-it-
 * open trick — and, visibly, its own idea of whether a line carries a glyph.
 * They also each inherited the same two placement faults: a panel that opens
 * under the app's sidebar from the left column, and one that opens *behind* the
 * create sheet, which is `z-30` where a `Dropdown` is `z-20`. That was reported
 * as "the files menu is hidden behind the create section", and it was true of
 * every menu on a screen with the sheet on it.
 *
 * **A dropdown on a pointer, a bottom sheet below `md`** — the pair the create
 * sheet's gear already is. A menu anchored to a control in the last column of a
 * grid, or at the right edge of a toolbar, opens off the side of a phone; a
 * sheet at the foot of the screen is where a thumb is anyway.
 *
 * **The placement is measured when the menu opens**, against the surfaces that
 * actually clip it rather than against the window: `<main>` on the horizontal
 * axis, because the sidebar is inside the window and paints over anything under
 * it, and the create sheet's top edge on the vertical, because it floats over
 * the foot of the column. Measured on the press rather than tracked — a trigger
 * does not move while its own menu is open, and a listener per menu is sixty of
 * them on a grid of sixty tiles.
 */
export function ActionMenu({
  label,
  actions,
  triggerLabel = `Actions for ${label}`,
  overlay = false,
  vertical = false,
  className = "",
  onOpenChange,
}: {
  /** What the menu is about — the sheet's title, and the trigger's name by default. */
  label: string;
  actions: readonly MenuAction[];
  /** When the name is about the page rather than about a thing: "More actions". */
  triggerLabel?: string;
  /** A glyph over a picture, rather than a control in a row. */
  overlay?: boolean;
  /** `⋮` rather than `⋯` — upright over a picture, flat in a row of text. */
  vertical?: boolean;
  /** Where the trigger sits. */
  className?: string;
  /** Told when the menu opens or closes. */
  onOpenChange?: (open: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const sheet = useRef<HTMLDivElement>(null);
  const anchor = useRef<HTMLDivElement>(null);

  /** Which way the panel opens, decided when it is opened. See the docblock. */
  const [upward, setUpward] = useState(false);
  const [leftward, setLeftward] = useState(true);

  /** The arming line's second press. */
  const arming = actions.find((action) => action.arm);
  const armed = useArmed({
    onFire: async () => {
      try {
        await arming?.onSelect();
      } finally {
        setOpen(false);
        setSheetOpen(false);
      }
    },
  });

  const close = useCallback(() => {
    // A half-pressed delete is never left live behind a closed menu.
    armed.disarm();
    setOpen(false);
    setSheetOpen(false);
    onOpenChange?.(false);
  }, [armed, onOpenChange]);

  /** Read the room, then open. */
  const place = useCallback(() => {
    const box = anchor.current?.getBoundingClientRect();
    if (!box) return;
    const bounds = (
      anchor.current?.closest("main") ?? document.documentElement
    ).getBoundingClientRect();
    // Leftward by default — every one of these triggers sits at the right edge
    // of the thing it belongs to, so that is the side with room.
    setLeftward(box.right - PANEL_W >= bounds.left);

    const floating = document.querySelector("[data-create-bar]")?.getBoundingClientRect();
    const floor = Math.min(window.innerHeight, floating?.top ?? Infinity);
    const below = floor - box.bottom;
    const height = actions.length * PANEL_LINE + PANEL_PAD;
    // When neither side fits, take the roomier one rather than always falling
    // downward.
    setUpward(below < height && box.top > below);
  }, [actions.length]);

  const wordOf = (action: MenuAction) =>
    action.arm
      ? armed.busy
        ? "Working…"
        : armed.armed
          ? (action.armedLabel ?? `Confirm — ${String(action.label).toLowerCase()}`)
          : action.label
      : action.label;

  const Glyph = vertical ? DotsVerticalIcon : DotsIcon;
  const triggerClass = iconButtonClass({
    size: "sm",
    ...(overlay ? { intent: "overlay" as const } : {}),
    className: overlay ? "bg-overlay-scrim/60" : "shrink-0 text-muted hover:text-ink",
  });

  return (
    <div ref={anchor} className={`${className} transition-opacity`}>
      {/* The pointer's menu. Hidden below `md`, where the sheet takes over. */}
      <Dropdown.Root
        open={open}
        onOpenChange={(next: boolean) => {
          if (!next) {
            close();
            return;
          }
          place();
          setOpen(true);
          onOpenChange?.(true);
        }}
      >
        <Dropdown.Trigger
          aria-label={triggerLabel}
          title={triggerLabel}
          className={`${triggerClass} max-md:hidden`}
        >
          <Glyph className={overlay ? "size-4 fill-current stroke-none" : undefined} />
        </Dropdown.Trigger>

        {/*
          **`z-40` because the menu is transient and everything it could hide is
          not.** The create sheet and the app header are both `z-30`, and a menu
          half-covered by either is a menu whose last lines cannot be read or
          pressed. The placement keeps it clear of both where there is room;
          this is what makes the remaining case legible rather than truncated.
        */}
        <Dropdown.Content
          className={`z-40 max-h-[70vh] overflow-y-auto ${
            leftward ? "left-auto right-0" : "left-0 right-auto"
          } ${upward ? "bottom-full top-auto mb-2 mt-0" : ""}`}
        >
          {actions.map((action) => (
            <Dropdown.Item
              key={action.key}
              disabled={action.disabled || (action.arm && armed.busy)}
              title={action.reason}
              className={`${action.className ?? ""} ${
                action.danger || armed.armed ? "text-danger" : ""
              }`}
              {...(action.arm ? armed.handlers : {})}
              onClick={
                action.arm
                  ? (event: React.MouseEvent) => {
                      // Arming must not close the menu — the confirmation IS
                      // the line.
                      if (!armed.armed) event.preventDefault();
                      armed.press();
                    }
                  : action.keepOpen
                    ? (event: React.MouseEvent) => {
                        event.preventDefault();
                        void action.onSelect();
                      }
                    : undefined
              }
              onSelect={action.arm || action.keepOpen ? undefined : () => void action.onSelect()}
            >
              <span
                className="flex items-center gap-2"
                aria-live={action.arm ? "assertive" : action.keepOpen ? "polite" : undefined}
              >
                {action.icon}
                {wordOf(action)}
              </span>
            </Dropdown.Item>
          ))}
        </Dropdown.Content>
      </Dropdown.Root>

      {/* The phone's: the same list as a sheet at the foot of the screen. */}
      <Drawer.Root
        side="bottom"
        open={sheetOpen}
        onOpenChange={(next: boolean) => {
          if (!next) {
            close();
            return;
          }
          setSheetOpen(true);
          onOpenChange?.(true);
        }}
      >
        <Drawer.Trigger
          aria-label={triggerLabel}
          title={triggerLabel}
          className={`${triggerClass} md:hidden`}
        >
          <Glyph className={overlay ? "size-4 fill-current stroke-none" : undefined} />
        </Drawer.Trigger>
        <Drawer.Backdrop />
        <Drawer.Panel ref={sheet} className="max-h-[85vh] overflow-y-auto rounded-t-lg pt-0">
          <Drawer.Title className="sr-only">{triggerLabel}</Drawer.Title>
          <SheetHandle panel={sheet} onDismiss={close} />
          <div className="flex flex-col pb-2">
            {/* What the menu is about, so a sheet that covers the thing it was
                opened from still says which one it is. */}
            <Text variant="caption" tone="muted" className="truncate px-2 pb-1">
              {label}
            </Text>
            {actions.map((action) => (
              <button
                key={action.key}
                type="button"
                disabled={action.disabled || (action.arm && armed.busy)}
                title={action.reason}
                {...(action.arm ? armed.handlers : {})}
                onClick={() => {
                  if (action.arm) {
                    armed.press();
                    return;
                  }
                  void action.onSelect();
                  if (!action.keepOpen) close();
                }}
                className={`flex min-h-11 items-center gap-3 rounded-md px-2 text-left text-sm
                            hover:bg-fill active:bg-fill-active disabled:opacity-50
                            ${action.className ?? ""}
                            ${action.danger || armed.armed ? "text-danger" : ""}`}
              >
                {action.icon}
                <span
                  aria-live={action.arm ? "assertive" : action.keepOpen ? "polite" : undefined}
                >
                  {wordOf(action)}
                </span>
              </button>
            ))}
          </div>
        </Drawer.Panel>
      </Drawer.Root>
    </div>
  );
}
