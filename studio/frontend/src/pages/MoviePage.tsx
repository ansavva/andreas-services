import { useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Spinner, Text } from "@ansavva/design-system";

import { getMovie } from "../apis/studio";
import { PageBar } from "../components/layout/PageBar";
import { EntityRow } from "../components/entity/EntityRow";
import { MediaThumb } from "../components/media/MediaThumb";
import { useResource } from "../hooks/useResource";
import { useProjectCrumb } from "../hooks/useProjectCrumb";
import { formatDate } from "../utils/format";
import { objectPath, scenePath } from "../utils/location";

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
  const { data, loading, error } = useResource(["movie", movieId], load);
  const crumbs = useProjectCrumb(data?.project ?? "");

  if (loading) {
    return (
      <>
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading movie" />
        </div>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <Alert.Root intent="danger">
          <Alert.Title>Could not open this movie</Alert.Title>
          <Alert.Description>{error ?? "It may have been deleted."}</Alert.Description>
        </Alert.Root>
      </>
    );
  }

  return (
    <>
      <PageBar crumbs={crumbs}>
        <Text variant="display">{data.title || data.slug}</Text>
        <Badge intent="neutral">{data.status}</Badge>
        <Text variant="caption" tone="muted">
          {formatDate(data.created)}
        </Text>
      </PageBar>

      {data.output && (
        <section className="flex flex-col gap-2">
          <Text variant="title">The piece</Text>
          <button
            type="button"
            onClick={() => navigate(objectPath(data.output!.node))}
            className="w-full max-w-2xl overflow-hidden rounded-md border border-line bg-card
                       focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <MediaThumb
              nodeId={data.output.node}
              url={data.output.url}
              name={data.output.name}
              isVideo
              aspect="video"
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
              <EntityRow
                key={scene.id}
                index={index + 1}
                title={scene.title || scene.slug}
                subtitle={scene.slug}
                status={scene.status}
                thumb={scene.thumb ?? null}
                onOpen={() => navigate(scenePath(scene.id))}
              />
            ))}
          </div>
        )}
      </section>
    </>
  );
}

