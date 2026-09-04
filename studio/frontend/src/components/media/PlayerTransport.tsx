import { useState } from "react";

import { IconButton, Slider, Text } from "@ansavva/design-system";

import type { MediaPlayback } from "../../hooks/useMediaPlayback";
import { formatDuration } from "../../utils/format";
import { PauseIcon, PlayIcon, SeekBackIcon, SeekForwardIcon } from "../common/icons";
import { CHROME_BUTTON } from "./chromeButton";

/** How far back-5 / forward-5 move. Named because the labels say the number. */
const SKIP_SECONDS = 5;

/**
 * The icon set replaces its default class wholesale rather than merging — see
 * the note at the top of `icons.tsx` — so a smaller glyph is a whole string.
 */
const SMALL_GLYPH = "size-4 fill-none stroke-current stroke-[1.5]";

interface PlayerTransportProps {
  /** The playback this transport drives. One `useMediaPlayback` per player. */
  playback: MediaPlayback;
  /**
   * How far the browser has buffered ahead, in seconds.
   *
   * Paints the seek bar's secondary fill. Optional: it is decoration, never a
   * bound on where a seek may go, and a caller that does not track it gets a
   * bar with one fill instead of two.
   */
  buffered?: number;
  /** `sm` for a player inline in a page column, `md` at object or fullscreen size. */
  size?: "sm" | "md";
  className?: string;
}

/**
 * Move through a clip in time: back 5, play/pause, forward 5, a seek bar and
 * the two times.
 *
 * **The controls are `IconButton` and `Slider` from the design system**, which
 * is the whole of what makes this file short. It replaces `VideoScrubber`'s
 * hand-rolled `TransportButton` — a `<button>` with its own hover, focus ring
 * and `aria-label` discipline retyped — and a bare `<input type="range">` that
 * deliberately kept the OS appearance because restyling it meant owning three
 * vendor-prefixed rules. The package owns those rules once now, and paints the
 * track in the app's own roles.
 *
 * **A drag paints, and only the release seeks.** `onValueChange` moves a local
 * position so the thumb follows the finger; `onValueCommit` is what touches
 * `currentTime`. Seeking on every movement of a drag asks the decoder for a
 * frame at 60Hz, which on a long clip stutters the very scrub it is meant to
 * serve — and the `Slider` was built with exactly this split in mind.
 *
 * The bar stays a real slider rather than a hand-built track, and that keeps
 * one behaviour worth naming: `useKeyboardNav` ignores events targeting an
 * INPUT, so arrow keys scrub while the bar has focus and move between items
 * when it does not, with nothing coordinating the two.
 */
export function PlayerTransport({
  playback,
  buffered,
  size = "md",
  className = "",
}: PlayerTransportProps) {
  const { paused, time, duration, togglePaused, seekTo, seekBy } = playback;

  /** Non-null only while a drag is in flight. See the note above. */
  const [scrub, setScrub] = useState<number | null>(null);

  // A clip whose metadata has not landed has no duration to scale to. Keeping
  // the track at a nominal 1 and disabling it means the bar appears in its
  // final position rather than popping into existence.
  const seekable = duration > 0;
  const position = scrub ?? Math.min(time, duration);
  const glyph = size === "sm" ? SMALL_GLYPH : undefined;
  const elapsed = formatDuration(position) || "0:00";
  const total = formatDuration(duration) || "—:—";

  return (
    <div className={`flex w-full items-center gap-1.5 ${className}`}>
      <IconButton
        label={`Back ${SKIP_SECONDS} seconds`}
        size={size}
        onClick={() => seekBy(-SKIP_SECONDS)}
        className={CHROME_BUTTON}
      >
        <SeekBackIcon className={glyph} />
      </IconButton>

      <IconButton
        label={paused ? "Play (space)" : "Pause (space)"}
        size={size}
        onClick={togglePaused}
        className={CHROME_BUTTON}
      >
        {paused ? <PlayIcon className={glyph} /> : <PauseIcon className={glyph} />}
      </IconButton>

      <IconButton
        label={`Forward ${SKIP_SECONDS} seconds`}
        size={size}
        onClick={() => seekBy(SKIP_SECONDS)}
        className={CHROME_BUTTON}
      >
        <SeekForwardIcon className={glyph} />
      </IconButton>

      {/* Mono, and not by preference: the elapsed time reads once a second and
          a proportional face makes the whole row twitch sideways as the digits
          change width. `tabular-nums` cannot help a face that has no tabular
          set, and the fixed width is what stops the slider resizing under it. */}
      <Text
        variant="caption"
        family="mono"
        className="w-10 shrink-0 text-right text-chrome-ink"
      >
        {elapsed}
      </Text>

      <Slider
        label="Seek"
        min={0}
        max={seekable ? duration : 1}
        step={0.1}
        value={seekable ? position : 0}
        buffered={buffered}
        disabled={!seekable}
        onValueChange={setScrub}
        onValueCommit={(value) => {
          seekTo(value);
          setScrub(null);
        }}
        aria-valuetext={`${elapsed} of ${total}`}
        className="min-w-0 flex-1"
      />

      <Text variant="caption" family="mono" className="w-10 shrink-0 text-muted">
        {total}
      </Text>
    </div>
  );
}
