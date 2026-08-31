import { useCallback, useState } from "react";

import { Alert, Button, Field, Input, Text } from "@ansavva/design-system";

import { ApiError } from "../../apis/client";
import { getCharacters, patchProject, setProjectCharacters } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import type { ProjectRecord } from "../../types";
import { AutoTextarea } from "../common/AutoTextarea";

interface Props {
  record: ProjectRecord;
  /**
   * The fields a write answered with, to MERGE — never a record to swap in.
   *
   * Neither route here returns one. `PATCH /projects` answers with the stored
   * record, which has no expanded `characters`; `PATCH /projects/characters`
   * answers with `{id, characters}` and nothing else. Replacing with either
   * dropped `counts` and crashed this page on `record.counts.runs`.
   */
  onSaved: (patch: Partial<ProjectRecord>) => void;
}

/**
 * A project's own fields, and who is in it.
 *
 * **The Overview tab was read-only.** A project's title and description could be
 * set at creation and never changed from the app, and involvement — which is
 * rows, and the thing that makes "which projects is this character in"
 * answerable — could not be edited at all. Both routes existed.
 *
 * Two writes, not one, because they are two different shapes: `PATCH /projects`
 * is a `rev`-guarded compare-and-swap on the record, and
 * `PATCH /projects/<id>/characters` replaces a set of link rows and takes no
 * revision. Chaining them the way the character page chains its two would be
 * inventing a conflict — the second cannot 409.
 *
 * Unlike the character page there is no draft to reconcile: these are two short
 * fields, so each save sends what is on screen and merges back whatever the
 * route answered with.
 */
export function ProjectDetails({ record, onSaved }: Props) {
  const [title, setTitle] = useState(record.title ?? "");
  const [description, setDescription] = useState(record.description ?? "");
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const dirty = title !== (record.title ?? "") || description !== (record.description ?? "");

  const save = useCallback(async () => {
    setBusy(true);
    setConflict(null);
    setError(null);
    try {
      onSaved(
        await patchProject(record.id, {
          rev: record.rev,
          title: title.trim(),
          description: description.trim(),
        }),
      );
    } catch (err) {
      // A 409 here is `rev` having moved, or a slug somebody took — this form
      // does not send a slug, so it is the first. The draft is kept either way.
      if (err instanceof ApiError && err.status === 409) setConflict(err.message);
      else setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }, [description, onSaved, record.id, record.rev, title]);

  return (
    <div className="flex flex-col gap-4">
      {conflict && (
        <Alert.Root intent="warning">
          <Alert.Title>This project moved under the edit</Alert.Title>
          <Alert.Description>{conflict}</Alert.Description>
        </Alert.Root>
      )}
      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not save</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      <Field.Root name="title">
        <Field.Label>Title</Field.Label>
        <Input value={title} onValueChange={setTitle} placeholder={record.slug} />
        <Field.Description>The slug is used when this is empty.</Field.Description>
      </Field.Root>

      <Field.Root name="description">
        <Field.Label>Description</Field.Label>
        <AutoTextarea
          value={description}
          onValueChange={setDescription}
          aria-label="Description"
          placeholder="What this project is."
        />
      </Field.Root>

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={!dirty || busy} onClick={() => void save()}>
          {busy ? "Saving…" : dirty ? "Save" : "Saved"}
        </Button>
        {dirty && (
          <Button
            intent="ghost"
            size="sm"
            onClick={() => {
              setTitle(record.title ?? "");
              setDescription(record.description ?? "");
            }}
          >
            Revert
          </Button>
        )}
        <Text variant="caption" tone="muted">
          revision {record.rev}
        </Text>
      </div>

      <Involvement record={record} onSaved={onSaved} />
    </div>
  );
}

/**
 * Who is in this project.
 *
 * **A whole-set replace, which is what the route takes.** There is no add and no
 * remove endpoint — `PATCH /characters` is given the list it should end up
 * with — so this sends the set on every press rather than pretending to be
 * incremental.
 *
 * A run records the characters it used independently of this, so removing
 * somebody here does not rewrite history: it says who the project is *about*,
 * which is the question "which projects involve this character" reads.
 */
function Involvement({ record, onSaved }: Props) {
  const { data } = useResource(["characters"], useCallback(() => getCharacters(), []));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const involved = new Set(record.characters.map((each) => each.id));

  const toggle = async (id: string) => {
    const next = new Set(involved);
    if (!next.delete(id)) next.add(id);
    setBusy(true);
    setError(null);
    try {
      // Merged, not refetched. The route answers in the shape a `GET` sends,
      // which it did not used to: it echoed the ids it was handed, so merging
      // put strings where this record holds objects and every chip read
      // unselected while the write had succeeded. A whole refetch of the
      // project was the workaround for that, and is no longer needed.
      const { characters } = await setProjectCharacters(record.id, [...next]);
      onSaved({ characters });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="flex flex-col gap-2 border-t border-line pt-4">
      <Text variant="title">Characters</Text>
      <Text variant="caption" tone="muted">
        Who this project is about. A run records the characters it used on its own,
        so this does not rewrite what has already been made.
      </Text>

      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not change who is involved</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      {(data ?? []).length === 0 ? (
        <Text variant="body" tone="muted">
          There are no characters in this library yet.
        </Text>
      ) : (
        <div className="flex flex-wrap gap-2">
          {(data ?? []).map((character) => {
            const on = involved.has(character.id);
            return (
              <button
                key={character.id}
                type="button"
                disabled={busy}
                aria-pressed={on}
                onClick={() => void toggle(character.id)}
                className={`rounded-none border px-3 py-1 font-body text-sm transition-colors
                            disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2
                            focus-visible:outline-primary ${
                              on
                                ? "border-primary bg-primary text-primary-text"
                                : "border-line text-muted hover:bg-surface-alt hover:text-ink"
                            }`}
              >
                {character.display_name || character.slug}
              </button>
            );
          })}
        </div>
      )}

    </section>
  );
}
