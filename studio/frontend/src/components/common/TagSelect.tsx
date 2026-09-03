import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import { Alert, Badge, Button, Input } from "@ansavva/design-system";

import { EmptyState } from "./EmptyState";

import { deleteTag, getTags, renameTag } from "../../apis/studio";
import type { TagInUse, TagScope } from "../../types";
import { ConfirmDestroyDialog } from "./ConfirmDestroyDialog";

interface Props {
  /** Which vocabulary. Files and templates never share one. */
  scope: TagScope;
  /** The tags on this item, in the order they were added. */
  value: string[];
  onChange: (tags: string[]) => void;
  /** What the box says when nothing is chosen. */
  placeholder?: string;
  /**
   * Whether renaming and deleting a tag ACROSS the whole vocabulary is offered.
   *
   * Off where the control is a filter: narrowing a listing and rewriting every
   * file in the library are not operations to put one keystroke apart.
   */
  manage?: boolean;
}

/** What a rename or a delete that did not land says, and which it was. */
interface Failure {
  title: string;
  message: string;
}

/**
 * Pick tags from the vocabulary, and keep the vocabulary worth picking from.
 *
 * **A tag was free text in a comma-separated box.** That produces a vocabulary
 * nobody can see, and a vocabulary nobody can see is one everybody spells
 * differently — `three-quarter` on Monday and `three quarter` on Tuesday are two
 * tags, and the filter that finds one finds none of the other. The list is the
 * point of this control: the words already in use are on screen before anybody
 * types a new one.
 *
 * ## Two vocabularies, never merged
 *
 * `scope` is required and has no default. A file's tags say what a picture shows
 * and what it is for; a template's say what a prompt makes. Offering one while
 * somebody edits the other would suggest words that mean nothing there.
 *
 * ## Creating is tagging
 *
 * There is no "create tag" that leaves one existing but unused — the vocabulary
 * is derived from what is carried, so typing a word nobody has used and pressing
 * Enter creates it by putting it on this item, and taking it off the last item
 * deletes it. That is the deletion rule as a mechanism rather than a promise.
 *
 * ## Renaming and deleting reach everything
 *
 * The name is the identity — no id sits underneath — so renaming rewrites every
 * carrier and deleting removes the word from all of them. **Deleting types the
 * name**, through `ConfirmDestroyDialog`, because it is an entity with children:
 * "remove `studio` from 43 files" rewrites forty-three records on one press,
 * and that press used to be a bare click on a button that said "Delete" with the
 * count on a sibling span. The dialog says the count in its own sentence.
 *
 * Both report a failure here, under the box, because nothing else can: the
 * item's own save error is about the item, and a rename that half-landed across
 * the library is not that.
 */
export function TagSelect({ scope, value, onChange, placeholder, manage }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [vocabulary, setVocabulary] = useState<TagInUse[]>([]);
  const [busy, setBusy] = useState(false);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [deleting, setDeleting] = useState<TagInUse | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const box = useRef<HTMLDivElement>(null);

  const reload = useCallback(() => {
    void getTags(scope)
      .then((got) => setVocabulary(got.tags))
      // A vocabulary that will not load leaves the box usable: typing a tag is
      // the operation, and the list is what makes it easier rather than what
      // makes it possible.
      .catch(() => setVocabulary([]));
  }, [scope]);

  useEffect(() => {
    if (open) reload();
  }, [open, reload]);

  // Closing on an outside press rather than on blur: the panel holds buttons,
  // and a blur handler closes it before their click lands.
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) {
        setOpen(false);
        setRenaming(null);
      }
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  /** Folded the way the API folds a tag, so what you see is what is stored. */
  const fold = (raw: string) => raw.trim().toLowerCase().split(/\s+/).join(" ");

  const offered = useMemo(() => {
    const wanted = fold(query);
    return vocabulary
      .filter((tag) => !value.includes(tag.name))
      .filter((tag) => !wanted || tag.name.includes(wanted));
  }, [query, value, vocabulary]);

  const exact = fold(query);
  const isNew = exact.length > 0 && !vocabulary.some((tag) => tag.name === exact);

  const add = (name: string) => {
    const clean = fold(name);
    if (clean && !value.includes(clean)) onChange([...value, clean]);
    setQuery("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      // The first match, or the typed word. Enter on a list means "the obvious
      // one", and the obvious one is what is under the cursor's own query.
      add(offered[0]?.name ?? query);
    } else if (event.key === "Backspace" && !query && value.length) {
      onChange(value.slice(0, -1));
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  const rename = async (from: string) => {
    const to = fold(draft);
    if (!to || to === from) {
      setRenaming(null);
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      await renameTag(scope, from, to);
      // The item in hand follows, because a rename reached every carrier and
      // this is one of them — re-reading the record to learn that would show a
      // stale word for as long as the round trip takes.
      onChange(value.map((tag) => (tag === from ? to : tag)));
      reload();
    } catch (problem) {
      setFailure({ title: "Could not rename the tag", message: describe(problem) });
    } finally {
      setBusy(false);
      setRenaming(null);
    }
  };

  const remove = async (name: string) => {
    setBusy(true);
    setFailure(null);
    try {
      await deleteTag(scope, name);
      onChange(value.filter((tag) => tag !== name));
      reload();
    } catch (problem) {
      setFailure({ title: "Could not delete the tag", message: describe(problem) });
    } finally {
      setBusy(false);
    }
  };

  const carriers = (count: number) => {
    const one = scope === "template" ? "template" : "file";
    return count === 1 ? `1 ${one}` : `${count} ${one}s`;
  };

  return (
    <div ref={box} className="relative flex flex-col gap-1.5">
      <div
        className="flex min-h-10 flex-wrap items-center gap-1.5 rounded-md border border-line
                   bg-card px-2 py-1.5"
        onClick={() => setOpen(true)}
      >
        {value.map((tag) => (
          <Badge key={tag} size="sm">
            {tag}
            <button
              type="button"
              aria-label={`Remove ${tag}`}
              className="pl-1 text-muted hover:text-ink"
              onClick={(event) => {
                event.stopPropagation();
                onChange(value.filter((each) => each !== tag));
              }}
            >
              ✕
            </button>
          </Badge>
        ))}
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setOpen(true)}
          placeholder={value.length === 0 ? (placeholder ?? "Add a tag…") : ""}
          aria-label="Add a tag"
          className="min-w-24 flex-1 bg-transparent text-sm outline-none placeholder:text-muted"
        />
      </div>

      {failure && (
        <Alert.Root intent="danger" onDismiss={() => setFailure(null)}>
          <Alert.Title>{failure.title}</Alert.Title>
          <Alert.Description>{failure.message}</Alert.Description>
        </Alert.Root>
      )}

      {/* Outside the list, which closes on any press outside the box — and the
          dialog portals to the body, so a press inside it is one. Controlled,
          because its opener is a row in a listbox rather than a button the
          dialog could draw itself. */}
      <ConfirmDestroyDialog
        open={deleting !== null}
        onOpenChange={(next) => {
          if (!next) setDeleting(null);
        }}
        label="Delete"
        title={`Delete tag ${deleting?.name ?? ""}?`}
        summary={`It comes off ${carriers(deleting?.count ?? 0)}. Each one is rewritten; nothing else is touched.`}
        confirmWord={deleting?.name ?? ""}
        onConfirm={async () => {
          if (deleting) await remove(deleting.name);
        }}
      />

      {open && (
        <div
          role="listbox"
          aria-label="Tags"
          className="absolute top-full z-20 mt-1 flex max-h-72 w-full flex-col gap-1
                     overflow-auto rounded-md border border-line bg-card p-1 shadow-lg"
        >
          {offered.length === 0 && !isNew && (
            <EmptyState
              title={vocabulary.length === 0 ? "No tags yet." : "Every tag is already on this."}
              hint={vocabulary.length === 0 ? "Type one and press Enter." : undefined}
              className="px-2 py-1.5"
            />
          )}

          {offered.map((tag) => (
            <div key={tag.name} className="flex items-center gap-1">
              {renaming === tag.name ? (
                <div className="flex flex-1 items-center gap-1 px-1">
                  <Input
                    value={draft}
                    onValueChange={setDraft}
                    aria-label={`Rename ${tag.name}`}
                  />
                  <Button size="sm" disabled={busy} onClick={() => void rename(tag.name)}>
                    Save
                  </Button>
                </div>
              ) : (
                <>
                  <button
                    type="button"
                    role="option"
                    aria-selected={false}
                    onClick={() => add(tag.name)}
                    className="flex flex-1 items-center justify-between rounded px-2 py-1.5
                               text-left text-sm hover:bg-surface-alt"
                  >
                    <span>{tag.name}</span>
                    {/* The count, because it is what makes a rename or a delete
                        answerable before it is pressed. */}
                    <span className="pl-2 text-xs text-muted tabular-nums">{tag.count}</span>
                  </button>
                  {manage && (
                    <>
                      <button
                        type="button"
                        aria-label={`Rename tag ${tag.name}`}
                        disabled={busy}
                        onClick={() => {
                          setRenaming(tag.name);
                          setDraft(tag.name);
                        }}
                        className="rounded px-1.5 py-1 text-xs text-muted hover:bg-surface-alt"
                      >
                        Rename
                      </button>
                      <button
                        type="button"
                        aria-label={`Delete tag ${tag.name}`}
                        disabled={busy}
                        onClick={() => setDeleting(tag)}
                        className="rounded px-1.5 py-1 text-xs text-muted hover:bg-surface-alt"
                      >
                        Delete
                      </button>
                    </>
                  )}
                </>
              )}
            </div>
          ))}

          {isNew && (
            <button
              type="button"
              role="option"
              aria-selected={false}
              onClick={() => add(query)}
              className="rounded px-2 py-1.5 text-left text-sm hover:bg-surface-alt"
            >
              Create <Badge size="sm">{exact}</Badge>
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function describe(problem: unknown): string {
  return problem instanceof Error ? problem.message : String(problem);
}
