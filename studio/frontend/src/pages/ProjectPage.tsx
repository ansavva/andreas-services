import { useCallback, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Button, Input, Tabs, Text } from "@ansavva/design-system";

import {
  createScene,
  getCharacters,
  getProject,
  getProjectMovies,
  getProjectScenes,
} from "../apis/studio";
import { EmptyState } from "../components/common/EmptyState";
import { PageLoading } from "../components/common/PageLoading";
import { SectionLoading } from "../components/common/SectionLoading";
import { FolderTab } from "../components/browse/FolderTab";
import { EntityRow } from "../components/entity/EntityRow";
import { ProjectDetails } from "../components/project/ProjectDetails";
import { ProjectBar } from "../components/project/ProjectBar";
import { RunFeed } from "../components/project/RunFeed";
import { ProjectReel } from "../components/reel/ProjectReel";
import { RunLightbox } from "../components/run/RunLightbox";
import { useResource } from "../hooks/useResource";
import type { HeroImage } from "../types";
import { formatDate } from "../utils/format";
import { moviePath, projectPath, runPath, scenePath } from "../utils/location";
import { useSearchParamState } from "../hooks/useSearchParamState";
import { LoadError } from "../components/common/LoadError";

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
 * ## The reel is this page too
 *
 * `/p/<project>/reel` sets `reel`, and `ProjectReel` covers the viewport —
 * everything the project holds, oldest first, swiped through. Same bargain
 * as the run: closing it is the feed again, off its cache.
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
export function ProjectPage({ reel = false }: { reel?: boolean }) {
  const { projectId = "", runId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  const [tabParam, setTab] = useSearchParamState("tab", "runs");
  // `?tab=overview` was the old default and is in old links; it is Settings now.
  const tab = tabParam === "overview" ? "settings" : tabParam;
  const load = useCallback(() => getProject(projectId), [projectId]);
  const project = useResource(["project", projectId], load);

  // The card image per character, for the chips — the listing the sidebar's
  // search already reads, so it costs no request of its own.
  const characters = useResource(["characters"], useCallback(() => getCharacters(), []));
  const heroes = useMemo<Record<string, HeroImage | null>>(
    () => Object.fromEntries((characters.data ?? []).map((each) => [each.id, each.hero])),
    [characters.data],
  );

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

  return (
    <>
      {/* `defaultValue` as well as `value`, which the package requires even
          when controlled: it seeds `useControllableState`, and Tabs does not
          introspect its List to guess a first tab. */}
      <Tabs.Root value={tab} defaultValue="runs" onValueChange={setTab}>
        <ProjectBar record={record} heroes={heroes} />

        <Tabs.Panel value="runs">
          <RunFeed
            projectId={record.id}
            characters={record.characters}
            locations={record.locations ?? []}
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

          <Text variant="caption" family="mono" tone="muted" className="border-t border-line pt-2">
            Created {formatDate(record.created)} · updated {formatDate(record.updated)}
          </Text>
        </Tabs.Panel>
      </Tabs.Root>

      {reel && (
        <ProjectReel
          projectId={record.id}
          rootId={record.root}
          name={record.name}
          onClose={() => navigate(projectPath(record.id) + location.search)}
        />
      )}

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

  return (
    <div className="flex flex-col gap-3">
      <NewScene projectId={projectId} />
      {!data || data.length === 0 ? (
        <EmptyState
          title="No scenes yet."
          hint="A scene is a series of runs cut into one take. Name one, then make its runs from its page."
        />
      ) : (
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
      )}
    </div>
  );
}

/**
 * A scene starts as a name. Everything else — its runs, its cut — is made
 * from its own page, where the create bar files runs under it.
 */
function NewScene({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const create = async () => {
    if (!name.trim() || busy) return;
    setBusy(true);
    setFailure(null);
    try {
      const scene = await createScene({ project: projectId, name: name.trim() });
      navigate(scenePath(scene.id));
    } catch (err) {
      setFailure((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        void create();
      }}
    >
      {/* `field-row`: the button stands at the input's 44, not a `sm` 32
          beside it — see `styles/app.css`. */}
      <div className="field-row flex flex-wrap items-center gap-2">
        <Input
          value={name}
          onValueChange={setName}
          placeholder="A new scene's name…"
          aria-label="Scene name"
          className="min-w-48 flex-1"
        />
        <Button type="submit" disabled={!name.trim() || busy}>
          {busy ? "Creating…" : "New scene"}
        </Button>
      </div>
      {failure && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not create the scene</Alert.Title>
          <Alert.Description>{failure}</Alert.Description>
        </Alert.Root>
      )}
    </form>
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
