import { useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Button, Spinner, Tabs, Text } from "@ansavva/design-system";

import {
  getProject,
  getProjectInputs,
  getProjectMovies,
  getProjectScenes,
} from "../apis/studio";
import { FolderTab } from "../components/browse/FolderBrowser";
import { AppHeader } from "../components/common/AppHeader";
import { RunsTable } from "../components/project/RunsTable";
import { useResource } from "../hooks/useResource";
import { formatBytes, formatDate } from "../utils/format";
import { characterPath, moviePath, runPath, scenePath } from "../utils/location";

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

  const load = useCallback(() => getProject(projectId), [projectId]);
  const project = useResource(load);

  if (project.loading) {
    return (
      <Shell>
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading project" />
        </div>
      </Shell>
    );
  }

  if (project.error || !project.data) {
    return (
      <Shell>
        <Alert.Root intent="danger">
          <Alert.Title>Could not open this project</Alert.Title>
          <Alert.Description>{project.error ?? "It may have been deleted."}</Alert.Description>
        </Alert.Root>
        <div>
          <Button size="sm" onClick={() => navigate("/")}>
            Back to home
          </Button>
        </div>
      </Shell>
    );
  }

  const record = project.data;

  return (
    <Shell subtitle={record.slug}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Text variant="display">{record.title || record.slug}</Text>
        <Text variant="caption" tone="muted">
          {record.slug}
        </Text>
      </div>

      <Tabs.Root defaultValue="overview">
        <Tabs.List className="flex-wrap border-b border-line">
          <Tabs.Tab value="overview">Overview</Tabs.Tab>
          <Tabs.Tab value="runs">Runs</Tabs.Tab>
          <Tabs.Tab value="scenes">Scenes</Tabs.Tab>
          <Tabs.Tab value="movies">Movies</Tabs.Tab>
          <Tabs.Tab value="inputs">Inputs</Tabs.Tab>
          <Tabs.Tab value="files">Files</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="overview" className="flex flex-col gap-4">
          {record.description && <Text variant="body">{record.description}</Text>}

          <div className="flex flex-wrap gap-2">
            <Badge intent="neutral">{record.counts.runs} runs</Badge>
            <Badge intent="neutral">{record.counts.scenes} scenes</Badge>
            <Badge intent="neutral">{record.counts.movies} movies</Badge>
          </div>

          <section className="flex flex-col gap-2">
            <Text variant="title">Characters</Text>
            {/* Involvement is rows, not a list on the record — which is what
                makes the reverse question ("which projects involve this
                character") answerable, and what lets a character delete find
                what points at it. */}
            {record.characters.length === 0 ? (
              <Text variant="body" tone="muted">
                Nobody is linked to this project yet.
              </Text>
            ) : (
              <div className="flex flex-wrap gap-2">
                {record.characters.map((character) => (
                  <Button
                    key={character.id}
                    intent="ghost"
                    size="sm"
                    onClick={() => navigate(characterPath(character.id))}
                  >
                    {character.display_name}
                  </Button>
                ))}
              </div>
            )}
          </section>

          <Text variant="caption" tone="muted">
            Created {formatDate(record.created)} · updated {formatDate(record.updated)} · revision{" "}
            {record.rev}
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
    </Shell>
  );
}

function ScenesTab({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const load = useCallback(() => getProjectScenes(projectId), [projectId]);
  const { data, loading, error } = useResource(load);

  if (loading) return <Spinner size="md" label="Loading scenes" />;
  if (error) return <LoadError what="scenes" message={error} />;
  if (!data || data.length === 0)
    return (
      <Text variant="body" tone="muted">
        No scenes yet. A scene is shots stitched into one continuous take.
      </Text>
    );

  return (
    <div className="flex flex-col gap-2">
      {data.map((scene) => (
        <ListRow
          key={scene.id}
          title={scene.title || scene.slug}
          subtitle={`${scene.slug} · ${formatDate(scene.created)}`}
          status={scene.status}
          thumbUrl={scene.thumb?.url ?? null}
          onOpen={() => navigate(scenePath(scene.id))}
        />
      ))}
    </div>
  );
}

function MoviesTab({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const load = useCallback(() => getProjectMovies(projectId), [projectId]);
  const { data, loading, error } = useResource(load);

  if (loading) return <Spinner size="md" label="Loading movies" />;
  if (error) return <LoadError what="movies" message={error} />;
  if (!data || data.length === 0)
    return (
      <Text variant="body" tone="muted">
        No movies yet. A movie is scenes cut into one piece.
      </Text>
    );

  return (
    <div className="flex flex-col gap-2">
      {data.map((movie) => (
        <ListRow
          key={movie.id}
          title={movie.title || movie.slug}
          subtitle={`${movie.slug} · ${formatDate(movie.created)}`}
          status={movie.status}
          thumbUrl={movie.thumb?.url ?? null}
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
 * the first time a shoot picks the wrong plate.
 */
function InputsTab({ projectId }: { projectId: string }) {
  const load = useCallback(() => getProjectInputs(projectId), [projectId]);
  const { data, loading, error } = useResource(load);

  if (loading) return <Spinner size="md" label="Loading inputs" />;
  if (error) return <LoadError what="inputs" message={error} />;
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
          key={input.node}
          className="flex items-center gap-3 rounded-md border border-line bg-card p-2"
        >
          <Text variant="body" className="w-8 shrink-0 text-right tabular-nums">
            {index + 1}
          </Text>
          <img
            src={input.url}
            alt=""
            className="size-12 shrink-0 rounded-md border border-line object-cover"
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

function ListRow({
  title,
  subtitle,
  status,
  thumbUrl,
  onOpen,
}: {
  title: string;
  subtitle: string;
  status: string;
  thumbUrl: string | null;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-md border border-line bg-card p-2 text-left
                 transition-colors hover:bg-surface-alt
                 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      <span className="size-14 shrink-0 overflow-hidden rounded-md border border-line bg-surface-alt">
        {thumbUrl && <img src={thumbUrl} alt="" className="h-full w-full object-cover" />}
      </span>
      <span className="min-w-0 flex-1">
        <Text variant="body" className="truncate">
          {title}
        </Text>
        <Text variant="caption" tone="muted" className="truncate">
          {subtitle}
        </Text>
      </span>
      <Badge intent="neutral">{status}</Badge>
    </button>
  );
}

function LoadError({ what, message }: { what: string; message: string }) {
  return (
    <Alert.Root intent="danger">
      <Alert.Title>Could not load {what}</Alert.Title>
      <Alert.Description>{message}</Alert.Description>
    </Alert.Root>
  );
}

function Shell({ children, subtitle }: { children: React.ReactNode; subtitle?: string }) {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-6 p-4 sm:p-6">
      <AppHeader subtitle={subtitle ?? "project"} />
      {children}
    </div>
  );
}
