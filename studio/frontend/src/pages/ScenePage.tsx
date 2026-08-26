import { useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Button, Collapsible, Spinner, Text } from "@ansavva/design-system";

import { getScene } from "../apis/studio";
import { AppHeader } from "../components/common/AppHeader";
import { useResource } from "../hooks/useResource";
import type { RunAsset, Shot } from "../types";
import { formatDate } from "../utils/format";
import { objectPath, projectPath, runPath } from "../utils/location";

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
  const { data, loading, error } = useResource(load);

  if (loading) {
    return (
      <Shell>
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading scene" />
        </div>
      </Shell>
    );
  }

  if (error || !data) {
    return (
      <Shell>
        <Alert.Root intent="danger">
          <Alert.Title>Could not open this scene</Alert.Title>
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
          <Text variant="title">The cut</Text>
          <button
            type="button"
            onClick={() => navigate(objectPath(data.output!.node))}
            className="w-full max-w-md overflow-hidden rounded-md border border-line bg-card
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
          <Text variant="caption" tone="muted">
            {data.shots.length} shot{data.shots.length === 1 ? "" : "s"}
            {plannedRuntime(data.shots) ? ` · ${plannedRuntime(data.shots)}s planned` : ""}
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
                  onOpenRun={(run) => navigate(runPath(data.project, run))}
                  onOpenNode={(node) => navigate(objectPath(node))}
                />
              ))}
          </div>
        )}
      </section>
    </Shell>
  );
}

/** The planned runtime, which is what a scene will cost time-wise once shot. */
function plannedRuntime(shots: Shot[]): number {
  return shots.reduce((total, shot) => total + (shot.motion?.duration ?? shot.duration ?? 0), 0);
}

/**
 * One shot: what it is, the frames it is made of, and what it rendered into.
 *
 * The layout carries two axes on purpose — the cards run down the page in cut
 * order, and each card's filmstrip runs across it in the order the images reach
 * the model: the frame it opens on, then its panels, then the clip that came
 * out. A storyboard read as a list of prompts is what this page used to be, and
 * a list of prompts is the one thing a person cannot judge a shot from.
 */
function ShotCard({
  shot,
  n,
  onOpenRun,
  onOpenNode,
}: {
  shot: Shot;
  n: number;
  onOpenRun: (run: string) => void;
  onOpenNode: (node: string) => void;
}) {
  const panels = shot.panels ?? [];
  const motion = shot.motion;
  const caption = shot.beat || shot.prompt || shot.id;
  const duration = motion?.duration ?? shot.duration;

  return (
    <article className="flex flex-col gap-3 rounded-md border border-line bg-card p-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Text variant="body" tone="muted" className="tabular-nums">
          {String(n).padStart(2, "0")}
        </Text>
        <Text variant="body" className="min-w-48 flex-1 font-medium">
          {caption}
        </Text>
        {shot.status && (
          <Badge intent={shot.status === "rendered" ? "success" : "neutral"}>{shot.status}</Badge>
        )}
        {duration ? <Badge intent="neutral">{duration}s</Badge> : null}
        {motion?.model && <Badge intent="neutral">{motion.model}</Badge>}
        {/* One answer to "has this been shot", not two. `status` is computed
            from the plan and is what a storyboarded scene carries; the badge
            below is for a scene assembled from bare runs, which has no status
            at all. Showing both put `rendered` next to `not rendered` on the
            same card. */}
        {shot.run ? (
          <Button intent="ghost" size="sm" onClick={() => onOpenRun(shot.run as string)}>
            Open its run
          </Button>
        ) : (
          !shot.status && <Badge intent="warning">not rendered</Badge>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {/* The frame this shot opens on. It outranks any panel composed for the
            same moment, so it leads the strip — a cut is only seamless from the
            literal last frame of the shot before it. */}
        {shot.opens_on?.frame && (
          <Frame
            label="opens on"
            hint={shot.continues === false ? "kept its own panel" : "handoff"}
            asset={shot.opens_on.frame}
            onOpen={onOpenNode}
          />
        )}

        {panels.length === 0 && !shot.clip && (
          <Text variant="caption" tone="muted">
            No panels — this shot was added straight from a run.
          </Text>
        )}

        {panels.map((panel) => (
          <Frame
            key={panel.n}
            label={panel.role ?? `panel ${panel.n}`}
            hint={panel.stale ? "stale" : undefined}
            title={panel.prompt}
            asset={panel.image}
            onOpen={onOpenNode}
          />
        ))}

        {shot.clip && <Frame label="clip" asset={shot.clip} onOpen={onOpenNode} />}
      </div>

      {motion?.prompt && (
        <Collapsible.Root>
          <Collapsible.Trigger>
            <Text variant="caption" tone="muted">
              Motion prompt
            </Text>
          </Collapsible.Trigger>
          <Collapsible.Panel>
            {/* Verbatim, and never parsed. It is a serialized JSON prompt whose
                shape the pipeline changes freely — the same rule the run page
                holds for `request.json`. */}
            <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-surface-alt p-2 text-xs whitespace-pre-wrap">
              {motion.prompt}
            </pre>
          </Collapsible.Panel>
        </Collapsible.Root>
      )}
    </article>
  );
}

/**
 * One tile of a shot's filmstrip — an image, a clip, or the space where one is
 * not yet.
 *
 * **A placeholder is the normal state of a board**, not an error: a panel is
 * planned before it is rendered, and the gap is the thing a person is looking
 * for when they ask what still needs shooting. So an unboarded panel draws as a
 * dashed frame carrying its prompt rather than being hidden.
 */
function Frame({
  label,
  hint,
  title,
  asset,
  onOpen,
}: {
  label: string;
  hint?: string;
  title?: string;
  asset?: RunAsset;
  onOpen: (node: string) => void;
}) {
  const isVideo = (asset?.content_type ?? "").startsWith("video/");
  const body = asset?.url ? (
    isVideo ? (
      <video src={asset.url} muted playsInline preload="metadata" className="h-full w-full object-cover" />
    ) : (
      <img src={asset.url} alt="" className="h-full w-full object-cover" />
    )
  ) : (
    <span className="flex h-full w-full items-center justify-center p-1 text-center">
      <Text variant="caption" tone="muted" className="line-clamp-4">
        {title || "not rendered"}
      </Text>
    </span>
  );

  const shell = (
    <span
      className={`block aspect-[3/4] w-24 overflow-hidden rounded-md bg-surface-alt ${
        asset?.url ? "border border-line" : "border border-dashed border-line"
      }`}
    >
      {body}
    </span>
  );

  return (
    <span className="flex w-24 flex-col gap-1">
      {asset?.node ? (
        <button
          type="button"
          onClick={() => onOpen(asset.node)}
          title={title ?? asset.name}
          className="text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          {shell}
        </button>
      ) : (
        <span title={title}>{shell}</span>
      )}
      <span className="flex flex-wrap items-center gap-1">
        <Text variant="caption" tone="muted">
          {label}
        </Text>
        {hint && <Badge intent={hint === "stale" ? "warning" : "neutral"}>{hint}</Badge>}
      </span>
    </span>
  );
}

function Shell({ children, subtitle }: { children: React.ReactNode; subtitle?: string }) {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-6 p-4 sm:p-6">
      <AppHeader subtitle={subtitle ?? "scene"} />
      {children}
    </div>
  );
}
