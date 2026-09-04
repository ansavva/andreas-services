import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";

import {
  Alert,
  Badge,
  Button,
  DateInput,
  Dropdown,
  Field,
  Input,
  Select,
  Text,
  buttonClass,
  useToast,
  type DateStatus,
} from "@ansavva/design-system";

import { getRuns, submitRun } from "../../apis/studio";
import { useNow } from "../../hooks/useNow";
import { useSearchParamState } from "../../hooks/useSearchParamState";
import type { HeroImage, RunAsset, RunFeedRow, RunStatus } from "../../types";
import { formatCost } from "../../utils/cost";
import { ApertureSpinner } from "../common/Aperture";
import { ConfirmDeleteButton } from "../common/ConfirmDeleteButton";
import { EmptyState } from "../common/EmptyState";
import { FilterBar } from "../common/FilterBar";
import {
  DotsIcon,
  FolderIcon,
  PencilIcon,
  RerunIcon,
  SearchIcon,
} from "../common/icons";
import { linkButtonClass } from "../common/linkButtonClass";
import { LoadError } from "../common/LoadError";
import { SectionLoading } from "../common/SectionLoading";
import { CharacterChipLink } from "../character/CharacterChip";
import { MediaThumb } from "../media/MediaThumb";
import { ArmedButton } from "../run/ArmedButton";
import {
  elapsedSince,
  groupByDay,
  inFlight,
  relativeTime,
} from "../run/feedTime";
import { ratioOf } from "../run/aspect";
import { OutputTile } from "../run/OutputTile";
import { ParamChips } from "../run/ParamChips";
import { PromoteDrawer } from "../run/PromoteDrawer";
import { promptText } from "../run/seed";
import { useRunActions } from "../run/useRunActions";

/** How often the feed re-reads while a run in it can still move. */
export const FEED_POLL_MS = 5_000;

/**
 * What the filter offers, and `draft` is on it deliberately.
 *
 * **"Any status" includes drafts, and this feed asks for them explicitly.** The
 * route hides them from a listing that names no status, on the reasoning that a
 * grid mixing intentions with submissions is a grid nobody can read. That is a
 * fair default for a route; it is not one a control labelled `Any status` may
 * apply silently. Drafts are the one thing a person has to be able to FIND — an
 * unsent payload nobody can see is a queue nobody works through.
 *
 * `discarded` is absent: it is gone, and offering a filter for it would suggest
 * otherwise.
 */
const STATUSES: RunStatus[] = [
  "draft",
  "pending",
  "running",
  "succeeded",
  "failed",
  "cancelled",
];

const STATUS_INTENT: Record<
  RunStatus,
  "neutral" | "success" | "danger" | "warning"
> = {
  draft: "neutral",
  discarded: "neutral",
  pending: "warning",
  running: "warning",
  succeeded: "success",
  failed: "danger",
  cancelled: "neutral",
  adopted: "neutral",
};

export interface FeedFilters {
  status: string;
  character: string;
  model: string;
  since: string;
  q: string;
}

/**
 * The five fields, each in the address.
 *
 * URL state, exactly as the file browser's `q`/`tags` are, so a filtered view
 * of a project's runs survives a reload and is a link somebody can be handed.
 * The model and the search box are typed and apply on Enter; the others are
 * chosen and apply on change. `applied` is what the query reads — the typed
 * fields are held locally until Enter so a request per keystroke never goes.
 */
export function useFeedFilters() {
  const [status, setStatus] = useSearchParamState("status", "");
  const [character, setCharacter] = useSearchParamState("character", "");
  const [model, setModel] = useSearchParamState("model", "");
  const [since, setSince] = useSearchParamState("since", "");
  const [q, setQ] = useSearchParamState("q", "");

  /**
   * One write, not five.
   *
   * `useSearchParamState` gives each field its own setter, and each reads the
   * URL fresh from its own render — calling all of them in one handler has
   * every one build its `next` from the SAME snapshot, so only the last
   * dispatch's single deletion survives.
   */
  const [searchParams, setSearchParams] = useSearchParams();
  const clear = useCallback(() => {
    const next = new URLSearchParams(searchParams);
    for (const key of ["status", "character", "model", "since", "q"])
      next.delete(key);
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const applied = useMemo<FeedFilters>(
    () => ({ status, character, model: model.trim(), since, q: q.trim() }),
    [character, model, q, since, status],
  );

  return {
    applied,
    setStatus,
    setCharacter,
    setModel,
    setSince,
    setQ,
    clear,
    activeCount: [status, character, model.trim(), since].filter(Boolean)
      .length,
  };
}

/**
 * The feed's pages, and whether any row in them can still move.
 *
 * **One key, shared.** The feed draws from it and the opened run walks it —
 * Left/Right and the filmstrip step through the rows already loaded, from the
 * same cache, so opening a run costs no second listing.
 *
 * Polls while a row is in flight, at the interval the old run page used, and
 * stops on its own when nothing can change — `inFlight` is what decides.
 */
export function useRunFeed(projectId: string, filters: FeedFilters) {
  const query = useInfiniteQuery({
    queryKey: ["runs", "feed", projectId, filters],
    queryFn: ({ pageParam }) =>
      getRuns({
        project: projectId,
        view: "feed",
        // "Any status" means any — see `STATUSES`.
        ...(filters.status
          ? { status: filters.status }
          : { include: "drafts" }),
        ...(filters.model ? { model: filters.model } : {}),
        ...(filters.character ? { character: filters.character } : {}),
        ...(filters.since ? { since: filters.since } : {}),
        ...(filters.q ? { q: filters.q } : {}),
        ...(pageParam ? { cursor: pageParam } : {}),
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.cursor,
    refetchInterval: (state) => {
      const pages = state.state.data?.pages ?? [];
      return pages.some((page) => page.runs.some((run) => inFlight(run.status)))
        ? FEED_POLL_MS
        : false;
    },
  });

  const rows = useMemo(
    () => (query.data?.pages ?? []).flatMap((page) => page.runs),
    [query.data],
  );

  return { ...query, rows };
}

interface Props {
  projectId: string;
  /** The project's characters, so the filter offers names rather than ids. */
  characters: Array<{ id: string; name: string }>;
  /** Every character's card image by id, for the cast chips. */
  heroes: Record<string, HeroImage | null>;
  /** Open a run — the row's press, and a tile's. */
  onOpen: (row: RunFeedRow, output?: number) => void;
}

/**
 * Every run in a project, newest first, grouped by day — the screen the
 * mockup calls the feed.
 *
 * **One row per run: outputs on the left, the plan on the right.** A run is
 * what it made and what it was for, and the two read side by side. The row
 * carries everything from one list call (`?view=feed`) — the plan, every send
 * signed, every output signed, the cast by name — so no row fetches anything.
 *
 * A run in flight draws full-size shimmering tiles with the aperture spinner
 * and the seconds since it went out, and the feed polls until it lands.
 */
export function RunFeed({ projectId, characters, heroes, onOpen }: Props) {
  const filters = useFeedFilters();
  const feed = useRunFeed(projectId, filters.applied);
  const [model, setModel] = useState(filters.applied.model);
  const [q, setQ] = useState(filters.applied.q);

  const anyInFlight = feed.rows.some((row) => inFlight(row.status));
  const now = useNow(anyInFlight);
  const groups = useMemo(() => groupByDay(feed.rows, now), [feed.rows, now]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {/* The prompt search, where the mockup puts it: on the feed, always
            open, under "Search prompts … in this project". Applies on Enter —
            a request per keystroke against a route that scans envelopes is
            the wrong bargain. */}
        <div className="relative min-w-48 flex-1">
          <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 fill-none stroke-current stroke-[1.5] text-muted" />
          <Input
            value={q}
            onValueChange={setQ}
            placeholder="Search prompts in this project…"
            aria-label="Search prompts"
            className="pl-8"
            onKeyDown={(event: React.KeyboardEvent) => {
              if (event.key === "Enter") filters.setQ(q.trim());
            }}
          />
        </div>

        <FilterBar
          activeCount={filters.activeCount}
          onClear={filters.clear}
          label="Filter runs"
        >
          <div className="min-w-40">
            <Field.Root name="status">
              <Field.Label>Status</Field.Label>
              <Select
                options={[
                  { value: "", label: "Any status" },
                  ...STATUSES.map((each) => ({ value: each, label: each })),
                ]}
                value={filters.applied.status}
                onValueChange={filters.setStatus}
              />
            </Field.Root>
          </div>

          <div className="min-w-48">
            <Field.Root name="character">
              <Field.Label>Character</Field.Label>
              <Select
                options={[
                  { value: "", label: "Any character" },
                  ...characters.map((each) => ({
                    value: each.id,
                    label: each.name,
                  })),
                ]}
                value={filters.applied.character}
                onValueChange={filters.setCharacter}
              />
            </Field.Root>
          </div>

          <div className="min-w-56 flex-1">
            <Field.Root name="model">
              <Field.Label>Model</Field.Label>
              <Input
                value={model}
                placeholder="google/nano-banana-pro"
                onValueChange={setModel}
                onKeyDown={(event: React.KeyboardEvent) => {
                  if (event.key === "Enter") filters.setModel(model.trim());
                }}
              />
            </Field.Root>
          </div>

          <div className="min-w-40">
            <Field.Root name="since">
              <Field.Label>Since</Field.Label>
              {/* `DateInput`, not `<input type="date">` — the package has no such
                  type and says why. Only `valid` and `empty` are acted on: `""`
                  means both "cleared" and "half-typed", and re-querying on a
                  half-typed date would drop the filter under the cursor. */}
              <DateInput
                value={filters.applied.since}
                picker="calendar"
                onValueChange={(next: string, status: DateStatus) => {
                  if (status === "valid" || status === "empty")
                    filters.setSince(next);
                }}
              />
            </Field.Root>
          </div>
        </FilterBar>
      </div>

      {feed.isError ? (
        <LoadError
          what="runs"
          message={(feed.error as Error).message}
          onRetry={() => void feed.refetch()}
        />
      ) : feed.isPending ? (
        <SectionLoading label="Loading runs" />
      ) : feed.rows.length === 0 && !feed.hasNextPage ? (
        <EmptyState
          title={
            filters.activeCount > 0 || filters.applied.q
              ? "Nothing here matches that search."
              : "No runs yet."
          }
          hint={
            filters.activeCount > 0 || filters.applied.q
              ? undefined
              : "Describe what to make in the bar above and press Send."
          }
        />
      ) : (
        <div className="flex flex-col gap-5">
          {groups.map((group) => (
            <section
              key={group.label}
              aria-label={group.label}
              className="flex flex-col gap-4"
            >
              <Text variant="caption" tone="muted">
                {group.label}
              </Text>
              {group.rows.map((row) => (
                <FeedRow
                  key={row.id}
                  row={row}
                  heroes={heroes}
                  now={now}
                  onOpen={onOpen}
                />
              ))}
            </section>
          ))}

          {feed.isFetchingNextPage && (
            <SectionLoading label="Loading more runs" />
          )}

          {/* A prompt search can answer a short or empty page with a cursor
              still set — "keep going", not "nothing more" — so the button
              stays while there is a cursor, whatever the page held. */}
          {feed.hasNextPage && !feed.isFetchingNextPage && (
            <div className="flex justify-center">
              <Button
                intent="secondary"
                size="sm"
                onClick={() => void feed.fetchNextPage()}
              >
                Load more
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * How many tiles a run in flight will fill.
 *
 * Read off the plan's own count parameter, whichever name the model gives it;
 * one otherwise. A guess drawn as placeholders costs nothing if wrong — the
 * real outputs replace them the moment the run lands.
 */
export function expectedOutputs(row: RunFeedRow): number {
  const params = row.plan?.params ?? {};
  for (const key of ["outputs", "num_outputs", "number_of_images", "n"]) {
    const value = params[key];
    if (typeof value === "number" && value >= 1)
      return Math.min(Math.floor(value), 8);
  }
  return 1;
}

function FeedRow({
  row,
  heroes,
  now,
  onOpen,
}: {
  row: RunFeedRow;
  heroes: Record<string, HeroImage | null>;
  now: number;
  onOpen: Props["onOpen"];
}) {
  const actions = useRunActions(row);
  const [promoting, setPromoting] = useState<RunAsset | null>(null);
  const flying = inFlight(row.status);
  const video = row.kind === "video";

  return (
    <article
      aria-label={`Run ${relativeTime(row.created, now)}`}
      // The outputs column is capped: on a wide screen a half-column clip
      // would be a metre tall, and the plan would sit a screen away from it.
      className="grid gap-4 border-t border-line pt-4 md:grid-cols-[minmax(0,48rem)_minmax(20rem,32rem)] md:gap-6"
    >
      {/* Outputs. The grid is by kind: four stills across, two clips. */}
      <div
        className={
          video
            ? "grid grid-cols-1 gap-2 sm:grid-cols-2"
            : "grid grid-cols-2 gap-2 sm:grid-cols-4"
        }
      >
        {flying ? (
          <InFlightTiles row={row} now={now} />
        ) : row.outputs.length > 0 ? (
          row.outputs.map((asset, index) => (
            <OutputTile
              key={asset.node}
              row={row}
              asset={asset}
              index={index}
              onOpen={() => onOpen(row, index)}
              onPromote={() => setPromoting(asset)}
              actions={actions}
            />
          ))
        ) : row.error ? (
          <div className="sm:col-span-2">
            <Alert.Root intent="danger">
              <Alert.Title>This run failed</Alert.Title>
              <Alert.Description>{row.error}</Alert.Description>
            </Alert.Root>
          </div>
        ) : row.status === "draft" ? (
          <DraftTiles row={row} />
        ) : (
          <div className="sm:col-span-2">
            <EmptyState title="Nothing came back." />
          </div>
        )}
      </div>

      {/* The plan. */}
      <div className="flex min-w-0 flex-col gap-2.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge status={row.status} />
          <Badge intent="neutral" className="rounded-none font-mono">
            {row.kind}
          </Badge>
          <Text
            variant="caption"
            family="mono"
            tone="muted"
            className="ml-auto tabular-nums"
          >
            {flying ? (
              <span className="text-warning">
                sent {relativeTime(row.submitted, now)}
              </span>
            ) : (
              <>
                {relativeTime(row.created, now)}
                {row.cost && formatCost(row.cost, "")
                  ? ` · ${formatCost(row.cost)}`
                  : ""}
              </>
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
                className="size-14 rounded-none border border-line"
              />
            ))}
          </div>
        )}

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

        <ParamChips params={row.plan?.params} model={row.model} />

        {actions.rerunFailure && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not create the run</Alert.Title>
            <Alert.Description>{actions.rerunFailure}</Alert.Description>
          </Alert.Root>
        )}

        <RowActions row={row} actions={actions} />
      </div>

      {promoting && (
        <PromoteDrawer
          asset={promoting}
          runCharacters={row.characters}
          onClose={() => setPromoting(null)}
        />
      )}
    </article>
  );
}

/**
 * The status, with the spinner on it while the run is out.
 *
 * A status is a value the API chose, not prose — mono is what says so, and is
 * what every other status in the app wears.
 */
export function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <Badge
      intent={STATUS_INTENT[status]}
      className="rounded-none gap-1.5 font-mono"
    >
      {inFlight(status) && (
        <ApertureSpinner
          size="sm"
          label={`Run ${status}`}
          className="size-3.5"
        />
      )}
      {status}
    </Badge>
  );
}

/**
 * The full-size placeholders a run in flight fills its row with.
 *
 * The first carries the spinner, the word and the elapsed time; the rest
 * shimmer. As many as the plan asked for, so the row is already the size it
 * will be when the outputs land and nothing below it jumps.
 */
function InFlightTiles({ row, now }: { row: RunFeedRow; now: number }) {
  const count = expectedOutputs(row);
  const ratio = ratioOf(row);
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          data-testid="in-flight-tile"
          style={{ aspectRatio: ratio }}
          className={`studio-shimmer flex flex-col items-center justify-center gap-2 rounded-none border ${
            i === 0 ? "border-warning/50" : "border-line"
          }`}
        >
          {i === 0 && (
            <>
              <ApertureSpinner
                size="lg"
                label={`Run ${row.status}`}
                className="text-warning"
              />
              <Text variant="body" weight="medium" className="text-warning">
                {row.status === "pending" ? "Sending…" : "Running…"}
              </Text>
              <Text
                variant="caption"
                family="mono"
                tone="muted"
                className="tabular-nums"
              >
                {elapsedSince(row.submitted ?? row.created, now)}
              </Text>
            </>
          )}
        </div>
      ))}
    </>
  );
}

/**
 * The empty frames a draft will fill — its outputs' shape and count, drawn
 * dashed, so a row that has not run yet is still the size it will be and the
 * eye has something where the pictures go.
 */
function DraftTiles({ row }: { row: RunFeedRow }) {
  const count = expectedOutputs(row);
  const ratio = ratioOf(row);
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          data-testid="draft-tile"
          style={{ aspectRatio: ratio }}
          className="flex flex-col items-center justify-center rounded-none border border-dashed border-line bg-surface-alt/40"
        >
          {i === 0 && (
            <Text variant="caption" tone="muted">
              Not run yet.
            </Text>
          )}
        </div>
      ))}
    </>
  );
}

/**
 * The prompt, clamped to three lines with a way to read the rest.
 *
 * Prose verbatim; a structured prompt serialised — the pipeline decodes
 * nothing, and the opened run's Request row is where a document reads whole.
 */
function Prompt({ row }: { row: RunFeedRow }) {
  const [expanded, setExpanded] = useState(false);
  const text = promptText(row.plan?.prompt);

  if (!text) {
    return (
      <Text variant="body" tone="muted">
        {row.plan ? "No prompt." : "This run predates the plan."}
      </Text>
    );
  }

  // Long enough that three lines will not hold it — a rough line is ~90
  // characters at this column's width.
  const long = text.length > 220;

  return (
    <div className="flex flex-col items-start gap-1">
      <Text
        variant="body"
        className={
          expanded
            ? "whitespace-pre-wrap break-words"
            : "line-clamp-3 break-words"
        }
      >
        {text}
      </Text>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          aria-expanded={expanded}
          className={linkButtonClass("muted")}
        >
          {expanded ? "Less" : "More"}
        </button>
      )}
    </div>
  );
}

/**
 * The run's own actions: icon+word, in a row, per the mockup.
 *
 * Which ones depends on where the run is. A draft can be Run (the armed
 * two-press gesture, and the press is the act — no approve step anywhere) or
 * edited; a run in flight can only be edited (nothing cancels a prediction
 * here); a finished run can be run again, edited, opened in Files, deleted,
 * or read.
 */
function RowActions({
  row,
  actions,
}: {
  row: RunFeedRow;
  actions: ReturnType<typeof useRunActions>;
}) {
  const client = useQueryClient();
  const toast = useToast();
  const flying = inFlight(row.status);
  const draft = row.status === "draft";

  const run = useCallback(async () => {
    try {
      await submitRun(row.id);
    } catch (err) {
      toast.add({
        intent: "danger",
        title: "Could not submit the run",
        description: (err as Error).message,
      });
    }
    await client.invalidateQueries({ queryKey: ["runs"] });
  }, [client, row.id, toast]);

  return (
    <div className="mt-auto flex flex-wrap items-center gap-1 pt-1">
      {draft && (
        <ArmedButton
          idle="Run"
          armed="Press again — this spends"
          busy="Running…"
          tooltip={`Sends the prompt, the parameters and the ${row.sends.length} image${
            row.sends.length === 1 ? "" : "s"
          } above, in that order. Sends it and starts billing.`}
          onFire={run}
          icon={<RerunIcon className={GLYPH} />}
        />
      )}
      {!draft && !flying && (
        <ArmedButton
          idle="Rerun"
          armed="Press again — this spends"
          busy="Running…"
          tooltip="Runs the same prompt, parameters and images as a new attempt. This one keeps its outputs."
          onFire={actions.rerun}
          intent="secondary"
          icon={<RerunIcon className={GLYPH} />}
          className="rounded-none"
        />
      )}
      <Action
        icon={<PencilIcon className={GLYPH} />}
        label="Edit"
        onClick={actions.edit}
      />
      {actions.folderHref && !flying && (
        <a
          href={actions.folderHref}
          className={buttonClass({
            intent: "secondary",
            size: "sm",
            className: "rounded-none",
          })}
        >
          <FolderIcon className={GLYPH} />
          Folder
        </a>
      )}
      {!flying && (
        <ConfirmDeleteButton
          noun="this run"
          tone="text"
          onConfirm={actions.remove}
          className="rounded-none"
        />
      )}
      <Dropdown.Root>
        <Dropdown.Trigger
          className={buttonClass({
            intent: "secondary",
            size: "sm",
            className: "rounded-none",
          })}
        >
          <DotsIcon className="size-4 fill-current stroke-none" />
          More
        </Dropdown.Trigger>
        <Dropdown.Content className="left-auto right-0">
          <Dropdown.Item onSelect={actions.copyPrompt} disabled={!row.plan}>
            Copy prompt
          </Dropdown.Item>
          <Dropdown.Item onSelect={actions.openRequest}>
            Open request documents
          </Dropdown.Item>
        </Dropdown.Content>
      </Dropdown.Root>
    </div>
  );
}

const GLYPH = "size-4 fill-none stroke-current stroke-[1.5]";

function Action({
  icon,
  label,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <Button
      intent="secondary"
      size="sm"
      onClick={onClick}
      className="rounded-none"
    >
      {icon}
      {label}
    </Button>
  );
}
