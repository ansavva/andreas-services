import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Alert, Breadcrumbs, Button, Input, Spinner, Text } from "@ansavva/design-system";

import {
  copyNodes,
  createNode,
  deleteNodes,
  describeNode,
  getTree,
  moveNodes,
  renameNode,
} from "../../apis/studio";
import { useFolder, type FolderPin } from "../../hooks/useFolder";
import { useReel } from "../../hooks/useReel";
import { useResource } from "../../hooks/useResource";
import { useSelection } from "../../hooks/useSelection";
import { useUploads } from "../../hooks/useUploads";
import type { FileEntry, SortOrder } from "../../types";
import type { FolderId, Target } from "../../utils/location";
import { ChipRow } from "../common/ChipRow";
import { ConfirmDeleteButton } from "../common/ConfirmDeleteButton";
import { CopyKeyButton } from "../common/CopyKeyButton";
import { TextPage } from "../text/TextPage";
import { ReelView } from "../viewer/ReelView";
import { DestinationPicker } from "./DestinationPicker";
import { FileRow } from "./FileRow";
import { FolderCard } from "./FolderCard";
import { MediaTile } from "./MediaTile";
import { SortControl } from "./SortControl";
import { UploadButton } from "./UploadButton";
import { UploadStatus } from "./UploadStatus";

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
  /** The folder on screen, or the file open over it. */
  target: Target;
  sort: SortOrder;
  setSort: (next: SortOrder) => void;
  /** `replace` is for the one move that is not a journey — leaving a deleted folder. */
  goToFolder: (id: FolderId, options?: { replace?: boolean }) => void;
  openFile: (file: FileEntry) => void;
  closeItem: () => void;
  /** The reel scrolled onto a different clip. Must never push history. */
  setCurrent: (file: FileEntry) => void;
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
type PickerTarget = {
  verb: "move" | "copy";
  ids: string[];
  noun: string;
  /** Set when a *folder* is moving: it cannot land inside itself. */
  forbiddenId?: string;
};

/**
 * The file layer, whole: listing, selection, upload, reel, text page, and every
 * write a person can make.
 *
 * This was the body of `BrowsePage` and is a component so that a character's and
 * a project's **Files** tab is the same browser rather than a second one that
 * drifts. Nothing about its behaviour changed in the entity rework except the
 * addresses it writes with: every write here takes node ids, where the nine
 * name-path routes it used to call took a slash-joined path that a rename
 * invalidated mid-flight.
 */
export function FolderBrowser({ nav, boundary = null }: Props) {
  const { target, sort } = nav;
  const openId = target.kind === "object" ? target.id : null;

  const [actionError, setActionError] = useState<string | null>(null);
  const [newFolder, setNewFolder] = useState<string | null>(null);
  const [reelFolder, setReelFolder] = useState<FolderPin>(null);
  const [pickerTarget, setPickerTarget] = useState<PickerTarget | null>(null);

  /**
   * Which folder the page *behind* the overlay is showing.
   *
   * Normally that is whatever the address points at — outright for a folder, and
   * for an open file its parent, which `useFolder` settles. While the recursive
   * reel is open it is pinned to the folder the reel was launched from, and that
   * pin is load-bearing: the reel walks across folders and rewrites the address
   * to each clip as it goes, so without it every scroll would land on a file in a
   * different folder and re-fetch the listing underneath — a request per clip,
   * for a listing nobody can see.
   */
  const { folderId, data, loading, error, reload } = useFolder(target, sort, reelFolder);

  // "Play reel" walks recursively from wherever you are, so a folder of only
  // subfolders still opens onto real media. Fetched lazily: the pages cost
  // nothing until the reel is actually opened that way.
  const reel = useReel(folderId ?? null, sort, reelFolder !== null);

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
  const boundaryIndex = boundary === null ? 0 : allCrumbs.findIndex((c) => c.id === boundary);
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

  const media = useMemo(
    () => (data?.files ?? []).filter((file) => file.kind === "image" || file.kind === "video"),
    [data],
  );
  const others = useMemo(
    () => (data?.files ?? []).filter((file) => file.kind !== "image" && file.kind !== "video"),
    [data],
  );

  /**
   * A text file opened by address, and a media file opened by address, are
   * different things: the first is a code viewer, the second is the reel. Both
   * are resolved from the listing rather than from a second fetch, because the
   * listing already carries the presigned URL and the kind.
   *
   * Resolved only while the recursive reel is closed: with it open the address
   * names a clip from some other folder, which this listing is not expected to
   * hold.
   */
  const browsing = reelFolder === null;
  const openIndex = browsing && openId ? media.findIndex((item) => item.id === openId) : -1;
  const openText =
    browsing && openId ? (others.find((item) => item.id === openId) ?? null) : null;

  const goToFolder = useCallback(
    (nextId: FolderId, options?: { replace?: boolean }) => {
      setReelFolder(null);
      setActionError(null);
      nav.goToFolder(nextId, options);
    },
    [nav],
  );

  /**
   * Closing the *recursive reel* is not closing an item, and that is why it is a
   * separate handler. "Play reel" is state, not a navigation — it pushed
   * nothing — so it only has to drop the pin and put the address back on the
   * folder it was launched from.
   */
  const closeReel = useCallback(() => {
    const launchedFrom = reelFolder ? reelFolder.id : (folderId ?? null);
    setReelFolder(null);
    nav.goToFolder(launchedFrom, { replace: true });
  }, [folderId, nav, reelFolder]);

  const selection = useSelection(media, folderId ?? null);

  /**
   * Where an upload lands: the folder on screen, by its own node id.
   *
   * The **last breadcrumb**, not `folderId`. `folderId` is `null` at the library
   * root — the address has nothing to name there — and `POST /api/nodes` needs a
   * parent node. The root has one; the crumbs carry it. So this is `null` only
   * while the listing has not landed, exactly like `prefix`.
   */
  const uploads = useUploads(hereId, reload);

  /** "3 files", "1 key" — the count and its noun, agreeing about plurality. */
  const selectedNoun = useCallback(
    (one: string, many: string) => `${selection.count} ${selection.count === 1 ? one : many}`,
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

  const deleteSelected = useCallback(async () => {
    await run(deleteNodes(selection.selectedItems.map((item) => item.id)));
    selection.clear();
  }, [run, selection]);

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
      if (pickerTarget.verb === "copy") await run(copyNodes(pickerTarget.ids, destination));
      else await run(moveNodes(pickerTarget.ids, destination));
      selection.clear();
    },
    [pickerTarget, run, selection],
  );

  /**
   * Writes from inside the viewer, which behave differently depending on which
   * reel you are in.
   *
   * In the *recursive* reel the pane simply leaves the list and the reel carries
   * on — you are working through a walk, and stopping it to go and look at a
   * folder is not what you asked for. In the *folder* reel the list comes from
   * the listing, which `run` has already re-fetched, so closing back to the
   * folder is both correct and what there is left to see.
   *
   * Deleting never advances to the next clip on its own. The next clip is one
   * scroll away, and arriving there automatically at the exact moment you
   * confirmed a delete is how the wrong thing gets deleted twice.
   */
  const deleteOpenFile = useCallback(
    async (file: FileEntry) => {
      await run(deleteNodes([file.id]));
      if (reelFolder !== null) reel.dropItem(file.id);
      else nav.goToFolder(folderId ?? null, { replace: true });
    },
    [folderId, nav, reel, reelFolder, run],
  );

  /**
   * A rename leaves the address alone, and that is the point of #313.
   *
   * The address used to be the object's key, so renaming it stranded the address
   * bar and every link anyone had sent. It names the node id now, and a rename
   * does not move a node — so there is nothing to navigate. The reel still drops
   * the pane, because its name, its key and its presigned URL all went stale even
   * though its id did not.
   */
  /**
   * A caption or a tag, written onto the file being looked at.
   *
   * **Unlike a rename this leaves the pane alone.** A rename invalidates the
   * name, the key and the presigned URL, so the reel drops the pane and picks
   * the file up again; a description touches none of the three. Dropping the
   * pane here would scroll the reel out from under somebody mid-sentence.
   *
   * `run` re-fetches the listing, which is what puts the new words back on the
   * chrome and into `file.tags` for the panel's chips.
   */
  const describeOpenFile = useCallback(
    async (
      file: FileEntry,
      changes: { description?: string | null; tags?: string[] | null },
    ) => {
      const updated = await run(describeNode(file.id, changes));
      // Patched from what the API answered, not from what was typed: tags are
      // folded server-side, and rendering the typed form would be a chip that
      // disagrees with the selector it just created.
      if (reelFolder !== null && updated) {
        reel.refreshItem(file.id, {
          description: updated.description,
          tags: updated.tags,
        });
      }
    },
    [reel, reelFolder, run],
  );

  const renameOpenFile = useCallback(
    async (file: FileEntry, name: string) => {
      await run(renameNode(file.id, name));
      if (reelFolder !== null) reel.dropItem(file.id);
    },
    [reel, reelFolder, run],
  );

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

  // Escape drops the selection, but only when it is the frontmost thing — the
  // reel, the text page and the move picker each bind Escape to their own close,
  // and clearing a selection out from under one of them would be a keystroke
  // doing two things at once. The picker matters most here: it is often open
  // *on* the selection, so dropping it would be Escape cancelling the move by
  // emptying what was being moved.
  const overlayOpen = openId !== null || reelFolder !== null || pickerTarget !== null;
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
    !loading && !error && data && data.folders.length === 0 && data.files.length === 0;

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
        dragging ? "outline-2 outline-offset-[-8px] outline-dashed outline-primary" : ""
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
          intent="ghost"
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
                  goToFolder(index === 0 && boundary === null ? null : crumb.id);
                }}
              >
                {crumb.name}
              </Breadcrumbs.Item>
            ))}
          </Breadcrumbs.Root>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-y border-line py-2">
        <SortControl value={sort} onChange={nav.setSort} />

        <div className="flex-1" />

        {/*
          One cluster of three icons, then the primary.

          All three act on the folder you are in — copy its prefix, delete it,
          make one inside it — so they read as a set. The divider is doing real
          work rather than decorating: `Play reel` is the only filled button here,
          and a delete sitting flush against it is a mis-click with no undo, so
          the destructive icon stays in the middle of its own cluster and a rule
          separates the cluster from the primary. Do not close that gap.
        */}
        <div className="flex shrink-0 items-center gap-0.5">
          {/* Still the *name path*, and still worth copying even though nothing
              is addressed by one any more: it is what a person types at the CLI,
              which resolves it through `GET /api/resolve`. */}
          <CopyKeyButton value={prefix ?? ""} noun="prefix" />

          <ConfirmDeleteButton
            tone="bar"
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
            className="shrink-0 rounded-md p-2 text-muted transition-colors hover:bg-surface-alt hover:text-ink
                       disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent
                       focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <svg
              viewBox="0 0 24 24"
              aria-hidden="true"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="size-5 fill-none stroke-current stroke-[1.5]"
            >
              <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
              <path d="M12 10.5v5M9.5 13h5" />
            </svg>
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

        {/* Disabled while the folder is unsettled — a cold link to an open file
            has not learned its parent yet, and `?? null` would play the root. */}
        <Button
          size="sm"
          disabled={folderId === undefined}
          onClick={() => setReelFolder({ id: folderId ?? null })}
        >
          Play reel
        </Button>
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
          className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-card p-3"
        >
          <Text variant="caption" tone="muted">
            New folder in {prefix ?? "…"}
          </Text>
          <div className="min-w-48 flex-1">
            <Input value={newFolder} onValueChange={setNewFolder} placeholder="folder name" />
          </div>
          <Button type="submit" size="sm">
            Create
          </Button>
          <Button type="button" intent="ghost" size="sm" onClick={() => setNewFolder(null)}>
            Cancel
          </Button>
        </form>
      )}

      {/* Above the listing rather than over it: an upload is something you
          started and then keep browsing through, and a floating panel would
          cover the grid it is filling. */}
      <UploadStatus items={uploads.items} onClearFinished={uploads.clearFinished} />

      {actionError && (
        <Alert.Root intent="danger">
          <Alert.Title>That did not work</Alert.Title>
          <Alert.Description>{actionError}</Alert.Description>
        </Alert.Root>
      )}

      {loading && (
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading folder" />
        </div>
      )}

      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not load this folder</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      {isEmpty && (
        <Text variant="body" tone="muted">
          This folder is empty.
        </Text>
      )}

      {data && data.folders.length > 0 && (
        <section className="flex flex-col gap-2">
          <Text variant="title">Folders</Text>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {data.folders.map((folder) => (
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
                onDelete={() => run(deleteNodes([folder.id]))}
              />
            ))}
          </div>
        </section>
      )}

      {media.length > 0 && (
        <section className="flex flex-col gap-2">
          {/*
            The heading keeps one control, and the selection gets its own bar,
            which only exists while there is a selection — so the heading line has
            a fixed shape. The counts are out of the button labels because the bar
            says "3 selected" two inches to the left.
          */}
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
            {/* "Media" was the API's word for it — `kind` is image | video |
                text | other — and it leaked into the page as a heading that names
                a type union rather than a thing. */}
            <Text variant="title">
              Photos &amp; video{" "}
              <span className="font-body text-sm text-muted">({media.length})</span>
            </Text>

            <Button
              intent="ghost"
              size="sm"
              onClick={selection.count > 0 ? selection.clear : selection.selectAll}
            >
              {selection.count > 0 ? "Select none" : "Select all"}
            </Button>
          </div>

          {selection.count > 0 && (
            <div className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-card px-3 py-2">
              <Text variant="caption" tone="muted" className="tabular-nums">
                {selection.count} of {media.length} selected
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
                className="shrink-0 rounded-md p-2 text-muted transition-colors hover:bg-surface-alt hover:text-ink
                           focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                {/* Two sheets, one behind the other: the source stays, which is
                    the whole difference from the arrow on the move button. */}
                <svg
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="size-5 fill-none stroke-current stroke-[1.5]"
                >
                  <rect x="9" y="9" width="12" height="12" rx="2" />
                  <path d="M6 15H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1" />
                </svg>
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
                className="shrink-0 rounded-md p-2 text-muted transition-colors hover:bg-surface-alt hover:text-ink
                           focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                {/* A folder with something going into it — the destination is
                    what a move is about, and the arrow says which way. */}
                <svg
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="size-5 fill-none stroke-current stroke-[1.5]"
                >
                  <path d="M2 9V7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-1" />
                  <path d="M2 13h9" />
                  <path d="m8 16 3-3-3-3" />
                </svg>
              </button>

              <ConfirmDeleteButton
                tone="bar"
                noun={selectedNoun("file", "files")}
                onConfirm={deleteSelected}
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {media.map((file, index) => (
              <MediaTile
                key={file.id}
                file={file}
                selected={selection.selected.has(file.id)}
                selectionActive={selection.count > 0}
                onOpen={() => nav.openFile(file)}
                onToggleSelect={(extend) => selection.toggleAt(index, extend)}
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
                onOpen={() => nav.openFile(file)}
                onRename={(name) => run(renameNode(file.id, name))}
                onMove={() =>
                  setPickerTarget({ verb: "move", ids: [file.id], noun: file.name })
                }
                onCopyTo={() =>
                  setPickerTarget({ verb: "copy", ids: [file.id], noun: file.name })
                }
                onDelete={() => run(deleteNodes([file.id]))}
              />
            ))}
          </div>
        </section>
      )}

      {/*
        One viewer, two sources.

        Opening a tile plays *this folder's* media, starting on the one that was
        clicked — which is what "open this" means and needs no second request,
        since the listing already has it. "Play reel" plays everything beneath the
        folder recursively, paged in from the API. Both routes land here.
      */}
      {reelFolder !== null ? (
        <ReelView
          items={reel.items}
          loading={reel.loading}
          exhausted={reel.exhausted}
          truncated={reel.truncated}
          startIndex={0}
          onLoadMore={reel.loadMore}
          onClose={closeReel}
          onCurrentChange={nav.setCurrent}
          onRename={renameOpenFile}
          onDelete={deleteOpenFile}
          onDescribe={describeOpenFile}
        />
      ) : (
        openIndex >= 0 && (
          <ReelView
            items={media}
            loading={false}
            exhausted
            startIndex={openIndex}
            onClose={nav.closeItem}
            onCurrentChange={nav.setCurrent}
            onRename={renameOpenFile}
            onDelete={deleteOpenFile}
            onDescribe={describeOpenFile}
          />
        )
      )}

      {/* A text file gets a page of its own, the way a clip does — same address,
          same "this is the thing you came for" treatment — and unlike a clip it
          can be edited, because these are notes and prompts a person wrote. */}
      {openText && <TextPage file={openText} onClose={nav.closeItem} onSaved={reload} />}

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

      {/* A share link to a node this folder does not hold — deleted upstream
          between the link being sent and being opened. The listing loaded fine,
          so this is specific and worth saying rather than silently showing the
          folder. The id itself is not shown: it is what the address bar already
          says, and it names nothing a person can act on. */}
      {openId && openIndex < 0 && !openText && !loading && !error && (
        <Alert.Root intent="warning">
          <Alert.Title>That file is not here any more</Alert.Title>
          <Alert.Description>
            Nothing in this folder matches that link. It may have been deleted.
          </Alert.Description>
        </Alert.Root>
      )}
    </div>
  );
}

/**
 * A browser driven by component state rather than by the URL — the Files tab.
 *
 * The address bar is spent on the entity, so navigating a subfolder inside a tab
 * cannot touch it: doing so would replace the page you are standing on, and
 * browser-back out of three subfolders would walk back through a character page
 * three times.
 *
 * What is given up is that a folder inside a tab is not linkable. That is the
 * right trade in one direction only, and it is why `/f/<id>` still exists and the
 * tab does not replace it: a *link* to a folder is a link to the browser.
 */
export function useLocalBrowserNav(rootId: string): BrowserNav {
  const [folder, setFolder] = useState<FolderId>(rootId);
  const [openId, setOpenId] = useState<string | null>(null);
  const [sort, setSort] = useState<SortOrder>("newest");

  // The tab is remounted per entity by its `key`, but a character page navigated
  // to from another character's page is the same mount with a different root.
  useEffect(() => {
    setFolder(rootId);
    setOpenId(null);
  }, [rootId]);

  // The target is built inside the memo rather than beside it: a fresh object
  // literal on every render is a dependency that never compares equal, which
  // would rebuild the nav — and re-run every effect keyed on it — each time.
  return useMemo(
    () => ({
      target: (openId
        ? { kind: "object", id: openId }
        : { kind: "folder", id: folder }) as Target,
      sort,
      setSort,
      goToFolder: (id: FolderId) => {
        setOpenId(null);
        // `null` is the *library* root, which a scoped browser has no way to
        // show and no business showing — the boundary crumb is this entity's
        // root, so that is where "up from the top" lands.
        setFolder(id ?? rootId);
      },
      openFile: (file: FileEntry) => setOpenId(file.id),
      closeItem: () => setOpenId(null),
      setCurrent: (file: FileEntry) => setOpenId(file.id),
    }),
    [folder, openId, rootId, sort],
  );
}

/**
 * The browser scoped to one entity's folder — a character's or a project's
 * **Files** tab.
 *
 * A component of its own so that the hook driving it is called at the top of
 * *something*: a tab panel renders nothing while it is inactive, so the state
 * belongs to the tab rather than to the page, and switching away genuinely
 * discards it.
 *
 * ## The chip row is where the folder tabs went
 *
 * A character's root children each used to get a tab of their own, beside
 * Profile and References. That made a *listing* into navigation: the strip grew
 * and shrank as folders were created and deleted, every one of those tabs showed
 * a folder the browser one tab over already held, and at 390px the seven of them
 * wrapped into three rows of underline. They are shortcuts now — one scrolling
 * row of a fixed shape, with the browser still the only place a folder opens.
 */
export function FolderTab({ rootId }: { rootId: string }) {
  const nav = useLocalBrowserNav(rootId);
  return (
    <div className="flex w-full flex-col gap-4">
      <FolderShortcuts rootId={rootId} nav={nav} />
      <FolderBrowser nav={nav} boundary={rootId} />
    </div>
  );
}

/**
 * The root's immediate children, as jump targets.
 *
 * Fetched here rather than handed down because both callers want it and only one
 * of them ever had the listing to hand. It is the same `GET /api/tree` the
 * browser itself makes for the root, and it renders nothing at all when the root
 * has no subfolders — a character whose starting folders were deleted gets no
 * empty rail.
 *
 * Scrolls rather than wraps — see `ChipRow`, which the reference tag filter uses
 * too, so the two rows cannot drift apart.
 */
function FolderShortcuts({ rootId, nav }: { rootId: string; nav: BrowserNav }) {
  const load = useCallback(() => getTree({ node: rootId }, "name"), [rootId]);
  const { data } = useResource(load);

  const folders = data?.folders ?? [];
  if (folders.length === 0) return null;

  // An open file overlays the page, so the folder behind it is not a place
  // anybody is standing — only a folder target lights a chip.
  const here = nav.target.kind === "folder" ? nav.target.id : null;

  return (
    <ChipRow role="group" aria-label="Folder shortcuts">
      <FolderChip label="Top" active={here === rootId} onClick={() => nav.goToFolder(rootId)} />
      {folders.map((folder) => (
        <FolderChip
          key={folder.id}
          label={folder.name}
          active={here === folder.id}
          onClick={() => nav.goToFolder(folder.id)}
        />
      ))}
    </ChipRow>
  );
}

function FolderChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "true" : undefined}
      className={`shrink-0 snap-start rounded-full border px-3 py-1 font-body text-sm transition-colors
                  focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                    active
                      ? "border-primary bg-primary text-primary-text"
                      : "border-line text-muted hover:bg-surface-alt hover:text-ink"
                  }`}
    >
      {label}
    </button>
  );
}
