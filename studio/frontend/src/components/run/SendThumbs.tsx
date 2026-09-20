import { useNavigate } from "react-router-dom";

import { Text } from "@ansavva/design-system";

import type { RunFeedRow, RunSend } from "../../types";
import { assetLabel } from "../../utils/format";
import { objectPath } from "../../utils/location";
import { pressInApp } from "../common/pressInApp";
import { ROLE_WORDS } from "../create/roles";
import { TILE_BOX, TILE_CAPTION, TILE_ROW } from "../create/tile";
import { MediaThumb } from "../media/MediaThumb";
import { checkpointName } from "./CheckpointList";

/**
 * The order the roles are drawn in, and what each one is called under a
 * picture.
 *
 * **The create sheet's own words and the create sheet's own order** — Start
 * frame, End frame, then the references in send order — because it is the same
 * fact read back: what this run was handed and as what. The caption on the
 * tile is the sheet's short form (`Start`, `End`, `Input`, `Source`,
 * `Image 1`); the tooltip and the link's name carry the long one.
 */
const ROLE_ORDER: Record<string, number> = { start: 0, end: 1, clip: 2, input: 3, reference: 4, lora: 5 };
const ROLE_WORD: Record<string, string> = {
  start: ROLE_WORDS.start.label,
  end: ROLE_WORDS.end.label,
  clip: ROLE_WORDS.clip.label,
  lora: "LoRA",
  input: ROLE_WORDS.input.label,
};
const ROLE_CAPTION: Record<string, string> = {
  start: "Start",
  end: "End",
  clip: "Source",
  input: "Input",
};

/**
 * What a run was sent — the pictures that went in, as what, and as links.
 *
 * **Drawn as the create sheet's tiles, because they are the create sheet's
 * tiles.** The sheet shows what a run will be handed as a row of 112px tiles,
 * each the picture whole at its own width with its role on a scrim at the
 * foot; this showed what a run was handed as 80px squares with the role
 * underneath — the same pictures, a screen apart, in a different shape.
 * Now the row here is the sheet's row (`tile.ts`): the box, the face, the
 * strip, and one line that scrolls sideways rather than wrapping. Edit on a
 * run loads these into the sheet, and they should look like they were
 * already there.
 *
 * **The role is on the picture, not in a tooltip.** These were a flat row of
 * squares with `reference · seed-01.jpg` hidden in a `title`: invisible on a
 * touch screen, and on a pointer only if you knew to hover. A video run
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
 * behind it is deleted; the tile stays so the run still says what it was sent,
 * and a link to a file that cannot be drawn would only lead to an error page.
 */
export function SendThumbs({ sends, cast }: { sends: readonly RunSend[]; cast?: RunFeedRow["cast"] }) {
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
  // Weights are not pictures. A LoRA pair in the tile row was two image-sized
  // boxes with a filename in each; it is one line under the pictures now —
  // which checkpoint, and the two files as links.
  const pictures = ordered.filter((send) => send.role !== "lora");
  const loras = ordered.filter((send) => send.role === "lora");

  return (
    <div className="flex min-w-0 flex-col gap-2">
    {pictures.length > 0 && (
    <div className={TILE_ROW} aria-label="Sent">
      {pictures.map((send) => {
        // A reference's number is its position among the references, which is
        // how a prompt cites it — not its position among every send.
        if (send.role === "reference") references += 1;
        const word =
          send.role === "reference"
            ? `Image ${references}`
            : (ROLE_WORD[send.role ?? ""] ?? send.field);
        const caption =
          send.role === "reference"
            ? word
            : (ROLE_CAPTION[send.role ?? ""] ?? word);

        const title = `${word} · ${assetLabel(send.name)}`;
        const tile = (
            <>
              {/* Whole, not cropped, at its own width: what went in is what a
                  person is checking the output against, and which take it
                  was is part of that. */}
              <MediaThumb
                nodeId={send.node}
                url={send.url}
                poster={send.poster}
                name={send.name}
                aspect="auto"
                fit="natural"
                className="h-full min-w-full rounded-md"
              />
              <span role="presentation" className={`${TILE_CAPTION} pointer-events-none`}>
                {caption}
              </span>
            </>
        );

        if (!send.url) {
          return (
            <span key={send.node} title={title} className={`${TILE_BOX} block`}>
              {tile}
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
            className={`${TILE_BOX} block focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary`}
          >
            {tile}
          </a>
        );
      })}
    </div>
    )}
    {loras.length > 0 && <LoraSends sends={loras} cast={cast} />}
    </div>
  );
}

/**
 * The LoRA pairs a run was handed, one line each: the checkpoint they are —
 * the stem and the save point read off the file name — and `high` / `low`
 * as links to the files. A pair is one thing to a person even though it is
 * two sends, so the two are grouped by stem and step.
 */
function LoraSends({ sends, cast }: { sends: readonly RunSend[]; cast?: RunFeedRow["cast"] }) {
  const navigate = useNavigate();
  // Whose weights: the send's source names the character it was filed under,
  // and the run's cast has that character's name.
  const nameOf = (send: RunSend) =>
    cast?.find((c) => c.id === send.source?.character)?.name ?? null;
  const pairs = new Map<string, { stem: string; step: number | null; who: string | null; files: Partial<Record<"high" | "low", RunSend>> }>();
  for (const send of sends) {
    const parsed = checkpointName(send.name ?? "");
    const key = parsed ? `${parsed.stem}:${parsed.step ?? "final"}` : (send.name ?? send.node);
    const entry = pairs.get(key) ?? { stem: parsed?.stem ?? assetLabel(send.name), step: parsed?.step ?? null, who: nameOf(send), files: {} };
    entry.files[parsed?.expert ?? "high"] = send;
    pairs.set(key, entry);
  }
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="LoRA">
      {[...pairs.values()].map((pair) => (
        <li
          key={`${pair.stem}:${pair.step ?? "final"}`}
          className="flex items-center gap-2 rounded-md border border-line bg-card px-2 py-1"
          data-lora-send=""
        >
          <Text variant="caption" weight="medium">
            LoRA
          </Text>
          {pair.who ? (
            <Text variant="caption" weight="medium">
              {pair.who}
            </Text>
          ) : null}
          <Text variant="caption" family="mono" tone="muted" className="max-w-[12rem] truncate">
            {pair.stem}
          </Text>
          <Text variant="caption" tone="muted" className="whitespace-nowrap tabular-nums">
            {pair.step === null ? "final" : `step ${pair.step}`}
          </Text>
          {(["high", "low"] as const).map((expert) => {
            const send = pair.files[expert];
            if (!send) return null;
            if (!send.url) {
              return (
                <Text key={expert} variant="caption" tone="muted" className="font-mono line-through">
                  {expert}
                </Text>
              );
            }
            const to = objectPath(send.node);
            return (
              <a
                key={expert}
                href={to}
                onClick={pressInApp(navigate, to)}
                aria-label={`Open ${expert}-noise LoRA — ${assetLabel(send.name)}`}
                className="rounded-sm border border-line px-1.5 py-0.5 font-mono text-xs hover:bg-surface-alt focus-visible:outline focus-visible:outline-2"
              >
                {expert}
              </a>
            );
          })}
        </li>
      ))}
    </ul>
  );
}
