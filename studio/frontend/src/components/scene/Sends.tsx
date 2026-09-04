import { Badge, Button, Text } from "@ansavva/design-system";

import type { Panel, PanelRole, RunAsset, Shot } from "../../types";
import { MediaThumb } from "../media/MediaThumb";

/**
 * The storyboard, split out of `ScenePage`.
 *
 * The page was 813 lines holding a board, a card, a prompt document, an editor
 * and a filmstrip — five things that change for different reasons. Nothing here
 * changed in the move.
 */

/**
 * What this shot intends to send, and what it deliberately does not.
 *
 * **The plan's declaration, not the resolved payload.** Which images actually
 * reach the engine is decided by the submit path against that engine's own rules
 * — Kling counts the start frame toward its cap of 7 and drops every reference
 * the moment an end frame joins them, Seedance excludes references from a start
 * frame outright — and those rules live in one place on purpose. This draws what
 * the storyboard asked for and names the command that resolves it, rather than
 * reimplementing the arithmetic and drifting from it.
 *
 * The distinction it exists to make visible: **a panel's references steer the
 * STILL, and are not what the video engine receives.** Those are two lists and
 * they were both invisible, which is how "why aren't you showing me the images
 * you intend to send" became a fair question.
 */
export function Sends({
  shot,
  bracketed,
  onView,
  onOpenRun,
}: {
  shot: Shot;
  bracketed: boolean;
  onView: (asset: RunAsset) => void;
  /** Opens the run that produced a tile. Absent on tiles that had no run. */
  onOpenRun: (run: string) => void;
}) {
  const panels = shot.panels ?? [];
  const withRole = (role: PanelRole) => panels.filter((p) => p.role === role);
  const handoff =
    shot.continues !== false && shot.opens_on?.node ? shot.opens_on : null;
  const startPanel = withRole("start")[0];
  const endPanel = withRole("end")[0];
  // A handoff outranks a start panel and demotes it to a reference — the only
  // frame that makes a cut seamless is the literal last frame of the shot before.
  const demoted = handoff && startPanel ? [startPanel] : [];
  const references = [...demoted, ...withRole("reference")];
  const samples = withRole("sample");
  const assets = shot.motion?.reference_assets ?? [];

  return (
    <section className="flex flex-col gap-3 rounded-none border border-line p-2">
      <SendRow label="Start">
        {handoff?.frame ? (
          <Frame
            hint="handoff"
            asset={handoff.frame}
            onOpen={onView}
            run={handoff.from_run}
            onOpenRun={onOpenRun}
          />
        ) : startPanel ? (
          <Frame
            hint={panelHint(startPanel, false)}
            title={startPanel.prompt}
            asset={startPanel.image}
            onOpen={onView}
            run={startPanel.run}
            onOpenRun={onOpenRun}
          />
        ) : (
          <Slot note="awaits previous shot" />
        )}
      </SendRow>

      {/* **Only when the scene brackets its shots.** A chained scene has no end
          frames anywhere, so a row saying "none" on all seven cards is seven
          rows of nothing. The mode is stated once, at the top of the board. */}
      {bracketed && (
        <SendRow label="End">
          {endPanel ? (
            <Frame
              hint={panelHint(endPanel, false)}
              title={endPanel.prompt}
              asset={endPanel.image}
              onOpen={onView}
              run={endPanel.run}
              onOpenRun={onOpenRun}
            />
          ) : (
            <Slot note="not bracketed" />
          )}
        </SendRow>
      )}

      <SendRow label="References">
        {references.map((p) => (
          <Frame
            key={`p${p.n}`}
            hint={panelHint(p, demoted.includes(p))}
            title={p.prompt}
            asset={p.image}
            onOpen={onView}
            run={p.run}
            onOpenRun={onOpenRun}
          />
        ))}
        {assets.map((a) => (
          <Frame
            key={a.node}
            hint="reference"
            title={a.name}
            asset={a}
            onOpen={onView}
          />
        ))}
        {references.length === 0 && assets.length === 0 && (
          <Slot note="scene frames" />
        )}
      </SendRow>

      {samples.length > 0 && (
        <SendRow label="Samples">
          {samples.map((p) => (
            <Frame
              key={`s${p.n}`}
              hint="not sent"
              title={p.prompt}
              asset={p.image}
              onOpen={onView}
              run={p.run}
              onOpenRun={onOpenRun}
            />
          ))}
        </SendRow>
      )}
    </section>
  );
}

/**
 * Whether a scene pins its shots at both ends.
 *
 * Chained is the default and the common case: one seed, every later shot opening
 * on the previous shot's last frame. Bracketed shots carry an `end` panel. The
 * board states which it is once rather than printing "not bracketed" on every
 * card of a scene that was never going to be.
 */
export function isBracketed(shots: Shot[]): boolean {
  return shots.some((s) => (s.panels ?? []).some((p) => p.role === "end"));
}

/**
 * An empty slot — a frame that is planned and not here.
 *
 * **Drawn, not described.** A storyboard is read by looking, so an absent frame
 * is a dashed rectangle the same size as a real one, not a sentence floating
 * where a picture should be. Two or three words inside it say why it is empty.
 */
export function Slot({ note }: { note: string }) {
  return (
    // `w-24`, matching `Frame`. A slot, a rendered panel and an unrendered one
    // are the same thing in three states — an image position on the board — and
    // this drew one of them four pixels narrower, so a row of Start /
    // References / Samples stepped in and out as panels rendered.
    <span
      className="flex aspect-[3/4] w-24 shrink-0 items-center justify-center rounded-none
                 border border-dashed border-line bg-surface-alt p-1 text-center"
    >
      <Text variant="caption" tone="muted">
        {note}
      </Text>
    </span>
  );
}

/**
 * The one thing most worth saying about a panel, in priority order.
 *
 * `stale` outranks the rest because it is the only one that means the picture is
 * WRONG — the prompt moved on after the image was rendered, so what you are
 * looking at no longer illustrates the words beside it. Demotion and absence are
 * both ordinary states of a board.
 */
function panelHint(panel: Panel, demoted: boolean): string | undefined {
  if (panel.stale) return "stale";
  if (demoted) return "demoted";
  if (!panel.image) return "not rendered";
  return undefined;
}

export function SendRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <Text variant="caption" tone="muted">
        {label}
      </Text>
      <div className="flex flex-wrap items-start gap-2">{children}</div>
    </div>
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
export function Frame({
  label,
  hint,
  title,
  asset,
  onOpen,
  run,
  onOpenRun,
}: {
  /** Omitted inside a `SendRow`, whose own label already says what this is. */
  label?: string;
  hint?: string;
  title?: string;
  asset?: RunAsset;
  /** Opens the frame in the board's viewer. The asset, not its id — the tile
      already holds everything the drawer needs to draw it. */
  onOpen: (asset: RunAsset) => void;
  /**
   * The run that produced this tile, when one did.
   *
   * **Every picture on this board came from somewhere and none of them said
   * where.** A sample, a start frame, a reference and the clip are all run
   * output, and the run holds the prompt and the payload that made them — the
   * things you want the moment a tile looks wrong. The board
   * had one link, on the shot, so a sample that came out badly was a dead end.
   */
  run?: string | null;
  onOpenRun?: (run: string) => void;
}) {
  const isVideo = (asset?.content_type ?? "").startsWith("video/");

  const shell = asset?.url ? (
    <MediaThumb
      nodeId={asset.node}
      url={asset.url}
      name={asset.name}
      isVideo={isVideo}
      aspect="portrait"
      className="w-24 shrink-0 rounded-none border border-line"
    />
  ) : (
    // A planned-but-unrendered panel is the normal state of a board, not an
    // error, so it draws as a dashed frame carrying its prompt.
    <span
      className="flex aspect-[3/4] w-24 shrink-0 items-center justify-center overflow-hidden rounded-none
                 border border-dashed border-line bg-surface-alt p-1 text-center"
    >
      <Text variant="caption" tone="muted" className="line-clamp-4">
        {title || "not rendered"}
      </Text>
    </span>
  );

  return (
    <span className="flex w-24 shrink-0 flex-col gap-1">
      {asset?.url ? (
        <button
          type="button"
          onClick={() => onOpen(asset)}
          title={title ?? asset.name}
          className="text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          {shell}
        </button>
      ) : (
        <span title={title}>{shell}</span>
      )}
      {(label || hint) && (
        <span className="flex flex-wrap items-center gap-1">
          {label && (
            <Text variant="caption" tone="muted">
              {label}
            </Text>
          )}
          {hint && (
            <Badge intent={hint === "stale" ? "warning" : "neutral"}>
              {hint}
            </Badge>
          )}
        </span>
      )}
      {run && onOpenRun && (
        <Button intent="secondary" size="sm" onClick={() => onOpenRun(run)}>
          Run
        </Button>
      )}
    </span>
  );
}
