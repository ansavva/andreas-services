import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { Breadcrumbs } from "@ansavva/design-system";

/** One step above the current page. The current page itself is never a crumb. */
export interface Crumb {
  label: string;
  to: string;
}

interface Props {
  /**
   * Where this page sits, nearest ancestor last.
   *
   * **This is what replaced three hand-rolled `← Project` buttons.** A run, a
   * scene and a movie each grew their own back button pointing at their
   * project, each styled and placed slightly differently, and every other page
   * had nothing at all — so "how do I get out of here" had three answers and
   * one shrug. A crumb says where you are as well as offering the way up, which
   * a button cannot.
   */
  crumbs?: Crumb[];
  /** The title block — a heading, a slug, whatever badges the page carries. */
  children?: ReactNode;
  /** This page's own controls. Delete lives here on the pages that have one. */
  actions?: ReactNode;
}

/**
 * A page's own header row: where it sits, what it is, and what can be done to it.
 *
 * The two groups are `justify-between` children rather than one run of items
 * with `ms-auto` on the last, and that is load-bearing on a phone: `ms-auto`
 * pins a control to the right of whatever *line* the flex run happened to break
 * at, so a destructive button moved around under the title depending on how long
 * the name was. Two groups give it one place on a wide screen and one place on a
 * narrow one.
 *
 * **A hairline under it, not a card around it.** The title block used to end
 * where the next section's own margin began, so on a page of stacked bordered
 * cards the heading read as one more card. One rule at the bottom is what
 * separates "what this page is" from "what is on it" — and it is the same rule
 * every section boundary in the app is drawn with now, so a page reads as one
 * column divided rather than a stack of boxes.
 */
export function PageBar({ crumbs, children, actions }: Props) {
  const navigate = useNavigate();

  return (
    // `gap-3` + `pb-3` is the 12px half-line the header's own padding sits on.
    <div className="flex flex-col gap-3 border-b border-line pb-3">
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

      {(children || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">{children}</div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </div>
      )}
    </div>
  );
}
