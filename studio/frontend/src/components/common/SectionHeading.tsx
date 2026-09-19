import type { ReactNode } from "react";

import { Text } from "@ansavva/design-system";

interface Props {
  title: string;
  /** How many the section holds, in mono after the title — `Projects (4)`. */
  count?: number;
  /** A control at the right edge — "See all", a sort. Baseline-aligned with the title. */
  trailing?: ReactNode;
}

/**
 * The one heading a section of a page wears.
 *
 * A `title` with a hairline under it — the same rule `PageBar` draws under a
 * page title, which is what makes a column of sections read as one ruled page
 * rather than as headings floating over grids. Five places drew it by hand
 * and two of them had drifted: home and favorites put the rule on a box
 * around the text with a mono `(n)` inside, a scene and a movie put the rule
 * on the `Text` itself with no count. One recipe now, and the count is a
 * prop so no caller re-spells the mono span.
 *
 * `trailing` sits on the same line at the far end, aligned to the title's
 * baseline.
 */
export function SectionHeading({ title, count, trailing }: Props) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line pb-2">
      <Text variant="title">
        {title}
        {count !== undefined && (
          <>
            {" "}
            <span className="font-mono text-sm text-muted tabular-nums">({count})</span>
          </>
        )}
      </Text>
      {trailing}
    </div>
  );
}
