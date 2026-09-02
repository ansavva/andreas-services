import { useState } from "react";
import type { KeyboardEvent } from "react";

import { Badge, Button, Input, Text } from "@ansavva/design-system";

import { ChipRow } from "../common/ChipRow";

interface Props {
  /** The tags currently narrowing the listing. Every entry carries ALL of them. */
  value: string[];
  onChange: (tags: string[]) => void;
  /**
   * The facet the last listing came back with — tag to how many entries carry
   * it, commonest first. Empty when nothing in reach is tagged.
   */
  facet: Record<string, number>;
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
export function TagFilter({ value, onChange, facet, searching }: Props) {
  const [draft, setDraft] = useState("");

  const add = (typed: string) => {
    // Folded the way the API folds them, so a chip and a typed word are the
    // same tag: lowercased, inner whitespace collapsed. Commas split, because
    // `default,face` is how the filter reads on the wire and in the CLI, and
    // typing it should not produce one tag with a comma in it.
    const clean = typed
      .split(",")
      .map((part) => part.trim().toLowerCase().split(/\s+/).join(" "))
      .filter((part) => part && !value.includes(part));
    if (clean.length) onChange([...value, ...clean]);
    setDraft("");
  };

  /**
   * Enter commits, Backspace on an empty box drops the last tag.
   *
   * **A key handler rather than a `<form>`.** Implicit submission is a browser
   * behaviour conditional on the form having exactly one field and no submit
   * button, and it did not fire here — which fails silently in the worst way:
   * the word sits in the box looking applied while the listing is unchanged.
   */
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      add(draft);
    } else if (event.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  };

  // Already-chosen tags are dropped from the chips: their count is the whole
  // result, so offering them again would narrow nothing.
  const offered = Object.entries(facet).filter(([tag]) => !value.includes(tag));

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-40 sm:max-w-56">
          <Input
            value={draft}
            onValueChange={setDraft}
            onKeyDown={onKeyDown}
            placeholder="Filter by tag…"
            aria-label="Filter by tag"
          />
        </div>

        {value.map((tag) => (
          <Button
            key={tag}
            size="sm"
            intent="secondary"
            onClick={() => onChange(value.filter((each) => each !== tag))}
            aria-label={`Remove tag ${tag}`}
          >
            {tag} ✕
          </Button>
        ))}

        {value.length > 0 && (
          <Button size="sm" intent="secondary" onClick={() => onChange([])}>
            Clear
          </Button>
        )}
      </div>

      {offered.length > 0 && (
        <ChipRow aria-label="Tags in these results">
          {offered.map(([tag, count]) => (
            <button key={tag} type="button" onClick={() => add(tag)} className="snap-start">
              <Badge>
                {tag} {count}
              </Badge>
            </button>
          ))}
        </ChipRow>
      )}

      {searching && (
        <Text variant="caption" tone="muted">
          Searching this folder and everything under it.
        </Text>
      )}
    </div>
  );
}
