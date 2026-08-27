import { useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Spinner, Text } from "@ansavva/design-system";

import { getScene, patchShot } from "../apis/studio";
import { PageBar } from "../components/layout/PageBar";
import { MediaThumb } from "../components/media/MediaThumb";
import { ShotCard } from "../components/scene/ShotCard";
import { isBracketed } from "../components/scene/Sends";
import { useResource } from "../hooks/useResource";
import { useProjectCrumb } from "../hooks/useProjectCrumb";
import type { RunAsset, Shot } from "../types";
import { formatDate } from "../utils/format";
import { objectPath, runPath } from "../utils/location";

/**
 * One scene: the plan, the shots, and the take they were stitched into.
 *
 * A scene exists because models have a duration ceiling — it is shots joined
 * into one continuous take — so what this page has to show is the *plan* beside
 * what has actually been rendered against it. Each shot names the run that
 * rendered it, by id, which is why revising a plan does not strand the work
 * already done: a shot whose `run` still points somewhere is still rendered, no
 * matter what happened to the plan around it.
 *
 * **The stitching itself is not here and never will be.** `ffmpeg` ships in the
 * pipeline wheel and the Lambda has none: `assemble` downloads, stitches locally,
 * uploads the result and patches the record. The API owns the record, not the
 * encode.
 */
export function ScenePage() {
  const { sceneId = "" } = useParams();
  const navigate = useNavigate();

  const load = useCallback(() => getScene(sceneId), [sceneId]);
  const { data, loading, error, setData } = useResource(["scene", sceneId], load);
  const crumbs = useProjectCrumb(data?.project ?? "");
  // Every frame on the board opens into the scene, so the viewer scrolls the
  // storyboard in cut order — the handoff, the panels, then the clip — rather
  // than whatever folder the files were written to.
  const openFrame = useCallback(
    (asset: RunAsset) => navigate(objectPath(asset.node, { in: "scene", id: sceneId })),
    [navigate, sceneId],
  );

  // The route answers with the merged shot, so the page swaps that one row in
  // rather than refetching the scene — a re-GET would re-sign every panel URL
  // on the board to show one reworded sentence.
  const saveShot = useCallback(
    async (shotId: string, body: Partial<Shot>) => {
      const updated = await patchShot(sceneId, shotId, body);
      setData((current) =>
        current
          ? {
              ...current,
              shots: current.shots.map((s) =>
                s.id === shotId ? { ...s, ...updated } : s,
              ),
            }
          : current,
      );
    },
    [sceneId, setData],
  );

  if (loading) {
    return (
      <>
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading scene" />
        </div>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <Alert.Root intent="danger">
          <Alert.Title>Could not open this scene</Alert.Title>
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
          <Text variant="title">The cut</Text>
          <button
            type="button"
            onClick={() =>
              navigate(objectPath(data.output!.node, { in: "scene", id: sceneId }))
            }
            className="w-full max-w-md overflow-hidden rounded-md border border-line bg-card
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

      {data.setting && (
        <section className="flex flex-col gap-1">
          <Text variant="title">Setting</Text>
          {/* Prepended byte-identically to every panel prompt, which is what
              makes seven separately rendered panels agree on one room. Shown
              once here for the same reason it is written once there. */}
          <Text variant="body" tone="muted" className="max-w-prose">
            {data.setting}
          </Text>
        </section>
      )}

      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <Text variant="title">Storyboard</Text>
          <Badge intent="neutral">{isBracketed(data.shots) ? "bracketed" : "chained"}</Badge>
          <Text variant="caption" tone="muted">
            {data.shots.length} shot{data.shots.length === 1 ? "" : "s"}
            {plannedRuntime(data.shots) ? ` · ${plannedRuntime(data.shots)}s planned` : ""}
            {isBracketed(data.shots)
              ? " · each shot pinned at both ends"
              : " · each shot opens on the last frame of the one before"}
          </Text>
        </div>
        {data.shots.length === 0 ? (
          <Text variant="body" tone="muted">
            Nothing planned yet.
          </Text>
        ) : (
          <div className="flex flex-col gap-3">
            {[...data.shots]
              .sort((a, b) => a.order - b.order)
              .map((shot, index) => (
                <ShotCard
                  key={shot.id}
                  shot={shot}
                  n={index + 1}
                  bracketed={isBracketed(data.shots)}
                  onOpenRun={(run) => navigate(runPath(data.project, run))}
                  onView={openFrame}
                  onSave={saveShot}
                />
              ))}
          </div>
        )}
      </section>

    </>
  );
}

/*
 * `FrameViewer` was here — a right-hand `Drawer` holding one frame at 75vh.
 *
 * It existed because opening a frame "would work and loses your place on the
 * board", which was true when the only alternative was the folder browser: a
 * storyboard tile led to the file tree, and back was a different screen. The
 * viewer is a screen with an address now, so `/o/<node>?in=scene:<id>` keeps
 * the board one back-press away AND makes the frame linkable — which a drawer
 * never was. It also could not be made fullscreen: `Drawer` portals to
 * `<body>`, and nothing portalled is painted inside a fullscreen element.
 */

/** The planned runtime, which is what a scene will cost time-wise once shot. */
function plannedRuntime(shots: Shot[]): number {
  return shots.reduce((total, shot) => total + (shot.motion?.duration ?? shot.duration ?? 0), 0);
}
