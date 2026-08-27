import { useNavigate } from "react-router-dom";

import { Text } from "@ansavva/design-system";

import type { Backlink } from "../../types";

interface Props {
  /** What the relationship is, from this page's point of view: "Cut into". */
  label: string;
  links: Backlink[];
  to: (id: string) => string;
}

/**
 * The way back UP the tree.
 *
 * Every other link in this app goes down — a project to its runs, a scene to
 * its shots, a movie to its cuts — because down is what a record holds. Up was
 * unanswerable: a run knew nothing of the scene that used it and a scene
 * nothing of the movie that cut it, so arriving at either from the reel was a
 * dead end and the way back was the project and down the other branch.
 *
 * **Renders nothing when there are no links**, rather than an empty row saying
 * so. A run that no scene has used is the ordinary case, not a gap — most runs
 * are never cut into anything, and a permanent "Used in: —" would be noise on
 * every one of them.
 */
export function Backlinks({ label, links, to }: Props) {
  const navigate = useNavigate();
  // `links ?? []`, not `links`: the API always sends the field, but a page is
  // not worth crashing over a missing array. This rendered `undefined.length`
  // and took the whole run page down with it when a fixture omitted the field,
  // which a `Partial<T> as T` cast hides from the compiler.
  const shown = links ?? [];
  if (shown.length === 0) return null;

  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <Text variant="caption" tone="muted">
        {label}
      </Text>
      {shown.map((link) => (
        <button
          key={link.id}
          type="button"
          onClick={() => navigate(to(link.id))}
          className="rounded text-sm text-accent underline underline-offset-2 hover:opacity-80"
        >
          {link.title || link.slug || link.id}
        </button>
      ))}
    </div>
  );
}
