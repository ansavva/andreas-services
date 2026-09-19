import type { ReactElement, ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Breadcrumbs, Text } from "@ansavva/design-system";

import { copyLabel, useCopyToClipboard } from "../../hooks/useCopyToClipboard";
import { absoluteUrl } from "../../utils/location";
import { ActionMenu } from "../common/ActionMenu";
import { LinkIcon } from "../common/icons";

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
export interface PageBarMenuItem {
  label: string;
  /** A glyph beside the word, as every menu line in the app now carries. */
  icon: ReactElement;
  onSelect: () => void;
  /** Red label — for an item that destroys something. */
  danger?: boolean;
  disabled?: boolean;
}

/**
 * The page's own address, as a menu line — "Copy link", for the `menu` above.
 *
 * **The address bar as-is**, tab and filters included: a character on its
 * Files tab three folders down, a project's Runs tab narrowed to one model,
 * a scene, a movie — every one of these is already a place with an address
 * (`useSearchParamState` is what made the tab one), and what a person means
 * by "send me this" is what they are looking at. The origin goes in front so
 * the pasted text is a URL and not a path.
 *
 * A hook rather than a prop on `PageBar`, so each page decides where in its
 * menu the line sits — first, before Delete, on every page that has one.
 */
export function useCopyLinkItem(): PageBarMenuItem {
  const { pathname, search } = useLocation();
  const { status, copy } = useCopyToClipboard();
  return {
    label: copyLabel(status, "Copy link"),
    icon: <LinkIcon className="size-4 shrink-0 fill-none stroke-current stroke-[1.5]" />,
    onSelect: () => void copy(absoluteUrl(`${pathname}${search}`)),
  };
}

interface Props {
  /** Where this page sits, nearest ancestor last. Never the current page. */
  crumbs?: Crumb[];
  /** The page's name. Ends the crumb trail as a truncating heading. */
  title?: string;
  /** Badges after the title — status, kind, a count, whatever the page counts as its own facts. */
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
 * called, and what can be done to it — on one line.
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
 * **It was three rows and is now one.** A crumb line, a display-sized title
 * with its badges under it, and the controls on the right took a hundred
 * pixels before the tabs, and on a project page the primary slot (the
 * character chips) sat alone at the far end of the middle row with nothing
 * beside it. The title now finishes the crumb trail — `Projects / andreas` —
 * the badges sit after it, and the controls keep the right edge, all on the
 * same line. The crumbs stay a `Breadcrumbs` landmark holding the ancestors
 * only, and the title stays a heading: a screen reader still gets a nav
 * and an `h3`, not one nav with the page as its last crumb. A page with no
 * crumbs (Home, a cold Object link) reads the same line with nothing before
 * the title, so nothing hops when a crumb loads a beat late.
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
  const hasCrumbs = Boolean(crumbs && crumbs.length > 0);

  return (
    <div className={`flex flex-col gap-3 ${tabs ? "" : "border-b border-line pb-3"}`}>
      <div className="flex min-h-9 min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
          {/* The trail: crumbs, a separator, the title — one run of heading
              type. The list inside `Breadcrumbs.Root` fixes its own size and
              face (`text-sm font-body`), so both are overridden at the `ol`
              to match the title beside it, and the landmark's `w-full` is
              undone so it takes only the width its crumbs need.

              When the line is short the crumbs give way first, and it is a
              GRID that says so. Its two `minmax(0, max-content)` tracks are
              handed the width they have in equal shares, each stopping at
              what it needs — so a short title (`request.json`) is whole
              before a run-id crumb beside it gets the rest, and a long title
              with no crumbs still elides rather than overflowing. Flex could
              not say this: it takes width away in proportion to what each
              item asked for, so the long crumb kept most of its width and
              the file page read `run-6b9b…d7d / re…`; weighting the
              crumbs' `shrink` only softened it, and capping the title at a
              fraction of the trail shrank a crumbless `Files` to `F…`,
              because the trail is as wide as its content. */}
          {(hasCrumbs || title) && (
            <div
              className={`grid min-w-0 items-center gap-xs font-heading text-xl ${
                hasCrumbs && title
                  ? "grid-cols-[minmax(0,max-content)_auto_minmax(0,max-content)]"
                  : "grid-cols-[minmax(0,max-content)]"
              }`}
            >
              {hasCrumbs && (
                <Breadcrumbs.Root className="w-auto min-w-0 [&>ol]:flex-nowrap [&>ol]:font-heading [&>ol]:text-xl [&_li]:min-w-0">
                  {crumbs!.map((crumb) => (
                    // `href` so it reads and behaves as a link — middle-click,
                    // copy address — with the router taking the plain click.
                    // The same bargain `FolderBrowser`'s trail makes.
                    <Breadcrumbs.Item
                      key={crumb.to}
                      href={crumb.to}
                      className="min-w-0 truncate"
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
              {hasCrumbs && title && (
                // The same glyph the landmark draws between its own crumbs,
                // and hidden from a reader for the same reason.
                <span aria-hidden="true" className="select-none text-muted">
                  /
                </span>
              )}
              {title && (
                // `truncate` is a PROP as of design-system 0.17.0, and it
                // works: the heading variants carry `text-balance`, a
                // shorthand that resets `text-wrap-mode`, and the package's
                // merge now knows the two conflict. `min-w-0` stays: that is
                // this element's job as a flex child, not the package's.
                // `text-xl` steps the variant's `text-2xl` down to the size
                // the crumbs share.
                <Text variant="heading" truncate className="min-w-0 text-xl">
                  {title}
                </Text>
              )}
            </div>
          )}
          {meta && (
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">{meta}</div>
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

      {tabs}
    </div>
  );
}
