import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Playback for the reel: which video is live, whether it has sound, and where
 * it is in time.
 *
 * ---------------------------------------------------------------------------
 * WHY UNMUTING USED TO FAIL
 * ---------------------------------------------------------------------------
 *
 * The reel autoplays its snapped pane muted, which is the only thing browsers
 * allow without a gesture. Turning sound on afterwards is the hard part, and the
 * previous implementation lost it in three separate ways:
 *
 * 1. **The gesture was spent before the work happened.** The mute button called
 *    `setMuted(v => !v)` and an effect further down set `video.muted` when it
 *    ran. A passive effect is not the click — it is a later task. Safari (iOS
 *    especially) grants sound only inside the gesture's own turn of the event
 *    loop, so by the time the effect touched the element the permission was
 *    gone, and the browser either kept it muted or paused it outright. That is
 *    the bug you feel as "the unmute button does nothing".
 *
 * 2. **The refusal was swallowed.** `video.play().catch(() => {})` discarded
 *    exactly the `NotAllowedError` that says sound was denied, so a reel that
 *    had quietly *stopped* looked identical to one playing silently.
 *
 * 3. **Nothing checked `volume`.** A muted element with `volume === 0` is still
 *    silent after `muted = false`, and volume survives across `src` changes on
 *    a reused element.
 *
 * So the toggle here is synchronous and imperative: the click handler sets
 * `muted` on the element itself, in the gesture, and React state follows to
 * describe what happened rather than to cause it. If the browser refuses anyway,
 * that is caught, playback falls back to muted rather than stopping, and
 * `blocked` is raised so the UI can say so instead of leaving a dead button.
 *
 * The preference is remembered across panes: scroll to the next clip and it
 * arrives with sound, because by then the document has the sticky activation
 * that first press established.
 */

export interface ReelPlayback {
  muted: boolean;
  /** True when the browser refused sound. Cleared by the next successful press. */
  blocked: boolean;
  paused: boolean;
  /** Seconds. `duration` is 0 until metadata lands. */
  time: number;
  duration: number;
  register: (key: string) => (element: HTMLVideoElement | null) => void;
  toggleMuted: () => void;
  togglePaused: () => void;
  seekTo: (seconds: number) => void;
  seekBy: (delta: number) => void;
}

export function useReelPlayback(currentKey: string | undefined): ReelPlayback {
  const videos = useRef(new Map<string, HTMLVideoElement>());
  // Read inside callbacks that must not be re-created per frame — a ref-backed
  // mirror keeps `register` and the seek helpers stable while `time` ticks.
  const currentKeyRef = useRef(currentKey);
  const mutedRef = useRef(true);

  const [muted, setMuted] = useState(true);
  const [blocked, setBlocked] = useState(false);
  const [paused, setPaused] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);

  currentKeyRef.current = currentKey;

  const currentVideo = useCallback(
    () => (currentKeyRef.current ? videos.current.get(currentKeyRef.current) : undefined),
    [],
  );

  /**
   * Ref callbacks, memoised per id.
   *
   * **The caller must pass something unique per pane.** This map is a pane's
   * identity for playback, so two panes sharing one string means one of them
   * silently loses its element. `ReelView` passes the node id for that reason;
   * it used to pass the file name, which collides constantly in an entity feed.
   *
   * An arrow function built inline in the render loop is a new identity every
   * render, which makes React detach and re-attach every mounted pane's ref on
   * every tick of the scrub bar. Caching them keeps the map stable.
   */
  const registrars = useRef(new Map<string, (element: HTMLVideoElement | null) => void>());
  const register = useCallback((key: string) => {
    const existing = registrars.current.get(key);
    if (existing) return existing;

    const callback = (element: HTMLVideoElement | null) => {
      if (element) videos.current.set(key, element);
      else videos.current.delete(key);
    };
    registrars.current.set(key, callback);
    return callback;
  }, []);

  /** Apply the current sound preference to one element and start it playing. */
  const play = useCallback((video: HTMLVideoElement, wantMuted: boolean) => {
    video.muted = wantMuted;
    // A muted element can still be sitting at volume 0 from a previous session's
    // controls; unmuting it alone would be silent.
    if (!wantMuted && video.volume === 0) video.volume = 1;

    // Never rejects. Two failures arrive here and they need opposite treatment:
    // `NotAllowedError` while unmuted is the autoplay policy refusing sound and
    // is worth reporting, while `AbortError` — a `play()` interrupted by the
    // next `pause()` — is the ordinary consequence of scrolling quickly and
    // means nothing at all. Letting either escape as an unhandled rejection
    // would put noise in the console on every flick of the reel.
    return video.play().catch((error: unknown) => {
      const refused = error instanceof DOMException && error.name === "NotAllowedError";
      if (!refused || wantMuted) return;

      // Sound was denied. Keep the reel playing silently — a paused reel is a
      // worse outcome than a quiet one — and tell the UI, so the button can say
      // why instead of looking broken.
      video.muted = true;
      mutedRef.current = true;
      setMuted(true);
      setBlocked(true);
      return video.play().catch(() => undefined);
    });
  }, []);

  const toggleMuted = useCallback(() => {
    const next = !mutedRef.current;
    // Set on the element first and synchronously: this runs inside the click,
    // which is the only moment the browser will grant sound. React state below
    // records the outcome; it does not cause it.
    mutedRef.current = next;
    setMuted(next);
    setBlocked(false);

    const video = currentVideo();
    if (video) void play(video, next);
  }, [currentVideo, play]);

  const togglePaused = useCallback(() => {
    const video = currentVideo();
    if (!video) return;
    if (video.paused) void play(video, mutedRef.current);
    else video.pause();
  }, [currentVideo, play]);

  const seekTo = useCallback(
    (seconds: number) => {
      const video = currentVideo();
      if (!video || !Number.isFinite(video.duration)) return;
      video.currentTime = Math.min(Math.max(seconds, 0), video.duration);
      setTime(video.currentTime);
    },
    [currentVideo],
  );

  const seekBy = useCallback(
    (delta: number) => {
      const video = currentVideo();
      if (!video) return;
      seekTo(video.currentTime + delta);
    },
    [currentVideo, seekTo],
  );

  /**
   * Exactly one video plays: the current one.
   *
   * Everything else is paused and rewound, so scrolling back to a clip restarts
   * it instead of resuming halfway through — and, with sound on, so no offscreen
   * pane is audible.
   */
  useEffect(() => {
    setTime(0);
    setDuration(0);

    for (const [key, video] of videos.current) {
      if (key === currentKey) continue;
      video.pause();
      video.muted = true;
      video.currentTime = 0;
    }

    const video = currentKey ? videos.current.get(currentKey) : undefined;
    if (!video) {
      setPaused(false);
      return;
    }

    setDuration(Number.isFinite(video.duration) ? video.duration : 0);
    void play(video, mutedRef.current);
  }, [currentKey, play]);

  /**
   * Track the current element rather than polling.
   *
   * `timeupdate` fires a few times a second, which is what the scrub bar wants;
   * `play`/`pause` are listened to instead of being inferred from our own calls
   * because the element can also be paused by the OS, by a headphone
   * disconnect, or by the browser's own autoplay enforcement.
   */
  useEffect(() => {
    const video = currentKey ? videos.current.get(currentKey) : undefined;
    if (!video) return;

    const onTime = () => setTime(video.currentTime);
    const onMeta = () => setDuration(Number.isFinite(video.duration) ? video.duration : 0);
    const onPlay = () => setPaused(false);
    const onPause = () => setPaused(true);
    // The element is the authority on whether it is muted: the browser mutes it
    // out from under us when it enforces its autoplay policy.
    const onVolume = () => {
      mutedRef.current = video.muted;
      setMuted(video.muted);
    };

    video.addEventListener("timeupdate", onTime);
    video.addEventListener("loadedmetadata", onMeta);
    video.addEventListener("durationchange", onMeta);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    video.addEventListener("volumechange", onVolume);

    onMeta();
    setPaused(video.paused);

    return () => {
      video.removeEventListener("timeupdate", onTime);
      video.removeEventListener("loadedmetadata", onMeta);
      video.removeEventListener("durationchange", onMeta);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("volumechange", onVolume);
    };
  }, [currentKey]);

  return {
    muted,
    blocked,
    paused,
    time,
    duration,
    register,
    toggleMuted,
    togglePaused,
    seekTo,
    seekBy,
  };
}
