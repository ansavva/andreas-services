import { useCallback } from "react";
import { useNavigate } from "react-router-dom";

import { Alert, Badge, Spinner, Text } from "@ansavva/design-system";

import { getCharacterProjects, getCharacterRuns } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { formatDate } from "../../utils/format";
import { projectPath, runPath } from "../../utils/location";
import { EntityCard } from "../entity/EntityCard";

/**
 * What this character has been IN — the two questions a character page could
 * not answer.
 *
 * **Both routes existed and neither had a caller.** `GET /characters/<id>/runs`
 * and `/projects` were written when involvement became rows rather than a list
 * on the record, precisely so the reverse question would be answerable — and
 * the app never asked it. A character was a dead end: you could see who it was
 * and what it looked like, and nothing about the work it appears in.
 *
 * They are two tabs rather than one because they answer different questions at
 * different grains. A run is a machine event with a date; a project is a place
 * to go.
 */
export function CharacterRuns({ characterId }: { characterId: string }) {
  const navigate = useNavigate();
  const load = useCallback(() => getCharacterRuns(characterId), [characterId]);
  const { data, loading, error } = useResource(load);

  if (loading) return <Spinner size="md" label="Loading runs" />;
  if (error) return <Failed what="runs" message={error} />;

  const runs = data?.runs ?? [];
  if (runs.length === 0) {
    return (
      <Text variant="body" tone="muted">
        Nothing has been rendered with this character yet. A run records which
        characters it used, so this fills in on its own.
      </Text>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {runs.map((run) => (
        <button
          key={run.id}
          type="button"
          // A run's address needs its project as well as its own id, and the
          // row carries both — which is the shape `/p/<id>/r/<id>` exists for.
          onClick={() => navigate(runPath(run.project, run.id))}
          className="flex w-full items-center gap-3 rounded-md border border-line bg-card p-2 text-left
                     transition-colors hover:bg-surface-alt
                     focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <span className="min-w-0 flex-1">
            {/* A run has no name — the date is what a person recognises it by. */}
            <Text variant="body" className="truncate">
              {formatDate(run.created)}
            </Text>
            <Text variant="caption" tone="muted" className="block truncate">
              {run.model}
            </Text>
          </span>
          <Badge intent={run.status === "failed" ? "danger" : "neutral"}>{run.status}</Badge>
        </button>
      ))}
    </div>
  );
}

export function CharacterProjects({ characterId }: { characterId: string }) {
  const navigate = useNavigate();
  const load = useCallback(() => getCharacterProjects(characterId), [characterId]);
  const { data, loading, error } = useResource(load);

  if (loading) return <Spinner size="md" label="Loading projects" />;
  if (error) return <Failed what="projects" message={error} />;
  if (!data || data.length === 0) {
    return (
      <Text variant="body" tone="muted">
        This character is not linked to a project yet.
      </Text>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {data.map((project) => (
        <EntityCard
          key={project.id}
          title={project.title || project.slug}
          slug={project.slug}
          hero={project.hero}
          counts={`${project.counts.runs} runs · ${project.counts.scenes} scenes · ${project.counts.movies} movies`}
          onOpen={() => navigate(projectPath(project.id))}
        />
      ))}
    </div>
  );
}

function Failed({ what, message }: { what: string; message: string }) {
  return (
    <Alert.Root intent="danger">
      <Alert.Title>Could not load {what}</Alert.Title>
      <Alert.Description>{message}</Alert.Description>
    </Alert.Root>
  );
}
