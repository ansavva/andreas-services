import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Button, useToast } from "@ansavva/design-system";

import { submitRun } from "../../apis/studio";
import { copyLabel, useCopyToClipboard } from "../../hooks/useCopyToClipboard";
import type { RunFeedRow } from "../../types";
import { absoluteUrl, runPath } from "../../utils/location";
import { ActionMenu, type MenuAction } from "../common/ActionMenu";
import { ApertureSpinner } from "../common/Aperture";
import {
  ClipboardIcon,
  FileIcon,
  FolderIcon,
  FolderIntoIcon,
  FolderPlusIcon,
  LinkIcon,
  OpenIcon,
  PencilIcon,
  RefreshIcon,
  RerunIcon,
  TrashIcon,
  VideoIcon,
} from "../common/icons";
import { ArmedButton } from "./ArmedButton";
import { inFlight } from "./feedTime";
import { MoveRunDialog } from "./MoveRunDialog";
import type { useRunActions } from "./useRunActions";

const GLYPH = "size-4 shrink-0 fill-none stroke-current stroke-[1.5]";

/**
 * The header this row sits in is a `@container`. Below 30rem it is a phone's
 * feed column or the opened run's 360px rail, and the header gives two
 * things up to keep the three controls on the badges' line: Edit's word
 * (here) and the meta's place on that line (`RunFeed`, `RunLightbox` — it
 * takes its own line below). Written out in full at each site, because
 * Tailwind finds classes by scanning source text.
 */

/**
 * What a run can do: two buttons and a menu.
 *
 * **The two a person reaches for, and everything else behind `⋯`.** The feed
 * row drew eight controls in a wrapping line — Open, Rerun, Edit, Refresh,
 * Folder, Delete, More — and the opened run's rail drew a list of twelve; on
 * a phone the row wrapped to three lines of pills, and on both surfaces the
 * one that spends sat between the one that navigates and the one that
 * destroys, all the same size and the same grey. Now the row is the money
 * gesture (Run on a draft, Rerun on anything finished — the armed two-press,
 * and the press is the act, no approve step anywhere), Edit, and a `⋯`
 * holding the rest; a run in flight has Edit and the menu, nothing that
 * spends or destroys.
 *
 * **One row for both surfaces**, the way `useRunActions` is one set of
 * actions for both: the feed and the rail had each grown their own version
 * of Refresh, Folder and Delete, and they disagreed on the delete's word.
 * The rail's output lines — Use as, This frame as, Upscale, Copy into a
 * character, Download — are about the picture on its stage, so the rail
 * passes them in as `leading` and they open the menu; the feed's tiles
 * carry those on their own `⋮`.
 *
 * **Delete is in the menu, and still arms.** `ActionMenu` keeps one arming
 * line open across its first press, so the second press is still a second
 * press, and Escape or a wander away disarms it — the same `useArmed` the
 * button was.
 */
export function RunActionRow({
  row,
  actions,
  onOpen,
  leading = [],
  folderHref,
  sceneHref,
  className = "",
}: {
  row: RunFeedRow;
  actions: ReturnType<typeof useRunActions>;
  /** Open the run, when this row is not already on it. */
  onOpen?: () => void;
  /** Lines the menu opens with, before the run's own. */
  leading?: readonly MenuAction[];
  /** The run's files. The feed and the rail know this differently — see `useRunActions.folderHref`. */
  folderHref: string | null;
  /** The scene this run is made for, when the surface can say. */
  sceneHref?: string | null;
  className?: string;
}) {
  const client = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const flying = inFlight(row.status);
  const draft = row.status === "draft";
  const link = useCopyToClipboard();
  const [moving, setMoving] = useState(false);

  const run = useCallback(async () => {
    try {
      await submitRun(row.id);
    } catch (err) {
      toast.add({
        intent: "danger",
        title: "Could not submit the run",
        description: (err as Error).message,
      });
    }
    await client.invalidateQueries({ queryKey: ["runs"] });
  }, [client, row.id, toast]);

  const menu: MenuAction[] = [
    ...leading,
    ...(onOpen
      ? [
          {
            key: "open",
            label: "Open",
            icon: <OpenIcon className={GLYPH} />,
            onSelect: onOpen,
          },
        ]
      : []),
    // Re-reads the record and the feed's row for it — `useRunActions.refresh`.
    // On every run: the poll stops at a terminal status, and the one wedged
    // short of it is the one this is for.
    {
      key: "refresh",
      label: actions.refreshing ? "Refreshing…" : "Refresh",
      icon: actions.refreshing ? (
        <ApertureSpinner size="sm" label="Refreshing" className="size-4" />
      ) : (
        <RefreshIcon className={GLYPH} />
      ),
      disabled: actions.refreshing,
      onSelect: () => void actions.refresh(),
    },
    ...(folderHref && !flying
      ? [
          {
            key: "folder",
            label: "Folder",
            icon: <FolderIcon className={GLYPH} />,
            onSelect: () => navigate(folderHref),
          },
        ]
      : []),
    // The scene this run belongs to, when it does. One line, not a list: a
    // run is made for at most one scene.
    ...(sceneHref
      ? [
          {
            key: "scene",
            label: "Scene",
            icon: <VideoIcon className={GLYPH} />,
            onSelect: () => navigate(sceneHref),
          },
        ]
      : []),
    {
      key: "copy-prompt",
      label: "Copy prompt",
      icon: <ClipboardIcon className={GLYPH} />,
      disabled: !row.plan,
      reason: row.plan ? undefined : "This run predates the plan.",
      onSelect: actions.copyPrompt,
    },
    // The run's own address, `/p/<project>/r/<run>` — the lightbox over the
    // feed, which is where a pasted link should land whether it was copied
    // from the feed row or from the opened run's rail. The bare address, not
    // the address bar: the feed's filters are the copier's, not the run's.
    {
      key: "copy-link",
      label: copyLabel(link.status, "Copy link"),
      icon: <LinkIcon className={GLYPH} />,
      keepOpen: true,
      onSelect: () => void link.copy(absoluteUrl(runPath(row.project, row.id))),
    },
    {
      key: "request",
      label: "Open request documents",
      icon: <FileIcon className={GLYPH} />,
      onSelect: actions.openRequest,
    },
    ...(actions.canAddToCut
      ? [
          {
            key: "add-to-cut",
            label: "Add to the cut",
            icon: <FolderPlusIcon className={GLYPH} />,
            onSelect: () => void actions.addToCut(),
          },
        ]
      : []),
    // Into another project. A dialog, because a choice comes first —
    // `MoveRunDialog` says what goes with the run and what it leaves.
    ...(!flying
      ? [
          {
            key: "move",
            label: "Move to project…",
            icon: <FolderIntoIcon className={GLYPH} />,
            onSelect: () => setMoving(true),
          },
        ]
      : []),
    ...(!flying
      ? [
          {
            key: "delete",
            label: "Delete",
            armedLabel: "Confirm — delete this run",
            icon: <TrashIcon className={GLYPH} />,
            danger: true,
            arm: true,
            onSelect: actions.remove,
          },
        ]
      : []),
  ];

  return (
    <div className={`flex items-center gap-1 ${className}`}>
      {/* Edit first and quiet; the money gesture filled, the one strong
          thing on the row; the menu last. */}
      {/* The word only where the header is wide enough for it — under 30rem
          the pencil stands alone, so the three controls fit beside the
          badges on one line at 320px. */}
      <Button intent="ghost" size="sm" aria-label="Edit" onClick={actions.edit} className="">
        <PencilIcon className={GLYPH} />
        <span className="hidden @min-[30rem]:inline">Edit</span>
      </Button>
      {draft && (
        <ArmedButton
          idle="Run"
          armed="Press again — this spends"
          busy="Running…"
          tooltip={`Sends the prompt, the parameters and the ${row.sends.length} image${
            row.sends.length === 1 ? "" : "s"
          } above, in that order. Sends it and starts billing.`}
          onFire={run}
          icon={<RerunIcon className={GLYPH} />}
        />
      )}
      {!draft && !flying && (
        <ArmedButton
          idle="Rerun"
          armed="Press again — this spends"
          busy="Running…"
          tooltip="Runs the same prompt, parameters and images as a new attempt. This one keeps its outputs."
          onFire={actions.rerun}
          icon={<RerunIcon className={GLYPH} />}
        />
      )}
      <ActionMenu label="This run" triggerLabel="More actions for this run" actions={menu} />
      {moving && <MoveRunDialog row={row} onClose={() => setMoving(false)} />}
    </div>
  );
}
