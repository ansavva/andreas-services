import { Fragment, useCallback, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Alert, Button, Text } from "@ansavva/design-system";

import {
  getLocations,
  getProject,
  getRun,
  setRunCharacters,
  setRunLocations,
} from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import type { HeroImage, RunFeedRow } from "../../types";
import {
  CharacterChipToggle,
  LocationChipToggle,
  LocationTag,
} from "../character/CharacterChip";
import { CheckIcon, PencilIcon } from "../common/icons";
import { CastTags } from "../project/RunFeed";

const GLYPH = "size-3.5 fill-none stroke-current stroke-[1.5]";

/**
 * Who a run is about and where it was shot — two rows of the rail's facts,
 * each with a pencil.
 *
 * **Both could only be set when the run was made.** `PATCH /api/runs` has taken
 * `characters` since the cast became edges and `locations` since locations
 * existed, and the client had both calls; the editor that once called the
 * first (`RunCast`) fell out of the tree in the shell rewrite and nothing was
 * ever mounted for the second. So a run made without its cast could not be
 * given one — and a prompt cites its cast by POSITION, so `@character.1.top`
 * had nothing to fill from — and a run shot somewhere could not say so after
 * the fact.
 *
 * ## Offered from the PROJECT's
 *
 * A run is about somebody the project is about and shot somewhere the project
 * is shot — the same sets the create bar offers a new run (`castOf`,
 * `locationsOf`). Anything already on the run is offered too, so it can be
 * taken off even when the project no longer lists it.
 *
 * ## Order is the payload, for the cast
 *
 * `@character.1.…` is the first of these and `[Image1]` counts the same way,
 * so the chips show their position and pressing one appends rather than
 * inserting. Locations carry no position.
 *
 * ## Re-read, never merge
 *
 * `cast` is DERIVED — the record's own `characters` when it has any, else the
 * owners of what the run binds — so patching `characters` into a row in hand
 * would leave `cast` where it was. The write is followed by `GET /runs/<id>`
 * into the run's own key and an invalidation of every feed, which is what the
 * lightbox draws the row from.
 */
export function RunSubjects({
  row,
  heroes,
}: {
  row: RunFeedRow;
  heroes: Record<string, HeroImage | null>;
}) {
  const client = useQueryClient();
  const project = useResource(
    ["project", row.project],
    useCallback(() => getProject(row.project), [row.project]),
  );
  const locations = useResource(["locations"], useCallback(() => getLocations(), []));
  const locationById = new Map((locations.data ?? []).map((each) => [each.id, each]));

  const saved = useCallback(async () => {
    client.setQueryData(["run", row.id], await getRun(row.id));
    await client.invalidateQueries({ queryKey: ["runs"] });
  }, [client, row.id]);

  // What the run NAMES, not `cast`: the cast is derived, and falls back to
  // the owners of the bound images when the run names nobody — so it is what
  // the read row shows, and the wrong thing to toggle, since taking the last
  // name off would leave every chip lit.
  const cast = row.characters;
  const offeredCast = withCurrent(project.data?.characters ?? [], cast, (id) => ({
    id,
    name: row.cast.find((each) => each.id === id)?.name ?? "deleted character",
  }));

  const shotIn = row.locations ?? [];
  const offeredLocations = withCurrent(project.data?.locations ?? [], shotIn, (id) => ({
    id,
    name: locationById.get(id)?.name ?? "deleted location",
  }));

  return (
    <>
      <SubjectRow
        label={row.cast.length === 1 ? "Character" : "Characters"}
        editLabel="Edit characters"
        errorTitle="Could not change the cast"
        value={cast}
        ordered
        offered={offeredCast}
        empty="nobody named"
        note={
          cast.length === 0 && row.cast.length > 0
            ? "Names nobody — the cast is read off the images it binds."
            : undefined
        }
        write={(next) => setRunCharacters(row.id, next)}
        onSaved={saved}
        tags={row.cast.length > 0 ? <CastTags cast={row.cast} heroes={heroes} /> : null}
        chip={(each, pressed, disabled, onClick) => (
          <CharacterChipToggle
            key={each.id}
            name={each.name}
            hero={heroes[each.id] ?? null}
            pressed={pressed}
            disabled={disabled}
            onClick={onClick}
          />
        )}
      />
      <SubjectRow
        label={shotIn.length === 1 ? "Location" : "Locations"}
        editLabel="Edit locations"
        errorTitle="Could not change the locations"
        value={shotIn}
        offered={offeredLocations}
        empty="nowhere named"
        write={(next) => setRunLocations(row.id, next)}
        onSaved={saved}
        tags={
          shotIn.length > 0
            ? shotIn.map((id) => (
                <LocationTag
                  key={id}
                  id={id}
                  name={locationById.get(id)?.name ?? "deleted location"}
                  hero={locationById.get(id)?.hero ?? null}
                />
              ))
            : null
        }
        chip={(each, pressed, disabled, onClick) => (
          <LocationChipToggle
            key={each.id}
            name={each.name}
            hero={locationById.get(each.id)?.hero ?? null}
            pressed={pressed}
            disabled={disabled}
            onClick={onClick}
          />
        )}
      />
    </>
  );
}

/** The project's list, plus whatever the run names that the project does not. */
function withCurrent<T extends { id: string }>(
  offered: ReadonlyArray<T>,
  current: ReadonlyArray<string>,
  make: (id: string) => T,
): T[] {
  const seen = new Set(offered.map((each) => each.id));
  return [...offered, ...current.filter((id) => !seen.has(id)).map(make)];
}

interface RowProps<T extends { id: string; name: string }> {
  label: string;
  editLabel: string;
  errorTitle: string;
  /** What the run names now, in the order it names them. */
  value: string[];
  /** Position matters — the chips are numbered and a press appends. */
  ordered?: boolean;
  offered: T[];
  /** What the row reads when the run names nothing. */
  empty: string;
  /** A line under the chips while editing, for what the value alone does not say. */
  note?: string;
  write: (next: string[]) => Promise<unknown>;
  onSaved: () => Promise<void>;
  /** The row as read — the same tags the feed row draws; null when there are none. */
  tags: ReactNode | null;
  chip: (each: T, pressed: boolean, disabled: boolean, onClick: () => void) => ReactNode;
}

/**
 * One `<dt>`/`<dd>` pair of the rail's `<dl>`: the tags and a pencil, or the
 * chips and a tick while editing. Every press writes — a whole-set replace,
 * which is what the route takes — so there is no draft to keep or revert.
 */
function SubjectRow<T extends { id: string; name: string }>({
  label,
  editLabel,
  errorTitle,
  value,
  ordered = false,
  offered,
  empty,
  note,
  write,
  onSaved,
  tags,
  chip,
}: RowProps<T>) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = async (id: string) => {
    const at = value.indexOf(id);
    const next = at >= 0 ? value.filter((each) => each !== id) : [...value, id];
    setBusy(true);
    setError(null);
    try {
      await write(next);
      await onSaved();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Fragment>
      <dt className="flex items-start pt-0.5">
        <Text as="span" variant="caption" tone="muted">
          {label}
        </Text>
      </dt>
      <dd className="flex min-w-0 flex-col gap-1.5">
        <span className="flex flex-wrap items-center gap-1.5">
          {editing ? (
            offered.length === 0 ? (
              <Text variant="caption" tone="muted">
                The project names none. Add them on its Overview tab first.
              </Text>
            ) : (
              offered.map((each) => {
                const at = value.indexOf(each.id);
                const node = chip(each, at >= 0, busy, () => void toggle(each.id));
                return ordered && at >= 0 ? (
                  <span key={each.id} className="inline-flex items-center gap-1">
                    <Text as="span" variant="caption" family="mono" tone="muted">
                      {at + 1}.
                    </Text>
                    {node}
                  </span>
                ) : (
                  node
                );
              })
            )
          ) : tags !== null ? (
            tags
          ) : (
            <Text as="span" variant="caption" tone="muted">
              {empty}
            </Text>
          )}
          <Button
            intent="ghost"
            size="sm"
            aria-label={editing ? "Done" : editLabel}
            disabled={busy}
            onClick={() => setEditing((open) => !open)}
            className="h-6 min-h-0 px-1.5"
          >
            {editing ? <CheckIcon className={GLYPH} /> : <PencilIcon className={GLYPH} />}
          </Button>
        </span>
        {editing && note && (
          <Text variant="caption" tone="muted">
            {note}
          </Text>
        )}
        {error && (
          <Alert.Root intent="danger">
            <Alert.Title>{errorTitle}</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        )}
      </dd>
    </Fragment>
  );
}
