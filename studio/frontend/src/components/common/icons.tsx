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

/**
 * A framed picture — the Media half of the file browser's view switch.
 *
 * `FileIcon` was the obvious reuse and is the wrong glyph: the switch's whole
 * job is "the tree, or the pictures in it", and a document beside a folder
 * reads as a second kind of tree rather than as its opposite.
 */
export const ImageIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <circle cx="8.5" cy="10" r="1.5" />
    <path d="m21 16-5-5-6 6-2-2-5 5" />
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

/**
 * The heart, in the two states a favorite has.
 *
 * **Two glyphs rather than one with a fill toggle**, because the default frame
 * is `fill-none stroke-current` and a filled heart wants the opposite pair. A
 * caller that passed `fill-current` to the outline would get a filled shape
 * with a stroke half a pixel outside it, which is visibly a different size from
 * the empty one — and a control that changes size when pressed is one people
 * press again to check.
 */
export const HeartIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M12 20s-7.5-4.35-7.5-9.75A4.25 4.25 0 0 1 12 7.5a4.25 4.25 0 0 1 7.5 2.75C19.5 15.65 12 20 12 20Z" />
  </Glyph>
);

export const HeartFilledIcon = ({
  className = "size-5 fill-current stroke-none",
}: Props) => (
  <Glyph className={className}>
    <path d="M12 20s-7.5-4.35-7.5-9.75A4.25 4.25 0 0 1 12 7.5a4.25 4.25 0 0 1 7.5 2.75C19.5 15.65 12 20 12 20Z" />
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

// --- the shell -------------------------------------------------------------

export const HomeIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M3 11.5 12 4l9 7.5V20H3Z" />
  </Glyph>
);

/** A board with a header row and a first column — a project is a table of runs. */
export const ProjectsIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <rect x="3" y="5" width="18" height="14" />
    <path d="M3 10h18M9 5v14" />
  </Glyph>
);

/** A sheet with two ruled lines: a template is text with holes in it. */
export const TemplateIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M4 4h16v16H4Z" />
    <path d="M8 9.5h8M8 13.5h8" />
  </Glyph>
);

/** Three bars. The one glyph a phone user reads as "the menu". */
export const MenuIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Glyph>
);

/** A panel with its left rail drawn — the sidebar's own toggle. */
export const SidebarIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <rect x="3" y="5" width="18" height="14" />
    <path d="M9 5v14" />
    <path d="m16.5 9.5-2.5 2.5 2.5 2.5" />
  </Glyph>
);

/**
 * A person in a ring — the ACCOUNT, as distinct from `AccountIcon`, which the
 * Characters section wears. Two person glyphs in one 64px rail have to differ,
 * and the ring is what says "you" rather than "them".
 */
export const ProfileIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <circle cx="12" cy="12" r="9" />
    <circle cx="12" cy="10" r="3" />
    <path d="M6.5 18.5a6 6 0 0 1 11 0" />
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

// --- the run feed and the opened run -------------------------------------

/**
 * A cog: settings — the project's Settings tab, and the create sheet's gear
 * on a phone. It was a circle with eight rays, which reads as a sun; a gear
 * has teeth, and ElevenLabs' is this one.
 */
export const SettingsIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
    <circle cx="12" cy="12" r="3" />
  </Glyph>
);

/** Run again — the same payload as a fresh attempt. */
export const RerunIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M19 12a7 7 0 1 1-2.1-5" />
    <path d="M19 4v4.5h-4.5" />
  </Glyph>
);

/** Enlarge and restore — the arrows leave the frame at both corners. */
export const UpscaleIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M4 20l6-6M4 14v6h6" />
    <path d="M20 4l-6 6M14 4h6v6" />
  </Glyph>
);

/** Put this picture into the create bar. */
export const UseInPromptIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <rect x="4" y="4" width="16" height="16" />
    <path d="M12 8v8M8 12h8" />
  </Glyph>
);

/** File an output as a character's identity. */
export const PromoteIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <circle cx="9" cy="8" r="3.5" />
    <path d="M3 20a6 6 0 0 1 12 0" />
    <path d="M18 8v6M15 11h6" />
  </Glyph>
);

/** A start frame — the first frame of a clip. */
export const StartFrameIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <rect x="4" y="5" width="16" height="14" />
    <path d="M4 9h16" />
  </Glyph>
);

export const ChevronLeftIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="m14.5 6-6 6 6 6" />
  </Glyph>
);

export const ChevronRightIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="m9.5 6 6 6-6 6" />
  </Glyph>
);

// --- the create bar ----------------------------------------------------------

/** A film frame: the VIDEO half of the kind switch. */
export const VideoIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <rect x="3" y="5" width="18" height="14" />
    <path d="M3 10h18M3 14h18M8 5v14M16 5v14" />
  </Glyph>
);

/** Two sliders: the parameters behind the bar. */
export const SlidersIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M3 7h18M3 17h18" />
    <circle cx="8" cy="7" r="2.5" />
    <circle cx="16" cy="17" r="2.5" />
  </Glyph>
);

/** An arrow leaving: Send. */
export const SendIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M4 12h15M13 6l6 6-6 6" />
  </Glyph>
);

/** An eye: the preview. */
export const EyeIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12Z" />
    <circle cx="12" cy="12" r="3" />
  </Glyph>
);

/** A padlock: keep the attached images for the next send. */
export const LockIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <rect x="5" y="11" width="14" height="10" />
    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
  </Glyph>
);

/** A person: a reference image, and a character with no picture yet. */
export const PersonIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21a8 8 0 0 1 16 0" />
  </Glyph>
);

/** A frame with its bottom bar: the end frame of a clip. */
export const FrameEndIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <rect x="3" y="5" width="18" height="14" />
    <path d="M3 15h18" />
  </Glyph>
);

// --- the create panel's chip row ------------------------------------------
//
// ElevenLabs' runner names each setting with a glyph and a value and no word
// (`▭ 16:9`, `⤢ 720p`, `◷ 4s`). These are those glyphs; the word is the
// control's `aria-label`.

/** A wide rectangle: the aspect ratio. */
export const AspectIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <rect x="3" y="7" width="18" height="10" rx="1.5" />
  </Glyph>
);

/** Two arrows pushing a corner out: resolution. */
export const ResolutionIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M14 4h6v6M4 20l7-7M20 4l-7 7M4 14v6h6" />
  </Glyph>
);

/** A clock face: a clip's duration. */
export const ClockIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </Glyph>
);

/** A diamond: quality. */
export const DiamondIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M12 3l9 8-9 10-9-10 9-8Z" />
    <path d="M3 11h18" />
  </Glyph>
);

/** Three stacked sheets: how many outputs. */
export const LayersIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="m12 4 8 4-8 4-8-4 8-4Z" />
    <path d="m4 12 8 4 8-4M4 16l8 4 8-4" />
  </Glyph>
);

/** Four cells: the model — a registry entry, one of a set. */
export const ModelIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <rect x="4" y="4" width="7" height="7" rx="1.5" />
    <rect x="13" y="4" width="7" height="7" rx="1.5" />
    <rect x="4" y="13" width="7" height="7" rx="1.5" />
    <rect x="13" y="13" width="7" height="7" rx="1.5" />
  </Glyph>
);

/** A picture with a plus: attach a reference. */
export const ImagePlusIcon = ({ className }: Props) => (
  <Glyph className={className}>
    <path d="M14 5H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-6" />
    <circle cx="8.5" cy="10" r="1.5" />
    <path d="m21 16-5-5-6 6-2-2-5 5M18 3v6M15 6h6" />
  </Glyph>
);
