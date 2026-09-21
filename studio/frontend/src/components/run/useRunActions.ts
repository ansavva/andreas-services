import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { useToast } from "@ansavva/design-system";

import { deleteRun, getAsset, getModels, getRun, getScene, setSceneRuns } from "../../apis/studio";
import { useCreateBar, type AttachRole } from "../../context/CreateBarContext";
import { useFrameGrab } from "../../hooks/useFrameGrab";
import { useCopyToClipboard } from "../../hooks/useCopyToClipboard";
import { useFavorites } from "../../hooks/useFavorites";
import { useResource } from "../../hooks/useResource";
import type { RunAsset, RunFeedRow } from "../../types";
import { objectPath, projectPath, runPath } from "../../utils/location";
import { FEED_QUERIES, patchFeedRows } from "./feedCache";
import { useRunAgain } from "./RunAgainButton";
import { promptText, refOfOutput, seedFromRow, seedWithOutput } from "./seed";

/**
 * The Replicate id of the one model in the registry that restores rather than
 * generates. Looked up by `model` rather than by key, because the key is the
 * registry's spelling and this is the provider's — the one `POST /api/runs`
 * records.
 */
export const UPSCALE_MODEL = "topazlabs/image-upscale";

/**
 * Everything a run's row and a run's rail can do, in one place.
 *
 * Two screens draw these — the feed row's icon+word actions and its tile
 * overlays, and the opened run's uniform grid — and a gesture that spends
 * money or hands something to the create bar has to mean the same thing in
 * both. Most of them are one call into `useCreateBar`: the bar is where a new
 * run is authored, so Edit, Again, Upscale and Animate all LOAD the bar rather
 * than creating anything. Nothing here submits except `rerun`, which is the
 * armed two-press gesture `useRunAgain` owns.
 */
export function useRunActions(row: RunFeedRow) {
  const bar = useCreateBar();
  const frameGrab = useFrameGrab();
  const navigate = useNavigate();
  const toast = useToast();
  const client = useQueryClient();
  const { copy } = useCopyToClipboard();
  const again = useRunAgain(row);
  // An output is a node, so the heart on it is the same heart as on a
  // browsed file: one cached id set for the app, `isFavorite` per line. Here
  // rather than in `outputMenu`, which is a plain function every tile calls.
  const favorites = useFavorites();
  // Read lazily by whoever mounts first and shared by key; the registry is
  // one request for the whole feed, not one per row.
  const models = useResource(["models"], useCallback(() => getModels(), []));

  /** Load this run into the bar, whole — the prompt, the params, the sends. */
  const edit = useCallback(() => bar.loadRun(seedFromRow(row)), [bar, row]);

  /**
   * Run this again with one of its outputs attached — a still goes in as a
   * reference, a clip's frame as the start of the next.
   */
  const outputAgain = useCallback(
    (asset: RunAsset, index: number) =>
      bar.loadRun(seedWithOutput(row, asset, index, row.kind === "video" ? "start" : "reference")),
    [bar, row],
  );

  /**
   * An image run on the upscaler with this output as its input. The registry
   * names the upscaler's one image slot `start` (`images.start: "image"`), so
   * that is the role the attachment carries.
   */
  const upscale = useCallback(
    (asset: RunAsset, index: number) => {
      const entry = Object.values(models.data ?? {}).find((each) => each.model === UPSCALE_MODEL);
      if (!entry) {
        toast.add({ intent: "danger", title: "Could not find the upscale model" });
        return;
      }
      bar.loadRun({
        project: row.project,
        kind: "image",
        model: entry.model,
        attachments: [{ ref: refOfOutput(row, asset, index), role: "start" }],
      });
    },
    [bar, models.data, row, toast],
  );

  /**
   * Add this output to whatever the bar holds — as a reference, a start
   * frame or an end frame. A frame switches the bar to video and replaces
   * the frame it held; a reference accumulates (`holdsOne`).
   *
   * **`Start frame` used to LOAD a fresh video run holding only this
   * picture**, while `Use as reference` attached to whatever was there, and
   * nothing offered an end frame at all. Three roles, one gesture: attach.
   */
  const useAs = useCallback(
    (asset: RunAsset, index: number, role: AttachRole) =>
      bar.attach(refOfOutput(row, asset, index), role),
    [bar, row],
  );

  /**
   * A frame of a clip to the bar, in the role — the first by default, or the
   * one at `at` seconds, which the opened run reads off its player. The
   * worker takes the still into the project's input pool and `useFrameGrab`
   * attaches it; the ref still says which run's output it was cut from.
   */
  const frameAs = useCallback(
    (asset: RunAsset, index: number, role: AttachRole, at = 0) =>
      frameGrab.take(refOfOutput(row, asset, index), role, at),
    [frameGrab, row],
  );

  /**
   * Signed with `response-content-disposition: attachment` server-side. A
   * plain `<a download>` would be ignored here, because the presigned URL is
   * cross-origin to this app.
   */
  const download = useCallback(async (asset: RunAsset) => {
    const signed = await getAsset(asset.node, "attachment");
    window.location.assign(signed.url);
  }, []);

  /**
   * Delete the run, keeping its folder — the route's default. The feed and
   * the project's counts are re-read; a lightbox open on it goes back to the
   * project.
   */
  const remove = useCallback(async () => {
    await deleteRun(row.id);
    // A draft the bar was editing: it is gone, so the bar stops writing to it.
    bar.forget(row.id);
    await Promise.all([
      client.invalidateQueries({ queryKey: ["runs"] }),
      client.invalidateQueries({ queryKey: ["project", row.project] }),
    ]);
    if (window.location.pathname === runPath(row.project, row.id)) {
      navigate(projectPath(row.project) + window.location.search, { replace: true });
    }
  }, [bar, client, navigate, row.id, row.project]);

  /**
   * Ask the API what the run is NOW, and draw that.
   *
   * The feed learns about a run in flight from `useRunWatch`, and the opened
   * run polls its own record — both stop the moment the status is terminal,
   * and neither can see a callback that landed while the tab was asleep or a
   * run wedged in `pending` whose watch has given up. This is the press that
   * asks anyway. One `GET /api/runs/<id>`, written to the record's own key
   * (the opened run reads it there) and into every feed page holding the row
   * (the feed reads it there), unconditionally — the press is the ask.
   */
  const [refreshing, setRefreshing] = useState(false);
  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const record = await client.fetchQuery({
        queryKey: ["run", row.id],
        queryFn: () => getRun(row.id),
        staleTime: 0,
      });
      patchFeedRows(client, FEED_QUERIES, [record], () => true);
    } catch (err) {
      toast.add({
        intent: "danger",
        title: "Could not refresh the run",
        description: (err as Error).message,
      });
    } finally {
      setRefreshing(false);
    }
  }, [client, row.id, toast]);

  const copyPrompt = useCallback(
    () => void copy(promptText(row.plan?.prompt) ?? ""),
    [copy, row.plan],
  );

  /**
   * Append this clip to its scene's cut. Only a succeeded video run that is IN
   * a scene has the gesture — the cut names runs, and a still or a run in no
   * scene has nothing to be appended to. The cut is read and re-sent whole:
   * `PATCH /scenes/<id>/runs` is a replace, and a reprise is legal, so a run
   * already in the cut goes in again rather than being refused.
   */
  const canAddToCut = Boolean(row.scene) && row.kind === "video" && row.status === "succeeded";
  const addToCut = useCallback(async () => {
    if (!row.scene) return;
    try {
      const scene = await getScene(row.scene);
      await setSceneRuns(row.scene, [...scene.runs.map((each) => each.id), row.id]);
      toast.add({ intent: "success", title: "Added to the cut", description: scene.name });
      await client.invalidateQueries({ queryKey: ["scene", row.scene] });
    } catch (err) {
      toast.add({ intent: "danger", title: "Could not add to the cut",
                  description: (err as Error).message });
    }
  }, [client, row.id, row.scene, toast]);

  /** The run, opened with its Request row already expanded. */
  const openRequest = useCallback(
    () => navigate(runPath(row.project, row.id) + window.location.search, { state: { request: true } }),
    [navigate, row.id, row.project],
  );

  /**
   * Where the run's files are. The feed row carries no folder node, so it
   * links to the first output in the viewer, scrolling the run's own files;
   * the rail, which holds the whole record, links to the folder itself.
   */
  const folderHref = row.outputs[0]
    ? objectPath(row.outputs[0].node, { in: "run", id: row.id })
    : null;

  return {
    rerun: again.fire,
    rerunFailure: again.failure,
    edit,
    outputAgain,
    upscale,
    useAs,
    frameAs,
    download,
    isFavorite: favorites.isFavorite,
    toggleFavorite: favorites.toggle,
    remove,
    refresh,
    refreshing,
    copyPrompt,
    openRequest,
    folderHref,
    canAddToCut,
    addToCut,
  };
}
