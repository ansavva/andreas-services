import { Select } from "@ansavva/design-system";

import { SORT_LABELS, type SortOrder } from "../../types";

interface Props {
  value: SortOrder;
  onChange: (next: SortOrder) => void;
}

const OPTIONS = (Object.keys(SORT_LABELS) as SortOrder[]).map((value) => ({
  value,
  label: SORT_LABELS[value],
}));

/**
 * Which order a listing comes back in.
 *
 * The order is a URL parameter rather than component state, so it survives a
 * reload and travels with a shared link — someone handed a folder link sorted
 * oldest-first sees it that way. It is applied by the API, not here: the reel
 * pages in, and a page sorted client-side would reshuffle under a scroll every
 * time the next one arrived.
 */
export function SortControl({ value, onChange }: Props) {
  return (
    <Select
      aria-label="Sort order"
      // The package's `Select` has no `size`: its trigger is `h-11` (44px)
      // unconditionally, where the `sm` ToggleGroup and `sm` Buttons beside
      // it in the browser's strip are 32. The trigger merges `className`
      // through `tailwind-merge`, so a later `h-8` displaces the `h-11`
      // rather than fighting it in the stylesheet — measured on 0.23.1 by
      // reading the emitted class list, which carries `h-8` and no `h-11`.
      // Not `.field-row`: that pins everything to 44, the opposite of this.
      className="h-8"
      options={OPTIONS}
      value={value}
      onValueChange={(next: string) => onChange(next as SortOrder)}
    />
  );
}
