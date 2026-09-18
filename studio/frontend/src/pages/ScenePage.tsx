import { useCallback, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Badge, Button, Text, useToast } from "@ansavva/design-system";

import { deleteScene, getScene, setSceneRuns } from "../apis/studio";
import { Backlinks } from "../components/common/Backlinks";
import { ConfirmDestroyDialog } from "../components/common/ConfirmDestroyDialog";
import { EmptyState } from "../components/common/EmptyState";
import { ArrowDownIcon, ArrowUpIcon, CloseIcon, TrashIcon } from "../components/common/icons";
import { LoadError } from "../components/common/LoadError";
import { PageLoading } from "../components/common/PageLoading";
import { EntityRow } from "../components/entity/EntityRow";
import { PageBar } from "../components/layout/PageBar";
import { OutputPanel } from "../components/media/OutputPanel";
import { RunFeed } from "../components/project/RunFeed";
import { useProjectCrumb } from "../hooks/useProjectCrumb";
import { useResource } from "../hooks/useResource";
import type { SceneCut, SceneRecord } from "../types";
import { formatDate } from "../utils/format";
import { moviePath, objectPath, projectPath, runPath } from "../utils/location";

/**
 * One scene: the cut, the runs made for it, and the take they were stitched
 * into.
 *
 * A scene is a named, ordered series of runs and nothing else. The **cut** is
 * the video runs in stitch order — the whole of the plan, and it may name a
 * run that has not rendered yet. The **runs** below it are every run that
 * belongs to the scene, stills and clips alike, drawn by the same feed the
 * project draws, narrowed by `?scene=`; the create bar on this page files new
 * runs under it.
 *
 * **There was a storyboard here** — shots with panels, a motion prompt each,
 * a setting prepended to every panel — and every one of those was a run
 * wearing a second record. The plan was kept in step with the runs by hand,
 * and it drifted. So the cut is the plan, and the runs are the runs.
 */
export function ScenePage() {
  const { sceneId = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const toast = useToast();

  const load = useCallback(() => getScene(sceneId), [sceneId]);
  const { data, loading, error, reload, setData } = useResource(
    ["scene", sceneId],
    load,
  );
  const crumbs = useProjectCrumb(data?.project ?? "");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  /**
   * Rewrite the cut and merge the answer in. The route replies with the cut
   * as rows — the same shape the record carries — so the page swaps that one
   * field rather than refetching the scene, which would re-sign every URL on
   * it to show one row moved.
   */
  const setCut = useCallback(
    async (runs: string[]) => {
      setSaving(true);
      try {
        const written = await setSceneRuns(sceneId, runs);
        setData((current) => (current ? { ...current, runs: written.runs } : current));
      } catch (err) {
        toast.add({
          intent: "danger",
          title: "Could not change the cut",
          description: (err as Error).message,
        });
      } finally {
        setSaving(false);
      }
    },
    [sceneId, setData, toast],
  );

  /** Open a run in the lightbox, with the feed still narrowed to this scene. */
  const openRun = useCallback(
    (row: { id: string; project: string }, output?: number) =>
      navigate(runPath(row.project, row.id) + `?scene=${encodeURIComponent(sceneId)}`, {
        state: output === undefined ? undefined : { output },
      }),
    [navigate, sceneId],
  );

  if (loading) return <PageLoading label="Loading scene" />;

  if (error || !data) {
    return (
      <LoadError
        what="this scene"
        message={error ?? "It may have been deleted."}
        onRetry={reload}
        escape={{ label: "Back to home", onClick: () => navigate("/") }}
      />
    );
  }

  const hasCut = Boolean(data.output) || (data.cuts ?? []).length > 0;
  const ids = data.runs.map((row) => row.id);
  const rendered = data.runs.filter((row) => row.output).length;

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
            <Text variant="caption" tone="muted" family="mono">
              {data.runs.length} in the cut
              {data.runs.length > 0 && rendered < data.runs.length
                ? ` · ${data.runs.length - rendered} not rendered yet`
                : ""}
            </Text>
          </>
        }
        menu={[{
              label: "Delete",
              icon: <TrashIcon className="size-4 shrink-0 fill-none stroke-current stroke-[1.5]" />,
              danger: true,
              onSelect: () => setDeleteOpen(true),
            }]}
      />

      <ConfirmDestroyDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        label="Delete"
        title={`Delete ${data.name}?`}
        summary="Its folder and its cuts go with it. The runs made for it stay in the project, and stop naming it."
        confirmWord={data.name}
        onConfirm={async () => {
          await deleteScene(data.id, "delete");
          void client.invalidateQueries({ queryKey: ["runs"] });
          navigate(projectPath(data.project));
        }}
      />

      {/* **The take leads, at full width.** It IS the scene — everything
          below is an account of how it was made. Every cut, newest first:
          assembling is not a one-shot act, and comparing two takes is the
          reason for re-cutting. */}
      {hasCut && (
        <section className="flex flex-col gap-3">
          <Text variant="title" className="border-b border-line pb-2">
            {(data.cuts ?? []).length > 0 ? "Takes" : "The take"}
          </Text>
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
      )}

      <section className="flex flex-col gap-3">
        <Text variant="title" className="border-b border-line pb-2">
          The cut
        </Text>
        {data.runs.length === 0 ? (
          <EmptyState
            title="Nothing in the cut yet."
            hint="A scene is its clips in order. Make a video run below, or add one from its ⋯ menu."
          />
        ) : (
          <div className="flex flex-col">
            {data.runs.map((row, index) => (
              <CutRow
                key={`${row.id}-${index}`}
                row={row}
                index={index}
                count={data.runs.length}
                disabled={saving}
                to={runPath(data.project, row.id) + `?scene=${encodeURIComponent(sceneId)}`}
                onMove={(delta) => {
                  const next = [...ids];
                  next.splice(index + delta, 0, ...next.splice(index, 1));
                  void setCut(next);
                }}
                onRemove={() => void setCut(ids.filter((_, at) => at !== index))}
              />
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <Text variant="title" className="border-b border-line pb-2">
          Runs
        </Text>
        {/* The same feed the project draws, narrowed by the URL's `?scene=`
            — which `useFeedFilters` reads, and which the lightbox opened from
            here keeps, so Left/Right step through this scene's rows. */}
        <SceneFeed record={data} onOpen={openRun} />
      </section>

      <Backlinks label="Cut into" links={data.movies} to={moviePath} />
    </>
  );
}

/**
 * One row of the cut. Its position is the fact — the arrows write the whole
 * list back — and a run that has not rendered draws as a row with no clip,
 * which is what a planned cut looks like.
 */
function CutRow({
  row,
  index,
  count,
  disabled,
  to,
  onMove,
  onRemove,
}: {
  row: SceneCut;
  index: number;
  count: number;
  disabled: boolean;
  to: string;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
}) {
  const clip = row.output;
  return (
    <EntityRow
      index={index + 1}
      title={row.model ?? row.id}
      subtitle={row.created ? formatDate(row.created) : row.id}
      mono
      status={row.status ?? "missing"}
      thumb={clip?.url ? { node: clip.node, url: clip.url, isVideo: true, poster: clip.poster } : { placeholder: "not rendered" }}
      to={to}
      trailing={
        <div className="flex items-center gap-1">
          <Button
            intent="secondary"
            size="sm"
            aria-label="Move up"
            disabled={disabled || index === 0}
            onClick={() => onMove(-1)}
          >
            <ArrowUpIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
          </Button>
          <Button
            intent="secondary"
            size="sm"
            aria-label="Move down"
            disabled={disabled || index === count - 1}
            onClick={() => onMove(1)}
          >
            <ArrowDownIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
          </Button>
          <Button
            intent="secondary"
            size="sm"
            aria-label="Remove from the cut"
            disabled={disabled}
            onClick={onRemove}
          >
            <CloseIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
          </Button>
        </div>
      }
    />
  );
}

/**
 * The scene's runs, as the project feed draws them.
 *
 * The feed reads `?scene=` off the URL, so this pins it there while the page
 * is up: a scene page with the param missing would be the whole project's
 * feed under a heading that says otherwise.
 */
function SceneFeed({
  record,
  onOpen,
}: {
  record: SceneRecord;
  onOpen: (row: { id: string; project: string }, output?: number) => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  if (params.get("scene") !== record.id) {
    params.set("scene", record.id);
    navigate({ search: `?${params}` }, { replace: true });
    return null;
  }
  return (
    <RunFeed
      projectId={record.project}
      characters={[]}
      heroes={{}}
      onOpen={onOpen}
    />
  );
}
