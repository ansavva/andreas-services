import { buttonClass } from "@ansavva/design-system";
import type { ButtonSize } from "@ansavva/design-system";

interface Options {
  size?: ButtonSize;
  /**
   * Let the label run to more than one line.
   *
   * `buttonClass` is `whitespace-nowrap` at a fixed height, which is right for
   * a word and wrong for a sentence — an armed delete spells out what it will
   * destroy, and on a phone a long noun ran off the side and took the page's
   * horizontal scroll with it.
   */
  wraps?: boolean;
  className?: string;
}

/**
 * The one recipe for a text button that destroys.
 *
 * **The package has no danger intent for a text button**, and says why:
 * `button.props.ts` records that the token set has no measured `danger-text`
 * pair. `IconButton` has one, because a glyph is not text, and this is its fill
 * row — `bg-danger` under `primary-text`, which flips with the scheme and was
 * measured at 5.8:1 light and 6.2:1 dark. So a text button destroying something
 * wears the same fill as an icon button doing the same, and the two read as one
 * kind of control.
 *
 * It is a class string, not an inline style. `buttonClass` merges through
 * tailwind-merge, which drops the intent's own `bg-*`/`text-*` when a later
 * class sets the same property — so this wins by construction, not by
 * stylesheet order. `ConfirmDeleteButton` used to argue the opposite and paint
 * its fill inline; that holds for two utilities that both survive the merge,
 * and none do here.
 */
export function dangerButtonClass({ size = "sm", wraps = false, className }: Options = {}) {
  return buttonClass({
    intent: "secondary",
    size,
    className: [
      "bg-danger text-primary-text hover:bg-danger-hover active:bg-danger-hover",
      wraps && "h-auto min-h-8 whitespace-normal py-1 text-start",
      className,
    ]
      .filter(Boolean)
      .join(" "),
  });
}
