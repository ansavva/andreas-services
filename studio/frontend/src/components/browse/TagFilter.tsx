import { Text } from "@ansavva/design-system";

import { TagSelect } from "../common/TagSelect";

interface Props {
  /** The tags currently narrowing the listing. Every entry carries ALL of them. */
  value: string[];
  onChange: (tags: string[]) => void;
  /** True once a tag is on, so the caller can say the scope changed. */
  searching: boolean;
}

/**
 * Narrow a listing to files carrying every one of a set of tags.
 *
 * **Tags are how things are found now**, so this is not a convenience. What was
 * a `REF#` row saying an image is a character's third face reference is the file
 * carrying `default` and `face`, and the only way back to it is to ask.
 *
 * ## Applying a tag searches the BRANCH
 *
 * Not knowing which folder a tagged image sits in is the entire reason for
 * asking by tag, so the listing switches to `depth=all` the moment one is on and
 * back when the last comes off. That is a real change of scope and it is said
 * out loud rather than left to be inferred from results appearing from
 * somewhere — see the note under the input.
 *
 * ## The chips are a facet, not a vocabulary
 *
 * Nothing stores a list of every tag in the library, and this deliberately does
 * not pretend to be one: the chips are the tags present in *what came back*,
 * counted. That makes the first one discoverable when you are standing
 * somewhere tagged, and — because the facet is computed after the filter — every
 * one after that is exactly a tag that co-occurs with what you already chose.
 * A filter you can only use by remembering what you typed last time is a filter
 * nobody uses.
 */
export function TagFilter({ value, onChange, searching }: Props) {
  return (
    <div className="flex flex-col gap-2">
      <div className="max-w-md">
        {/*
          **The vocabulary, not a text box.** This was a comma-separated input
          and a row of chips built from whatever came back — so narrowing by a
          tag meant remembering how it was spelled, and a filter you can only
          use by remembering is a filter nobody uses.

          `manage` is off: narrowing a listing and rewriting every file in the
          library are not two operations to put one keystroke apart.
        */}
        <TagSelect
          scope="file"
          value={value}
          onChange={onChange}
          placeholder="Filter by tag…"
        />
      </div>

      {searching && (
        <Text variant="caption" tone="muted">
          Searching this folder and everything under it.
        </Text>
      )}
    </div>
  );
}
