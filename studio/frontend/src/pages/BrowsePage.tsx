import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { Alert, Breadcrumbs, Button, Input, Spinner, Text } from "@ansavva/design-system";

import {
  copyObjects,
  createFolder,
  deleteFolder,
  deleteObjects,
  moveFolder,
  moveObjects,
  renameFolder,
  renameObject,
} from "../apis/studio";
import { FileRow } from "../components/browse/FileRow";
import { FolderCard } from "../components/browse/FolderCard";
import { MediaTile } from "../components/browse/MediaTile";
import { DestinationPicker } from "../components/browse/DestinationPicker";
import { SortControl } from "../components/browse/SortControl";
import { UploadButton } from "../components/browse/UploadButton";
import { UploadStatus } from "../components/browse/UploadStatus";
import { ConfirmDeleteButton } from "../components/common/ConfirmDeleteButton";
import { CopyKeyButton } from "../components/common/CopyKeyButton";
import { LibrarySwitcher } from "../components/common/LibrarySwitcher";
import { TextPage } from "../components/text/TextPage";
import { ReelView } from "../components/viewer/ReelView";
import { useAuth } from "../context/AuthContext";
import { useFolder, type FolderPin } from "../hooks/useFolder";
import { useReel } from "../hooks/useReel";
import { useSelection } from "../hooks/useSelection";
import { useUploads } from "../hooks/useUploads";
import { DEFAULT_SORT, isSortOrder, type FileEntry, type SortOrder } from "../types";
import { folderPath, objectPath, targetFromPath, type FolderId } from "../utils/location";

/**
 * What the destination picker is open on, and which operation it will perform.
 *
 * Two shapes because a folder carries a subtree and a set of objects does not —
 * the counting and the refusals are genuinely different, which is why the API
 * has two move endpoints. Collapsing them here would only push the branch one
 * layer down.
 *
 * `verb` rides along rather than being separate state so the two cannot drift:
 * there is no way to have a picker open with no operation chosen, or to close
 * one and leave a stale verb behind for the next.
 */
type PickerTarget =
  | { verb: "move"; kind: "folder"; prefix: string; name: string }
  | { verb: "move" | "copy"; kind: "objects"; keys: string[]; noun: string };

export function BrowsePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { email, logout } = useAuth();

  /**
   * The URL is the state.
   *
   * `/f/<node_id>` is a folder and `/o/<node_id>` is that file, open. Nothing
   * here mirrors the location into component state: doing so is what makes
   * browser back and a pasted link disagree, and both have to work for a share
   * link to mean anything.
   */
  const target = useMemo(() => targetFromPath(location.pathname), [location.pathname]);
  const openId = target.kind === "object" ? target.id : null;

  const sortParam = params.get("sort");
  const sort: SortOrder = isSortOrder(sortParam) ? sortParam : DEFAULT_SORT;

  const [actionError, setActionError] = useState<string | null>(null);
  const [newFolder, setNewFolder] = useState<string | null>(null);
  const [reelFolder, setReelFolder] = useState<FolderPin>(null);
  const [pickerTarget, setPickerTarget] = useState<PickerTarget | null>(null);

  /**
   * Which folder the page *behind* the overlay is showing.
   *
   * Normally that is whatever the URL points at — outright for `/f/<id>`, and
   * for `/o/<id>` the file's parent, which `useFolder` settles. While the
   * recursive reel is open it is pinned to the folder the reel was launched
   * from, and that pin is load-bearing: the reel walks across folders and
   * rewrites the URL to each clip as it goes, so without it every scroll would
   * land on a file in a different folder and re-fetch the listing underneath —
   * a request per clip, for a listing nobody can see.
   */
  const { folderId, data, loading, error, reload } = useFolder(target, sort, reelFolder);

  // "Play reel" walks recursively from wherever you are, so a folder of only
  // subfolders — `projects/<project>/` — still opens onto real media. Fetched lazily:
  // the pages cost nothing until the reel is actually opened that way.
  const reel = useReel(folderId ?? null, sort, reelFolder !== null);

  /**
   * The listing's own breadcrumbs are where every *path* on this page comes
   * from now.
   *
   * The URL used to carry the path, so the folder's name, its parent and
   * whether it was the root were all string arithmetic on it. An id URL carries
   * none of that, and the crumbs already do: the server walks `parent_id` and
   * hands back the trail with an id and a name path per level. Reading it here
   * rather than rebuilding it is what keeps the SPA off a path↔id translation of
   * its own.
   *
   * `prefix` is `null` until the listing lands, and it is not `""` — `""` is the
   * root, and "create this folder at the root" is not a safe reading of "we do
   * not know yet". Every control that writes is disabled while it is null.
   */
  const crumbs = data?.breadcrumbs ?? [];
  const prefix = data?.prefix ?? null;
  const atRoot = crumbs.length <= 1;
  const parentId = crumbs.at(-2)?.id ?? null;
  const folderName = crumbs.at(-1)?.name ?? "";

  const media = useMemo(
    () => (data?.files ?? []).filter((file) => file.kind === "image" || file.kind === "video"),
    [data],
  );
  const others = useMemo(
    () => (data?.files ?? []).filter((file) => file.kind !== "image" && file.kind !== "video"),
    [data],
  );

  /**
   * A text file opened by URL, and a media file opened by URL, are different
   * things: the first is a code viewer, the second is the reel. Both are
   * resolved from the listing rather than from a second fetch, because the
   * listing already carries the presigned URL and the kind.
   *
   * Resolved only while the recursive reel is closed: with it open the URL names
   * a clip from some other folder, which this listing is not expected to hold.
   */
  const browsing = reelFolder === null;
  const openIndex = browsing && openId ? media.findIndex((item) => item.id === openId) : -1;
  const openText =
    browsing && openId ? (others.find((item) => item.id === openId) ?? null) : null;

  /**
   * `replace` is for the one navigation that is not a journey: leaving a folder
   * because it no longer exists. Pushing there would leave the deleted prefix
   * as the entry behind you, so back would load an empty listing of something
   * you just destroyed. Every other move between folders is a real history
   * entry, because the browser's back button has to retrace browsing.
   */
  const goToFolder = useCallback(
    (nextId: FolderId, { replace = false }: { replace?: boolean } = {}) => {
      setReelFolder(null);
      setActionError(null);
      navigate({ pathname: folderPath(nextId), search: location.search }, { replace });
    },
    [location.search, navigate],
  );

  const openFile = useCallback(
    (file: FileEntry) => {
      navigate({ pathname: objectPath(file.id), search: location.search });
    },
    [location.search, navigate],
  );

  /**
   * Closing an *item* goes back rather than pushing the folder again.
   *
   * Opening it pushed a history entry, so closing should undo that entry —
   * otherwise open-then-close leaves a folder entry behind per item viewed, and
   * the browser's back button walks a trail of the same folder over and over.
   * Someone who arrived on a shared link has no entry to undo (`location.key`
   * is React Router's `"default"` for the first entry in a session), so that
   * case navigates to the folder instead of stepping out of the app.
   */
  const closeItem = useCallback(() => {
    if (location.key === "default") {
      navigate(
        { pathname: folderPath(folderId ?? null), search: location.search },
        { replace: true },
      );
    } else {
      navigate(-1);
    }
  }, [folderId, location.key, location.search, navigate]);

  /**
   * Closing the *recursive reel* is the opposite case, and that is why it is a
   * separate handler. "Play reel" is state, not a navigation — it pushed
   * nothing — so going back would leave the folder entirely. It only has to
   * drop the pin and put the URL back on the folder it was launched from.
   */
  const closeReel = useCallback(() => {
    const launchedFrom = reelFolder ? reelFolder.id : (folderId ?? null);
    setReelFolder(null);
    navigate({ pathname: folderPath(launchedFrom), search: location.search }, { replace: true });
  }, [folderId, location.search, navigate, reelFolder]);

  // Scrolling the reel rewrites the URL rather than pushing to it. Twenty clips
  // scrolled past would otherwise be twenty back presses to escape.
  const onReelCurrentChange = useCallback(
    (item: FileEntry) => {
      navigate({ pathname: objectPath(item.id), search: location.search }, { replace: true });
    },
    [location.search, navigate],
  );

  const setSort = useCallback(
    (next: SortOrder) => {
      const nextParams = new URLSearchParams(params);
      if (next === DEFAULT_SORT) nextParams.delete("sort");
      else nextParams.set("sort", next);
      setParams(nextParams, { replace: true });
    },
    [params, setParams],
  );

  const selection = useSelection(media, folderId ?? null);

  /**
   * Where an upload lands: the folder on screen, by its own node id.
   *
   * The **last breadcrumb**, not `folderId`. `folderId` is `null` at the library
   * root — the URL has nothing to name there — and `POST /api/nodes` needs a
   * parent node. The root has one; the crumbs carry it. So this is `null` only
   * while the listing has not landed, exactly like `prefix`, and every control
   * that writes is disabled in that state.
   */
  const uploadInto = crumbs.at(-1)?.id ?? null;
  const uploads = useUploads(uploadInto, reload);

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
    // Still keys: `DELETE /api/objects` is key-addressed until #316. The
    // selection holds ids; the entries it holds them for carry both.
    const keys = selection.selectedItems.map((item) => item.key);
    await run(deleteObjects(keys));
    selection.clear();
  }, [run, selection]);

  /**
   * The picker's submit, for whichever operation and kind it was opened on.
   *
   * It deliberately does *not* close the picker — it closes itself on
   * a resolved promise and stays open with the message on a rejected one, which
   * is the same bargain `RenameForm` makes: "that name is taken there" is fixed
   * by picking a different folder, and closing to say so would throw away the
   * navigating you just did.
   */
  const submitPicker = useCallback(
    async (destination: string) => {
      if (!pickerTarget) return;
      if (pickerTarget.kind === "folder") {
        await run(moveFolder(pickerTarget.prefix, destination));
        return;
      }
      if (pickerTarget.verb === "copy") {
        // Unlike a move, a copy can land in the folder you are looking at — so
        // this re-fetches, and `run` does by default. Favouriting skipped the
        // refresh because its destination was always somewhere you were not.
        await run(copyObjects(pickerTarget.keys, destination));
        selection.clear();
        return;
      }
      await run(moveObjects(pickerTarget.keys, destination));
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
      await run(deleteObjects([file.key]));
      if (reelFolder !== null) {
        reel.dropItem(file.id);
      } else {
        navigate(
          { pathname: folderPath(folderId ?? null), search: location.search },
          { replace: true },
        );
      }
    },
    [folderId, location.search, navigate, reel, reelFolder, run],
  );

  /**
   * A rename leaves the URL alone, and that is the point of #313.
   *
   * The address used to be the object's key, so renaming it stranded the address
   * bar on a key that no longer existed and every link anyone had sent. It names
   * the node id now, and a rename does not move a node — so there is nothing to
   * navigate. The reel still drops the pane, because its name, its key and its
   * presigned URL all went stale even though its id did not.
   */
  const renameOpenFile = useCallback(
    async (file: FileEntry, name: string) => {
      await run(renameObject(file.key, name));
      if (reelFolder !== null) reel.dropItem(file.id);
    },
    [reel, reelFolder, run],
  );

  /**
   * Delete the folder you are standing in, then step up into its parent.
   *
   * The listing already had a delete for every folder *except* this one, which
   * meant emptying a run folder and then getting rid of it took navigating back
   * out to find it in the grid — and for a folder you arrived at by share link,
   * out was somewhere you had never been.
   *
   * It refuses to refresh on the way out. `run` re-fetches by default, and the
   * prefix it would re-fetch is the one that has just stopped existing: one
   * request for an empty listing, rendered for as long as the navigation takes.
   * Going up is what re-fetches, against a prefix that is still there.
   */
  const deleteCurrentFolder = useCallback(async () => {
    if (prefix === null) return;
    await run(deleteFolder(prefix), { refresh: false });
    goToFolder(parentId, { replace: true });
  }, [goToFolder, parentId, prefix, run]);

  const submitNewFolder = useCallback(async () => {
    const name = (newFolder ?? "").trim();
    if (!name || prefix === null) {
      setNewFolder(null);
      return;
    }
    await run(createFolder(prefix, name)).then(
      () => setNewFolder(null),
      () => undefined,
    );
  }, [newFolder, prefix, run]);

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
      className={`mx-auto flex min-h-full w-full max-w-7xl flex-col gap-6 p-4 sm:p-6 ${
        dragging ? "outline-2 outline-offset-[-8px] outline-dashed outline-primary" : ""
      }`}
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Text variant="display">Studio</Text>
          <Text variant="caption" tone="muted">
            media library
          </Text>
        </div>

        <div className="flex items-center gap-2">
          {/* A sibling of the sign-out button, never inside a listing row: every
              card and row on this page is itself a `<button>`, and the switcher
              renders one. See `LibrarySwitcher`. */}
          <LibrarySwitcher />
          {email && (
            <Text variant="caption" tone="muted" className="hidden sm:block">
              {email}
            </Text>
          )}
          <Button
            intent="ghost"
            size="sm"
            onClick={() => {
              void logout().then(() => navigate("/"));
            }}
          >
            Sign out
          </Button>
        </div>
      </header>

      {/*
        Two rows, not one.

        These are two different kinds of control and they used to share a line:
        where you are (back, breadcrumbs) and what you can do here (sort, copy the
        prefix, delete, new folder, play). On any real path the breadcrumbs took
        the width and the buttons wrapped underneath them anyway — in whatever order
        the flex run happened to break — so a folder deep in `projects/` opened
        onto a bar that looked different from the one at the root. Splitting them
        makes that layout the intended one rather than the one that fell out, and
        gives each row a shape that does not change with the length of the path.
      */}
      <div className="flex min-w-0 items-center gap-2">
        {/*
          Up one folder, not browser-back.
          They are different journeys and both are wanted: back retraces how you
          got here, which after a shared link is nowhere, and after ten minutes of
          browsing is ten minutes of browsing. This goes *up the tree*, which is
          where "back" means to someone reading a folder they were linked into.
          The browser's own back button still works, because every navigation here
          is a real history entry.
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
                href={folderPath(crumb.id)}
                onClick={(event: React.MouseEvent) => {
                  event.preventDefault();
                  goToFolder(crumb.id);
                }}
              >
                {crumb.name}
              </Breadcrumbs.Item>
            ))}
          </Breadcrumbs.Root>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-y border-line py-2">
        <SortControl value={sort} onChange={setSort} />

        <div className="flex-1" />

        {/*
          One cluster of three icons, then the primary.

          All three act on the folder you are in — copy its prefix, delete it,
          make one inside it — so they read as a set: same weight, same size, and a
          tighter gap between them than the row's own. The copy control used to sit up beside
          the breadcrumbs, which put two of the three folder actions in one row
          and the third in another; that is what made this bar look like loose
          parts. The two rows still mean what the comment above says, with the
          line drawn one notch tighter: *where you are* above, everything you can
          *do* below.

          The divider is doing real work rather than decorating. `Play reel` is
          the only filled button on the page, and a delete sitting flush against
          it is a mis-click with no undo — so the destructive icon is kept in the
          middle of its own cluster, and a rule separates the cluster from the
          primary. Do not close that gap.
        */}
        <div className="flex shrink-0 items-center gap-0.5">
          <CopyKeyButton value={prefix ?? ""} noun="prefix" />

          {/*
            The folder you are in, deletable from inside it.

            Every other folder in the library has a delete in the `ItemActions`
            menu on its card — but that card is drawn by the folder's *parent*,
            so the one folder without one was the folder you were standing in,
            and getting rid of it meant navigating back out to find it in the
            grid.

            Armed before it fires, and the `bar` tone is why it is worth the
            extra width: the trash can alone at rest, growing into a sentence
            that names the folder once armed. An icon changing colour is not
            enough for a press that takes a subtree with it. It is disabled at
            the root, which the API refuses anyway — the root node has no
            `parent_id`, so there is no `NAME#` item to delete — saying so before
            the round trip rather than after it.
          */}
          <ConfirmDeleteButton
            tone="bar"
            disabled={atRoot || prefix === null}
            noun={atRoot ? "this folder" : folderName}
            onConfirm={deleteCurrentFolder}
          />

          {/* An icon, like the two beside it: "New folder" is a noun-shaped
              action with an icon everyone already knows, and spelling it out
              made it the widest thing in the row. The label lives on
              `aria-label` and `title`, so it is still there for a screen reader
              and for anyone who hovers. */}
          <button
            type="button"
            onClick={() => setNewFolder("")}
            disabled={prefix === null}
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
          Upload, on the other side of the divider from the destructive cluster
          and beside the primary rather than in it.

          It is labelled where its three neighbours are icons, because there is no
          icon everyone reads as "put a file here" — the tray-with-an-arrow means
          upload, download and share depending on the platform — and this is the
          one control on the page a person arrives *looking* for.

          Disabled until the listing lands, like every other write here: without
          the crumbs there is no parent node to create under. It is not disabled
          while a queue is running — adding to one is ordinary.
        */}
        <UploadButton onFiles={uploads.start} disabled={uploadInto === null} />

        {/* Disabled while the folder is unsettled — a cold `/o/<id>` link has
            not learned its parent yet, and `?? null` would play the root. */}
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
                onRename={(name) => run(renameFolder(folder.prefix, name))}
                onMove={() =>
                  setPickerTarget({ verb: "move", kind: "folder", prefix: folder.prefix, name: folder.name })
                }
                onDelete={() => run(deleteFolder(folder.prefix))}
              />
            ))}
          </div>
        </section>
      )}

      {media.length > 0 && (
        <section className="flex flex-col gap-2">
          {/*
            The heading keeps one control, and the selection gets its own bar.

            These were one line, and with something selected it held a heading, a
            count and five buttons whose labels each restated that count —
            "Copy 3 keys", "Delete 3 files" — so the row was mostly the number 3,
            written five times, wrapping wherever it ran out of width.

            Three things changed. The selection actions moved to a strip that only
            exists while there is a selection, so the heading line has a fixed
            shape. The counts came out of the button labels, because the bar says
            "3 selected" two inches to the left — and delete went all the way down
            to the trash can the rows use, expanding back into a written
            confirmation only once it is armed, which is the one press where
            restating what is about to go is the point. And "Clear" is gone:
            it did the same job as "Select none", which is what the toggle already
            reads once everything is picked, and Escape clears from anywhere.
          */}
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
            {/* "Media" was the API's word for it — `kind` is image | video |
                text | other — and it leaked into the page as a heading that
                names a type union rather than a thing. What is in this grid is
                photographs and clips, so that is what it says. It also stops the
                two headings from lying about their difference: "Media" and
                "Files" read as a distinction between media and files, when both
                sections are files and the real split is what you look at versus
                what you read. */}
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

              {/* The same copy control the rows use, told what it is copying.
                  One key per line, in grid order rather than the order they were
                  picked: this is going into a shell loop or a `--keys` argument,
                  and the order you happened to click in is not information. */}
              <CopyKeyButton
                value={selection.selectedItems.map((item) => item.key).join("\n")}
                noun={selectedNoun("key", "keys")}
              />

              {/* Media has no per-tile menu the way a row does — sixty thumbnails
                  with a control each is the crowding this grid exists to avoid —
                  so this bar is where a bulk move and a bulk copy are reached
                  from. Picking the keepers out of a run is the whole reason to
                  select forty tiles at once, and copying them somewhere is now
                  how that is done. */}
              <button
                type="button"
                onClick={() =>
                  setPickerTarget({
                    verb: "copy",
                    kind: "objects",
                    keys: selection.selectedItems.map((item) => item.key),
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
                    kind: "objects",
                    keys: selection.selectedItems.map((item) => item.key),
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
                onOpen={() => openFile(file)}
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
                onOpen={() => openFile(file)}
                onRename={(name) => run(renameObject(file.key, name))}
                onMove={() =>
                  setPickerTarget({
                    verb: "move",
                    kind: "objects",
                    keys: [file.key],
                    noun: file.name,
                  })
                }
                onCopyTo={() =>
                  setPickerTarget({
                    verb: "copy",
                    kind: "objects",
                    keys: [file.key],
                    noun: file.name,
                  })
                }
                onDelete={() => run(deleteObjects([file.key]))}
              />
            ))}
          </div>
        </section>
      )}

      {/*
        One viewer, two sources.

        Opening a tile plays *this folder's* media, starting on the one that was
        clicked — which is what "open this" means and needs no second request,
        since the listing already has it. "Play reel" plays everything beneath
        the folder recursively, paged in from the API. There is no lightbox any
        more; both routes land here.
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
          onCurrentChange={onReelCurrentChange}
          onRename={renameOpenFile}
          onDelete={deleteOpenFile}
        />
      ) : (
        openIndex >= 0 && (
          <ReelView
            items={media}
            loading={false}
            exhausted
            startIndex={openIndex}
            onClose={closeItem}
            onCurrentChange={onReelCurrentChange}
            onRename={renameOpenFile}
            onDelete={deleteOpenFile}
          />
        )
      )}

      {/* A text file gets a page of its own, the way a clip does — same URL, same
          "this is the thing you came for" treatment — and unlike a clip it can be
          edited, because these are notes and prompts a person wrote. */}
      {openText && <TextPage file={openText} onClose={closeItem} onSaved={reload} />}

      {pickerTarget && (
        <DestinationPicker
          verb={pickerTarget.verb}
          noun={pickerTarget.kind === "folder" ? pickerTarget.name : pickerTarget.noun}
          startPrefix={prefix ?? ""}
          currentPrefix={prefix ?? ""}
          // A folder cannot land inside itself, and the picker greys out the
          // branch rather than letting the request come back refused.
          forbiddenPrefix={pickerTarget.kind === "folder" ? pickerTarget.prefix : undefined}
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
