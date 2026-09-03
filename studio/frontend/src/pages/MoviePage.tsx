import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Badge, Text } from "@ansavva/design-system";

import { EmptyState } from "../components/common/EmptyState";
import { LoadError } from "../components/common/LoadError";
import { PageLoading } from "../components/common/PageLoading";
import { deleteMovie, getMovie } from "../apis/studio";
import { ConfirmDestroyDialog } from "../components/common/ConfirmDestroyDialog";
import { PageBar } from "../components/layout/PageBar";
import { EntityRow } from "../components/entity/EntityRow";
import { MediaThumb } from "../components/media/MediaThumb";
import { useResource } from "../hooks/useResource";
import { useProjectCrumb } from "../hooks/useProjectCrumb";
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
  const { data, loading, error, reload } = useResource(["movie", movieId], load);
  const crumbs = useProjectCrumb(data?.project ?? "");
  /** The delete dialog, opened from the page bar's menu rather than drawn loose. */
  const [deleteOpen, setDeleteOpen] = useState(false);

  if (loading) return <PageLoading label="Loading movie" />;

  if (error || !data) {
    return (
      <LoadError
        what="this movie"
        message={error ?? "It may have been deleted."}
        onRetry={reload}
        escape={{ label: "Back to home", onClick: () => navigate("/") }}
      />
    );
  }

  return (
    <>
      <PageBar
        crumbs={crumbs}
        title={data.name}
        meta={
          <>
            <Badge intent="neutral" className="font-mono">
              {data.status}
            </Badge>
            <Text variant="caption" tone="muted" className="font-mono">
              {formatDate(data.created)}
            </Text>
          </>
        }
        menu={[{ label: "Delete", danger: true, onSelect: () => setDeleteOpen(true) }]}
      />

      <ConfirmDestroyDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        label="Delete"
        title={`Delete ${data.name}?`}
        summary="Its folder and the cut piece go with it. The scenes it was cut from stay — they hold their own shots and their own cuts."
        confirmWord={data.name}
        onConfirm={async () => {
          await deleteMovie(data.id, "delete");
          navigate(projectPath(data.project));
        }}
      />

      {data.output && (
        <section className="flex flex-col gap-3">
          <Text variant="title" className="border-b border-line pb-2">
            The piece
          </Text>
          <button
            type="button"
            onClick={() => navigate(objectPath(data.output!.node))}
            className="w-full max-w-2xl overflow-hidden rounded-none border border-line bg-card
                       focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <MediaThumb
              nodeId={data.output.node}
              url={data.output.url}
              name={data.output.name}
              isVideo
              aspect="video"
            />
            <Text variant="caption" tone="muted" className="truncate px-2 py-1 font-mono">
              {data.output.name}
            </Text>
          </button>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <Text variant="title" className="border-b border-line pb-2">
          Scenes
        </Text>
        {data.scenes.length === 0 ? (
          <EmptyState title="No scenes yet." hint="A movie is scenes cut into one piece." />
        ) : (
          <div className="flex flex-col">
            {data.scenes.map((scene, index) => (
              <EntityRow
                key={scene.id}
                index={index + 1}
                title={scene.name}
                // The date, not the name a second time — the row already
                // carries the title once.
                subtitle={formatDate(scene.created)}
                status={scene.status}
                thumb={scene.thumb ?? null}
                to={scenePath(scene.id)}
              />
            ))}
          </div>
        )}
      </section>
    </>
  );
}
