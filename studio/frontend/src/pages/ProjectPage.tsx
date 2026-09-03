import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Badge, Tabs, Text } from "@ansavva/design-system";

import {
  deleteProject,
  getProject,
  getProjectMovies,
  getProjectScenes,
} from "../apis/studio";
import { EmptyState } from "../components/common/EmptyState";
import { PageLoading } from "../components/common/PageLoading";
import { SectionLoading } from "../components/common/SectionLoading";
import { FolderTab } from "../components/browse/FolderTab";
import { PageBar } from "../components/layout/PageBar";
import { EntityRow } from "../components/entity/EntityRow";
import { ProjectDetails } from "../components/project/ProjectDetails";
import { RunsTable } from "../components/project/RunsTable";
import { NewRunStrip } from "../components/run/NewRunStrip";
import { useResource } from "../hooks/useResource";
import type { ProjectRecord } from "../types";
import { formatDate } from "../utils/format";
import { PROJECTS_PATH, moviePath, runPath, scenePath } from "../utils/location";
import { useSearchParamState } from "../hooks/useSearchParamState";
import { LoadError } from "../components/common/LoadError";
import { ConfirmDestroyDialog } from "../components/common/ConfirmDestroyDialog";

/**
 * One project: what it is, what has been run in it, and everything under it.
 *
 * The five tabs are fixed here where a character's are not, and the difference
 * is real rather than an inconsistency. A character's tabs after References are
 * *folders*, which people make and rename freely. A project's are **entity
 * listings** — runs, scenes, movies are rows queried by project id — plus its
 * files. The five starting folders (`runs/`, `scenes/`, `movies/`, `chains/`,
 * `input/`) are still only a convention, and they show up where all folders do:
 * inside Files.
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
  const { projectId = "" } = useParams();
  const navigate = useNavigate();

  const [tab, setTab] = useSearchParamState("tab", "overview");
  /** The delete dialog, opened from the page bar's menu rather than drawn loose. */
  const [deleteOpen, setDeleteOpen] = useState(false);
  const load = useCallback(() => getProject(projectId), [projectId]);
  const project = useResource(["project", projectId], load);

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
      {/* **Delete lives behind `⋯` now, and the noun still spells out the
          cascade.** `ConfirmDestroyDialog` types the name because a project
          takes its runs, scenes and movies with it — the same reasoning as
          before, opened from the menu instead of drawn loose beside the
          title.

          **`New run` is the page's primary now, not a strip above the Runs
          tab.** It still opens the same drawer — `NewRunStrip` — because what
          it makes belongs to the project either way; only the trigger moved,
          to the one place every other entity's create control lives. */}
      <PageBar
        crumbs={[{ label: "Projects", to: PROJECTS_PATH }]}
        title={record.name}
        primary={<NewRunStrip projectId={record.id} characters={record.characters} />}
        menu={[{ label: "Delete", danger: true, onSelect: () => setDeleteOpen(true) }]}
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

      {/* `defaultValue` as well as `value`, which the package requires even
          when controlled: it seeds `useControllableState`, and Tabs does not
          introspect its List to guess a first tab. */}
      <Tabs.Root value={tab} defaultValue="overview" onValueChange={setTab}>
        {/* Scrolls rather than wraps, like the character page's: a tab strip
            that grows a second row draws a second underline, which reads as two
            strips. Six of these wrapped at 390px, and five is not far enough
            under that to change the rule. */}
        <Tabs.List className="overflow-x-auto border-b border-line">
          <Tabs.Tab value="overview">Overview</Tabs.Tab>
          <Tabs.Tab value="runs">Runs</Tabs.Tab>
          <Tabs.Tab value="scenes">Scenes</Tabs.Tab>
          <Tabs.Tab value="movies">Movies</Tabs.Tab>
          <Tabs.Tab value="files">Files</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="overview" className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            <Badge intent="neutral" className="font-mono tabular-nums">
              {record.counts.runs} runs
            </Badge>
            <Badge intent="neutral" className="font-mono tabular-nums">
              {record.counts.scenes} scenes
            </Badge>
            <Badge intent="neutral" className="font-mono tabular-nums">
              {record.counts.movies} movies
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

          {/* `block`: `caption` is a `<span>`, and an inline box takes no
              top border or padding of its own. */}
          <Text variant="caption" tone="muted" className="block border-t border-line pt-2 font-mono">
            Created {formatDate(record.created)} · updated {formatDate(record.updated)}
          </Text>
        </Tabs.Panel>

        {/* The strip sits above the table rather than in the page bar, because
            what it makes is a run in THIS project — and because the page bar's
            one action deletes the project. */}
        <Tabs.Panel value="runs" className="flex flex-col gap-4">
          {/* **One reading, not a choice of two.** The Grid view — the file
              browser scoped to `runs/`, in Media view — is gone: "which runs
              failed" and "what did this project make" are different questions
              with different owners, and the second is Files' job, one tab
              over, on exactly the same folder. A run's OUTPUTS live there; a
              run's own fields — status, model, cost, when — live here.

              `New run` moved to the page bar's primary slot, so there is
              nothing left to draw above the table at all. */}
          <RunsTable
            projectId={record.id}
            characters={record.characters}
            to={(run) => runPath(record.id, run.id)}
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
      </Tabs.Root>
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
