import { useNavigate } from "react-router-dom";

import { Text } from "@ansavva/design-system";

import type { RunSend } from "../../types";
import { assetLabel } from "../../utils/format";
import { objectPath } from "../../utils/location";
import { pressInApp } from "../common/pressInApp";
import { MediaThumb } from "../media/MediaThumb";

/**
 * The order the roles are drawn in, and what each one is called under a
 * picture.
 *
 * **The create sheet's own words and the create sheet's own order** — Start
 * frame, End frame, then the references in send order — because it is the same
 * fact read back: what this run was handed and as what. `Image refs` is the
 * plural on a tile row, so a single picture takes the numbered form the sheet
 * captions its own tiles with (`Image 1`).
 */
const ROLE_ORDER: Record<string, number> = { start: 0, end: 1, input: 2, reference: 3 };
const ROLE_WORD: Record<string, string> = {
  start: "Start frame",
  end: "End frame",
  input: "Input",
};

/**
 * What a run was sent — the pictures that went in, as what, and as links.
 *
 * **The role is on the picture now, not in a tooltip.** These were a flat row
 * of squares with `reference · seed-01.jpg` hidden in a `title`: invisible on
 * a touch screen, and on a pointer only if you knew to hover. A video run
 * carrying a start frame, an end frame and three references drew five
 * identical thumbs in the order they happened to be sent, so the one question
 * this block exists to answer — which picture was the start frame — was the
 * one thing it did not say. Now each one carries its word, and they are
 * grouped: frames first, then the references in send order, numbered the way a
 * prompt cites them.
 *
 * **A real `<a href>`, so the browser's own gestures work.** ⌘-click and
 * middle-click open a new tab and Copy address yields a link — `pressInApp`
 * hands those back to the browser and keeps a plain click for the router, the
 * same bargain `EntityRow` and `MediaTile` already strike. A bare href would be
 * a full page load of a single-page app.
 *
 * **No `?in=`, deliberately.** A send is a picture from somewhere else — a
 * character's reference pool, an input folder, another run's output — so there
 * is no sequence here to walk. `/o/<id>` on its own is the contextless case the
 * object screen already handles: it draws the file and offers `OwnerLink` back
 * to whatever owns it.
 *
 * **A send whose node is gone is not a link.** `url` is null once the object
 * behind it is deleted; the thumb stays so the run still says what it was sent,
 * and a link to a file that cannot be drawn would only lead to an error page.
 */
export function SendThumbs({
  sends,
  size,
}: {
  sends: readonly RunSend[];
  /** `20` in a feed row, `28` in the opened run's rail — the two that exist. */
  size: "size-20" | "size-28";
}) {
  const navigate = useNavigate();
  if (sends.length === 0) return null;

  // **Sorted for reading, never for sending.** `order` is what the model was
  // handed and it is preserved inside a role — the references stay in their
  // send order, which is what `Image 2` means — but the frames come first,
  // because "which one was the start" is the question a person opens a video
  // run with.
  const ordered = [...sends].sort((a, b) => {
    const byRole =
      (ROLE_ORDER[a.role ?? ""] ?? 4) - (ROLE_ORDER[b.role ?? ""] ?? 4);
    return byRole !== 0 ? byRole : a.order - b.order;
  });

  let references = 0;

  return (
    <div className="flex flex-wrap gap-1.5" aria-label="Sent">
      {ordered.map((send) => {
        // A reference's number is its position among the references, which is
        // how a prompt cites it — not its position among every send.
        if (send.role === "reference") references += 1;
        const word =
          send.role === "reference"
            ? `Image ${references}`
            : (ROLE_WORD[send.role ?? ""] ?? send.field);

        const title = `${word} · ${assetLabel(send.name)}`;
        const thumb = (
          <span className="flex flex-col gap-1">
            {/* Whole, not cropped: what went in is what a person is checking
                the output against. */}
            <MediaThumb
              nodeId={send.node}
              url={send.url}
              name={send.name}
              aspect="square"
              fit="contain"
              className={`${size} border border-line`}
            />
            {/* Under the picture rather than over it: at this size a caption
                laid on the frame hides what it labels, and these are small
                enough that every pixel of the picture is doing work. */}
            <Text
              variant="caption"
              tone="muted"
              className={`${size === "size-28" ? "w-28" : "w-20"} truncate text-center`}
            >
              {word}
            </Text>
          </span>
        );

        if (!send.url) {
          return (
            <span key={send.node} title={title}>
              {thumb}
            </span>
          );
        }

        const to = objectPath(send.node);
        return (
          <a
            key={send.node}
            href={to}
            title={title}
            aria-label={`Open ${word} — ${assetLabel(send.name)}`}
            onClick={pressInApp(navigate, to)}
            className="block shrink-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            {thumb}
          </a>
        );
      })}
    </div>
  );
}
