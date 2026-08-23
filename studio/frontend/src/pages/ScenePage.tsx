import { useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Button, Spinner, Text } from "@ansavva/design-system";

import { getScene } from "../apis/studio";
import { AppHeader } from "../components/common/AppHeader";
import { useResource } from "../hooks/useResource";
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

      <section className="flex flex-col gap-2">
        <Text variant="title">Shots</Text>
        {data.shots.length === 0 ? (
          <Text variant="body" tone="muted">
            Nothing planned yet.
          </Text>
        ) : (
          <div className="flex flex-col gap-2">
            {[...data.shots]
              .sort((a, b) => a.order - b.order)
              .map((shot, index) => (
                <div
                  key={shot.id}
                  className="flex flex-wrap items-start gap-3 rounded-md border border-line bg-card p-3"
                >
                  <Text variant="body" className="w-8 shrink-0 text-right tabular-nums">
                    {index + 1}
                  </Text>
                  <Text variant="body" className="min-w-48 flex-1">
                    {shot.prompt}
                  </Text>
                  {shot.panel && <Badge intent="neutral">{shot.panel}</Badge>}
                  {shot.run ? (
                    <Button
                      intent="ghost"
                      size="sm"
                      onClick={() => navigate(runPath(data.project, shot.run as string))}
                    >
                      Open its run
                    </Button>
                  ) : (
                    <Badge intent="warning">not rendered</Badge>
                  )}
                </div>
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
      <AppHeader subtitle={subtitle ?? "scene"} />
      {children}
    </div>
  );
}
