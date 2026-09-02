import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Alert, Button, Field, Input, Select, Text } from "@ansavva/design-system";

import { ApiError } from "../../apis/client";
import {
  copyNodes,
  createNode,
  describeNode,
  getCharacter,
  getCharacters,
  getFolder,
  listNodes,
} from "../../apis/studio";
import { MediaThumb } from "../media/MediaThumb";
import { TagSelect } from "../common/TagSelect";
import { useResource } from "../../hooks/useResource";
import type { RunAsset } from "../../types";
import { characterPath, objectPath } from "../../utils/location";

/**
 * The tag that makes an image one the character SENDS.
 *
 * The whole of what a `REF#` row and a `default_set` entry used to say between
 * them, on the picture. A promotion writes it, because promoting is precisely
 * the act of deciding this image is identity.
 */
export const DEFAULT_TAG = "default";

/**
 * A group left unnamed. Kept as a word rather than as "no tag at all" so a
 * promotion nobody classified is still findable, and one `describe` away from
 * wherever it belongs.
 */
export const UNSORTED = "unsorted";

/**
 * The groups a character conventionally has, offered alongside its real ones.
 *
 * A suggestion list and never a menu — a group is an ordinary tag, so any word
 * is legal and the API validates none of these. They are here because a first
 * promotion into a fresh character has no existing tags to offer, and "face" is
 * what it almost always wants.
 */
export const CONVENTIONAL_GROUPS = ["face", "body", "frame", "wardrobe"];

/** The pool folder a character's references live under. `REFERENCE_POOL`. */
const REFERENCE_POOL = "reference";

/** What landed, once a promotion has finished. */
export interface Promoted {
  /** The COPY — a new node, with a name the destination may have numbered. */
  copy: { id: string; name: string };
  group: string;
  /**
   * The attach answered 409: this node is already a reference.
   *
   * Not an error. The CLI says "left alone" and carries on for the same reason
   * — the state asked for is the state that holds.
   */
  already: boolean;
}

/**
 * The attach failed after the copy had already landed.
 *
 * **Carries where the copy is, because that is the only thing a person can act
 * on.** Nothing is rolled back: the bytes are real and deleting them on a
 * failure would be this component destroying media on its own initiative. So
 * the partial state is reported rather than swept, exactly as the CLI tolerates
 * it — the file is in the character's folder and is not yet identity.
 */
export class AttachFailed extends Error {
  constructor(
    message: string,
    readonly copy: { id: string; name: string },
    readonly group: string,
  ) {
    super(message);
    this.name = "AttachFailed";
  }
}

/** One folder's immediate child folders, by name. */
async function childFolder(parent: string, name: string): Promise<string | null> {
  const tree = await getFolder({ node: parent }, "name");
  return tree.folders.find((folder) => folder.name === name)?.id ?? null;
}

/**
 * The named child folder, created if it is absent.
 *
 * `store.ensure_child_folder`'s shape, in the app: idempotent by construction,
 * and a 409 means something else created it between the listing and the create
 * — so the node it made is the right answer, and re-listing is how this finds
 * it. Not a retry loop; one round, because there is only one thing the conflict
 * can be.
 */
async function ensureFolder(parent: string, name: string): Promise<string> {
  const found = await childFolder(parent, name);
  if (found) return found;
  try {
    return (await createNode(parent, name, "folder")).id;
  } catch (err) {
    if ((err as ApiError).status !== 409) throw err;
    const raced = await childFolder(parent, name);
    if (!raced) throw err;
    return raced;
  }
}

/**
 * Promote one image into a character's identity — **a real copy, then a tag.**
 *
 * **The copy is not optional, and it is what ownership now rests on.** A `REF#`
 * row could name a node anywhere in the library, so attaching a run's own output
 * was possible; a tag says nothing about whose image it is, and the character's
 * branch is what answers that. So the run's output is copied into the
 * character's `reference/` folder and the COPY is tagged. Two blobs with
 * independent lifetimes: the run keeps its own output, every record citing it
 * stays correct, and untagging or deleting the promoted image later cannot reach
 * back into the run.
 *
 * **The id tagged is the one the copy route answered with**, never the source and
 * never a name this could have guessed. A destination already holding the name
 * numbers it — `clip.mp4` lands as `clip (2).mp4` — and the numbering is decided
 * there, not here.
 *
 * **The group is a tag, not a folder.** It used to be both — a `<group>/`
 * subfolder and a column on the row — which is two places for one fact and the
 * shape this whole change removes. The copy lands in `reference/` and the group
 * rides along beside `default`.
 *
 * Exported so its ORDER is testable. Getting it wrong is not cosmetic: tagging
 * the original would make the run's own output the character's identity, which
 * is the exact thing the copy exists to avoid.
 */
export async function promoteToReference({
  character,
  node,
  group,
  description,
  tags,
}: {
  character: string;
  node: string;
  group: string;
  description?: string;
  tags?: string[];
}): Promise<Promoted> {
  const record = await getCharacter(character);
  const pool = await ensureFolder(record.root, REFERENCE_POOL);

  const copied = await copyNodes([node], pool);
  const made = copied.nodes[0];
  if (!made) throw new Error("the copy reported nothing — nothing was tagged");
  const copy = { id: made.id, name: made.name };

  // `default` first, then the group, then anything typed. De-duplicated because
  // somebody typing `face` in the tags box as well should not produce it twice.
  const written = [...new Set([DEFAULT_TAG, group, ...(tags ?? [])])].filter(Boolean);

  try {
    await describeNode(copy.id, {
      tags: written,
      ...(description ? { description } : {}),
    });
  } catch (err) {
    const error = err as ApiError;
    throw new AttachFailed(error.message, copy, group);
  }

  return { copy, group, already: false };
}

/**
 * Promote a run's output into a character's reference library, inline.
 *
 * **Hard rule #2b is what this panel is shaped by.** A character's references
 * are who it IS, and adding one is a separate decision from having paid to
 * render something — which is why a generated image never arrives in a
 * character on its own. In the app the person's press IS that approval, so
 * there is no second confirm; what the rule buys instead is that the panel
 * states plainly what pressing will do, so nobody discovers afterwards that
 * they filed an image as identity.
 *
 * **It is the body of a right-hand `Drawer`**, and this used to say it expanded
 * under the outputs. The form is read against the picture it is about — is this
 * the face to file as identity — so the output has to stay on screen while it
 * is filled in; an expando pushed the grid around to make room and put the form
 * below the thing it described.
 *
 * Studio deleted two drawers before this one and neither argument reaches a
 * form: both held MEDIA — a reference thumbnail too small to judge, and a frame
 * viewer that needed an address and fullscreen. What this holds is four fields.
 */
export function PromotePanel({
  asset,
  runCharacters,
  onClose,
  onDirtyChange,
  unsavedWarning,
  onDiscard,
  onKeepEditing,
}: {
  asset: RunAsset;
  /** The character ids this run recorded. Offered first — usually the answer. */
  runCharacters: string[];
  onClose: () => void;
  /**
   * Whether anything has been typed here, reported up so Escape can decline.
   *
   * The panel owns the fields, and the key handler lives with whatever owns
   * "which panel is open" — so the one that knows has to tell the one that
   * acts. Without it a stray Escape discards a written description silently.
   */
  onDirtyChange?: (dirty: boolean) => void;
  /** A dismissal was refused because this form has words in it. */
  unsavedWarning?: boolean;
  /** Throw the words away and close. */
  onDiscard?: () => void;
  /** Stay, and put the warning away. */
  onKeepEditing?: () => void;
}) {
  const navigate = useNavigate();
  const datalistId = useId();

  const loadCharacters = useCallback(() => getCharacters(), []);
  const characters = useResource(["characters"], loadCharacters);

  /**
   * The run's own characters first, then everyone else, each half by name.
   *
   * A run records who it was of, so the character being promoted into is almost
   * always one of them — and on a library of forty, scrolling past thirty-nine
   * to reach the obvious one is the whole difference between this and the CLI,
   * where the name is typed.
   */
  const offered = useMemo(() => {
    const all = characters.data ?? [];
    const own = new Set(runCharacters);
    const by = (a: { name: string }, b: { name: string }) =>
      a.name.localeCompare(b.name);
    return [
      ...all.filter((each) => own.has(each.id)).sort(by),
      ...all.filter((each) => !own.has(each.id)).sort(by),
    ];
  }, [characters.data, runCharacters]);

  const [chosen, setChosen] = useState<string | null>(null);
  /**
   * Preselected only when the run names exactly ONE character.
   *
   * Two is a choice this cannot make — an image of two people is a reference of
   * whichever the person says — and preselecting the first would be a guess
   * wearing the shape of an answer.
   */
  const sole = runCharacters.length === 1 ? runCharacters[0] : null;
  const character =
    chosen ?? (sole && offered.some((each) => each.id === sole) ? sole : null);

  const [group, setGroup] = useState(UNSORTED);
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState<string[]>([]);

  // The character is not counted: it is preselected for most runs, so it is
  // not something a person typed and losing it costs nothing.
  const dirty =
    group !== UNSORTED || description.trim() !== "" || tags.length > 0;
  /**
   * Reported through a ref, and depending on `dirty` ALONE.
   *
   * The caller passes an inline arrow, so its identity changes on every render
   * — and with it in the dependency list the effect tore down and re-ran every
   * time, firing its own cleanup. The cleanup says "nothing typed here", which
   * put the dismissal warning away one render after the dismissal raised it:
   * clicking outside a filled form appeared to do nothing at all.
   */
  const notifyDirty = useRef(onDirtyChange);
  useEffect(() => {
    notifyDirty.current = onDirtyChange;
  });
  useEffect(() => {
    notifyDirty.current?.(dirty);
    return () => notifyDirty.current?.(false);
  }, [dirty]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ title: string; body: string } | null>(
    null,
  );
  const [done, setDone] = useState<Promoted | null>(null);

  // **The character's real tags, off the listing's own facet.** There is no
  // reference index to read groups out of; what the character actually uses is
  // whatever its images carry, which every listing already counts. Asked only
  // once a character is chosen — before that there is nobody whose tags these
  // would be.
  const loadTags = useCallback(
    () =>
      character
        ? getCharacter(character).then((record) =>
            listNodes({ node: record.root }, { depth: "all", kind: ["image"] }),
          )
        : Promise.reject(new Error("none")),
    [character],
  );
  const inUse = useResource(
    character ? ["character-tags", character] : null,
    character ? loadTags : null,
  );

  const groups = useMemo(() => {
    // `default` is not offered: it is what a promotion writes, not a group to
    // choose, and putting it in the list would invite somebody to pick it twice.
    const existing = Object.keys(inUse.data?.tags ?? {}).filter(
      (tag) => tag !== DEFAULT_TAG,
    );
    return [...new Set([...existing, ...CONVENTIONAL_GROUPS, UNSORTED])].sort();
  }, [inUse.data]);

  const name = offered.find((each) => each.id === character)?.name ?? "";
  const target = group.trim() || UNSORTED;

  async function promote() {
    if (!character) return;
    setBusy(true);
    setFailure(null);
    try {
      setDone(
        await promoteToReference({
          character,
          node: asset.node,
          group: target,
          description: description.trim(),
          tags,
        }),
      );
    } catch (err) {
      if (err instanceof AttachFailed) {
        // The one failure that leaves something behind. Say where, in the words
        // a person would use to go and find it.
        setFailure({
          title: "The picture was copied, but it is not a reference yet",
          // The one failure that leaves something behind, so this is the one
          // message that names a folder: the reader has to go and find it.
          body:
            `${err.message} You will find it as “${err.copy.name}” in ` +
            `${name || "the character"}'s reference/${err.group}/ folder — ` +
            `add it from there, or delete it. This run's own copy is fine.`,
        });
      } else {
        setFailure({
          title: "Nothing was added",
          body: (err as Error).message,
        });
      }
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <section className="flex flex-col gap-2 rounded-none border border-line bg-card p-3">
        <Alert.Root intent="success">
          <Alert.Title>
            {done.already
              ? "That picture is already a reference"
              : `Added to ${name || "the character"}'s references`}
          </Alert.Title>
          <Alert.Description>
            <span>
              It is in the {done.group} group, and shots of{" "}
              {name || "this character"} will be matched against it from now on.
              This run still has its own copy.{" "}
            </span>
            {/* A real `<a href>`: command-click belongs to the browser, which is
                the same bargain `OutputPanel`'s caption makes. */}
            <a
              href={character ? characterPath(character) : "#"}
              onClick={(event) => {
                if (
                  event.metaKey ||
                  event.ctrlKey ||
                  event.shiftKey ||
                  event.altKey ||
                  !character
                )
                  return;
                event.preventDefault();
                navigate(characterPath(character));
              }}
              className="text-sm text-accent underline underline-offset-2 hover:opacity-80"
            >
              Open {name || "the character"}'s references
            </a>
          </Alert.Description>
        </Alert.Root>
        <div>
          <Button intent="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-3 rounded-none border-line bg-card p-3">
      <Text variant="title">
        {name ? `Add to ${name}'s references` : "Add to a character's references"}
      </Text>

      {/* **A click outside does not throw typed words away.** The drawer asks
          to close, this form declines while it holds anything, and the choice
          is put where the words are rather than in a second dialog over the
          top of them. */}
      {unsavedWarning && (
        <Alert.Root intent="warning">
          <Alert.Title>Leave without adding it?</Alert.Title>
          <Alert.Description>
            <span className="flex flex-col gap-2">
              <span>What you have filled in here would be lost.</span>
              <span className="flex flex-wrap gap-2">
                <Button intent="secondary" onClick={onKeepEditing}>
                  Keep editing
                </Button>
                {/* No `danger` intent exists — the package ships three
                    weights and says so. The Alert around it is what carries
                    the warning; this is just the choice inside it. */}
                <Button intent="secondary" onClick={onDiscard}>
                  Discard
                </Button>
              </span>
            </span>
          </Alert.Description>
        </Alert.Root>
      )}

      {/* **The sentence hard rule #2b asks for, said in the reader's terms.**
          It used to describe the mechanism — a copy into a `reference/<group>/`
          folder, "marks the copy as identity", "two files, two lifetimes" —
          which is what the code does, not what the person is deciding. What
          they are deciding is whether this picture is one of the ones every
          later shot should look like. The reassurance stays, because "will
          this move my output" is a real question; it just stops being told in
          paths and lifetimes. */}
      {/* **The picture, next to the words about it.** A form deciding whether
          an image should be one of the ones a character is matched against is
          unanswerable without seeing it, and the run behind the drawer is
          dimmed by the backdrop.

          Small, and a real `<a target="_blank">`: at this size it is a
          reminder rather than something to judge on, so the way to look
          properly is a full page of its own — in a new tab, because the form
          in front of it is half filled in and navigating would lose it. */}
      <Text variant="body" className="max-w-prose">
        References are the pictures studio works from to keep{" "}
        {name || "this character"} looking the same in everything you make.
        Adding “{asset.name}” puts it in that set.
      </Text>

      {/* **The picture, under the words about it.** A form deciding whether an
          image should be one of the ones a character is matched against is
          unanswerable without seeing it, and the run behind the drawer is
          dimmed by the backdrop.

          `contain`, never `cover`: this is the thing being judged, and filling
          a square box crops the edges off anything that is not one — which on
          a portrait frame took the head off. `OutputPanel` makes the same
          choice for the same reason.

          A real `<a target="_blank">`, because at this size it is a reminder
          rather than something to decide on, and the form in front of it is
          half filled in — navigating away would lose it. */}
      <a
        href={objectPath(asset.node)}
        target="_blank"
        rel="noreferrer"
        className="self-start focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        <MediaThumb
          nodeId={asset.node}
          url={asset.url}
          name={asset.name}
          aspect="square"
          fit="contain"
          className="w-28 rounded-none"
          title="Open this picture in a new tab"
        />
      </a>

      {failure && (
        <Alert.Root intent="danger">
          <Alert.Title>{failure.title}</Alert.Title>
          <Alert.Description>{failure.body}</Alert.Description>
        </Alert.Root>
      )}

      {/* `items-start`, as below — one rule for both rows of this form. */}
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-56">
          <Field.Root name="promote-character">
            <Field.Label>Character</Field.Label>
            <Select
              options={offered.map((each) => ({
                value: each.id,
                label: each.name,
              }))}
              value={character}
              placeholder={
                characters.loading ? "Loading characters…" : "Choose a character"
              }
              disabled={characters.loading || offered.length === 0}
              onValueChange={setChosen}
            />
          </Field.Root>
        </div>

        <div className="min-w-48">
          <Field.Root name="promote-group">
            <Field.Label>Group</Field.Label>
            {/* An Input with a datalist, not a Select: the group is a free
                attribute on the row and any word is legal, so a closed menu
                would be this app inventing a vocabulary the API does not
                have. The list is a shortcut past typing, never a constraint. */}
            <Input
              value={group}
              onValueChange={setGroup}
              list={datalistId}
              placeholder={UNSORTED}
            />
            <datalist id={datalistId}>
              {groups.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
            {/* The field had no explanation at all, and "group" says nothing
                on its own to anyone who has not read the CLI. */}
            <Field.Description>
              What this picture is good for — a face, a full body, an outfit.
              Sorting them this way is how a few of the right ones get chosen
              for a shot instead of all of them.
            </Field.Description>
          </Field.Root>
        </div>
      </div>

      {/* **`items-start`, now that every control in the row is the same
          height.** Bottom-aligned, a cell carrying a `Field.Description` rode
          up by the height of the sentence and took its label with it. Aligning
          tops instead puts every label on one line and every control on the
          next, and lets a helper sentence hang under the field it describes —
          which is where it has to be, or it reads as a note about the row. */}
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-56 flex-1">
          <Field.Root name="promote-description">
            <Field.Label>Description</Field.Label>
            <Input
              value={description}
              onValueChange={setDescription}
              placeholder="Optional — what the image shows"
            />
            {/* The CLI's own warning, said before the fact rather than after —
                and in terms of what it costs the reader, not of tags and sets. */}
            <Field.Description>
              Say what the picture shows. Once a character has a lot of
              references, this is how the right one gets found; without it this
              one tends to be passed over.
            </Field.Description>
          </Field.Root>
        </div>

        <div className="min-w-48 flex-1">
          <Field.Root name="promote-tags">
            <Field.Label>Tags</Field.Label>
            <Field.Description>
              What the copy shows. Picked from the tags this library already uses.
            </Field.Description>
            <TagSelect scope="file" value={tags} onChange={setTags} />
          </Field.Root>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          disabled={!character || busy}
          onClick={() => void promote()}
        >
          {busy ? "Adding…" : "Add reference"}
        </Button>
        <Button intent="secondary" disabled={busy} onClick={onClose}>
          Cancel
        </Button>
      </div>
    </section>
  );
}
