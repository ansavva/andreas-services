import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Alert, Badge, Button, Collapsible, IconButton, Text, buttonClass } from "@ansavva/design-system";

import { getRun, submitRun } from "../../apis/studio";
import { useShellSidebar } from "../../context/SidebarContext";
import { useArmed } from "../../hooks/useArmed";
import { useKeyboardNav } from "../../hooks/useKeyboardNav";
import { useNow } from "../../hooks/useNow";
import { useResource } from "../../hooks/useResource";
import { isTerminal, type HeroImage, type RunAsset, type RunFeedRow, type RunRecord } from "../../types";
import { formatCost } from "../../utils/cost";
import { formatBytes } from "../../utils/format";
import { folderPath, projectPath, runPath } from "../../utils/location";
import { ApertureSpinner } from "../common/Aperture";
import { EmptyState } from "../common/EmptyState";
import {
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CloseIcon,
  DownloadIcon,
  FolderIcon,
  PencilIcon,
  PlayIcon,
  PromoteIcon,
  RerunIcon,
  TrashIcon,
  UpscaleIcon,
  UseInPromptIcon,
} from "../common/icons";
import { LoadError } from "../common/LoadError";
import { SectionLoading } from "../common/SectionLoading";
import { CharacterChipLink } from "../character/CharacterChip";
import { MediaPlayer } from "../media/MediaPlayer";
import { MediaThumb } from "../media/MediaThumb";
import { StatusBadge, useFeedFilters, useRunFeed } from "../project/RunFeed";
import { elapsedSince, inFlight, relativeTime } from "./feedTime";
import { ParamChips } from "./ParamChips";
import { PayloadDocument, PayloadPreview } from "./PayloadDocument";
import { PromoteDrawer, isPromotable, isVideoAsset } from "./PromoteDrawer";
import { promptText } from "./seed";
import { useRunActions } from "./useRunActions";

/** How often an opened run in flight re-reads its record. */
const RUN_POLL_MS = 5_000;

interface Props {
  projectId: string;
  runId: string;
  /** The project's characters, to name a cast the record holds only as ids. */
  characters: Array<{ id: string; name: string }>;
  heroes: Record<string, HeroImage | null>;
}

/**
 * One run, opened in place over the feed — `/p/<project>/r/<run>`.
 *
 * **A lightbox, not a page.** The two-column run page that used to answer this
 * address is gone; this sits over the feed, the create bar stays live above
 * it, and closing it is the feed again with the tab and the filters still in
 * the address. The sidebar collapses to its rail while it is open and comes
 * back as it was on close, so the picture gets the width.
 *
 * Three things are drawn, and they are the feed's three. The **row** — plan,
 * sends, outputs, cast — comes off the feed's own cache (`useRunFeed` shares
 * the key), so a run opened from the feed costs no second listing and
 * Left/Right and the strip walk the rows already loaded. The **record**
 * (`getRun`) is fetched for what a row does not carry: the folder, the
 * prediction id, and the three payload nodes behind the Request row. A cold
 * link — nothing in the cache yet — draws the row off the record instead.
 *
 * The **actions** are `useRunActions`, the same set the feed row and its tiles
 * draw, in one uniform grid: equal cells, the icon over the word. Nothing here
 * spends except Rerun, which arms first, exactly as it does in the row.
 */
export function RunLightbox({ projectId, runId, characters, heroes }: Props) {
  const navigate = useNavigate();
  const location = useLocation();

  // Collapse the rail for as long as this is open, and put it back as it was.
  // `setCollapsed` is stable; what was captured on the first render is what
  // comes back.
  const { collapsed, setCollapsed } = useShellSidebar();
  const restore = useRef(collapsed);
  useEffect(() => {
    const prior = restore.current;
    setCollapsed(true);
    return () => setCollapsed(prior);
  }, [setCollapsed]);

  const filters = useFeedFilters();
  const feed = useRunFeed(projectId, filters.applied);
  const rows = feed.rows;
  const index = rows.findIndex((row) => row.id === runId);

  const load = useCallback(() => getRun(runId), [runId]);
  const record = useResource(["run", runId], load, {
    refetchInterval: (query) => {
      const data = query.state.data as RunRecord | undefined;
      return data && !isTerminal(data.status) ? RUN_POLL_MS : false;
    },
  });

  const row = useMemo<RunFeedRow | null>(
    () =>
      rows[index] ??
      (record.data ? rowOfRecord(record.data, characters) : null),
    [characters, index, record.data, rows],
  );

  const close = useCallback(
    () => navigate(projectPath(projectId) + location.search, { replace: true }),
    [location.search, navigate, projectId],
  );

  // Stepping REPLACES: walking ten runs is one place, not ten history entries.
  const goTo = useCallback(
    (target: RunFeedRow) =>
      navigate(runPath(projectId, target.id) + location.search, { replace: true }),
    [location.search, navigate, projectId],
  );
  const prev = index > 0 ? () => goTo(rows[index - 1]!) : undefined;
  const next =
    index >= 0 && index < rows.length - 1
      ? () => goTo(rows[index + 1]!)
      : feed.hasNextPage && !feed.isFetchingNextPage
        ? () => void feed.fetchNextPage()
        : undefined;

  // The promote drawer binds Escape itself, so while it is up the keys are its.
  const [promoting, setPromoting] = useState<RunAsset | null>(null);
  useKeyboardNav({
    onPrev: promoting ? undefined : prev,
    onNext: promoting ? undefined : next,
    onClose: promoting ? undefined : close,
  });

  return (
    <div
      role="dialog"
      aria-label="Run"
      data-testid="run-lightbox"
      className="fixed inset-x-0 z-20 flex flex-col overflow-y-auto bg-bg md:left-16 md:flex-row md:overflow-hidden"
      style={{ top: "var(--header-h)", height: "calc(100dvh - var(--header-h))" }}
    >
      {/* `key` resets the output index and the Request row per run. */}
      {row ? (
        <Opened
          key={row.id}
          row={row}
          record={record.data}
          recordError={record.error}
          onReload={record.reload}
          heroes={heroes}
          onClose={close}
          onPrev={prev}
          onNext={next}
          promoting={promoting}
          onPromote={setPromoting}
          strip={
            <RunStrip
              rows={rows}
              currentId={row.id}
              loading={feed.isFetchingNextPage}
              onSelect={goTo}
              onPrev={prev}
              onNext={next}
            />
          }
        />
      ) : record.error ? (
        <div className="flex flex-1 flex-col items-start gap-4 p-6">
          <LoadError what="this run" message={record.error} onRetry={record.reload} />
          <Button intent="secondary" size="sm" onClick={close} className="rounded-none">
            Back to the project
          </Button>
        </div>
      ) : (
        <div className="flex flex-1 items-center justify-center">
          <ApertureSpinner size="lg" label="Loading run" />
        </div>
      )}
    </div>
  );
}

function Opened({
  row,
  record,
  recordError,
  onReload,
  heroes,
  onClose,
  onPrev,
  onNext,
  promoting,
  onPromote,
  strip,
}: {
  row: RunFeedRow;
  record: RunRecord | null;
  recordError: string | null;
  onReload: () => void;
  heroes: Record<string, HeroImage | null>;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  promoting: RunAsset | null;
  onPromote: (asset: RunAsset | null) => void;
  strip: ReactNode;
}) {
  const location = useLocation();
  const state = (location.state ?? {}) as { output?: number; request?: boolean };
  const [output, setOutput] = useState(() =>
    Math.min(Math.max(state.output ?? 0, 0), Math.max(row.outputs.length - 1, 0)),
  );
  const [requestOpen, setRequestOpen] = useState(Boolean(state.request));

  const actions = useRunActions(row);
  const flying = inFlight(row.status);
  const now = useNow(flying);
  const asset = row.outputs[output] ?? null;
  const video = asset ? isVideoAsset(asset) || row.kind === "video" : row.kind === "video";
  const sent = row.submitted !== null;

  return (
    <>
      {/* The stage: the output large, the run's other outputs under it, and
          the project's runs along the bottom. */}
      <div className="relative flex min-h-[60dvh] min-w-0 flex-1 flex-col md:min-h-0">
        <div className="absolute right-3 top-3 z-10 flex gap-1">
          <IconButton label="Close (Esc)" size="sm" intent="overlay" onClick={onClose} className="rounded-none">
            <CloseIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
          </IconButton>
        </div>
        {onPrev && (
          <IconButton
            label="Previous run (←)"
            size="sm"
            intent="overlay"
            onClick={onPrev}
            className="absolute left-3 top-1/2 z-10 -translate-y-1/2 rounded-none"
          >
            <ChevronLeftIcon className="size-5 fill-none stroke-current stroke-[1.5]" />
          </IconButton>
        )}
        {onNext && (
          <IconButton
            label="Next run (→)"
            size="sm"
            intent="overlay"
            onClick={onNext}
            className="absolute right-3 top-1/2 z-10 -translate-y-1/2 rounded-none"
          >
            <ChevronRightIcon className="size-5 fill-none stroke-current stroke-[1.5]" />
          </IconButton>
        )}

        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 p-4 md:p-8">
          {flying ? (
            <div
              data-testid="in-flight-stage"
              className={`studio-shimmer flex w-full max-w-xl flex-col items-center justify-center gap-2 rounded-none border border-warning/50 ${
                row.kind === "video" ? "aspect-video" : "aspect-[3/4]"
              }`}
            >
              <ApertureSpinner size="lg" label={`Run ${row.status}`} className="text-warning" />
              <Text variant="body" weight="medium" className="text-warning">
                {row.status === "pending" ? "Sending…" : "Running…"}
              </Text>
              <Text variant="caption" family="mono" tone="muted" className="tabular-nums">
                {elapsedSince(row.submitted ?? row.created, now)}
              </Text>
            </div>
          ) : asset ? (
            <>
              <div className="min-h-0 w-full flex-1">
                <MediaPlayer
                  key={asset.node}
                  nodeId={asset.node}
                  url={asset.url}
                  name={asset.name}
                  isVideo={video}
                  aspect="auto"
                  fit="contain"
                  className="h-full w-full border border-line"
                />
              </div>
              <Text variant="caption" family="mono" tone="muted" className="tabular-nums">
                {asset.name}
                {asset.size ? ` · ${formatBytes(asset.size)}` : ""}
              </Text>
            </>
          ) : row.error ? (
            <div className="w-full max-w-xl">
              <Alert.Root intent="danger">
                <Alert.Title>This run failed</Alert.Title>
                <Alert.Description>{row.error}</Alert.Description>
              </Alert.Root>
            </div>
          ) : (
            <EmptyState title={row.status === "draft" ? "Not run yet." : "Nothing came back."} />
          )}
        </div>

        {row.outputs.length > 1 && !flying && (
          <div className="flex justify-center gap-1.5 px-4 pb-2" aria-label="Outputs">
            {row.outputs.map((each, i) => (
              // The tile is the press; `MediaThumb` inside it is decorative.
              // eslint-disable-next-line studio/no-hand-rolled-button -- a media tile, the same shape as Filmstrip's.
              <button
                key={each.node}
                type="button"
                aria-label={`Output ${i + 1} of ${row.outputs.length}`}
                aria-current={i === output ? "true" : undefined}
                onClick={() => setOutput(i)}
                className={`w-14 shrink-0 rounded-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                  i === output ? "ring-2 ring-primary" : "opacity-70 hover:opacity-100"
                }`}
              >
                <MediaThumb
                  nodeId={each.node}
                  url={each.url}
                  name={each.name}
                  isVideo={isVideoAsset(each) || row.kind === "video"}
                  aspect="square"
                  className="rounded-none"
                />
              </button>
            ))}
          </div>
        )}

        {strip}
      </div>

      {/* The rail: the run this output came from, and what to do with it. */}
      <aside
        aria-label="Run details"
        className="flex w-full shrink-0 flex-col gap-3 border-t border-line bg-bg p-5 md:w-[360px] md:overflow-y-auto md:border-l md:border-t-0"
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge status={row.status} />
          <Badge intent="neutral" className="rounded-none font-mono">
            {row.kind}
          </Badge>
          <Text variant="caption" family="mono" tone="muted" className="ml-auto tabular-nums">
            {flying ? (
              <span className="text-warning">sent {relativeTime(row.submitted, now)}</span>
            ) : (
              relativeTime(row.created, now)
            )}
          </Text>
        </div>

        <Prompt row={row} />

        {row.sends.length > 0 && (
          <div className="flex flex-wrap gap-1.5" aria-label="Sent">
            {row.sends.map((send) => (
              <MediaThumb
                key={send.node}
                nodeId={send.node}
                url={send.url}
                name={send.name}
                aspect="square"
                title={`${send.role ?? send.field} · ${send.name}`}
                badge={send.role ?? send.field}
                className="size-14 rounded-none border border-line"
              />
            ))}
          </div>
        )}

        <ParamChips params={row.plan?.params} model={row.model} />

        {row.cast.length > 0 && (
          <div className="flex flex-wrap gap-1.5" aria-label="Cast">
            {row.cast.map((member) => (
              <CharacterChipLink
                key={member.id}
                id={member.id}
                name={member.name ?? "deleted character"}
                hero={heroes[member.id] ?? null}
              />
            ))}
          </div>
        )}

        <Text variant="caption" family="mono" tone="muted" className="tabular-nums">
          {[
            formatCost(row.cost, ""),
            row.cost?.predict_time ? `${Math.round(row.cost.predict_time)}s` : "",
            record?.prediction_id ? `prediction ${record.prediction_id.slice(0, 8)}…` : "",
          ]
            .filter(Boolean)
            .join(" · ") || "—"}
        </Text>

        {actions.rerunFailure && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not create the run</Alert.Title>
            <Alert.Description>{actions.rerunFailure}</Alert.Description>
          </Alert.Root>
        )}

        <ActionGrid
          row={row}
          record={record}
          asset={asset}
          output={output}
          actions={actions}
          onPromote={() => asset && onPromote(asset)}
        />

        {/* The Request row, collapsed: the three documents the provider owns,
            as text and never decoded. Sits last, because it is what you go
            looking for rather than what you opened the run to see. */}
        <Collapsible.Root
          open={requestOpen}
          onOpenChange={setRequestOpen}
          className="mt-auto border-y border-line"
        >
          <Collapsible.Trigger className="w-full justify-between rounded-none">
            <span className="text-muted">Request</span>
            <Text variant="caption" family="mono" tone="muted" className="truncate">
              prompt.json · request.json · response.json
            </Text>
            <ChevronDownIcon
              className={`size-4 shrink-0 fill-none stroke-current stroke-[1.5] text-muted transition-transform motion-reduce:transition-none ${
                requestOpen ? "rotate-180" : ""
              }`}
            />
          </Collapsible.Trigger>
          <Collapsible.Panel>
            {record ? (
              <div className="flex flex-col gap-2 pb-2">
                <Text variant="caption" tone="muted">
                  {sent
                    ? "Exactly what went to the provider and exactly what came back. Studio stores these and decodes neither."
                    : "Nothing has gone to the provider yet. What follows is what WOULD go, rebuilt from the plan every time you open this."}
                </Text>
                {!sent && requestOpen && <PayloadPreview runId={record.id} />}
                <PayloadDocument label="prompt.json" node={record.payload.prompt} sent={sent} />
                <PayloadDocument label="request.json" node={record.payload.request} sent={sent} />
                <PayloadDocument label="response.json" node={record.payload.response} sent={sent} />
              </div>
            ) : recordError ? (
              <div className="py-2">
                <LoadError what="the request" message={recordError} onRetry={onReload} />
              </div>
            ) : (
              <SectionLoading label="Loading the request" />
            )}
          </Collapsible.Panel>
        </Collapsible.Root>
      </aside>

      {promoting && (
        <PromoteDrawer
          asset={promoting}
          runCharacters={row.characters}
          onClose={() => onPromote(null)}
        />
      )}
    </>
  );
}

/** The prompt, whole — the feed clamps it; this is where it reads entire. */
function Prompt({ row }: { row: RunFeedRow }) {
  const text = promptText(row.plan?.prompt);
  if (!text) {
    return (
      <Text variant="body" tone="muted">
        {row.plan ? "No prompt." : "This run predates the plan."}
      </Text>
    );
  }
  return (
    <Text variant="body" className="max-h-48 overflow-y-auto whitespace-pre-wrap break-words">
      {text}
    </Text>
  );
}

const GLYPH = "size-4 fill-none stroke-current stroke-[1.5]";

/**
 * Everything a run can do, in one grid of equal cells — the icon over the word.
 *
 * Which cells depends on where the run is, the same way the feed row decides:
 * a draft offers Run; a run in flight offers Edit and nothing that spends or
 * destroys; a finished run offers the lot. Image-only cells (Upscale, Animate,
 * Promote) go with the output on the stage.
 */
function ActionGrid({
  row,
  record,
  asset,
  output,
  actions,
  onPromote,
}: {
  row: RunFeedRow;
  record: RunRecord | null;
  asset: RunAsset | null;
  output: number;
  actions: ReturnType<typeof useRunActions>;
  onPromote: () => void;
}) {
  const flying = inFlight(row.status);
  const draft = row.status === "draft";
  const still = asset !== null && !isVideoAsset(asset) && row.kind !== "video";
  const folder = record ? folderPath(record.folder) : actions.folderHref;

  const run = useCallback(async () => {
    await submitRun(row.id);
  }, [row.id]);

  return (
    <section className="flex flex-col gap-2">
      <Text variant="caption" tone="muted" className="font-semibold uppercase tracking-wide">
        Actions
      </Text>
      <div className="grid grid-cols-3 gap-2" aria-label="Actions">
        {draft && (
          <ArmedCell idle="Run" armed="Spends" busy="Running…" icon={<RerunIcon className={GLYPH} />} onFire={run} />
        )}
        {!draft && !flying && (
          <ArmedCell
            idle="Rerun"
            armed="Spends"
            busy="Running…"
            icon={<RerunIcon className={GLYPH} />}
            onFire={actions.rerun}
          />
        )}
        <Cell icon={<PencilIcon className={GLYPH} />} label="Edit" onClick={actions.edit} />
        {asset && (
          <Cell
            icon={<UseInPromptIcon className={GLYPH} />}
            label="Use as reference"
            onClick={() => actions.useInPrompt(asset, output)}
          />
        )}
        {asset && still && (
          <Cell
            icon={<PlayIcon className="size-4 fill-current stroke-none" />}
            label="Animate"
            onClick={() => actions.animate(asset, output)}
          />
        )}
        {asset && still && (
          <Cell icon={<UpscaleIcon className={GLYPH} />} label="Upscale" onClick={() => actions.upscale(asset, output)} />
        )}
        {asset && isPromotable(asset) && (
          <Cell icon={<PromoteIcon className={GLYPH} />} label="Promote" onClick={onPromote} />
        )}
        {asset && (
          <Cell icon={<DownloadIcon className={GLYPH} />} label="Download" onClick={() => void actions.download(asset)} />
        )}
        {folder && !flying && (
          <a href={folder} className={buttonClass({ intent: "secondary", size: "sm", className: CELL })}>
            <FolderIcon className={GLYPH} />
            Folder
          </a>
        )}
        {!flying && (
          <ArmedCell
            idle="Trash"
            armed="Confirm"
            busy="Deleting…"
            danger
            icon={<TrashIcon className={GLYPH} />}
            onFire={actions.remove}
          />
        )}
      </div>
    </section>
  );
}

const CELL =
  "flex h-auto min-h-16 flex-col items-center justify-center gap-1 rounded-none px-1 py-2 text-xs font-medium";

function Cell({ icon, label, onClick }: { icon: ReactNode; label: string; onClick: () => void }) {
  return (
    <Button intent="secondary" size="sm" onClick={onClick} className={CELL}>
      {icon}
      <span className="text-center leading-tight">{label}</span>
    </Button>
  );
}

/**
 * A cell that arms on the first press and acts on the second — `useArmed`,
 * the one machine every spending and destroying control in the app runs on.
 * The accessible name is the full sentence, so a screen reader hears what the
 * second press does; the cell shows the short form to stay the size of its
 * neighbours.
 */
function ArmedCell({
  idle,
  armed,
  busy,
  icon,
  onFire,
  danger = false,
}: {
  idle: string;
  armed: string;
  busy: string;
  icon: ReactNode;
  onFire: () => Promise<unknown>;
  danger?: boolean;
}) {
  const state = useArmed({ onFire });
  const label = state.busy ? busy : state.armed ? armed : idle;
  const name = state.busy
    ? busy
    : state.armed
      ? danger
        ? "Confirm — delete this run"
        : "Press again — this spends"
      : idle;

  return (
    <Button
      intent={state.armed || state.busy ? (danger ? "danger" : "primary") : "secondary"}
      size="sm"
      aria-label={name}
      onClick={state.press}
      {...state.handlers}
      disabled={state.busy}
      className={CELL}
    >
      {icon}
      <span className="text-center leading-tight">{label}</span>
      <span className="sr-only" aria-live="assertive">
        {state.armed ? name : ""}
      </span>
    </Button>
  );
}

/**
 * The project's runs along the bottom of the stage, this one marked.
 *
 * One tile per RUN — its first output, or a shimmer while it is out — from
 * the rows the feed has loaded. Pressing one opens it here; the arrows are the
 * step Left/Right take, drawn so the shortcut can be found.
 */
function RunStrip({
  rows,
  currentId,
  loading,
  onSelect,
  onPrev,
  onNext,
}: {
  rows: RunFeedRow[];
  currentId: string;
  loading: boolean;
  onSelect: (row: RunFeedRow) => void;
  onPrev?: () => void;
  onNext?: () => void;
}) {
  const strip = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = strip.current;
    const tile = el?.querySelector<HTMLElement>(`[data-run="${currentId}"]`);
    if (!el || !tile) return;
    // Centre the current tile by scrolling the strip alone — never the page.
    // See `Filmstrip` for why `scrollIntoView` is the wrong tool here.
    const tileBox = tile.getBoundingClientRect();
    const stripBox = el.getBoundingClientRect();
    const left = el.scrollLeft + (tileBox.left - stripBox.left) - (el.clientWidth - tileBox.width) / 2;
    if (typeof el.scrollTo === "function") el.scrollTo({ left, behavior: "smooth" });
    else el.scrollLeft = left;
  }, [currentId]);

  if (rows.length < 2) return null;

  return (
    <div className="flex items-center gap-1 border-t border-line px-2 py-2" aria-label="Runs in this project">
      <IconButton label="Previous run" size="sm" disabled={!onPrev} onClick={() => onPrev?.()}>
        <ChevronLeftIcon className="size-5 fill-none stroke-current stroke-[1.5]" />
      </IconButton>
      <div ref={strip} className="no-scrollbar flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto p-1.5">
        {rows.map((row) => {
          const current = row.id === currentId;
          const thumb = row.thumb ?? row.outputs[0] ?? null;
          return (
            // eslint-disable-next-line studio/no-hand-rolled-button -- a media tile, the same shape as Filmstrip's.
            <button
              key={row.id}
              type="button"
              data-run={row.id}
              aria-current={current ? "true" : undefined}
              aria-label={`Run ${relativeTime(row.created, Date.now())}${current ? " (open)" : ""}`}
              onClick={() => onSelect(row)}
              className={`relative w-16 shrink-0 rounded-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                current ? "ring-2 ring-primary" : "opacity-70 hover:opacity-100"
              }`}
            >
              {inFlight(row.status) ? (
                <span className="studio-shimmer flex aspect-square items-center justify-center rounded-none border border-warning/50">
                  <ApertureSpinner size="sm" label={`Run ${row.status}`} className="text-warning" />
                </span>
              ) : thumb ? (
                <MediaThumb
                  nodeId={thumb.node}
                  url={thumb.url}
                  name={row.outputs[0]?.name ?? row.id}
                  isVideo={row.kind === "video"}
                  aspect="square"
                  className="rounded-none"
                />
              ) : (
                <span className="flex aspect-square items-center justify-center rounded-none border border-line bg-card">
                  <Text variant="caption" family="mono" tone="muted">
                    {row.status}
                  </Text>
                </span>
              )}
            </button>
          );
        })}
        {loading && (
          <span className="flex shrink-0 items-center px-2">
            <ApertureSpinner size="sm" label="Loading more runs" />
          </span>
        )}
      </div>
      <IconButton label="Next run" size="sm" disabled={!onNext} onClick={() => onNext?.()}>
        <ChevronRightIcon className="size-5 fill-none stroke-current stroke-[1.5]" />
      </IconButton>
    </div>
  );
}

/**
 * A feed row built from the record, for a run the feed has not loaded.
 *
 * A cold link lands here before any listing has answered, and the record
 * carries everything the row does except the cast's names — those are looked
 * up in the project's own characters, and a character no longer in the
 * project reads as deleted, which is what the feed says too.
 */
export function rowOfRecord(
  record: RunRecord,
  characters: Array<{ id: string; name: string }>,
): RunFeedRow {
  const first = record.outputs[0];
  return {
    id: record.id,
    lib: record.lib,
    project: record.project,
    status: record.status,
    kind: record.kind,
    engine: record.engine,
    model: record.model,
    created: record.created,
    updated: null,
    submitted: record.submitted,
    completed: record.completed,
    error: record.error,
    cost: record.cost,
    ...(record.fingerprint ? { fingerprint: record.fingerprint } : {}),
    plan: record.plan,
    characters: record.characters,
    cast: (record.cast ?? record.characters).map((id) => ({
      id,
      name: characters.find((each) => each.id === id)?.name ?? null,
    })),
    sends: record.sends,
    outputs: record.outputs,
    thumb: first ? { node: first.node, url: first.url } : null,
  };
}
