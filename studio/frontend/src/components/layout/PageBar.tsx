import type { ReactElement, ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { Breadcrumbs, Text } from "@ansavva/design-system";

import { ActionMenu } from "../common/ActionMenu";

/** One step above the current page. The current page itself is never a crumb. */
export interface Crumb {
  label: string;
  to: string;
}

/**
 * One entry in the overflow menu behind the `⋯` trigger.
 *
 * **The arming escape hatches are gone**, and nothing lost them: `ActionMenu`
 * draws this menu now and carries `danger` itself, which is what those two
 * props (`onClick` + `itemProps`) existed to let a caller hand-roll. No page
 * used them; every one of the four passes a Delete that opens its own
 * `ConfirmDestroyDialog`.
 */
interface PageBarMenuItem {
  label: string;
  /** A glyph beside the word, as every menu line in the app now carries. */
  icon: ReactElement;
  onSelect: () => void;
  /** Red label — for an item that destroys something. */
  danger?: boolean;
  disabled?: boolean;
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
  /** Told when the menu opens or closes. */
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
              // `truncate` is a PROP as of design-system 0.17.0, and it works.
              // It used to be an inline `style={{ textWrap: "nowrap" }}`: the
              // heading variants carry `text-balance`, which is a shorthand
              // that also resets `text-wrap-mode` to `wrap`, and the package's
              // class merge did not know the two conflicted — so both survived
              // and stylesheet order decided, wrapping a long project or run
              // name onto three lines instead of eliding it. The package now
              // states that conflict in its own merge, so the prop and a bare
              // `className="truncate"` both win. `min-w-0` stays: that is this
              // element's job as a flex child, not the package's.
              <Text variant="display" truncate className="min-w-0">
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
                <ActionMenu
                  label={typeof title === "string" ? title : "this page"}
                  triggerLabel="More actions"
                  onOpenChange={onMenuOpenChange}
                  actions={menu.map((item) => ({
                    key: item.label,
                    label: item.label,
                    icon: item.icon,
                    danger: item.danger,
                    disabled: item.disabled,
                    // A page's danger item opens its own confirmation rather
                    // than arming in the menu — see the prop's docblock — so it
                    // is `danger` for the colour and fires on the first press.
                    onSelect: item.onSelect,
                  }))}
                />
              )}
            </div>
          )}
        </div>
      )}

      {tabs}
    </div>
  );
}
