import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { Button, Input, Text } from "@ansavva/design-system";

import { AutoTextarea } from "../common/AutoTextarea";
import type { FileEntry } from "../../types";

interface Props {
  file: FileEntry;
  onSave: (changes: { description?: string | null; tags?: string[] | null }) => Promise<unknown>;
  onClose: () => void;
  /**
   * Fields about this node in some *other* thing's terms, above the file's own.
   *
   * A reference's group, order and caption are facts about the picture's role in
   * a character, not about the file — the same image is a plain file everywhere
   * else. They share this panel rather than getting a second one because one
   * button and one surface is the whole point of the viewer rework; they are
   * kept above and separated so nothing reads as belonging to the file.
   */
  extra?: ReactNode;
}

/**
 * What the picture shows, and how it is selected — edited where you are looking
 * at it.
 *
 * **The object screen is the right place for this and the grid is not.** You
 * decide what a frame is of while it is large in front of you, not from a
 * thumbnail — the same argument `ObjectActions` makes for putting rename and
 * delete on that screen rather than on a tile.
 *
 * **It is a panel now, not a bottom sheet.** It used to be
 * `absolute inset-x-0 bottom-0 max-h-[60%]` over the reel, covering the
 * transport on purpose, because there was no page underneath to occupy — the
 * viewer was a full-viewport takeover. On a page it takes the column beside the
 * player, in place of the read-only `ObjectDetails` it is the editor for, and
 * nothing has to be covered for it to be readable.
 *
 * ## Tags are free-form, and the input is the whole vocabulary
 *
 * There is no list to pick from because there is no list: a tag is whatever
 * somebody typed, and `--pick-tag` has worked that way since before any of this
 * was a row. What the API does is FOLD them — trimmed, lower-cased,
 * de-duplicated — so `Poolside` and `poolside ` cannot become two selectors that
 * look identical in a chip and return different sets.
 *
 * That folding is why this renders what came back from the save rather than what
 * was typed. Showing the typed form would be a display that disagrees with the
 * selector it just created.
 *
 * The existing tags on the file are offered as suggestions from the other
 * pictures on screen — see `known` — which is a convenience and not a
 * constraint: anything typed is accepted.
 *
 * ## Saving
 *
 * Description saves on an explicit press, not on blur. Blur-to-save inside an
 * overlay that also closes on Escape is how an edit gets committed by the
 * gesture meant to abandon it. Tags save the moment one is added or removed,
 * because a chip with an unsaved state is a control that lies about what a
 * `--pick-tag` would now match.
 */
export function DescribePanel({ file, onSave, onClose, extra }: Props) {
  const [draft, setDraft] = useState(file.description ?? "");
  const [tag, setTag] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tagInput = useRef<HTMLInputElement>(null);

  const tags = useMemo(() => file.tags ?? [], [file.tags]);

  // Stepping to another file must not leave the previous one's caption sitting
  // in the field — the same reset `RenameDialog` performs, and for the same
  // reason.
  useEffect(() => {
    setDraft(file.description ?? "");
    setTag("");
    setError(null);
  }, [file.id, file.description]);

  const save = useCallback(
    async (changes: { description?: string | null; tags?: string[] | null }) => {
      setBusy(true);
      setError(null);
      try {
        await onSave(changes);
      } catch (failure) {
        setError(failure instanceof Error ? failure.message : "Could not save");
      } finally {
        setBusy(false);
      }
    },
    [onSave],
  );

  const addTag = useCallback(async () => {
    const wanted = tag.trim();
    if (!wanted) return;
    setTag("");
    // Trimmed here because the empty check needs it anyway; the CASE is left to
    // the API, which folds and answers with the folded list. That answer is what
    // this renders, so a duplicate the fold catches disappears rather than
    // appearing twice.
    await save({ tags: [...tags, wanted] });
    tagInput.current?.focus();
  }, [save, tag, tags]);

  const dirty = draft.trim() !== (file.description ?? "").trim();

  return (
    <section
      className="border-t border-line pt-3 lg:border-t-0 lg:pt-0"
      aria-label="File details"
    >
      <div className="flex flex-col gap-4">
        {/* Only the Hide control at the top. The sentence that used to sit here
            said "both are the file's own", which stopped being true the moment
            this panel could carry an entity's fields above them — a reference's
            group and caption belong to a CHARACTER, not to the file. It moved
            down to sit directly over the two things it describes. */}
        <div className="flex items-start justify-end">
          <Button intent="ghost" size="sm" onClick={onClose} className="shrink-0">
            Hide
          </Button>
        </div>

        {extra}

        <div className="flex flex-col gap-2">
          <Text variant="caption" tone="muted">
            What this shows, and how it is selected. Both are the file&apos;s own —
            they travel with it through a move, a rename and a copy.
          </Text>
          <Text variant="caption" tone="muted">
            Description
          </Text>
          <AutoTextarea
            value={draft}
            onValueChange={setDraft}
            placeholder="Shirtless at the pool, whistle on a cord, palms behind."
            aria-label="Description"
          />
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              disabled={!dirty || busy}
              onClick={() => void save({ description: draft.trim() || null })}
            >
              {busy ? "Saving…" : "Save description"}
            </Button>
            {dirty && (
              <Button
                intent="ghost"
                size="sm"
                onClick={() => setDraft(file.description ?? "")}
              >
                Discard
              </Button>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <Text variant="caption" tone="muted">
            Tags
          </Text>
          <div className="flex flex-wrap items-center gap-2">
            {tags.map((each) => (
              <span
                key={each}
                className="flex items-center gap-1 rounded-xs bg-neutral-a3 py-1 ps-2 pe-1
                           font-mono text-xs text-ink"
              >
                {each}
                <button
                  type="button"
                  aria-label={`Remove ${each}`}
                  disabled={busy}
                  className="rounded-xs px-1.5 text-muted hover:bg-neutral-a5 hover:text-ink"
                  onClick={() =>
                    void save({ tags: tags.filter((keep) => keep !== each) })
                  }
                >
                  ×
                </button>
              </span>
            ))}
            {tags.length === 0 && (
              <Text variant="caption" tone="muted">
                No tags yet.
              </Text>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Input
              ref={tagInput}
              value={tag}
              onValueChange={setTag}
              placeholder="Add a tag…"
              aria-label="Add a tag"
              // Enter adds rather than submitting anything: this panel is not a
              // form, and the page behind it binds single keys.
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void addTag();
                }
                // Stopped here so typing a tag with an `m` or an `f` in it does
                // not mute the clip or go fullscreen behind the panel.
                // `useKeyboardNav` ignores INPUT targets as well; this is the
                // belt to that braces, and it costs one line.
                event.stopPropagation();
              }}
            />
            <Button size="sm" disabled={!tag.trim() || busy} onClick={() => void addTag()}>
              Add
            </Button>
          </div>
        </div>

        {error && (
          <Text variant="caption" className="text-danger">
            {error}
          </Text>
        )}
      </div>
    </section>
  );
}
