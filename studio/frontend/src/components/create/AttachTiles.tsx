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
 * The tiles under the mode switch: one per image role this model takes —
 * ElevenLabs' `Image refs` / `Start frame` / `End frame`.
 *
 * **A tile is a role, and pressing it is what opens the picker.** The picker
 * supplies images for whichever role is highlighted, so the tile is the
 * control: press it and the picker under the prompt fills that role; press
 * the highlighted one again and it closes. The role list is read off the
 * model (`fieldFor`), so a still model never shows a start frame and a model
 * with no reference list never shows Refs.
 *
 * **What is attached is drawn IN the tile**, as thumbs with their own ×, so
 * the tile reads as "what this role holds" rather than "a button". A role
 * that holds one image and already does draws no empty slot beside it; the
 * reference list always has room for one more.
 *
 * Nothing here is a `<button>` inside a `<button>`: the tile is the button,
 * the thumbs and their × sit beside it inside the group.
 */
export function AttachTiles({
  kind,
  entry,
  attachments,
  role,
  onRole,
  onDetach,
  onClear,
  keep,
  onKeep,
}: {
  kind: RunKind;
  entry: ModelEntry;
  attachments: readonly Attachment[];
  /** The highlighted role, or none. */
  role: AttachRole | null;
  onRole: (role: AttachRole | null) => void;
  /** Take one attachment off, by its index in `attachments`. */
  onDetach: (index: number) => void;
  onClear: () => void;
  keep: boolean;
  onKeep: (keep: boolean) => void;
}) {
  const roles = ROLES_BY_KIND[kind].filter((each) => fieldFor(each, entry) !== null);
  if (roles.length === 0) return null;

  return (
    <div className="flex flex-wrap items-start gap-2" data-mode-strip="">
      {roles.map((each) => {
        const words = ROLE_WORDS[each];
        const Icon = ROLE_ICONS[each];
        const held = attachments
          .map((attachment, index) => ({ attachment, index }))
          .filter(({ attachment }) => attachment.role === each);
        const on = role === each;
        const toggle = () => onRole(on ? null : each);
        const slot = held.length === 0 || each === "reference";
        return (
          <div
            key={each}
            role="group"
            aria-label={words.label}
            data-role-cell={each}
            className={`flex items-stretch gap-1 rounded-md p-1 transition-colors ${on ? "bg-fill-hover" : "bg-fill-faint"}`}
          >
            {slot && (
              <Button
                intent="secondary"
                size="md"
                aria-pressed={on}
                title={words.hint}
                className={`h-14 min-w-28 gap-2 rounded-sm px-4 active:bg-fill-active
                            ${on ? "bg-fill-hover text-ink hover:bg-fill-hover" : "bg-transparent text-muted hover:bg-fill hover:text-ink"}`}
                onClick={toggle}
              >
                <Icon className={GLYPH} />
                {words.label}
              </Button>
            )}
            {held.map(({ attachment, index }) => (
              <AttachmentThumb
                key={`${attachment.ref.node}-${index}`}
                attachment={attachment}
                onPress={slot ? undefined : toggle}
                onDetach={() => onDetach(index)}
              />
            ))}
          </div>
        );
      })}

      {attachments.length > 0 && (
        <div className="ml-auto flex items-center gap-0.5 self-center">
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

/**
 * One attached image: the picture, and the way off.
 *
 * The × is a sibling of the picture rather than a child of a button around
 * it — a control inside a control is invalid HTML the browser resolves by
 * dropping one. Where the tile has no empty slot (a one-image role that is
 * full), the picture itself is what opens the picker to swap it.
 */
export function AttachmentThumb({
  attachment,
  onPress,
  onDetach,
}: {
  attachment: Attachment;
  onPress?: (() => void) | undefined;
  onDetach: () => void;
}) {
  const { ref, role } = attachment;
  const title = `${ROLE_WORDS[role].label} · ${assetLabel(ref.name)}`;
  const picture = (
    <img
      src={ref.url ?? undefined}
      alt=""
      className="size-full object-cover"
    />
  );
  return (
    // `ref.name` is absent when the node it names has been deleted — see
    // `AttachRef`. The thumb stays, so it can be seen and removed.
    <div
      className="relative size-14 shrink-0 overflow-hidden rounded-sm bg-fill"
      title={title}
    >
      {onPress ? (
        <Button
          intent="secondary"
          size="md"
          aria-label={`Change ${ROLE_WORDS[role].label.toLowerCase()}`}
          className="block size-full rounded-none bg-transparent p-0 hover:bg-transparent"
          onClick={onPress}
        >
          {picture}
        </Button>
      ) : (
        picture
      )}
      <IconButton
        intent="overlay"
        size="sm"
        label={`Remove ${assetLabel(ref.name)}`}
        className="absolute right-0.5 top-0.5 size-5 rounded-pill bg-overlay-scrim/70"
        onClick={onDetach}
      >
        <CloseIcon className="size-3 fill-none stroke-current stroke-2" />
      </IconButton>
    </div>
  );
}
