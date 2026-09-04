import { useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { Breadcrumbs, Dropdown, Text, iconButtonClass } from "@ansavva/design-system";

import { DotsIcon } from "../common/icons";

/** One step above the current page. The current page itself is never a crumb. */
export interface Crumb {
  label: string;
  to: string;
}

/** One entry in the overflow menu behind the `⋯` trigger. */
interface PageBarMenuItem {
  label: string;
  /** Fires and closes the menu. Omit for an item that manages its own click — see `onClick`. */
  onSelect?: () => void;
  /**
   * The escape hatch `onSelect` cannot cover: an item that arms in place rather
   * than firing on the first press.
   *
   * `ItemActions`' delete item is the model — call `event.preventDefault()`
   * while unarmed to keep the menu open, and let it through once armed so the
   * menu closes the way any other selection does. `onSelect` is skipped when
   * this is given, so a caller does not have to fire the same action twice.
   */
  onClick?: (event: React.MouseEvent<HTMLButtonElement>) => void;
  /** Red label — for an item that destroys something. */
  danger?: boolean;
  disabled?: boolean;
  /**
   * Passed straight to the underlying `Dropdown.Item` — `useArmed`'s
   * `handlers` (`onBlur`, `onKeyDown`) for an item that arms in place, so it
   * disarms on blur and on Escape the same way `ItemActions`' does.
   */
  itemProps?: Record<string, unknown>;
}

interface Props {
  /** Where this page sits, nearest ancestor last. Never the current page. */
  crumbs?: Crumb[];
  /** The page's name. A string renders as `Text variant="display"`, truncating. */
  title?: string;
  /** A row under the title — status, kind, a date, whatever the page counts as its own facts. */
  meta?: ReactNode;
  /** The one action worth a full button — "New character", "Run again". */
  primary?: ReactNode;
  /**
   * Everything else this page can do to itself, behind one `⋯`.
   *
   * A danger item opens its own confirmation rather than firing straight from
   * the menu — render a `ConfirmDestroyDialog` in controlled `open` mode
   * beside the page's `PageBar` call and toggle it from `onSelect`.
   */
  menu?: PageBarMenuItem[];
  /**
   * Told when the menu opens or closes — for a caller with an arm-in-place
   * item, so it can disarm when the menu is dismissed rather than leaving a
   * half-pressed delete live behind a closed menu. Mirrors `ItemActions`'
   * `onOpenChange`.
   */
  onMenuOpenChange?: (open: boolean) => void;
  /**
   * Icon buttons that have to stay reachable — a copy, a download, a close.
   *
   * Kept separate from `menu` because these are not optional to reach: Object
   * draws its Copy/Edit/Download/Close here, where a menu would cost an extra
   * press for a control used on every visit.
   */
  actions?: ReactNode;
  /**
   * A `Tabs.List`, rendered at the bar's own bottom edge so its underline is
   * the bar's hairline rather than a second rule an inch below it.
   *
   * Passed as an element rather than owned here: the page still wraps
   * everything — this bar included — in its own `Tabs.Root`, and an element
   * handed down as a prop renders inside that tree exactly as if it had been
   * written beside the panels, so the shared context reaches it either way.
   */
  tabs?: ReactNode;
}

/**
 * The page frame every routed screen now shares: where it sits, what it is
 * called, and what can be done to it.
 *
 * **This used to be a title bar with two open slots — `children` for the
 * heading and `actions` for whatever controls the page carried — and every
 * page filled them differently.** One page's Delete sat loose beside its
 * title; another buried it three tabs deep; a third drew five icon buttons
 * over the media it was destroying. `menu`, `primary` and `actions` are the
 * three answers a page's own controls can be, in order of how often they are
 * reached for — most pages need one of the first two and nothing else.
 * `children` carried the transitional shape while every page migrated and is
 * gone now that all of them have: every call site names `title`.
 *
 * **The back arrow is gone.** It answered "where did I come from", which the
 * browser's own Back already answers, and it changed the bar's height
 * depending on `location.key` — the one piece of layout on this component that
 * moved for a reason nothing on screen explained. A crumb still answers "where
 * am I", which Back cannot.
 *
 * **The crumb row holds its height with zero crumbs.** Object's cold-link case
 * and Templates' single-crumb case both pass through here, and a title that
 * hops up a line the moment a crumb does load is worse than a blank row above
 * it always.
 */
export function PageBar({
  crumbs,
  title,
  meta,
  primary,
  menu,
  onMenuOpenChange,
  actions,
  tabs,
}: Props) {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className={`flex flex-col gap-3 ${tabs ? "" : "border-b border-line pb-3"}`}>
      {/* Fixed to one line's height regardless of content, so a page with no
          crumbs (a cold Object link) reads with the same title position as one
          with two. */}
      <div className="flex min-h-5 min-w-0 items-center gap-2">
        {crumbs && crumbs.length > 0 && (
          <Breadcrumbs.Root>
            {crumbs.map((crumb) => (
              // `href` so it reads and behaves as a link — middle-click, copy
              // address — with the router taking the plain click. The same
              // bargain `FolderBrowser`'s trail makes.
              <Breadcrumbs.Item
                key={crumb.to}
                href={crumb.to}
                onClick={(event: React.MouseEvent) => {
                  if (event.metaKey || event.ctrlKey || event.shiftKey) return;
                  event.preventDefault();
                  navigate(crumb.to);
                }}
              >
                {crumb.label}
              </Breadcrumbs.Item>
            ))}
          </Breadcrumbs.Root>
        )}
      </div>

      {(title || primary || menu || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <div className="flex min-w-0 flex-col gap-1">
            {title && (
              // `Text`'s heading variants carry `text-balance` by default,
              // which is `text-wrap: balance` — a shorthand that resets
              // `text-wrap-mode` to `wrap` wherever it wins the cascade. That
              // beats `truncate`'s `white-space: nowrap` on stylesheet order
              // alone, not on anything this className says, so an inline
              // style is what actually wins: a long project or run name wrapped
              // onto three lines instead of eliding, exactly the failure mode
              // `design-system-spacing-overrides-need-inline-style` already
              // named for the same twMerge gap.
              <Text
                variant="display"
                className="min-w-0 truncate"
                style={{ textWrap: "nowrap" }}
              >
                {title}
              </Text>
            )}
            {meta && (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">{meta}</div>
            )}
          </div>

          {(primary || menu || actions) && (
            <div className="flex shrink-0 items-center gap-2">
              {actions}
              {primary}
              {menu && menu.length > 0 && (
                <Dropdown.Root
                  open={menuOpen}
                  onOpenChange={(next: boolean) => {
                    setMenuOpen(next);
                    onMenuOpenChange?.(next);
                  }}
                >
                  <Dropdown.Trigger
                    aria-label="More actions"
                    title="More actions"
                    className={iconButtonClass({ size: "sm", className: "touch-target rounded-none" })}
                  >
                    <DotsIcon />
                  </Dropdown.Trigger>
                  <Dropdown.Content className="rounded-none">
                    {menu.map((item) => (
                      <Dropdown.Item
                        key={item.label}
                        disabled={item.disabled}
                        onSelect={item.onClick ? undefined : item.onSelect}
                        onClick={item.onClick}
                        className={item.danger ? "text-danger" : undefined}
                        {...item.itemProps}
                      >
                        {item.label}
                      </Dropdown.Item>
                    ))}
                  </Dropdown.Content>
                </Dropdown.Root>
              )}
            </div>
          )}
        </div>
      )}

      {tabs}
    </div>
  );
}
