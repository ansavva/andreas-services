import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Button, Text } from "@ansavva/design-system";

import { EmptyState } from "../components/common/EmptyState";
import { LoadError } from "../components/common/LoadError";
import { PageLoading } from "../components/common/PageLoading";
import { deleteScene, getScene, patchScene, patchShot } from "../apis/studio";
import { AutoTextarea } from "../components/common/AutoTextarea";
import { ConfirmDestroyDialog } from "../components/common/ConfirmDestroyDialog";
import { PageBar } from "../components/layout/PageBar";
import { Backlinks } from "../components/common/Backlinks";
import { OutputPanel } from "../components/media/OutputPanel";
import { ShotCard } from "../components/scene/ShotCard";
import { isBracketed } from "../components/scene/Sends";
import { useResource } from "../hooks/useResource";
import { useProjectCrumb } from "../hooks/useProjectCrumb";
import type { RunAsset, Shot } from "../types";
import { formatDate } from "../utils/format";
import { moviePath, objectPath, projectPath, runPath } from "../utils/location";

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
  const { data, loading, error, reload, setData } = useResource(
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
  /**
   * The setting, which was readable and not editable.
   *
   * It is the one field on a scene a person actually revises — prepended
   * byte-identically to every panel prompt, so it is the single lever that
   * keeps separately rendered panels agreeing on one room — and the only way to
   * change it was to re-ingest the whole plan from a JSON file.
   */
  /** The delete dialog, opened from the page bar's menu rather than drawn loose. */
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editingSetting, setEditingSetting] = useState(false);
  const [settingDraft, setSettingDraft] = useState("");
  const [settingSaving, setSettingSaving] = useState(false);
  const [settingError, setSettingError] = useState<string | null>(null);

  const saveSetting = useCallback(async () => {
    setSettingSaving(true);
    setSettingError(null);
    try {
      const updated = await patchScene(sceneId, { setting: settingDraft });
      // The route answers with the whole scene, but only this field moved —
      // merging rather than replacing keeps every presigned panel URL on the
      // board alive instead of re-signing the lot to show one sentence.
      setData((current) =>
        current ? { ...current, setting: updated.setting } : current,
      );
      setEditingSetting(false);
    } catch (err) {
      setSettingError((err as Error).message);
    } finally {
      setSettingSaving(false);
    }
  }, [sceneId, setData, settingDraft]);

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

  /** A scene that has not been cut has nothing for the second column. */
  const hasCut = Boolean(data.output) || (data.cuts ?? []).length > 0;

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
            {/* **How the scene is built belongs with what it is called.** This
                sat over the shots as its own ruled row, which made it read as
                a section heading for them — but `chained`, the shot count and
                the planned runtime are facts about the SCENE, the same kind
                of thing as its status and its date, and this is where those
                already are. */}
            <Badge intent="neutral" className="font-mono">
              {isBracketed(data.shots) ? "bracketed" : "chained"}
            </Badge>
            <Text variant="caption" tone="muted" className="font-mono">
              {formatDate(data.created)}
            </Text>
            <Text variant="caption" tone="muted" family="mono">
              {data.shots.length} shot{data.shots.length === 1 ? "" : "s"}
              {plannedRuntime(data.shots)
                ? ` · ${plannedRuntime(data.shots)}s planned`
                : ""}
              {isBracketed(data.shots)
                ? " · each shot pinned at both ends"
                : " · each shot opens on the last frame of the one before"}
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
        summary="Its shots and its folder go with it. Any movie already cut from it keeps its own copy of the piece."
        confirmWord={data.name}
        onConfirm={async () => {
          await deleteScene(data.id, "delete");
          navigate(projectPath(data.project));
        }}
      />

      {/* **The cut leads, at full width.** It IS the scene — every shot below
          is an account of how it was made — so it is not a column beside the
          storyboard, it is what the storyboard produced.

          The split that matters on this page is one level down, inside each
          shot, where that shot's own inputs and its own output sit side by
          side. A page-level split was the wrong reading of the run screen: a
          run has one payload and one output, a scene has a result and then N
          shots that each have both. */}
      {hasCut && (
        <section className="flex flex-col gap-3">
          <Text variant="title" className="border-b border-line pb-2">
            {(data.cuts ?? []).length > 0 ? "Cuts" : "The cut"}
          </Text>
          {/* **Every cut, newest first, not just the current one.** Assembling
              is not a one-shot act: a shot gets re-rendered and the scene is
              cut again, and comparing the two is the reason for doing it. An
              older cut overwritten in place would survive only as an S3 object
              version, which is recoverable and not something anyone can look
              at. */}
          <div className="flex flex-col gap-3">
            {[
              ...(data.output ? [{ asset: data.output, current: true }] : []),
              ...(data.cuts ?? []).map((asset) => ({
                asset,
                current: false,
              })),
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

      <div className="flex min-w-0 flex-col gap-6">
        {/* **One block that says what this scene is, then the shots.**
            It was three competing headings — `Setting` over one paragraph,
            `Storyboard` over the shots — each with its own rule, so the page
            read as three sections of which two were labels for a sentence. A
            scene IS its shots, and `Setting` is jargon for a description that
            happens to be locked.

            So: what it looks like, then how it is built, under one rule, and
            the shots after it. Both lines are muted and neither is a heading —
            the scene's own name at the top is the heading. */}
        <section className="flex flex-col gap-3">
          {/* The description, and it earns its place twice: it is what the
              scene looks like, and it is prepended byte-identically to every
              panel prompt, which is what makes separately rendered panels agree
              on one room. Editable for that second reason — it is the lever,
              not a caption. */}
          {editingSetting ? (
            <div className="flex max-w-prose flex-col gap-2">
              {settingError && (
                <Alert.Root intent="danger">
                  <Alert.Title>Could not save the setting</Alert.Title>
                  <Alert.Description>{settingError}</Alert.Description>
                </Alert.Root>
              )}
              <AutoTextarea
                value={settingDraft}
                onValueChange={setSettingDraft}
                minRows={3}
                aria-label="Setting"
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() => void saveSetting()}
                  disabled={settingSaving}
                >
                  {settingSaving ? "Saving…" : "Save"}
                </Button>
                <Button
                  intent="secondary"
                  size="sm"
                  onClick={() => setEditingSetting(false)}
                  disabled={settingSaving}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex max-w-prose flex-col items-start gap-1">
              {data.setting ? (
                <Text variant="body" tone="muted">
                  {data.setting}
                </Text>
              ) : (
                <EmptyState
                  title="No setting yet."
                  hint="Where every shot in this scene happens, carried into each one's prompt."
                />
              )}
              <Button
                intent="secondary"
                size="sm"
                onClick={() => {
                  setSettingDraft(data.setting ?? "");
                  setSettingError(null);
                  setEditingSetting(true);
                }}
              >
                Edit the setting
              </Button>
            </div>
          )}

          {data.shots.length === 0 ? (
            <EmptyState
              title="No shots yet."
              hint="A scene is shots stitched into one continuous take."
            />
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
                    runHref={(run) => runPath(data.project, run)}
                    onView={openFrame}
                    // The scene owns the `?in=` context, so it is the scene
                    // that can name a frame's address — a shot knows only the
                    // asset.
                    frameHref={(asset) =>
                      objectPath(asset.node, { in: "scene", id: sceneId })
                    }
                    onSave={saveShot}
                  />
                ))}
            </div>
          )}
        </section>

        <Backlinks label="Cut into" links={data.movies} to={moviePath} />
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
