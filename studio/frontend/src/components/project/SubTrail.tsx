import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { Breadcrumbs } from "@ansavva/design-system";

import { ActionMenu } from "../common/ActionMenu";
import type { PageBarMenuItem } from "../layout/PageBar";

/**
 * Where a scene or a movie sits under its project's tabs — the row the Files
 * tab draws for a folder, for an entity: `<project> / <name>`, its facts, and
 * its `⋯`.
 *
 * The page bar above it is the project's (`ProjectBar`), so this row is where
 * everything about the entity itself goes: the trail says which one it is,
 * `meta` says what state it is in, and `menu` is what can be done to it.
 * The project crumb leads back to the tab it is listed under, not to the
 * project's default — a person who pressed it wants the listing they came
 * through, one row up, not the feed.
 */
export function SubTrail({
  parent,
  title,
  meta,
  menu,
}: {
  /** The project, linked to the tab this entity is listed under. */
  parent: { label: string; to: string };
  /** The entity's own name — the current crumb, never a link. */
  title: string;
  /** Badges after the trail — status, a date, a count. */
  meta?: ReactNode;
  /** The entity's own `⋯`, in `PageBar`'s shape. */
  menu?: PageBarMenuItem[];
}) {
  const navigate = useNavigate();
  return (
    <div className="flex min-h-9 min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-2">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
        <Breadcrumbs.Root className="w-auto min-w-0 [&>ol]:flex-nowrap [&_li]:min-w-0">
          {/* `href` so it reads and behaves as a link — middle-click, copy
              address — with the router taking the plain click. The same
              bargain `PageBar`'s trail makes. */}
          <Breadcrumbs.Item
            href={parent.to}
            className="min-w-0 truncate"
            onClick={(event: React.MouseEvent) => {
              if (event.metaKey || event.ctrlKey || event.shiftKey) return;
              event.preventDefault();
              navigate(parent.to);
            }}
          >
            {parent.label}
          </Breadcrumbs.Item>
          <Breadcrumbs.Item current className="min-w-0 truncate">
            {title}
          </Breadcrumbs.Item>
        </Breadcrumbs.Root>
        {meta && <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">{meta}</div>}
      </div>
      {menu && menu.length > 0 && (
        // Named for the entity — `Actions for <name>` — where `PageBar`'s is
        // "More actions": the project's `⋯` sits a few lines up with that
        // name, and two triggers reading the same is a coin toss for a
        // reader and for a test.
        <ActionMenu
          label={title}
          actions={menu.map((item) => ({
            key: item.label,
            label: item.label,
            icon: item.icon,
            danger: item.danger,
            disabled: item.disabled,
            onSelect: item.onSelect,
          }))}
        />
      )}
    </div>
  );
}
