import type { ReactNode } from "react";

/**
 * Every icon studio draws, in one place.
 *
 * **The design system ships none**, deliberately — it takes icons as slot props
 * and leaves the set to the consumer. So each of these was drawn at its call
 * site, sixteen times across fourteen files, with the same `viewBox`, the same
 * round joins and the same `stroke-[1.5]` retyped each time. The folder glyph
 * had three copies and the tick two, which is how two of them ended up at
 * different stroke weights.
 *
 * **`className` REPLACES the default rather than merging with it.** Tailwind
 * has no cascade to rely on here: `stroke-current` and `stroke-muted` set the
 * same property, so which one wins is decided by their order in the generated
 * stylesheet and not by their order in the attribute. A caller that wants a
 * muted, shrink-proof icon passes the whole string and gets exactly that. The
 * default covers the common case and nothing has to be un-set.
 */
const DEFAULT = "size-5 fill-none stroke-current stroke-[1.5]";

interface Props {
  className?: string;
}

/**
 * The shared frame: the box, the joins, and hidden from the accessibility tree.
 *
 * `aria-hidden` on all of them without exception. Every icon in this app sits
 * inside a control that carries its own label — the same rule that makes a
 * thumbnail's `alt` empty — and an icon that announces itself competes with
 * that label rather than adding to it.
 */
function Glyph({ className = DEFAULT, children }: Props & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {children}
    </svg>
  );
}

// --- the file tree ---------------------------------------------------------

export const FolderIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
  </Glyph>
);

/** A bare plus. What "make one of these" looks like above a list. */
export const PlusIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M12 5v14M5 12h14" />
  </Glyph>
);

/** A folder with something going into it. The arrow is what says which way. */
export const FolderIntoIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M2 9V7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-1" />
    <path d="M2 13h9" />
    <path d="m8 16 3-3-3-3" />
  </Glyph>
);

export const FileIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
    <path d="M14 3v5h5" />
  </Glyph>
);

// --- actions ---------------------------------------------------------------

/** Two sheets, one behind the other: the source stays. That is the whole difference from a move. */
export const CopyIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <rect x="9" y="9" width="12" height="12" rx="2" />
    <path d="M6 15H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1" />
  </Glyph>
);

export const ClipboardIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M9.5 8.5h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1Z" />
    <path d="M15 5.5v-1a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h1" />
  </Glyph>
);

export const PencilIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M4 20h4l10-10a2.83 2.83 0 1 0-4-4L4 16Z" />
    <path d="M13.5 6.5 17.5 10.5" />
  </Glyph>
);

export const TrashIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M4 7h16" />
    <path d="M10 11v6m4-6v6" />
    <path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12" />
    <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </Glyph>
);

/** Armed delete. The icon has to say this press is not the same as the last one. */
export const QuestionIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M9.5 9a2.5 2.5 0 1 1 3 2.45V13" />
    <path d="M12 16.5v.01" />
    <circle cx="12" cy="12" r="9" />
  </Glyph>
);

export const DownloadIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 19h16" />
  </Glyph>
);

export const CheckIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="m5 12.5 5 5L19 7" />
  </Glyph>
);

export const WarningIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M12 4 2.5 20.5h19L12 4Z" />
    <path d="M12 10v4.5" />
    <path d="M12 17.5v.01" />
  </Glyph>
);

export const CloseIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Glyph>
);

export const ArrowUpIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M12 19V5m0 0-6 6m6-6 6 6" />
  </Glyph>
);

export const ArrowDownIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M12 5v14m0 0-6-6m6 6 6-6" />
  </Glyph>
);

export const ChevronDownIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="m6 9 6 6 6-6" />
  </Glyph>
);

/** Filled, not stroked — three dots read as blobs at this size or not at all. */
export const DotsIcon = ({ className = "size-5 fill-current stroke-none" }: Props) => (
  <Glyph className={className}>
    <circle cx="5" cy="12" r="1.6" />
    <circle cx="12" cy="12" r="1.6" />
    <circle cx="19" cy="12" r="1.6" />
  </Glyph>
);

export const SearchIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="m20 20-4.35-4.35" />
  </Glyph>
);

export const AccountIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <circle cx="12" cy="8" r="3.5" />
    <path d="M4.5 20a7.5 7.5 0 0 1 15 0" />
  </Glyph>
);

// --- the viewer ------------------------------------------------------------

export const SoundOnIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M11 5 6 9H3v6h3l5 4Z" />
    <path d="M15.5 8.5a5 5 0 0 1 0 7M18 6a9 9 0 0 1 0 12" />
  </Glyph>
);

export const SoundOffIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M11 5 6 9H3v6h3l5 4Z" />
    <path d="m16 9 5 6m0-6-5 6" />
  </Glyph>
);

export const FullscreenEnterIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M3 9V3h6M21 9V3h-6M3 15v6h6m12-6v6h-6" />
  </Glyph>
);

export const FullscreenExitIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M9 3v6H3m12-6v6h6M9 21v-6H3m12 6v-6h6" />
  </Glyph>
);

// --- transport -------------------------------------------------------------

export const SeekBackIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M11 7 6 12l5 5" />
    <path d="M18 7l-5 5 5 5" />
  </Glyph>
);

export const SeekForwardIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M13 7l5 5-5 5" />
    <path d="M6 7l5 5-5 5" />
  </Glyph>
);

export const PlayIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M8 5v14l11-7Z" />
  </Glyph>
);

export const PauseIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M9 5v14M15 5v14" />
  </Glyph>
);
