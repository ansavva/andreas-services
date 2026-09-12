import { useCallback, useEffect, useRef, useState } from "react";

import { useToast } from "@ansavva/design-system";

import { getAsset, getProjectInputs, grabFrame } from "../apis/studio";
import { useCreateBar, useCreateBarState, type AttachRef, type AttachRole } from "../context/CreateBarContext";
import { assetLabel } from "../utils/format";
import { ROLE_WORDS } from "../components/create/roles";

/** The still's name: the clip's stem, marked as its first frame. */
export function firstFrameName(clip: string | undefined): string {
  const stem = (clip ?? "clip").replace(/\.[^.]+$/, "");
  return `${stem}-first.png`;
}

/**
 * The first frame of a clip, into the create bar as a still.
 *
 * **Why a motion-transfer run wants this.** `kling-v3-motion-control` copies
 * the movement of a reference clip onto one still, and it holds together when
 * the still's pose and framing already match the clip's opening frame —
 * otherwise the first frames are the model dragging the picture into place.
 * So the still is made *from* that frame: take it, hand it to an image model
 * as a reference with the character, render the character into it, and that
 * render is the motion run's start frame. This is the first step, and until
 * now it was `studio frames at <run> --time 0 --add-input` and a walk back
 * through the picker.
 *
 * **The worker does the work.** The app has no ffmpeg; `POST /api/renders`
 * with `kind: frame, at: 0` asks the render worker for the still and the hook
 * polls the row until it lands. The frame goes into the project's **input
 * pool** — the same folder `frames at --add-input` writes to, never a
 * character's `reference/` (hard rule 2b: a frame of a clip is not identity).
 * Which project is the bar's own target; with none chosen there is nowhere to
 * put the frame, and the toast says so rather than guessing.
 *
 * `attach` is the bar's: the same call a `Use as` line makes for a picture,
 * so a first frame attached as a reference accumulates and as a frame
 * replaces, and the bar switches to video for a frame exactly as it would
 * for any other still.
 */
export function useFirstFrame() {
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
    async (clip: AttachRef, role: AttachRole) => {
      if (!target) {
        toast.add({
          intent: "danger",
          title: "Choose a project first",
          description: "The frame goes into a project's input pool, and the bar has none yet.",
        });
        return;
      }
      if (!gone.current) setBusy(clip.node);
      try {
        const { folder } = await getProjectInputs(target);
        const frame = await grabFrame({
          node: clip.node,
          at: 0,
          dest: folder,
          name: firstFrameName(clip.name),
        });
        const asset = await getAsset(frame.node);
        bar.attach({ node: frame.node, url: asset.url, name: frame.name, kind: "object" }, role);
        toast.add({
          intent: "success",
          title: `First frame of ${assetLabel(clip.name)}`,
          description: `${frame.name} is in the input pool and on the bar as ${ROLE_WORDS[role].label.toLowerCase()}.`,
        });
      } catch (err) {
        toast.add({
          intent: "danger",
          title: "Could not take the first frame",
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
