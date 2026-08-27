import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Button, Spinner, Tabs, Text } from "@ansavva/design-system";

import { ApiError } from "../apis/client";
import { deleteCharacter, getCharacter, patchCharacter, putCharacterProfile } from "../apis/studio";
import { FolderTab } from "../components/browse/FolderBrowser";
import { PageBar } from "../components/layout/PageBar";
import { ProfileForm } from "../components/character/ProfileForm";
import { ReferencesGrid } from "../components/character/ReferencesGrid";
import { ConfirmDeleteButton } from "../components/common/ConfirmDeleteButton";
import { useResource } from "../hooks/useResource";
import { CHARACTERS_PATH } from "../utils/location";
import type { CharacterIdentity, CharacterProfile } from "../types";

/**
 * One character: who they are, what they look like, and everything filed under
 * them.
 *
 * ## Three tabs, where there were seven
 *
 * The root's children — `reference/`, `corpus/`, `seed/`, `archive/` and
 * anything made by hand — each used to get a tab beside Profile and References.
 * The reasoning was sound and the result was not: nothing requires any of those
 * folders, so a fixed list would have been exactly the rigidity the entity model
 * removed (ENTITY_MODEL.md, "the folder layout is convention, not schema") — but
 * building the strip from the listing made *navigation out of data*. It grew and
 * shrank as folders came and went, every folder tab showed what Files already
 * held, and at 390px the seven of them wrapped into three rows of underline.
 *
 * The folders are shortcut chips at the top of Files now. `FolderTab` builds
 * them from the same listing, so nothing about the convention hardened.
 *
 * ## The `reference/` folder and the References tab were never the same thing
 *
 * **References is the row index; `reference/` is a folder.** An image is
 * identity because a `REF#` row says so, not because of where it sits, so the
 * two can and do disagree — and that disagreement is worth seeing. It used to be
 * shown as two adjacent tabs called `References` and `reference`, which is the
 * worst available way to say it: the reader had to diff two listings by eye to
 * find the interesting case. `ReferencesGrid` names the state instead.
 *
 * ## Two writes, one button
 *
 * The identity fields and the bible are both on the character record and both
 * write with `rev`, and they are still two routes: renaming is one write that
 * moves no bytes, a bible edit is a whole-document replace. That split is right
 * and it is not a person's problem — it used to surface as a Save on the
 * identity card and a second Save on the form under it, each with its own
 * "revision N" beside it, both showing the same number.
 *
 * They cannot go in parallel. Both are compare-and-swap on the same row, so the
 * identity write bumps `rev` and a profile write carrying the number read before
 * it comes back 409 — a conflict the page invented for itself. So `saveCharacter`
 * chains: patch identity, take `rev` off what came back, put the profile with
 * that.
 */
export function CharacterPage() {
  const { characterId = "" } = useParams();
  const navigate = useNavigate();

  const load = useCallback(() => getCharacter(characterId), [characterId]);
  const character = useResource(load);

  /**
   * The 409 message, as the API worded it.
   *
   * **A boolean would be a lie here.** This route refuses with 409 for two
   * unrelated reasons — a slug somebody else has taken, and a `rev` that moved
   * under the write — and nothing in the response distinguishes them. So the
   * page shows what the API said rather than guessing, and offers a re-read,
   * which is the right next move for either: harmless against a taken slug and
   * the whole fix for a stale record.
   */
  const [conflict, setConflict] = useState<string | null>(null);

  const saveCharacter = useCallback(
    async (
      changes: { identity?: CharacterIdentity; profile?: CharacterProfile },
      rev: number,
    ) => {
      setConflict(null);
      try {
        let record = character.data;
        let at = rev;

        if (changes.identity) {
          record = await patchCharacter(characterId, { rev: at, ...changes.identity });
          at = record.rev;
        }
        if (changes.profile) {
          record = await putCharacterProfile(characterId, changes.profile, at);
        }

        if (record) character.setData(record);
      } catch (err) {
        // A 409 is not a failure to write — it is a refusal to overwrite
        // somebody else's write, which is the whole reason `rev` exists. The
        // draft is kept and the form offers a re-read.
        if (err instanceof ApiError && err.status === 409) setConflict(err.message);
        throw err;
      }
    },
    [character, characterId],
  );

  if (character.loading) {
    return (
      <>
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading character" />
        </div>
      </>
    );
  }

  if (character.error || !character.data) {
    return (
      <>
        <Alert.Root intent="danger">
          <Alert.Title>Could not open this character</Alert.Title>
          <Alert.Description>{character.error ?? "It may have been deleted."}</Alert.Description>
        </Alert.Root>
        <div>
          <Button size="sm" onClick={() => navigate("/")}>
            Back to home
          </Button>
        </div>
      </>
    );
  }

  const record = character.data;

  return (
    <>
      {/*
        The two-group layout this page argued for is `PageBar` now, and the
        argument is unchanged — it just holds for every page instead of this one.

        `ms-auto` pins a control to the right of whatever *line* it lands on,
        and on a phone that line is whichever one the flex run happened to break
        at — so the destructive control moved around under the title depending on
        how long the name was. Two children and `justify-between` give it one
        place on a wide screen and one place on a narrow one: beside the title,
        or on its own line beneath it.

        **No cascade here, and the noun says so.** Projects and runs that name
        this character hold link rows, and `force` drops those — but the runs
        themselves stay, because a run really did use this subject and deleting
        the character is not a reason to delete the work. The API refuses
        without `force`; the button always sends it, since a person who has read
        the armed label has answered that question.
      */}
      <PageBar
        crumbs={[{ label: "Characters", to: CHARACTERS_PATH }]}
        actions={
          <ConfirmDeleteButton
            tone="page"
            noun={`character ${record.slug} and its reference library`}
            onConfirm={async () => {
              await deleteCharacter(record.id, "delete", true);
              navigate(CHARACTERS_PATH);
            }}
          />
        }
      >
        <Text variant="display">{record.display_name}</Text>
        <Text variant="caption" tone="muted">
          {record.slug}
        </Text>
        {/* The consent question, unchanged in meaning and now a real field
            rather than a key in a document nobody could query. */}
        <Badge intent={record.fictional ? "neutral" : "warning"}>
          {record.fictional ? "fictional" : "real person"}
        </Badge>
      </PageBar>

      <Tabs.Root defaultValue="profile">
        {/* Scrolls rather than wraps. Three labels fit a 390px screen with room
            to spare, and the rule holds anyway: a tab strip that grows a second
            row draws a second underline, which reads as two strips. */}
        <Tabs.List className="overflow-x-auto border-b border-line">
          <Tabs.Tab value="profile">Profile</Tabs.Tab>
          <Tabs.Tab value="references">References</Tabs.Tab>
          <Tabs.Tab value="files">Files</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="profile">
          <ProfileForm
            // Remounted when the record changes revision, so a save that
            // succeeded leaves the form holding what the API returned rather
            // than a draft it has to be reconciled against.
            key={record.rev}
            identity={{
              slug: record.slug,
              display_name: record.display_name,
              fictional: record.fictional,
            }}
            profile={record.profile}
            rev={record.rev}
            onSave={saveCharacter}
            conflict={conflict}
            onReload={character.reload}
          />
        </Tabs.Panel>

        <Tabs.Panel value="references">
          <ReferencesGrid
            characterId={record.id}
            rootId={record.root}
            defaultSet={record.default_set}
          />
        </Tabs.Panel>

        <Tabs.Panel value="files">
          {/* The raw browser at the character's root, with the root's own
              subfolders as chips above it: create, upload, rename, move, copy,
              delete, exactly as anywhere else. */}
          <FolderTab rootId={record.root} />
        </Tabs.Panel>
      </Tabs.Root>
    </>
  );
}

