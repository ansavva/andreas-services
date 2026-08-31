import { useCallback, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  Alert,
  Badge,
  Button,
  Spinner,
  Tabs,
  Text,
} from "@ansavva/design-system";

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
import { OutputPanel } from "../components/media/OutputPanel";
import { MediaThumb } from "../components/media/MediaThumb";
import { ApproveBar, InFlightBar, RunPlan } from "../components/run/RunPlan";
import { formatCost } from "../utils/cost";
import { RunPlanEditor } from "../components/run/RunPlanEditor";
import { useResource } from "../hooks/useResource";
import { useProjectCrumb } from "../hooks/useProjectCrumb";
import { formatBytes, formatDate, formatTextContent } from "../utils/format";
import {
  isTerminal,
  isUnsubmitted,
  type RunAsset,
  type RunRecord,
} from "../types";
import { objectPath, scenePath } from "../utils/location";

/**
 * One run: what studio recorded about it, what came out, and — separately, and
 * verbatim — what was sent to the provider and what came back.
 *
 * **That separation is the rule the entity model preserved rather than removed.**
 * Everything above `payload` is studio's own envelope: the status, the model, the
 * bindings as node ids, the outputs and the cost. It is validated, it
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

  /**
   * Which half of the left column is showing.
   *
   * Deliberately NOT in the address. The tab a person is on is a reading
   * position, not a place — `?in=` and the run id are what a pasted link has to
   * carry, and a payload pane in the query string would survive a share and
   * open someone else on a raw request document.
   */
  const [pane, setPane] = useState("plan");
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
          <Alert.Description>
            {error ?? "It may have been deleted."}
          </Alert.Description>
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
        {/* A status and a kind are values the API chose, not prose — mono is
            what says so, and is what every other status in the app wears. */}
        <Badge
          intent={data.status === "failed" ? "danger" : "neutral"}
          className="font-mono"
        >
          {data.status}
        </Badge>
        <Badge intent="neutral" className="font-mono">
          {data.kind}
        </Badge>
      </PageBar>

      {/* **Split like the provider's own playground, and output-first when it
          cannot split.** What made the run on the left, what came back on the
          right — the run page used to stack them, so on any screen the thing a
          person opened the page for sat below a fact table, an approval bar and
          whatever bindings there were.

          The output section is FIRST IN THE DOM on purpose. Below `lg` that is
          the whole mechanism: one column, result at the top, no `order`
          override to keep in sync with anything. Above `lg` it is placed into
          the second column explicitly, so the visual swap costs one pair of
          `col-start`/`row-start` rather than a reordering the markup has to
          remember. It also means a screen reader reaches the result first at
          every width, which is the right reading of a run. */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:items-start">
        <section className="flex flex-col gap-3 lg:col-start-2 lg:row-start-1">
          <Text variant="title" className="border-b border-line pb-2">
            Outputs
          </Text>
          {data.outputs.length === 0 ? (
            <Text variant="body" tone="muted">
              Nothing came back.
            </Text>
          ) : (
            <div
              className={`grid gap-2 ${
                data.outputs.length === 1
                  ? "grid-cols-1"
                  : "grid-cols-2 sm:grid-cols-3"
              }`}
            >
              {data.outputs.map((asset) => (
                <OutputPanel
                  key={asset.node}
                  asset={asset}
                  sole={data.outputs.length === 1}
                  to={objectPath(asset.node, RUN)}
                />
              ))}
            </div>
          )}
        </section>

        <div className="flex min-w-0 flex-col gap-6 lg:col-start-1 lg:row-start-1">
          {/* **`Inputs` is the heading; the tabs live under it.** It names the
              column, so it is the pair to `Outputs` and is set in the same
              hand. What the tabs divide is the two kinds of input a run has —
              what a person authored, and the documents that actually went over
              the wire. */}
          <Text variant="title" className="border-b border-line pb-2">
            Inputs
          </Text>

          {/* `defaultValue` as well as `value` — the package seeds
              `useControllableState` from it and does not introspect its List to
              guess a first tab. */}
          <Tabs.Root value={pane} defaultValue="plan" onValueChange={setPane}>
            <Tabs.List className="overflow-x-auto border-b border-line">
              <Tabs.Tab value="plan">Plan</Tabs.Tab>
              <Tabs.Tab value="payload">Payload</Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="plan">
              <div className="flex min-w-0 flex-col gap-6 pt-4">
                {data.error && (
                  <Alert.Root intent="danger">
                    <Alert.Title>This run failed</Alert.Title>
                    <Alert.Description>{data.error}</Alert.Description>
                  </Alert.Root>
                )}

                {/* **Seven bordered cards became one ruled grid.** Each fact was a box
            with its own border and fill, so the densest, least decorative part of
            the page — a model name and five timestamps — carried the most chrome
            on it. A rule above each cell separates them for the same cost as a
            border and reads as one table rather than seven objects. */}

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
                    <RunPlan
                      run={data}
                      onView={(asset) => navigate(objectPath(asset.node, RUN))}
                    />
                    {/* **Only while nothing has been sent.** `PATCH /plan` refuses a
                submitted run — its plan is what went out, and a plan edited
                afterwards would sit beside `request.json` describing something
                that was never sent — so the button is absent rather than present
                and answered with a 409. */}
                    {isUnsubmitted(data.status) && (
                      <div>
                        <Button
                          intent="ghost"
                          size="sm"
                          onClick={() => setEditing(true)}
                        >
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
                      void decide(() =>
                        approveRun(data.id, data.plan_digest ?? ""),
                      )
                    }
                    onRevoke={() =>
                      void decide(() => revokeRunApproval(data.id))
                    }
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

                {/* **Only when there are no sends to have drawn instead.**
            `Plan → Images` says everything this said and more — the order, the
            role, and which character group each picture came from — so drawing
            both put the same three pictures on the screen twice, the second time
            with less information. This is what a run that predates the send rows
            and has not been backfilled still needs, and it retires itself. */}
                {data.sends.length === 0 && (
                  <section className="flex flex-col gap-3">
                    <Text variant="title" className="border-b border-line pb-2">
                      Bindings
                    </Text>
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
                          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                            {assets.map((asset) => (
                              <AssetTile
                                key={asset.node}
                                asset={asset}
                                onOpen={() =>
                                  navigate(objectPath(asset.node, RUN))
                                }
                              />
                            ))}
                          </div>
                        </div>
                      ))
                    )}
                  </section>
                )}
              </div>
            </Tabs.Panel>

            <Tabs.Panel value="payload">
              <div className="flex min-w-0 flex-col gap-3 pt-4">
                <section className="flex flex-col gap-3">
                  <Text variant="caption" tone="muted">
                    Exactly what went to the provider and exactly what came
                    back. Studio stores these and decodes neither.
                  </Text>
                  <PayloadDocument
                    label="prompt.json"
                    node={data.payload.prompt}
                  />
                  <PayloadDocument
                    label="request.json"
                    node={data.payload.request}
                  />
                  <PayloadDocument
                    label="response.json"
                    node={data.payload.response}
                  />
                </section>
              </div>
            </Tabs.Panel>
          </Tabs.Root>

          <Backlinks label="Used in" links={data.scenes} to={scenePath} />

          {/* **Last, not first.** These are the run's provenance — model, prediction
            id, the three timestamps, what it cost — and every one of them is
            something you go looking for, not something you read on the way to the
            result. They led the page because a stacked layout had nowhere else to
            put them; a split one does. */}
          <section className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
            <Fact label="Model" value={data.model} />
            <Fact label="Engine" value={data.engine} />
            <Fact label="Prediction" value={data.prediction_id ?? "—"} />
            <Fact label="Created" value={formatDate(data.created)} />
            <Fact
              label="Submitted"
              value={data.submitted ? formatDate(data.submitted) : "—"}
            />
            <Fact
              label="Completed"
              value={data.completed ? formatDate(data.completed) : "—"}
            />
            <Fact label="Cost" value={formatCost(data.cost)} />
          </section>
        </div>
      </div>
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
function PayloadDocument({
  label,
  node,
}: {
  label: string;
  node: string | null;
}) {
  const load = useCallback(
    () =>
      node === null ? Promise.reject(new Error("absent")) : getNodeText(node),
    [node],
  );
  const [open, setOpen] = useState(false);
  const { data, loading, error } = useResource(
    open && node !== null ? ["node-text", node] : null,
    load,
  );

  if (node === null) {
    return (
      <div className="border-t border-line py-2">
        <Text variant="caption" tone="muted" className="font-mono">
          {label} — not written for this run
        </Text>
      </div>
    );
  }

  return (
    <div className="border-t border-line">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 py-2 text-left transition-colors hover:text-muted
                   focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
      >
        <span aria-hidden="true" className="text-muted">
          {open ? "▾" : "▸"}
        </span>
        {/* A file name, so mono — this is the one label on the page that is
            literally a path a person would type. */}
        <Text variant="body" family="mono">
          {label}
        </Text>
      </button>

      {open && (
        <div className="border-t border-line bg-card">
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
            // `whitespace-pre-wrap` + `break-words`, not `overflow-x-auto`.
            // A payload is mostly one very long line — a serialized prompt, or
            // a presigned URL with a signature on the end — so a scrolling
            // `<pre>` hid the half of it that mattered behind a gesture, and in
            // a half-width column it hid most of it. `break-words` is what
            // handles the URLs, which carry no spaces to break at.
            <pre className="whitespace-pre-wrap break-words p-3 font-mono text-xs leading-relaxed text-ink">
              <code>{formatTextContent(data.content, data.language)}</code>
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function AssetTile({
  asset,
  onOpen,
  aspect = "square",
}: {
  asset: RunAsset;
  onOpen: () => void;
  /**
   * A grid of tiles wants one shape so the rows line up. A run's SINGLE output
   * is not a tile in a grid — it is the thing the page is about — so it takes
   * the media's own aspect instead of being letterboxed into a square the
   * width of half the page.
   */
  aspect?: "square" | "auto";
}) {
  const isVideo = (asset.content_type ?? "").startsWith("video/");
  return (
    <button
      type="button"
      onClick={onOpen}
      title={asset.name}
      className="flex flex-col gap-1 rounded-none border border-line bg-card p-1 text-left
                 transition-colors hover:bg-surface-alt
                 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      <MediaThumb
        nodeId={asset.node}
        url={asset.url}
        name={asset.name}
        isVideo={isVideo}
        aspect={aspect}
        className="w-full rounded-none"
      />
      <Text variant="caption" tone="muted" className="truncate font-mono">
        {asset.name}
      </Text>
      {asset.size !== undefined && (
        <Text variant="caption" tone="muted" className="font-mono tabular-nums">
          {formatBytes(asset.size)}
        </Text>
      )}
    </button>
  );
}

/**
 * One fact, under a hairline.
 *
 * The value is mono without exception, because every one of them is a value
 * rather than a sentence — a model id, a prediction id, three timestamps and a
 * cost. Setting them in the body face made a column of them fail to line up on
 * anything, which is the whole argument for a monospaced face carrying metadata.
 */
function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-t border-line py-2">
      <Text variant="caption" tone="muted" className="block">
        {label}
      </Text>
      <Text variant="body" family="mono" className="truncate">
        {value}
      </Text>
    </div>
  );
}
