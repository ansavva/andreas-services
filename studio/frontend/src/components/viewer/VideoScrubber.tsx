import { formatDuration } from "../../utils/format";
import type { ReelPlayback } from "../../hooks/useReelPlayback";

interface Props {
  playback: ReelPlayback;
}

const SKIP_SECONDS = 5;

/**
 * Move through a clip in time, from inside the reel.
 *
 * The reel deliberately gives its `<video>` elements no native `controls`: the
 * pane is a scroll-snap target, and the browser's own control bar swallows the
 * drags that scroll it — you end up scrubbing when you meant to move to the next
 * clip. So the transport is ours, sits above the pane, and leaves the middle of
 * the frame free for the scroll gesture.
 *
 * The seek itself is a native `<input type="range">` rather than a hand-built
 * bar, and that is worth stating: it is keyboard-operable and announced without
 * any work, and `useKeyboardNav` already ignores events targeting an INPUT — so
 * arrow keys scrub while the bar has focus and move between clips when it does
 * not, with no coordination between the two.
 */
export function VideoScrubber({ playback }: Props) {
  const { paused, time, duration, togglePaused, seekTo, seekBy } = playback;
  const seekable = duration > 0;

  return (
    <div
      className="pointer-events-auto flex items-center gap-2 rounded-full bg-black/55 px-2 py-1.5
                 backdrop-blur-sm"
    >
      <TransportButton label={`Back ${SKIP_SECONDS} seconds`} onClick={() => seekBy(-SKIP_SECONDS)}>
        <path d="M11 7 6 12l5 5" />
        <path d="M18 7l-5 5 5 5" />
      </TransportButton>

      <TransportButton label={paused ? "Play (space)" : "Pause (space)"} onClick={togglePaused}>
        {paused ? <path d="M8 5v14l11-7Z" /> : <path d="M9 5v14M15 5v14" />}
      </TransportButton>

      <TransportButton
        label={`Forward ${SKIP_SECONDS} seconds`}
        onClick={() => seekBy(SKIP_SECONDS)}
      >
        <path d="M13 7l5 5-5 5" />
        <path d="M6 7l5 5-5 5" />
      </TransportButton>

      <span className="w-10 shrink-0 text-right font-body text-[11px] tabular-nums text-white/80">
        {formatDuration(time) || "0:00"}
      </span>

      <input
        type="range"
        min={0}
        // A clip whose metadata has not landed yet has no duration to scale to.
        // Keeping the track at a nominal 1 and disabling it means the bar
        // appears in its final position rather than popping into existence.
        max={seekable ? duration : 1}
        step={0.1}
        value={seekable ? Math.min(time, duration) : 0}
        disabled={!seekable}
        onChange={(event) => seekTo(Number(event.target.value))}
        aria-label="Seek"
        aria-valuetext={`${formatDuration(time) || "0:00"} of ${formatDuration(duration) || "0:00"}`}
        // Left as a *native* range: `appearance-none` deletes WebKit's track and
        // thumb outright and hands back the job of drawing both through
        // `::-webkit-slider-thumb`, which Tailwind cannot express and which is
        // three vendor-prefixed rules to maintain for no gain. `accent-primary`
        // paints it in the app's own accent, and `color-scheme: dark` on the
        // body (see app.css) keeps the track dark under it.
        className="w-32 min-w-0 flex-1 cursor-pointer accent-primary disabled:cursor-default sm:w-48"
      />

      <span className="w-10 shrink-0 font-body text-[11px] tabular-nums text-white/60">
        {formatDuration(duration) || "—:—"}
      </span>
    </div>
  );
}

function TransportButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="shrink-0 rounded-full p-1.5 text-white/85 transition-colors hover:bg-white/15
                 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2
                 focus-visible:outline-primary"
    >
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="size-5 fill-none stroke-current stroke-[1.5]"
      >
        {children}
      </svg>
    </button>
  );
}
