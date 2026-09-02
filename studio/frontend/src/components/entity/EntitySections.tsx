import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import type { ReactNode } from "react";

import { Text } from "@ansavva/design-system";

import { ApertureSpinner } from "../common/Aperture";
import { getCharacters, getProjects } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { characterPath, projectPath } from "../../utils/location";
import { EntityCard } from "./EntityCard";
import { LoadError } from "../common/LoadError";
import { CreateEntityDialog } from "./CreateEntityDialog";

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

/**
 * Nothing here yet, and the way to change that.
 *
 * **The button appears only when the heading has none.** Both were shown at
 * first and an empty list drew "New project" twice, a handspan apart — the
 * section's own action and the empty state's call to action, which are the same
 * control. Home passes no action, so its empty state carries the button; the
 * index pages put it in the heading, where it stays once the list fills up.
 */
function Empty({ kind, hasAction }: { kind: "character" | "project"; hasAction: boolean }) {
  return (
    <div className="flex flex-col items-start gap-2">
      <Text variant="body" tone="muted">No {kind}s yet.</Text>
      {!hasAction && (
        <CreateEntityDialog kind={kind} />
      )}
    </div>
  );
}

/** The shared frame: a heading with a count, and whichever of the four states applies. */
function Section({
  title,
  count,
  loading,
  error,
  errorTitle,
  onRetry,
  empty,
  action,
  children,
}: {
  title: string;
  count?: number;
  loading: boolean;
  error: string | null;
  errorTitle: string;
  onRetry?: () => void;
  empty: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      {/* A hairline under the heading, the same rule `PageBar` draws under a
          page title. It is what makes a column of sections read as one ruled
          page rather than as headings floating over grids. */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
        <Text variant="title">
          {title}{" "}
          {count !== undefined && (
            <span className="font-mono text-sm text-muted tabular-nums">({count})</span>
          )}
        </Text>
        {action}
      </div>

      {loading && <ApertureSpinner size="md" label={`Loading ${title.toLowerCase()}`} />}
      {error && <LoadError what={errorTitle.replace("Could not load ", "")} message={error} onRetry={onRetry} />}
      {count === 0 && empty}

      {children}
    </section>
  );
}

export function CharactersSection({ action }: { action?: ReactNode }) {
  const navigate = useNavigate();
  const { data, loading, error, reload } = useResource(
    ["characters"],
    useCallback(() => getCharacters(), []),
  );

  return (
    <Section
      title="Characters"
      count={data?.length}
      loading={loading}
      error={error}
      errorTitle="Could not load characters"
      onRetry={reload}
      action={action}
      empty={<Empty kind="character" hasAction={action !== undefined} />}
    >
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {(data ?? []).map((character) => (
          <EntityCard
            key={character.id}
            name={character.name}
            hero={character.hero}
            counts={`${character.counts.default} sent · ${character.counts.files} files`}
            onOpen={() => navigate(characterPath(character.id))}
          />
        ))}
      </div>
    </Section>
  );
}

export function ProjectsSection({ action }: { action?: ReactNode }) {
  const navigate = useNavigate();
  const { data, loading, error, reload } = useResource(
    ["projects"],
    useCallback(() => getProjects(), []),
  );

  return (
    <Section
      title="Projects"
      count={data?.length}
      loading={loading}
      error={error}
      errorTitle="Could not load projects"
      onRetry={reload}
      action={action}
      empty={<Empty kind="project" hasAction={action !== undefined} />}
    >
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {(data ?? []).map((project) => (
          <EntityCard
            key={project.id}
            name={project.name}
            hero={project.hero}
            counts={`${project.counts.runs} runs · ${project.counts.scenes} scenes · ${project.counts.movies} movies`}
            onOpen={() => navigate(projectPath(project.id))}
          />
        ))}
      </div>
    </Section>
  );
}
