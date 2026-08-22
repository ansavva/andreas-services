import { useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Button, Spinner, Text } from "@ansavva/design-system";

import { getMovie } from "../apis/studio";
import { AppHeader } from "../components/common/AppHeader";
import { useResource } from "../hooks/useResource";
import { formatDate } from "../utils/format";
import { objectPath, projectPath, scenePath } from "../utils/location";

/**
 * One movie: the scenes it is cut from, in order, and the finished piece.
 *
 * The tier above a scene, and the same envelope one level up — ids and a status,
 * with the cut as a node id. Its scenes are listed rather than embedded because
 * a scene is an entity of its own with its own page, and duplicating its shots
 * here would be a second rendering of the same rows to keep in step.
 */
export function MoviePage() {
  const { movieId = "" } = useParams();
  const navigate = useNavigate();

  const load = useCallback(() => getMovie(movieId), [movieId]);
  const { data, loading, error } = useResource(load);

  if (loading) {
    return (
      <Shell>
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading movie" />
        </div>
      </Shell>
    );
  }

  if (error || !data) {
    return (
      <Shell>
        <Alert.Root intent="danger">
          <Alert.Title>Could not open this movie</Alert.Title>
          <Alert.Description>{error ?? "It may have been deleted."}</Alert.Description>
        </Alert.Root>
      </Shell>
    );
  }

  return (
    <Shell subtitle={data.slug}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Button intent="ghost" size="sm" onClick={() => navigate(projectPath(data.project))}>
          <span aria-hidden="true">←</span> Project
        </Button>
        <Text variant="display">{data.title || data.slug}</Text>
        <Badge intent="neutral">{data.status}</Badge>
        <Text variant="caption" tone="muted">
          {formatDate(data.created)}
        </Text>
      </div>

      {data.output && (
        <section className="flex flex-col gap-2">
          <Text variant="title">The piece</Text>
          <button
            type="button"
            onClick={() => navigate(objectPath(data.output!.node))}
            className="w-full max-w-2xl overflow-hidden rounded-md border border-line bg-card
                       focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <video
              src={data.output.url}
              muted
              playsInline
              preload="metadata"
              className="aspect-video w-full object-cover"
            />
            <Text variant="caption" tone="muted" className="truncate px-2 py-1">
              {data.output.name}
            </Text>
          </button>
        </section>
      )}

      <section className="flex flex-col gap-2">
        <Text variant="title">Scenes</Text>
        {data.scenes.length === 0 ? (
          <Text variant="body" tone="muted">
            No scenes are cut into this yet.
          </Text>
        ) : (
          <div className="flex flex-col gap-2">
            {data.scenes.map((scene, index) => (
              <button
                key={scene.id}
                type="button"
                onClick={() => navigate(scenePath(scene.id))}
                className="flex w-full items-center gap-3 rounded-md border border-line bg-card p-2 text-left
                           transition-colors hover:bg-surface-alt
                           focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                <Text variant="body" className="w-8 shrink-0 text-right tabular-nums">
                  {index + 1}
                </Text>
                <span className="size-14 shrink-0 overflow-hidden rounded-md border border-line bg-surface-alt">
                  {scene.thumb && (
                    <img src={scene.thumb.url} alt="" className="h-full w-full object-cover" />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <Text variant="body" className="truncate">
                    {scene.title || scene.slug}
                  </Text>
                  <Text variant="caption" tone="muted" className="truncate">
                    {scene.slug}
                  </Text>
                </span>
                <Badge intent="neutral">{scene.status}</Badge>
              </button>
            ))}
          </div>
        )}
      </section>
    </Shell>
  );
}

function Shell({ children, subtitle }: { children: React.ReactNode; subtitle?: string }) {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-6 p-4 sm:p-6">
      <AppHeader subtitle={subtitle ?? "movie"} />
      {children}
    </div>
  );
}
