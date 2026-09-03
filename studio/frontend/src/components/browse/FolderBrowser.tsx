import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  Alert,
  Breadcrumbs,
  Button,
  Input,
  Text,
  Toggle,
  ToggleGroup,
  useToast,
} from "@ansavva/design-system";

import {
  copyNodes,
  createNode,
  deleteNodes,
  moveNodes,
  renameNode,
} from "../../apis/studio";
import { EmptyState } from "../common/EmptyState";
import { LoadError } from "../common/LoadError";
import { PageLoading } from "../common/PageLoading";
import { useFolder } from "../../hooks/useFolder";
import { useSearchParamState } from "../../hooks/useSearchParamState";
import { useSelection } from "../../hooks/useSelection";
import { useUploads } from "../../hooks/useUploads";
import type { EntryKind, FileEntry, SortOrder } from "../../types";
import { MEDIA_GRID } from "../../utils/grid";
import type { FolderId } from "../../utils/location";
import { ConfirmDeleteButton } from "../common/ConfirmDeleteButton";
import { CopyKeyButton } from "../common/CopyKeyButton";
import { DestinationPicker } from "./DestinationPicker";
import { FileRow } from "./FileRow";
import {
  FilterControl,
  folderMatchesFilter,
  matchesFilter,
} from "./FilterControl";
import { FolderCard } from "./FolderCard";
import { MediaTile } from "./MediaTile";
import { SortControl } from "./SortControl";
import { TagFilter } from "./TagFilter";
import { UploadButton } from "./UploadButton";
import { UploadStatus } from "./UploadStatus";
import { CopyIcon, FolderIntoIcon, FolderPlusIcon } from "../common/icons";
import { BULK_GATE, ConfirmDestroyDialog } from "../common/ConfirmDestroyDialog";

/**
 * How the browser is addressed, supplied by whoever is showing it.
 *
 * **The browser has two callers with genuinely different address spaces**, which
 * is why this is an interface rather than the browser reaching for the router
 * itself. On `/f/` and `/o/` the URL *is* the state: it has to be, or browser
 * back and a pasted link disagree, and both have to work for a share link to
 * mean anything. Inside a character's or a project's Files tab there is no URL
 * to spend — the address bar names the entity, and navigating a subfolder must
 * not replace the page you are standing on — so the same component is driven by
 * component state. Neither is a special case of the other, and threading a
 * boolean through would put a branch in every handler.
 */
export interface BrowserNav {
  /** The folder on screen. A file open over it is a different screen now. */
  folder: FolderId;
  sort: SortOrder;
  setSort: (next: SortOrder) => void;
  /** `replace` is for the one move that is not a journey — leaving a deleted folder. */
  goToFolder: (id: FolderId, options?: { replace?: boolean }) => void;
  /**
   * Opens the viewer at this file, with this browser as its context.
   *
   * **`deep` is what the listing on screen actually was, and it is not
   * cosmetic.** A context of `f:<folder>` makes the viewer re-read that folder
   * one level down to find the file's neighbours — which is right for a readdir
   * and wrong for every listing that searched the branch. A tile in the Media
   * view, or under a tag filter, is usually in some *sub*folder, so the feed
   * came back without it: the viewer showed "No images or videos here", or
   * silently opened whatever was first in the folder instead. Deep listings say
   * so, and the nav encodes the recursive context that holds them.
   */
  openFile: (file: FileEntry, deep?: boolean) => void;
  /**
   * The same destination as `openFile`, as an address rather than an act.
   *
   * Both exist because a tile needs both: an `href` so the browser can offer
   * its own new-tab, new-window and copy-address gestures, and a handler so a
   * plain click stays a client-side navigation instead of a page load.
   */
  fileHref: (file: FileEntry, deep?: boolean) => string;
}

interface Props {
  nav: BrowserNav;
  /**
   * The folder this browser may not climb above.
   *
   * `null` — the library root — for the standalone browser, and an entity's
   * `root` node id inside a Files tab. It trims the breadcrumb trail and
   * disables Back at the top, so a character's Files tab is a browser *of that
   * character* rather than a view of the whole library that happens to start
   * there. It is presentation only: the API is scoped by library membership, not
   * by this.
   */
  boundary?: FolderId;
  /**
   * What to call the boundary crumb, when its stored name is not worth showing.
   *
   * An entity's root folder is **named by the entity id** — `char-<uuid>` — so
   * that two characters called the same thing do not collide on the folder
   * tree's own name uniqueness. That is the right stored name and the wrong
   * label: a Files tab drew a 41-character UUID as the first crumb, which
   * wrapped onto two lines at 390px and named nothing a person recognises.
   *
   * Display only, and only the first crumb. `prefix` — what Copy prefix yields
   * and what `GET /api/resolve` takes — is still built from stored names, so
   * the address does not change because the label did.
   */
  boundaryLabel?: string;
  /**
   * Which view this browser opens on — see `MEDIA_VIEW`.
   *
   * `folders` everywhere a person is browsing *files*. `media` where the whole
   * point of the screen is the pictures: a project's Runs tab in Grid, which is
   * this browser scoped to `runs/`.
   */
  defaultView?: string;
  /**
   * The query parameter the view rides in, and the one `folder` rides in beside
   * it (`<viewParam>Folder`).
   *
   * **Both are named because two browsers can share a page.** A project draws
   * one under Files and another under Runs, and with one key between them
   * switching tabs would carry a folder id from one subtree into the other —
   * a browser standing somewhere it cannot show.
   */
  viewParam?: string;
}

/**
 * What the destination picker is open on.
 *
 * **One shape, where there used to be two.** A folder and a set of files needed
 * different endpoints while a folder's address was a prefix and a file's was a
 * key — the two counted different things and refused for different reasons. They
 * are all node ids now, so a mixed selection is one call and this is one branch
 * fewer.
 *
 * `verb` rides along rather than being separate state so the two cannot drift:
 * there is no way to have a picker open with no operation chosen, or to close
 * one and leave a stale verb behind for the next.
 */
const VIEW_FOLDERS = "folders";
const VIEW_MEDIA = "media";

/**
 * What the Media view asks the listing for.
 *
 * `image,video` — which, because `getFolder` sends any `kind` filter with
 * `depth=all`, is also what turns this from a readdir into a search of the whole
 * subtree. That is the point of it: "every picture of this character" is not a
 * question about the folder you happen to be standing in, and answering it by
 * walking `reference/`, `corpus/`, `seed/` and `archive/` in turn is the thing
 * the view exists to stop.
 *
 * Folders and text drop out of the result, so the two sections that draw them
 * render nothing on their own — there is no `view` branch anywhere below.
 */
const MEDIA_VIEW: EntryKind[] = ["image", "video"];

type PickerTarget = {
  verb: "move" | "copy";
  ids: string[];
  noun: string;
  /** Set when a *folder* is moving: it cannot land inside itself. */
  forbiddenId?: string;
};

/**
 * The file layer, whole: listing, selection, upload, text page, and every
 * write a person can make.
 *
 * This was the body of `BrowsePage` and is a component so that a character's and
 * a project's **Files** tab is the same browser rather than a second one that
 * drifts. Nothing about its behaviour changed in the entity rework except the
 * addresses it writes with: every write here takes node ids, where the nine
 * name-path routes it used to call took a slash-joined path that a rename
 * invalidated mid-flight.
 */
export function FolderBrowser({
  nav,
  boundary = null,
  boundaryLabel,
  defaultView = VIEW_FOLDERS,
  viewParam = "view",
}: Props) {
  const { folder, sort } = nav;

  const [actionError, setActionError] = useState<string | null>(null);
  const [newFolder, setNewFolder] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  /**
   * The tags narrowing the listing — a SERVER filter, unlike `filter` above.
   *
   * The name filter hides rows the listing already returned; a tag filter
   * changes what is asked for, and changes the scope with it: one tag turns the
   * request into a search of everything under this folder. They compose, and the
   * order is the honest one — the server narrows, then the typed name hides.
   */
  const [tags, setTags] = useState<string[]>([]);
  /**
   * Folders, or every picture and clip beneath here — see `MEDIA_VIEW`.
   *
   * In the URL rather than in component state, so it is linkable and so it
   * survives leaving a Files tab and coming back. It rides beside `?folder=`,
   * which means the two compose: a chip narrows *where*, this narrows *what*.
   */
  const [view, setView] = useSearchParamState(viewParam, defaultView);
  const [pickerTarget, setPickerTarget] = useState<PickerTarget | null>(null);

  /**
   * The listing, straight from the folder the caller names.
   *
   * `useFolder` used to sit here resolving an *object* address to its parent,
   * because `/o/<id>` rendered this component with the file open over it. The
   * viewer is its own screen now, so this only ever shows a folder and the
   * resolution — and the request it cost on every cold link — is gone with it.
   */
  const { data, loading, error, reload } = useFolder(
    folder,
    sort,
    tags,
    view === VIEW_MEDIA ? MEDIA_VIEW : [],
  );
  const folderId = folder;

  /**
   * Whether what is on screen is a branch search rather than a readdir.
   *
   * **Read off the answer, not off the request.** `data.depth` is what the
   * server says it did, so this cannot drift from the listing the way a
   * `view === VIEW_MEDIA || tags.length > 0` recomputation here would — and it
   * covers both ways of going deep with one expression. It is what a tile hands
   * `openFile`; see `BrowserNav`.
   */
  const deep = data?.depth === "all";

  /**
   * The listing's own breadcrumbs are where every *path* on this page comes from.
   *
   * An id address carries no path, and the crumbs already do: the server walks
   * `parent_id` and hands back the trail with an id and a name path per level.
   *
   * **Trimmed at `boundary`**, which is what scopes a Files tab. The server has
   * no idea which entity a tab is showing — it returns the trail from the library
   * root — so the cut is made here, and made by *finding* the boundary rather
   * than by counting: a listing that has not landed, or a folder that somehow
   * sits outside it, falls back to the whole trail instead of showing an empty
   * one.
   */
  const allCrumbs = data?.breadcrumbs ?? [];
  const boundaryIndex =
    boundary === null ? 0 : allCrumbs.findIndex((c) => c.id === boundary);
  const crumbs = boundaryIndex > 0 ? allCrumbs.slice(boundaryIndex) : allCrumbs;

  /**
   * `prefix` is `null` until the listing lands, and it is not `""` — `""` is the
   * root, and "create this folder at the root" is not a safe reading of "we do
   * not know yet". Every control that writes is disabled while it is null.
   */
  const prefix = data?.prefix ?? null;
  const atRoot = crumbs.length <= 1;
  const parentId = crumbs.at(-2)?.id ?? null;
  const folderName = crumbs.at(-1)?.name ?? "";
  /** The folder on screen as a real node, which the root has and `folderId` does not. */
  const hereId = crumbs.at(-1)?.id ?? null;

  /**
   * The listing, narrowed by whatever is typed in the filter.
   *
   * Applied before the split so both sections narrow together, and before
   * `useSelection` sees the media — selecting all should select what is on
   * screen, not what a filter is hiding.
   */
  const files = useMemo(
    () => (data?.files ?? []).filter((file) => matchesFilter(file, filter)),
    [data, filter],
  );
  const media = useMemo(
    () =>
      files.filter((file) => file.kind === "image" || file.kind === "video"),
    [files],
  );
  const others = useMemo(
    () =>
      files.filter((file) => file.kind !== "image" && file.kind !== "video"),
    [files],
  );
  const folders = useMemo(
    () =>
      (data?.folders ?? []).filter((folder) =>
        folderMatchesFilter(folder, filter),
      ),
    [data, filter],
  );

  const goToFolder = useCallback(
    (nextId: FolderId, options?: { replace?: boolean }) => {
      setActionError(null);
      nav.goToFolder(nextId, options);
    },
    [nav],
  );

  /**
   * One selection over BOTH lists.
   *
   * The grid could be selected and acted on in bulk and the rows below it could
   * not, so deleting five `result.json` files was five trips through a per-row
   * menu — while deleting fifty images was two presses. It is one folder, so it
   * is one selection.
   *
   * Keyed on `files` rather than on either half, because `toggleAt` takes an
   * index and shift-click means "everything between" — a range that stopped at
   * the boundary between images and text would be a range that lies.
   */
  const selection = useSelection(files, folderId ?? null);

  /** Where each entry sits in the combined list, for the two renders that split it. */
  const indexOf = useMemo(
    () => new Map(files.map((file, index) => [file.id, index])),
    [files],
  );

  /**
   * Where an upload lands: the folder on screen, by its own node id.
   *
   * The **last breadcrumb**, not `folderId`. `folderId` is `null` at the library
   * root — the address has nothing to name there — and `POST /api/nodes` needs a
   * parent node. The root has one; the crumbs carry it. So this is `null` only
   * while the listing has not landed, exactly like `prefix`.
   */
  const uploads = useUploads(hereId, reload);
  const toast = useToast();

  /** "3 files", "1 key" — the count and its noun, agreeing about plurality. */
  const selectedNoun = useCallback(
    (one: string, many: string) =>
      `${selection.count} ${selection.count === 1 ? one : many}`,
    [selection.count],
  );

  /**
   * Every write funnels through here: run it, surface the message if it fails,
   * and re-fetch the listing if it succeeds.
   *
   * Re-fetching rather than patching local state is deliberate. A rename does
   * not just change a name — under `newest` it can change the item's *position*,
   * and under `name` it certainly does. Replaying that into a sorted array
   * correctly is more code than one request, and it is code that would be wrong
   * in exactly the cases nobody tests.
   */
  const run = useCallback(
    async <T,>(work: Promise<T>, { refresh = true } = {}): Promise<T> => {
      setActionError(null);
      try {
        const result = await work;
        if (refresh) reload();
        return result;
      } catch (err) {
        setActionError((err as Error).message);
        throw err;
      }
    },
    [reload],
  );

  /**
   * A delete leaves nothing behind to read — the listing refetches and the
   * row is simply not there — so the toast is the only record that it
   * happened rather than, say, the refresh dropping it.
   */
  const deleteSelected = useCallback(async () => {
    const noun = selectedNoun("file", "files");
    await run(deleteNodes(selection.selectedItems.map((item) => item.id)));
    selection.clear();
    toast.add({ intent: "success", title: `Deleted ${noun}` });
  }, [run, selectedNoun, selection, toast]);

  const deleteOne = useCallback(
    async (id: string, name: string) => {
      await run(deleteNodes([id]));
      toast.add({ intent: "success", title: `Deleted ${name}` });
    },
    [run, toast],
  );

  /**
   * The picker's submit, for whichever operation it was opened on.
   *
   * It deliberately does *not* close the picker — it closes itself on a resolved
   * promise and stays open with the message on a rejected one, which is the same
   * bargain `RenameForm` makes: "that name is taken there" is fixed by picking a
   * different folder, and closing to say so would throw away the navigating you
   * just did.
   */
  const submitPicker = useCallback(
    async (destination: string) => {
      if (!pickerTarget) return;
      // Unlike a move, a copy can land in the folder you are looking at — so
      // both re-fetch, which `run` does by default.
      if (pickerTarget.verb === "copy")
        await run(copyNodes(pickerTarget.ids, destination));
      else await run(moveNodes(pickerTarget.ids, destination));
      selection.clear();
    },
    [pickerTarget, run, selection],
  );

  /*
   * The writes that used to live here — rename, delete and describe for the
   * pane that was open over this listing — moved to `ViewerPage` with the
   * viewer itself. They were never about the folder; they acted on one node and
   * then had to reconcile a listing they happened to be rendered inside.
   */

  /**
   * Delete the folder you are standing in, then step up into its parent.
   *
   * The listing has a delete for every folder *except* this one, which would mean
   * emptying a run folder and then getting rid of it takes navigating back out to
   * find it in the grid — and for a folder arrived at by share link, out is
   * somewhere you have never been.
   *
   * It refuses to refresh on the way out. `run` re-fetches by default, and the
   * folder it would re-fetch is the one that has just stopped existing.
   *
   * Disabled at the top of the browser, which is also the one refusal the API
   * makes here: a folder that is some entity's `root` cannot be deleted while the
   * entity exists, and the message names the entity to delete instead.
   */
  const deleteCurrentFolder = useCallback(async () => {
    if (hereId === null) return;
    await run(deleteNodes([hereId]), { refresh: false });
    goToFolder(parentId, { replace: true });
  }, [goToFolder, hereId, parentId, run]);

  const submitNewFolder = useCallback(async () => {
    const name = (newFolder ?? "").trim();
    if (!name || hereId === null) {
      setNewFolder(null);
      return;
    }
    await run(createNode(hereId, name, "folder")).then(
      () => setNewFolder(null),
      () => undefined,
    );
  }, [hereId, newFolder, run]);

  // Escape drops the selection, but only when it is the frontmost thing. The
  // move picker binds Escape to its own close, and it is often open *on* the
  // selection — so clearing it there would be Escape cancelling the move by
  // emptying what was being moved. The reel and the text page used to be in
  // this list and are their own screen now, where this component is unmounted.
  const overlayOpen = pickerTarget !== null;
  useEffect(() => {
    if (overlayOpen || selection.count === 0) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") selection.clear();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [overlayOpen, selection]);

  /**
   * Drag-and-drop, which is the desktop convenience and never the mechanism.
   *
   * The file input is what has to work — it is the only picker a phone has — and
   * this is twelve lines on top of it. The counter is the whole subtlety:
   * `dragleave` fires every time the pointer crosses from one child element to
   * another, so a boolean toggled on it flickers the highlight off over every
   * tile on the page. Counting enter against leave is the standard fix.
   *
   * `onDragOver` must call `preventDefault` on *every* event, not just the first,
   * or the browser keeps its default handling and opens the dropped file as a
   * page — which navigates away from the app with no warning.
   */
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      dragDepth.current = 0;
      setDragging(false);
      const dropped = Array.from(event.dataTransfer.files ?? []);
      if (dropped.length > 0) void uploads.start(dropped);
    },
    [uploads],
  );

  const isEmpty =
    !loading &&
    !error &&
    data &&
    data.folders.length === 0 &&
    data.files.length === 0;

  // Empty because of the filter is a different sentence from empty because the
  // folder is: one is undone by clearing a box, the other is a fact about the
  // library. Saying "this folder is empty" over a folder holding sixty things
  // is the kind of wrong that makes someone go looking for a bug.
  const hiddenByFilter =
    !loading &&
    !error &&
    !isEmpty &&
    folders.length === 0 &&
    media.length === 0 &&
    others.length === 0;

  return (
    <div
      onDragEnter={(event) => {
        // A drag of selected text or a link carries no files; highlighting for
        // one would promise an upload that then does nothing.
        if (!event.dataTransfer.types.includes("Files")) return;
        dragDepth.current += 1;
        setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => {
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (dragDepth.current === 0) setDragging(false);
      }}
      onDrop={onDrop}
      className={`flex w-full flex-col gap-6 ${
        dragging
          ? "outline-2 outline-offset-[-8px] outline-dashed outline-primary"
          : ""
      }`}
    >
      {/*
        Two rows, not one.

        These are two different kinds of control and they used to share a line:
        where you are (back, breadcrumbs) and what you can do here (sort, copy the
        prefix, delete, new folder, play). On any real path the breadcrumbs took
        the width and the buttons wrapped underneath them anyway — in whatever
        order the flex run happened to break — so a folder deep in a project
        opened onto a bar that looked different from the one at the root.
      */}
      <div className="flex min-w-0 items-center gap-2">
        {/*
          Up one folder, not browser-back.
          They are different journeys and both are wanted: back retraces how you
          got here, which after a shared link is nowhere. This goes *up the tree*,
          which is where "back" means to someone reading a folder they were linked
          into — and it stops at the browser's boundary, so a character's Files
          tab cannot climb out of the character.
        */}
        <Button
          intent="secondary"
          size="sm"
          disabled={atRoot}
          aria-label="Up one folder"
          onClick={() => goToFolder(parentId)}
        >
          <span aria-hidden="true">←</span> Back
        </Button>

        {/* Breadcrumbs.Root carries `w-full` of its own, so it needs a shrinking
            flex parent or it claims the row and wraps what follows beneath it. */}
        <div className="min-w-0 flex-1">
          <Breadcrumbs.Root>
            {crumbs.map((crumb, index, all) => (
              <Breadcrumbs.Item
                key={crumb.id}
                current={index === all.length - 1}
                href="#"
                onClick={(event: React.MouseEvent) => {
                  event.preventDefault();
                  // The boundary crumb is the browser's own root, and inside a
                  // Files tab that is not the library root — so it is navigated
                  // to by id rather than by the `null` the standalone browser
                  // uses for the top.
                  goToFolder(
                    index === 0 && boundary === null ? null : crumb.id,
                  );
                }}
              >
                {/* See `boundaryLabel`: the entity's name in place of the id
                    its root folder is stored under. Only the first crumb, and
                    only inside a scoped browser — the standalone one's first
                    crumb is `/`. */}
                {index === 0 && boundary !== null && boundaryLabel
                  ? boundaryLabel
                  : crumb.name}
              </Breadcrumbs.Item>
            ))}
          </Breadcrumbs.Root>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-line py-2">
        {/*
          **Two views of one folder, and the pair is the whole control.**

          Folders is the readdir this has always been. Media is every image and
          clip *beneath* here, flat and newest-first — the same shape the tag
          filter already produces, which is why it needed no second component to
          draw it.

          Single-select, and empty is refused: `ToggleGroup` lets the pressed
          member be unpressed, and a browser showing neither view is not a
          state — it is the listing gone blank with no way to say why.
        */}
        <ToggleGroup.Root
          aria-label="View"
          value={[view === VIEW_MEDIA ? VIEW_MEDIA : VIEW_FOLDERS]}
          onValueChange={(next) => {
            if (next.length > 0) setView(next[0]!);
          }}
        >
          <Toggle value={VIEW_FOLDERS}>Folders</Toggle>
          <Toggle value={VIEW_MEDIA}>Media</Toggle>
        </ToggleGroup.Root>

        <SortControl value={sort} onChange={nav.setSort} />
        <FilterControl
          value={filter}
          onChange={setFilter}
          total={(data?.folders.length ?? 0) + (data?.files.length ?? 0)}
        />

        <div className="flex-1" />

        {/*
          One cluster of three icons, then the primary.

          All three act on the folder you are in — copy its prefix, delete it,
          make one inside it — so they read as a set. The divider is doing real
          work rather than decorating: Upload is the one button on the far side
          of it, and a delete sitting flush against a control a person arrives
          looking for is a mis-click with no undo, so the destructive icon stays
          in the middle of its own cluster and a rule separates the two. Do not
          close that gap.
        */}
        <div className="flex shrink-0 items-center gap-0.5">
          {/* Still the *name path*, and still worth copying even though nothing
              is addressed by one any more: it is what a person types at the CLI,
              which resolves it through `GET /api/resolve`. */}
          <CopyKeyButton value={prefix ?? ""} noun="prefix" />

          <ConfirmDeleteButton
            tone="icon"
            disabled={atRoot || hereId === null}
            noun={atRoot ? "this folder" : folderName}
            onConfirm={deleteCurrentFolder}
          />

          {/* An icon, like the two beside it: "New folder" is a noun-shaped
              action with an icon everyone already knows, and spelling it out
              made it the widest thing in the row. The label lives on
              `aria-label` and `title`. */}
          <button
            type="button"
            onClick={() => setNewFolder("")}
            disabled={hereId === null}
            aria-label="New folder"
            title="New folder"
            className="shrink-0 rounded-none p-2 text-muted transition-colors hover:bg-surface-alt hover:text-ink
                       disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent
                       focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <FolderPlusIcon />
          </button>
        </div>

        <div aria-hidden="true" className="mx-1 h-6 w-px shrink-0 bg-line" />

        {/*
          Upload, on the other side of the divider from the destructive cluster.

          It is labelled where its three neighbours are icons, because there is no
          icon everyone reads as "put a file here" — the tray-with-an-arrow means
          upload, download and share depending on the platform — and this is the
          one control a person arrives *looking* for.
        */}
        <UploadButton onFiles={uploads.start} disabled={hereId === null} />

        {files.length > 0 && (
          <Button
            intent="secondary"
            size="sm"
            onClick={
              selection.count > 0 ? selection.clear : selection.selectAll
            }
          >
            {selection.count > 0 ? "Select none" : "Select all"}
          </Button>
        )}
      </div>

      <div className="border-b border-line pb-2">
        <TagFilter value={tags} onChange={setTags} searching={data?.depth === "all"} />
      </div>

      {newFolder !== null && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void submitNewFolder();
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") setNewFolder(null);
          }}
          aria-label="New folder"
          className="flex flex-wrap items-center gap-2 rounded-none border border-line bg-card p-3"
        >
          <Text variant="caption" tone="muted">
            New folder in {prefix ?? "…"}
          </Text>
          <div className="min-w-48 flex-1">
            <Input
              value={newFolder}
              onValueChange={setNewFolder}
              placeholder="folder name"
            />
          </div>
          <Button type="submit" size="sm">
            Create
          </Button>
          <Button
            type="button"
            intent="secondary"
            size="sm"
            onClick={() => setNewFolder(null)}
          >
            Cancel
          </Button>
        </form>
      )}

      {/* Above the listing rather than over it: an upload is something you
          started and then keep browsing through, and a floating panel would
          cover the grid it is filling. */}
      <UploadStatus
        items={uploads.items}
        onClearFinished={uploads.clearFinished}
      />

      {actionError && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not update this folder</Alert.Title>
          <Alert.Description>{actionError}</Alert.Description>
        </Alert.Root>
      )}

      {loading && <PageLoading label="Loading folder" />}

      {error && <LoadError what="this folder" message={error} onRetry={reload} />}

      {isEmpty && tags.length === 0 && <EmptyState title="No files here yet." />}

      {/* Empty because of the TAGS is a third sentence, and it has to name the
          scope: "nothing here" would be wrong when the search covered the whole
          branch and still found nothing. */}
      {isEmpty && tags.length > 0 && (
        <EmptyState title={`Nothing under this folder is tagged ${tags.join(" + ")}.`} />
      )}

      {hiddenByFilter && <EmptyState title={`Nothing here matches “${filter}”.`} />}

      {/* **The selection bar sits over BOTH lists, not inside the grid.**
          It used to live in the `Photos & video` section, which was right while
          only images could be selected — a folder holding nothing but
          `result.json` files then had no bar at all, and "Select all" under a
          heading that says "Photos" would now also take the text files. */}
      {selection.count > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-none border border-line bg-card px-3 py-2">
          <Text
            variant="caption"
            tone="muted"
            className="font-mono tabular-nums"
          >
            {selection.count} of {files.length} selected
          </Text>

          <div className="flex-1" />

          {/* One key per line, in grid order rather than the order they were
                picked: this is going into a shell loop or a `--keys` argument,
                and the order you happened to click in is not information. */}
          <CopyKeyButton
            value={selection.selectedItems.map((item) => item.key).join("\n")}
            noun={selectedNoun("key", "keys")}
          />

          {/* Media has no per-tile menu the way a row does — sixty thumbnails
                with a control each is the crowding this grid exists to avoid —
                so this bar is where a bulk move and a bulk copy are reached
                from. */}
          <button
            type="button"
            onClick={() =>
              setPickerTarget({
                verb: "copy",
                ids: selection.selectedItems.map((item) => item.id),
                noun: selectedNoun("file", "files"),
              })
            }
            aria-label={`Copy ${selectedNoun("file", "files")} to…`}
            title={`Copy ${selectedNoun("file", "files")} to…`}
            className="shrink-0 rounded-none p-2 text-muted transition-colors hover:bg-surface-alt hover:text-ink
                         focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            {/* Two sheets, one behind the other: the source stays, which is
                  the whole difference from the arrow on the move button. */}
            <CopyIcon />
          </button>

          <button
            type="button"
            onClick={() =>
              setPickerTarget({
                verb: "move",
                ids: selection.selectedItems.map((item) => item.id),
                noun: selectedNoun("file", "files"),
              })
            }
            aria-label={`Move ${selectedNoun("file", "files")}`}
            title={`Move ${selectedNoun("file", "files")}`}
            className="shrink-0 rounded-none p-2 text-muted transition-colors hover:bg-surface-alt hover:text-ink
                         focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            {/* A folder with something going into it — the destination is
                  what a move is about, and the arrow says which way. */}
            <FolderIntoIcon />
          </button>

          {/* Under five, the armed button — the cost of being wrong is a
                handful of frames still on screen. Above it, the count has to
                be typed: a selection is invisible once it is gone, and
                "select all" then "delete" is two presses from emptying a
                folder. */}
          {selection.count < BULK_GATE ? (
            <ConfirmDeleteButton
              tone="icon"
              noun={selectedNoun("file", "files")}
              onConfirm={deleteSelected}
            />
          ) : (
            <ConfirmDestroyDialog
              label={`Delete ${selection.count}`}
              title={`Delete ${selectedNoun("file", "files")}?`}
              summary="They are removed from this folder and from the library. Nothing else is touched."
              confirmWord={String(selection.count)}
              onConfirm={deleteSelected}
            />
          )}
        </div>
      )}

      {folders.length > 0 && (
        <section className="flex flex-col gap-2">
          <Text variant="title">Folders</Text>
          {/* A ruled list, like the files below it — not a grid of its own. A
              folder and a file are the same row shape now, so a folder of
              folders no longer reads as a different kind of listing from a
              folder of files. */}
          <div className="flex flex-col">
            {folders.map((folder) => (
              <FolderCard
                key={folder.id}
                name={folder.name}
                prefix={folder.prefix}
                onOpen={() => goToFolder(folder.id)}
                onRename={(name) => run(renameNode(folder.id, name))}
                onMove={() =>
                  setPickerTarget({
                    verb: "move",
                    ids: [folder.id],
                    noun: folder.name,
                    forbiddenId: folder.id,
                  })
                }
                onDelete={() => deleteOne(folder.id, folder.name)}
              />
            ))}
          </div>
        </section>
      )}

      {media.length > 0 && (
        <section className="flex flex-col gap-2">
          {/* "Media" was the API's word for it — `kind` is image | video |
              text | other — and it leaked into the page as a heading that names
              a type union rather than a thing. */}
          <Text variant="title">
            Photos &amp; video{" "}
            <span className="font-body text-sm text-muted">
              ({media.length})
            </span>
          </Text>

          <div className={MEDIA_GRID}>
            {media.map((file) => (
              <MediaTile
                key={file.id}
                file={file}
                selected={selection.selected.has(file.id)}
                selectionActive={selection.count > 0}
                onOpen={() => nav.openFile(file, deep)}
                to={nav.fileHref(file, deep)}
                onToggleSelect={(extend) =>
                  selection.toggleAt(indexOf.get(file.id) ?? 0, extend)
                }
              />
            ))}
          </div>
        </section>
      )}

      {others.length > 0 && (
        <section className="flex flex-col gap-2">
          <Text variant="title">Files</Text>
          <div className="flex flex-col gap-2">
            {others.map((file) => (
              <FileRow
                key={file.id}
                file={file}
                selected={selection.selected.has(file.id)}
                selectionActive={selection.count > 0}
                onToggleSelect={(extend) =>
                  selection.toggleAt(indexOf.get(file.id) ?? 0, extend)
                }
                onOpen={() => nav.openFile(file, deep)}
                to={nav.fileHref(file, deep)}
                onRename={(name) => run(renameNode(file.id, name))}
                onMove={() =>
                  setPickerTarget({
                    verb: "move",
                    ids: [file.id],
                    noun: file.name,
                  })
                }
                onCopyTo={() =>
                  setPickerTarget({
                    verb: "copy",
                    ids: [file.id],
                    noun: file.name,
                  })
                }
                onDelete={() => deleteOne(file.id, file.name)}
              />
            ))}
          </div>
        </section>
      )}

      {pickerTarget && (
        <DestinationPicker
          verb={pickerTarget.verb}
          noun={pickerTarget.noun}
          startId={hereId}
          currentId={hereId}
          // A folder cannot land inside itself, and the picker greys out the
          // branch rather than letting the request come back refused. Greying the
          // folder itself is enough to fence the whole subtree, because it is the
          // only way into one.
          forbiddenId={pickerTarget.forbiddenId}
          onSubmit={submitPicker}
          onClose={() => setPickerTarget(null)}
        />
      )}
    </div>
  );
}
