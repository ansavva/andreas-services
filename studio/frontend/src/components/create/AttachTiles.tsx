import { useState, type DragEvent, type ReactElement } from "react";

import { Button, IconButton } from "@ansavva/design-system";

import type { AttachRef, AttachRole, Attachment } from "../../context/CreateBarContext";
import { WIDE, useMediaQuery } from "../../hooks/useMediaQuery";
import type { ModelEntry, RunKind } from "../../types";
import { assetLabel } from "../../utils/format";
import { ActionMenu, type MenuAction } from "../common/ActionMenu";
import { ApertureSpinner } from "../common/Aperture";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  CloseIcon,
  FrameEndIcon,
  ImagePlusIcon,
  PencilIcon,
  StartFrameIcon,
  SwapIcon,
  TrashIcon,
  VideoIcon,
} from "../common/icons";
import { isNodeDrag, readNodeDrag } from "./dragRef";
import { ROW_ATTR, useReorder, type Sortable } from "./reorder";
import { ROLES_BY_KIND, ROLE_WORDS, fieldFor } from "./roles";

const ROLE_ICONS: Record<AttachRole, (props: { className?: string }) => ReactElement> = {
  reference: ImagePlusIcon,
  input: PencilIcon,
  start: StartFrameIcon,
  end: FrameEndIcon,
  clip: VideoIcon,
};

const GLYPH = "size-4 shrink-0 fill-none stroke-current stroke-[1.5]";

/** The roles a model of this kind draws tiles for. */
function rolesOf(kind: RunKind, entry: ModelEntry): AttachRole[] {
  return ROLES_BY_KIND[kind].filter((each) => fieldFor(each, entry) !== null);
}

/**
 * The model's own rules, as why a role cannot take one more picture — or
 * null when it can. `start_excludes_refs` / `end_excludes_refs` say a model
 * takes a frame OR references; `max_refs` is the ceiling on references.
 */
function blockedReason(
  of: AttachRole,
  entry: ModelEntry,
  attachments: readonly Attachment[],
): string | null {
  const images = entry.images ?? {};
  const has = (role: AttachRole) => attachments.some((each) => each.role === role);
  const refs = attachments.filter((each) => each.role === "reference").length;
  const start = has("start");
  const end = has("end");
  if (of === "reference") {
    if (start && images.start_excludes_refs)
      return "This model takes a start frame or reference images, not both.";
    if (end && images.end_excludes_refs)
      return "This model takes an end frame or reference images, not both.";
    const cap = images.max_refs;
    if (typeof cap === "number") {
      const used = refs + (start && images.start_counts_toward_max_refs ? 1 : 0);
      if (used >= cap) return `This model takes at most ${cap} reference images.`;
    }
    return null;
  }
  if (of === "start" && refs > 0 && images.start_excludes_refs)
    return "This model takes a start frame or reference images, not both.";
  if (of === "end" && refs > 0 && images.end_excludes_refs)
    return "This model takes an end frame or reference images, not both.";
  return null;
}

/**
 * Whether a dragged node may land on this role. A drag carries a still —
 * `MediaThumb` never starts one on a clip — and the clip cell takes only a
 * video, so a drop there is refused and the picker is the way in.
 */
function takesDrop(of: AttachRole): boolean {
  return of !== "clip";
}

/**
 * Where a picture dropped on the sheet but on no particular tile goes.
 *
 * The tiles name a role; the rest of the sheet does not, and a drop there is
 * still a person putting a picture into the run. It takes the role a press
 * on a tile would have picked first — a reference — and falls back through
 * the roles a still can fill (an edit model's input, a video model's start
 * frame, its end frame) to the first the model has room for. Null when none
 * has, and the drop is refused the way a blocked tile refuses it.
 */
export function fallbackDropRole(
  kind: RunKind,
  entry: ModelEntry,
  attachments: readonly Attachment[],
): AttachRole | null {
  const roles = rolesOf(kind, entry);
  // No `clip`: a drop is a still, and a still is not a clip.
  const order: AttachRole[] = ["reference", "input", "start", "end"];
  return (
    order.find(
      (of) =>
        roles.includes(of) &&
        blockedReason(of, entry, attachments) === null &&
        // One picture per frame or input: a second drop there would replace
        // nothing and attach nothing a person can see.
        (of === "reference" || !attachments.some((each) => each.role === of)),
    ) ?? null
  );
}

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
 *
 * **References can be dragged along the row into a new order**, by mouse or
 * by a held finger, and a focused one moves with the arrow keys — see
 * `reorder.ts`. Their order is the order they are sent in and the number the
 * prompt cites, so `Image 2` before `Image 1` has to be a gesture and not a
 * remove-and-reattach. Frames have the ⇄ instead: two roles, not a row.
 *
 * **On a phone, pressing a picture opens a sheet of what can be done to it**
 * — choose another, move it earlier or later, swap the frames, remove it —
 * as 44px rows, where on a desk the same press reopens the picker. The
 * hold-then-drag and the × still work there; they were just not enough. A
 * 20px × at a tile's corner and a 250ms hold on a row that also scrolls
 * were the two things a thumb could not do reliably, and a picture is the
 * one target on the row that is big. The same split every menu in the app
 * makes (`ActionMenu`: a dropdown above `md`, a bottom sheet below), and
 * the × itself grows to 32px with a 40px reach where the pointer is coarse.
 *
 * **Each cell is also where a dragged picture lands.** A tile in the library's
 * grid can be dragged straight onto the role it should fill, which is the one
 * thing the buttons on those tiles cannot express — a button has to pick a role
 * for you, and it picks `reference`. A blocked cell refuses the drop rather
 * than taking it and failing at send: no `preventDefault`, so the cursor says
 * no. See `dragRef.ts` for why the decision is made from the type list.
 */
export function AttachTiles({
  kind,
  entry,
  attachments,
  role,
  onRole,
  onDetach,
  onSwapFrames,
  onMove,
  onDropRef,
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
  /** Move the attachment at one index in `attachments` to sit at another. */
  onMove: (from: number, to: number) => void;
  /** A picture dragged onto a role tile. The bar decides what `attach` does with it. */
  onDropRef: (ref: AttachRef, role: AttachRole) => void;
}) {
  /** The cell a drag is currently over, drawn as that cell's highlighted state. */
  const [over, setOver] = useState<AttachRole | null>(null);

  const held = (of: AttachRole) =>
    attachments
      .map((attachment, index) => ({ attachment, index }))
      .filter(({ attachment }) => attachment.role === of);
  const start = held("start")[0];
  const end = held("end")[0];
  const refs = held("reference");
  const input = held("input")[0];
  const clip = held("clip")[0];

  // The drag speaks in positions among the references; the bar in indices.
  const sortable = useReorder(refs.length, (from, to) => {
    const a = refs[from];
    const b = refs[to];
    if (a && b) onMove(a.index, b.index);
  });

  const roles = rolesOf(kind, entry);
  if (roles.length === 0) return null;

  // The model's own rules, as which tile is blocked and why.
  const blocked = (of: AttachRole): string | null => blockedReason(of, entry, attachments);

  /**
   * The phone sheet's lines for one attached picture. `Choose…` is the press
   * a desk makes on the picture — the picker on its role; the two moves
   * are the drag; the swap is the ⇄; Remove is the ×. Every gesture on the
   * row, as a row of words a thumb can hit.
   */
  const menuFor = (
    holding: { attachment: Attachment; index: number },
    among?: { position: number; count: number },
  ): MenuAction[] => {
    const of = holding.attachment.role;
    const lines: MenuAction[] = [
      {
        key: "choose",
        label: `${ROLE_WORDS[of].choose}…`,
        icon: <ImagePlusIcon className={GLYPH} />,
        onSelect: () => onRole(of),
      },
    ];
    if (among && among.count > 1) {
      lines.push(
        {
          key: "earlier",
          label: "Move earlier",
          icon: <ChevronLeftIcon className={GLYPH} />,
          disabled: among.position === 0,
          reason: among.position === 0 ? "Already first." : undefined,
          onSelect: () => {
            const to = refs[among.position - 1];
            if (to) onMove(holding.index, to.index);
          },
        },
        {
          key: "later",
          label: "Move later",
          icon: <ChevronRightIcon className={GLYPH} />,
          disabled: among.position === among.count - 1,
          reason: among.position === among.count - 1 ? "Already last." : undefined,
          onSelect: () => {
            const to = refs[among.position + 1];
            if (to) onMove(holding.index, to.index);
          },
        },
      );
    }
    if ((of === "start" || of === "end") && start && end)
      lines.push({
        key: "swap",
        label: "Swap the start and end frames",
        icon: <SwapIcon className={GLYPH} />,
        onSelect: onSwapFrames,
      });
    lines.push({
      key: "remove",
      label: "Remove",
      icon: <TrashIcon className={GLYPH} />,
      danger: true,
      onSelect: () => onDetach(holding.index),
    });
    return lines;
  };

  /**
   * The four handlers that make one cell a target.
   *
   * `dragover` fires continuously and must `preventDefault` on **every** one of
   * them or the browser keeps its default handling — `FolderBrowser`'s upload
   * zone carries the same note. `dragleave` is filtered through `contains`
   * because it fires on every crossing between a cell's own children, and a
   * highlight toggled off by each of those flickers; the cell's group element
   * has no box (`display: contents`) and is still an element in the tree, so
   * the containment test works.
   */
  const dropTarget = (of: AttachRole) => {
    const refused = blocked(of) !== null || !takesDrop(of);
    return {
      onDragEnter: (event: DragEvent) => {
        if (!isNodeDrag(event) || refused) return;
        event.preventDefault();
        setOver(of);
      },
      onDragOver: (event: DragEvent) => {
        if (!isNodeDrag(event) || refused) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      },
      onDragLeave: (event: DragEvent) => {
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
        setOver((current) => (current === of ? null : current));
      },
      onDrop: (event: DragEvent) => {
        setOver(null);
        if (refused) return;
        const ref = readNodeDrag(event);
        if (!ref) return;
        event.preventDefault();
        // The sheet under these cells takes a drop as a reference; a drop that
        // named its role has already been answered here.
        event.stopPropagation();
        onDropRef(ref, of);
      },
    };
  };

  const frameTile = (of: "start" | "end", holding: { attachment: Attachment; index: number } | undefined) => (
    <div
      key={of}
      role="group"
      aria-label={ROLE_WORDS[of].label}
      data-role-cell={of}
      className="contents"
      {...dropTarget(of)}
    >
      {holding ? (
        <Thumb
          attachment={holding.attachment}
          caption={of === "start" ? "Start" : "End"}
          onPress={() => onRole(role === of ? null : of)}
          onDetach={() => onDetach(holding.index)}
          menu={menuFor(holding)}
        />
      ) : (
        <Ghost
          role={of}
          on={role === of || over === of}
          blocked={blocked(of)}
          onPress={() => onRole(role === of ? null : of)}
        />
      )}
    </div>
  );

  return (
    <div className="flex items-center gap-2" data-mode-strip="">
      {/* `min-w-0` + `overflow-x-auto`: the row scrolls rather than wraps. */}
      <div
        className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto pb-1 [scrollbar-width:thin]"
        {...{ [ROW_ATTR]: "" }}
      >
        {roles.includes("start") && frameTile("start", start)}
        {start && end && (
          <IconButton size="sm" label="Swap the start and end frames" onClick={onSwapFrames}>
            <SwapIcon />
          </IconButton>
        )}
        {roles.includes("end") && frameTile("end", end)}

        {roles.includes("input") && (
          <div
            role="group"
            aria-label={ROLE_WORDS.input.label}
            data-role-cell="input"
            className="contents"
            {...dropTarget("input")}
          >
            {input ? (
              <Thumb
                attachment={input.attachment}
                caption="Input"
                onPress={() => onRole(role === "input" ? null : "input")}
                onDetach={() => onDetach(input.index)}
                menu={menuFor(input)}
              />
            ) : (
              <Ghost
                role="input"
                on={role === "input" || over === "input"}
                blocked={null}
                onPress={() => onRole(role === "input" ? null : "input")}
              />
            )}
          </div>
        )}

        {roles.includes("reference") && (
          <div
            role="group"
            aria-label={ROLE_WORDS.reference.label}
            data-role-cell="reference"
            className="contents"
            {...dropTarget("reference")}
          >
            {/* Keyed by node — `attach` holds each node once per role — so
                a tile keeps its element across a reorder, and the pointer
                capture on it holds. */}
            {refs.map(({ attachment, index }, position) => (
              <Thumb
                key={attachment.ref.node}
                attachment={attachment}
                caption={`Image ${position + 1}`}
                onPress={() => onRole(role === "reference" ? null : "reference")}
                onDetach={() => onDetach(index)}
                sortable={refs.length > 1 ? sortable(position) : undefined}
                menu={menuFor({ attachment, index }, { position, count: refs.length })}
              />
            ))}
            <Ghost
              role="reference"
              on={role === "reference" || over === "reference"}
              blocked={blocked("reference")}
              onPress={() => onRole(role === "reference" ? null : "reference")}
            />
          </div>
        )}

        {roles.includes("clip") && (
          <div role="group" aria-label={ROLE_WORDS.clip.label} data-role-cell="clip" className="contents">
            {clip ? (
              <Thumb
                attachment={clip.attachment}
                caption="Source"
                onPress={() => onRole(role === "clip" ? null : "clip")}
                onDetach={() => onDetach(clip.index)}
                menu={menuFor(clip)}
              />
            ) : (
              <Ghost
                role="clip"
                on={role === "clip"}
                blocked={null}
                onPress={() => onRole(role === "clip" ? null : "clip")}
              />
            )}
          </div>
        )}
      </div>

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
 * dropping one. The picture itself reopens the picker on its role — on a
 * desk; on a phone it opens the sheet of `menu` (see `AttachTiles`), the
 * picture being the `ActionMenu`'s trigger and the sheet its body.
 *
 * **The × is drawn for the pointer.** 20px at the corner under a mouse;
 * where the pointer is coarse it is 32px, set inside the corner rather
 * than over it, and reaches 4px past its own edge — a 40px target, which
 * is the floor a thumb needs. The reach stays inside the tile's box so the
 * row, which scrolls, is not handed 8px of overflow to scroll into.
 *
 * **A `pending` ref is drawn as what it is being made from, waiting.** A
 * clip's first frame takes the worker a few seconds, and a menu line that
 * did nothing visible for those seconds read as a menu line that did
 * nothing — so the tile appears at once, over the clip's own poster, with
 * the spinner and the word `Taking…`, and turns into the frame when it
 * lands. Its × takes it off the bar; the worker still finishes and the
 * frame still reaches the input pool, which is a file and not a spend.
 */
export function Thumb({
  attachment,
  caption,
  onPress,
  onDetach,
  sortable,
  menu,
}: {
  attachment: Attachment;
  caption: string;
  onPress: () => void;
  onDetach: () => void;
  /** Given when the tile can be dragged along its row — see `reorder.ts`. */
  sortable?: Sortable;
  /** The phone sheet's lines. Without it the press opens the picker on every screen. */
  menu?: MenuAction[];
}) {
  const wide = useMediaQuery(WIDE);
  const { ref, role } = attachment;
  // `ref.name` is absent when the node it names has been deleted — see
  // `AttachRef`. The thumb stays, so it can be seen and removed.
  const pending = ref.pending !== undefined;
  const title = pending ? ref.pending! : `${ROLE_WORDS[role].label} · ${assetLabel(ref.name)}`;
  const pictureClass = "relative block size-full overflow-hidden rounded-md bg-fill p-0 hover:bg-fill";
  const picture = (
    <>
      {pending ? (
        // The source it is being made from — a clip, for a first frame —
        // dimmed under the spinner. `<video>` because that source is a clip
        // today; an `<img>` of an mp4 is a broken picture.
        <>
          <video
            src={ref.url ?? undefined}
            muted
            playsInline
            preload="metadata"
            className="size-full object-cover opacity-40"
          />
          <span className="absolute inset-0 flex items-center justify-center">
            <ApertureSpinner size="sm" label={ref.pending!} />
          </span>
        </>
      ) : role === "clip" ? (
        // `preload="metadata"` is the free poster frame; nothing plays here.
        <video
          src={ref.url ?? undefined}
          muted
          playsInline
          preload="metadata"
          className="size-full object-cover"
        />
      ) : (
        <img src={ref.url ?? undefined} alt="" className="size-full object-cover" />
      )}
      {/* The word over the picture's foot, on a scrim, the way ElevenLabs
          labels `@Image 1`. */}
      <span className="absolute inset-x-0 bottom-0 truncate bg-overlay-scrim/60 px-1 py-0.5 text-center text-[11px] font-medium text-overlay-ink">
        {pending ? "Taking…" : caption}
      </span>
    </>
  );
  return (
    <div
      className={`relative size-[4.5rem] shrink-0 ${
        sortable
          ? // No callout on a held touch, and no image drag from a mouse: the
            // hold and the move are this row's own gesture.
            "select-none [-webkit-touch-callout:none] [&_img]:pointer-events-none"
          : ""
      } ${sortable?.dragging ? "z-10 scale-105 shadow-lg ring-2 ring-accent" : ""}`}
      title={title}
      data-attachment={role}
      data-pending={pending || undefined}
      aria-busy={pending || undefined}
      {...sortable?.wrapper}
    >
      {menu && !wide && !pending ? (
        <ActionMenu
          label={`${caption} — ${assetLabel(ref.name)}`}
          triggerLabel={`${caption} — ${assetLabel(ref.name)}`}
          actions={menu}
          className="contents"
          trigger={{ node: picture, className: pictureClass }}
        />
      ) : (
        <Button
          intent="secondary"
          size="md"
          aria-label={pending ? ref.pending! : `Change ${caption.toLowerCase()} — ${assetLabel(ref.name)}`}
          aria-description={sortable ? "Drag, or press an arrow key, to change its order." : undefined}
          className={pictureClass}
          onClick={onPress}
          disabled={pending}
          {...sortable?.button}
        >
          {picture}
        </Button>
      )}
      <IconButton
        intent="overlay"
        size="sm"
        label={`Remove ${assetLabel(ref.name)}`}
        className="absolute -right-1 -top-1 size-5 rounded-pill bg-overlay-scrim/80
                   pointer-coarse:right-1 pointer-coarse:top-1 pointer-coarse:size-8
                   pointer-coarse:before:absolute pointer-coarse:before:-inset-1 pointer-coarse:before:content-['']"
        onClick={onDetach}
      >
        <CloseIcon className="size-3 fill-none stroke-current stroke-2 pointer-coarse:size-4" />
      </IconButton>
    </div>
  );
}
