import type { ReactElement } from "react";

import { Button, IconButton } from "@ansavva/design-system";

import type { AttachRole, Attachment } from "../../context/CreateBarContext";
import type { ModelEntry, RunKind } from "../../types";
import { assetLabel } from "../../utils/format";
import {
  CloseIcon,
  FrameEndIcon,
  ImagePlusIcon,
  LockIcon,
  PencilIcon,
  StartFrameIcon,
  SwapIcon,
  TrashIcon,
} from "../common/icons";
import { ROLES_BY_KIND, ROLE_WORDS, fieldFor } from "./roles";

const ROLE_ICONS: Record<AttachRole, (props: { className?: string }) => ReactElement> = {
  reference: ImagePlusIcon,
  input: PencilIcon,
  start: StartFrameIcon,
  end: FrameEndIcon,
};

const GLYPH = "size-4 shrink-0 fill-none stroke-current stroke-[1.5]";

/**
 * The row under the mode switch: what the run will be handed, and the tiles
 * that add to it — ElevenLabs' `Start frame · End frame · Image refs`.
 *
 * **One row, scrolling sideways, pictures first.** A frame that has been
 * chosen stands where its ghost tile stood, and the two frames get a ⇄
 * between them; references line up in send order, each captioned with the
 * position a prompt would cite (`Image 1`, `Image 2`), and the `Image refs`
 * tile stays at the end as long as the model has room for one more. Every
 * picture carries its own ×, and pressing the picture reopens the picker on
 * its role to swap it.
 *
 * **A ghost tile dims when the model's own rules block it.** The registry's
 * `start_excludes_refs` / `end_excludes_refs` say a model takes a frame OR
 * references; the tile that would break that is drawn but disabled, and its
 * hover says why. `max_refs` retires the `Image refs` tile once it is met.
 * Which roles exist at all is read off the model too (`fieldFor`): a still
 * model never shows a frame.
 *
 * Nothing here is a `<button>` inside a `<button>`: the picture is a button,
 * its × a sibling.
 */
export function AttachTiles({
  kind,
  entry,
  attachments,
  role,
  onRole,
  onDetach,
  onSwapFrames,
  onClear,
  keep,
  onKeep,
}: {
  kind: RunKind;
  entry: ModelEntry;
  attachments: readonly Attachment[];
  /** The highlighted role — the one the picker is filling — or none. */
  role: AttachRole | null;
  onRole: (role: AttachRole | null) => void;
  /** Take one attachment off, by its index in `attachments`. */
  onDetach: (index: number) => void;
  /** The start frame becomes the end frame and vice versa. */
  onSwapFrames: () => void;
  onClear: () => void;
  keep: boolean;
  onKeep: (keep: boolean) => void;
}) {
  const roles = ROLES_BY_KIND[kind].filter((each) => fieldFor(each, entry) !== null);
  if (roles.length === 0) return null;

  const images = entry.images ?? {};
  const held = (of: AttachRole) =>
    attachments
      .map((attachment, index) => ({ attachment, index }))
      .filter(({ attachment }) => attachment.role === of);
  const start = held("start")[0];
  const end = held("end")[0];
  const refs = held("reference");
  const input = held("input")[0];

  // The model's own rules, as which tile is blocked and why.
  const blocked = (of: AttachRole): string | null => {
    if (of === "reference") {
      if (start && images.start_excludes_refs)
        return "This model takes a start frame or reference images, not both.";
      if (end && images.end_excludes_refs)
        return "This model takes an end frame or reference images, not both.";
      const cap = images.max_refs;
      if (typeof cap === "number") {
        const used = refs.length + (start && images.start_counts_toward_max_refs ? 1 : 0);
        if (used >= cap) return `This model takes at most ${cap} reference images.`;
      }
      return null;
    }
    if (of === "start" && refs.length > 0 && images.start_excludes_refs)
      return "This model takes a start frame or reference images, not both.";
    if (of === "end" && refs.length > 0 && images.end_excludes_refs)
      return "This model takes an end frame or reference images, not both.";
    return null;
  };

  const frameTile = (of: "start" | "end", holding: { attachment: Attachment; index: number } | undefined) => (
    <div key={of} role="group" aria-label={ROLE_WORDS[of].label} data-role-cell={of} className="contents">
      {holding ? (
        <Thumb
          attachment={holding.attachment}
          caption={of === "start" ? "Start" : "End"}
          onPress={() => onRole(role === of ? null : of)}
          onDetach={() => onDetach(holding.index)}
        />
      ) : (
        <Ghost role={of} on={role === of} blocked={blocked(of)} onPress={() => onRole(role === of ? null : of)} />
      )}
    </div>
  );

  return (
    <div className="flex items-center gap-2" data-mode-strip="">
      {/* `min-w-0` + `overflow-x-auto`: the row scrolls rather than wraps,
          and the keep/clear controls stay put beside it. */}
      <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto pb-1 [scrollbar-width:thin]">
        {roles.includes("start") && frameTile("start", start)}
        {start && end && (
          <IconButton size="sm" label="Swap the start and end frames" onClick={onSwapFrames}>
            <SwapIcon />
          </IconButton>
        )}
        {roles.includes("end") && frameTile("end", end)}

        {roles.includes("input") && (
          <div role="group" aria-label={ROLE_WORDS.input.label} data-role-cell="input" className="contents">
            {input ? (
              <Thumb
                attachment={input.attachment}
                caption="Input"
                onPress={() => onRole(role === "input" ? null : "input")}
                onDetach={() => onDetach(input.index)}
              />
            ) : (
              <Ghost
                role="input"
                on={role === "input"}
                blocked={null}
                onPress={() => onRole(role === "input" ? null : "input")}
              />
            )}
          </div>
        )}

        {roles.includes("reference") && (
          <div role="group" aria-label={ROLE_WORDS.reference.label} data-role-cell="reference" className="contents">
            {refs.map(({ attachment, index }, position) => (
              <Thumb
                key={`${attachment.ref.node}-${index}`}
                attachment={attachment}
                caption={`Image ${position + 1}`}
                onPress={() => onRole(role === "reference" ? null : "reference")}
                onDetach={() => onDetach(index)}
              />
            ))}
            <Ghost
              role="reference"
              on={role === "reference"}
              blocked={blocked("reference")}
              onPress={() => onRole(role === "reference" ? null : "reference")}
            />
          </div>
        )}
      </div>

      {attachments.length > 0 && (
        <div className="flex shrink-0 items-center gap-0.5">
          <IconButton
            size="sm"
            pressed={keep}
            label={
              keep
                ? "Keep these images for the next send (on)"
                : "Keep these images for the next send"
            }
            onClick={() => onKeep(!keep)}
          >
            <LockIcon />
          </IconButton>
          <IconButton size="sm" label="Clear images" onClick={onClear}>
            <TrashIcon />
          </IconButton>
        </div>
      )}
    </div>
  );
}

/** A role with nothing in it yet: the glyph and the word, and it opens the picker. */
function Ghost({
  role,
  on,
  blocked,
  onPress,
}: {
  role: AttachRole;
  on: boolean;
  /** Why this tile cannot be used right now, or null when it can. */
  blocked: string | null;
  onPress: () => void;
}) {
  const words = ROLE_WORDS[role];
  const Icon = ROLE_ICONS[role];
  return (
    <Button
      intent="secondary"
      size="md"
      aria-pressed={on}
      disabled={blocked !== null}
      title={blocked ?? words.hint}
      className={`h-[4.5rem] shrink-0 gap-2 rounded-md px-4 active:bg-fill-active
                  ${on ? "bg-fill-hover text-ink hover:bg-fill-hover" : "bg-fill-faint text-muted hover:bg-fill hover:text-ink"}`}
      onClick={onPress}
    >
      <Icon className={GLYPH} />
      {words.label}
    </Button>
  );
}

/**
 * One attached picture: the thumb, a caption saying what it is to the run,
 * and the way off.
 *
 * The × is a sibling of the picture rather than a child of a button around
 * it — a control inside a control is invalid HTML the browser resolves by
 * dropping one. The picture itself reopens the picker on its role.
 */
export function Thumb({
  attachment,
  caption,
  onPress,
  onDetach,
}: {
  attachment: Attachment;
  caption: string;
  onPress: () => void;
  onDetach: () => void;
}) {
  const { ref, role } = attachment;
  // `ref.name` is absent when the node it names has been deleted — see
  // `AttachRef`. The thumb stays, so it can be seen and removed.
  const title = `${ROLE_WORDS[role].label} · ${assetLabel(ref.name)}`;
  return (
    <div className="relative size-[4.5rem] shrink-0" title={title} data-attachment={role}>
      <Button
        intent="secondary"
        size="md"
        aria-label={`Change ${caption.toLowerCase()} — ${assetLabel(ref.name)}`}
        className="relative block size-full overflow-hidden rounded-md bg-fill p-0 hover:bg-fill"
        onClick={onPress}
      >
        <img src={ref.url ?? undefined} alt="" className="size-full object-cover" />
        {/* The word over the picture's foot, on a scrim, the way ElevenLabs
            labels `@Image 1`. */}
        <span className="absolute inset-x-0 bottom-0 truncate bg-overlay-scrim/60 px-1 py-0.5 text-center text-[11px] font-medium text-overlay-ink">
          {caption}
        </span>
      </Button>
      <IconButton
        intent="overlay"
        size="sm"
        label={`Remove ${assetLabel(ref.name)}`}
        className="absolute -right-1 -top-1 size-5 rounded-pill bg-overlay-scrim/80"
        onClick={onDetach}
      >
        <CloseIcon className="size-3 fill-none stroke-current stroke-2" />
      </IconButton>
    </div>
  );
}
