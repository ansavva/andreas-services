import type { ReactNode } from "react";

import { Text } from "@ansavva/design-system";

interface Props {
  /**
   * One short sentence. Two shapes: "No ‹nouns› yet." for a list that will
   * fill, "Nothing here matches …" for a filter that found nothing.
   */
  title: string;
  /** One line on what would put something here — a concept, or a step. */
  hint?: ReactNode;
  /** The control that fills it, when the heading above does not carry one. */
  action?: ReactNode;
  className?: string;
}

/**
 * A list with nothing in it, said the same way everywhere.
 *
 * Twenty-odd sentences said this across the app, in twenty-odd voices —
 * "This folder is empty", "Nothing planned yet", "There are no characters in
 * this library yet" — some as body text, some as captions, two in an info
 * alert with a border around them. An empty list is not an event and gets no
 * frame: muted text, the title first, and a hint only where the reader may
 * not know what the noun is or what would make one.
 *
 * `action` is for a create control that already exists on the page and has
 * nowhere else to sit. When the heading carries it, pass nothing — an empty
 * list drew "New project" twice, a handspan apart, before `EntitySections`
 * learned this.
 */
export function EmptyState({ title, hint, action, className = "" }: Props) {
  return (
    <div className={`flex flex-col items-start gap-2 ${className}`.trim()}>
      <div className="flex flex-col gap-1">
        <Text variant="body" tone="muted">
          {title}
        </Text>
        {hint !== undefined && (
          <Text variant="caption" tone="muted" className="max-w-prose">
            {hint}
          </Text>
        )}
      </div>
      {action}
    </div>
  );
}
