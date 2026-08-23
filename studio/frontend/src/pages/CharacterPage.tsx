import { useCallback, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Button, Field, Input, Spinner, Switch, Tabs, Text } from "@ansavva/design-system";

import { ApiError } from "../apis/client";
import {
  deleteCharacter,
  getCharacter,
  getTree,
  patchCharacter,
  putCharacterProfile,
} from "../apis/studio";
import { FolderTab } from "../components/browse/FolderBrowser";
import { ProfileForm } from "../components/character/ProfileForm";
import { ReferencesGrid } from "../components/character/ReferencesGrid";
import { AppHeader } from "../components/common/AppHeader";
import { ConfirmDeleteButton } from "../components/common/ConfirmDeleteButton";
import { useResource } from "../hooks/useResource";
import type { CharacterProfile } from "../types";

/**
 * One character: who they are, what they look like, and everything filed under
 * them.
 *
 * ## The tabs after References are built from the tree, not from a list here
 *
 * A character starts with `reference/`, `corpus/`, `seed/` and `archive/`,
 * created because an empty character is unhelpful — and **nothing afterwards
 * requires any of them**. They can be renamed, moved or deleted, and a folder
 * somebody makes by hand is not second-class. So the tabs are the root's
 * children as the listing reports them, and a fixed list would be exactly the
 * rigidity the entity model removed. See ENTITY_MODEL.md, "the folder layout is
 * convention, not schema".
 *
 * That includes `reference/` itself, and its tab is not a duplicate of the
 * References one: **the References tab is the row index and the folder tab is
 * the folder.** An image is identity because a `REF#` row says so, not because
 * of where it sits, so the two can and do disagree — an image in `reference/`
 * that nobody attached is exactly the state worth being able to see.
 *
 * ## Two records, two revisions
 *
 * The identity fields and the bible are both on the character record and both
 * write with `rev`, but they are separate saves: renaming is one write that
 * moves no bytes, and a bible edit is a whole-document replace. Mixing them
 * would make a rename wait on a form nobody had finished filling in.
 */
export function CharacterPage() {
  const { characterId = "" } = useParams();
  const navigate = useNavigate();

  const load = useCallback(() => getCharacter(characterId), [characterId]);
  const character = useResource(load);

  const root = character.data?.root ?? null;
  const loadRoot = useCallback(
    () => (root === null ? Promise.reject(new Error("no root")) : getTree({ node: root }, "name")),
    [root],
  );
  const tree = useResource(root === null ? null : loadRoot);

  const [staleProfile, setStaleProfile] = useState(false);

  const saveProfile = useCallback(
    async (profile: CharacterProfile, rev: number) => {
      setStaleProfile(false);
      try {
        const updated = await putCharacterProfile(characterId, profile, rev);
        character.setData(updated);
      } catch (err) {
        // A 409 here is not a failure to write — it is a refusal to overwrite
        // somebody else's write, which is the whole reason `rev` exists. The
        // draft is kept and the page offers a re-read.
        if (err instanceof ApiError && err.status === 409) setStaleProfile(true);
        throw err;
      }
    },
    [character, characterId],
  );

  const folders = useMemo(() => tree.data?.folders ?? [], [tree.data]);

  if (character.loading) {
    return (
      <Shell>
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading character" />
        </div>
      </Shell>
    );
  }

  if (character.error || !character.data) {
    return (
      <Shell>
        <Alert.Root intent="danger">
          <Alert.Title>Could not open this character</Alert.Title>
          <Alert.Description>{character.error ?? "It may have been deleted."}</Alert.Description>
        </Alert.Root>
        <div>
          <Button size="sm" onClick={() => navigate("/")}>
            Back to home
          </Button>
        </div>
      </Shell>
    );
  }

  const record = character.data;

  return (
    <Shell subtitle={record.slug}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Text variant="display">{record.display_name}</Text>
        <Text variant="caption" tone="muted">
          {record.slug}
        </Text>
        {/* The consent question, unchanged in meaning and now a real field
            rather than a key in a document nobody could query. */}
        <Badge intent={record.fictional ? "neutral" : "warning"}>
          {record.fictional ? "fictional" : "real person"}
        </Badge>

        {/* **No cascade here, and the noun says so.** Projects and runs that
            name this character hold link rows, and `force` drops those — but
            the runs themselves stay, because a run really did use this subject
            and deleting the character is not a reason to delete the work. The
            API refuses without `force`; the button always sends it, since a
            person who has read the armed label has answered that question. */}
        <span className="ms-auto">
          <ConfirmDeleteButton
            tone="page"
            noun={`character ${record.slug} and its reference library`}
            onConfirm={async () => {
              await deleteCharacter(record.id, "delete", true);
              navigate("/");
            }}
          />
        </span>
      </div>

      <Tabs.Root defaultValue="profile">
        <Tabs.List className="flex-wrap border-b border-line">
          <Tabs.Tab value="profile">Profile</Tabs.Tab>
          <Tabs.Tab value="references">References</Tabs.Tab>
          {folders.map((folder) => (
            <Tabs.Tab key={folder.id} value={`folder:${folder.id}`}>
              {folder.name}
            </Tabs.Tab>
          ))}
          <Tabs.Tab value="files">Files</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="profile" className="flex flex-col gap-6">
          <IdentityFields
            characterId={record.id}
            slug={record.slug}
            displayName={record.display_name}
            fictional={record.fictional}
            rev={record.rev}
            onSaved={character.reload}
          />
          <ProfileForm
            // Remounted when the record changes revision, so a save that
            // succeeded leaves the form holding what the API returned rather
            // than a draft it has to be reconciled against.
            key={record.rev}
            profile={record.profile}
            rev={record.rev}
            onSave={saveProfile}
            staleRev={staleProfile}
            onReload={character.reload}
          />
        </Tabs.Panel>

        <Tabs.Panel value="references">
          <ReferencesGrid characterId={record.id} defaultSet={record.default_set} />
        </Tabs.Panel>

        {folders.map((folder) => (
          <Tabs.Panel key={folder.id} value={`folder:${folder.id}`}>
            <FolderTab rootId={folder.id} />
          </Tabs.Panel>
        ))}

        <Tabs.Panel value="files">
          {/* The raw browser at the character's root: create, upload, rename,
              move, copy, delete, exactly as anywhere else. */}
          <FolderTab rootId={record.root} />
        </Tabs.Panel>
      </Tabs.Root>
    </Shell>
  );
}

/**
 * Slug, display name and the consent flag — the three fields promoted out of the
 * bible onto the record.
 *
 * **Renaming here moves nothing.** No object is copied, no run document is
 * rewritten, and every reference, binding and default-set entry keeps pointing at
 * the same node ids: the slug is a label on one row, and the root folder's name
 * changes in the same transaction. It was a sweep over four pools plus a rewrite
 * pass over every run that cited the old path.
 */
function IdentityFields({
  characterId,
  slug,
  displayName,
  fictional,
  rev,
  onSaved,
}: {
  characterId: string;
  slug: string;
  displayName: string;
  fictional: boolean;
  rev: number;
  onSaved: () => void;
}) {
  const [nextSlug, setNextSlug] = useState(slug);
  const [nextName, setNextName] = useState(displayName);
  const [nextFictional, setNextFictional] = useState(fictional);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);

  const dirty = nextSlug !== slug || nextName !== displayName || nextFictional !== fictional;

  const save = useCallback(() => {
    setBusy(true);
    setError(null);
    setConflict(false);
    patchCharacter(characterId, {
      rev,
      slug: nextSlug,
      display_name: nextName,
      fictional: nextFictional,
    })
      .then(() => onSaved())
      // 409 covers both refusals this route makes — a taken slug and a stale
      // `rev` — so the message is the API's rather than a guess at which.
      .catch((err: Error) => {
        if (err instanceof ApiError && err.status === 409) setConflict(true);
        setError(err.message);
      })
      .finally(() => setBusy(false));
  }, [characterId, nextFictional, nextName, nextSlug, onSaved, rev]);

  return (
    <section className="flex flex-col gap-3 rounded-md border border-line bg-card p-3">
      <Text variant="title">Identity</Text>

      {error && (
        <Alert.Root intent={conflict ? "warning" : "danger"}>
          <Alert.Title>{conflict ? "That did not go through" : "Could not save"}</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      <Field.Root name="slug">
        <Field.Label>Slug</Field.Label>
        <Input value={nextSlug} onValueChange={setNextSlug} />
        <Field.Description>
          Library-unique, and the address a person types. Changing it copies no objects.
        </Field.Description>
      </Field.Root>

      <Field.Root name="display_name">
        <Field.Label>Display name</Field.Label>
        <Input value={nextName} onValueChange={setNextName} />
      </Field.Root>

      {/* Not a `<label>` — `Switch.Root` is a `<button>`, which is not labelable. */}
      <div className="flex items-center gap-3">
        <Switch.Root
          checked={nextFictional}
          aria-label="Fictional"
          onCheckedChange={setNextFictional}
        >
          <Switch.Thumb />
        </Switch.Root>
        <Text variant="body">Fictional</Text>
      </div>

      <div className="flex items-center gap-2">
        <Button size="sm" disabled={!dirty || busy} onClick={save}>
          {busy ? "Saving…" : "Save identity"}
        </Button>
        <Text variant="caption" tone="muted" className="tabular-nums">
          revision {rev}
        </Text>
      </div>
    </section>
  );
}

function Shell({ children, subtitle }: { children: React.ReactNode; subtitle?: string }) {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-6 p-4 sm:p-6">
      <AppHeader subtitle={subtitle ?? "character"} />
      {children}
    </div>
  );
}
