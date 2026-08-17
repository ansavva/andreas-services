import { useCallback, useEffect, useRef, useState } from "react";

type Tone = "row" | "tile" | "chrome";
type Phase = "idle" | "busy" | "done";

interface Props {
  /** What is being favourited, written into the label. */
  noun: string;
  /** True when it is already in its project's favourites — see the note below. */
  favorited?: boolean;
  /** Resolves once the copy has landed. Rejecting leaves the star hollow. */
  onFavorite: () => Promise<unknown>;
  /** Which surface this sits on. The three `CopyKeyButton` has, for the same reasons. */
  tone?: Tone;
  className?: string;
}

/**
 * Copy a file onto its project's favourites shelf.
 *
 * **A gold star here means the file really is in the folder**, not that this
 * button was pressed. Every listing carries `favorited`, worked out server-side
 * by matching name and size against the favourites folder, so the state survives
 * a reload and shows up on a file favourited from another device. That is the
 * reason this is a lit indicator at all rather than a fire-and-forget action —
 * an unlit star over a file you picked last week would be a lie you could only
 * catch by opening the folder.
 *
 * Where a favourite *goes* is never asked. The server derives the folder from
 * the key, so pressing this in a run under `projects/<project>/` puts a copy in
 * `projects/<project>/favorites/` and there is no argument here that could aim it
 * anywhere else. Files that cannot be favourited — anything under `characters/`,
 * and any non-media file — never render this button, because the API tells the
 * listing so (`favorites_prefix`).
 *
 * It is always a *sibling* of whatever opens the file, never a child: every
 * card, row and tile in this app is itself a `<button>`, and a button inside a
 * button is invalid HTML browsers resolve by dropping one of them.
 *
 * Pressing an already-favourited file is not offered — the server would skip it
 * anyway — and un-favouriting is a plain delete of the copy, from inside the
 * favourites folder where it is unambiguous which object is going.
 */
export function FavoriteButton({
  noun,
  favorited = false,
  onFavorite,
  tone = "row",
  className = "",
}: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  // Set on unmount so a resolving copy cannot setState afterwards — the reel
  // pane this sits on can be scrolled away mid-request.
  const gone = useRef(false);

  useEffect(() => {
    gone.current = false;
    return () => {
      gone.current = true;
    };
  }, []);

  const press = useCallback(() => {
    if (phase !== "idle") return;
    setPhase("busy");
    void onFavorite()
      .then(
        () => {
          if (!gone.current) setPhase("done");
        },
        () => {
          // The page surfaces the message; this only owns the star, which goes
          // back to hollow because nothing was copied.
          if (!gone.current) setPhase("idle");
        },
      );
  }, [onFavorite, phase]);

  const lit = favorited || phase === "done";
  const label = lit
    ? `${noun} is in favorites`
    : phase === "busy"
      ? `Adding ${noun} to favorites…`
      : `Add ${noun} to favorites`;

  return (
    <button
      type="button"
      onClick={press}
      disabled={lit || phase === "busy"}
      aria-label={label}
      aria-pressed={lit}
      title={label}
      className={`shrink-0 rounded-md transition-colors disabled:cursor-default
                  focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary
                  ${toneStyles[tone]} ${lit ? litStyles[tone] : ""} ${className}`}
    >
      {/* The outcome of a press whose only other signal is a colour change. */}
      <span className="sr-only" aria-live="polite">
        {phase === "idle" ? "" : label}
      </span>
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={`${tone === "tile" ? "size-4" : "size-5"} stroke-[1.5]
                    ${lit ? "fill-current stroke-current" : "fill-none stroke-current"}`}
      >
        <path d="M12 4l2.35 4.76 5.25.76-3.8 3.7.9 5.23L12 15.98l-4.7 2.47.9-5.23-3.8-3.7 5.25-.76Z" />
      </svg>
    </button>
  );
}

/** The three surfaces a file is favourited from. Matches `CopyKeyButton`. */
const toneStyles: Record<Tone, string> = {
  row: "p-2 text-muted hover:bg-surface-alt hover:text-ink",
  tile: "bg-black/55 p-1.5 text-white/85 hover:bg-black/80 hover:text-white",
  chrome: "p-2 text-white/80 hover:bg-white/15 hover:text-white",
};

/**
 * Lit beats tone, the way `CopyKeyButton`'s green tick does: a favourite reads
 * gold over a photograph as readily as it does on a row.
 */
const litStyles: Record<Tone, string> = {
  row: "text-warning hover:text-warning",
  tile: "text-warning hover:text-warning",
  chrome: "text-warning hover:text-warning",
};
