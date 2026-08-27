import { useCallback, useMemo } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { FolderBrowser, type BrowserNav } from "../components/browse/FolderBrowser";
import { DEFAULT_SORT, isSortOrder, type FileEntry, type SortOrder } from "../types";
import { folderPath, objectPath, targetFromPath, type FolderId } from "../utils/location";

/**
 * The library's file browser, at `/f`, `/f/<node_id>` and `/o/<node_id>`.
 *
 * **The URL is the state.** Nothing here mirrors the location into component
 * state: doing so is what makes browser back and a pasted link disagree, and
 * both have to work for a share link to mean anything. That is the whole of what
 * this page is now — the listing, the selection, the uploads and the viewer live
 * in `FolderBrowser`, which a character's and a project's Files tab render too.
 *
 * The split is not tidying. Those tabs cannot be driven by the URL — the address
 * bar is spent naming the entity — so the browser had to stop reaching for the
 * router itself, and this file is what took over doing it. See `BrowserNav`.
 */
export function BrowsePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const target = useMemo(() => targetFromPath(location.pathname), [location.pathname]);

  const sortParam = params.get("sort");
  const sort: SortOrder = isSortOrder(sortParam) ? sortParam : DEFAULT_SORT;

  const setSort = useCallback(
    (next: SortOrder) => {
      const nextParams = new URLSearchParams(params);
      if (next === DEFAULT_SORT) nextParams.delete("sort");
      else nextParams.set("sort", next);
      setParams(nextParams, { replace: true });
    },
    [params, setParams],
  );

  /**
   * `replace` is for the one navigation that is not a journey: leaving a folder
   * because it no longer exists. Pushing there would leave the deleted folder as
   * the entry behind you, so back would load an empty listing of something you
   * just destroyed. Every other move between folders is a real history entry,
   * because the browser's back button has to retrace browsing.
   */
  const goToFolder = useCallback(
    (nextId: FolderId, { replace = false }: { replace?: boolean } = {}) => {
      navigate({ pathname: folderPath(nextId), search: location.search }, { replace });
    },
    [location.search, navigate],
  );

  /**
   * Closing an *item* goes back rather than pushing the folder again.
   *
   * Opening it pushed a history entry, so closing should undo that entry —
   * otherwise open-then-close leaves a folder entry behind per item viewed, and
   * the browser's back button walks a trail of the same folder over and over.
   * Someone who arrived on a shared link has no entry to undo (`location.key` is
   * React Router's `"default"` for the first entry in a session), so that case
   * navigates to the folder instead of stepping out of the app.
   */
  const closeItem = useCallback(() => {
    if (location.key === "default") {
      const parent = target.kind === "folder" ? target.id : null;
      navigate({ pathname: folderPath(parent), search: location.search }, { replace: true });
    } else {
      navigate(-1);
    }
  }, [location.key, location.search, navigate, target]);

  const nav: BrowserNav = useMemo(
    () => ({
      target,
      sort,
      setSort,
      goToFolder,
      openFile: (file: FileEntry) =>
        navigate({ pathname: objectPath(file.id), search: location.search }),
      closeItem,
      // Scrolling the reel rewrites the URL rather than pushing to it. Twenty
      // clips scrolled past would otherwise be twenty back presses to escape.
      setCurrent: (file: FileEntry) =>
        navigate({ pathname: objectPath(file.id), search: location.search }, { replace: true }),
    }),
    [closeItem, goToFolder, location.search, navigate, sort, setSort, target],
  );

  return <FolderBrowser nav={nav} />;
}
