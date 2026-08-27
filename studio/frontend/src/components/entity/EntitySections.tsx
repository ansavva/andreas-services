import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import type { ReactNode } from "react";

import { Alert, Spinner, Text } from "@ansavva/design-system";

import { getCharacters, getProjects } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { characterPath, projectPath } from "../../utils/location";
import { EntityCard } from "./EntityCard";

/**
 * The two entity lists, as sections that can be rendered anywhere.
 *
 * They were open-coded in `HomePage` and are shared now because there are three
 * callers: home, which shows both, and the two index pages the header links to,
 * which show one each. Lifting them is what makes `/characters` a real screen
 * rather than a second, subtly different copy of a list home already had.
 *
 * Each section owns its own fetch. That looks wasteful on home — two requests
 * where the page could have made them side by side — and is the right shape
 * anyway: the alternative is home fetching both and passing them down, which
 * means the index pages need their own fetch regardless and the two paths drift.
 * One place per list, three callers.
 */

/** The shared frame: a heading with a count, and whichever of the four states applies. */
function Section({
  title,
  count,
  loading,
  error,
  errorTitle,
  empty,
  action,
  children,
}: {
  title: string;
  count?: number;
  loading: boolean;
  error: string | null;
  errorTitle: string;
  empty: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Text variant="title">
          {title}{" "}
          {count !== undefined && <span className="font-body text-sm text-muted">({count})</span>}
        </Text>
        {action}
      </div>

      {loading && <Spinner size="md" label={`Loading ${title.toLowerCase()}`} />}
      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>{errorTitle}</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}
      {count === 0 && empty}

      {children}
    </section>
  );
}

export function CharactersSection({ action }: { action?: ReactNode }) {
  const navigate = useNavigate();
  const { data, loading, error } = useResource(useCallback(() => getCharacters(), []));

  return (
    <Section
      title="Characters"
      count={data?.length}
      loading={loading}
      error={error}
      errorTitle="Could not load characters"
      action={action}
      empty={
        <Text variant="body" tone="muted">
          No characters yet. `studio character create &lt;slug&gt;` makes one.
        </Text>
      }
    >
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {(data ?? []).map((character) => (
          <EntityCard
            key={character.id}
            title={character.display_name}
            slug={character.slug}
            hero={character.hero}
            counts={`${character.counts.references} references · ${character.counts.files} files`}
            onOpen={() => navigate(characterPath(character.id))}
          />
        ))}
      </div>
    </Section>
  );
}

export function ProjectsSection({ action }: { action?: ReactNode }) {
  const navigate = useNavigate();
  const { data, loading, error } = useResource(useCallback(() => getProjects(), []));

  return (
    <Section
      title="Projects"
      count={data?.length}
      loading={loading}
      error={error}
      errorTitle="Could not load projects"
      action={action}
      empty={
        <Text variant="body" tone="muted">
          No projects yet. `studio projects new &lt;slug&gt;` makes one.
        </Text>
      }
    >
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {(data ?? []).map((project) => (
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
    </Section>
  );
}
