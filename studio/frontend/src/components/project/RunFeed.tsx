import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useInfiniteQuery } from "@tanstack/react-query";

import {
  Alert,
  Badge,
  Button,
  DateInput,
  Field,
  Input,
  Select,
  Text,
  Toggle,
  ToggleGroup,
  type DateStatus,
} from "@ansavva/design-system";

import { getRuns } from "../../apis/studio";
import { useNow } from "../../hooks/useNow";
import { useRunWatch } from "../../hooks/useRunWatch";
import { useSearchParamState } from "../../hooks/useSearchParamState";
import type { HeroImage, RunAsset, RunFeedRow, RunStatus } from "../../types";
import { costParts } from "../../utils/cost";
import { ApertureSpinner } from "../common/Aperture";
import { EmptyState } from "../common/EmptyState";
import { FilterBar } from "../common/FilterBar";
import {
  ChevronDownIcon,
  ChevronUpIcon,
  FeedIcon,
  SearchIcon,
  TilesIcon,
} from "../common/icons";
import { LoadError } from "../common/LoadError";
import { PromptText } from "../common/PromptText";
import { SectionLoading } from "../common/SectionLoading";
import { CharacterTag } from "../character/CharacterChip";
import {
  elapsedSince,
  groupByDay,
  inFlight,
  relativeTime,
} from "../run/feedTime";
import { expectedOutputs, ratioOf } from "../run/aspect";
import { OutputTile } from "../run/OutputTile";
import { SendThumbs } from "../run/SendThumbs";
import { ParamChips } from "../run/ParamChips";
import { PromoteDrawer } from "../run/PromoteDrawer";
import { promptText } from "../run/seed";
import { useRunActions } from "../run/useRunActions";
import { RunActionRow } from "../run/RunActionRow";
import { RunTiles } from "./RunTiles";

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

/**
 * **In flight is `neutral`, not `warning`.** A run that is still going is not a
 * problem, and gold over a wall of media read as one — in a palette whose whole
 * rule is that the chrome carries almost no chroma. The shimmer and the ticking
 * elapsed time are what say "working".
 */
const STATUS_INTENT: Record<RunStatus, "neutral" | "success" | "danger"> = {
  draft: "neutral",
  discarded: "neutral",
  pending: "neutral",
  running: "neutral",
  succeeded: "success",
  failed: "danger",
  cancelled: "neutral",
  adopted: "neutral",
};

/**
 * The two ways the runs draw, and the address carries which.
 *
 * `feed` is a row per run, plan beside outputs; `tiles` is the outputs alone,
 * a square each, the design system's `ImageList`. Same pages, same filters,
 * same lightbox on a press — a layout, not a place — and a URL key like the
 * filters' so the wall survives a reload and the run opened from it closes
 * back to it (`openRun` carries the search). `layout`, not `view`: the Files
 * tab's browser already rides in `view`, and a project's tabs share one
 * address.
 */
export const LAYOUT_FEED = "feed";
export const LAYOUT_TILES = "tiles";

export interface FeedFilters {
  status: string;
  /** `image`, `video`, or both when empty — the run's kind, `?kind=` on the route. */
  kind: string;
  character: string;
  model: string;
  since: string;
  q: string;
  /**
   * One scene's runs. A URL filter like the others rather than a prop, so a
   * run opened from a scene page — `/p/<project>/r/<run>?scene=<id>` — keeps
   * walking the scene's rows in the lightbox, off the same cache.
   */
  scene: string;
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
  const [kind, setKind] = useSearchParamState("kind", "");
  const [character, setCharacter] = useSearchParamState("character", "");
  const [model, setModel] = useSearchParamState("model", "");
  const [since, setSince] = useSearchParamState("since", "");
  const [q, setQ] = useSearchParamState("q", "");
  const [scene, setScene] = useSearchParamState("scene", "");

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
    // `scene` is not cleared: it is where the feed IS, not a filter on it.
    for (const key of ["status", "kind", "character", "model", "since", "q"])
      next.delete(key);
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const applied = useMemo<FeedFilters>(
    () => ({
      status,
      kind,
      character,
      model: model.trim(),
      since,
      q: q.trim(),
      scene,
    }),
    [character, kind, model, q, scene, since, status],
  );

  return {
    applied,
    setStatus,
    setKind,
    setCharacter,
    setModel,
    setSince,
    setQ,
    setScene,
    clear,
    activeCount: [status, kind, character, model.trim(), since].filter(Boolean)
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
 * **The pages are never re-read on a timer.** Refetching an infinite query
 * re-runs every page it holds, so watching one run land used to cost a
 * `?view=feed` call per loaded page every five seconds — each re-reading an
 * envelope per row and re-signing every send and output on it. `useRunWatch`
 * asks after the rows that are actually out, one `GET /api/runs/<id>` each,
 * and writes what comes back into these pages. See the hook for the rest.
 */
export function useRunFeed(projectId: string, filters: FeedFilters) {
  const key = useMemo(
    () => ["runs", "feed", projectId, filters],
    [filters, projectId],
  );
  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ pageParam }) =>
      getRuns({
        project: projectId,
        view: "feed",
        // "Any status" means any — see `STATUSES`.
        ...(filters.status
          ? { status: filters.status }
          : { include: "drafts" }),
        ...(filters.kind ? { kind: filters.kind } : {}),
        ...(filters.model ? { model: filters.model } : {}),
        ...(filters.character ? { character: filters.character } : {}),
        ...(filters.since ? { since: filters.since } : {}),
        ...(filters.q ? { q: filters.q } : {}),
        ...(filters.scene ? { scene: filters.scene } : {}),
        ...(pageParam ? { cursor: pageParam } : {}),
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.cursor,
  });

  const rows = useMemo(
    () => (query.data?.pages ?? []).flatMap((page) => page.runs),
    [query.data],
  );

  useRunWatch(key, rows);

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
  const [layout, setLayout] = useSearchParamState("layout", LAYOUT_FEED);
  const tiles = layout === LAYOUT_TILES;

  const anyInFlight = feed.rows.some((row) => inFlight(row.status));
  const now = useNow(anyInFlight);
  const groups = useMemo(() => groupByDay(feed.rows, now), [feed.rows, now]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {/* The prompt search, where the mockup puts it: on the feed, always
            open, under "Search prompts … in this project". Applies on Enter —
            a request per keystroke against a route that scans envelopes is
            the wrong bargain.

            `h-8`, because this strip is the 32px line the `sm` layout pair
            and the filter button already sit on, not a field row. The
            package's `Input` composes its classes through `cn` (tailwind-
            merge), so `h-8` DISPLACES its own `h-10` rather than joining it
            — measured: the rendered element carries `h-8` and no `h-10` — and
            `app.css`'s `input.h-10 { height: 2.75rem }` then has nothing to
            match. One class on the input, no selector in the stylesheet. */}
        <div className="relative min-w-48 flex-1">
          <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 fill-none stroke-current stroke-[1.5] text-muted" />
          <Input
            value={q}
            onValueChange={setQ}
            placeholder="Search prompts in this project…"
            aria-label="Search prompts"
            className="h-8 pl-8"
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

          {/* What the run made. Stills, clips, or — the default — both: a
              wall of clips is the reel a project has, and a wall of stills
              is its frames. */}
          <div className="min-w-36">
            <Field.Root name="kind">
              <Field.Label>Kind</Field.Label>
              <Select
                options={[
                  { value: "", label: "Images and videos" },
                  { value: "image", label: "Images" },
                  { value: "video", label: "Videos" },
                ]}
                value={filters.applied.kind}
                onValueChange={filters.setKind}
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

        {/* The layout pair, the Files tab's Folders | Media control over
            again: `sm` to sit on the row's 32px line, single-select with
            empty refused, a glyph on a phone and the word beside it above
            `sm`. `label` keeps the accessible name where the word is not
            drawn. */}
        <ToggleGroup.Root
          aria-label="Layout"
          size="sm"
          value={[tiles ? LAYOUT_TILES : LAYOUT_FEED]}
          onValueChange={(next) => {
            if (next.length > 0) setLayout(next[0]!);
          }}
        >
          <Toggle value={LAYOUT_FEED} label="Feed">
            <FeedIcon className="size-4 fill-none stroke-current stroke-[1.5] sm:hidden" />
            <span className="hidden sm:inline">Feed</span>
          </Toggle>
          <Toggle value={LAYOUT_TILES} label="Tiles">
            <TilesIcon className="size-4 fill-none stroke-current stroke-[1.5] sm:hidden" />
            <span className="hidden sm:inline">Tiles</span>
          </Toggle>
        </ToggleGroup.Root>
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
          {tiles ? (
            <RunTiles groups={groups} now={now} onOpen={onOpen} />
          ) : (
            groups.map((group) => (
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
            ))
          )}

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

  return (
    <article
      aria-label={`Run ${relativeTime(row.created, now)}`}
      // **The outputs column takes the rest of the width; the plan is what is
      // capped.** It used to be the other way round — `minmax(0,48rem)` for the
      // outputs — so a row was 80rem wide however wide the window was, and a
      // 2000px screen drew a quarter of itself empty down the right-hand side
      // of every row. What the cap was protecting against is a clip blown up to
      // half a column; that is the tile grid's job below, and it does it by
      // fitting MORE tiles across rather than bigger ones.
      className="grid gap-4 border-t border-line pt-4 md:grid-cols-[minmax(0,1fr)_minmax(20rem,32rem)] md:gap-6"
    >
      {/* Outputs. One grid for both kinds, so a still and a clip are the same
          width in the same column.

          **`content-start`, and it is load-bearing.** This column is a cell of
          the article's own grid, so it is stretched to whatever the plan beside
          it is tall — and a grid whose rows are free to grow hands that height
          to its one row of tiles. Every still became a 100px picture at the top
          of a 360px box: two thirds of every tile was black, the eye read the
          black as part of the picture, and a press there landed on the hover
          overlay below rather than on the picture. Rows keep their own height;
          the slack stays at the foot of the column. */}
      {/* **`auto-fill` with a floor, not a fixed count.** Four across of
          whatever width meant a still was 190px on a 1400px screen and 370px on
          a 2400px one; now the tile has a size and the row has as many as fit —
          four across on a wide screen, one on a phone.

          **One floor, not one per kind.** Stills had `11rem` and clips
          `18rem`, on the reasoning that a portrait reads small and a wide
          frame does not — and the feed showed a clip at twice the width of
          the still it was made from, one row apart. The output is the unit
          here, whatever its shape; a still and a clip get the same track.

          **`min(18rem, 100%)`, not `18rem`.** A floor is a promise the column
          has to be able to keep. The plan column beside this one grows to its
          32rem cap on any long prompt, and on a feed around 800px wide that
          left this column ~150px — narrower than the clip's floor — so the
          one tile overflowed its cell and ran under the prompt beside it.
          The floor is now the smaller of the tile's size and the column's. */}
      <div className="grid content-start gap-2 sm:grid-cols-[repeat(auto-fill,minmax(min(18rem,100%),1fr))]">
        {flying ? (
          <>
            {/* **A training run's outputs land while it runs.** Each
                checkpoint pair is filed the minute it reaches the bucket, so
                a running row of that kind draws what has landed and keeps one
                in-flight tile for what is still training. Every other kind
                has no outputs until it closes, so this maps nothing. */}
            {row.outputs.map((asset, index) => (
              <OutputTile
                key={asset.node}
                row={row}
                asset={asset}
                index={index}
                onOpen={() => onOpen(row, index)}
                onPromote={() => setPromoting(asset)}
                actions={actions}
              />
            ))}
            <InFlightTiles row={row} now={now} />
          </>
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

      {/* The plan. **Every row has one job**: the header says what state the
          run is in and what it can do; the tiles say what it was handed; the
          box says what it was told; the tags say the rest. The sheet's
          order, read back — a run is what the sheet sent. */}
      <div className="flex min-w-0 flex-col gap-2.5">
        {/* **The controls never leave the badges' line.** The header is a
            container; when it is narrower than 30rem the meta is sent to
            the end of the flex order on a full-width basis — its own line
            under the badges — and `RunActionRow` drops Edit's word. What
            wraps is the time, never the buttons. */}
        <div className="@container flex flex-wrap items-center gap-1.5">
          <StatusBadge status={row.status} />
          <Badge intent="neutral" className="font-mono">
            {row.kind}
          </Badge>
          <Text
            variant="caption"
            family="mono"
            tone="muted"
            className="tabular-nums @max-[30rem]:order-last @max-[30rem]:basis-full"
          >
            {flying ? `sent ${relativeTime(row.submitted, now)}` : runMeta(row, now)}
          </Text>
          <RunActionRow
            row={row}
            actions={actions}
            onOpen={() => onOpen(row)}
            folderHref={actions.folderHref}
            className="ml-auto"
          />
        </div>

        <SendThumbs sends={row.sends} />

        <RunPrompt row={row} />

        <ParamChips
          params={row.plan?.params}
          model={row.model}
          leading={<CastTags cast={row.cast} heroes={heroes} />}
        />

        {actions.rerunFailure && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not create the run</Alert.Title>
            <Alert.Description>{actions.rerunFailure}</Alert.Description>
          </Alert.Root>
        )}
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
 * `2h ago · USD 0.088 · 199s` — when, what it cost, how long the model took.
 * Each part only when it is known; a draft is just its age.
 */
export function runMeta(row: RunFeedRow, now: number): string {
  const { price, seconds } = costParts(row.cost);
  return [relativeTime(row.created, now), price, seconds].filter(Boolean).join(" · ");
}

/**
 * The run's cast as tags, first on the line of facts. Nothing when there is
 * none — a `ParamChips` with no leading tags draws the parameters alone.
 */
export function CastTags({
  cast,
  heroes,
}: {
  cast: RunFeedRow["cast"];
  heroes: Record<string, HeroImage | null>;
}) {
  if (cast.length === 0) return null;
  return (
    <>
      {cast.map((member) => (
        <CharacterTag
          key={member.id}
          id={member.id}
          name={member.name ?? "deleted character"}
          hero={heroes[member.id] ?? null}
        />
      ))}
    </>
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
      className="gap-1.5 font-mono"
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
  // Less what has already landed (a training run's checkpoints), never none:
  // the spinner and the clock live on the first tile.
  const count = Math.max(expectedOutputs(row) - row.outputs.length, 1);
  const ratio = ratioOf(row);
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          data-testid="in-flight-tile"
          style={{ aspectRatio: ratio }}
          // `md`, the corner `RunTiles` gives the same run on the wall.
          className="studio-shimmer flex flex-col items-center justify-center gap-2 rounded-md border border-line"
        >
          {i === 0 && (
            <>
              <ApertureSpinner
                size="lg"
                label={`Run ${row.status}`}
                className="text-muted"
              />
              <Text variant="body" weight="medium" tone="muted">
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
          // `md`, the corner `RunTiles` gives the same draft on the wall.
          className="flex flex-col items-center justify-center rounded-md border border-dashed border-line bg-surface-alt/40"
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
 *
 * **The opened run's rail draws this same one.** It had a box of its own —
 * the whole prompt behind a `max-h-48` scroll — which on a phone is a scroll
 * inside the scroll the frame already is: the prompt cut off mid-line with
 * nothing saying there was more, and the feed's More a screen back. One
 * clamp, one word, both places.
 */
/**
 * The box the prompt sits in — the sheet's fill under the sheet's text.
 *
 * On the sheet the prompt reads as a thing because the frosted card is
 * around it; drawn bare in a feed row it was lines of body type between a
 * row of tiles and a row of chips, and the More and the Negative under it
 * read as three more loose lines. The fill gives it an edge: the prompt,
 * the way to read the rest, and the negative prompt under a hairline are
 * one block, and the chips are what comes after it.
 */
const PROMPT_BOX = "flex w-full flex-col gap-2 rounded-md bg-fill-faint px-3 py-2";

export function RunPrompt({ row, className = "" }: { row: RunFeedRow; className?: string }) {
  const text = promptText(row.plan?.prompt);
  const negative = negativePromptOf(row.plan?.params);

  if (!text) {
    return (
      <div className={`${PROMPT_BOX} ${className}`}>
        <Text variant="body" tone="muted">
          {row.plan ? "No prompt." : "This run predates the plan."}
        </Text>
      </div>
    );
  }

  return (
    <div className={`${PROMPT_BOX} ${className}`}>
      <Clamped text={text} />
      {/* **The negative prompt is prose, and reads as prose.** It is a
          parameter to the provider and was drawn as one — a `key value` pill
          beside `seed` — which for a sentence is the wrong shape: the pill
          either clipped it or wrapped into a box no one would read. It is a
          second prompt, so it gets the prompt's treatment under a word saying
          which one it is, and `ParamChips` leaves it out. */}
      {negative && (
        <div className="flex items-baseline gap-2 border-t border-line pt-2">
          <Text variant="caption" tone="muted" className="shrink-0">
            Negative
          </Text>
          <PromptText text={negative} tone="muted" className="min-w-0" />
        </div>
      )}
    </div>
  );
}

/** The plan's `negative_prompt`, when it is a non-empty string. */
export function negativePromptOf(params: Record<string, unknown> | undefined): string | null {
  const raw = params?.negative_prompt;
  return typeof raw === "string" && raw.trim() !== "" ? raw : null;
}

/**
 * Three lines and a way to read the rest — the prompt's clamp.
 *
 * **Drawn as the create sheet draws it** — `PromptText`: the sheet's face,
 * its line height, its pills for a citation — and clamped, which the sheet
 * is not. The sheet holds one prompt; a feed holds twenty, and a list whose
 * rows are as tall as their prompts is a list nobody scrolls.
 *
 * **Clamped by height and faded, not `line-clamp`.** The prompt is
 * pre-wrapped, so a paragraph break is a line, and `line-clamp-3` on two
 * short paragraphs put its `…` alone on the blank third line — an ellipsis
 * with nothing before it, which read as a rendering fault. A box three lines
 * tall that fades out at its foot says "there is more" wherever the cut
 * falls, and More under it says where to press.
 */
function Clamped({ text, tone }: { text: string; tone?: "muted" }) {
  const [expanded, setExpanded] = useState(false);
  /**
   * Whether the clamp is hiding anything — measured, not guessed. It was
   * `text.length > 220`, a rough three lines of prose, and a prompt is not
   * only prose: two short paragraphs are three lines with the blank one
   * between, and a pill is wider than the characters it holds. Either
   * clamped the text and drew no More, which is text cut off with nothing
   * saying so. The box says whether it overflowed; asked again when the
   * text changes and when the column is resized.
   */
  const box = useRef<HTMLDivElement>(null);
  const [long, setLong] = useState(false);
  useLayoutEffect(() => {
    const element = box.current;
    if (!element) return;
    const measure = () => {
      // Only the clamped box can overflow; an expanded one is as tall as
      // its text, and would read as "nothing hidden" and drop the Less.
      if (element.dataset.clamped !== undefined)
        setLong(element.scrollHeight > element.clientHeight + 1);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [text, expanded]);

  return (
    <div className="flex flex-col gap-1">
      {/* `max-h-18`: three lines at `leading-6`. The mask only once there is
          something under it — a short prompt must not fade.

          **Paragraph gaps are collapsed while clamped.** Three lines is the
          budget, and a blank line spent one of them on nothing: two short
          paragraphs showed two lines of text and a fade over an empty third.
          The gaps come back on More — the string itself is never touched. */}
      <PromptText
        ref={box}
        text={expanded ? text : text.replace(/\n{2,}/g, "\n")}
        tone={tone}
        data-clamped={expanded ? undefined : ""}
        className={
          expanded
            ? ""
            : `max-h-18 overflow-hidden ${
                long ? "[mask-image:linear-gradient(to_bottom,black_55%,transparent)]" : ""
              }`
        }
      />
      {/* A small pill at the box's right edge, where the fade points, rather
          than a bare word at the left where it read as one more line. */}
      {long && (
        <div className="-mt-1 flex justify-end">
          <Button
            intent="secondary"
            size="sm"
            onClick={() => setExpanded((current) => !current)}
            aria-expanded={expanded}
            className="h-6 gap-1 rounded-pill bg-fill pl-2.5 pr-2 text-xs text-muted hover:text-ink"
          >
            {expanded ? "Less" : "More"}
            {expanded ? (
              <ChevronUpIcon className="size-3 fill-none stroke-current stroke-2" />
            ) : (
              <ChevronDownIcon className="size-3 fill-none stroke-current stroke-2" />
            )}
          </Button>
        </div>
      )}
    </div>
  );
}


