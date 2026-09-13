import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { useToast } from "@ansavva/design-system";

import { deleteRun, getAsset, getModels } from "../../apis/studio";
import { useCreateBar, type AttachRole } from "../../context/CreateBarContext";
import { useFirstFrame } from "../../hooks/useFirstFrame";
import { useCopyToClipboard } from "../../hooks/useCopyToClipboard";
import { useResource } from "../../hooks/useResource";
import type { RunAsset, RunFeedRow } from "../../types";
import { objectPath, projectPath, runPath } from "../../utils/location";
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
  const firstFrame = useFirstFrame();
  const navigate = useNavigate();
  const toast = useToast();
  const client = useQueryClient();
  const { copy } = useCopyToClipboard();
  const again = useRunAgain(row);
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
   * A clip's FIRST FRAME to the bar, in the role. The worker takes the still
   * into the project's input pool and `useFirstFrame` attaches it; the ref
   * still says which run's output it was cut from.
   */
  const firstFrameAs = useCallback(
    (asset: RunAsset, index: number, role: AttachRole) =>
      firstFrame.take(refOfOutput(row, asset, index), role),
    [firstFrame, row],
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
    await Promise.all([
      client.invalidateQueries({ queryKey: ["runs"] }),
      client.invalidateQueries({ queryKey: ["project", row.project] }),
    ]);
    if (window.location.pathname === runPath(row.project, row.id)) {
      navigate(projectPath(row.project) + window.location.search, { replace: true });
    }
  }, [client, navigate, row.id, row.project]);

  const copyPrompt = useCallback(
    () => void copy(promptText(row.plan?.prompt) ?? ""),
    [copy, row.plan],
  );

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
    firstFrameAs,
    download,
    remove,
    copyPrompt,
    openRequest,
    folderHref,
  };
}
