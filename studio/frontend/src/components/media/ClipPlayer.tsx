import { useCallback, useEffect, useRef, useState } from "react";

import {
  Container,
  Controls,
  FullscreenButton,
  MuteButton,
  PlayButton,
  SeekButton,
  Time,
  TimeSlider,
  bufferFeature,
  controlsFeature,
  createPlayer,
  errorFeature,
  fullscreenFeature,
  playbackFeature,
  selectFullscreen,
  timeFeature,
  volumeFeature,
} from "@videojs/react";
import { Video } from "@videojs/react/video";

import { IconButton, Text } from "@ansavva/design-system";

import { useNearViewport } from "../../hooks/useNearViewport";
import { useSignedSrc } from "../../hooks/useSignedSrc";
import {
  CloseIcon,
  FullscreenEnterIcon,
  FullscreenExitIcon,
  PauseIcon,
  PlayIcon,
  SeekBackIcon,
  SeekForwardIcon,
  SoundOffIcon,
  SoundOnIcon,
} from "../common/icons";
import {
  ASPECTS,
  CHROME_SCRIM,
  FITS,
  FULLSCREEN_BOTTOM,
  FULLSCREEN_TOP,
  Unavailable,
  type MediaPlayerControls,
  type MediaPlayerProps,
} from "./playerShell";

/**
 * A clip, played on Video.js v10.
 *
 * **This replaced ~2,000 lines of our own player** — `PlayerTransport`,
 * `useMediaPlayback`, `useChromeIdle` and the clip half of `useFullscreen` —
 * none of which anyone chose: the transport was rebuilt "on Replicate's
 * chrome" in #556 and everything after was an increment on it. The package
 * owns play, mute (and the iOS unmute-inside-the-gesture rule that hook
 * documented three bugs around), seek, buffered, idle-hide, and fullscreen.
 *
 * **Fullscreen is the reason it was worth doing.** Video.js fullscreens the
 * `Container` where the Fullscreen API exists, so our chrome is painted
 * inside it on a laptop; where it does not — an iPhone, on any browser, since
 * every one of them is WebKit — it hands the `<video>` to
 * `webkitSetPresentationMode("fullscreen")`, and the phone draws its own
 * player: Safari's bar gone, PiP, AirPlay, speed. Our old fallback was an
 * in-app box *under* Safari's bar, which was the worst of both.
 *
 * **The controls are still the design system's.** Every Video.js control
 * takes a `render` prop and renders at most one element, so each button here
 * is an `IconButton` handed the package's props — its handlers, ARIA and
 * state attributes — rather than a `<button>` restyled to look like one. The
 * package brings behaviour; the look stays ours.
 *
 * **What the package does not do is still here**: the poster (a full-bleed
 * press target the size of the frame), the signed `src` and its re-sign on
 * expiry, withholding `src` until the box is near the viewport, the file
 * chrome the caller passes as `actions`, and the controls handed up for the
 * page's own keys. Stills are `StillPlayer`; a video player does not do
 * pictures.
 */

/** How far back-5 / forward-5 move. Named because the labels say the number. */
const SKIP_SECONDS = 5;

/**
 * The icon set replaces its default class wholesale rather than merging — see
 * the note at the top of `icons.tsx` — so a smaller glyph is a whole string.
 */
const SMALL_GLYPH = "size-4 fill-none stroke-current stroke-[1.5]";

/**
 * One store shape for every clip player in the app. `createPlayer` is a
 * module-level call by design: it returns the typed `Player` and `usePlayer`
 * for this feature set, and a new pair per render would be a new context.
 *
 * **Not `videoFeatures`, deliberately.** The preset carries quality, audio
 * tracks, text tracks, playback rate, PiP and remote playback — none of which
 * a clip out of a model has or this chrome draws — and each is code in the
 * bundle and a listener on the element. The audio-track one also attaches to
 * `media.audioTracks`, which jsdom declares without making an `EventTarget`,
 * so the preset logs a `TypeError` under every test. This is the list the
 * controls below actually read.
 */
const { Player, usePlayer } = createPlayer({
  features: [
    playbackFeature,
    volumeFeature,
    timeFeature,
    bufferFeature,
    fullscreenFeature,
    controlsFeature,
    errorFeature,
  ],
  displayName: "ClipPlayer",
});

type ClipPlayerProps = Omit<MediaPlayerProps, "isVideo" | "zoomable" | "zoom" | "onZoomChange" | "drag">;

export function ClipPlayer(props: ClipPlayerProps) {
  return (
    <Player>
      <Clip {...props} />
    </Player>
  );
}

/**
 * Inside the `Player`, where the store is. The split from `ClipPlayer` is only
 * that: every hook below wants the context the wrapper provides.
 */
function Clip({
  nodeId,
  url,
  name = "",
  aspect = "video",
  fit = "contain",
  autoPlay = false,
  startMuted = true,
  className = "",
  onClose,
  onContainerChange,
  onControlsChange,
  onFullscreenChange,
  overlay,
  actions,
}: ClipPlayerProps) {
  const [playing, setPlaying] = useState(autoPlay);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const player = usePlayer();
  const fullscreen = usePlayer(selectFullscreen);
  const isFullscreen = fullscreen?.fullscreen ?? false;

  const { src, failed, onError } = useSignedSrc(nodeId, url);
  const near = useNearViewport(containerRef, true);

  // Held in a ref so a caller passing an inline arrow does not change the
  // identity of the ref callback below, which would detach and re-attach the
  // container on every render.
  const onContainerChangeRef = useRef(onContainerChange);
  useEffect(() => {
    onContainerChangeRef.current = onContainerChange;
  });

  /**
   * Reported straight out of the ref callback rather than through state, so
   * the caller sees exactly what React saw, when React saw it, in both
   * directions — including the `null` on unmount that a `setState` would drop.
   */
  const setContainerNode = useCallback((element: HTMLDivElement | null) => {
    containerRef.current = element;
    onContainerChangeRef.current?.(element);
  }, []);

  /**
   * The press that starts a clip, inside the gesture that made it.
   *
   * The `<video>` is mounted under the poster — `preload="metadata"` is how
   * the poster frame and the duration arrive — so `play()` here is a call on
   * a real element inside a real click, which is the only place a browser
   * grants sound. `startMuted` is the default because a first press is
   * usually a look rather than a listen; a caller that wants sound from the
   * first frame gets it cleared here, in the same gesture.
   */
  const startPlaying = useCallback(() => {
    if (!startMuted && player.muted) player.toggleMuted();
    setPlaying(true);
    void player.play();
  }, [player, startMuted]);

  /** Back to the poster: paused, rewound to the first frame, out of fullscreen. */
  const close = useCallback(() => {
    if (isFullscreen) void fullscreen?.exitFullscreen();
    player.pause();
    const video = videoRef.current;
    if (video) video.currentTime = 0;
    setPlaying(false);
    onClose?.();
  }, [fullscreen, isFullscreen, onClose, player]);

  // Reported on change only, through a ref, so an inline arrow from the
  // caller neither re-subscribes nor fires on every tick.
  const onFullscreenChangeRef = useRef(onFullscreenChange);
  useEffect(() => {
    onFullscreenChangeRef.current = onFullscreenChange;
  });
  useEffect(() => {
    onFullscreenChangeRef.current?.(isFullscreen);
  }, [isFullscreen]);

  /**
   * The controls a keyboard shortcut needs, handed up once.
   *
   * Everything they touch is read through `latest` rather than closed over, so
   * the object is created on mount and never again — a caller holding it in
   * state (which is how `ObjectPage` gets it to `useKeyboardNav`) would
   * otherwise re-render on every tick, and re-registering would loop.
   */
  const onControlsChangeRef = useRef(onControlsChange);
  const latest = useRef({ playing, startPlaying, player });
  useEffect(() => {
    onControlsChangeRef.current = onControlsChange;
    latest.current = { playing, startPlaying, player };
  });

  useEffect(() => {
    const controls: MediaPlayerControls = {
      togglePlay: () => {
        const now = latest.current;
        // From the poster, "play" is the press that starts playback at all.
        if (now.playing) now.player.togglePaused();
        else now.startPlaying();
      },
      pause: () => {
        const now = latest.current;
        if (now.playing && !now.player.paused) now.player.pause();
      },
      currentTime: () => videoRef.current?.currentTime ?? 0,
      toggleMuted: () => latest.current.player.toggleMuted(),
      toggleFullscreen: () => void latest.current.player.toggleFullscreen(),
      // No-ops on a clip: zoom is a still's.
      zoomIn: () => undefined,
      zoomOut: () => undefined,
      zoomReset: () => undefined,
    };
    onControlsChangeRef.current?.(controls);
    return () => onControlsChangeRef.current?.(null);
  }, []);

  /**
   * Fullscreen is for viewing. Play, pause and seek; sound on and off; and
   * out again — nothing about the file. The caller's `actions` and the
   * player's own Close (which ends playback, not the view) wait outside it.
   */
  const fileChrome = !isFullscreen;
  const shownActions = fileChrome ? actions : undefined;

  const glyph = SMALL_GLYPH;
  const media = `h-full w-full ${FITS[fit]}`;
  const box = [
    // `overflow-clip`, not `-hidden`: a scroll container the browser can
    // nudge to bring a focused button into view is not wanted here.
    "relative isolate block overflow-clip bg-overlay-scrim",
    // `:fullscreen` sizes the element itself; the ratio is for the page.
    isFullscreen ? "" : ASPECTS[aspect],
    // The cursor goes with the chrome. `:has()` rather than state, because the
    // cursor belongs on the box and the visibility to the controls surface.
    "[&:has([data-clip-controls]:not([data-visible]))]:cursor-none",
    className,
  ].join(" ");

  return (
    <Container
      ref={setContainerNode}
      className={box}
      // Which route fullscreen took, for anything reading the DOM — a test, a
      // script. The package decides: the container where the API exists, the
      // phone's own presentation where it does not.
      data-fullscreen={isFullscreen ? "native" : undefined}
    >
      {failed ? (
        <Unavailable />
      ) : (
        <Video
          ref={videoRef}
          // Withheld until the box is near the viewport, and unconditional once
          // playing — a press is not a moment to start waiting for an observer.
          src={near || playing ? src : undefined}
          onError={onError}
          // **Autoplay across a step, without a remount.** `ObjectPage` keeps
          // one player mounted while walking a feed, so a new `src` arrives on
          // an element that was playing; the native attribute plays each new
          // source as it loads. Off under the poster, so a poster never starts
          // itself.
          autoPlay={playing}
          loop
          muted={startMuted}
          playsInline
          preload={playing ? "auto" : "metadata"}
          className={media}
        />
      )}

      {/* The poster's press target is the whole box, which is the size a finger
          wants. The circle is what says it is pressable. */}
      {!playing && !failed && (
        // eslint-disable-next-line studio/no-hand-rolled-button -- a full-bleed hit target the size of the frame.
        <button
          type="button"
          onClick={startPlaying}
          aria-label={`Play ${name}`}
          className="absolute inset-0 z-10 flex cursor-pointer items-center justify-center
                     bg-overlay-scrim/20 transition-colors hover:bg-overlay-scrim/40
                     focus-visible:outline-2 focus-visible:outline-offset-[-2px]
                     focus-visible:outline-primary"
        >
          <span className="flex size-14 items-center justify-center rounded-pill bg-overlay-scrim/70 text-overlay-ink">
            <PlayIcon className="size-7 fill-none stroke-current stroke-[1.5]" />
          </span>
        </button>
      )}

      {/* The duration, where a poster would otherwise say nothing about length.
          `data-unavailable` until metadata lands, and hidden by it. */}
      {!playing && !failed && (
        <Time.Value
          type="duration"
          render={(props) => (
            <Text
              {...props}
              variant="caption"
              family="mono"
              className="pointer-events-none absolute bottom-1.5 right-1.5 z-10
                         bg-overlay-scrim/80 px-1.5 py-0.5 text-overlay-ink
                         data-[unavailable]:hidden"
            />
          )}
        />
      )}

      {!failed && (
        <Controls.Root>
          <Controls.Content
            data-clip-controls=""
            // `invisible`, not just `opacity-0`: visibility is what takes the
            // buttons out of the tab order and out from under a finger, so the
            // first tap on a hidden chrome reaches the picture and brings it
            // back rather than landing on whatever button was there.
            className={(state) =>
              `pointer-events-none absolute inset-0 z-20 transition-[opacity,visibility] duration-200 ${
                state.visible ? "" : "invisible opacity-0"
              }`
            }
          >
            {/*
              **No scrim across the picture — each control carries its own.**
              A pill behind each glyph keeps it legible over the two dozen
              pixels it occupies instead of over the whole width of the frame.
              The transport keeps its bottom gradient: it is a row of text and
              a scrub bar, not two glyphs, and it is only drawn while the clip
              plays.
            */}
            <div
              className={`absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-2 ${
                isFullscreen ? FULLSCREEN_TOP : ""
              }`}
            >
              <div className="pointer-events-auto flex min-w-0 items-center gap-1">{shownActions}</div>

              <div className="pointer-events-auto flex shrink-0 items-center gap-1">
                {/*
                  Sound is the leftmost control and Close the rightmost,
                  deliberately: a mis-tap on the button you reach for mid-clip
                  should not be the one that ends the clip.
                */}
                {playing && (
                  <MuteButton
                    label={(state) => (state.muted ? "Unmute (m)" : "Mute (m)")}
                    render={(props, state) => (
                      <IconButton
                        {...props}
                        label={state.muted ? "Unmute (m)" : "Mute (m)"}
                        size="sm"
                        intent="overlay"
                        className={CHROME_SCRIM}
                      >
                        {state.muted ? <SoundOffIcon /> : <SoundOnIcon />}
                      </IconButton>
                    )}
                  />
                )}

                {/*
                  Drawn wherever the package can answer it — which is every
                  browser this app runs in, since a phone answers with its
                  own presentation. The package hides it where nothing can.
                */}
                <FullscreenButton
                  label={(state) => (state.fullscreen ? "Exit fullscreen (f)" : "Fullscreen (f)")}
                  render={(props, state) => (
                    <IconButton
                      {...props}
                      label={state.fullscreen ? "Exit fullscreen (f)" : "Fullscreen (f)"}
                      size="sm"
                      intent="overlay"
                      className={CHROME_SCRIM}
                    >
                      {state.fullscreen ? <FullscreenExitIcon /> : <FullscreenEnterIcon />}
                    </IconButton>
                  )}
                />

                {fileChrome && (playing || onClose) && (
                  <IconButton
                    label={playing ? `Close ${name}` : "Close"}
                    size="sm"
                    onClick={close}
                    intent="overlay"
                    className={CHROME_SCRIM}
                  >
                    <CloseIcon />
                  </IconButton>
                )}
              </div>
            </div>

            {playing && (
              <div
                className={`absolute inset-x-0 bottom-0 flex flex-col gap-1
                            bg-gradient-to-t from-overlay-scrim/85 to-transparent px-3 pb-3 pt-12
                            ${isFullscreen ? FULLSCREEN_BOTTOM : ""}`}
              >
                <div className="pointer-events-auto mx-auto flex w-full max-w-2xl items-center gap-1.5">
                  <SeekButton
                    seconds={-SKIP_SECONDS}
                    label={`Back ${SKIP_SECONDS} seconds`}
                    render={(props) => (
                      <IconButton {...props} label={`Back ${SKIP_SECONDS} seconds`} size="sm" intent="overlay">
                        <SeekBackIcon className={glyph} />
                      </IconButton>
                    )}
                  />

                  <PlayButton
                    label={(state) => (state.paused ? "Play (space)" : "Pause (space)")}
                    render={(props, state) => (
                      <IconButton
                        {...props}
                        label={state.paused ? "Play (space)" : "Pause (space)"}
                        size="sm"
                        intent="overlay"
                      >
                        {state.paused ? <PlayIcon className={glyph} /> : <PauseIcon className={glyph} />}
                      </IconButton>
                    )}
                  />

                  <SeekButton
                    seconds={SKIP_SECONDS}
                    label={`Forward ${SKIP_SECONDS} seconds`}
                    render={(props) => (
                      <IconButton {...props} label={`Forward ${SKIP_SECONDS} seconds`} size="sm" intent="overlay">
                        <SeekForwardIcon className={glyph} />
                      </IconButton>
                    )}
                  />

                  {/* Mono, and not by preference: the elapsed time reads once a
                      second and a proportional face makes the whole row twitch
                      sideways as the digits change width. The fixed width is
                      what stops the slider resizing under it. */}
                  <Time.Value
                    type="current"
                    render={(props) => (
                      <Text
                        {...props}
                        variant="caption"
                        family="mono"
                        className="w-10 shrink-0 text-right text-overlay-ink"
                      />
                    )}
                  />

                  {/*
                    **The package's slider, in the app's roles.** Fill and
                    buffer are clip-paths off the custom properties the root
                    sets (`--media-slider-fill`, `--media-slider-buffer`), and
                    the thumb rides the fill. Seeks are throttled to 100ms
                    during a drag by the root itself.
                  */}
                  <TimeSlider.Root
                    label="Seek"
                    className="group/seek relative flex h-8 min-w-0 flex-1 cursor-pointer touch-none select-none items-center outline-none"
                  >
                    <TimeSlider.Track className="relative h-1 w-full overflow-hidden rounded-pill bg-overlay-ink/30 transition-[height] group-hover/seek:h-1.5 group-focus-visible/seek:h-1.5 group-data-[dragging]/seek:h-1.5">
                      <TimeSlider.Buffer className="absolute inset-0 bg-overlay-ink/40 [clip-path:inset(0_calc(100%-var(--media-slider-buffer))_0_0)]" />
                      <TimeSlider.Fill className="absolute inset-0 bg-overlay-ink [clip-path:inset(0_calc(100%-var(--media-slider-fill))_0_0)]" />
                    </TimeSlider.Track>
                    <TimeSlider.Thumb className="absolute top-1/2 left-[var(--media-slider-fill)] size-3 -translate-x-1/2 -translate-y-1/2 rounded-pill bg-overlay-ink opacity-0 transition-opacity group-hover/seek:opacity-100 group-focus-visible/seek:opacity-100 group-data-[dragging]/seek:opacity-100 group-focus-visible/seek:outline-2 group-focus-visible/seek:outline-offset-2 group-focus-visible/seek:outline-primary" />
                  </TimeSlider.Root>

                  <Time.Value
                    type="duration"
                    render={(props) => (
                      <Text
                        {...props}
                        variant="caption"
                        family="mono"
                        className="w-10 shrink-0 text-muted"
                      />
                    )}
                  />
                </div>
              </div>
            )}
          </Controls.Content>
        </Controls.Root>
      )}

      {overlay}
    </Container>
  );
}
