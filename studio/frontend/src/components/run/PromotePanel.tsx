import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Alert, Button, Field, Input, Select, Text, useToast } from "@ansavva/design-system";

import { ApiError } from "../../apis/client";
import { copyNodes, describeNode, getCharacter, getCharacters, getFolder } from "../../apis/studio";
import { DestinationPicker } from "../browse/DestinationPicker";
import { MediaThumb } from "../media/MediaThumb";
import { TagSelect } from "../common/TagSelect";
import { FolderIcon } from "../common/icons";
import { useResource } from "../../hooks/useResource";
import type { RunAsset } from "../../types";
import { assetLabel } from "../../utils/format";
import { characterPath, objectPath } from "../../utils/location";

/** What landed, once a copy has finished. */
interface Copied {
  /** The COPY — a new node, with a name the destination may have numbered. */
  copy: { id: string; name: string };
  /** Where it went, as a person would say it: `<character>/reference/face`. */
  where: string;
}

/**
 * The describe failed after the copy had already landed.
 *
 * **Carries where the copy is, because that is the only thing a person can act
 * on.** Nothing is rolled back: the bytes are real and deleting them on a
 * failure would be this component destroying media on its own initiative. So
 * the partial state is reported rather than swept — the file is in the folder
 * that was chosen, and it carries no tags yet.
 */
class DescribeFailed extends Error {
  constructor(
    message: string,
    readonly copy: { id: string; name: string },
    readonly where: string,
  ) {
    super(message);
    this.name = "DescribeFailed";
  }
}

/**
 * Copy one picture into a character's tree — **a real copy, then the tags.**
 *
 * **Nothing writes `default`.** It used to be put on every promotion, which
 * made one press mean two things: file this picture under a character, and
 * declare it part of that character's identity. Those are different decisions
 * — hard rule #2b says so — and identity is now a tag somebody types.
 *
 * **The copy is what ownership rests on.** A tag says nothing about whose image
 * it is; the character's branch is what answers that. So the run's output is
 * copied into a folder inside the character and the COPY is described. Two
 * blobs with independent lifetimes: the run keeps its own output, every record
 * citing it stays correct, and re-tagging or deleting the copy later cannot
 * reach back into the run.
 *
 * **The id described is the one the copy route answered with**, never the
 * source and never a name this could have guessed. A destination already
 * holding the name numbers it — `clip.mp4` lands as `clip (2).mp4` — and the
 * numbering is decided there, not here.
 *
 * **No folder is created and no tag is invented.** It used to make a
 * `reference/` pool if one was missing and write `default` on everything that
 * went through it, which is this app deciding both where a character's pictures
 * live and which of them are its identity. The folder is chosen and the tags
 * are typed.
 *
 * Exported so its ORDER is testable. Getting it wrong is not cosmetic: describing
 * the original would put a run's own output into a character's identity, which
 * is the exact thing the copy exists to avoid.
 */
export async function copyIntoCharacter({
  node,
  folder,
  where,
  description,
  tags,
}: {
  /** The picture being copied. */
  node: string;
  /** The destination folder's node id, chosen in the picker. */
  folder: string;
  /** That folder as a person would say it — for the messages, never for the write. */
  where: string;
  description?: string;
  tags?: string[];
}): Promise<Copied> {
  const copied = await copyNodes([node], folder);
  const made = copied.nodes[0];
  if (!made) throw new Error("the copy reported nothing — nothing was described");
  const copy = { id: made.id, name: made.name };

  const written = [...new Set(tags ?? [])].filter(Boolean);
  if (written.length === 0 && !description) return { copy, where };

  try {
    await describeNode(copy.id, {
      ...(written.length > 0 ? { tags: written } : {}),
      ...(description ? { description } : {}),
    });
  } catch (err) {
    throw new DescribeFailed((err as ApiError).message, copy, where);
  }

  return { copy, where };
}

/**
 * Copy a run's output into a character, inline.
 *
 * **This was `Promote`, and the word was doing too much.** It copied into a
 * `reference/` pool the app created, tagged the copy `default`, and asked for a
 * "group" — a word with no meaning left in the entity model, since a group was
 * neither a folder nor a schema field but a tag with a special name. What a
 * person actually wants is the two plain things underneath all that: put this
 * picture in a folder of this character, and label it. So: a character, a
 * folder chosen by browsing the character's own tree, and tags.
 *
 * **Hard rule #2b is better served by it, not worse.** Identity is the
 * `default` tag; that tag is now something a person types rather than something
 * a press implies, so nothing becomes a character's identity without somebody
 * saying so in as many words.
 *
 * **It is the body of a right-hand `Drawer`.** The form is read against the
 * picture it is about — is this worth keeping under this character — so the
 * output has to stay on screen while it is filled in.
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
   * Whether anything has been chosen or typed here, reported up so Escape can
   * decline.
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
  const toast = useToast();

  const loadCharacters = useCallback(() => getCharacters(), []);
  const characters = useResource(["characters"], loadCharacters);

  /**
   * The run's own characters first, then everyone else, each half by name.
   *
   * A run records who it was of, so the character being copied into is almost
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
   * Two is a choice this cannot make — an image of two people belongs to
   * whichever the person says — and preselecting the first would be a guess
   * wearing the shape of an answer.
   */
  const sole = runCharacters.length === 1 ? runCharacters[0] : null;
  const character =
    chosen ?? (sole && offered.some((each) => each.id === sole) ? sole : null);
  const name = offered.find((each) => each.id === character)?.name ?? "";

  /** The character's root, which is where the folder picker opens. */
  const loadRoot = useCallback(
    () =>
      character
        ? getCharacter(character).then(async (record) => {
            const tree = await getFolder({ node: record.root }, "name");
            return { id: record.root, prefix: tree.prefix ?? "" };
          })
        : Promise.reject(new Error("no character")),
    [character],
  );
  const root = useResource(character ? ["character-root", character] : null, character ? loadRoot : null);

  const [folder, setFolder] = useState<{ id: string; where: string } | null>(null);
  const [picking, setPicking] = useState(false);
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState<string[]>([]);

  // A folder inside one character means nothing inside another.
  useEffect(() => setFolder(null), [character]);

  // The character is not counted: it is preselected for most runs, so it is not
  // something a person typed and losing it costs nothing.
  const dirty = folder !== null || description.trim() !== "" || tags.length > 0;
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
  const [failure, setFailure] = useState<{ title: string; body: string } | null>(null);
  const [done, setDone] = useState<Copied | null>(null);

  /**
   * What the chosen folder is called, said from the character down.
   *
   * A folder's own `prefix` is the whole name path from the library root, and
   * an entity's root folder is named after its id — so the raw prefix reads
   * `characters/char-57399438-…/reference`. The character's name is what the
   * reader knows it by, so the root's prefix is cut off the front and the
   * name put in its place, the way the Files tab's boundary crumb does it.
   */
  const label = useCallback(
    (prefix: string, rootPrefix: string, characterName: string) => {
      const rest = prefix.startsWith(rootPrefix) ? prefix.slice(rootPrefix.length) : prefix;
      return `${characterName}${rest}`.replace(/\/$/, "");
    },
    [],
  );

  const pick = useCallback(
    async (destination: string) => {
      const tree = await getFolder({ node: destination }, "name");
      setFolder({
        id: destination,
        where: label(tree.prefix ?? "", root.data?.prefix ?? "", name || "the character"),
      });
      setPicking(false);
    },
    [label, name, root.data?.prefix],
  );

  async function copy() {
    if (!folder) return;
    setBusy(true);
    setFailure(null);
    try {
      const result = await copyIntoCharacter({
        node: asset.node,
        folder: folder.id,
        where: folder.where,
        description: description.trim(),
        tags,
      });
      setDone(result);
      // The alert below carries the link; the toast is for the reader who has
      // already scrolled back to the outputs.
      toast.add({
        intent: "success",
        title: "Copied",
        description: `“${result.copy.name}” is in ${result.where}.`,
      });
    } catch (err) {
      if (err instanceof DescribeFailed) {
        // The one failure that leaves something behind. Say where, in the words
        // a person would use to go and find it.
        setFailure({
          title: "Copied, but the tags did not save",
          body:
            `${err.message} The picture is in ${err.where} as “${err.copy.name}” ` +
            `and carries no tags yet — add them there, or delete it. This run's ` +
            `own copy is fine.`,
        });
      } else {
        setFailure({ title: "Could not copy the picture", body: (err as Error).message });
      }
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <section className="flex flex-col gap-2 border border-line bg-card p-3">
        <Alert.Root intent="success">
          <Alert.Title>Copied into {done.where}</Alert.Title>
          <Alert.Description>
            <span>
              It is there as “{done.copy.name}”
              {tags.length > 0 ? `, tagged ${tags.join(", ")}` : ", untagged"}. This
              run still has its own copy.{" "}
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
              Open {name || "the character"}
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
    <section className="flex flex-col gap-3 border-line bg-card p-3">
      <Text variant="title">
        {name ? `Copy into ${name}` : "Copy into a character"}
      </Text>

      {/* **A click outside does not throw typed words away.** The drawer asks
          to close, this form declines while it holds anything, and the choice
          is put where the words are rather than in a second dialog over the
          top of them. */}
      {unsavedWarning && (
        <Alert.Root intent="warning">
          <Alert.Title>Leave without copying it?</Alert.Title>
          <Alert.Description>
            <span className="flex flex-col gap-2">
              <span>What you have filled in here would be lost.</span>
              <span className="flex flex-wrap gap-2">
                <Button intent="secondary" size="sm" onClick={onKeepEditing}>
                  Keep editing
                </Button>
                {/* No `danger` intent exists — the package ships three
                    weights and says so. The Alert around it is what carries
                    the warning; this is just the choice inside it. */}
                <Button intent="secondary" size="sm" onClick={onDiscard}>
                  Leave without saving
                </Button>
              </span>
            </span>
          </Alert.Description>
        </Alert.Root>
      )}

      {/* **The picture, and no prose.** A form deciding where a picture should
          be kept is unanswerable without seeing it, and the run behind the
          drawer is dimmed by the backdrop — so the thumb stays. The sentences
          that used to sit around it do not: four labelled fields and a button
          that says Copy are the whole of what this does, and a paragraph
          explaining each one reads as an apology for a form that needs none.

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
          className="w-28"
          title="Open this picture in a new tab"
        />
      </a>

      {failure && (
        <Alert.Root intent="danger">
          <Alert.Title>{failure.title}</Alert.Title>
          <Alert.Description>{failure.body}</Alert.Description>
        </Alert.Root>
      )}

      {/* `items-start`: one rule for every row of this form, so a helper
          sentence hangs under the field it describes instead of pushing its
          label up. */}
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-56 flex-1">
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

        <div className="min-w-56 flex-1">
          <Field.Root name="promote-folder">
            <Field.Label>Folder</Field.Label>
            {/* **Browsed, not typed or listed.** A character's folders are its
                own — `reference`, `seed`, whatever somebody made — so a menu
                here would be this app naming them again, and a text box would
                be a name to get wrong. It is the picker the browser already
                moves and copies with, opened at this character's root. */}
            <Button
              intent="secondary"
              disabled={!character || root.loading}
              onClick={() => setPicking(true)}
              className="w-full justify-start gap-2 font-normal"
            >
              <FolderIcon className="size-4 shrink-0 fill-none stroke-current stroke-[1.5]" />
              <span className="truncate">
                {folder ? folder.where : root.loading ? "Loading…" : "Choose a folder…"}
              </span>
            </Button>
          </Field.Root>
        </div>
      </div>

      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-56 flex-1">
          <Field.Root name="promote-description">
            <Field.Label>Description</Field.Label>
            <Input
              value={description}
              onValueChange={setDescription}
              placeholder="Optional — what the image shows"
            />
          </Field.Root>
        </div>

        <div className="min-w-56 flex-1">
          <Field.Root name="promote-tags">
            <Field.Label>Tags</Field.Label>
            <TagSelect scope="file" value={tags} onChange={setTags} />
          </Field.Root>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button disabled={!character || !folder || busy} onClick={() => void copy()}>
          {busy ? "Copying…" : "Copy"}
        </Button>
        <Button intent="secondary" disabled={busy} onClick={onClose}>
          Cancel
        </Button>
      </div>

      {picking && root.data && (
        <DestinationPicker
          verb="copy"
          noun={assetLabel(asset.name)}
          startId={root.data.id}
          currentId={root.data.id}
          // The root folder is named after the character's id; this is what the
          // reader knows it by. See `rootLabel`.
          rootLabel={name || undefined}
          onSubmit={pick}
          onClose={() => setPicking(false)}
        />
      )}
    </section>
  );
}
