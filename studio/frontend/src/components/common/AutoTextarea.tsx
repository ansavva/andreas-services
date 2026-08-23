import { useCallback, useLayoutEffect, useRef, type ComponentProps } from "react";

import { Textarea } from "@ansavva/design-system";

type TextareaProps = ComponentProps<typeof Textarea>;

interface Props extends Omit<TextareaProps, "rows"> {
  /** Never shorter than this. Falls back to the package's own default of 3. */
  minRows?: number;
  /**
   * Past this it scrolls inside instead of growing.
   *
   * Set high on purpose: for a bible field the page scrolling is better than the
   * box scrolling, and a cap only exists so a pathological value cannot produce
   * an element thousands of pixels tall.
   */
  maxRows?: number;
}

/** Matches the package's own `minHeightForRows` arithmetic, which native uses. */
const LINE_HEIGHT = 20;
const VERTICAL_PADDING = 16;

/**
 * A `Textarea` that is as tall as what it holds.
 *
 * **A fixed `rows` cannot be right on two screen widths at once.** `rows` counts
 * *lines*, and how many lines a value takes depends entirely on how wide the
 * column is: the same 300-character bible field is four lines on a desktop and
 * eleven on a phone, so `rows={4}` showed all of it in one place and a third of
 * it in the other. Guessing from the character count has the same flaw one step
 * removed — it still has to assume a width.
 *
 * So the height is measured rather than guessed: set it to `auto`, read
 * `scrollHeight`, and use that. Re-run on every value change, and — via a
 * `ResizeObserver` watching only the width — whenever the column itself changes,
 * which covers rotating a phone, resizing a window, and a collapsed section
 * being opened for the first time.
 *
 * **Guarded for jsdom**, which implements no layout at all and reports
 * `scrollHeight` as 0. Left unguarded it would set every textarea in the test
 * suite to zero height; guarded, the element simply keeps the `rows` the
 * package gave it, which is what a test can meaningfully assert on anyway.
 */
export function AutoTextarea({ minRows = 3, maxRows = 40, value, ...rest }: Props) {
  const ref = useRef<HTMLTextAreaElement | null>(null);
  const lastWidth = useRef<number | null>(null);

  const fit = useCallback(() => {
    const node = ref.current;
    if (!node) return;

    node.style.height = "auto";
    const wanted = node.scrollHeight;

    // jsdom, or an element not laid out yet. Leave `rows` in charge.
    if (wanted === 0) {
      node.style.height = "";
      return;
    }

    const ceiling = maxRows * LINE_HEIGHT + VERTICAL_PADDING;
    node.style.height = `${Math.min(wanted, ceiling)}px`;
    node.style.overflowY = wanted > ceiling ? "auto" : "hidden";
  }, [maxRows]);

  useLayoutEffect(fit, [fit, value]);

  useLayoutEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return undefined;

    // Width only. Observing height would react to the height this very effect
    // sets, which is a loop.
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width === undefined || width === lastWidth.current) return;
      lastWidth.current = width;
      fit();
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [fit]);

  return <Textarea ref={ref} rows={minRows} value={value} {...rest} />;
}
