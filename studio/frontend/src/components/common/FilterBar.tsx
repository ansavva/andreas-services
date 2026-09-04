import { useState, type ReactNode } from "react";

import { Badge, Button, Collapsible, buttonClass } from "@ansavva/design-system";

interface Props {
  /** How many fields are narrowing the listing right now — the badge, and whether Clear shows. */
  activeCount: number;
  /** Reset every field this bar holds, back to its resting value. */
  onClear: () => void;
  /** The fields themselves. Each owns its own `useSearchParamState` — this component knows nothing about what it holds. */
  children: ReactNode;
  /** Names the disclosure for a page with more than one — a project's Runs tab is the only one today. */
  label?: string;
}

/**
 * One collapsible filter surface, shared by the file browser and the Runs
 * table.
 *
 * **Both used to be always open.** The browser's text filter and tag picker
 * sat in the toolbar on every folder, most of which nobody was filtering; the
 * Runs table's five fields filled a `border bg-card` panel above three runs.
 * Collapsed by default is the fix for both — a count badge says whether
 * anything is narrowing the list, so closing the panel does not hide that a
 * filter is active.
 *
 * **Every field is URL state, not this component's.** That is what makes a
 * filtered view a link: `FilterBar` only draws the disclosure and reads how
 * many fields the caller says are active, so a shared URL restores the same
 * fields open to the same values whether or not the panel itself was left
 * open — the panel's own open/closed state is the one thing here that does
 * NOT belong in the address bar, because it is chrome rather than a fact about
 * the listing.
 */
export function FilterBar({ activeCount, onClear, children, label = "Filter" }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="contents">
      <Collapsible.Trigger
        className={buttonClass({ intent: "secondary", size: "sm", className: "shrink-0 gap-2" })}
      >
        {label}
        {activeCount > 0 && (
          <Badge intent="neutral" className="font-mono tabular-nums">
            {activeCount}
          </Badge>
        )}
      </Collapsible.Trigger>

      {/* `basis-full` sits on THIS wrapper rather than on `Collapsible.Panel`
          itself: the panel's own `className` prop reaches its innermost div,
          two levels below the one that is actually laid out as this flex
          row's child, so a width set there would never reach the box that
          needs to wrap onto its own line.

          **Conditional on `open`, not constant.** `Collapsible.Root`'s
          `contents` display means this div is a flex item of the CALLER's
          toolbar row even while collapsed — so a bare `basis-full` claimed
          the whole line whether or not the panel had anything in it,
          wrapping every sibling after `FilterBar` (Upload, the folder `⋯`)
          onto a second row at every width, not just below the one the panel
          itself needs to stack at.

          **`basis-0 min-w-0` CLOSED, not `undefined`.** That last sentence
          used to read "closed, this is a normal auto-basis item … with no
          claim on the line at all", and it was wrong — measured at 390px, the
          closed wrapper was the full 358px of the row. An auto-basis flex
          item is sized by its CONTENT, and the content is the collapsed
          panel's filter controls, whose min-content width is most of a phone.
          Invisible (the panel is zero-height) and still occupying a whole
          line, which is what kept pushing the folder browser's `⋯` onto a
          second row after everything else had been made narrow enough.
          `basis-0` gives it no base size and `min-w-0` lets it actually reach
          zero, so closed it claims nothing. */}
      <div className={open ? "basis-full" : "min-w-0 basis-0"}>
        <Collapsible.Panel>
          <div className="flex flex-wrap items-end gap-2 border border-line bg-card p-3">
            {children}
            {activeCount > 0 && (
              <Button intent="secondary" size="sm" onClick={onClear}>
                Clear
              </Button>
            )}
          </div>
        </Collapsible.Panel>
      </div>
    </Collapsible.Root>
  );
}
