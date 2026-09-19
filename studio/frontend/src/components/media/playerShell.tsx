import type { ReactNode } from "react";

import { Text } from "@ansavva/design-system";

import type { AttachRef } from "../../context/CreateBarContext";
import type { ZoomState } from "./useZoom";

/**
 * What `StillPlayer` and `ClipPlayer` share: the box, the chrome's constants,
 * the props, and the controls handed up to a page. Neither imports the other;
 * `MediaPlayer` is the one that picks.
 */

/**
 * Every class here is a whole literal, for the reason `MediaThumb` spells out:
 * Tailwind finds classes by scanning source text, so anything assembled from a
 * template literal compiles to no CSS at all.
 */
export const ASPECTS = {
  square: "aspect-square",
  portrait: "aspect-[3/4]",
  video: "aspect-video",
  /** No ratio of its own — the caller sized the box. */
  auto: "",
} as const;

export const FITS = { cover: "object-cover", contain: "object-contain" } as const;

/**
 * Padding that clears a notch, a home indicator and a landscape bezel — and
 * ONLY while the player owns the screen.
 *
 * Inline in a page column these insets are wrong rather than merely unused: a
 * landscape iPhone reports `safe-area-inset-left: 44px`, which would put 44px
 * of padding inside a 300px-wide player sitting nowhere near the bezel. The
 * page's own layout is what keeps an inline player clear of an edge; these two
 * strings are for the fullscreen element, which has no layout above it.
 */
export const FULLSCREEN_TOP = "pt-[max(0.5rem,env(safe-area-inset-top))]";
export const FULLSCREEN_BOTTOM =
  "pb-[max(0.75rem,env(safe-area-inset-bottom))] pl-[max(0.75rem,env(safe-area-inset-left))] pr-[max(0.75rem,env(safe-area-inset-right))]";

/**
 * The pill behind one glyph over media — what replaced the gradient across the
 * top of every picture. Same treatment as a tile's `⋮` and its heart.
 */
export const CHROME_SCRIM = "bg-overlay-scrim/60";

/**
 * The things a keyboard shortcut needs and the DOM cannot reach.
 *
 * Play, mute, fullscreen and zoom all live behind state a player owns, so a
 * page that binds Space, `m`, `f` and `+`/`-`/`0` cannot press them by finding
 * a button and clicking it: the labels would become an API. This is that API,
 * stated once, and each player answers the verbs it has — zoom is a no-op on a
 * clip, play on a still.
 *
 * `togglePlay` is deliberately one verb rather than two. From the poster it
 * *starts* playback; once playing it pauses and resumes. "Space plays" means
 * the same thing to a person in both states.
 */
export interface MediaPlayerControls {
  togglePlay: () => void;
  /** Stop where it is. A no-op on a still and on a poster that never played. */
  pause: () => void;
  /**
   * Where the clip is, in seconds — the frame on screen, read off the element
   * at the moment of the call. `0` on a still, and on a poster: a clip that
   * never played is on its first frame.
   */
  currentTime: () => number;
  toggleMuted: () => void;
  toggleFullscreen: () => void;
  /** `+`, `-` and `0`. No-ops on a video, and on a player that is not `zoomable`. */
  zoomIn: () => void;
  zoomOut: () => void;
  zoomReset: () => void;
}

export interface MediaPlayerProps {
  /**
   * The node id, which is what a re-sign addresses.
   *
   * Not the key: `/api/asset` signs by node, and a name path would leave every
   * expired tile broken for anything uploaded through the app.
   */
  nodeId: string;
  /**
   * Presigned inline GET. Re-signed through `useSignedSrc` when it expires,
   * and **absent when the node it names is gone** — see `RunAsset`, and
   * `MediaThumb`'s `url`, which carries the reasoning. `useSignedSrc` reports
   * that as `failed`, which is the `Unavailable` panel.
   */
  url?: string | null;
  /** What the file is called. Names the play and close controls. */
  name?: string;
  isVideo?: boolean;
  /** The box's ratio. `auto` where the caller sized the box itself. */
  aspect?: keyof typeof ASPECTS;
  /**
   * `contain` by default, where `MediaThumb` defaults to `cover`.
   *
   * A player is where a frame is judged, and the bucket mixes 1:1, 9:16 and
   * 16:9 output from the same run family — cropping to fill would hide exactly
   * the thing being looked at.
   */
  fit?: "cover" | "contain";
  /** Skip the poster and start playback on first render. A clip's only. */
  autoPlay?: boolean;
  /**
   * Whether playback starts silent. Defaults to true — a first press is
   * usually a look rather than a listen. A clip's only.
   */
  startMuted?: boolean;
  /** Extra classes for the box: borders and rounding, which vary by surface. */
  className?: string;
  /**
   * Fires when the viewer closes playback back to the poster, after the player
   * has already done so. Not a request to unmount — the player stays.
   */
  onClose?: () => void;
  /**
   * The player's own container element, as it mounts and unmounts.
   *
   * **This is the seam that lets a dialog open inside fullscreen.** The
   * Fullscreen API paints only the fullscreen element and its descendants, so
   * anything portalled to `<body>` is invisible while one is up — which is why
   * six files in this app hand-roll an inline dialog. Pass this element to
   * `Dialog.Root` / `Drawer.Root` / `AlertDialog.Root`'s `container` prop and
   * the portal lands inside the player instead.
   */
  onContainerChange?: (element: HTMLElement | null) => void;
  /**
   * The player's controls, as they become available and as they go.
   *
   * For a caller that binds keys — `ObjectPage` binds Space, `m` and `f`. Held
   * in state the same way `onContainerChange`'s element is; the object handed
   * over keeps one identity for the life of the player, so storing it does not
   * loop.
   */
  onControlsChange?: (controls: MediaPlayerControls | null) => void;
  /**
   * Whether the player owns the screen — the browser's fullscreen, the phone's
   * own presentation of a clip, or the app's own expansion of a still where
   * the browser refuses.
   *
   * A caller that listens to `fullscreenchange` itself hears only the first:
   * `ObjectPage` drew its edit and delete controls "while fullscreen" and
   * never on a phone, where the rail that otherwise carries them is exactly
   * what fullscreen covers.
   */
  onFullscreenChange?: (fullscreen: boolean) => void;
  /**
   * Chrome drawn inside the player, above the media and below the transport.
   *
   * Rendered as a descendant of the container, so it is painted in fullscreen
   * too. The caller positions it; the player only guarantees the stacking
   * context.
   */
  overlay?: ReactNode;
  /**
   * Extra buttons at the left of the top chrome row — a frame menu, edit,
   * delete. **Not drawn in fullscreen**, by any route: that view is for
   * looking, and its chrome is the transport, sound, and the way back out.
   */
  actions?: ReactNode;
  /**
   * Whether a still can be zoomed and panned — see `useZoom`.
   *
   * Off by default: a tile in a scene's cut is not a place to pinch,
   * and a wheel over it must scroll the page. The two viewers turn it on.
   */
  zoomable?: boolean;
  /**
   * The zoom, controlled — for two players zooming together on the compare
   * stage. Either one's gesture arrives at `onZoomChange`; the stage holds one
   * state and hands it to both.
   */
  zoom?: ZoomState;
  onZoomChange?: (next: ZoomState) => void;
  /**
   * What a drag of the picture carries to the create sheet — `MediaThumb`'s
   * `drag`, with the same default: a still drags its node as an object, a
   * clip drags nothing, and a viewer showing a run's output passes
   * `refOfOutput` so the provenance goes with it. Off while zoomed, where a
   * drag is the pan.
   */
  drag?: boolean | AttachRef;
}

/** What a box says when its node is gone from the bucket. */
export function Unavailable() {
  return (
    <div className="flex h-full w-full items-center justify-center p-6 text-center">
      <Text variant="caption" tone="muted">
        This file could not be loaded. It may have been removed from the bucket.
      </Text>
    </div>
  );
}
