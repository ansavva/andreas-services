import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Tabs } from "@ansavva/design-system";

import { LoadError } from "../components/common/LoadError";
import { PageLoading } from "../components/common/PageLoading";
import { ApiError } from "../apis/client";
import { deleteCharacter, getCharacter, patchCharacter, setCharacterProfile } from "../apis/studio";
import { FolderTab } from "../components/browse/FolderTab";
import { PageBar } from "../components/layout/PageBar";
import { CharacterProjects, CharacterRuns } from "../components/character/CharacterWork";
import { ProfileForm } from "../components/character/ProfileForm";
import { useResource } from "../hooks/useResource";
import { CHARACTERS_PATH } from "../utils/location";
import type { CharacterIdentity, CharacterProfile, CharacterRecord } from "../types";
import { useSearchParamState } from "../hooks/useSearchParamState";
import { ConfirmDestroyDialog } from "../components/common/ConfirmDestroyDialog";

/**
 * One character: who they are, what they look like, and everything filed under
 * them.
 *
 * ## Four tabs, where there were seven
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
 * ## There is no Identity tab, and there should not be one
 *
 * There was: the References tab became `Identity`, which was Files with
 * `default` already typed into the tag filter. That is not a second kind of
 * thing — **identity is a tag on a file**, and a tab whose whole content is one
 * preset filter of the tab beside it is a second way of looking at the same
 * listing dressed as a place. The filter is in Files, where every other way of
 * narrowing the listing is, and it is one press from the same result.
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

  const [tab, setTab] = useSearchParamState("tab", "profile");
  /** The delete dialog, opened from the page bar's menu rather than drawn loose. */
  const [deleteOpen, setDeleteOpen] = useState(false);
  const load = useCallback(() => getCharacter(characterId), [characterId]);
  const character = useResource(["character", characterId], load);

  /**
   * The 409 message, as the API worded it.
   *
   * **A string rather than a boolean, because the API words it.** A 409 here is
   * a `rev` that moved under the write — names stopped being unique, so there
   * is no longer a second reason for one — and the page shows what the API said
   * rather than inventing its own sentence. The offered re-read is the fix.
   */
  const [conflict, setConflict] = useState<string | null>(null);

  const saveCharacter = useCallback(
    async (
      changes: { identity?: CharacterIdentity; profile?: CharacterProfile },
      rev: number,
    ) => {
      setConflict(null);
      try {
        // **Merged into what the page holds, never swapped in.** Both writes
        // answer with the stored record, which has neither `hero_url` nor the
        // `counts` a `GET` adds — see `EntityPatch`.
        let patch: Partial<CharacterRecord> = {};
        let at = rev;

        if (changes.identity) {
          patch = await patchCharacter(characterId, { rev: at, ...changes.identity });
          at = patch.rev ?? at;
        }
        if (changes.profile) {
          patch = { ...patch, ...(await setCharacterProfile(characterId, changes.profile, at)) };
        }

        character.setData((current) => (current ? { ...current, ...patch } : current));
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

  if (character.loading) return <PageLoading label="Loading character" />;

  if (character.error || !character.data) {
    return (
      <LoadError
        what="this character"
        message={character.error ?? "It may have been deleted."}
        onRetry={character.reload}
        escape={{ label: "Back to home", onClick: () => navigate("/") }}
      />
    );
  }

  const record = character.data;

  return (
    <>
      {/*
        Delete lives in the menu now, behind `⋯` — the button itself moved,
        the confirmation did not: it is still `ConfirmDestroyDialog`, still
        typing the name, just opened by a menu item instead of drawn loose
        beside the title.

        **No cascade here, and the noun says so.** Projects and runs that name
        this character hold link rows, and `force` drops those — but the runs
        themselves stay, because a run really did use this subject and deleting
        the character is not a reason to delete the work. The API refuses
        without `force`; the button always sends it, since a person who has read
        the armed label has answered that question.
      */}
      <PageBar
        crumbs={[{ label: "Characters", to: CHARACTERS_PATH }]}
        title={record.name}
        menu={[{ label: "Delete", danger: true, onSelect: () => setDeleteOpen(true) }]}
      />

      <ConfirmDestroyDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        label="Delete"
        title={`Delete ${record.name}?`}
        summary={
          "The character, its profile and its whole reference library go. " +
          "Runs that used it stay — a run really did use this subject, and " +
          "deleting the character is not a reason to delete the work."
        }
        confirmWord={record.name}
        onConfirm={async () => {
          await deleteCharacter(record.id, "delete", true);
          navigate(CHARACTERS_PATH);
        }}
      />

      {/* `defaultValue` as well as `value`, which the package requires even
          when controlled: it seeds `useControllableState`, and Tabs does not
          introspect its List to guess a first tab. */}
      <Tabs.Root value={tab} defaultValue="profile" onValueChange={setTab}>
        {/* Scrolls rather than wraps. Three labels fit a 390px screen and five
            do not, which is exactly why this was already written to scroll: a
            tab strip that grows a second row draws a second underline, and that
            reads as two strips. */}
        <Tabs.List className="overflow-x-auto border-b border-line">
          <Tabs.Tab value="profile">Profile</Tabs.Tab>
          <Tabs.Tab value="files">Files</Tabs.Tab>
          {/* The reverse questions. Both routes existed with no caller, so a
              character was a dead end: who it is, what it looks like, and
              nothing about the work it appears in. */}
          <Tabs.Tab value="runs">Runs</Tabs.Tab>
          <Tabs.Tab value="projects">Projects</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="profile">
          <ProfileForm
            // Remounted when the record changes revision, so a save that
            // succeeded leaves the form holding what the API returned rather
            // than a draft it has to be reconciled against.
            key={record.rev}
            identity={{ name: record.name }}
            profile={record.profile}
            rev={record.rev}
            onSave={saveCharacter}
            conflict={conflict}
            onReload={character.reload}
          />
        </Tabs.Panel>

        <Tabs.Panel value="runs">
          <CharacterRuns characterId={record.id} />
        </Tabs.Panel>

        <Tabs.Panel value="projects">
          <CharacterProjects characterId={record.id} />
        </Tabs.Panel>

        <Tabs.Panel value="files">
          {/* The raw browser at the character's root, with the root's own
              subfolders as chips above it: create, upload, rename, move, copy,
              delete, exactly as anywhere else. */}
          <FolderTab rootId={record.root} label={record.name} />
        </Tabs.Panel>
      </Tabs.Root>
    </>
  );
}

