import { useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Button, Spinner, Tabs, Text } from "@ansavva/design-system";

import {
  deleteProject,
  getProject,
  getProjectInputs,
  getProjectMovies,
  getProjectScenes,
} from "../apis/studio";
import { FolderTab } from "../components/browse/FolderTab";
import { PageBar } from "../components/layout/PageBar";
import { EntityRow } from "../components/entity/EntityRow";
import { MediaThumb } from "../components/media/MediaThumb";
import { ProjectDetails } from "../components/project/ProjectDetails";
import { RunsTable } from "../components/project/RunsTable";
import { useResource } from "../hooks/useResource";
import type { ProjectRecord } from "../types";
import { formatBytes, formatDate } from "../utils/format";
import { PROJECTS_PATH, moviePath, runPath, scenePath } from "../utils/location";
import { useSearchParamState } from "../hooks/useSearchParamState";
import { LoadError } from "../components/common/LoadError";
import { ConfirmDestroyDialog } from "../components/common/ConfirmDestroyDialog";

/**
 * One project: what it is, what has been run in it, and everything under it.
 *
 * The six tabs are fixed here where a character's are not, and the difference is
 * real rather than an inconsistency. A character's tabs after References are
 * *folders*, which people make and rename freely. A project's are **entity
 * listings** — runs, scenes, movies are rows queried by project id — plus its
 * input pool and its files. The five starting folders (`runs/`, `scenes/`,
 * `movies/`, `chains/`, `input/`) are still only a convention, and they show up
 * where all folders do: inside Files.
 */
export function ProjectPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();

  const [tab, setTab] = useSearchParamState("tab", "overview");
  const load = useCallback(() => getProject(projectId), [projectId]);
  const project = useResource(["project", projectId], load);

  if (project.loading) {
    return (
      <>
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading project" />
        </div>
      </>
    );
  }

  if (project.error || !project.data) {
    return (
      <>
        <Alert.Root intent="danger">
          <Alert.Title>Could not open this project</Alert.Title>
          <Alert.Description>{project.error ?? "It may have been deleted."}</Alert.Description>
        </Alert.Root>
        <div>
          <Button size="sm" onClick={() => navigate("/")}>
            Back to home
          </Button>
        </div>
      </>
    );
  }

  const record = project.data;

  const counts = record.counts;
  const held = counts.runs + counts.scenes + counts.movies;

  return (
    <>
      {/* **The noun spells out the cascade, because the button IS the
          confirmation.** `ConfirmDeleteButton` arms in place rather than
          opening a modal — the reasoning is in that file — so the armed label
          is the only thing standing between a click and 29 runs. It says the
          count for that reason, and the count comes off the record rather
          than a second fetch.

          The `ms-auto` this used to hang the button off is gone with the bar:
          it pinned the control to whichever line the flex run broke at, which
          on a phone moved a destructive button around under the title. */}
      <PageBar
        crumbs={[{ label: "Projects", to: PROJECTS_PATH }]}
        actions={
          <ConfirmDestroyDialog
            label="Delete"
            title={`Delete ${record.slug}?`}
            summary={deleteSummary(held, counts)}
            confirmWord={record.slug}
            onConfirm={async () => {
              await deleteProject(record.id, "delete", held > 0);
              navigate(PROJECTS_PATH);
            }}
          />
        }
      >
        <Text variant="display">{record.title || record.slug}</Text>
        <Text variant="caption" tone="muted">
          {record.slug}
        </Text>
      </PageBar>

      {/* `defaultValue` as well as `value`, which the package requires even
          when controlled: it seeds `useControllableState`, and Tabs does not
          introspect its List to guess a first tab. */}
      <Tabs.Root value={tab} defaultValue="overview" onValueChange={setTab}>
        {/* Scrolls rather than wraps, like the character page's. Six labels
            wrapped to two rows on a phone, and a tab strip that grows a second
            row draws a second underline — which reads as two strips. */}
        <Tabs.List className="overflow-x-auto border-b border-line">
          <Tabs.Tab value="overview">Overview</Tabs.Tab>
          <Tabs.Tab value="runs">Runs</Tabs.Tab>
          <Tabs.Tab value="scenes">Scenes</Tabs.Tab>
          <Tabs.Tab value="movies">Movies</Tabs.Tab>
          <Tabs.Tab value="inputs">Inputs</Tabs.Tab>
          <Tabs.Tab value="files">Files</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="overview" className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            <Badge intent="neutral">{record.counts.runs} runs</Badge>
            <Badge intent="neutral">{record.counts.scenes} scenes</Badge>
            <Badge intent="neutral">{record.counts.movies} movies</Badge>
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

          <Text variant="caption" tone="muted">
            Created {formatDate(record.created)} · updated {formatDate(record.updated)}
          </Text>
        </Tabs.Panel>

        <Tabs.Panel value="runs">
          <RunsTable
            projectId={record.id}
            characters={record.characters}
            onOpen={(run) => navigate(runPath(record.id, run.id))}
          />
        </Tabs.Panel>

        <Tabs.Panel value="scenes">
          <ScenesTab projectId={record.id} />
        </Tabs.Panel>

        <Tabs.Panel value="movies">
          <MoviesTab projectId={record.id} />
        </Tabs.Panel>

        <Tabs.Panel value="inputs">
          <InputsTab projectId={record.id} />
        </Tabs.Panel>

        <Tabs.Panel value="files">
          <FolderTab rootId={record.root} />
        </Tabs.Panel>
      </Tabs.Root>
    </>
  );
}

function ScenesTab({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const load = useCallback(() => getProjectScenes(projectId), [projectId]);
  const { data, loading, error, reload } = useResource(["project-scenes", projectId], load);

  if (loading) return <Spinner size="md" label="Loading scenes" />;
  if (error) return <LoadError what="scenes" message={error} onRetry={reload} />;
  if (!data || data.length === 0)
    return (
      <Text variant="body" tone="muted">
        No scenes yet. A scene is shots stitched into one continuous take.
      </Text>
    );

  return (
    <div className="flex flex-col gap-2">
      {data.map((scene) => (
        <EntityRow
          key={scene.id}
          title={scene.title || scene.slug}
          subtitle={`${scene.slug} · ${formatDate(scene.created)}`}
          status={scene.status}
          thumb={scene.thumb ?? null}
          onOpen={() => navigate(scenePath(scene.id))}
        />
      ))}
    </div>
  );
}

function MoviesTab({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const load = useCallback(() => getProjectMovies(projectId), [projectId]);
  const { data, loading, error, reload } = useResource(["project-movies", projectId], load);

  if (loading) return <Spinner size="md" label="Loading movies" />;
  if (error) return <LoadError what="movies" message={error} onRetry={reload} />;
  if (!data || data.length === 0)
    return (
      <Text variant="body" tone="muted">
        No movies yet. A movie is scenes cut into one piece.
      </Text>
    );

  return (
    <div className="flex flex-col gap-2">
      {data.map((movie) => (
        <EntityRow
          key={movie.id}
          title={movie.title || movie.slug}
          subtitle={`${movie.slug} · ${formatDate(movie.created)}`}
          status={movie.status}
          thumb={movie.thumb ?? null}
          onOpen={() => navigate(moviePath(movie.id))}
        />
      ))}
    </div>
  );
}

/**
 * The working pool, numbered.
 *
 * **The number is the whole point.** `--input N` is a *position* in this list,
 * which the API sorts name-ascending — nothing stores it, so renaming a file
 * renumbers the pool. Showing the positions is what stops that being a surprise
 * the first time a turnaround picks the wrong angle image.
 */
function InputsTab({ projectId }: { projectId: string }) {
  const load = useCallback(() => getProjectInputs(projectId), [projectId]);
  const { data, loading, error, reload } = useResource(["project-inputs", projectId], load);

  if (loading) return <Spinner size="md" label="Loading inputs" />;
  if (error) return <LoadError what="inputs" message={error} onRetry={reload} />;
  if (!data || data.length === 0)
    return (
      <Text variant="body" tone="muted">
        The input pool is empty.
      </Text>
    );

  return (
    <div className="flex flex-col gap-2">
      <Text variant="caption" tone="muted">
        The number is what <code>--input N</code> means. It is a position in this order, not
        anything stored — renaming a file renumbers the pool.
      </Text>
      {data.map((input, index) => (
        <div
          key={input.id}
          className="flex items-center gap-3 rounded-md border border-line bg-card p-2"
        >
          <Text variant="body" className="w-8 shrink-0 text-right tabular-nums">
            {index + 1}
          </Text>
          <MediaThumb
            nodeId={input.id}
            url={input.url}
            name={input.name}
            aspect="auto"
            className="size-12 shrink-0 rounded-md border border-line"
          />
          <div className="min-w-0 flex-1">
            <Text variant="body" className="truncate">
              {input.name}
            </Text>
            {input.size !== undefined && (
              <Text variant="caption" tone="muted">
                {formatBytes(input.size)}
              </Text>
            )}
          </div>
        </div>
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
