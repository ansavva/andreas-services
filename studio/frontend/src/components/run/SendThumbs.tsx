import { useNavigate } from "react-router-dom";

import type { RunSend } from "../../types";
import { assetLabel } from "../../utils/format";
import { objectPath } from "../../utils/location";
import { pressInApp } from "../common/pressInApp";
import { MediaThumb } from "../media/MediaThumb";

/**
 * What a run was sent — the pictures that went in, as links.
 *
 * **They were pictures and nothing else, and that was the bug.** A press did
 * nothing at all: no open, no new tab, no way through to the file the run was
 * checked against. The output tiles beside them open, the character chip opens,
 * the folder cell opens; the one thing a person is most likely to want to look
 * at closely was inert.
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

  return (
    <div className="flex flex-wrap gap-1.5" aria-label="Sent">
      {sends.map((send) => {
        // Whole, not cropped: what went in is what a person is checking the
        // output against. The role is the tooltip, not a word over the picture
        // — at this size a label hides what it labels.
        const title = `${send.role ?? send.field} · ${assetLabel(send.name)}`;
        const thumb = (
          <MediaThumb
            nodeId={send.node}
            url={send.url}
            name={send.name}
            aspect="square"
            fit="contain"
            title={send.url ? undefined : title}
            className={`${size} border border-line`}
          />
        );
        if (!send.url) return <span key={send.node}>{thumb}</span>;

        const to = objectPath(send.node);
        return (
          <a
            key={send.node}
            href={to}
            title={title}
            aria-label={`Open ${assetLabel(send.name)}`}
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
