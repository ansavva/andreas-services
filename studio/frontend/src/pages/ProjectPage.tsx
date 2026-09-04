import { useCallback, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { Badge, Tabs, Text } from "@ansavva/design-system";

import {
  deleteProject,
  getCharacters,
  getProject,
  getProjectMovies,
  getProjectScenes,
} from "../apis/studio";
import { ApertureSpinner } from "../components/common/Aperture";
import { EmptyState } from "../components/common/EmptyState";
import { PageLoading } from "../components/common/PageLoading";
import { SectionLoading } from "../components/common/SectionLoading";
import { SettingsIcon } from "../components/common/icons";
import { FolderTab } from "../components/browse/FolderTab";
import { CharacterChipLink } from "../components/character/CharacterChip";
import { PageBar } from "../components/layout/PageBar";
import { EntityRow } from "../components/entity/EntityRow";
import { ProjectDetails } from "../components/project/ProjectDetails";
import { RunFeed } from "../components/project/RunFeed";
import { RunLightbox } from "../components/run/RunLightbox";
import { useInFlightRuns } from "../hooks/useInFlightRuns";
import { useResource } from "../hooks/useResource";
import type { HeroImage, ProjectRecord } from "../types";
import { formatDate } from "../utils/format";
import { PROJECTS_PATH, moviePath, runPath, scenePath } from "../utils/location";
import { useSearchParamState } from "../hooks/useSearchParamState";
import { LoadError } from "../components/common/LoadError";
import { ConfirmDestroyDialog } from "../components/common/ConfirmDestroyDialog";

/**
 * One project: the feed of what has been run in it, and everything under it.
 *
 * **Runs is the default tab and the feed is the page.** A project is where
 * things get made, so what it opens on is the making — every run, newest
 * first, grouped by day, with the create bar live above it. Scenes, Movies and
 * Files keep their screens as tabs; Settings, behind the gear at the far end
 * of the strip, is what the Overview tab used to be: the name, the
 * description, who is involved, and Delete.
 *
 * The five tabs are fixed here where a character's are not, and the difference
 * is real rather than an inconsistency. A character's tabs after References are
 * *folders*, which people make and rename freely. A project's are **entity
 * listings** — runs, scenes, movies are rows queried by project id — plus its
 * files. The five starting folders (`runs/`, `scenes/`, `movies/`, `chains/`,
 * `input/`) are still only a convention, and they show up where all folders do:
 * inside Files.
 *
 * ## The opened run is this page, with a lightbox over it
 *
 * `/p/<project>/r/<run>` renders this same component with `runId` set, and
 * `RunLightbox` sits over the feed rather than replacing it — closing it is
 * the feed again, scrolled where it was, with the tab and the filters still
 * in the address. The two-column run page that used to answer that URL is
 * gone.
 *
 * ## There is no Inputs tab, and there should not be one
 *
 * There was: `input/` got a tab of its own, drawing the same nodes Files draws
 * one tab over, in a numbered list. That is the folder-tab mistake the character
 * page already made and undid — a tab whose whole content is one folder of the
 * browser beside it — and the numbering did not save it. `--input N` is a
 * *position in a name-ascending listing*, which nothing stores, so the numbers
 * were derived from the same order Files shows under `name` sort. Reading them
 * off the pool is the CLI's job, and `studio projects inputs <project>` prints
 * each position beside its node.
 */
export function ProjectPage() {
  const { projectId = "", runId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  const [tabParam, setTab] = useSearchParamState("tab", "runs");
  // `?tab=overview` was the old default and is in old links; it is Settings now.
  const tab = tabParam === "overview" ? "settings" : tabParam;
  /** The delete dialog, opened from the page bar's menu rather than drawn loose. */
  const [deleteOpen, setDeleteOpen] = useState(false);
  const load = useCallback(() => getProject(projectId), [projectId]);
  const project = useResource(["project", projectId], load);

  // The card image per character, for the chips — the listing the sidebar's
  // search already reads, so it costs no request of its own.
  const characters = useResource(["characters"], useCallback(() => getCharacters(), []));
  const heroes = useMemo<Record<string, HeroImage | null>>(
    () => Object.fromEntries((characters.data ?? []).map((each) => [each.id, each.hero])),
    [characters.data],
  );

  const running = useInFlightRuns()[projectId] ?? 0;

  const openRun = useCallback(
    (row: { id: string }, output?: number) =>
      navigate(runPath(projectId, row.id) + location.search, {
        state: output === undefined ? undefined : { output },
      }),
    [location.search, navigate, projectId],
  );

  if (project.loading) return <PageLoading label="Loading project" />;

  if (project.error || !project.data) {
    return (
      <LoadError
        what="this project"
        message={project.error ?? "It may have been deleted."}
        onRetry={project.reload}
        escape={{ label: "Back to home", onClick: () => navigate("/") }}
      />
    );
  }

  const record = project.data;

  const counts = record.counts;
  const held = counts.runs + counts.scenes + counts.movies;

  return (
    <>
      {/* `defaultValue` as well as `value`, which the package requires even
          when controlled: it seeds `useControllableState`, and Tabs does not
          introspect its List to guess a first tab. */}
      <Tabs.Root value={tab} defaultValue="runs" onValueChange={setTab}>
        {/* **Delete lives behind `⋯`, and the noun still spells out the
            cascade.** `ConfirmDestroyDialog` types the name because a project
            takes its runs, scenes and movies with it.

            **Nothing here makes a run.** The create bar in the top bar is
            where a run is authored, on every screen; the page's own primary
            slot holds who the project is about instead, per the mockup. */}
        <PageBar
          crumbs={[{ label: "Projects", to: PROJECTS_PATH }]}
          title={record.name}
          meta={
            <>
              <Badge intent="neutral" className="rounded-none font-mono tabular-nums">
                {counts.runs} {counts.runs === 1 ? "run" : "runs"}
              </Badge>
              {running > 0 && (
                <Badge intent="warning" className="rounded-none gap-1.5 font-mono tabular-nums">
                  <ApertureSpinner size="sm" label={`${running} running`} className="size-3.5" />
                  {running} running
                </Badge>
              )}
            </>
          }
          primary={
            record.characters.length > 0 ? (
              <div className="flex flex-wrap items-center gap-2" aria-label="Characters">
                {record.characters.map((each) => (
                  <CharacterChipLink
                    key={each.id}
                    id={each.id}
                    name={each.name}
                    hero={heroes[each.id] ?? null}
                  />
                ))}
              </div>
            ) : undefined
          }
          menu={[{ label: "Delete", danger: true, onSelect: () => setDeleteOpen(true) }]}
          tabs={
            // Scrolls rather than wraps, like the character page's: a tab
            // strip that grows a second row draws a second underline, which
            // reads as two strips. Settings sits at the far end, after a gap,
            // because it is about the project rather than in it.
            <Tabs.List className="overflow-x-auto border-b border-line">
              <Tabs.Tab value="runs">Runs</Tabs.Tab>
              <Tabs.Tab value="scenes">Scenes</Tabs.Tab>
              <Tabs.Tab value="movies">Movies</Tabs.Tab>
              <Tabs.Tab value="files">Files</Tabs.Tab>
              <Tabs.Tab value="settings" className="ml-auto gap-1.5">
                <SettingsIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
                Settings
              </Tabs.Tab>
            </Tabs.List>
          }
        />

        <ConfirmDestroyDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          label="Delete"
          title={`Delete ${record.name}?`}
          summary={deleteSummary(held, counts)}
          confirmWord={record.name}
          onConfirm={async () => {
            await deleteProject(record.id, "delete", held > 0);
            navigate(PROJECTS_PATH);
          }}
        />

        <Tabs.Panel value="runs">
          <RunFeed
            projectId={record.id}
            characters={record.characters}
            heroes={heroes}
            onOpen={openRun}
          />
        </Tabs.Panel>

        <Tabs.Panel value="scenes">
          <ScenesTab projectId={record.id} />
        </Tabs.Panel>

        <Tabs.Panel value="movies">
          <MoviesTab projectId={record.id} />
        </Tabs.Panel>

        <Tabs.Panel value="files">
          <FolderTab rootId={record.root} label={record.name} />
        </Tabs.Panel>

        <Tabs.Panel value="settings" className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            <Badge intent="neutral" className="font-mono tabular-nums">
              {counts.runs} runs
            </Badge>
            <Badge intent="neutral" className="font-mono tabular-nums">
              {counts.scenes} scenes
            </Badge>
            <Badge intent="neutral" className="font-mono tabular-nums">
              {counts.movies} movies
            </Badge>
          </div>

          {/* Involvement is rows, not a list on the record — which is what makes
              the reverse question ("which projects involve this character")
              answerable, and what lets a character delete find what points at
              it. Editing it lives in here with the fields it sits beside. */}
          <ProjectDetails
            record={record}
            // Merged, never swapped in: these routes answer with less than a
            // `GET` does. See `EntityPatch`.
            onSaved={(patch) =>
              project.setData((current) => (current ? { ...current, ...patch } : current))
            }
          />

          <Text variant="caption" tone="muted" className="border-t border-line pt-2 font-mono">
            Created {formatDate(record.created)} · updated {formatDate(record.updated)}
          </Text>
        </Tabs.Panel>
      </Tabs.Root>

      {runId && (
        <RunLightbox
          projectId={record.id}
          runId={runId}
          characters={record.characters}
          heroes={heroes}
        />
      )}
    </>
  );
}

function ScenesTab({ projectId }: { projectId: string }) {
  const load = useCallback(() => getProjectScenes(projectId), [projectId]);
  const { data, loading, error, reload } = useResource(["project-scenes", projectId], load);

  if (loading) return <SectionLoading label="Loading scenes" />;
  if (error) return <LoadError what="scenes" message={error} onRetry={reload} />;
  if (!data || data.length === 0)
    return (
      <EmptyState
        title="No scenes yet."
        hint="A scene is shots stitched into one continuous take."
      />
    );

  return (
    <div className="flex flex-col">
      {data.map((scene) => (
        <EntityRow
          key={scene.id}
          title={scene.name}
          // The date, not the name said twice — the row already carries the
          // title once.
          subtitle={formatDate(scene.created)}
          status={scene.status}
          thumb={scene.thumb ?? null}
          to={scenePath(scene.id)}
        />
      ))}
    </div>
  );
}

function MoviesTab({ projectId }: { projectId: string }) {
  const load = useCallback(() => getProjectMovies(projectId), [projectId]);
  const { data, loading, error, reload } = useResource(["project-movies", projectId], load);

  if (loading) return <SectionLoading label="Loading movies" />;
  if (error) return <LoadError what="movies" message={error} onRetry={reload} />;
  if (!data || data.length === 0)
    return <EmptyState title="No movies yet." hint="A movie is scenes cut into one piece." />;

  return (
    <div className="flex flex-col">
      {data.map((movie) => (
        <EntityRow
          key={movie.id}
          title={movie.name}
          subtitle={formatDate(movie.created)}
          status={movie.status}
          thumb={movie.thumb ?? null}
          to={moviePath(movie.id)}
        />
      ))}
    </div>
  );
}

/**
 * What the delete dialog says is about to go.
 *
 * Spelled out rather than "this project", because the cascade is the part a
 * person cannot see from the header: the runs, scenes and movies go with it,
 * and the sentence is the last chance to notice that.
 */
function deleteSummary(held: number, counts: ProjectRecord["counts"]): string {
  if (held === 0) return "It holds no runs, scenes or movies. Its folder and files go with it.";
  return (
    `${counts.runs} run(s), ${counts.scenes} scene(s) and ${counts.movies} movie(s) ` +
    "go with it, along with the project's folder and everything in it."
  );
}
