import { useCallback, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Button, Spinner, Text } from "@ansavva/design-system";

import {
  approveRun,
  getNodeText,
  getRun,
  reconcileRun,
  revokeRunApproval,
  submitRun,
} from "../apis/studio";
import { PageBar } from "../components/layout/PageBar";
import { Backlinks } from "../components/common/Backlinks";
import { MediaThumb } from "../components/media/MediaThumb";
import { ApproveBar, InFlightBar, RunPlan } from "../components/run/RunPlan";
import { RunPlanEditor } from "../components/run/RunPlanEditor";
import { useResource } from "../hooks/useResource";
import { useProjectCrumb } from "../hooks/useProjectCrumb";
import { formatBytes, formatDate, formatTextContent } from "../utils/format";
import { isTerminal, isUnsubmitted, type RunAsset, type RunRecord } from "../types";
import { objectPath, runPath, scenePath } from "../utils/location";

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
 *
 * **`plan` is the third thing, and it is neither of those.** It is what a person
 * decided — the prompt, the parameters, and the ordered images with a word each
 * about why — recorded by studio and safe to render as fields for the same
 * reason the envelope is. Before it existed, intent lived only inside
 * `request.json`, so this page could show what came out of a run and never what
 * it was for.
 */
export function RunPage() {
  const { projectId = "", runId = "" } = useParams();
  const navigate = useNavigate();

  const load = useCallback(() => getRun(runId), [runId]);
  /**
   * A run is an async job, and this page was a snapshot of one.
   *
   * It showed whatever the status was when it opened and waited for somebody to
   * press reload — on the one screen in the app whose whole subject is a thing
   * that changes underneath you. It polls while the run can still move and stops
   * the moment it cannot, which is what `isTerminal` is for.
   */
  const { data, loading, error, setData } = useResource(["run", runId], load, {
    refetchInterval: (query) => {
      const status = (query.state.data as RunRecord | undefined)?.status;
      return status && !isTerminal(status) ? 5_000 : false;
    },
  });
  const crumbs = useProjectCrumb(projectId);

  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);
  /**
   * Whether the plan is being edited rather than read.
   *
   * A mode rather than an always-editable form, because this page is read far
   * more often than it is written and a run's plan is the thing an approval
   * names — a page whose prompt sits in a text box invites a keystroke into the
   * document somebody is about to say yes to.
   */
  const [editing, setEditing] = useState(false);

  /**
   * Approve or revoke, then swap the record in rather than refetching.
   *
   * The route answers with the whole updated run, and a re-GET would re-sign
   * every send and every output URL to show one badge changing.
   */
  const decide = useCallback(
    async (act: () => Promise<RunRecord>) => {
      setApproving(true);
      setApproveError(null);
      try {
        setData(await act());
      } catch (err) {
        setApproveError((err as Error).message);
      } finally {
        setApproving(false);
      }
    },
    [setData],
  );

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

      <Backlinks label="Used in" links={data.scenes} to={scenePath} />
      <Backlinks
        label="Chained into"
        links={data.derived}
        to={(id) => runPath(data.project, id)}
      />

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

      {/* **Above the outputs, because it is what the outputs came from.** The
          page used to open on the result of a submission with no account of the
          intent behind it, which is the wrong way round for the one screen a
          person opens to ask "what was this?" */}
      {editing ? (
        <RunPlanEditor
          run={data}
          onSaved={(updated) => {
            setData(updated);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <>
          <RunPlan run={data} onView={(asset) => navigate(objectPath(asset.node, RUN))} />
          {/* **Only while nothing has been sent.** `PATCH /plan` refuses a
              submitted run — its plan is what went out, and a plan edited
              afterwards would sit beside `request.json` describing something
              that was never sent — so the button is absent rather than present
              and answered with a 409. */}
          {isUnsubmitted(data.status) && (
            <div>
              <Button intent="ghost" size="sm" onClick={() => setEditing(true)}>
                Edit the plan
              </Button>
            </div>
          )}
        </>
      )}

      {/* **Under the plan, not over it.** Its own sentence says "reads the
          payload above", and it sat above the payload — so the control that
          spends money was the first thing on the screen and the thing it asks
          you to read was the second. */}
      {/* Hidden while the plan is being edited: an approve button beside a form
          holding unsaved words is a yes to whichever of the two you were not
          looking at. */}
      {!editing && (
      <ApproveBar
        run={data}
        busy={approving}
        error={approveError}
        onApprove={() =>
          void decide(() => approveRun(data.id, data.plan_digest ?? ""))
        }
        onRevoke={() => void decide(() => revokeRunApproval(data.id))}
        /* **The app can spend now, and until generation moved into the API it
           could not.** The credential lived in the CLI, so a run approved on
           this page had to be sent from a terminal. `decide` needs no change:
           the route answers with the whole updated run, exactly as approve
           does, so the badge and this bar swap over together. */
        onSubmit={() => void decide(() => submitRun(data.id))}
      />
      )}

      {/* Sent, and not back yet. Its own control, because what a person can do
          about a run in flight is nothing like what they can do about one that
          has not gone — and because this state did not exist while the CLI held
          the whole lifecycle in one blocking command. */}
      <InFlightBar
        run={data}
        busy={approving}
        error={approveError}
        onReconcile={() => void decide(() => reconcileRun(data.id))}
      />

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

      {/* **Only when there are no sends to have drawn instead.**
          `Plan → Images` says everything this said and more — the order, the
          role, and which character group each picture came from — so drawing
          both put the same three pictures on the screen twice, the second time
          with less information. This is what a run that predates the send rows
          and has not been backfilled still needs, and it retires itself. */}
      {data.sends.length === 0 && (
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
      )}

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
  const { data, loading, error } = useResource(open && node !== null ? ["node-text", node] : null, load);

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

