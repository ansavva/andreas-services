import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import {
  Alert,
  Badge,
  Button,
  Drawer,
  Tabs,
  Text,
} from "@ansavva/design-system";

import {
  deleteRun,
  getNodeText,
  getRun,
  getRunPayloadPreview,
  getRuns,
  reconcileRun,
} from "../apis/studio";
import { EmptyState } from "../components/common/EmptyState";
import { LoadError } from "../components/common/LoadError";
import { PageLoading } from "../components/common/PageLoading";
import { SectionLoading } from "../components/common/SectionLoading";
import { PageBar } from "../components/layout/PageBar";
import { Backlinks } from "../components/common/Backlinks";
import { ConfirmDeleteButton } from "../components/common/ConfirmDeleteButton";
import { EntityRow } from "../components/entity/EntityRow";
import { OutputPanel } from "../components/media/OutputPanel";
import { InFlightBar, RunBar, RunPlan } from "../components/run/RunPlan";
import { PromotePanel } from "../components/run/PromotePanel";
import { RunAgainButton } from "../components/run/RunAgainButton";
import { formatCost } from "../utils/cost";
import { RunPlanEditor } from "../components/run/RunPlanEditor";
import { useDisclosure } from "../hooks/useDisclosure";
import { useResource } from "../hooks/useResource";
import { useProjectCrumb } from "../hooks/useProjectCrumb";
import { formatBytes, formatDate, formatTextContent } from "../utils/format";
import { MEDIA_GRID } from "../utils/grid";
import {
  isTerminal,
  isUnsubmitted,
  type RunAsset,
  type RunRecord,
} from "../types";
import { objectPath, projectPath, runPath, scenePath } from "../utils/location";

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
  const { data, loading, error, reload, setData } = useResource(
    ["run", runId],
    load,
    {
      refetchInterval: (query) => {
        const status = (query.state.data as RunRecord | undefined)?.status;
        return status && !isTerminal(status) ? 5_000 : false;
      },
    },
  );
  const crumbs = useProjectCrumb(projectId);

  /**
   * Which half of the left column is showing.
   *
   * Deliberately NOT in the address. The tab a person is on is a reading
   * position, not a place — `?in=` and the run id are what a pasted link has to
   * carry, and a payload pane in the query string would survive a share and
   * open someone else on a raw request document.
   */
  /** Whether anything has actually gone to the provider — see `PayloadDocument`. */
  const sent = Boolean(data?.submitted);
  const [pane, setPane] = useState("plan");
  // The in-flight bar's "check now", and nothing else — see `decide`.
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  /**
   * Whether the plan is being edited rather than read.
   *
   * A mode rather than an always-editable form, because this page is read far
   * more often than it is written and a run's plan is the thing an approval
   * names — a page whose prompt sits in a text box invites a keystroke into the
   * document somebody is about to say yes to.
   */
  /**
   * **Opened in the editor when whoever navigated here said so.** A draft made
   * by the composer strip has an empty plan and exists only to be filled in, so
   * landing on its read view — a page saying a run predates the plan, with an
   * "Edit the plan" button under it — would be a step nobody wants. The state is
   * carried by the navigation rather than by the URL: it describes one arrival,
   * not the page, and a shared link should open what everyone else sees.
   */
  const arrived = useLocation().state as { editing?: boolean } | null;
  const [editing, setEditing] = useState(Boolean(arrived?.editing));

  /**
   * **Re-read on every change of run, because this page does not remount.**
   *
   * `useState`'s initial value is evaluated once per MOUNT, and moving from one
   * run to another is the same route pattern — React Router re-renders this
   * component rather than remounting it. So `Duplicate`, which navigates from a
   * run page to the draft it just made, handed `editing` to a `useState` that
   * had already run: the draft opened read-only, with an "Edit the plan" button
   * under it, which is the one thing a clone made to be changed should not do.
   * Arriving from anywhere else worked, because that was a real mount.
   *
   * Keyed on the run rather than on the state so it also CLOSES the editor when
   * the run changes — carrying an open editor onto a different run would be a
   * form pointing at a plan nobody opened it for.
   */
  const openedFor = useRef<string | null>(null);
  useEffect(() => {
    if (openedFor.current === runId) return;
    openedFor.current = runId;
    setEditing(Boolean(arrived?.editing));
  }, [runId, arrived]);

  /**
   * Which output has its promote panel open — a node id, or nothing.
   *
   * One at a time, and scoped to the output rather than to the page: promoting
   * is a decision about one picture, and a panel that stayed open while you
   * pressed a second tile would be a form pointing at an image you were no
   * longer looking at.
   *
   * **Nothing is refetched when it succeeds.** Promoting copies the output into
   * a character and attaches the copy; the run is not touched by any of it, so
   * a re-read would re-sign every URL on the page to show nothing new.
   */
  const promoteDirty = useRef(false);
  /** Raised when a dismissal was refused because the form had words in it. */
  const [promoteWarning, setPromoteWarning] = useState(false);
  const promote = useDisclosure(
    useCallback(() => !promoteDirty.current, []),
  );

  /**
   * Reconcile, then swap the record in rather than refetching.
   *
   * The route answers with the whole updated run, and a re-GET would re-sign
   * every send and every output URL to show one badge changing.
   *
   * **It used to carry approve, revoke and submit too**, and carries neither
   * approve nor submit now: those are one act performed inside `RunBar`, which
   * owns its own busy and error state because the two calls it makes have to be
   * told apart — a refusal on the first means nothing was sent.
   */
  const decide = useCallback(
    async (act: () => Promise<RunRecord>) => {
      setChecking(true);
      setCheckError(null);
      try {
        setData(await act());
      } catch (err) {
        setCheckError((err as Error).message);
      } finally {
        setChecking(false);
      }
    },
    [setData],
  );

  // Every frame on this page opens into the run, so scrolling the viewer walks
  // what the run produced and was given rather than the folder those files
  // happen to sit in.
  const RUN = useMemo(() => ({ in: "run" as const, id: runId }), [runId]);

  if (loading) return <PageLoading label="Loading run" />;

  if (error || !data) {
    return (
      <LoadError
        what="this run"
        message={error ?? "It may have been deleted."}
        onRetry={reload}
        escape={{ label: "Back to home", onClick: () => navigate("/") }}
      />
    );
  }

  /**
   * The editor is for a plan that can still change, so a submitted run never
   * gets one — including when `state.editing` said to open it. The state
   * describes an intention at the moment of navigation and the run is what
   * decides whether it is possible.
   */
  const showEditor = editing && isUnsubmitted(data.status);

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
          {/* **A failure IS the outcome, so it belongs here.** It sat under
              Inputs → Plan, beside the images and the parameters — the account
              of what was asked for — while Outputs said "Nothing came back" and
              did not say why. The one column a person reads to find out what
              happened had the answer in the other one. */}
          {data.error && (
            <Alert.Root intent="danger">
              <Alert.Title>This run failed</Alert.Title>
              <Alert.Description>{data.error}</Alert.Description>
            </Alert.Root>
          )}

          {/* **An empty Outputs means three different things**, and it used to
              say the last one whichever it was: "Nothing came back" on a draft
              claims the run went out and the model returned nothing, which is
              false about a run nobody has sent. A person reading it on a plan
              they are still writing has been told their run failed.

              A failed run is a fourth: the alert above says what happened, so
              repeating "Nothing came back" underneath it says nothing twice. */}
          {data.outputs.length === 0 ? (
            data.error ? null : (
              <EmptyState
                title={
                  isUnsubmitted(data.status)
                    ? "Not run yet."
                    : data.status === "pending" || data.status === "running"
                      ? "Still working."
                      : "Nothing came back."
                }
              />
            )
          ) : (
            // The one output is the subject of the page, not a tile among
            // others — `OutputPanel`'s own `sole` prop is what changes for it.
            <div className={data.outputs.length === 1 ? "grid grid-cols-1 gap-2" : MEDIA_GRID}>
              {data.outputs.map((asset) => (
                <Fragment key={asset.node}>
                  <OutputPanel
                    asset={asset}
                    sole={data.outputs.length === 1}
                    to={objectPath(asset.node, RUN)}
                    /* On the caption row, against the file it acts on. Below
                       the card it read as debris floating between the output
                       and the next heading, belonging to neither.

                       **Images only**, which is the CLI's own restriction:
                       `add-refs --from-run` resolves output nodes by image
                       extension. A reference is a picture a later render is
                       checked against, and a clip cannot be one. */
                    /* **The trigger stays and stops being the primary.** Its
                       panel carries the live `Promote`, so a second filled
                       button up here would be one act wearing two controls;
                       pressed, this one is the open row's marker and the way
                       to close it again. */
                    action={
                      isPromotable(asset) ? (
                        <Button
                          size="sm"
                          intent={promote.isOpen(asset.node) ? "ghost" : "primary"}
                          aria-expanded={promote.isOpen(asset.node)}
                          onClick={() => promote.toggle(asset.node)}
                        >
                          Promote
                        </Button>
                      ) : undefined
                    }
                  />

                  {/* **A drawer, not an expando under the tile.** The form is
                      read against the picture it is about — is this the face
                      to file as identity — so the output has to stay on screen
                      while it is filled in. An expando pushed the grid around
                      to make room and put the form below the thing it was
                      about; a right-hand panel leaves the outputs where they
                      are and sits beside them.

                      Studio has deleted two drawers before, and neither
                      argument reaches this one: both held MEDIA — a 256px
                      reference thumbnail nobody could judge, and a frame
                      viewer that needed an address and fullscreen. A form
                      needs neither. */}
                  {promote.isOpen(asset.node) && (
                    <Drawer.Root
                      open
                      onOpenChange={(next: boolean) => {
                        if (next) return;
                        // The backdrop and Escape both arrive here. A form
                        // with words in it declines and says so rather than
                        // discarding them on a stray click outside.
                        if (promoteDirty.current) {
                          setPromoteWarning(true);
                          return;
                        }
                        promote.close();
                      }}
                    >
                      <Drawer.Backdrop />
                      <Drawer.Panel className="w-full max-w-md overflow-y-auto">
                        <PromotePanel
                          asset={asset}
                          runCharacters={data.characters ?? []}
                          onClose={promote.close}
                          onDirtyChange={(dirty) => {
                            promoteDirty.current = dirty;
                            if (!dirty) setPromoteWarning(false);
                          }}
                          unsavedWarning={promoteWarning}
                          onDiscard={() => {
                            setPromoteWarning(false);
                            promote.close();
                          }}
                          onKeepEditing={() => setPromoteWarning(false)}
                        />
                      </Drawer.Panel>
                    </Drawer.Root>
                  )}
                </Fragment>
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
                {/* **Seven bordered cards became one ruled grid.** Each fact was a box
            with its own border and fill, so the densest, least decorative part of
            the page — a model name and five timestamps — carried the most chrome
            on it. A rule above each cell separates them for the same cost as a
            border and reads as one table rather than seven objects. */}

                {/* **Above the outputs, because it is what the outputs came from.** The
            page used to open on the result of a submission with no account of the
            intent behind it, which is the wrong way round for the one screen a
            person opens to ask "what was this?" */}
                {showEditor ? (
                  <RunPlanEditor
                    run={data}
                    onSaved={(updated) => {
                      setData(updated);
                      setEditing(false);
                    }}
                    // The record moved and the edit is not finished — the cast
                    // is the one thing changed from inside the editor.
                    onChanged={setData}
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
                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          intent="secondary"
                          size="sm"
                          onClick={() => setEditing(true)}
                        >
                          Edit the plan
                        </Button>
                        {/* **Discard, and it is offered here only.** `DELETE
                            /api/runs/<id>` has no status gate — it will take a
                            succeeded run and its outputs as readily as an
                            abandoned draft — so what restricts this to
                            unsubmitted runs is the app, deliberately. Nothing
                            has been spent on one, and a draft made by a
                            mis-click should cost nothing to undo.

                            `files=keep` by default: an unsubmitted run has
                            produced no files, so there is nothing to sweep and
                            asking would be a question about nothing. */}
                        <ConfirmDeleteButton
                          noun="this run"
                          tone="text"
                          onConfirm={async () => {
                            await deleteRun(data.id);
                            navigate(projectPath(data.project));
                          }}
                        />
                      </div>
                    )}
                  </>
                )}

                {/* Read before the button that spends, which is the only place
                    it can do its job. */}
                {!showEditor && isUnsubmitted(data.status) && (
                  <DuplicateNotice run={data} />
                )}

                {/* **Under the plan, not over it.** Its own sentence says "the
            payload above", and it sat above the payload — so the control that
            spends money was the first thing on the screen and the thing it asks
            you to read was the second. */}
                {/* Hidden while the plan is being edited: an armed spend button beside a
            form holding unsaved words is a yes to whichever of the two you were
            not looking at. */}
                {/* **Right-aligned, with every other control that acts on
                    this run.** A button on the left edge of a wide column
                    reads as the start of a sentence the page does not
                    continue; the actions belong together at the end of the
                    block they act on. */}
                {!showEditor && (
                  <div className="flex justify-end">
                    <RunBar run={data} onRan={setData} onReload={reload} />
                  </div>
                )}

                {/* **The only thing a submitted run can still do**, and it makes
                    a second run rather than re-sending this one — a run row
                    records one submission. Beside the approval sentence
                    `RunBar` leaves behind, because the two together are the
                    account of this attempt and the offer of the next. */}
                {!isUnsubmitted(data.status) && (
                  <div className="flex justify-end">
                    <RunAgainButton run={data} />
                  </div>
                )}

                {/* Sent, and not back yet. Its own control, because what a person can do
            about a run in flight is nothing like what they can do about one that
            has not gone — and because this state did not exist while the CLI held
            the whole lifecycle in one blocking command. */}
                <InFlightBar
                  run={data}
                  busy={checking}
                  error={checkError}
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
                      <EmptyState title="Nothing was bound." />
                    ) : (
                      Object.entries(data.bindings).map(([role, assets]) => (
                        <div key={role} className="flex flex-col gap-1">
                          <Text variant="caption" tone="muted">
                            {role}
                          </Text>
                          {/* Rows, not a grid of tiles of its own — a binding is
                              a listing entry like any other, and `EntityRow` is
                              the one shape a listing draws. */}
                          <div className="flex flex-col">
                            {assets.map((asset) => (
                              <EntityRow
                                key={asset.node}
                                title={asset.name}
                                subtitle={
                                  asset.size !== undefined
                                    ? formatBytes(asset.size)
                                    : undefined
                                }
                                thumb={{
                                  node: asset.node,
                                  url: asset.url,
                                  isVideo: (asset.content_type ?? "").startsWith("video/"),
                                }}
                                to={objectPath(asset.node, RUN)}
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
                    {sent
                      ? "Exactly what went to the provider and exactly what came back. Studio stores these and decodes neither."
                      : "Nothing has gone to the provider yet. What follows is what WOULD go, rebuilt from the plan every time you open this — it is what an approval is of. The stored documents below are written at submit time."}
                  </Text>

                  {/* **A draft's payload, so it can be read before it is
                      approved.** Hard rule #2 asks a person to approve the full
                      payload and the page could not show one: a draft has no
                      `request.json`, because that records what was actually
                      sent. Built by the API from the same allowlist `submit`
                      uses, never re-derived here — see `getRunPayloadPreview`. */}
                  {!sent && <PayloadPreview runId={data.id} />}
                  <PayloadDocument
                    label="prompt.json"
                    node={data.payload.prompt}
                    sent={sent}
                  />
                  <PayloadDocument
                    label="request.json"
                    node={data.payload.request}
                    sent={sent}
                  />
                  <PayloadDocument
                    label="response.json"
                    node={data.payload.response}
                    sent={sent}
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
 * Whether this output can become a character reference.
 *
 * **Images only.** A reference is a picture every later render is checked
 * against, so a clip cannot be one — the CLI says the same thing by resolving
 * `--from-run` output nodes against its image extension set. Decided on
 * `content_type`, which the API sends off the stored row, rather than on the
 * filename: the extension is a label a rename can change and the type is what
 * was measured when the bytes landed.
 */
function isPromotable(asset: RunAsset): boolean {
  return (asset.content_type ?? "").startsWith("image/");
}

/**
 * **This payload has already been sent from this project.**
 *
 * A fingerprint is the hash of what would go to the provider, so two runs
 * carrying the same one are two charges for the same picture. `rerunBodyOf`
 * copies a payload byte for byte precisely so that stays detectable — which is
 * only worth anything if something reads it back.
 *
 * **A warning and not a refusal**, because running the same payload twice is a
 * real thing to want: a model is not deterministic, and a second attempt at the
 * same prompt is the ordinary way to get a different frame. It is the CLI's
 * `--again` said as something to read rather than as a flag to remember, and the
 * decision stays with the person.
 *
 * Drafts and discarded runs are not twins: nothing was sent for either, so
 * neither cost anything. An approved one is counted — it is cleared to send, and
 * two runs racing to spend on one payload is exactly the case this is for.
 *
 * It clears itself on an edit without being told to: the fingerprint moves with
 * the plan, so the query asks about a payload nothing else has.
 */
function DuplicateNotice({ run }: { run: RunRecord }) {
  const navigate = useNavigate();
  const fingerprint = run.fingerprint ?? null;
  const load = useCallback(
    () =>
      getRuns({
        project: run.project,
        fingerprint: fingerprint ?? "",
        // Without it the route hides drafts — including the one being asked
        // about, which would make a draft invisible to its own question.
        include: "drafts",
      }),
    [fingerprint, run.project],
  );
  const { data } = useResource(
    fingerprint ? ["runs", "fingerprint", fingerprint] : null,
    fingerprint ? load : null,
  );

  const twin = (data?.runs ?? []).find(
    (other) =>
      other.id !== run.id &&
      other.status !== "draft" &&
      other.status !== "discarded",
  );
  if (!twin) return null;

  return (
    <Alert.Root intent="warning">
      <Alert.Title>This payload has been run here before</Alert.Title>
      <Alert.Description>
        <span>
          Another run in this project sent exactly this prompt, these parameters
          and these images on {formatDate(twin.created)}. Running it again is
          allowed and bills again — a model answers differently every time, so a
          second attempt is often the point.{" "}
        </span>
        <button
          type="button"
          onClick={() => navigate(runPath(twin.project, twin.id))}
          className="rounded text-sm text-accent underline underline-offset-2 hover:opacity-80"
        >
          Open the earlier run
        </button>
      </Alert.Description>
    </Alert.Root>
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
/**
 * What a draft would send, fetched fresh.
 *
 * Re-read whenever the run record changes — an edit to the plan rewrites the
 * payload, and a preview that went stale the moment it was useful would be
 * worse than none.
 */
function PayloadPreview({ runId }: { runId: string }) {
  const load = useCallback(() => getRunPayloadPreview(runId), [runId]);
  const { data, loading, error } = useResource(["payload", runId], load);

  if (loading) return <SectionLoading label="Reading the payload" />;
  if (error || !data) {
    return (
      <Text variant="caption" tone="muted">
        The payload could not be built: {error ?? "nothing came back"}
      </Text>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <Text variant="caption" tone="muted" className="font-mono">
        request.json — what this run would send
      </Text>
      <pre className="max-h-96 overflow-y-auto whitespace-pre-wrap break-words rounded-none border border-line bg-card p-3 font-mono text-xs leading-relaxed text-ink">
        <code>{JSON.stringify(data.request, null, 2)}</code>
      </pre>
    </div>
  );
}

function PayloadDocument({
  label,
  node,
  sent,
}: {
  label: string;
  node: string | null;
  /**
   * Whether this run has been submitted.
   *
   * An absent document means two different things and the page said one
   * sentence for both. On a draft nothing has gone out yet, so there is nothing
   * to record — and a person who has just edited the plan reasonably wonders
   * why `request.json` does not show the edit. On a submitted run an absent
   * document is a gap in the record instead.
   */
  sent: boolean;
}) {
  const load = useCallback(
    () =>
      node === null ? Promise.reject(new Error("absent")) : getNodeText(node),
    [node],
  );
  const [open, setOpen] = useState(false);
  const { data, loading, error, reload } = useResource(
    open && node !== null ? ["node-text", node] : null,
    load,
  );

  if (node === null) {
    return (
      <div className="border-t border-line py-2">
        <Text variant="caption" tone="muted" className="font-mono">
          {label} —{" "}
          {sent
            ? "not written for this run"
            : "written when this run is submitted"}
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
          {loading && <SectionLoading label={`Loading ${label}`} />}
          {error && (
            <div className="p-3">
              <LoadError what={label} message={error} onRetry={reload} />
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
