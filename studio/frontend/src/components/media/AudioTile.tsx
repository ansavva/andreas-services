import { useCallback, useEffect, useRef, useState, type DragEvent, type MouseEvent } from "react";

import { IconButton } from "@ansavva/design-system";

import type { AttachRef } from "../../context/CreateBarContext";
import { objectRef, startNodeDrag } from "../create/dragRef";
import { useSignedSrc } from "../../hooks/useSignedSrc";
import { formatDuration } from "../../utils/format";
import { PauseIcon, PlayIcon, SoundOnIcon } from "../common/icons";

/**
 * The one element allowed to be making a sound.
 *
 * Module-level rather than context, for the same reason `MediaThumb`'s autoplay
 * budget is: it is a property of the page, not of any tree, and a tile in the
 * create sheet has to stop a tile in the picker behind it.
 */
let current: HTMLAudioElement | null = null;

interface Props {
  /** The node id — what a re-sign addresses. Same contract as `MediaThumb`. */
  nodeId: string;
  /** The presigned URL, or nothing: a record may point at a node that is gone. */
  url: string | null | undefined;
  name?: string;
  /** Extra classes for the box. The caller sizes it; this fills what it is given. */
  className?: string;
  /** Selected tiles fade so the ring around them reads — `MediaThumb`'s word. */
  dimmed?: boolean;
  /** What a drag of this file carries to the create sheet — see `dragRef`. */
  drag?: boolean | AttachRef;
  title?: string;
  /**
   * Whether this tile carries its own play control.
   *
   * **Off wherever the tile is already inside a control.** A button inside a
   * button is invalid HTML and the browser resolves it by dropping one of
   * them — so on the create sheet's strip, where the tile IS the button that
   * opens the preview drawer, the glyph stands alone and the drawer is where
   * it plays. The picker keeps it on by making the attach control a sibling
   * rather than a parent.
   */
  playable?: boolean;
}

/**
 * One audio file, as a tile you can hear.
 *
 * **Audio is the first kind in this library with nothing to look at**, which is
 * the whole reason it is not a branch inside `MediaThumb`. Every line of that
 * component is about a picture — the poster under a clip, the lazy `<img>`, the
 * shimmer until it decodes, the viewport budget that caps how many decoders run
 * at once — and none of it has an answer for a file whose entire content is a
 * waveform nobody has drawn. A fourth branch through it would have been a tile
 * that is `<img>`-shaped everywhere except in the one place it renders.
 *
 * So: a glyph, the name, and a play button. That is the tile.
 *
 * **It plays in place and never on hover.** A picture previews on hover because
 * looking costs nothing; sound does not work that way — a grid that started
 * talking as the pointer crossed it would be the worst control in the app. A
 * press starts it, a press stops it, and moving away leaves it playing, which
 * is what a person listening to a voice sample while reading the rest of the
 * page actually wants.
 *
 * **One at a time, across the whole page.** Two voice samples playing together
 * is noise rather than a comparison, so starting one stops the other — the same
 * discipline `MediaThumb`'s autoplay budget keeps for decoders, for a reason a
 * person can hear rather than measure.
 */
export function AudioTile({
  nodeId,
  url,
  name = "",
  className = "",
  dimmed = false,
  drag = true,
  title,
  playable = true,
}: Props) {
  const { src, failed, onError } = useSignedSrc(nodeId, url);
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState<number | null>(null);

  // A tile that goes away stops talking. Closing the picker over a playing
  // sample is the ordinary case, and a detached element keeps playing.
  useEffect(() => {
    const element = audio.current;
    return () => {
      element?.pause();
      if (element === current) current = null;
    };
  }, []);

  const toggle = useCallback(() => {
    const element = audio.current;
    if (!element || !src) return;
    if (element.paused) {
      if (current && current !== element) current.pause();
      current = element;
      // A rejected `play()` is ordinary — a tile unmounted mid-promise, an
      // autoplay policy on a page nobody has touched yet — and the `pause`
      // event puts the button back either way.
      void element.play().catch(() => undefined);
    } else {
      element.pause();
    }
  }, [src]);

  const draggable = drag !== false && !failed;
  const onDragStart = (event: DragEvent) =>
    startNodeDrag(event, drag === true ? objectRef(nodeId, url, name) : (drag as AttachRef));

  return (
    <span
      title={title}
      draggable={draggable || undefined}
      onDragStart={draggable ? onDragStart : undefined}
      className={`relative flex h-full w-full flex-col items-center justify-center gap-2
                  bg-surface-alt px-3 py-4 ${dimmed ? "opacity-75" : ""} ${className}`}
      data-audio-tile=""
    >
      {failed ? (
        <span className="text-center text-xs text-muted">Unavailable</span>
      ) : !playable ? (
        <SoundOnIcon className="size-6 fill-none stroke-current stroke-[1.5] text-muted" />
      ) : (
        <>
          <audio
            ref={audio}
            src={src}
            preload="metadata"
            onError={onError}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onEnded={() => setPlaying(false)}
            onLoadedMetadata={(event) => {
              const seconds = event.currentTarget.duration;
              // A stream with no known length reports `Infinity`, and a
              // chip reading `Infinity:NaN` is worse than no chip.
              setDuration(Number.isFinite(seconds) ? seconds : null);
            }}
          />
          <IconButton
            intent="secondary"
            size="md"
            label={playing ? `Pause ${name}` : `Play ${name}`}
            onClick={(event: MouseEvent) => {
              // The tile sits inside the picker's own press target, which
              // would otherwise attach the file the moment you listened to it.
              event.preventDefault();
              event.stopPropagation();
              toggle();
            }}
            className="rounded-pill"
          >
            {/* The two are drawn differently on purpose: `PlayIcon` is one
                filled triangle, `PauseIcon` is two strokes. Giving the second
                `stroke-none` — as the first wants — draws nothing at all,
                which is a play button that turns blank when pressed. */}
            {playing ? (
              <PauseIcon className="size-4 fill-none stroke-current stroke-2" />
            ) : (
              <PlayIcon className="size-4 fill-current stroke-none" />
            )}
          </IconButton>
          <SoundOnIcon className="size-4 fill-none stroke-current stroke-[1.5] text-muted" />
          {duration !== null && (
            <span className="pointer-events-none absolute bottom-1.5 right-1.5 bg-overlay-scrim/80
                             px-1.5 py-0.5 font-mono text-[11px] tabular-nums text-overlay-ink">
              {formatDuration(duration)}
            </span>
          )}
        </>
      )}
    </span>
  );
}
