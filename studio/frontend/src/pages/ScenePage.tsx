import { useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Spinner, Text } from "@ansavva/design-system";

import { getScene, patchShot } from "../apis/studio";
import { PageBar } from "../components/layout/PageBar";
import { Backlinks } from "../components/common/Backlinks";
import { OutputPanel } from "../components/media/OutputPanel";
import { ShotCard } from "../components/scene/ShotCard";
import { isBracketed } from "../components/scene/Sends";
import { useResource } from "../hooks/useResource";
import { useProjectCrumb } from "../hooks/useProjectCrumb";
import type { RunAsset, Shot } from "../types";
import { formatDate } from "../utils/format";
import { moviePath, objectPath, runPath } from "../utils/location";

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
  const { data, loading, error, setData } = useResource(
    ["scene", sceneId],
    load,
  );
  const crumbs = useProjectCrumb(data?.project ?? "");
  // Every frame on the board opens into the scene, so the viewer scrolls the
  // storyboard in cut order — the handoff, the panels, then the clip — rather
  // than whatever folder the files were written to.
  const openFrame = useCallback(
    (asset: RunAsset) =>
      navigate(objectPath(asset.node, { in: "scene", id: sceneId })),
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
          <Alert.Description>
            {error ?? "It may have been deleted."}
          </Alert.Description>
        </Alert.Root>
      </>
    );
  }

  return (
    <>
      <PageBar crumbs={crumbs}>
        <Text variant="display">{data.title || data.slug}</Text>
        <Badge intent="neutral" className="font-mono">
          {data.status}
        </Badge>
        <Text variant="caption" tone="muted" className="font-mono">
          {formatDate(data.created)}
        </Text>
      </PageBar>

      {/* **The same split the run screen takes**, for the same reason: a scene
          has a thing it produced and an account of how, and stacking them put
          the cut — the whole point of the page — under a setting paragraph and
          a storyboard of seven panels.

          The cut is FIRST IN THE DOM, so below `lg` it simply leads and needs
          no `order` override, and above `lg` a `col-start` puts it on the
          right. Identical mechanism to `RunPage`; if one changes, change both. */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:items-start">
        <section className="flex flex-col gap-3 lg:col-start-2 lg:row-start-1">
          <Text variant="title" className="border-b border-line pb-2">
            {(data.cuts ?? []).length > 0 ? "Cuts" : "The cut"}
          </Text>
          {/* **Every cut, newest first, not just the current one.** Assembling
              is not a one-shot act: a shot gets re-rendered and the scene is
              cut again, and comparing the two is the reason for doing it. The
              older cut used to be overwritten in place and survived only as an
              S3 object version, which is recoverable and not something anyone
              can look at. */}
          <div className="flex flex-col gap-3">
            {[
              ...(data.output ? [{ asset: data.output, current: true }] : []),
              ...(data.cuts ?? []).map((asset) => ({ asset, current: false })),
            ].map(({ asset, current }) => (
              <OutputPanel
                key={asset.node}
                asset={asset}
                sole={(data.cuts ?? []).length === 0}
                to={objectPath(asset.node, { in: "scene", id: sceneId })}
                badge={!current && <Badge intent="neutral">earlier</Badge>}
              />
            ))}
          </div>
        </section>

        <div className="flex min-w-0 flex-col gap-6 lg:col-start-1 lg:row-start-1">
          {data.setting && (
            <section className="flex flex-col gap-2">
              <Text variant="title" className="border-b border-line pb-2">
                Setting
              </Text>
              {/* Prepended byte-identically to every panel prompt, which is what
                  makes seven separately rendered panels agree on one room. Shown
                  once here for the same reason it is written once there. */}
              <Text variant="body" tone="muted" className="max-w-prose">
                {data.setting}
              </Text>
            </section>
          )}

          <section className="flex flex-col gap-3">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line pb-2">
              <Text variant="title">Storyboard</Text>
              <Badge intent="neutral" className="font-mono">
                {isBracketed(data.shots) ? "bracketed" : "chained"}
              </Badge>
              <Text variant="caption" tone="muted">
                {data.shots.length} shot{data.shots.length === 1 ? "" : "s"}
                {plannedRuntime(data.shots)
                  ? ` · ${plannedRuntime(data.shots)}s planned`
                  : ""}
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
              <div className="flex flex-col">
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

          <Backlinks label="Cut into" links={data.movies} to={moviePath} />
        </div>
      </div>
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
  return shots.reduce(
    (total, shot) => total + (shot.motion?.duration ?? shot.duration ?? 0),
    0,
  );
}
