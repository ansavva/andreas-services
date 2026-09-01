import { useCallback } from "react";
import { useNavigate } from "react-router-dom";

import { Text } from "@ansavva/design-system";

import { ApertureSpinner } from "../common/Aperture";
import { getCharacterProjects, getCharacterRuns } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { projectPath, runPath } from "../../utils/location";
import { EntityCard } from "../entity/EntityCard";
import { RunList } from "../run/RunList";
import { LoadError } from "../common/LoadError";

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
  const { data, loading, error, reload } = useResource(["character-runs", characterId], load);

  if (loading) return <ApertureSpinner size="md" label="Loading runs" />;
  if (error) return <LoadError what="runs" message={error} onRetry={reload} />;

  const runs = data?.runs ?? [];
  if (runs.length === 0) {
    return (
      <Text variant="body" tone="muted">
        Nothing has been rendered with this character yet. A run records which
        characters it used, so this fills in on its own.
      </Text>
    );
  }

  // The rows are `RunList`'s. This tab used to draw its own — no thumbnail, and
  // a status badge that only knew `failed`, so a `running` run read grey here
  // and amber on a project page for the same run.
  return <RunList runs={runs} onOpen={(run) => navigate(runPath(run.project as string, run.id))} />;
}

export function CharacterProjects({ characterId }: { characterId: string }) {
  const navigate = useNavigate();
  const load = useCallback(() => getCharacterProjects(characterId), [characterId]);
  const { data, loading, error, reload } = useResource(["character-projects", characterId], load);

  if (loading) return <ApertureSpinner size="md" label="Loading projects" />;
  if (error) return <LoadError what="projects" message={error} onRetry={reload} />;
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

