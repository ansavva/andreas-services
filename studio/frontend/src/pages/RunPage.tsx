import { useCallback, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Button, Spinner, Text } from "@ansavva/design-system";

import { getNodeText, getRun } from "../apis/studio";
import { PageBar } from "../components/layout/PageBar";
import { MediaThumb } from "../components/media/MediaThumb";
import { useResource } from "../hooks/useResource";
import { useProjectCrumb } from "../hooks/useProjectCrumb";
import { formatBytes, formatDate, formatTextContent } from "../utils/format";
import type { RunAsset } from "../types";
import { objectPath, runPath } from "../utils/location";

/**
 * One run: what studio recorded about it, what came out, and — separately, and
 * verbatim — what was sent to the provider and what came back.
 *
 * **That separation is the rule the entity model preserved rather than removed.**
 * Everything above `payload` is studio's own envelope: the status, the model, the
 * bindings as node ids, the outputs, the cost, the lineage. It is validated, it
 * is queryable, and it is safe to render as fields. The request and response
 * bodies are the provider's, the pipeline changes their shape freely, and this
 * page shows them as **text and nothing else**. It does not parse them, it does
 * not pick fields out of them, and it must not start.
 */
export function RunPage() {
  const { projectId = "", runId = "" } = useParams();
  const navigate = useNavigate();

  const load = useCallback(() => getRun(runId), [runId]);
  const { data, loading, error } = useResource(load);
  const crumbs = useProjectCrumb(projectId);

  // Every frame on this page opens into the run, so scrolling the viewer walks
  // what the run produced and was given rather than the folder those files
  // happen to sit in.
  const RUN = useMemo(() => ({ in: "run" as const, id: runId }), [runId]);

  if (loading) {
    return (
      <>
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading run" />
        </div>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <Alert.Root intent="danger">
          <Alert.Title>Could not open this run</Alert.Title>
          <Alert.Description>{error ?? "It may have been deleted."}</Alert.Description>
        </Alert.Root>
      </>
    );
  }

  return (
    <>
      {/* The run's project is in its own address — `/p/<id>/r/<id>` — which is
          what that shape is for: a pasted link knows which project it belongs
          to before anything has answered. The name is a request on top of that,
          not instead of it. */}
      <PageBar crumbs={crumbs}>
        {/* A run has no name — the date is what a person recognises it by. */}
        <Text variant="display">{formatDate(data.created)}</Text>
        <Badge intent={data.status === "failed" ? "danger" : "neutral"}>{data.status}</Badge>
        <Badge intent="neutral">{data.kind}</Badge>
      </PageBar>

      {data.error && (
        <Alert.Root intent="danger">
          <Alert.Title>This run failed</Alert.Title>
          <Alert.Description>{data.error}</Alert.Description>
        </Alert.Root>
      )}

      <section className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <Fact label="Model" value={data.model} />
        <Fact label="Engine" value={data.engine} />
        <Fact label="Prediction" value={data.prediction_id ?? "—"} />
        <Fact label="Created" value={formatDate(data.created)} />
        <Fact label="Submitted" value={data.submitted ? formatDate(data.submitted) : "—"} />
        <Fact label="Completed" value={data.completed ? formatDate(data.completed) : "—"} />
        <Fact
          label="Cost"
          value={data.cost ? `${data.cost.currency} ${data.cost.amount.toFixed(3)}` : "not reported"}
        />
      </section>

      <section className="flex flex-col gap-2">
        <Text variant="title">Outputs</Text>
        {data.outputs.length === 0 ? (
          <Text variant="body" tone="muted">
            Nothing came back.
          </Text>
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
            {data.outputs.map((asset) => (
              <AssetTile
                key={asset.node}
                asset={asset}
                onOpen={() => navigate(objectPath(asset.node, RUN))}
              />
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <Text variant="title">Bindings</Text>
        {/* Node ids, never URLs and never paths. A URL-shaped binding is refused
            by the API — hard rule #3, enforced for both halves of studio rather
            than only for the CLI — so what is drawn here is always material that
            was already in the library when the run went out. */}
        {Object.keys(data.bindings).length === 0 ? (
          <Text variant="body" tone="muted">
            Nothing was bound.
          </Text>
        ) : (
          Object.entries(data.bindings).map(([role, assets]) => (
            <div key={role} className="flex flex-col gap-1">
              <Text variant="caption" tone="muted">
                {role}
              </Text>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
                {assets.map((asset) => (
                  <AssetTile
                    key={asset.node}
                    asset={asset}
                    onOpen={() => navigate(objectPath(asset.node, RUN))}
                  />
                ))}
              </div>
            </div>
          ))
        )}
      </section>

      <section className="flex flex-col gap-2">
        <Text variant="title">Chain</Text>
        {/* Lineage is two node-shaped pointers and nothing more, which is exactly
            enough to walk a chain backwards: the run this one continued, and the
            frame of it that was picked up. */}
        {data.lineage.from_run === null ? (
          <Text variant="body" tone="muted">
            This run starts a chain — nothing came before it.
          </Text>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              intent="ghost"
              size="sm"
              onClick={() => navigate(runPath(projectId, data.lineage.from_run as string))}
            >
              Continued from the previous run
            </Button>
            {data.lineage.from_output && (
              <Button
                intent="ghost"
                size="sm"
                onClick={() => navigate(objectPath(data.lineage.from_output as string))}
              >
                Open the frame it started from
              </Button>
            )}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <Text variant="title">Payload</Text>
        <Text variant="caption" tone="muted">
          Exactly what went to the provider and exactly what came back. Studio stores these and
          decodes neither.
        </Text>
        <PayloadDocument label="prompt.json" node={data.payload.prompt} />
        <PayloadDocument label="request.json" node={data.payload.request} />
        <PayloadDocument label="response.json" node={data.payload.response} />
      </section>
    </>
  );
}

/**
 * One payload document, as text.
 *
 * Fetched only when it is opened, because three of these on every run page is
 * three requests for documents that are usually large and usually not what the
 * page was opened for.
 *
 * `formatTextContent` re-indents JSON **for reading** and is the only thing done
 * to it. That is not parsing in the sense the rule forbids: no field is looked
 * up, nothing branches on the shape, and what is shown is the same document.
 */
function PayloadDocument({ label, node }: { label: string; node: string | null }) {
  const load = useCallback(
    () => (node === null ? Promise.reject(new Error("absent")) : getNodeText(node)),
    [node],
  );
  const [open, setOpen] = useState(false);
  const { data, loading, error } = useResource(open && node !== null ? load : null);

  if (node === null) {
    return (
      <div className="rounded-md border border-line bg-card px-3 py-2">
        <Text variant="caption" tone="muted">
          {label} — not written for this run
        </Text>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-line bg-card">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left
                   focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
      >
        <span aria-hidden="true" className="text-muted">
          {open ? "▾" : "▸"}
        </span>
        <Text variant="body">{label}</Text>
      </button>

      {open && (
        <div className="border-t border-line">
          {loading && (
            <div className="flex justify-center py-6">
              <Spinner size="md" label={`Loading ${label}`} />
            </div>
          )}
          {error && (
            <div className="p-3">
              <Alert.Root intent="danger">
                <Alert.Title>Could not read {label}</Alert.Title>
                <Alert.Description>{error}</Alert.Description>
              </Alert.Root>
            </div>
          )}
          {data && (
            <pre className="overflow-x-auto p-3 font-mono text-xs leading-relaxed text-ink">
              <code>{formatTextContent(data.content, data.language)}</code>
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function AssetTile({ asset, onOpen }: { asset: RunAsset; onOpen: () => void }) {
  const isVideo = (asset.content_type ?? "").startsWith("video/");
  return (
    <button
      type="button"
      onClick={onOpen}
      title={asset.name}
      className="flex flex-col gap-1 rounded-md border border-line bg-card p-1 text-left
                 transition-colors hover:bg-surface-alt
                 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      <MediaThumb
        nodeId={asset.node}
        url={asset.url}
        name={asset.name}
        isVideo={isVideo}
        className="w-full rounded-md"
      />
      <Text variant="caption" tone="muted" className="truncate">
        {asset.name}
      </Text>
      {asset.size !== undefined && (
        <Text variant="caption" tone="muted" className="tabular-nums">
          {formatBytes(asset.size)}
        </Text>
      )}
    </button>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-card px-3 py-2">
      <Text variant="caption" tone="muted">
        {label}
      </Text>
      <Text variant="body" className="truncate">
        {value}
      </Text>
    </div>
  );
}

