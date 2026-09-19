import { useCallback, useMemo, useState } from "react";

import { Button, Input, Text } from "@ansavva/design-system";

import { getTemplates } from "../../apis/studio";
import { EmptyState } from "../common/EmptyState";
import { SectionLoading } from "../common/SectionLoading";
import { useResource } from "../../hooks/useResource";
import { LoadError } from "../common/LoadError";
import { TemplateIcon } from "../common/icons";
import { citationsIn } from "../../utils/citations";

interface Props {
  /**
   * Called with the chosen template's prompt, as written — citations and all.
   * FILLING it is the caller's, because only the caller knows the cast; the
   * create bar expands it before it reaches the box. It does NOT save, because
   * picking a template is the start of an edit rather than the end of one.
   */
  onPick: (prompt: string) => void;
  /** How many characters this run binds. `@character.1.…` is the first of them. */
  cast: number;
  /** Put the caret in the search box on open — under a mouse, not a thumb. */
  autoFocus?: boolean;
}

const GLYPH = "size-4 shrink-0 fill-none stroke-current stroke-[1.5]";

/**
 * The highest `@character.N.…` a template cites, or 0 if it cites none.
 *
 * **Not every template needs a character**, which is why this is a number rather
 * than a flag: one built entirely from `@block.…` fills against a run that
 * binds nobody, and a picker that hid every template until a cast existed would
 * hide exactly the ones that never needed one.
 */
function castNeededBy(prompt: string): number {
  let most = 0;
  for (const cited of citationsIn(prompt)) {
    if (cited.namespace !== "character") continue;
    const [, position] = cited.name.split(".");
    if (/^\d+$/.test(position ?? "")) most = Math.max(most, Number(position));
  }
  return most;
}

/**
 * Start a prompt from a template somebody wrote.
 *
 * **This is what the turnaround was, minus the fan-out.** A reference angle was
 * a prompt plus a description plus tags, and the only thing that could use one
 * rendered all fourteen at once, each chained off the first. The prompts are
 * the part worth keeping: a template is picked for one run, filled from that
 * run's cast, and edited before it goes anywhere.
 *
 * ## It fills the box and stops
 *
 * Choosing does not save and does not submit. The prompt lands in the editor as
 * text a person then reads, changes and says to send — which is where hard
 * rule #2 has always put the decision. A picker that saved would make "look at a
 * template" and "commit to it" the same gesture.
 *
 * ## Nothing here is blocked
 *
 * A template built from `@block.…` alone fills against a run that binds
 * nobody, so gating the list on a cast would hide exactly the templates that
 * never needed one. And gating the ROWS is barely better: a person who wants a
 * template that cites a character they have not added yet wants to add the
 * character, not to be told they may not look. So every row is pickable, a row
 * that needs more cast than the run has says so, and a pick whose fill is
 * refused leaves the template in the box with the refusal named beside it.
 *
 * ## The same list the model and the project draw
 *
 * A search box, then one row per name with a glyph in a square, the name and
 * a caption under it — `ModelList` and `ProjectList` in `CreateChips`, to the
 * class. It was a column of bordered cards with mono captions, which looked
 * like nothing else behind a chip; three chips in one row opening three
 * different shapes of list read as three different apps.
 *
 * ## What it does NOT copy
 *
 * The template's `description` and `tags` describe the image it makes, not the
 * run that makes it, so they belong to a promotion rather than to a plan. They
 * stay on the template until somebody promotes an output into a character.
 */
export function TemplateList({ onPick, cast, autoFocus = false }: Props) {
  const load = useCallback(() => getTemplates(), []);
  const library = useResource(["templates"], load);
  const [query, setQuery] = useState("");

  const offered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (library.data?.templates ?? []).filter(
      (each) =>
        q === "" ||
        each.name.toLowerCase().includes(q) ||
        each.prompt.toLowerCase().includes(q) ||
        each.tags.some((tag) => tag.toLowerCase().includes(q)),
    );
  }, [library.data, query]);

  return (
    <div className="flex flex-col gap-2">
      <Input
        aria-label="Search templates"
        placeholder="Search templates…"
        value={query}
        onValueChange={setQuery}
        autoFocus={autoFocus}
      />

      {library.loading && <SectionLoading label="Loading templates" />}

      {library.error && (
        <LoadError
          what="templates"
          message={library.error}
          onRetry={library.reload}
        />
      )}

      {library.data && (
        <ul className="flex flex-col" role="listbox" aria-label="Templates">
          {offered.map((entry) => {
            const needs = castNeededBy(entry.prompt);
            const short = needs > cast;
            return (
              <li key={entry.id} role="presentation">
                <Button
                  intent="secondary"
                  size="sm"
                  wrap
                  role="option"
                  aria-selected={false}
                  className="h-auto w-full justify-start gap-3 rounded-sm px-2 py-2 text-left
                             hover:bg-fill active:bg-fill-active bg-transparent"
                  onClick={() => onPick(entry.prompt)}
                >
                  <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-sm bg-fill-hover text-ink">
                    <TemplateIcon className={GLYPH} />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <Text as="span" variant="body" weight="medium" className="truncate">
                      {entry.name}
                    </Text>
                    {/* The first line only. A template is a wall of prose and a
                        list of walls is unreadable; what a person is choosing
                        between is which template, not which paragraph. */}
                    <Text variant="caption" tone="muted" className="line-clamp-2 whitespace-normal">
                      {entry.prompt.trim().split("\n")[0]}
                    </Text>
                    {/* **Said, not enforced.** Every template is pickable: it
                        lands in the box, filled where it can be and left as
                        written where it cannot, and the cast is editable right
                        there. Blocking the pick instead would be this screen
                        deciding which of its own problems a person is allowed
                        to see. */}
                    {short && (
                      <Text variant="caption" tone="muted" className="whitespace-normal">
                        Needs character {needs}; this run binds{" "}
                        {cast === 0 ? "none" : cast}.
                      </Text>
                    )}
                  </span>
                </Button>
              </li>
            );
          })}
          {offered.length === 0 && (
            <li className="px-2 py-3">
              {library.data.templates.length === 0 ? (
                // The same empty state the Templates page shows, rather than
                // a paragraph of its own — a fresh dev stack seeds one
                // character and no templates, so this is the first thing
                // the dropdown shows there.
                <EmptyState
                  title="No templates yet."
                  hint={
                    <>
                      Write one on the Templates page, or push several at once with{" "}
                      <code>studio templates push --path &lt;file&gt;</code>.
                    </>
                  }
                />
              ) : (
                <EmptyState title={`Nothing here matches “${query}”.`} />
              )}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
