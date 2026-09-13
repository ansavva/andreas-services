import { useCallback, useEffect, useRef, useState } from "react";

import { useToast } from "@ansavva/design-system";

import { getAsset, getProjectInputs, grabFrame } from "../apis/studio";
import { useCreateBar, useCreateBarState, type AttachRef, type AttachRole } from "../context/CreateBarContext";
import { assetLabel } from "../utils/format";

let sequence = 0;

/** `0:04.2` — the moment, the way the transport writes it, to a tenth. */
export function formatMoment(seconds: number): string {
  const whole = Math.floor(seconds);
  const minutes = Math.floor(whole / 60);
  const rest = seconds - minutes * 60;
  return `${minutes}:${rest < 10 ? "0" : ""}${rest.toFixed(1)}`;
}

/**
 * The still's name: the clip's stem, marked with the moment it was taken
 * at — `dance-first.png` for the opening frame, `dance-at-0m04.2s.png` for
 * any other, so two frames of one clip sort together and read apart.
 */
export function frameName(clip: string | undefined, at: number): string {
  const stem = (clip ?? "clip").replace(/\.[^.]+$/, "");
  if (at <= 0) return `${stem}-first.png`;
  const minutes = Math.floor(at / 60);
  const rest = at - minutes * 60;
  return `${stem}-at-${minutes}m${rest < 10 ? "0" : ""}${rest.toFixed(1)}s.png`;
}

/**
 * One frame of a clip, into the create bar as a still.
 *
 * **Why a motion-transfer run wants this.** `kling-v3-motion-control` copies
 * the movement of a source video onto one still, and it holds together when
 * the still's pose and framing already match the frame the transfer starts
 * from — otherwise the first frames are the model dragging the picture into
 * place. So the still is made *from* that frame: take it, hand it to an
 * image model as a reference with the character, render the character into
 * it, and that render is the motion run's start frame. This is the first
 * step. `at: 0` is the opening frame, which a whole clip starts from; any
 * other moment is the frame a person has scrubbed to and is looking at, for
 * a transfer that starts mid-clip or a still that is simply the good one.
 *
 * **The worker does the work.** The app has no ffmpeg; `POST /api/renders`
 * with `kind: frame` asks the render worker for the still and the hook polls
 * the row until it lands. The frame goes into the project's **input pool** —
 * the same folder `frames at --add-input` writes to, never a character's
 * `reference/` (hard rule 2b: a frame of a clip is not identity). Which
 * project is the bar's own target; with none chosen there is nowhere to put
 * the frame, and the toast says so rather than guessing.
 *
 * **On the bar before the worker is asked.** `attach` is called at once with
 * a `pending` placeholder drawn over the clip's own poster — the seconds the
 * grab takes are otherwise seconds in which pressing the line did nothing
 * anyone can see — and `replace` swaps it for the frame when it lands, or
 * `drop` takes it off when it does not. No toast on success: the tile
 * turning into the picture is the whole of the news. The attach is the
 * bar's own, so a frame attached as a reference accumulates and as a frame
 * replaces, exactly as any other still.
 */
export function useFrameGrab() {
  const bar = useCreateBar();
  const { target } = useCreateBarState();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);

  // Set on unmount so a landing frame cannot write state into a page that is
  // gone — the same guard `useUploads` keeps. The attach itself still runs:
  // the bar outlives the page, and the frame is in the pool either way.
  const gone = useRef(false);
  useEffect(() => {
    gone.current = false;
    return () => {
      gone.current = true;
    };
  }, []);

  const take = useCallback(
    async (clip: AttachRef, role: AttachRole, at = 0) => {
      if (!target) {
        toast.add({
          intent: "danger",
          title: "Choose a project first",
          description: "The frame goes into a project's input pool, and the bar has none yet.",
        });
        return;
      }
      // To a tenth of a second: what the transport shows, and what the name
      // carries. ffmpeg seeks to the nearest frame from there.
      const moment = Math.max(0, Math.round(at * 10) / 10);
      const name = frameName(clip.name, moment);
      const which = moment > 0 ? `the frame at ${formatMoment(moment)}` : "the first frame";
      const placeholder = `pending-${++sequence}-${clip.node}`;
      bar.attach(
        {
          node: placeholder,
          url: clip.url,
          name,
          kind: "object",
          pending: `Taking ${which} of ${assetLabel(clip.name)}…`,
        },
        role,
      );
      if (!gone.current) setBusy(clip.node);
      try {
        const { folder } = await getProjectInputs(target);
        const frame = await grabFrame({ node: clip.node, at: moment, dest: folder, name });
        const asset = await getAsset(frame.node);
        bar.replace(placeholder, { node: frame.node, url: asset.url, name: frame.name, kind: "object" });
      } catch (err) {
        bar.drop(placeholder);
        toast.add({
          intent: "danger",
          title: `Could not take ${which} of ${assetLabel(clip.name)}`,
          description: (err as Error).message,
        });
      } finally {
        if (!gone.current) setBusy(null);
      }
    },
    [bar, target, toast],
  );

  return { take, busy };
}
