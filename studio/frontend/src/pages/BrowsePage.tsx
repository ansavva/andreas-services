import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { Alert, Breadcrumbs, Button, Input, Spinner, Text } from "@ansavva/design-system";

import {
  createFolder,
  deleteFolder,
  deleteObjects,
  renameFolder,
  renameObject,
} from "../apis/studio";
import { FileRow } from "../components/browse/FileRow";
import { FolderCard } from "../components/browse/FolderCard";
import { MediaTile } from "../components/browse/MediaTile";
import { SortControl } from "../components/browse/SortControl";
import { ConfirmDeleteButton } from "../components/common/ConfirmDeleteButton";
import { CopyKeyButton } from "../components/common/CopyKeyButton";
import { CodeViewer } from "../components/text/CodeViewer";
import { ReelView } from "../components/viewer/ReelView";
import { useAuth } from "../context/AuthContext";
import { copyLabel, useCopyToClipboard } from "../hooks/useCopyToClipboard";
import { useReel } from "../hooks/useReel";
import { useSelection } from "../hooks/useSelection";
import { useTree } from "../hooks/useTree";
import { DEFAULT_SORT, isSortOrder, type FileEntry, type SortOrder } from "../types";
import { ROOT_PREFIX, folderPath, objectPath, parentPrefix, targetFromPath } from "../utils/location";

export function BrowsePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { email, logout } = useAuth();

  /**
   * The URL is the state.
   *
   * `/projects/fred/runs/` is a folder and `/projects/fred/runs/x/output/clip.mp4`
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
  // subfolders — `projects/mr-p/` — still opens onto real media. Fetched lazily:
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
  const keysCopy = useCopyToClipboard();

  const copySelectedKeys = useCallback(() => {
    // One key per line, in grid order rather than the order they were picked:
    // this is going into a shell loop or a `--keys` argument, and the order you
    // happened to click in is not information.
    void keysCopy.copy(selection.selectedItems.map((item) => item.key).join("\n"));
  }, [keysCopy, selection.selectedItems]);

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
    async <T,>(work: Promise<T>): Promise<T> => {
      setActionError(null);
      try {
        const result = await work;
        reload();
        return result;
      } catch (err) {
        setActionError((err as Error).message);
        throw err;
      }
    },
    [reload],
  );

  const deleteSelected = useCallback(async () => {
    const keys = selection.selectedItems.map((item) => item.key);
    await run(deleteObjects(keys));
    selection.clear();
  }, [run, selection]);

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
  // reel and the code viewer each bind Escape to their own close, and clearing a
  // selection out from under one of them would be a keystroke doing two things
  // at once.
  const overlayOpen = openKey !== null || reelPrefix !== null;
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
            x-harness media library
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

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          {/*
            Up one folder, not browser-back.
            They are different journeys and both are wanted: back retraces how
            you got here, which after a shared link is nowhere, and after ten
            minutes of browsing is ten minutes of browsing. This goes *up the
            tree*, which is where "back" means to someone reading a folder they
            were linked into. The browser's own back button still works, because
            every navigation here is a real history entry.
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

          {/* Breadcrumbs.Root carries `w-full` of its own, so it needs a
              shrinking flex parent or it claims the row and wraps what follows
              beneath it. */}
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
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <SortControl value={sort} onChange={setSort} />

          {/* Clicking a folder navigates into it rather than opening an
              overlay, so this is that folder's "opened" copy affordance. */}
          <CopyKeyButton value={data?.prefix ?? prefix} noun="prefix" />

          <Button intent="ghost" size="sm" onClick={() => setNewFolder("")}>
            New folder
          </Button>

          <Button size="sm" onClick={() => setReelPrefix(prefix)}>
            Play reel
          </Button>
        </div>
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
                onDelete={() => run(deleteFolder(folder.prefix))}
              />
            ))}
          </div>
        </section>
      )}

      {media.length > 0 && (
        <section className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
            <Text variant="title">
              Media <span className="font-body text-sm text-muted">({media.length})</span>
            </Text>

            {/* Nothing here is ever disabled: until something is picked there
                is only "Select all", and the actions appear with the count
                they act on written into them. */}
            <div className="flex flex-wrap items-center gap-2">
              {selection.count > 0 && (
                <Text variant="caption" tone="muted" className="tabular-nums">
                  {selection.count} of {media.length} selected
                </Text>
              )}

              <Button
                intent="ghost"
                size="sm"
                onClick={selection.allSelected ? selection.clear : selection.selectAll}
              >
                {selection.allSelected ? "Select none" : "Select all"}
              </Button>

              {selection.count > 0 && (
                <>
                  {!selection.allSelected && (
                    <Button intent="ghost" size="sm" onClick={selection.clear}>
                      Clear
                    </Button>
                  )}
                  <Button size="sm" onClick={copySelectedKeys}>
                    {copyLabel(
                      keysCopy.status,
                      `Copy ${selection.count} ${selection.count === 1 ? "key" : "keys"}`,
                    )}
                  </Button>
                  <ConfirmDeleteButton
                    tone="bar"
                    noun={`${selection.count} ${selection.count === 1 ? "file" : "files"}`}
                    onConfirm={deleteSelected}
                  />
                </>
              )}
            </div>
          </div>

          {selection.count === 0 && (
            <Text variant="caption" tone="muted">
              Pick tiles to copy or delete their keys — shift-click to take a range.
            </Text>
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

      {openText && <CodeViewer file={openText} onClose={closeItem} />}

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
