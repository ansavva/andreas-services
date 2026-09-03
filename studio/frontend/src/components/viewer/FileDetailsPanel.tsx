import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { Alert, Button, Input, Text } from "@ansavva/design-system";

import { AutoTextarea } from "../common/AutoTextarea";
import { FormBar, useSavedFlash } from "../common/FormBar";
import { TagSelect } from "../common/TagSelect";
import type { FileEntry } from "../../types";

interface Props {
  file: FileEntry;
  /** Writes the file's own description and tags. */
  onSave: (changes: { description?: string | null; tags?: string[] | null }) => Promise<unknown>;
  /** Writes the file's name. A rejection keeps the panel open with the reason. */
  onRename: (name: string) => Promise<unknown>;
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
  /**
   * Whether anything has been typed here, reported up so a dismissal can decline.
   *
   * The panel owns the fields and the drawer owns "is it open", so the one that
   * knows has to tell the one that acts. `PromotePanel` carries the same pair
   * for the same reason.
   */
  onDirtyChange?: (dirty: boolean) => void;
  /** A dismissal was refused because this form holds unsaved words. */
  unsavedWarning?: boolean;
  /** Leave without saving: the words go, and the drawer closes. */
  onDiscard?: () => void;
  /** Stay, and put the warning away. */
  onKeepEditing?: () => void;
}

/**
 * Everything the file itself says about itself — its name, what it shows, and
 * how it is selected — edited where you are looking at it.
 *
 * **The object screen is the right place for this and the grid is not.** You
 * decide what a frame is of while it is large in front of you, not from a
 * thumbnail — the same argument `ObjectActions` makes for putting rename and
 * delete on that screen rather than on a tile.
 *
 * **This used to be `DescribePanel`, and rename used to be a dialog beside it.**
 * Two controls in one action row opened two surfaces that edited three fields of
 * one row: a toggle that took over the column, and a popup over the top of it.
 * Nothing distinguished them to a reader — "describe" and "rename" are both
 * "change what this file says about itself" — so they are one drawer with the
 * name at the top, and the popup is gone.
 *
 * It has been three shapes now, and each move answered the last one's problem.
 * A bottom sheet over the reel covered the transport, because the viewer was a
 * full-viewport takeover with no page underneath. A panel in the column beside
 * the player fixed that and created a second one: the column is also where the
 * file's read-only details live, so opening the editor *replaced* the thing it
 * edits. A drawer leaves the page as it was and lays the form over it.
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
 * ## Saving
 *
 * The name and the description save together on an explicit press, not on blur.
 * Blur-to-save inside a surface that also closes on Escape is how an edit gets
 * committed by the gesture meant to abandon it. Tags save the moment one is
 * added or removed, because a chip with an unsaved state is a control that lies
 * about what a `--pick-tag` would now match.
 *
 * **One press, but only the half that moved is written.** A name is a different
 * route from a description — `PATCH /nodes/<id>/name` against
 * `PATCH /nodes/<id>` — so a press that renames nothing must not issue a rename,
 * and a press that renamed something must not re-write a description nobody
 * touched. `RunPlanEditor` splits the plan from its sends on exactly this rule.
 */
export function FileDetailsPanel({
  file,
  onSave,
  onRename,
  onClose,
  extra,
  onDirtyChange,
  unsavedWarning,
  onDiscard,
  onKeepEditing,
}: Props) {
  const [name, setName] = useState(file.name);
  const [draft, setDraft] = useState(file.description ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * What the server is believed to hold: the file as it arrived, and then
   * whatever a save committed.
   *
   * Compared against instead of the prop, because the reload that carries a
   * write back is a round trip — without this the form reads as dirty for a beat
   * after a successful save, and a dismissal landing in that beat is refused
   * over words that are already stored.
   */
  const [saved, setSaved] = useState({
    name: file.name,
    description: file.description ?? "",
  });

  const tags = useMemo(() => file.tags ?? [], [file.tags]);
  // Tags have no Save to go grey, so the field itself says a write landed.
  const [tagsSaved, flashTagsSaved] = useSavedFlash();

  /**
   * Stepping to another file must not leave the previous one's name or caption
   * sitting in a field. The page also keys this panel per file, so this is the
   * belt to that braces.
   *
   * **Guarded on the id, and that guard is load-bearing.** A save reloads the
   * feed, so the same file arrives back with a new name or description — and a
   * reset that fired on those would overwrite whatever the OTHER field still
   * held unsaved. Renaming into a taken name would have thrown away the
   * description typed beside it, on the way to reporting the 409.
   */
  const shown = useRef(file.id);
  useEffect(() => {
    if (shown.current === file.id) return;
    shown.current = file.id;
    setName(file.name);
    setDraft(file.description ?? "");
    setSaved({ name: file.name, description: file.description ?? "" });
    setError(null);
  }, [file.id, file.name, file.description]);

  const saveTags = useCallback(
    async (next: string[]) => {
      setBusy(true);
      setError(null);
      try {
        await onSave({ tags: next });
        flashTagsSaved();
      } catch (failure) {
        setError(failure instanceof Error ? failure.message : "Could not save");
      } finally {
        setBusy(false);
      }
    },
    [flashTagsSaved, onSave],
  );

  const wantedName = name.trim();
  const renaming = wantedName !== "" && wantedName !== saved.name;
  const describing = draft.trim() !== saved.description.trim();
  const dirty = renaming || describing;

  /**
   * Reported through a ref, and depending on `dirty` ALONE.
   *
   * The caller passes an inline arrow, so its identity changes on every render —
   * and with it in the dependency list the effect tore down and re-ran every
   * time, firing its own cleanup. The cleanup says "nothing typed here", which
   * put the dismissal warning away one render after the dismissal raised it:
   * clicking outside a filled form appeared to do nothing at all. `PromotePanel`
   * paid for this once already.
   */
  const notifyDirty = useRef(onDirtyChange);
  useEffect(() => {
    notifyDirty.current = onDirtyChange;
  });
  useEffect(() => {
    notifyDirty.current?.(dirty);
    return () => notifyDirty.current?.(false);
  }, [dirty]);

  /**
   * The name first, then the description — and each half re-baselines the
   * moment it lands.
   *
   * They are two writes and either can fail on its own. The name goes first
   * because its failure is the one a person fixes by typing — 409, that name is
   * taken — and stopping there leaves the description in the field, still
   * unsaved, rather than reported as an error about something else. Recording
   * each success as it happens is what makes pressing Save again re-issue only
   * what is still outstanding, instead of renaming a file to the name it
   * already has.
   */
  const commit = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      if (renaming) {
        await onRename(wantedName);
        setSaved((was) => ({ ...was, name: wantedName }));
      }
      if (describing) {
        const next = draft.trim();
        await onSave({ description: next || null });
        setSaved((was) => ({ ...was, description: next }));
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }, [describing, draft, onRename, onSave, renaming, wantedName]);

  return (
    <section className="flex flex-col gap-4" aria-label="Edit file details">
      <div className="flex items-start justify-between gap-2">
        <Text variant="title">File details</Text>
        <Button intent="secondary" size="sm" onClick={onClose} className="shrink-0">
          Close
        </Button>
      </div>

      {/* **A click outside does not throw typed words away.** The drawer asks to
          close, this form declines while it holds anything unsaved, and the
          choice is put where the words are rather than in a second dialog over
          the top of them. `PromotePanel` says the same thing the same way. */}
      {unsavedWarning && (
        <Alert.Root intent="warning">
          <Alert.Title>Leave without saving?</Alert.Title>
          <Alert.Description>
            <span className="flex flex-col gap-2">
              <span>The name and description you typed would be lost.</span>
              <span className="flex flex-wrap gap-2">
                <Button intent="secondary" size="sm" onClick={onKeepEditing}>
                  Keep editing
                </Button>
                {/* No `danger` intent exists on Button — the package ships three
                    weights and says so. The Alert around it carries the warning;
                    this is only the choice inside it. Says "leave", not
                    "discard": the row below has a Revert, and a second word for
                    throwing words away would read as a second way to do it. */}
                <Button intent="secondary" size="sm" onClick={onDiscard}>
                  Leave without saving
                </Button>
              </span>
            </span>
          </Alert.Description>
        </Alert.Root>
      )}

      {extra}

      <div className="flex flex-col gap-2">
        {/* Labelled the way the two fields under it are — a caption over the
            control and an `aria-label` on it — rather than through `Field`. One
            panel, one way of naming a field. */}
        <Text variant="caption" tone="muted">
          Name
        </Text>
        <Input
          value={name}
          onValueChange={setName}
          placeholder={file.name}
          aria-label="Name"
          // Enter saves, and stops there: this panel is not a form, and the page
          // behind it binds single keys — an `m` or an `f` typed into a filename
          // would otherwise mute the clip or go fullscreen.
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              if (dirty && !busy) void commit();
            }
            event.stopPropagation();
          }}
        />

        <Text variant="caption" tone="muted">
          Description
        </Text>
        <AutoTextarea
          value={draft}
          onValueChange={setDraft}
          placeholder="Shirtless at the pool, whistle on a cord, palms behind."
          aria-label="Description"
        />
        <FormBar
          dirty={dirty}
          saving={busy}
          onSave={() => void commit()}
          onRevert={() => {
            setName(saved.name);
            setDraft(saved.description);
          }}
          error={error}
        />
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Text variant="caption" tone="muted">
            Tags
          </Text>
          {tagsSaved && (
            <Text variant="caption" tone="muted" family="mono">
              Saved
            </Text>
          )}
        </div>
        {/*
          **The vocabulary, not a text box.** This was a free-text input with an
          Add button, so the words already on other files were invisible while
          typing one — and a vocabulary nobody can see is one everybody spells
          differently. `three-quarter` on Monday and `three quarter` on Tuesday
          are two tags, and a filter that finds one finds none of the other.

          Every change saves immediately, as the box did: this panel is not a
          form and has no submit.
        */}
        <TagSelect scope="file" value={tags} onChange={(next) => void saveTags(next)} manage />
      </div>
    </section>
  );
}
