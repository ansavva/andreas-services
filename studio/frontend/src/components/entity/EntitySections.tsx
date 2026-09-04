import { useCallback } from "react";
import type { ReactNode } from "react";

import { Text } from "@ansavva/design-system";

import { EmptyState } from "../common/EmptyState";
import { SectionLoading } from "../common/SectionLoading";
import { getCharacters, getProjects } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { ENTITY_GRID } from "../../utils/grid";
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
 * **The button appears only when nothing else on the page already offers it.**
 * Home shows both sections with no page-level create control, so their empty
 * states carry the button. `/characters` and `/projects` have one now — the
 * page's own `PageBar primary` — and passing it a second time here would draw
 * "New project" twice, a handspan apart.
 */
function Empty({ kind, hasPrimary }: { kind: "character" | "project"; hasPrimary: boolean }) {
  return (
    <EmptyState
      title={`No ${kind}s yet.`}
      action={hasPrimary ? undefined : <CreateEntityDialog kind={kind} />}
    />
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
  children,
  heading = true,
}: {
  title: string;
  count?: number;
  loading: boolean;
  error: string | null;
  errorTitle: string;
  onRetry: () => void;
  empty: ReactNode;
  children: ReactNode;
  /**
   * Off on `/characters` and `/projects`, whose `PageBar` already carries
   * this title — `HomePage` stacks three sections and keeps its own.
   */
  heading?: boolean;
}) {
  return (
    <section className="flex flex-col gap-3">
      {/* A hairline under the heading, the same rule `PageBar` draws under a
          page title. It is what makes a column of sections read as one ruled
          page rather than as headings floating over grids. */}
      {heading && (
        <div className="border-b border-line pb-2">
          <Text variant="title">
            {title}{" "}
            {count !== undefined && (
              <span className="font-mono text-sm text-muted tabular-nums">({count})</span>
            )}
          </Text>
        </div>
      )}

      {loading && <SectionLoading label={`Loading ${title.toLowerCase()}`} />}
      {error && <LoadError what={errorTitle.replace("Could not load ", "")} message={error} onRetry={onRetry} />}
      {count === 0 && empty}

      {children}
    </section>
  );
}

interface SectionProps {
  hasPrimary?: boolean;
  heading?: boolean;
}

export function CharactersSection({ hasPrimary = false, heading }: SectionProps) {
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
      empty={<Empty kind="character" hasPrimary={hasPrimary} />}
      heading={heading}
    >
      <div className={ENTITY_GRID}>
        {(data ?? []).map((character) => (
          <EntityCard
            key={character.id}
            name={character.name}
            hero={character.hero}
            counts={`${character.counts.default} sent · ${character.counts.files} files`}
            to={characterPath(character.id)}
          />
        ))}
      </div>
    </Section>
  );
}

export function ProjectsSection({ hasPrimary = false, heading }: SectionProps) {
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
      empty={<Empty kind="project" hasPrimary={hasPrimary} />}
      heading={heading}
    >
      <div className={ENTITY_GRID}>
        {(data ?? []).map((project) => (
          <EntityCard
            key={project.id}
            name={project.name}
            hero={project.hero}
            counts={`${project.counts.runs} runs · ${project.counts.scenes} scenes · ${project.counts.movies} movies`}
            to={projectPath(project.id)}
          />
        ))}
      </div>
    </Section>
  );
}
