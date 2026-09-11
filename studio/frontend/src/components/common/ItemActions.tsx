import { copyLabel, useCopyToClipboard } from "../../hooks/useCopyToClipboard";
import { ActionMenu, type MenuAction } from "./ActionMenu";
import { ClipboardIcon, CopyIcon, FolderIntoIcon, PencilIcon, TrashIcon } from "./icons";

/** Every line's glyph, at the size a line of text carries. */
const GLYPH = "size-4 shrink-0 fill-none stroke-current stroke-[1.5]";

interface Props {
  /** What is being acted on, written into every label. */
  name: string;
  /** A file's or folder's name path — what "Copy" puts on the clipboard, for a
   *  `studio` command to resolve. Not an S3 key, and not what the actions beside
   *  it write with: rename, move, copy and delete all take node ids. */
  copyValue: string;
  /** What `copyValue` names, which is all that differs between the two labels. */
  copyNoun?: "path" | "prefix";
  /** Opens the parent's rename field. The parent owns it so it can be full width. */
  onRename: () => void;
  /** Opens the parent's destination picker on a move. */
  onMove: () => void;
  /**
   * Opens it on a copy. Optional because folders cannot be copied — there is no
   * folder-copy endpoint — so a folder card passes only `onMove`.
   */
  onCopyTo?: () => void;
  onDelete: () => Promise<unknown>;
}

/**
 * Every per-item action, behind one button — a row's `⋯`.
 *
 * Each row used to carry its controls as a strip of icons — rename, copy,
 * delete — and adding move would have made four, on every folder card and every
 * file row, permanently, next to a name that is usually a forty-character
 * timestamp. The strip was reading as more chrome than content. So the actions
 * collapse into one trigger, and what a row shows at rest is the thing it names.
 *
 * **What is left here is the list; `ActionMenu` is the menu.** The two items
 * that behave unusually are its features rather than this file's: `keepOpen`
 * for Copy, whose entire feedback is its own label changing to "Copied" — a
 * menu that closed would take the confirmation with it — and `danger` for
 * Delete, which arms in place and fires on the second press. This file used to
 * carry both by hand, alongside three other menus that carried them by hand
 * differently.
 *
 * It stays a browse-page control because a menu is the answer to "four icons on
 * every row", which is a listing's problem and not the object screen's — that
 * screen has one file and room to name its actions.
 */
export function ItemActions({
  name,
  copyValue,
  copyNoun = "path",
  onRename,
  onMove,
  onCopyTo,
  onDelete,
}: Props) {
  const { status, copy } = useCopyToClipboard();

  const actions: MenuAction[] = [
    {
      key: "rename",
      label: "Rename…",
      icon: <PencilIcon className={GLYPH} />,
      onSelect: onRename,
    },
    {
      key: "move",
      label: "Move…",
      icon: <FolderIntoIcon className={GLYPH} />,
      onSelect: onMove,
    },
    // "Copy to…" rather than "Copy", because the line below it copies the path
    // to the clipboard and the two must not read as the same thing.
    ...(onCopyTo
      ? [
          {
            key: "copy-to",
            label: "Copy to…",
            icon: <CopyIcon className={GLYPH} />,
            onSelect: onCopyTo,
          },
        ]
      : []),
    {
      key: "copy-path",
      label: copyLabel(status, `Copy ${copyNoun}`),
      icon: <ClipboardIcon className={GLYPH} />,
      keepOpen: true,
      onSelect: () => void copy(copyValue),
    },
    {
      key: "delete",
      label: "Delete",
      armedLabel: `Confirm — delete ${name}`,
      icon: <TrashIcon className={GLYPH} />,
      danger: true,
      arm: true,
      onSelect: onDelete,
    },
  ];

  return <ActionMenu label={name} triggerLabel={`Actions for ${name}`} actions={actions} />;
}
