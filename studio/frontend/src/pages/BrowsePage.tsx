import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { Alert, Breadcrumbs, Button, Input, Spinner, Text } from "@ansavva/design-system";

import {
  addFavorites,
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
import { MovePicker } from "../components/browse/MovePicker";
import { SortControl } from "../components/browse/SortControl";
import { ConfirmDeleteButton } from "../components/common/ConfirmDeleteButton";
import { CopyKeyButton } from "../components/common/CopyKeyButton";
import { FavoriteButton } from "../components/common/FavoriteButton";
import { TextPage } from "../components/text/TextPage";
import { ReelView } from "../components/viewer/ReelView";
import { useAuth } from "../context/AuthContext";
import { useReel } from "../hooks/useReel";
import { useSelection } from "../hooks/useSelection";
import { useTree } from "../hooks/useTree";
import { DEFAULT_SORT, isSortOrder, type FileEntry, type SortOrder } from "../types";
import { ROOT_PREFIX, folderPath, objectPath, parentPrefix, targetFromPath } from "../utils/location";

/**
 * What the destination picker is open on.
 *
 * Two shapes because the API has two move endpoints, and it has two because a
 * folder move carries a subtree and an object move does not — the counting and
 * the refusals are genuinely different. Collapsing them here would only push the
 * branch one layer down.
 */
type MoveTarget =
  | { kind: "folder"; prefix: string; name: string }
  | { kind: "objects"; keys: string[]; noun: string };

export function BrowsePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { email, logout } = useAuth();

  /**
   * The URL is the state.
   *
   * `/projects/<project>/runs/` is a folder and `/projects/<project>/runs/x/output/clip.mp4`
   * is that clip, open. Nothing here mirrors the location into component state:
   * doing so is what makes browser back and a pasted link disagree, and both
   * have to work for a share link to mean anything.
   */
  const target = useMemo(() => targetFromPath(location.pathname), [location.pathname]);
  const openKey = target.kind === "object" ? target.key : null;

  const sortParam = params.get("sort");
  const sort: SortOrder = isSortOrder(sortParam) ? sortParam : DEFAULT_SORT;

  const [actionError, setActionError] = useState<string | null>(null);
  const [newFolder, setNewFolder] = useState<string | null>(null);
  const [reelPrefix, setReelPrefix] = useState<string | null>(null);
  const [moveTarget, setMoveTarget] = useState<MoveTarget | null>(null);

  /**
   * Which folder the page *behind* the overlay is showing.
   *
   * Normally that is whatever the URL points at. While the recursive reel is
   * open it is pinned to the folder the reel was launched from, and that pin is
   * load-bearing: the reel walks across folders and rewrites the URL to each
   * clip as it goes, so without it every scroll would land on a key in a
   * different folder and re-fetch the listing underneath — a request per clip,
   * for a listing nobody can see.
   */
  const prefix = reelPrefix ?? target.prefix;

  const { data, loading, error, reload } = useTree(prefix, sort);

  // "Play reel" walks recursively from wherever you are, so a folder of only
  // subfolders — `projects/<project>/` — still opens onto real media. Fetched lazily:
  // the pages cost nothing until the reel is actually opened that way.
  const reel = useReel(reelPrefix ?? prefix, sort, reelPrefix !== null);

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
  const browsing = reelPrefix === null;
  const openIndex = browsing && openKey ? media.findIndex((item) => item.key === openKey) : -1;
  const openText =
    browsing && openKey ? (others.find((item) => item.key === openKey) ?? null) : null;

  const goToFolder = useCallback(
    (nextPrefix: string) => {
      setReelPrefix(null);
      setActionError(null);
      navigate({ pathname: folderPath(nextPrefix), search: location.search });
    },
    [location.search, navigate],
  );

  const openFile = useCallback(
    (file: FileEntry) => {
      navigate({ pathname: objectPath(file.key), search: location.search });
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
      navigate({ pathname: folderPath(prefix), search: location.search }, { replace: true });
    } else {
      navigate(-1);
    }
  }, [location.key, location.search, navigate, prefix]);

  /**
   * Closing the *recursive reel* is the opposite case, and that is why it is a
   * separate handler. "Play reel" is state, not a navigation — it pushed
   * nothing — so going back would leave the folder entirely. It only has to
   * drop the pin and put the URL back on the folder it was launched from.
   */
  const closeReel = useCallback(() => {
    const launchedFrom = reelPrefix ?? prefix;
    setReelPrefix(null);
    navigate({ pathname: folderPath(launchedFrom), search: location.search }, { replace: true });
  }, [location.search, navigate, prefix, reelPrefix]);

  // Scrolling the reel rewrites the URL rather than pushing to it. Twenty clips
  // scrolled past would otherwise be twenty back presses to escape.
  const onReelCurrentChange = useCallback(
    (item: FileEntry) => {
      navigate({ pathname: objectPath(item.key), search: location.search }, { replace: true });
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

  const selection = useSelection(media, prefix);

  /**
   * Which of the selection can actually be favourited.
   *
   * Everything in one grid comes from one folder, so this is all of it or none
   * of it — but the API answers per file and this reads that answer rather than
   * inferring it from the prefix, which is the same reason `favorites_prefix`
   * arrives per file in the first place.
   */
  const favoritable = useMemo(
    () => selection.selectedItems.filter((item) => item.favorites_prefix && !item.favorited),
    [selection.selectedItems],
  );

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

  /**
   * Favouriting is the one write that does not re-fetch, because it does not
   * change this folder.
   *
   * The copy lands in `projects/<subject>/favorites/`, which is somewhere you
   * are not: an item can only be favourited from outside that folder, so the
   * listing on screen is the same listing afterwards. Re-fetching would be a
   * request whose only visible effect is the grid flickering — and in the reel
   * it would re-walk the subtree under the scroll position, which is exactly
   * what `useReel.dropItem` exists to avoid. The star reports itself instead.
   */
  const favorite = useCallback(
    (keys: string[]) => run(addFavorites(keys), { refresh: false }),
    [run],
  );

  const deleteSelected = useCallback(async () => {
    const keys = selection.selectedItems.map((item) => item.key);
    await run(deleteObjects(keys));
    selection.clear();
  }, [run, selection]);

  /**
   * The picker's submit, for whichever kind of thing it was opened on.
   *
   * It deliberately does *not* close the picker — `MovePicker` closes itself on
   * a resolved promise and stays open with the message on a rejected one, which
   * is the same bargain `RenameForm` makes: "that name is taken there" is fixed
   * by picking a different folder, and closing to say so would throw away the
   * navigating you just did.
   */
  const submitMove = useCallback(
    async (destination: string) => {
      if (!moveTarget) return;
      if (moveTarget.kind === "folder") {
        await run(moveFolder(moveTarget.prefix, destination));
        return;
      }
      await run(moveObjects(moveTarget.keys, destination));
      selection.clear();
    },
    [moveTarget, run, selection],
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
      if (reelPrefix !== null) {
        reel.dropItem(file.key);
      } else {
        navigate(
          { pathname: folderPath(parentPrefix(file.key)), search: location.search },
          { replace: true },
        );
      }
    },
    [location.search, navigate, reel, reelPrefix, run],
  );

  const renameOpenFile = useCallback(
    async (file: FileEntry, name: string) => {
      const result = await run(renameObject(file.key, name));
      if (reelPrefix !== null) {
        reel.dropItem(file.key);
        return;
      }
      // The URL names the object, so a rename has to move it or the address bar
      // is left pointing at a key that no longer exists.
      navigate({ pathname: objectPath(result.key), search: location.search }, { replace: true });
    },
    [location.search, navigate, reel, reelPrefix, run],
  );

  /**
   * Favouriting from inside the viewer, which — unlike renaming and deleting —
   * behaves identically in both reels.
   *
   * Nothing leaves the list and nothing moves: the clip on screen is still the
   * clip on screen, and a copy of it now exists on a shelf elsewhere. So there
   * is no `dropItem`, no navigation, and no re-fetch on either path.
   */
  const favoriteOpenFile = useCallback(
    (file: FileEntry) => favorite([file.key]),
    [favorite],
  );

  const submitNewFolder = useCallback(async () => {
    const name = (newFolder ?? "").trim();
    if (!name) {
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
  const overlayOpen = openKey !== null || reelPrefix !== null || moveTarget !== null;
  useEffect(() => {
    if (overlayOpen || selection.count === 0) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") selection.clear();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [overlayOpen, selection]);

  const crumbs = data?.breadcrumbs ?? [{ name: "/", prefix: ROOT_PREFIX }];
  const atRoot = prefix === ROOT_PREFIX;
  const isEmpty =
    !loading && !error && data && data.folders.length === 0 && data.files.length === 0;

  return (
    <div className="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-6 p-4 sm:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Text variant="display">Studio</Text>
          <Text variant="caption" tone="muted">
            media library
          </Text>
        </div>

        <div className="flex items-center gap-2">
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
        where you are (back, breadcrumbs, the prefix) and what you can do here
        (sort, new folder, play). On any real path the breadcrumbs took the width
        and the four buttons wrapped underneath them anyway — in whatever order
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
          onClick={() => goToFolder(parentPrefix(prefix))}
        >
          <span aria-hidden="true">←</span> Back
        </Button>

        {/* Breadcrumbs.Root carries `w-full` of its own, so it needs a shrinking
            flex parent or it claims the row and wraps what follows beneath it. */}
        <div className="min-w-0 flex-1">
          <Breadcrumbs.Root>
            {crumbs.map((crumb, index, all) => (
              <Breadcrumbs.Item
                key={crumb.prefix}
                current={index === all.length - 1}
                href={folderPath(crumb.prefix)}
                onClick={(event: React.MouseEvent) => {
                  event.preventDefault();
                  goToFolder(crumb.prefix);
                }}
              >
                {crumb.name}
              </Breadcrumbs.Item>
            ))}
          </Breadcrumbs.Root>
        </div>

        {/* Clicking a folder navigates into it rather than opening an overlay, so
            this is that folder's "opened" copy affordance — and it belongs beside
            the path it copies rather than in the action row below. */}
        <CopyKeyButton value={data?.prefix ?? prefix} noun="prefix" />
      </div>

      <div className="flex flex-wrap items-center gap-2 border-y border-line py-2">
        <SortControl value={sort} onChange={setSort} />

        <div className="flex-1" />

        {/* An icon, like the copy control beside the path: "New folder" is a
            noun-shaped action with an icon everyone already knows, and spelling
            it out made it the widest thing in a row of three. The label lives on
            `aria-label` and `title`, so it is still there for a screen reader and
            for anyone who hovers. */}
        <button
          type="button"
          onClick={() => setNewFolder("")}
          aria-label="New folder"
          title="New folder"
          className="shrink-0 rounded-md p-2 text-muted transition-colors hover:bg-surface-alt hover:text-ink
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

        <Button size="sm" onClick={() => setReelPrefix(prefix)}>
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
            New folder in {prefix}
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
                key={folder.prefix}
                name={folder.name}
                prefix={folder.prefix}
                onOpen={() => goToFolder(folder.prefix)}
                onRename={(name) => run(renameFolder(folder.prefix, name))}
                onMove={() =>
                  setMoveTarget({ kind: "folder", prefix: folder.prefix, name: folder.name })
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

              {/* Picking the keepers out of a run is the whole reason to select
                  forty tiles at once, so the star belongs beside the bulk move
                  and delete. Only the favouritable ones are sent — in this grid
                  that is all or none, since a folder sits in one tree, but the
                  filter is what makes that a fact rather than an assumption. */}
              {favoritable.length > 0 && (
                <FavoriteButton
                  noun={`${favoritable.length} ${favoritable.length === 1 ? "file" : "files"}`}
                  onFavorite={() =>
                    favorite(favoritable.map((item) => item.key)).then(selection.clear)
                  }
                />
              )}

              {/* Media has no per-tile menu the way a row does — sixty thumbnails
                  with a control each is the crowding this grid exists to avoid —
                  so this bar is where a bulk move is reached from. */}
              <button
                type="button"
                onClick={() =>
                  setMoveTarget({
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
                key={file.key}
                file={file}
                selected={selection.selected.has(file.key)}
                selectionActive={selection.count > 0}
                onOpen={() => openFile(file)}
                onToggleSelect={(extend) => selection.toggleAt(index, extend)}
                onFavorite={
                  file.favorites_prefix ? () => favorite([file.key]) : undefined
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
                key={file.key}
                file={file}
                onOpen={() => openFile(file)}
                onRename={(name) => run(renameObject(file.key, name))}
                onMove={() =>
                  setMoveTarget({ kind: "objects", keys: [file.key], noun: file.name })
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
      {reelPrefix !== null ? (
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
          onFavorite={favoriteOpenFile}
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
            onFavorite={favoriteOpenFile}
          />
        )
      )}

      {/* A text file gets a page of its own, the way a clip does — same URL, same
          "this is the thing you came for" treatment — and unlike a clip it can be
          edited, because these are notes and prompts a person wrote. */}
      {openText && <TextPage file={openText} onClose={closeItem} onSaved={reload} />}

      {moveTarget && (
        <MovePicker
          noun={moveTarget.kind === "folder" ? moveTarget.name : moveTarget.noun}
          startPrefix={prefix}
          currentPrefix={prefix}
          // A folder cannot land inside itself, and the picker greys out the
          // branch rather than letting the request come back refused.
          forbiddenPrefix={moveTarget.kind === "folder" ? moveTarget.prefix : undefined}
          onMove={submitMove}
          onClose={() => setMoveTarget(null)}
        />
      )}

      {/* A share link to a key this folder does not hold — deleted upstream, or
          mistyped. The listing loaded fine, so this is specific and worth
          saying rather than silently showing the folder. */}
      {openKey && openIndex < 0 && !openText && !loading && !error && (
        <Alert.Root intent="warning">
          <Alert.Title>That file is not here any more</Alert.Title>
          <Alert.Description>
            Nothing in this folder matches {openKey}. It may have been renamed or deleted.
          </Alert.Description>
        </Alert.Root>
      )}
    </div>
  );
}
